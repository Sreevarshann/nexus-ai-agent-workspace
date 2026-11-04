"""Sandboxed DuckDB execution over a single uploaded dataset."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from nexus.config import get_settings
from nexus.domain.sqlguard import guard_sql


class QueryError(RuntimeError):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    sql: str
    row_count: int


def _clean(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


def sql_literal(value: str | Path) -> str:
    """Quote a server-generated path for DDL statements, which DuckDB cannot parameterise."""
    return "'" + str(value).replace("'", "''") + "'"


def open_sandbox(parquet_path: str | Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:", config={"threads": 2, "memory_limit": "512MB"})
    con.execute(f"CREATE TABLE dataset AS SELECT * FROM read_parquet({sql_literal(parquet_path)})")
    # From here on: no filesystem/network, and settings cannot be changed back.
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def run_query(parquet_path: str | Path, sql: str, params: list[Any] | None = None, *, guarded: bool = True,
              limit: int = 5000) -> QueryResult:
    safe_sql = guard_sql(sql, limit) if guarded else sql
    con = open_sandbox(parquet_path)
    timer = threading.Timer(get_settings().query_timeout_s, con.interrupt)
    timer.start()
    try:
        cur = con.execute(safe_sql, params or [])
        cols = [d[0] for d in cur.description or []]
        rows = [[_clean(v) for v in r] for r in cur.fetchall()]
    except duckdb.InterruptException as e:
        raise QueryError(f"Query exceeded {get_settings().query_timeout_s:.0f}s time limit") from e
    except duckdb.Error as e:
        raise QueryError(str(e).split("\n")[0][:400]) from e
    finally:
        timer.cancel()
        con.close()
    return QueryResult(columns=cols, rows=rows, sql=safe_sql, row_count=len(rows))
