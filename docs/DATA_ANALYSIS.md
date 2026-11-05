# Data analysis

1. **Ingest**: CSV via DuckDB `read_csv_auto`, XLSX via pandas/openpyxl → Parquet. Row cap
   `NEXUS_MAX_DATASET_ROWS`, upload cap 25 MB, magic-byte checks.
2. **Profile**: DuckDB computes per-column type, kind, nulls, approximate distinct count, min/max/mean/std/median
   and top values. Displayed verbatim in Data Lab → Profile.
3. **Sandbox**: every query runs in a fresh in-memory DuckDB connection that loads only that Parquet file, then
   sets `enable_external_access = false` and `lock_configuration = true`, with a 512 MB memory limit, 2 threads and
   an interrupt timer (`NEXUS_QUERY_TIMEOUT_S`).
4. **SQL guard** (`nexus/domain/sqlguard.py`, sqlglot): exactly one `SELECT`/`WITH` statement; no DDL/DML, PRAGMA,
   SET, ATTACH, COPY; no table functions; a deny-list of file/system functions; only the table `dataset` (and the
   query's own CTEs); a `LIMIT` is added. Evaluated: 8/8 unsafe queries blocked, 3/3 safe allowed.
5. **Typed operations** (`nexus/data/analysis.py`): `aggregate`, `timeseries` (with split), `top_n`, `correlation`,
   `distribution`, `anomalies` (z-score). Column names are validated against the schema and quoted; filter values
   are bound parameters. Grouped sums are reconciled against the ungrouped total.
6. **AI analyst**: a catalog of valid operations is derived from the profile; the local model only *selects* catalog
   ids (structured output). If its selection is unusable a keyword heuristic is used and the UI says so. DuckDB
   computes the values; the model then narrates them, citing `[D#]`. The model never writes code or SQL that is
   executed unguarded, and no Python execution is offered.

Measured numeric correctness against pandas on the sample dataset: 4/4 checks pass (`evals/results/latest.md`).
