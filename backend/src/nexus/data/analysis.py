"""Typed analytical operations compiled to SQL from validated column names.

The AI analyst never writes free-form code: it selects operations from this closed set, the server
validates every column reference against the dataset schema and executes deterministic SQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from nexus.data.engine import QueryResult, run_query

Agg = Literal["sum", "avg", "min", "max", "count", "median"]
Granularity = Literal["day", "week", "month", "quarter", "year"]


class Metric(BaseModel):
    column: str = Field(description="Numeric column, or '*' with agg=count")
    agg: Agg = "sum"


class Condition(BaseModel):
    column: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "in", "contains"]
    value: str | float | int | list[str | float | int]


class AggregateOp(BaseModel):
    op: Literal["aggregate"] = "aggregate"
    title: str = ""
    group_by: list[str] = Field(default_factory=list, max_length=2)
    metrics: list[Metric] = Field(min_length=1, max_length=4)
    order: Literal["desc", "asc"] = "desc"
    limit: int = Field(default=25, ge=1, le=500)
    chart: Literal["bar", "pie", "none"] = "bar"


class TimeSeriesOp(BaseModel):
    op: Literal["timeseries"] = "timeseries"
    title: str = ""
    date_column: str
    granularity: Granularity = "month"
    metric: Metric
    split_by: str | None = Field(default=None, description="Optional categorical column for one line per value")
    chart: Literal["line", "area", "bar"] = "line"


class TopNOp(BaseModel):
    op: Literal["top_n"] = "top_n"
    title: str = ""
    column: str
    metric: Metric
    n: int = Field(default=10, ge=1, le=100)
    ascending: bool = False


class CorrelationOp(BaseModel):
    op: Literal["correlation"] = "correlation"
    title: str = ""
    x: str
    y: str
    chart: Literal["scatter", "none"] = "scatter"


class DistributionOp(BaseModel):
    op: Literal["distribution"] = "distribution"
    title: str = ""
    column: str
    bins: int = Field(default=12, ge=3, le=50)


class AnomalyOp(BaseModel):
    op: Literal["anomalies"] = "anomalies"
    title: str = ""
    date_column: str
    granularity: Granularity = "month"
    metric: Metric
    z_threshold: float = Field(default=2.0, ge=1.0, le=5.0)


Operation = Annotated[
    AggregateOp | TimeSeriesOp | TopNOp | CorrelationOp | DistributionOp | AnomalyOp, Field(discriminator="op")
]


class AnalysisPlan(BaseModel):
    """Plan produced by the analyst model."""

    objective: str = Field(description="One sentence restating what the user wants to learn")
    filters: list[Condition] = Field(default_factory=list, max_length=5)
    operations: list[Operation] = Field(min_length=1, max_length=6)


class AnalysisError(ValueError):
    pass


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class Compiler:
    def __init__(self, columns: list[dict[str, Any]]):
        self.cols = {c["name"]: c for c in columns}
        self.lower = {c["name"].lower(): c["name"] for c in columns}

    def col(self, name: str, kinds: tuple[str, ...] | None = None) -> str:
        real = self.cols.get(name) and name or self.lower.get(name.lower())
        if not real:
            raise AnalysisError(f"Unknown column '{name}'. Available: {', '.join(self.cols)}")
        if kinds and self.cols[real]["kind"] not in kinds:
            raise AnalysisError(f"Column '{real}' is {self.cols[real]['kind']}, expected {' or '.join(kinds)}")
        return real

    def metric(self, m: Metric) -> tuple[str, str]:
        if m.agg == "count":
            return "count(*)", "count"
        c = self.col(m.column, ("numeric",))
        return f"{m.agg}({_q(c)})", f"{m.agg}_{c}"

    def where(self, conds: list[Condition]) -> tuple[str, list[Any]]:
        parts, params = [], []
        for c in conds:
            col = _q(self.col(c.column))
            if c.op == "in":
                vals = c.value if isinstance(c.value, list) else [c.value]
                parts.append(f"{col} IN ({', '.join('?' for _ in vals)})")
                params.extend(vals)
            elif c.op == "contains":
                parts.append(f"CAST({col} AS VARCHAR) ILIKE ?")
                params.append(f"%{c.value}%")
            elif isinstance(c.value, list):
                raise AnalysisError(f"Operator {c.op} needs a single value")
            else:
                parts.append(f"{col} {c.op} ?")
                params.append(c.value)
        return (" WHERE " + " AND ".join(parts)) if parts else "", params


def _period(col: str, g: Granularity) -> str:
    return f"date_trunc('{g}', CAST({_q(col)} AS TIMESTAMP))"


def execute_operation(parquet: str | Path, columns: list[dict[str, Any]], op: Any,
                      filters: list[Condition] | None = None) -> dict[str, Any]:
    """Run one operation; returns {title, op, sql, columns, rows, chart, checks, insights}."""
    c = Compiler(columns)
    where, params = c.where(filters or [])
    checks: list[dict[str, Any]] = []
    chart: dict[str, Any] | None = None
    insights: dict[str, Any] = {}

    if isinstance(op, AggregateOp):
        groups = [c.col(g) for g in op.group_by]
        mexprs = [c.metric(m) for m in op.metrics]
        select = ", ".join([_q(g) for g in groups] + [f"{e} AS {_q(a)}" for e, a in mexprs])
        group = f" GROUP BY {', '.join(_q(g) for g in groups)}" if groups else ""
        order = f" ORDER BY {_q(mexprs[0][1])} {op.order.upper()}" if groups else ""
        res = run_query(parquet, f"SELECT {select} FROM dataset{where}{group}{order} LIMIT {op.limit}", params,
                        guarded=False)
        # Validation: for sum/count, grouped totals must reconcile with the ungrouped total
        if groups and op.metrics[0].agg in ("sum", "count") and len(res.rows) < op.limit:
            total = run_query(parquet, f"SELECT {mexprs[0][0]} FROM dataset{where}", params, guarded=False).rows[0][0]
            grouped = sum((r[len(groups)] or 0) for r in res.rows)
            ok = total is None or abs((total or 0) - grouped) <= 1e-6 * max(1.0, abs(total or 0))
            checks.append({"check": "group totals reconcile with overall total", "passed": ok,
                           "overall": total, "sum_of_groups": grouped})
        if groups and op.chart != "none":
            chart = {"type": op.chart, "x": groups[0], "y": [a for _, a in mexprs],
                     "series": groups[1] if len(groups) > 1 else None}
    elif isinstance(op, TimeSeriesOp):
        d = c.col(op.date_column, ("temporal", "categorical"))
        expr, alias = c.metric(op.metric)
        if op.split_by:
            s = c.col(op.split_by, ("categorical", "boolean"))
            sql = (f"SELECT {_period(d, op.granularity)} AS period, {_q(s)} AS series, {expr} AS {_q(alias)} "
                   f"FROM dataset{where} GROUP BY 1, 2 ORDER BY 1, 2")
        else:
            sql = (f"SELECT {_period(d, op.granularity)} AS period, {expr} AS {_q(alias)} "
                   f"FROM dataset{where} GROUP BY 1 ORDER BY 1")
        res = run_query(parquet, sql, params, guarded=False)
        chart = {"type": op.chart, "x": "period", "y": [alias], "series": "series" if op.split_by else None}
        if not op.split_by and len(res.rows) >= 2:
            first, last = res.rows[0][1], res.rows[-1][1]
            if first:
                insights["change_first_to_last_pct"] = round(100 * (last - first) / abs(first), 2)
            peak = max(res.rows, key=lambda r: r[1] or 0)
            insights["peak_period"], insights["peak_value"] = peak[0], peak[1]
    elif isinstance(op, TopNOp):
        col = c.col(op.column)
        expr, alias = c.metric(op.metric)
        res = run_query(parquet, f"SELECT {_q(col)}, {expr} AS {_q(alias)} FROM dataset{where} GROUP BY 1 "
                                 f"ORDER BY 2 {'ASC' if op.ascending else 'DESC'} LIMIT {op.n}", params, guarded=False)
        chart = {"type": "bar", "x": col, "y": [alias], "series": None, "horizontal": True}
    elif isinstance(op, CorrelationOp):
        x, y = c.col(op.x, ("numeric",)), c.col(op.y, ("numeric",))
        corr = run_query(parquet, f"SELECT corr({_q(x)}, {_q(y)}), count(*) FROM dataset{where}", params,
                         guarded=False).rows[0]
        insights["pearson_r"], insights["n"] = (round(corr[0], 4) if corr[0] is not None else None), corr[1]
        res = run_query(parquet, f"SELECT {_q(x)}, {_q(y)} FROM dataset{where} USING SAMPLE 500 ROWS", params,
                        guarded=False)
        if op.chart != "none":
            chart = {"type": "scatter", "x": x, "y": [y], "series": None}
    elif isinstance(op, DistributionOp):
        col = c.col(op.column, ("numeric",))
        sql = (f"WITH f AS (SELECT * FROM dataset{where}), "
               f"b AS (SELECT min({_q(col)}) lo, max({_q(col)}) hi FROM f) "
               f"SELECT round(lo + (hi - lo) / {op.bins} * least(floor(({_q(col)} - lo) / nullif(hi - lo, 0) "
               f"* {op.bins}), {op.bins - 1}), 4) AS bucket_start, count(*) AS count "
               f"FROM f, b WHERE {_q(col)} IS NOT NULL GROUP BY 1 ORDER BY 1")
        res = run_query(parquet, sql, params, guarded=False)
        chart = {"type": "bar", "x": "bucket_start", "y": ["count"], "series": None}
    elif isinstance(op, AnomalyOp):
        d = c.col(op.date_column, ("temporal", "categorical"))
        expr, alias = c.metric(op.metric)
        sql = (f"WITH s AS (SELECT {_period(d, op.granularity)} AS period, {expr} AS v FROM dataset{where} "
               f"GROUP BY 1), z AS (SELECT period, v, (v - avg(v) OVER ()) / nullif(stddev_samp(v) OVER (), 0) AS z "
               f"FROM s) SELECT period, v AS {_q(alias)}, round(z, 3) AS z_score, abs(z) >= {op.z_threshold} AS anomaly "
               f"FROM z ORDER BY period")
        res = run_query(parquet, sql, params, guarded=False)
        insights["anomalous_periods"] = [r[0] for r in res.rows if r[3]]
        chart = {"type": "line", "x": "period", "y": [alias], "series": None, "highlight": "anomaly"}
    else:
        raise AnalysisError(f"Unsupported operation {type(op).__name__}")

    return {"title": op.title or op.op.replace("_", " ").title(), "op": op.op, "sql": res.sql,
            "columns": res.columns, "rows": res.rows, "chart": chart, "checks": checks, "insights": insights}


def run_sql(parquet: str | Path, sql: str) -> QueryResult:
    """User / tool SQL: always passes the guard."""
    return run_query(parquet, sql, guarded=True)
