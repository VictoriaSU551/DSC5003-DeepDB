# Separate LOCAL_SSB_SF500 model and CI

This is a separately labelled experiment on the existing corrected native local population. It cannot complete the paper's author SSB reproduction. The author-strict generator report remains `MISMATCH`, its outer lifecycle remains `TAINTED`, and all three execution flags in `full_ssb_native_model.py` remain false. No frozen native, scientific, strict bridge, or strict runner file is modified by this adapter.

The immutable decision is `output/full/ssb/local_sf500_source/root_local_decision.json`, SHA256 `cb2d7f0164570edc3e199a0875f92922b06b44978452f680e40130c76bf250ad`. Its status is `ROOT_LOCAL_SCOPE_DECISION`; it authorizes source audit only after code review, and does **not** authorize model execution. A separately reviewed plan, root memory release and root's sole launcher are required later. No additional resource authorization is inferred from this decision.

## Evidence and scientific scope

The pinned original report is `output/full/results/ssb_native_v2.json`, SHA256 `740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e`. Its population has exactly 3,000,028,242 rows and 9,996,946 retained sample rows. There are 2059 distinct integer truth groups: all 346 groups from queries 0–5 match the published truth, and all 1713 groups from customer queries 6–12 differ. Group identities match with zero missing or extra. The diagnostic SHA is `7ee4e56e98a2d6db6828634e0139c7bd132dd90631ddef9cc57563a52db2da9a`. These are recorded facts of the rejected author comparison, not a new author PASS.

The local source audit requires the exact original report, diagnostic and decision; all 4000 committed shard reductions, checkpoint, source/build/plan bindings and raw sample prefixes; all four physical dimensions; exact complete source/runtime inventories; and independent stream/lifecycle/stderr closure. It checks `STREAM_COMPLETE`, the actual plan SHA, finite nonnegative elapsed time, integer nonnegative peak RSS and equality with the original report. The exact historical author-rejection TAINTED record is required. It must never adopt another incomplete/failed generator state.

The local truth is the complete original streaming integer reduction, not another traversal of three billion rows. The LP64 and SQLite gates are implementation checks at their recorded scales; they are not independent full-population SQL execution. Neither identical author raw bytes nor the author's unidentified customer variant is established. No generation, raw-data rewrite, author receipt replacement or source resealing occurs.

Sampling retains `hash < 61482997997673935`, with denominator `2**64`; requested probability was `3333/1,000,000`. Learned tuple normalization remains actual retained `n/p`, approximately 2,999,383,738.3738375, distinct from exact population N. Exact integer numerator/denominator pairs are saved. Frozen preparation/training/evaluation and sample moments keep original row order, int64 and pandas mean behavior. Formal parameters remain single ensemble, RDC .3, seed 1, 1M/table (date has 2556 actual rows), five SPNs, original central 90% intervals and original warnings. No frozen formula or parameter changes.

## Separate namespaces and publication

| Item | Fixed location |
| --- | --- |
| Local source adapter | `code/full_ssb_local_source.py` |
| Local model adapter | `code/full_ssb_local_model.py` |
| Local runner | `code/full_ssb_local_model_run.py` |
| Local source result and seal | `output/full/results/ssb_local_sf500_source.json`, `ssb_local_sf500_source_seal.json` |
| Source audit and publication controllers | `output/full/ssb/local_sf500_source/audits/<bindingSHA[:20]>/` |
| Reviewed model plan and seal | `output/full/ssb/local_sf500_models/plans/<P[:20]>/plan.json`, `plan.seal.json` |
| Prepared/model/evaluation | `output/full/ssb/local_sf500_models/runs/<P[:20]>/{prepared,model,evaluation}/` |
| Lossless local truth projection | `.../runs/<P[:20]>/core_truth_checkpoint.json` |
| Sample moments | `.../runs/<P[:20]>/sample_moments_native/` |
| CI native helper | `output/full/ssb/local_sf500_models/runtime/native/` |
| Whole-run, publication, supervisor controllers | `.../runs/<P[:20]>/{formal_control,publication_control,supervisor_control}/` |
| Scientific verification and seal | `.../runs/<P[:20]>/{verification.json,verification_seal.json}` |
| Published model result | `output/full/results/ssb_local_sf500_model_aqp_ci.json` |

Full SHA bindings are checked despite shortened physical directory names. Every stage has a durable lifecycle and receipt. Whole FORMAL and PUBLICATION transactions reject RUNNING/TAINTED remnants and never repair or overwrite an existing publication. Publication failures persistently taint the whole local FORMAL. Supervisor failures taint only their own local FORMAL/PUBLICATION tail. Separate controller locks prevent concurrent local runs. Existing author-failure paths are never touched.

The model artifact validator has independent required sets, not a report-controlled rglob: all five raw tables; prepared metadata, binding and all main/unmatched HDF references found through static pickle opcodes; six model pickle files and all per-table JSON/RNG checkpoint records; four moments files and four helper build artifacts; all three outer frozen stage guards and their sibling directories; exactly 26 physical query/seal files in original order; source/runtime/adapter closure, source audit/publication controls, plan, full FORMAL and published report. It does not unpickle model/HDF data during verification.

Only the frozen five scientific entry points are called: `guarded_prepare`, `guarded_train`, `guarded_evaluate`, `sample_moments_native`, `population_truth_groups`. A fresh worker temporarily routes the frozen core OUTPUT to the separate local runtime directory, restoring it in `finally`. No strict provider/global module swap occurs. The local lossless projection substitutes **local** integer truth as input, with an explicit 1713-group author mismatch annotation.

## Operational contract

The runner reuses frozen `OwnedWindowsJob`, `LiveResourceProbe`, `run_owned_child`, direct-base interpreter discovery and inherited-venv launching. It contains no copied Windows API implementation. A direct base bootstrap waits for GO, is assigned to its named job, verifies membership after GO, then starts the original isolated `.venv` worker. The worker verifies inherited membership before science. Bootstrap/launcher/actual worker PID nesting, commands, interpreter hashes and named job are recorded.

The unchanged operational policy requires at least 5GiB available RAM at launch, 4GiB at stage start, at least 1GiB live available RAM, observed owned-tree RSS at most 6GiB, at least 8GiB free disk, and at most 16GiB combined SSB storage including the 5GiB stage reserve. RSS/RAM/free disk are polled every two seconds; full storage scans run separately every 30 seconds and become invalid after 90 seconds. Wall limit is 48 hours. Closing the job kills only the owned tree. No supervisor/other experiment process is killed.

The public read-only verifier requires all seven operational descriptors: stdout, stderr, monitor, bootstrap, worker_start, supervisor receipt and lifecycle. Empty logs are valid physical artifacts. Exit zero alone is insufficient: monitor policy/resource evidence, nested member identity, scientific publication SHA links and whole `LOCAL_SUPERVISOR` PASS must all agree. Only direct native Windows imports `KERNEL32.dll`/`msvcrt.dll` are physically bound; this does not claim a complete transitive Windows DLL closure.

## Read-only API and report shape

`full_ssb_local_source.verify_local_source()` requires an already complete independent local physical gate and returns its report plus `receipt_path`, `receipt_sha256`, `verification`, `verification_seal`, `audit_receipt`, `audit_lifecycle`, `publication_receipt`, `publication_lifecycle`. Status is `PASS_LOCAL_SOURCE_PHYSICAL_GATE_ONLY`, never author PASS. It rechecks all actual physical dependencies and never writes, repairs, generates or trains.

`full_ssb_local_model.verify_local_formal()` requires complete source, model and supervisor publications. Its exact success status is `PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH`; original query errors append `_WITH_ERRORS`, which independent replay must reject for a success claim. It returns:

- `report`, `verification`, `verification_seal`, `published_result`, `plan`, `formal_receipt`, `formal_lifecycle`, complete unique actual `artifacts`, and `dependencies`;
- `model_path`, `model_sha256`, `sample_rows=9996946`, `population_rows=3000028242`, the original ordered 13 `queries` and `evaluation_binding`;
- `original_mismatch` descriptor, `author_different_groups=1713`, `scope='LOCAL_SSB_SF500'`, `author_reproduction_complete=False`, `full_paper_reproduction_complete=False`;
- explicit false `database_connected`, `training_executed`, `inference_executed`, `files_modified`.

The scientific report uses stage `LOCAL_SSB_SF500_SINGLE_1M_AQP_CI`, status `PASS_LOCAL_SSB_SF500_MODEL_AQP_CI` or `LOCAL_MODEL_QUERY_ERRORS_RECORDED`, and additionally fixes `author_population_row_count_and_13_truths_match=False`, `author_full_row_byte_identity_proven=False`, `spn_count=5`. Every query retains exact original SQL (strict `splitlines`), S1.1–S4.3 identity, union group coverage, missing/extra/zero truth, prediction/error/CI or explicit original exception. Local replay/tables/status are separately owned root adapters; they cannot replace the incomplete primary author SSB ledger.

## Commands and current execution boundary

All commands run from the original Deep DB directory using the original `.venv`; none changes dependencies. These commands are operational interfaces, not permission to execute later stages:

```powershell
.venv\Scripts\python.exe code/full_ssb_local_model_run.py --help
.venv\Scripts\python.exe code/full_ssb_local_model_run.py audit-source --root-decision-sha256 cb2d7f0164570edc3e199a0875f92922b06b44978452f680e40130c76bf250ad --reviewed-local-codes-sha256 <ROOT-reviewed-objectSHA-of-exact-three-local-source-map>
.venv\Scripts\python.exe code/full_ssb_local_model_run.py candidate-plan --source-receipt-sha256 <actual-local-source-receipt-SHA>
.venv\Scripts\python.exe code/full_ssb_local_model_run.py seal-plan --source-receipt-sha256 <actual-local-source-receipt-SHA> --root-reviewed-candidate-sha256 <explicit-root-reviewed-candidate-objectSHA>
.venv\Scripts\python.exe code/full_ssb_local_model_run.py supervise --plan-path <reviewed-plan-path> --plan-file-sha256 <actual-plan-file-SHA> --root-memory-approved
.venv\Scripts\python.exe code/full_ssb_local_model_run.py verify-formal
```

The source audit's reviewed code hash is `value_hash(source.code_snapshot())` over exactly the three local adapters. Scientific plans additionally take optional `--frozen-auxiliary-sources-json` on both candidate/seal commands, containing the explicitly root-frozen map for `code/full_ssb_local_replay.py`. No live/new replay is automatically included in the source dependency snapshot. Coordinate the final source freeze before audit and planning. A bare root-decision SHA cannot launch a model.

Implementation tasks 1–3 are implemented, with source/model/operational TDD and pure/synthetic tests plus a tiny real owned Windows process tree. The tiny test replaces the scientific function inside its isolated test process; it proves assignment-before-GO and actual exited PID nesting, not model preparation/training correctness. Actual local physical audit, formal plan publication, SF500 HDF preparation, 1M/table training, 13-query model/CI evaluation and independent local replay remain **unexecuted** until separate code/operational review and root acceptance. No scientific receipt claiming these stages has been created.

Selected validation command (local files only):

```powershell
.venv\Scripts\python.exe -m pytest code/tests/test_full_ssb_local_source.py code/tests/test_full_ssb_local_model.py code/tests/test_full_ssb_local_model_run.py -q --tb=short
```
