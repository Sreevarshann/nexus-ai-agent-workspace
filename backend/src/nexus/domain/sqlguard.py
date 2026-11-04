"""Read-only SQL guard for dataset queries (user-written or model-written).

Accepts exactly one SELECT-style query over the table ``dataset`` (plus its own CTEs). Rejects DDL/DML,
PRAGMA/SET/ATTACH/COPY/INSTALL/LOAD, table functions and file/network/system functions. DuckDB is also run
with external access disabled and a locked configuration, so this is defence in depth, not the only layer.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

DATASET_TABLE = "dataset"
MAX_LIMIT = 5000

BLOCKED_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_text",
    "read_blob",
    "parquet_scan",
    "csv_scan",
    "glob",
    "getenv",
    "current_setting",
    "pragma",
    "duckdb_settings",
    "duckdb_extensions",
    "duckdb_databases",
    "duckdb_tables",
    "duckdb_columns",
    "query",
    "query_table",
    "sniff_csv",
    "load",
    "install",
    "copy",
    "export",
    "import",
    "attach",
    "system",
    "shell",
}
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Merge,
    exp.Copy,
    exp.Set,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Use,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Into,
)


class UnsafeSQL(ValueError):
    pass


def guard_sql(sql: str, limit: int = MAX_LIMIT) -> str:
    sql = sql.strip().rstrip(";")
    if not sql:
        raise UnsafeSQL("Empty query")
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"Could not parse SQL: {str(e).splitlines()[0]}") from e
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeSQL("Exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeSQL("Only SELECT queries are allowed")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQL(f"{type(node).__name__} is not allowed")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name in BLOCKED_FUNCTIONS:
                raise UnsafeSQL(f"Function {name}() is not allowed")
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise UnsafeSQL("Table functions are not allowed")
        if table.db or table.catalog:
            raise UnsafeSQL("Qualified table names are not allowed")
        if table.name.lower() not in cte_names | {DATASET_TABLE}:
            raise UnsafeSQL(f"Unknown table '{table.name}'. Query the table named `dataset`.")
    existing = tree.args.get("limit")
    if existing is None:
        tree = tree.limit(limit)
    return tree.sql(dialect="duckdb")
