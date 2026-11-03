# LOCAL Verdict SSB implementation plan

This is the versioned implementation protocol. Candidate/unrun statements below
describe their implementation stage; current actual execution and acceptance
status is maintained in [FULL_REPRODUCTION_STATUS.md](FULL_REPRODUCTION_STATUS.md).

Goal: a separately configured original Verdict existing-sample controller for the accepted LOCAL SF500 population, with no change to frozen SF2/scientific sources and no execution during the local model/replay stage.

Architecture: compose pinned pure parsing/SQL/hash/COPY and project pg_ctl ownership functions with explicit LOCAL configuration, source/oracle and database operations. Do not copy the old runner or patch its DB/LIMITS/globals. Parent-model verification is lazy and unavailable until all explicitly pinned final publications exist. An executable plan additionally needs independently reviewed relation/row-width measurements and the separate 12GiB resource envelope.

Files and interfaces:

- `code/full_verdict_ssb_local.py`: `local_spec()`, `load_frozen()`, `moments_oracle(moment,N,n,queries)`, `collect_lineage(expected)`, `build_pilot_plan(expected)`, `build_plan(expected,measurement_descriptor,resource_review)` and strict read-only artifact contracts.
- `code/full_verdict_ssb_local_ops.py`: explicit `LocalDatabase(spec)` for connection/protected catalogs/import/SHARE-lock/snapshots; `LocalBudget(spec,home,stage)`; explicit CI/model/replay busy-process guard; shared pinned pg_ctl/ownership and bounded JVM operations only where their implicit constants match and are explicitly bound.
- `code/full_verdict_ssb_local_run.py`: `describe`, `pilot-plan`, `plan`, `pilot`, `run`, `verify`, `verify-pilot` CLI. `describe` does not inspect unfinished outputs. All execution requires an exact external approval, complete parent lineage, resource review and a fresh namespace. `verify` forbids DB/process/science and uses the shared native Windows fingerprint context.
- `code/full_verdict_ssb_local_bridge.java`: new fixed LOCAL DB/n/N context, retaining original JAR/public APIs and one execute per call. Do not modify the SF2 Java source/class.
- New `code/tests/test_full_verdict_ssb_local*.py`: pure/micro fixtures only in this phase.

Fixed invariants: LOCAL N=3,000,028,242; n=9,996,946; source ID a574cd95f8ba184c809c66e438c88f69ddb1ddcc7b984c9ea99bcbb4c476dcf9; 1,713 author differences; fresh V11 DB deepdb_verdict_ssb_local500_v11; three protected prior databases; full four dimensions; zero-row fact skeleton; fact-only n/N metadata and 100 partitions; 13 raw + six child SUMs per mode = 38 calls; exact13 signed-integer moment oracles; two-SUM difference only, no child population truth or adapter CI. Original p and DeepDB n/p stay separate.

Implementation sequence:

1. TDD explicit spec/SQL identities, early missing-parent rejection, moment integer/scale/NULL/duplicate/SQL mismatch gates and the distinction between profit and child truth.
2. TDD explicit LOCAL DB/protected set/schema/metadata, complete canonical COPY and before/after auxiliary snapshots, independent 12GiB budget and WAL LSN accounting. Reuse only a documented whitelist of frozen functions; test that SF2 DB/globals do not change.
3. Implement the new bridge and serial 38-call controller with original raw decoding/rewrites/errors, exact receipts and atomic RUNNING/TAINTED/PASS lifecycle. Execution and pilot remain unrun.
4. TDD exact manifest/command/query/mode/SQL/resource semantics, read-only forbidden-operation verifier, absence of parent seals, unapproved measurement and over-budget failures. No real PG/SQLite/JVM/model import or data generation in tests.
5. Freeze candidate source/test/protocol SHA and send root for independent review. No commit/push or actual pilot/formal launch by this agent.

Primary review risks: accidental use of a frozen function's SF2 implicit DB/N/n; scalar SQL NULL versus absent grouped rows; arbitrary re-sealed parent/measurement sets; omission or duplication of native calls; performance/storage claims extrapolated from SF2. Tests must pin these boundaries. Formal source/model/reverse/moments physical acceptance and actual relation-width measurement are deliberately missing until root completes and reviews those separate stages.

The candidate has not run PostgreSQL, SQLite, Javac, the original JVM engine, the resource pilot, or any parent-model verifier. Tests use synthetic integers, descriptors and process rows. They do read the already frozen small utility/SQL sources and the native OS fingerprint when testing the forbidden-operation verifier. No performance or formal resource feasibility is claimed.

The v3 parent request is an exact four-entry `source/model/canonical/reverse` descriptor map (`path`, `bytes`, `sha256`). All four final files must exist before any is hashed. The source and unchanged original model descriptors have fixed SHAs in `local_spec`. `canonical` is exactly `output/full/results/ssb_local_sf500_canonical_aqp_ci.json`; `reverse` must be that report's exact `<canonical-run>/reverse/verification.json`, inside the separate canonical namespace. Root explicitly binds the descriptors in the approved plan. The earlier failed9c reverse publication is history only and cannot be supplied as a current parent.

Before delegated imports,16 independent literal SHA pins cover the original13-source closure plus canonical provider `9c041ffc8ca40386ad9e3582fd81cb1f0e76fd3db1a337cb97bb686a521ff6b6`, canonical runner `36ff7385082662163fafe972747d70b6c83506e3d2db5e91eafbbaf243583012` and typed group adapter `48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c`. The original model's9c source pin is retained only as immutable historical provenance; it is never an acceptance call. The actually loaded canonical module must be the pinned physical source. Payload-provided hashes cannot select a new verifier.

Within forbidden DB/process/science and verified native-platform contexts, the collector invokes only `full_ssb_local_canonical.verify_canonical()` once. That verifier itself performs the complete original model/science/supervisor verification once. The collector inherits its actual full `parent_snapshot`, including the unchanged original `report`, and unions every physical descriptor from the original and canonical artifact closures. It does not reconstruct a PASS from selected summaries, accept an external skip/proof, invoke failed9c, or call the complete formal verifier again. It still independently checks all13 native integer moments and their raw TSV/process/seal. New lineage aliases are explicit: `parent_canonical` is the new result, `parent_reverse` is canonical.reverse, and `parent_formal` is the original da358 model report. Evaluation variant `CANONICAL_DECODED_GROUP_PROTOTYPE_V1`, adapter SHA,1,713 author differences, false author/full completion flags and `historical_reverse_accepted=false` are retained in lineage and the final read-only API. Original Verdict arithmetic, raw Q4 errors, child-oracle gaps and native95% CI remain unchanged. The only external artifact exceptions remain KERNEL32.dll and msvcrt.dll, with exact absolute path, bytes, SHA and `external_scope=windows_direct_native_import`; every other external path is refused.

Single-entry verification cost is explicit: `pilot-plan`, `build_plan`, public `verify_pilot` and public `verify` each call the full parent verifier **once** through frozen replay. A private fresh boundary proof carries this complete evidence through nested pilot/plan checks. Public APIs accept no skip flag or proof/cache. A new public entry always verifies afresh. `pilot` and `run` have two separate fresh boundaries (entry and exit); only final output validation reuses the just-completed exit proof. No result or artifact cache crosses these boundaries. Unique repeated descriptors are checked once within a collector, while conflicting repeats fail. This avoids four full parent validations per public plan/verify without weakening before/after checks. It is a code/fixture count, not a measured runtime promise.

Database and resource behavior is explicit. The LOCAL operation alone creates `deepdb_verdict_ssb_local500_v11`; it refuses an existing database and never adopts/reimports/replaces any prior database, including the failed V9 `deepdb_verdict_ssb_local500` and V10 `deepdb_verdict_ssb_local500_v10`. The three prior databases are protected by catalog identities, not a claim of per-row protected-data hashing. Only a proven controller-owned stopped project cluster may be started; pg_ctl uses the already reviewed file-handle logging and ownership cleanup. PG11.5 and fixed sealed JDK paths/JAR are verified. Python/Java connections request `extra_float_digits=3`, 16MiB work memory, 1GiB per-backend temp-file limit and 600s statement timeout; JVM heap is384MiB, metaspace192MiB, process RSS cap1GiB, timeout660s. The original shared cluster startup options remain bound in e141; connection-specific values override work memory for these sessions. No global database/system settings are changed.

Full four dimensions and the existing fact sample are copied in bounded10000-row chunks. Each committed table has an individual receipt, exact target row count and canonical all-field COPY bytes/row-count/SHA, preserving duplicate rows and string/NULL serialization. The complete import requires the five unique targets (15M customer,1M supplier,1.8M part,2556 dates,9996946 fact rows). The original fact relation remains empty. Only the fact has original uniform sample metadata and100 `verdict_vpart` partitions; dimensions have neither metadata nor auxiliary partition columns. Exact native float8 bits validate n/N. A SHARE lock covers the fact, full dimensions and both metadata tables through all38 serial original calls; before/after all-field and auxiliary COPY, schema, own catalog, partition histograms and protected catalogs must match. These checks are not replaced by an OID or COUNT-only assertion.

The candidate12GiB envelope is separate from the16GiB SSB source/model tree: own PG database≤8GiB, positive physical cluster WAL growth≤2GiB, positive global/database temp growth≤1GiB, new output/staging files≤1GiB, total≤12GiB, Python RSS≤512MiB. Startup requires≥4GiB available RAM and≥18GiB free disk. It does not use whole-drive free-space differences as owned storage. Generated WAL bytes are recorded from live LSN observations; that cumulative I/O counter is distinct from the positive retained-WAL storage cap. After owned shutdown, samples retain the last live LSN plus observation time and explicitly mark the monitor connection closed. Startup, imports, setup, each query and pilot relations use the independent busy-process guard covering model, canonical runner, CI runner, typed-group replay and scoped replay entrypoints. This is a bounded scan/check window, not an OS reservation against an unrelated new process.

Execution still requires an actual measured/reviewed allowance. The bounded read-only pilot reuses the accepted SF2 own database `deepdb_verdict_ssb`, under SHARE locks, solely to measure the five actual relation row counts, AVG/MAX pg_column_size and heap/index/total storage. It does not reconstruct SF2 SQLite, reimport, recompile, reregister, run the original engine or sample any data. Its own root-approved plan binds completed LOCAL parents plus source/runtime; its final receipt independently binds all eight required files, owned-server lifecycle/logs and resource semantics. A formal plan requires that exact completed pilot final descriptor and a separate root resource-review document linking its SHA, fixed limits, projected own-DB and total storage. A loose unsealed row-width JSON cannot enable formal execution. Extrapolations from SF2 are reviewed projections, not measured SF500 cost.

Review/run sequence (all commands below remain unrun in this candidate phase):

```powershell
.venv/Scripts/python.exe -B code/full_verdict_ssb_local_run.py pilot-plan --parents <complete_parent_descriptors.json> --output output/full/verdict_ssb/local_sf500/plans/pilot_plan.json
.venv/Scripts/python.exe -B code/full_verdict_ssb_local_run.py pilot --plan <pilot_plan.json> --review <root_measurement_approval.json> --review-sha256 <exact_SHA> --name <fresh_name> --start-project-postgres
.venv/Scripts/python.exe -B code/full_verdict_ssb_local_run.py verify-pilot --measurement output/full/verdict_ssb/local_sf500/measurements/<fresh_name>/final.json
.venv/Scripts/python.exe -B code/full_verdict_ssb_local_run.py plan --parents <complete_parent_descriptors.json> --measurement <completed_pilot_final.json> --resource-review <reviewed_projection.json> --output output/full/verdict_ssb/local_sf500/plans/formal_plan.json
.venv/Scripts/python.exe -B code/full_verdict_ssb_local_run.py run --plan <formal_plan.json> --review <root_execution_approval.json> --review-sha256 <exact_SHA> --name <fresh_formal_name> --start-project-postgres
.venv/Scripts/python.exe -B code/full_verdict_ssb_local_run.py verify --name <fresh_formal_name>
```

Root is sole actual launcher. Operational names require1--32 ASCII letters/digits/underscore/hyphen before expensive parent verification, reducing the fixed long Windows child-path risk; actual names should remain short. A fresh namespace is atomically claimed; exceptions persist TAINTED, budget and safe ownership diagnostics. No automatic failed-namespace recovery is provided. Prior SF2 v2/v3 failures, verified v4 receipts and the strict author-SF500 MISMATCH remain immutable. The default action is inert `describe`. CLI writers only accept a new path inside this LOCAL `plans/` or `audits/` tree and reject existing files, measurements and sealed run paths before expensive work.

The final read-only `verify(home)` returns `PASS_READONLY_LOCAL_VERDICT_EVIDENCE_WITH_AUTHOR_MISMATCH`, point gate/evaluation status, exact N/n, n/N,38-call count, scope/1713/false completion flags, and physical descriptors `final`, `plan`, `evaluation`. It launches no process, database, SQLite, model, compiler or inference. Its acceptance proves the complete evidence closure; the point gate can separately be false. Consumers must retain that distinction. `evaluation.json` keeps all raw calls/errors/groups/NULL/nonfinite CI states, raw compound-Q4 discrepancies and two-SUM adapter comparisons. Physical SUM children have neither a profit fulltruth nor an invented component oracle. Adapter confidence intervals remain unavailable. Full LOCAL truth is only a population-error reference; exact retained integer sum×N/n is the point-scaling oracle. Original generator p and DeepDB n/p are never substituted for Verdict n/N. No author-SSB fidelity or end-to-end3B sampling claim follows from a LOCAL baseline result.

Candidate v1 code verification: all37 pure/micro tests passed in0.70s with `.venv/Scripts/python.exe -m pytest code/tests/test_full_verdict_ssb_local.py code/tests/test_full_verdict_ssb_local_ops.py code/tests/test_full_verdict_ssb_local_run.py -q --basetemp=output/tmp/verdict_ssb_local_frozen_v1b`. The full log is `output/full/verdict_ssb/audits/local_candidate_tests_v1_final2.log`. Earlier module-missing and descriptor/process/snapshot/private-proof failures are retained separately, including `local_review_red.log`, `local_load_red.log`, `local_boundary_red.log` and `local_budget_raw_red2.log`. Negative fixtures cover exact external descriptor scope, absent final parent, CI/replay resource overlap, duplicate/missing five-table snapshots and wrong rows, raw-versus-resealed results, actual JVM argv, SQL, scale/NULL semantics, zero/extra manifests, immutable output namespaces, stale pilot code/runtime binding, final scope/stage flags, malformed JSON and resource/WAL counters. No SF2 science or actual LOCAL publication was reverified or rerun to obtain these test results.

Candidate v2 closes the independent delegated-verifier trust boundary and bounds fresh namespace names. Before changing candidate bytes, all nine v1 files were preserved byte-exactly under `output/full/verdict_ssb/audits/local_candidate_v1/source_snapshot/`, matching the original v1 freeze; its receipt/seal remain untouched. Two new boundary tests first failed on v1: a supplied model could repin a modified replay and reach a forbidden import;32-character name validation did not exist. Independent13-source pin rejection fixtures are also included. The new source closure includes these13 literal parent pins; no actual parent publication/replay, PG or JVM was invoked for this revision. V2 gets a separate freeze receipt and keeps v1 evidence as history, not an accepted current executable plan.

V2 verification:52 pure/micro tests passed in0.85s with the same three test files and `--basetemp=output/tmp/verdict_ssb_local_frozen_v2`; log `output/full/verdict_ssb/audits/local_candidate_tests_v2_final.log`. Pre-fix two-test failure is `local_delegate_red_v2.log`. A separate source-only check compared all13 current `.py` hashes to both the literal pins and `git show HEAD:<path>` byte streams; it imported no delegated scientific module and performed no parent verification. The first new actual parent validation and PG measurement still require ROOT's reviewed completed publications and exclusive resource window.

V3 changes only the parent acceptance/projection and busy-science names. Before editing, all nine v2 files were copied byte-exactly to `output/full/verdict_ssb/audits/local_candidate_v3/v2_source_snapshot/`; snapshot receipt SHA256 `037ac0de677bd3fba41c05dda48124046a7f61a5f9d6dd3e0454cb62daf7fd28`. The original v2 freeze remains unchanged. New tests first observed three failures for the four-parent contract and canonical-runner resource scan, then three more for omitted original/canonical artifact closures and a shadow-loaded provider. Pure fixtures prove one canonical call, full old/new physical union, every literal pin, wrong API flags/aliases/status/adapter/N/n rejection and no import of failed9c. The frozen Java bytes, old utility/scientific sources,38-query plan, moment formula, PG operation code and resource values are unchanged. Candidate v3 has not run any actual parent verifier, PG measurement, import, compiler, query or model operation. The separate v3 freeze records focused pure-test evidence; an executable plan still requires every original actual gate plus ROOT review and sole launch.

V5 explicitly consumes the independently reviewed canonical continuation. The nine V4 sources and freeze remain identified by `audits/local_candidate_v5/v4_preservation.json` and their existing V4 snapshots; no new source copies are added. All16 previous parent pins are retained and two fixed continuation source pins are added. After those checks, one lazy `full_ssb_local_continuation.verify_canonical()` call supplies the complete fresh original formal parent snapshot and accepted old-FORWARD/new-REVERSE artifact union. No old failed ROOT or reverse is promoted to PASS, and no second original formal F is called by this consumer.

The accepted canonical scope/status are now `LOCAL_SSB_SF500_CANONICAL_CONTINUATION` / `PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH`, with exact protocol `ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1`. The public result path remains unchanged; the reverse must be under `output/full/ssb/local_sf500_continuation/runs/` and share its directory with the new canonical report. That report must say `adopted_forward=true` and `forward_reexecuted=false`. The returned Verdict lineage binds those facts and `canonical_execution_protocol`, while preserving the unchanged full original model, source, native moments, N/n oracle, typed group adapter,1713 author differences and false author/full-paper flags. The three protected databases, original Java and38-call plan, SQL, resource limits and all numerical methods are unchanged.

The busy-science scanner also explicitly covers the actual `full_ssb_local_continuation_run.py` bootstrap, worker and supervisor names. Those names do not contain model/ci/replay/canonical, so the old regex would miss them. Six focused tests first observed the missing two pins, new reverse namespace rejection and three missed process names. Validation remains pure fixtures only: no actual parent F, process scan, PG, JVM, model, moments scan, scientific call or plan is performed. A new source-bound plan and ROOT's exclusive actual resource approval are still required.

V7 fixes a definition-import boundary in LOCAL metadata planning. The actual v6
`pilot-plan` reached the pinned continuation verifier, whose original physical
source verifier imports the pinned native generator module. That module's
top-level `import sqlite3` was rejected by the frozen SF2 audit guard, before
any SQLite connection or native operation. A pure regression reproduces that
exact native definition import through a single stub parent call, with the
real frozen guard and no actual parent F or data scan.

Only LOCAL `forbid_parent_operations` adapts this boundary. It first enters the
unchanged frozen `audit.forbid_science(core)`, then disables native `_sqlite3`
`connect`, `Connection` and `Cursor` and initializes only
the standard `sqlite3`/`sqlite3.dbapi2` definitions with those APIs disabled.
It guards the same three APIs on all three modules. Only these three already-loaded modules may bypass
the blanket SQLite import rejection. Other builtin imports retain the frozen
guard; dynamic PG imports and other SQLite module imports are rejected too.
All existing core, subprocess and OS operation blocks remain delegated to the
frozen guard. Cold initialization inside an already-active frozen guard is
covered too. SQLite APIs and both import hooks are restored on normal exit or
exception; freshly created wrapper modules recover their original native API
identities, including a completed child left cached by a failed package import.
A nested LOCAL guard restores its outer guard rather than exposing live APIs.
Negative tests replace native entry points with fail-fast tripwires,
so even an escaping test cannot create a real database. Native definitions,
ordinary imported aliases, constructors, process/PG bans and hook restoration
are covered. The original guard, parent/CI/native sources, Java/ops/runner,
moment arithmetic, resource limits and all accepted results remain unchanged.
V7 focused checks passed 47 tests (30 unrelated tests deselected) in 2.57s.
No actual F, PG/JVM, model, pilot or plan was run for this revision; ROOT alone
reviews the new source-bound metadata plan before actual baseline execution.

V8 addresses a separate cold standard-library definition dependency. In the
real v7 metadata attempt, importing sklearn's definitions eventually imported
`numpy.testing`, `unittest` and Windows asyncio. The stdlib declaration
`class Popen(subprocess.Popen)` failed because the frozen process guard correctly
replaced `subprocess.Popen` with its forbidden function. No process was started.
A pure test executes that exact sealed stdlib file under the unchanged guard
and retains the original TypeError as the reference behavior.

`load_frozen()` now prepares only `asyncio.windows_utils` and its ordinary
stdlib dependencies before entering the outer read-only guard, matching the
existing runner's ordering. Its physical source SHA is fixed to
`e6fcffefa2521666bc2aed0f5caf8e862c1c1014ad12d2ab5fbce09c2df9c6f0`,
with the actual base-Python stdlib path and imported module identity checked;
its descriptor is included in the planning source closure. This imports class
definitions, not an event loop or process. Neither sklearn nor parent F is
preloaded. Nested verifier entry uses the cached definition. If a first cold
definition is requested after the process guard has already been entered, it
fails closed rather than replacing the forbidden Popen with a live constructor.
Non-Windows code does not claim this Windows preparation; the Windows-specific
tests are explicitly skipped there.

The LOCAL parent context additionally disables the cached Windows Popen
class's `__init__` while verification runs. This covers ordinary aliases to the
preloaded class as well as the module attribute, preserving the process ban
without changing the class definition or the frozen audit. Normal, exception
and nested exits restore the previous constructor identity. SQLite adaptation
and all original core/process/OS/PG bans remain intact. Module import and default
`describe` remain inert. No frozen runner, parent, CI, native, Java, scientific
formula, resource value or accepted result changes. V8 evidence is 29 focused
pure tests passing in 0.84s, with 56 unrelated tests deselected; no actual F,
model, process constructor, PG/JVM, metadata pilot or plan was run.

V9 fixes descriptor path representation after the complete v8 parent provider
had returned successfully. The original model and continuation reports retain
four dimension descriptors with absolute project paths. LOCAL `artifact()`
returns canonical project-relative paths; comparing those strings rejected
physically identical files. ROOT independently checked all four files' bytes
and SHA and recorded the diagnosis in
`audits/local_candidate_v8/root_actual_metadata_failure_diagnosis.json`
(SHA256 `74ee0f321a9ea5439ae89b04d9789980ee568f56175046335bd4655868a2e37c`).
Those data checks and the complete parent verification are not repeated while
implementing this revision.

The new pure `canonical_parent_descriptor` resolves legitimate relative,
absolute and `..` aliases, then expresses project files relative to the project
root. It does not hash or mutate a parent record. Bytes must be a non-boolean
integer >=0 and the digest must contain exactly 64 hex characters. Physical
acceptance still compares the declared bytes and SHA exactly with the current
file. Any `external_scope` field on a project descriptor is rejected, including
null. External files remain limited to the original KERNEL32.dll/msvcrt.dll
whitelist and exact `windows_direct_native_import` scope.

Only the recursive lineage walk indexes descriptors by that canonical identity
before checking for duplicates. A repeated alias must declare identical bytes,
SHA and scope; conflicts are rejected without a second walk hash. The first
occurrence is still physically verified. This is an entry-local walk index,
not a cross-entry cache or substitute for the fresh parent F. Initial parent
publication checks and the tail `add` physical rechecks remain unchanged. Raw
parent JSON, paths and seals are not edited; only the LOCAL derived `files`
inventory uses canonical keys.

TDD first observed three failures for absolute/`..` identities and a repeated
walk alias. The corresponding descriptor/alias/drift/DLL suite then passed 19
pure tests in 0.99s. After the interrupted session resumed, three additional
project-scope negative cases and one original-lineage regression passed in
0.48s; the already-passed 19 tests were not repeated. These checks use tiny
fixtures and stub one parent call; no actual F, raw data scan, model, PG/JVM,
metadata plan, deletion or commit occurs. Only the LOCAL contract, its tests,
this protocol and a small v9 freeze manifest change; protected sources and
all numerical and resource rules remain fixed.

V10 removes the unbounded physical-order sort in all three LOCAL readback paths:
post-import fields, SHARE-locked before/after fields, and auxiliary native bits
and partitions. The actual V9 customer readback failed at its `ORDER BY ctid`
when the 15M-row external sort reached the unchanged 1GiB temp limit. Its
TAINTED run and old database are not repaired, adopted or deleted. Python's
explicit spec and the Java DATABASE literal both select the fresh
`deepdb_verdict_ssb_local500_v10`; all Java query, registration and resource
statements otherwise remain unchanged.

Each V10 readback performs one `SELECT ctid::text,<same projection> FROM ONLY
<target>` COPY, without sorting, filtering, joins or CTID-range rescans. Before
COPY, transaction-local `synchronize_seqscans=off` and
`max_parallel_workers_per_gather=0` are set and read back. `EXPLAIN
(VERBOSE,FORMAT JSON)` must show exactly one serial, unfiltered Seq Scan on the
explicit schema/relation, with its original alias and no child plans. PostgreSQL
11 documents that disabling synchronized scans starts a sequential scan at the
beginning, and setting parallel workers to zero disables parallel query.
The actual output independently must have strictly increasing, unique physical
`(block,offset)` CTIDs; a different or wrapped scan fails closed. The two prior
setting values are restored and checked before a successful return. On error,
restoration is attempted without masking the first error; a SQL-aborted
transaction still fails and is closed/rolled back by the existing controller.
No server-wide settings, work memory, temp or runtime caps are increased.

COPY retains pipe CSV and explicitly selects UTF8. The CTID prefix has no pipe
or quotes, so the bounded sink removes only that prefix and its first delimiter.
It never parses/re-encodes the payload's quoted fields. The frozen raw
normalizer already rejects NUL, CR and LF inside fields; the sink also rejects
CR/NUL and malformed/truncated physical records. Arbitrary fragments, including
UTF8 split points, quoted empty strings, literal backslash-N, doubled quotes
and duplicate payloads retain exactly their original bytes and SHA. Auxiliary
hashes retain the CTID prefix itself, as before. A record is limited to64KiB
and an incoming fragment to8MiB; no full-table Python buffer or disk staging is
introduced, and the existing512MiB Python RSS cap still applies. Small
`physical_scan` receipts record the verified plan/settings/row count/CTID range;
the offline committed/full-field load verifier rechecks those receipts.
The independent offline snapshot verifier also requires the auxiliary scan
receipt with CTIDs retained; matching auxiliary row counts and hashes alone
cannot bypass that order/plan/settings proof.

The changed source closure invalidates V9 pilot and formal bindings. ROOT must
create a fresh `pilot-plan`, approve its exact binding/limits and run `pilot`
with a fresh name and explicit project-PG startup. The completed new measurement
then needs a new `APPROVED_LOCAL_VERDICT_RESOURCE_PLAN` with its final SHA,
unchanged limits, positive integer projected own-DB/total sizes within both
caps. `plan` accepts only that current measurement, followed by ROOT's new
`APPROVED_LOCAL_VERDICT_EXECUTION` binding/limits review and a fresh `run` name.
There is no old measurement adoption, failed-DB adoption or skipped parent F.
Development uses only pure/mock tests:27 new cases failed before implementation,
then27 passed; the expanded complete ops file passed50 tests, and three focused
spec/command/pilot-source-binding regressions passed. No actual F, database,
JVM, metadata plan, scientific call, deletion or commit is run by this change.
Five auxiliary-proof tamper cases additionally first failed to raise under the
old offline verifier, then passed after its one-line physical-scan check.

Primary references: [PostgreSQL11 synchronized scans](https://www.postgresql.org/docs/11/runtime-config-compatible.html),
[parallel-worker setting](https://www.postgresql.org/docs/11/runtime-config-resource.html),
and [COPY CSV/encoding](https://www.postgresql.org/docs/11/sql-copy.html).

V11 addresses source order during insertion, separately from V10's correctly
ordered physical readback. V10's 15M customer import failed the exact
source/readback comparison; its per-table failure did not retain the two digest
tuples, so that failed full run cannot itself prove that values were unchanged.
ROOT's separate PG11.5 probe on1M actual customer-prefix rows reproduced a pure
reorder: both committed-table cases (100COPYs and1COPY) retained every key and
original per-key payload, but differed in ordered SHA. Their first inversion
was row176095, key176159→176094 at CTID(2681,1). Both newly created-in-transaction
cases retained the exact94,774,977-byte source sequence and SHA
`e33e8d0ded89661a6cb73f45b2cd19be172882b57df9f5952c6e5d7948ecd251`.
The four small reports are in `output/full/verdict_ssb/audits/order_probe_v11/`.
These observations establish the bounded diagnostic mechanism, not completion
of the SF500 baseline or any formal latency measurement.

The pinned PostgreSQL11.5 implementation sets `HEAP_INSERT_SKIP_FSM` for a
new-in-current-transaction target. Without it, insertion can revisit earlier
free-space-map pages even within a single COPY. See the primary
[COPY source](https://github.com/postgres/postgres/blob/REL_11_5/src/backend/commands/copy.c)
and [heap buffer-selection source](https://github.com/postgres/postgres/blob/REL_11_5/src/backend/access/heap/hio.c).
V11 creates each target and performs its COPY and exact physical readback in
one transaction, committing only after equality. The empty fact skeleton is
created separately; the retained sample still has the same LIKE schema, two
auxiliary columns/defaults, seed, and registration/query parameters. No
TRUNCATE, old-table adoption, extra ordinal column/index or larger sort/cap is
introduced. The existing strict physical CTID and CSV byte equality gates stay.

One bounded `NormalizedCopyReader` composes the unchanged frozen `raw_chunks`
generator and `CopyHashSink` for each target's single COPY FROM. It returns at
most64KiB UTF8 bytes per read, retaining at most one8MiB normalized chunk;
resources are checked before consuming more source. Complete EOF, normalized
row count, emitted-byte row count and expected rows must all agree. Closing
the generator is explicit, and a close/diagnostic error cannot replace the
first import error. Successful receipts declare
`FRESH_CREATE_SINGLE_COPY_SAME_TRANSACTION_V1`, one COPY, same-transaction
creation and complete EOF/counts; offline committed-load verification requires
all those fields. On failure, the small `import_<table>_failure.json` retains
the stage, expected/generated/emitted counts, COPY completion, emitted source
bytes/SHA, actual bytes/SHA and physical proof when available, and the original
exception. Partial source hashes are not claimed to be committed server data.

Python and Java change only their database literal to
`deepdb_verdict_ssb_local500_v11`; parent pins, resource limits, numerical
formulas, all original columns and38 SQL calls stay fixed. V10's9-source freeze
and23 parent pins remain historical evidence, with original source bytes in
Git commit `9ccc8b8bb20381ed32738306aa2b0ce5cb16b7b8`. A fresh V11 pilot/plan,
resource review and ROOT approval remain mandatory. Implementation validation
is pure/mock; the actual1M probe was run separately by ROOT, not by this code
editing task. No implementer F, PG/JVM, model, science, plan, deletion or commit
is performed for V11.
