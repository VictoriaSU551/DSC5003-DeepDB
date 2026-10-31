# Independent scalar-oracle uniform title-key baseline

This is `LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY_V1`. It is **not** the identified implementation/configuration of DeepDB's author-reported Perfect Selectivities method. [DeepDB §6.1](https://www.vldb.org/pvldb/vol13/p992-hilprecht.pdf) defines an oracle for single-table cardinalities but does not publish the cross-table combination driver (local extracted lines 1052–1056). Neither matching a historical summary nor these local results identifies that missing formula.

## Registered scientific contract

Only the exact existing 70 JOB-light SQL statements are admitted (physical SHA256 `e61da91710ce62d3669be70a8ded2499c6de1d759fcfac9a954b939465e76fdb`). Their grammar is COUNT(*), two to five distinct tables, integer conjunction filters, and a complete title.id-to-child.movie_id star. There are exactly 50 distinct single-table conjunctions including unfiltered ones. Six parameterized single-table aggregate queries collect the 50 scalar counts; none evaluates a multi-table target COUNT. Five separate FK checks are assumption tests, not training labels.

For a query with title predicate F and child predicates G_i, the **predeclared local approximation** is

`filtered_title_count(F) * product(filtered_child_count(G_i) / unfiltered_title_count)`.

Counts are nonnegative Python integers, arithmetic is `fractions.Fraction`, and numerator/denominator are serialized as decimal strings. Zero stays exactly 0/1. This assumes child foreign keys are distributed uniformly across the complete title key domain and ignores correlations between tables. It retains each whole within-table conjunction, including correlation between predicates on the same table. It preserves duplicate child-row multiplicity. A correlated toy has exact join COUNT=2 and an estimate 3/4: an intentional approximation, not a claimed exact join oracle.

Unique, non-NULL id primary keys and no NULL/orphan movie_id references are strict acceptance assumptions. Actual built-in integer/numeric column type OIDs are recorded and validated; COPY binary bytes are never manually decoded as presumed int4 values. SQL NULL predicate semantics are PostgreSQL's own semantics. Unsupported SQL, missing joins, duplicate aliases/joins, incomplete counts and negative/noninteger counts fail closed.

Evaluation is separate: `full_scalar_oracle_audit.qerror` explicitly floors both evaluation operands at 1. It never rewrites raw predictions and has no path back into estimation. This candidate does not load a multi-table truth file or generate Table 1 error metrics. Subsequent metric/table integration must bind its evaluation labels independently.

## Source and database boundary

The already sealed raw manifest and historic six-table PostgreSQL import receipts are pinned, alongside the frozen import driver's source. No raw CSV is scanned by this implementation. These receipts are provenance, **not a retrospective proof of current database all-column equality to original CSVs**.

Actual execution records the current six relations' schema/type/valid-PK identity and two matching binary COPY hashes of all query-relevant integer/numeric columns plus id/movie_id, ordered by id. The full current query-column projection is included; text columns unused by these queries are not. The matching snapshots establish the consumed query-column population during this run, within the stated historic import lineage. They do not add an original-CSV all-field identity claim. The source-bound plan and every result preserve that limitation.

The collector only connects to existing `127.0.0.1:55432/deepdb_job`, PostgreSQL 11.5, under the pinned project cluster and executable. It temporarily removes/restores PG* environment settings, disables loopback SSL and explicitly points libpq to an enforced nonexistent local password file: no external service/options/password file is silently consumed. It has no install/start/stop/import/schema-change API. The operator ROOT starts/stops PostgreSQL separately, in an approved exclusive resource window. psycopg2 set_session configures its own implicit REPEATABLE READ READ ONLY transaction; SHARE locks on all six tables precede the first SELECT. It uses SELECT, COPY TO and transaction-local settings; rollback/connection close release locks. PostgreSQL's read-only mode does not mean the server never writes hint bits or other internal pages.

The current client uses <=512 MiB RSS, requires >=5 GiB available memory at startup and >=1 GiB while running, and >=8 GiB free disk. PostgreSQL runs serially with work_mem 16 MiB, temp_file_limit 1 GiB, statement_timeout 600 s, and lock_timeout 5 s; the total collection window is capped at 1800 s. The temporary-file cap permits exact DISTINCT-id assumption counting without pretending it is free. Binary snapshots are streamed into a digest, with a 2 GiB per-table transfer cap; no snapshot rows are written to output. All timing includes validation/collection as described by each receipt, not free oracle latency. The resource monitor cancels only its connection's statement and never stops an adopted server. A monitor failure permanently blocks every later SQL/COPY operation and every later COPY write block, even when cancellation occurred while the backend was idle. Checks surround cursor operations and COPY writes; cancellation failure, a monitor thread remaining alive, or a join exception prevents PASS and leaves the run TAINTED after rollback/close. Its budget does not claim to measure the entire adopted server process tree.

## Exact authorization and lifecycle

`plan` builds a candidate by hashing current code, this protocol, the workload, historic inputs, the complete installed project PostgreSQL runtime, project base Python source/native runtime, venv executable/config and psycopg2 installation. It does not connect. The complete discovered file map is regenerated for validation, preventing self-resealed dependency subsets. The direct native dependency is the exact absolute `C:/Windows/System32/kernel32.dll` used both by the physical inventory and `ctypes.WinDLL`; a different `SystemRoot` environment value cannot select the recorded asset. It is the only permitted project-external artifact. This is a direct-import closure, not all transitive Windows components.

The run requires the exact current plan plus a ROOT receipt with status `APPROVED_BY_ROOT_FOR_SINGLE_SCALAR_ORACLE_RUN`, matching binding and original plan path/bytes/SHA, an explicit review reference, and `exclusive_window: true`. A template remains PENDING and cannot authorize execution. There is no permanent False execution flag, no automatic approval, and no database action during import/default verification.

Each binding claims a new `output/full/scalar_oracle/runs/<binding-prefix>/` directory atomically. Existing directories are refused, even without a lifecycle file. RUNNING is persisted before collection; any exception produces TAINTED, and restoring old inputs cannot resume that namespace. A later retry requires a new explicit `--attempt` identity, a new source-bound plan and a new ROOT approval, while preserving the failed namespace; it does not require editing frozen code. Before publishing PASS, the producer rechecks current physical inputs and invokes independent receipt/arithmetic validators. The final self-seal binds the exact six required JSON artifacts and itself; it is integrity evidence, not a signature establishing authenticity against deliberate wholesale forgery.

`full_scalar_oracle_audit.verify()` is strictly offline. It checks the exact nonempty file set, physical uniqueness, hashes/self-seal, PASS lifecycle, original ROOT approval, current full dependency closure, all 50 scalars/11 executed requests, schema/snapshot/resource scope and all 70 exact fractions. It imports no database driver, launches no process, performs no query and writes nothing. Missing or TAINTED evidence fails. A result remains a local method variant; author-method and full-paper completion flags stay false.

## Commands for a later ROOT-reviewed window

These are documentation, not operations performed during candidate implementation:

```powershell
.venv/Scripts/python.exe -B code/full_scalar_oracle_run.py plan --plan output/full/scalar_oracle/plans/candidate.json
# ROOT independently reviews candidate; creates a separate explicit approval JSON.
.venv/Scripts/python.exe -B code/full_scalar_oracle_run.py run --plan output/full/scalar_oracle/plans/candidate.json --approval output/full/scalar_oracle/approval.json
.venv/Scripts/python.exe -B code/full_scalar_oracle_audit.py
```

Only new file-scoped pure/mock tests are run before that review. No actual plan, database connection, 50-count execution, source CSV scan, model invocation or baseline metric is created in this implementation phase.

The original reviewed candidate remains byte-for-byte in `output/full/scalar_oracle/review/candidate_v1/source_snapshot/`, with its own freeze manifest. Candidate v2 closes the independently reproduced idle-cancellation and SystemRoot/DLL-identity defects; it does not rewrite v1 evidence or add scientific results.

Candidate v3 follows the first actual v2 connection: PostgreSQL 11 returned `inet_server_addr()::text` as `127.0.0.1/32`, so the strict host-only identity check stopped before any COPY, scalar count or prediction. The failed attempt and v2 sources remain preserved. The single production change selects `host(inet_server_addr())`; the exact `127.0.0.1`, port, executable, cluster, read-only and isolation checks remain unchanged. A mock now reproduces the actual inet/text distinction. A fresh source-bound plan and ROOT approval are required; the old TAINTED namespace cannot be repaired or resumed.

Candidate v4 follows an actual v3 resource stop: the first `cast_info` snapshot of 36,244,344 ordered rows exceeded the original 120-second per-statement limit. It did not reach scalar counting or prediction. The current collector uses a 600-second SQL statement cap, sent from the bound policy; this applies to its snapshot, schema, scalar and FK validation statements. The total collection cap remains 1800 seconds, and all memory, disk, per-table COPY-byte limits, per-block checks, cancellation and read-only constraints remain unchanged. Validation cost is still measured and is not an online query latency. A separate new plan/approval is required. Candidates v1-v3 used the original 120-second statement budget.
