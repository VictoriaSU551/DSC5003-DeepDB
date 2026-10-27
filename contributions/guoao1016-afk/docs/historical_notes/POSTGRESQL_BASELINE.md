# Local PostgreSQL cardinality-estimation baseline

Date: 2026-10-15. This compares estimated counts, not query execution speed.

## Procedure

1. Obtain PostgreSQL Windows binaries from EDB's official distribution. The local
   archive is PostgreSQL 16.15-5; record the executable version and archive SHA256.
2. Keep the binaries and persistent database under `team project/tools/postgresql`.
   Windows initialization failed on the Chinese directory path. The local junction
   `D:\codex\deepdb-postgresql-local` provides an ASCII alias to that same directory.
3. Initialize a separate UTF-8/C-locale cluster, bound only to 127.0.0.1:55432,
   using a dedicated role and randomly generated password. Credentials are local
   under tools and must not be committed. No Windows service is installed.
4. Import all six full IMDb CSVs using COPY CSV with backslash as ESCAPE. Check
   source hashes and counts. Table definitions are the six corresponding blocks
   of `code/benchmarks/job-light/setup-sql/alternative_schema.sql`.
5. Add each table's primary key and applicable indexes from `setup-sql/fk.sql`.
   Despite its name, fk.sql contains CREATE INDEX statements. This experiment does
   not declare foreign-key constraints or extended statistics.
6. Run ANALYZE with default_statistics_target=100. Disable query parallelism and
   JIT. Use shared_buffers=512MB, work_mem=16MB and maintenance_work_mem=256MB.
   Full settings and version are in the result's run.json. Autovacuum is disabled
   for this dedicated experiment cluster; it is not a production configuration.
7. Run EXPLAIN (FORMAT JSON, SUMMARY ON) on the original 70 SELECT COUNT(*) queries.
   Read Plan Rows from the sole child of the top Aggregate. The top Aggregate's
   one output row is not the cardinality of the underlying join. No workload
   query is executed. Each query gets one warmup and five measured EXPLAIN calls.
8. Match ordered query strings and official truths to all nine previously verified
   DeepDB runs, recompute q-error, save raw plans, summaries and bilingual plots.

## Local commands

From the project directory, with the local alias already created:

```powershell
$env:DEEPDB_PG_HOME='D:\codex\deepdb-postgresql-local'
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe -u code/postgres_baseline.py
.venv/Scripts/python.exe ../tools/report_postgresql_baseline.py
```

The first script skips a completed PASS result. Inspect and preserve prior
records before intentionally running a different configuration. The reporting
helper currently resides in the parent tools folder and is not yet packaged for
GitHub submission.

Results: `output/postgresql_baseline_20261015/`. Large database files and local
credentials remain outside the Git checkout. Bilingual figures/reports are in
the parent `学习记录/图表与解释` directory. No files have been pushed to GitHub.

## Interpretation boundaries

- Official ground truths are used. This does not independently recompute all 70
  true counts; table row counts alone are not workload query answers.
- PostgreSQL Planning Time, client EXPLAIN time and historical DeepDB estimator
  latency measure different scopes. Do not report an execution speedup.
- One PostgreSQL version/configuration and one ANALYZE snapshot are studied.
  This is not an exact match to every setting in the paper.
- The accuracy plot uses the original seed 1 models. The report also discloses
  all nine runs to avoid relying solely on one selected seed.

References:
- https://www.enterprisedb.com/download-postgresql-binaries
- https://www.postgresql.org/docs/16/using-explain.html
- https://www.postgresql.org/docs/16/sql-analyze.html
- https://www.postgresql.org/docs/16/sql-copy.html
