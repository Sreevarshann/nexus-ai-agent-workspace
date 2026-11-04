import io

import pandas as pd
import pytest
from httpx import AsyncClient

from nexus.domain.sqlguard import UnsafeSQL, guard_sql

CSV = (
    "\n".join(
        ["date,region,units,revenue,rating"]
        + [
            f"2024-{m:02d}-15,{r},{m * k},{m * k * 10.5},{3 + (m % 3) * 0.5}"
            for m in range(1, 13)
            for k, r in ((1, "North"), (2, "South"), (3, "East"))
        ]
    )
    + "\n"
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dataset",
        "SELECT region, sum(revenue) FROM dataset GROUP BY 1",
        "WITH t AS (SELECT * FROM dataset) SELECT count(*) FROM t",
        "SELECT * FROM dataset WHERE region = 'North' LIMIT 3",
    ],
)
def test_guard_allows_read_only_queries(sql: str) -> None:
    out = guard_sql(sql)
    assert "LIMIT" in out.upper()


@pytest.mark.parametrize(
    "sql,why",
    [
        ("DROP TABLE dataset", "SELECT"),
        ("DELETE FROM dataset", "SELECT"),
        ("INSERT INTO dataset VALUES (1)", "SELECT"),
        ("SELECT 1; DROP TABLE dataset", "one statement"),
        ("SELECT * FROM read_csv('/etc/passwd')", "read_csv"),
        ("SELECT * FROM read_parquet('x.parquet')", "read_parquet"),
        ("SELECT getenv('HOME')", "getenv"),
        ("COPY dataset TO '/tmp/out.csv'", "SELECT"),
        ("ATTACH 'other.db' AS o", "SELECT"),
        ("SELECT * FROM information_schema.tables", "Qualified"),
        ("SELECT * FROM secrets", "Unknown table"),
        ("PRAGMA database_list", "SELECT"),
        ("SET enable_external_access=true", "SELECT"),
    ],
)
def test_guard_rejects_unsafe_sql(sql: str, why: str) -> None:
    with pytest.raises(UnsafeSQL) as e:
        guard_sql(sql)
    assert why.lower() in str(e.value).lower()


async def upload(client: AsyncClient) -> dict:
    r = await client.post("/api/datasets", files={"file": ("sales.csv", CSV.encode())})
    assert r.status_code == 201, r.text
    return r.json()


async def test_profile_matches_pandas(client: AsyncClient, user: dict) -> None:
    ds = await upload(client)
    df = pd.read_csv(io.StringIO(CSV))
    cols = {c["name"]: c for c in ds["columns"]}
    assert ds["row_count"] == len(df)
    assert cols["date"]["kind"] == "temporal" and cols["region"]["kind"] == "categorical"
    assert cols["revenue"]["mean"] == pytest.approx(df.revenue.mean())
    assert cols["units"]["max"] == df.units.max()


async def test_operations_compute_correct_values(client: AsyncClient, user: dict) -> None:
    ds = await upload(client)
    df = pd.read_csv(io.StringIO(CSV))
    agg = (
        await client.post(
            f"/api/datasets/{ds['id']}/operation",
            json={
                "operation": {
                    "op": "aggregate",
                    "group_by": ["region"],
                    "metrics": [{"column": "revenue", "agg": "sum"}],
                }
            },
        )
    ).json()
    got = {r[0]: r[1] for r in agg["rows"]}
    assert got == pytest.approx(df.groupby("region").revenue.sum().to_dict())
    assert agg["checks"][0]["passed"] is True

    ts = (
        await client.post(
            f"/api/datasets/{ds['id']}/operation",
            json={
                "operation": {
                    "op": "timeseries",
                    "date_column": "date",
                    "granularity": "quarter",
                    "metric": {"column": "units", "agg": "sum"},
                }
            },
        )
    ).json()
    assert len(ts["rows"]) == 4 and sum(r[1] for r in ts["rows"]) == df.units.sum()

    filt = (
        await client.post(
            f"/api/datasets/{ds['id']}/operation",
            json={
                "operation": {"op": "aggregate", "metrics": [{"column": "*", "agg": "count"}]},
                "filters": [{"column": "region", "op": "=", "value": "North"}],
            },
        )
    ).json()
    assert filt["rows"][0][0] == 12

    corr = (
        await client.post(
            f"/api/datasets/{ds['id']}/operation",
            json={"operation": {"op": "correlation", "x": "units", "y": "revenue"}},
        )
    ).json()
    assert corr["insights"]["pearson_r"] == pytest.approx(df.units.corr(df.revenue), abs=1e-4)


async def test_unknown_column_is_rejected(client: AsyncClient, user: dict) -> None:
    ds = await upload(client)
    r = await client.post(
        f"/api/datasets/{ds['id']}/operation",
        json={"operation": {"op": "aggregate", "group_by": ["nope"], "metrics": [{"column": "revenue", "agg": "sum"}]}},
    )
    assert r.status_code == 422 and "Unknown column" in r.json()["detail"]


async def test_every_catalog_operation_executes(client: AsyncClient, user: dict) -> None:
    from nexus.agents.analyst import build_catalog
    from nexus.data.analysis import AnalysisPlan, execute_operation
    from nexus.db import session_scope
    from nexus.models import Dataset

    ds = await upload(client)
    async with session_scope() as db:
        row = await db.get(Dataset, __import__("uuid").UUID(ds["id"]))
    catalog = build_catalog(row)
    assert len(catalog) >= 8
    plan = AnalysisPlan.model_validate({"objective": "all", "operations": [c["operation"] for c in catalog[:6]]})
    for op in plan.operations:
        assert execute_operation(row.parquet_path, row.columns, op)["rows"]


async def test_guarded_query_and_export(client: AsyncClient, user: dict) -> None:
    ds = await upload(client)
    q = await client.post(
        f"/api/datasets/{ds['id']}/query", json={"sql": "SELECT region, count(*) n FROM dataset GROUP BY 1 ORDER BY 1"}
    )
    assert q.json()["rows"] == [["East", 12], ["North", 12], ["South", 12]]
    bad = await client.post(f"/api/datasets/{ds['id']}/query", json={"sql": "SELECT * FROM read_csv('/etc/hosts')"})
    assert bad.status_code == 422
    exp = await client.post(
        f"/api/datasets/{ds['id']}/export", json={"sql": "SELECT * FROM dataset WHERE region='East'"}
    )
    assert exp.headers["content-type"].startswith("text/csv") and exp.text.count("\n") == 13


async def test_dataset_upload_validation(client: AsyncClient, user: dict) -> None:
    assert (await client.post("/api/datasets", files={"file": ("x.json", b"{}")})).status_code == 422
    assert (await client.post("/api/datasets", files={"file": ("x.xlsx", b"not a zip")})).status_code == 422
    assert (await client.post("/api/datasets", files={"file": ("x.csv", b"")})).status_code == 422
