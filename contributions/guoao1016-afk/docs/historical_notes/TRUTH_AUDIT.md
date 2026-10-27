# Independent JOB-light true-count audit

The 2026-10-27 audit executes the original 70 `SELECT COUNT(*)` queries against
the existing six full IMDb tables in the dedicated local PostgreSQL database.
The actual answer is obtained from the SQL result before comparison to the
official CSV. EXPLAIN estimates and official truth values never populate the
actual-count field.

## Running the visible audit

From the repository root, after restoring the project environment if its parent
directory has moved:

```powershell
$env:DEEPDB_PG_HOME='D:\codex\deepdb-postgresql-20261027'
.venv/Scripts/pythonw.exe code/recompute_joblight_truth.py
```

The native window displays the current SQL, completed/matched totals, elapsed
time for the active query and a scrolling result log. It starts automatically
after eight seconds. The Stop and Save button requests cancellation and saves
completed results; the window stays open after completion.

The audit starts the saved database if needed and stops it after completion
only if this run started it. Credentials are read from the local tools folder
and are never displayed or included in the handoff. It uses a read-only
connection, sequential queries, `max_parallel_workers_per_gather=0`,
`work_mem=32MB`, `jit=off` and `temp_file_limit=4GB`. The first attempt has a
120-second timeout; unresolved queries can receive one retry of up to 600
seconds. The overall limit is two hours.

Three large queries hit the initial time or 4GB temporary-file limits. After
68 queries had matched, the audit's own SQL connection was ended to preserve
results and change resource settings. The initial run metadata and exact script
are retained under output history. With `TRUTH_AUDIT_BIG_RETRY=1`, the visible
window resumes only unresolved queries, using work_mem=64MB, at most two parallel
workers per query, temp_file_limit=16GB, enable_nestloop=off, and 600/900-second
attempt limits. Queries and reference counts remain unchanged. Timing results
therefore span different execution configurations and are descriptive only.

This completed 69 original SQL queries. The remaining query (ID 59) exceeded
the direct-execution limits, so its exact count was obtained by equivalent
grouped SQL: count each filtered child table per movie_id, join these groups
to the filtered title rows, multiply the child multiplicities per title, and
sum. This is exact for the validated inner-star equijoins and single-table
numeric predicates; no statistical-independence assumption or reference-answer
substitution is used. The transformation rejects unsupported query shapes.
It was cross-checked on IDs 0, 14, 34 and 57 against actual original SQL results.
The result CSV identifies execution_method and preserves executed_sql. Report
the outcome as 69 direct original SQL successes plus one equivalent exact SQL
calculation, not 70 successful original-query executions.

Query SQL, IDs and file hashes must match the previous PostgreSQL estimate
experiment. All six table counts are checked against the source-data audit.
Successful completed queries may be resumed from the existing result CSV after
matching SQL/IDs/official counts; attempts remain in an append-only log.

## Outputs and checks

`output/truth_audit_20261027/` stores `truth_counts.csv`, `attempts.jsonl`,
`run.json`, `progress.log` and `verification.json`. After all queries pass,
`../tools/finalize_truth_audit.py` independently verifies the saved records,
exports a standard recomputed-truth CSV, creates bilingual reports/plots and
adds folder 06 to the local handoff. It preserves the original handoff ZIP and
creates a new ZIP whose name indicates that the full count audit is included.

No raw data, database credentials or model binaries are packaged. This audit
independently recomputes reference answers by SQL on the same imported dataset;
it is not an independent team, independent SQL-engine implementation, or
different-dataset audit. Single-run COUNT timings include actual execution and
client return and must not be compared directly with model estimation latency
as a query-execution speedup.

## Local path repairs

The project moved to `<LOCAL_PROJECT>`. The virtual
environment's Python home was updated, retaining its previous config backup.
A new ASCII junction, `D:/codex/deepdb-postgresql-20261027`, points to the current
`tools/postgresql` directory; the stale historical junction was left unchanged.
No data reimport or dependency download was needed.
