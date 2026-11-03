# SSB native v2 model I/O bridge

The independent bridge is `code/full_ssb_native_model.py`; its tests are `code/tests/test_full_ssb_native_model.py`. Operational launching/monitoring is separate in `code/full_ssb_native_model_run.py` with `code/tests/test_full_ssb_native_model_run.py`. This version supplies source validation, orchestration, whole-run transactions, strict publication and read-only acceptance. It has not prepared HDFs, trained an SF500 model, evaluated model queries or produced a native model scientific receipt. All execution latches remain false: `FINAL_RECEIPT_INTERFACE_FROZEN`, `GENERATOR_CLOSURE_INTERFACE_FROZEN`, `FORMAL_PUBLICATION_REVIEW_COMPLETE`.

The frozen native generator candidate has passed its small gates/readiness preparation. An actual final SF500 receipt must pass the complete author gate before a root-reviewed executable model plan can be prepared. Today's printed `plan` is non-executable and writes no file. Matching the author's population row count and 13 SQL truths does not establish identity of every original row byte. Old SF2 model gates demonstrate algorithm equivalence only; they cannot validate the faulty historical population or change its MISMATCH.

## Frozen boundaries

The bridge leaves original sources, inputs and historical outputs unchanged. It delegates scientific work only to frozen `full_ssb_guard.guarded_prepare`, `guarded_train`, `guarded_evaluate`, and `full_ssb_model.sample_moments_native`, `population_truth_groups`. Frozen source pins are:

| File | SHA256 |
| --- | --- |
| `code/full_ssb_model.py` | `5b6d31a15884cf09ba29c19d3c49db2c5a79d82a5fba40e4aa1d7e714f23aa27` |
| `code/full_ssb_guard.py` | `fc19133d00216ceac72198eed747107d81e82f224804c69440290931a201f842` |
| `code/full_ssb_replay.py` | `fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab` |

The native candidate is pinned independently, so a self-resealed subset inventory cannot authorize it:

| Candidate file | SHA256 |
| --- | --- |
| `code/full_ssb_native_v2.py` | `9dc407892acaa14042cf4c9645b455747efbbba46d63fb8385946ee30a60eaeb` |
| `code/full_ssb_native_v2_stream.py` | `ddcd3b3d387b8b6a28324ceb89b39f1b0911db8f4130ccf5dbd4567424e422b1` |
| `code/full_ssb_native_v2_formal.py` | `52de0f43faf554a761f8dacca3cee5e9d919113402743aacf1a211ddcd882b40` |
| `output/full/ssb/native_v2/readiness/readiness.json` | `0bc498c29664ef4f44692ef08e61d4fe4734d73b904be0a8a581a74ba9ac00e1` |
| `output/full/ssb/native_v2/formal_review_plan.json` | `da3d91cfcc02e8d0934b9925c2a77c88c7adac834eb043f2bb1c2a138cc0dd34` |

These pins do not open execution. An explicit root-reviewed final generation receipt SHA is also required.

## Actual native v1 contract

The actual owner API is `full_ssb_native_v2_formal.verify_final(path)`, strictly read-only. The bridge calls no constructor, compiler, gate adoption or stream function. Final path is `output/full/results/ssb_native_v2.json`; seal is `ssb_native_v2_seal.json` (stem plus `_seal`, not `.seal`). Required generation fields include:

- `schema='ssb_native_v2_final_v1'`, `status='PASS_AUTHOR_TRUTHS'`, `complete=true`, `paper_population_row_count_and_13_truths_match=true`.
- Exact integer `N=population_rows=3000028242`, actual integer `sample_rows`, and plain 64-hex `source_id` bound to the plan.
- `canonical_truth`: all 2,059 unique `{query_no:int, group:list[str], value:int}` records for indices 0 through 12, exactly equal to the pinned author pickle SHA `14ff6ea9cf4d8b8e0b0f05066e8854cbb5f4e186715f67bf5d528f27722f0d1c`. No float conversion, subset or duplicate may pass source acceptance.
- Actual absolute descriptors `plan`, `checkpoint`, `raw_sample`, `review_plan`, `dimension_receipt`, with bytes/SHA. Checkpoint is a descriptor; its physical body is separately read. Dimensions are keyed customer/supplier/part/date. `artifacts` is a flat exact map, not the obsolete draft nested manifest.
- Exactly 4,000 zero-based shards 0 through 3999 with contiguous ranges covering orders 1 through 750,000,000; completed checkpoint `next_shard=4000`. Rows, sample bytes/SHA/count, source binding and canonical integer aggregates must agree. The owner's pinned verifier also checks each committed chunk/sample segment and the exact inventory without truncation or repair.

Nominal formal probability follows the original public schema: `3333/1000000`, not `10000000/N`. Retain `hash < actual_cutoff`, with `actual_cutoff=floor(3333*2**64/1000000)`. Effective p is exact cutoff divided by `2**64`; required `effective_probability` is only its descriptive float. Integer probability and normalizer fractions are authoritative. The fact normalizer is actual retained `n/p`, never exact N. Actual retained count must be reported, including departures from ten million.

The frozen generator flat map omits two consumed stream files. The bridge independently seals `Path(plan.path).parent/lifecycle.json` and `native.stderr.log`. Lifecycle must be `STREAM_COMPLETE`; `plan_sha256` must equal the actual canonical plan hash; finite nonnegative seconds and nonnegative integer native peak bytes must exactly equal the report. The returned outer `final_guard` must be `FINAL_PASS` and match exact report/review-plan SHAs. This closes the consumed-file gap without editing generator bytes.

Raw sample is `data/ssb/sf500_native_v2/lineorder_sampled.csv`, dimensions under `dimensions/`. Raw SHA/rows are independently streamed with field widths 17 facts, 8 customer, 7 supplier, 9 part, 17 date; optional terminal pipes are accepted only at the expected width. Full dimension counts are 15,000,000 customer, 1,000,000 supplier, 1,800,000 part, 2,556 date. Full physical input checks repeat after model stages and before publication.

## Source, parser and runtime

`dependency_snapshot()` binds complete original algorithm sources, three frozen model files, the entire bridge/context, installed SPFlow Python files, exactly 22 sqlparse Python files, package versions and actual loaded roots. Actual numpy/pandas/scipy/sklearn/joblib/tables/spn/sqlparse/networkx module files must reside in the original project `.venv`. All package DLL/PYD hashes are separate dependencies.

The `.venv/Scripts/python.exe` launcher alone is insufficient: `.venv/pyvenv.cfg`, actual `sys._base_executable` and project-local base interpreter EXE/DLL/PYD files are also bound, including python38.dll, python3.dll, vcruntime and extensions. A read-only preflight observed 58 base/configuration files, 283 package native files, nine module roots and 22 parser files. These are observed counts, not substitutes for the complete executable-plan snapshot.

Generator closure fixes complete MinGW 5,906-file tree SHA `91ee6db0baa926fe4ae966c790504b29e43097988bdf6a989c58593ba1c7c081` and Cygwin 3,136-file tree SHA `72898942c4a6d9b37ebe230ba7c092604ba95bac2f7f862cf983d96dc933dce5`. It verifies the fixed MinGW archive, Cygwin lock SHA `335fba5f9eb8c2ad6c465f96bd55401811898c9d1a27ce730d9e24c350f65383`, all 26 official package archives against lock SHA512 checksums, PASS receipt/seal/lifecycle and actual layout-probe executable. Preflight yielded 9,074 generator runtime/archive/evidence descriptors. Changed files, deletions or self-resealed subsets fail the fixed inventory hashes.

Only external paths `C:/Windows/System32/KERNEL32.dll` and `C:/Windows/System32/msvcrt.dll` are accepted, labelled `external_scope='windows_direct_native_import'`. Every other artifact is physically project-contained. These bind observed direct PE imports, not the entire Windows transitive operating-system closure.

## Model and resource boundaries

Settings remain one million requested rows/table, `single`, RDC .3, minimum slice 1%, seed 1, post-sampling factor 10, one RDC/BLAS/OMP worker. Date uses its actual 2,556 rows. Original schema N remains source metadata; prepared fact length and learned `full_join_estimate` must equal actual n/p. Original row order, int64 reduction and pandas mean are retained for SUM references. The lossless truth projection changes JSON shape only, with no arithmetic or rounding.

Only a fresh dedicated child may temporarily route `core.OUTPUT` to the new runtime. The context restores the exact original value in `finally`, including exceptions. Whole bridge/context source is hashed. All four `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS` must equal `1`.

Stage entry requires at least 4 GiB available RAM, 8 GiB free disk, and combined `data/ssb` + `output/full/ssb` bytes plus 5 GiB planning reserve no greater than 16 GiB. The supervisor requires at least 5 GiB RAM before launch. Reserve is not measured peak. The concrete independent launcher/monitor is implemented but remains execution-latched; final source acceptance, closure/launcher review and root memory release all precede an explicit enable version.

The supervisor starts the direct project base interpreter (`sys._base_executable`) as a waiting bootstrap, not the Windows venv redirector. Before GO, that bootstrap starts no children and waits for its bounded stdin handshake. The supervisor first assigns it to a new named Windows Job Object with kill-on-close, then releases GO. Only then does the bootstrap verify membership and start the original `.venv` worker; both the venv redirector and actual base-interpreter worker inherit the job. The actual worker checks named-job membership after its handshake; the bridge checks again before stages. Explicit `python_base_executable` and original venv executable roles are bound to existing physical native-runtime hashes. Assignment or existing-host-job incompatibility fails closed, with no uncontrolled fallback.

This order fixes the independently reproduced venv-launcher race: assignment after its base child already exists does not retroactively add that child to the job. Tiny real tests delay assignment by .5 seconds, child scheduling by .5 seconds, and both together; they use the actual shared `launch_inherited_venv_worker` and verify original-venv membership and launcher/worker PID-parent relationships. `bootstrap.json` and `worker_start.json` retain actual bootstrap PID, venv launcher PID, actual worker PID/parent, commands, interpreters and membership-after-GO. Closing the supervisor kills only assigned descendants. Other microtests proved parent/grandchild disappearance on close, explicit termination with active-PID list zero and survival of the unrelated supervisor parent. Live leaked descendants are refused; briefly retained already-dead job accounting entries are distinguished by exited process state.

Running RAM, assigned-tree working sets and free disk are sampled every two seconds. Stop when available RAM falls below 1 GiB, observed summed owned RSS exceeds 6 GiB, free disk falls below 8 GiB, observed combined SSB bytes exceed 16 GiB, or wall time exceeds 48 hours. RSS is a sampled live-tree working-set maximum, not an operating-system hard memory quota or proof that no between-sample transient occurred. The full budget walk runs in a separate controlled thread every 30 seconds; snapshots older than 90 seconds or scan errors refuse continued execution. RAM/RSS checks never wait for that walk. A complete synchronous storage scan runs before launch and after child success. Replacing repeated Path stat calls with DirEntry metadata reduced the observed whole-tree probe from 18.06 seconds to 0.81 seconds on this checkout; timing can vary under contention. Slow/error/stale-budget tests verify the separation. No generator source was changed.

Any resource stop closes/terminates only the assigned job, writes STOPPED monitor evidence and taints the SUPERVISOR plus any existing FORMAL/PUBLICATION lifecycle. The supervisor retains stdout, stderr, monitor JSON, receipt and lifecycle. A zero exit code alone cannot pass: the complete scientific publication and its hashes must validate, as must resource evidence and the sealed waiting-worker command. A RUNNING supervisor tail is never adopted or automatically rerun.

## Whole-FORMAL and publication controls

An OS kernel lock protects the whole new namespace; a second controller is refused. Above frozen stage guards, FORMAL persists RUNNING before production, validates all actual results/dependencies before PASS and durably TAINTS any exception. Cached PASS is reused only after complete validation. RUNNING tails, incomplete PASS, changed bindings and TAINTED states are refused without rerun or repair. Physical run IDs use the first 20 plan-hash characters for Windows paths, while full 64-character hash remains in all checked bindings, preventing silent collision reuse.

Publication is a separate durable PUBLICATION transaction bound to FORMAL receipt SHA and report hash. Any publication exception or leftover RUNNING tail taints PUBLICATION and whole FORMAL. It cannot leave a reusable whole-FORMAL PASS or regenerate publication silently. Scientific final seal binds every actual stage/source/runtime/plan/input record; outer PUBLICATION then binds that seal, verification and published-result SHAs without a hash cycle.

Required sets are independently enumerated, not trusted from `rglob` or a supplied manifest. They include three outer stage guards, prepared metadata/binding/main HDFs plus unmatched HDF paths found by static pickle opcodes, six model pickles, five training receipts and model inputs, sample moments/helper source/binary/build receipts, and exactly 26 query result/seal files. Read-only inventory does not unpickle models or metadata. All 13 original SQL/name/index identities, 2,059 truth groups, union coverage, missing/extra/model counts and query-error totals are checked against actual files. Zero/nonfinite/CI fields remain explicit. Synthetic fake models cannot pass real `verify_formal()`.

## Stable paths and report

Let P=`value_hash(reviewed_plan)`, S=P[:20], R=`output/full/ssb/native_v2_models/runs/S`. These are future paths, not current successful or pending scientific receipts.

| Artifact | Path |
| --- | --- |
| Generation report/seal | `output/full/results/ssb_native_v2.json` / `ssb_native_v2_seal.json` |
| Model plan/seal | `output/full/ssb/native_v2_models/plans/S/plan.json` / `plan.seal.json` |
| Whole FORMAL | `R/formal_control/{receipt.json,lifecycle.json,controller.lock}` |
| PUBLICATION | `R/publication_control/{receipt.json,lifecycle.json,controller.lock}` |
| SUPERVISOR | `R/supervisor_control/{stdout.log,stderr.log,monitor.json,bootstrap.json,worker_start.json,receipt.json,lifecycle.json,controller.lock}` |
| Verification/scientific seal | `R/verification.json` / `R/verification_seal.json` |
| Published result | `output/full/results/ssb_native_v2_model_aqp_ci.json`, same report as verification |
| Prepared files | `R/prepared/`, plus frozen sibling PREPARED guard |
| Model | `R/model/ensemble_single.pkl`, plus frozen sibling MODEL guard |
| CI helper | `output/full/ssb/native_v2_models/runtime/native/` |
| Sample moments | `R/sample_moments_native/{moments.json,moments.tsv,seal.json}` |
| Truth projection | `R/core_truth_checkpoint.json` |
| Evaluation | `report.evaluation_directory`, under `R/evaluation/` |
| Query pairs | `query_00.json` + `query_00.seal.json` through index 12 |

A reviewed executable plan requires schema `ssb_native_v2_model_plan_v1`, `status='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN'`, `executable=true`, exact `model=MODEL`, explicit `source_receipt_sha256`, complete `dependencies=dependency_snapshot()` including the independent operational launcher descriptor, exact operational policy, actual plan and seal. `candidate-plan` is read-only and returns `CANDIDATE_REQUIRES_ROOT_REVIEW`, `executable=false`. After root reviews its canonical candidate SHA, `seal-plan` checks that explicit approval hash against a freshly validated identical candidate, derives the reviewed plan and seals it. Exact existing plan bytes are reused without writes; incomplete or changed prior plans are refused. No such plan is produced while the execution latches are closed or the actual final source is absent.

Report fields include status, stage `SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI`, directory, plan, plan_path, plan_binding_sha256, plan_file_sha256, source_receipt, source_receipt_sha256, inputs, population_rows, actual_sample_rows, exact fact_normalizer, prepared_directory, model_directory, model_path/hash, spn_count, training_tables, evaluation_directory/binding, queries, point_query_errors, ci_query_errors, resources_at_start, ci_scope, normalizer_scope, adapter_source_sha256 and core_truth_projection_sha256. Nested original model/evaluation reports remain intact. Query names are S1.1, S1.2, S1.3, S2.1, S2.2, S2.3, S3.1, S3.2, S3.3, S3.4, S4.1, S4.2, S4.3; SQL is the pinned file's exact `splitlines()` sequence. CI scope remains original central 90%, with original warnings/errors. Author full-row byte identity is false; full-paper completion is not claimed by this component.

## Stable read-only API

`verify_generation(receipt_path=None, expected_receipt_sha256=None, root=ROOT)` requires an explicit reviewed SHA and complete final source. Return includes population/sample rows, 2,059 truth-group count, source_id, exact `probability={numerator,denominator}`, `fact_normalizer={numerator,denominator}`, receipt path/SHA, canonical truth SHA, physical_artifacts and limited scope. Missing/nonfinal sources fail before raw input access. It does not prepare, train, infer, compile or repair.

`verify_formal(root=ROOT)` rejects absent/unfinished/unreviewed/incomplete bundles. Successful fixed return shape is:

```text
status: PASS_READ_ONLY_SSB_NATIVE_V2_FORMAL_MODEL
report: complete published report
verification: {path, bytes, sha256}
verification_seal: {path, bytes, sha256}
published_result: {path, bytes, sha256}
plan: {path, bytes, sha256}
formal_receipt: {path, bytes, sha256}
formal_lifecycle: {path, bytes, sha256}
artifacts: complete unique actual physical descriptors
dependencies: complete source/parser/runtime snapshot
model_path, model_sha256, sample_rows, population_rows
queries: all 13 original ordered query objects
evaluation_binding: original evaluation binding
database_connected: false
training_executed: false
inference_executed: false
files_modified: false
```

If original point/CI errors exist, status ends `_WITH_ERRORS`. Root reverse replay accepts only the status without that suffix and does not retry failed original queries. Acceptance does not connect DB, load model, infer, launch/probe processes, write seals, fill files or create output. The public API additionally requires complete SUPERVISOR PASS and includes all seven operational evidence descriptors. `verify_formal_publication()` is an internal post-child validation boundary for the supervisor; it does not certify completed supervision and must not be used for public model acceptance. Descriptors are relative except the two scoped Windows imports. New root replay/tables consume the strict public API; frozen historical replay stays unchanged.

## Validation and unexecuted work

Pure/synthetic tests cover actual-v1 metadata rejection, complete author identities, physical row/hash/shape changes, n/p, resources, context restoration, controller locking, FORMAL recovery refusal, PUBLICATION writer failures and RUNNING-tail taints, exact inventories, self-resealed subsets, runtime trees, base Python DLL/config changes and external-import restrictions. Synthetic publication uses labelled fake HDF/model/executable bytes: controller evidence only. The Windows-path regression physically creates guard temporary files at actual checkout root length with the short namespace.

```powershell
.venv\Scripts\python.exe -m pytest code/tests/test_full_ssb_native_model.py -q
.venv\Scripts\python.exe code/full_ssb_native_model.py --help
.venv\Scripts\python.exe code/full_ssb_native_model.py plan
.venv\Scripts\python.exe -m pytest code/tests/test_full_ssb_native_model_run.py -q
.venv\Scripts\python.exe code/full_ssb_native_model_run.py --help
```

Future reviewed commands (all currently fail closed; placeholders are not existing approved artifacts):

```powershell
.venv\Scripts\python.exe code/full_ssb_native_model_run.py candidate-plan --source-receipt-sha256 <actual-final-source-sha>
.venv\Scripts\python.exe code/full_ssb_native_model_run.py seal-plan --source-receipt-sha256 <actual-final-source-sha> --root-reviewed-candidate-sha256 <root-reviewed-candidate-sha>
.venv\Scripts\python.exe code/full_ssb_native_model_run.py supervise --plan-path <sealed-plan-path> --plan-file-sha256 <sealed-plan-file-sha> --root-memory-approved
```

Still unexecuted: actual final source acceptance, SF500 HDF preparation, million-row/table training, all 13 model/CI queries and independent reverse inference. Before enable: complete real N+2,059 author gate; root-review final source SHA, bridge and operational layer; obtain root memory release; seal the reviewed executable plan. Pure/synthetic and tiny waiting-process tests do not authorize science. No empty PENDING scientific receipt represents these stages.
