# LOCAL_SSB_SF500 Model and CI Implementation Plan

> **For agentic workers:** This is a proposal only. Root must first decide whether the customer/source variant remains unidentified and explicitly authorize this separate local experiment. Do not implement, enable, seal a scientific receipt or execute model stages from this document alone. After authorization, use `superpowers:executing-plans` task by task; do not spawn agents, commit or push without root instructions.

**Goal:** Evaluate the unchanged DeepDB model and CI algorithms on the already generated local native SF500 population, while preserving the failed author reproduction and its primary-ledger incompleteness.

**Architecture:** A new independent local physical-input gate consumes the exact existing MISMATCH report, complete checkpoint, retained sample and full dimensions. Separate local model/runner/replay adapters use the frozen scientific routines and existing generic transaction, resource and Windows-job primitives. They never call or relax the strict author-acceptance APIs, change their three false latches, or rewrite historical source evidence.

**Tech stack:** Original project `.venv`, Python 3.8, frozen RSPN/SPFlow/Pandas preparation and CI helpers, original 13 SQL lines, Windows named Job Objects. No new dependencies or database import.

**Spec:** Root's local-variant planning instruction after the native SF500 author MISMATCH; existing `docs/FULL_SSB_NATIVE_MODEL.md` supplies the reviewed scientific/operational boundaries. This proposal does not supersede that strict protocol.

## Global constraints

- Proposal only; no code implementation, model plan writes, scientific receipts, preparation, training or inference are authorized now.
- Preserve all frozen native, strict bridge/runner, original model/guard/replay and historical data/output bytes. Strict author latches remain False.
- No second generator or 3B-row traversal. Only existing committed files, retained sample, dimensions and small published truth records may be audited after approval.
- Keep author reproduction incomplete. A local result is an additional experiment, never a replacement for author SSB tables or a full-paper completion claim.
- Preserve exact integer local truth and exact author comparison; do not train or tune on either query-truth set.
- Keep original 1M/table, single ensemble, RDC .3, 1% minimum slice, seed 1, post-sampling factor 10 and one RDC/BLAS/OMP thread. Date uses its actual 2,556 rows.
- Learned fact normalizer remains retained n divided by actual cutoff probability; author N is source/evaluation metadata, not a replacement learned length.
- Retain 16 GiB combined SSB budget, >=8 GiB free disk, >=5 GiB launch RAM (>=4 GiB stage-entry RAM), live available RAM >=1 GiB and observed owned-tree RSS <=6 GiB. Keep reviewed monitoring/timeout policy and independent root resource release.

## Observed source boundary

Only final JSON/checkpoint/lifecycle metadata was read for this proposal. No physical source gate or scientific function was run.

| Item | Existing evidence |
| --- | --- |
| Original native report | `output/full/results/ssb_native_v2.json` |
| Exact report SHA256 | `740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e` |
| Native source ID | `a574cd95f8ba184c809c66e438c88f69ddb1ddcc7b984c9ea99bcbb4c476dcf9` |
| Original status | `MISMATCH`, `complete=false`, author-match flag false |
| Exact population rows | 3,000,028,242 |
| Actual retained fact rows | 9,996,946 |
| Stream | 4,000 committed shards; stream lifecycle `STREAM_COMPLETE` |
| Local integer truth | 2,059 unique groups, 13 query indices |
| Author comparison | 0 missing, 0 extra, 1,713 different values; indices 0..5 all match |
| Sample policy | requested 3333/1,000,000; cutoff 61,482,997,997,673,935 over 2**64 |
| Original n/p float | 2,999,383,738.3738375; exact fraction remains authoritative |
| Original outer lifecycle | `TAINTED`, exact author-comparison-MISMATCH rejection; must remain so |

Existing LP64 all-field/dimension and SQLite gates validate the native implementation at their recorded scales. The formal 3B local integer truth comes from the committed streaming reductions. This proposal does not claim an independent SQLite traversal of all 3B rows or proof of author raw-byte identity. The customer-related author/source discrepancy remains under diagnosis.

## Review focus

1. Accepting a local physical source must not change or obscure the original MISMATCH/TAINTED receipts.
2. A similarly named TAINTED source caused by corruption, missing chunks or an unknown exception must fail; only this explicitly reviewed source/report pair is in scope.
3. Local truth and author truth must never be interchanged, passed through an author gate by monkeypatch, or used as learning inputs.
4. A newly sealed subset cannot replace the exact raw/dimension/chunk/source/runtime/HDF/model/13-query required sets.
5. Local status, paths, replay and table scope must be incompatible with strict-author success consumers; no global source flag or namespace mutation.

## Proposed files and namespaces

No existing file is modified. Future ownership and implementation need a root assignment.

| New file | Responsibility |
| --- | --- |
| `code/full_ssb_local_source.py` | Independent exact-source physical gate and read-only local receipt verifier |
| `code/full_ssb_local_model.py` | Thin local scientific I/O orchestration, complete local model artifact acceptance |
| `code/full_ssb_local_model_run.py` | Local plan/approval and supervisor using reviewed generic job/resource primitives |
| `code/full_ssb_local_replay.py` | Independent reverse-order local replay; root may own this separately |
| Matching `code/tests/test_full_ssb_local_*.py` | Pure/source-boundary, synthetic publication and tiny operational gates |
| `docs/FULL_SSB_LOCAL_MODEL.md` | Actual local-only protocol and measured results after implementation |

The existing raw files stay read-only in `data/ssb/sf500_native_v2/`; do not copy or regenerate them. Let P be the full reviewed local plan hash, S=P[:20], R=`output/full/ssb/local_sf500_models/runs/S`.

| Future local artifact | Separate path |
| --- | --- |
| Local source verification/seal | `output/full/ssb/local_sf500_source/<source-token>/{verification.json,verification_seal.json}` |
| Local source public result | `output/full/results/ssb_local_sf500_source.json` |
| Reviewed local plan/seal | `output/full/ssb/local_sf500_models/plans/S/{plan.json,plan.seal.json}` |
| Prepared/model/evaluation | `R/{prepared,model,evaluation}/` and independent sibling frozen stage guards |
| CI helper | `output/full/ssb/local_sf500_models/runtime/native/` |
| Whole local controllers | `R/{formal_control,publication_control,supervisor_control}/` |
| Local model result | `output/full/results/ssb_local_sf500_model_aqp_ci.json` |
| Local reverse result | `output/full/results/ssb_local_sf500_model_reverse_replay.json` |

No PENDING scientific receipts are created during planning. Full P remains in bindings; S is only the Windows-safe path token.

## Task 1: Independent local source acceptance

**Files:** New `code/full_ssb_local_source.py` and its tests. Strict bridge/native modules remain frozen.

**Interfaces:** Future execution command `audit_local_source(expected_native_report_sha256, root_local_decision_sha256)` writes only the new local gate after validation. Default `verify_local_source()` is strictly read-only, refuses missing/incomplete evidence and returns status, population/sample counts, exact p and n/p, canonical local truth hash, complete artifact descriptors, original mismatch descriptors and author-difference scope.

- [ ] Write failing pure tests for wrong report SHA, a different TAINTED cause, original source status edited to PASS, missing/duplicate/noninteger local groups, changed author difference counts, unfinished checkpoint/range gaps and a self-resealed artifact subset.
- [ ] Implement an exact-source allow-list: pin the above MISMATCH report/seal, native reviewed plan/readiness/source hashes, complete checkpoint, and the original TAINTED outer lifecycle descriptor/reason. Preserve the original report verbatim as a dependency. Never turn its status/complete flag into a pass, and never call or patch strict `verify_generation()`/`verify_final()` to accept it.
- [ ] Reuse only already read-only native checks: `controller.check_plan(..., physical=True)`, `validate_restore(..., truncate=False)`, exact `manifest_paths(...)`, existing readiness/review/dimension receipt verifiers. These validate existing evidence; no build, adoption, recovery or stream command is permitted. Add stream lifecycle, stderr and the original TAINTED outer lifecycle independently to the physical inventory.
- [ ] Require all 4,000 exact shard file sets, contiguous 750M-order coverage, unmatched-FK count zero, complete sample segments with no tail, N=3,000,028,242 and n=9,996,946. Re-merge existing per-shard integer aggregates and require equality with checkpoint and original canonical local truth. This reads existing reductions and the 10M retained sample, not unretained 3B fact rows.
- [ ] Verify sample/four dimensions by full bytes/SHA/physical rows/field widths; bind original native build, all frozen source/readiness evidence, toolchains, Python base/venv/package native runtime, 22 parser files and scoped direct Windows imports using the same independently fixed inventories. Recheck original MISMATCH SHA after the audit.
- [ ] Compare all 2,059 local integers against the pinned author pickle, preserving the exact 1,713 value-difference records and per-query counts. Require 0 missing/extra; record that indices 0..5 match. Do not substitute author values.
- [ ] After root authorization and pure tests, perform this real read-only physical audit once; publish a new local gate and verify it read-only. Reuse trustworthy identical local evidence, never silently repair it.

Suggested source schema/status: `ssb_local_sf500_source_v1` / `PASS_LOCAL_SOURCE_PHYSICAL_GATE_ONLY`. Required explicit fields include `scope='LOCAL_SSB_SF500'`, `local_physical_gate_complete=true`, `author_truth_match=false`, `author_full_row_byte_identity_proven=false`, `author_different_groups=1713`, `original_report_status='MISMATCH'`, `original_outer_status='TAINTED'`, original descriptors and the root local-decision descriptor. No `PASS_AUTHOR_TRUTHS`, synthetic FINAL_PASS or generic author-complete flag is allowed.

## Task 2: Thin local model and complete publication

**Files:** New `code/full_ssb_local_model.py` and tests.

- [ ] Write failing synthetic tests for namespace escape, truth-source interchange, author-success aliasing, incomplete HDF/model/query sets, missing local source gate and changed runtime.
- [ ] Reuse the frozen `guarded_prepare`, `guarded_train`, `guarded_evaluate`, `sample_moments_native`, `population_truth_groups` directly. Build the same schema from the retained sample/full dimensions. Only new paths and a lossless local truth-checkpoint projection change. Prepare/train receive raw/model inputs only; load local evaluation truth after the sealed model stage.
- [ ] Reuse safe generic helpers from the frozen strict bridge: physical descriptors, exact truth shape, hashes, atomic JSON, OS locks and durable transactions. Its dependency snapshot may be reused as a frozen environment closure and extended with all new local adapter/runner/replay source descriptors. Do not invoke its author-dependent acceptance/orchestration, change its globals, or pass local truth as an alleged author truth.
- [ ] Implement a small local completeness adapter with explicit namespace and `expected_local_truth` inputs. Enumerate prepared main/unmatched HDFs, static metadata references, all six model pickles/five training records, three frozen stage guards, moments/helper build and exactly 26 query files. Do not clone/change learning code or copy the entire strict driver to replace status strings.
- [ ] In the fresh local worker only, route the frozen core CI helper's OUTPUT through a separate local context and restore it in finally. Bind this context source and test success/error restoration. Never mutate strict bridge/runner constants.
- [ ] Require local input physical hashes before/after all phases, exact source/runtime/plan closure, all 13 original SQL identities/order, all 2,059 local truth groups and explicit missing/extra/zero/nonfinite/error states. Preserve original central90 CI and same actual retained-sample references, row order/int64/pandas mean, and n/p normalizer.
- [ ] Add independent FORMAL/PUBLICATION lifecycle/receipt seals and whole-local namespace lock; exceptions/RUNNING tails taint the local namespace. No automatic rerun/repair or adoption of old strict outputs.

Suggested model result status: `PASS_LOCAL_SSB_SF500_MODEL_AQP_CI` or `LOCAL_MODEL_QUERY_ERRORS_RECORDED`. Mandatory fields retain original source MISMATCH, all 1,713 author differences (or an exact sealed descriptor), `author_reproduction_complete=false`, and `full_paper_reproduction_complete=false`. A local engineering stage PASS never changes the primary author ledger.

## Task 3: Local plan and owned supervision

**Files:** New `code/full_ssb_local_model_run.py` and tests.

- [ ] Write failing tests for closed local approval, wrong candidate/source SHA, wrong local namespace, missing bootstrap/worker trace and incomplete supervisor PASS.
- [ ] Reuse frozen operational primitives `OwnedWindowsJob`, `LiveResourceProbe`, `run_owned_child`, `base_python_executable`, `launch_inherited_venv_worker` and the reviewed resource policy. These are generic and do not require opening the strict author latches.
- [ ] Add only a local plan/approval and local bootstrap/worker dispatch. Direct base interpreter waits for GO, then verifies named-job membership and starts original `.venv` worker after assignment. Preserve the proven delayed-assignment behavior and record actual bootstrap/venv-launcher/worker PIDs, parent links and interpreter identities. Use a distinct local named-job prefix and source-bound local approval latch.
- [ ] Seal the complete local source gate, local scope, original mismatch SHA, fixed model settings, all frozen/local source/runtime dependencies and operational policy into the local candidate. Root reviews the canonical candidate SHA before plan sealing; root alone launches one controller after resource release.
- [ ] Require all seven operational artifacts and their publication links. Stop on resource violation and taint local supervisor/FORMAL/PUBLICATION; zero exit alone is insufficient. Default acceptance neither probes/launches processes nor repairs files.

Do not copy/rewrite the Windows-job implementation or modify the strict runner. Its path-specific author supervisor/verification functions are not reused as local success APIs.

## Task 4: Strict local read-only API and independent reverse replay

**Files:** New local model verifier and `code/full_ssb_local_replay.py`; root may separately implement local tables/status.

The proposed `verify_local_formal()` return shape mirrors the established descriptor API, but its successful status is `PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH` (plus `_WITH_ERRORS` if original query errors exist). It returns report/verification/seal/published-result/plan/controller descriptors, complete artifacts/dependencies, model path/SHA, actual sample rows, N, original ordered 13 queries, evaluation binding, original mismatch descriptor and explicit author-difference/local-only scope. Database connected, training, inference and files modified are false. Strict-author consumers must reject this distinct status.

- [ ] Write failing tests for missing local status/scope/original mismatch, author-status aliases, query subsets, omitted author-difference receipts and local result fed to strict-author consumers.
- [ ] Implement complete local source/model/supervisor read-only verification. It cannot create/fill missing artifacts or accept the source by changing the original TAINTED guard.
- [ ] Reuse frozen replay `execute_query`, `compare_query` and coverage helpers with the locally accepted model/source snapshot, fresh models/caches and reverse query order. New replay paths and status remain local-only; require all 13 identities and union groups, and do not retry original model errors as success.
- [ ] Independently review the source gate and model/operational adapters before any actual run. After root approves, execute preparation/train/evaluate once, then reverse replay. Retain actual timings/RSS and failed stages rather than claiming completion from a plan.

## Decision and publication boundary

If diagnosis identifies the author's customer/source variant, root can reject this proposal and continue the author reproduction through a separately reviewed corrected source path. If it remains unidentified, root may approve this explicitly local experiment without weakening any author gate. Either way, this plan writes no scientific receipt, changes no status/source flag and does not authorize a new generator run.

Any later local figure/table must carry `LOCAL_SSB_SF500` visibly, retain the author discrepancy and avoid ranking it as completed author reproduction. Root's primary full-paper ledger keeps SSB author AQP/CI incomplete. Flights-style local-population honesty is the precedent for scope labelling, not evidence that these two source populations are the same.
