"""Dataset ingestion (CSV/XLSX → Parquet) and profiling."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from nexus.config import get_settings
from nexus.data.engine import _clean, run_query, sql_literal
from nexus.rag.ingest import UploadRejected, safe_filename

NUMERIC = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
)
TEMPORAL = ("DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIME")


def kind_of(duck_type: str) -> str:
    t = duck_type.upper()
    if t.startswith(NUMERIC):
        return "numeric"
    if t.startswith(TEMPORAL):
        return "temporal"
    if t == "BOOLEAN":
        return "boolean"
    return "categorical"


def convert_to_parquet(user_id: uuid.UUID, filename: str, data: bytes) -> tuple[str, Path]:
    s = get_settings()
    filename = safe_filename(filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise UploadRejected("Datasets must be .csv or .xlsx")
    if not data:
        raise UploadRejected("File is empty")
    if len(data) > s.max_upload_bytes:
        raise UploadRejected(f"File exceeds {s.max_upload_bytes // (1024 * 1024)} MB limit")
    if suffix == ".xlsx" and not data.startswith(b"PK\x03\x04"):
        raise UploadRejected("File contents do not match its extension")
    if suffix == ".csv" and b"\x00" in data[:4096]:
        raise UploadRejected("CSV appears to be binary")

    out_dir = s.dataset_dir / str(user_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:16]
    raw = out_dir / f"{digest}{suffix}"
    raw.write_bytes(data)
    parquet = out_dir / f"{digest}-{uuid.uuid4().hex[:6]}.parquet"
    try:
        con = duckdb.connect(":memory:")
        if suffix == ".csv":
            con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv_auto({sql_literal(raw)}, sample_size=20000)")
        else:
            df = pd.read_excel(raw, sheet_name=0, engine="openpyxl")
            df.columns = [str(c) for c in df.columns]
            con.register("df", df)
            con.execute("CREATE TABLE t AS SELECT * FROM df")
        n = con.execute("SELECT count(*) FROM t").fetchone()
        if not n or n[0] == 0:
            raise UploadRejected("Dataset has no rows")
        if n[0] > s.max_dataset_rows:
            raise UploadRejected(f"Dataset has {n[0]:,} rows; limit is {s.max_dataset_rows:,}")
        con.execute(f"COPY t TO {sql_literal(parquet)} (FORMAT parquet)")
        con.close()
    except UploadRejected:
        raise
    except (duckdb.Error, ValueError) as e:
        raise UploadRejected(f"Could not parse dataset: {str(e).splitlines()[0][:300]}") from e
    finally:
        raw.unlink(missing_ok=True)
    return filename, parquet


def profile(parquet: str | Path) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    """Real column statistics computed by DuckDB."""
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW d AS SELECT * FROM read_parquet({sql_literal(parquet)})")
    row_count = con.execute("SELECT count(*) FROM d").fetchone()[0]  # type: ignore[index]
    schema = con.execute("DESCRIBE d").fetchall()
    columns: list[dict[str, Any]] = []
    for name, dtype, *_ in schema:
        q = f'"{name.replace(chr(34), chr(34) * 2)}"'
        kind = kind_of(dtype)
        nulls, distinct = con.execute(f"SELECT count(*) - count({q}), approx_count_distinct({q}) FROM d").fetchone()  # type: ignore[misc]
        col: dict[str, Any] = {
            "name": name,
            "type": dtype,
            "kind": kind,
            "nulls": int(nulls),
            "null_pct": round(100 * nulls / row_count, 2) if row_count else 0,
            "distinct": int(distinct),
        }
        if kind == "numeric":
            mn, mx, mean, std, med = con.execute(
                f"SELECT min({q}), max({q}), avg({q}), stddev_samp({q}), median({q}) FROM d"
            ).fetchone()  # type: ignore[misc]
            col.update(min=_clean(mn), max=_clean(mx), mean=_clean(mean), std=_clean(std), median=_clean(med))
        elif kind == "temporal":
            mn, mx = con.execute(f"SELECT min({q}), max({q}) FROM d").fetchone()  # type: ignore[misc]
            col.update(min=_clean(mn), max=_clean(mx))
        else:
            top = con.execute(f"SELECT {q}, count(*) c FROM d GROUP BY 1 ORDER BY c DESC LIMIT 5").fetchall()
            col["top"] = [{"value": _clean(v), "count": c} for v, c in top]
        columns.append(col)
    con.close()
    summary = {
        "numeric": [c["name"] for c in columns if c["kind"] == "numeric"],
        "categorical": [c["name"] for c in columns if c["kind"] == "categorical"],
        "temporal": [c["name"] for c in columns if c["kind"] == "temporal"],
        "missing_cells": sum(c["nulls"] for c in columns),
    }
    return int(row_count), columns, summary


def preview(parquet: str | Path, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    res = run_query(parquet, f"SELECT * FROM dataset LIMIT {int(limit)} OFFSET {int(offset)}", guarded=False)
    return {"columns": res.columns, "rows": res.rows}
