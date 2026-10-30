# Proposal only: separate LOCAL_SSB_10M_CI

No implementation, scientific execution, plan publication or change to the three frozen local providers is authorized by this document. The current 1M model/replay proceeds first. This proposal preserves the author-strict MISMATCH/TAINTED records, all three false flags, the 1713-group author gap and the incomplete primary full-paper SSB ledger.

## Purpose and fixed scope

Paper section 6.2, Confidence Intervals, says its reference uses 10 million samples and its models learn from the same budget. The AQP accuracy experiment uses 1M, while the README CI path still names a single1M model; this disagreement is already recorded in FULL_AQP_PROTOCOL, table row 142. The existing local1M result must continue to say `paper_figure11_training_budget_reproduced=False`. An additional labelled model can address this training-budget distinction only for our local population, never establish author SSB reproduction.

Proposed stage/scope: `LOCAL_SSB_SF500_SINGLE_10M_CI` / `LOCAL_SSB_10M_CI`. New namespaces only:

- `output/full/ssb/local_sf500_ci10m/{plans,runs,runtime}`;
- `output/full/results/ssb_local_sf500_ci10m.json` and separate verification/publication/supervisor seals;
- new `code/full_ssb_local_ci.py`, `code/full_ssb_local_ci_run.py`, configurable `code/full_ssb_local_stage_validation.py`, tests and protocol. Root separately owns any replay/table/status integration.

Every report/API must retain N=3,000,028,242, actual fact n=9,996,946, 2059 LOCAL integer truth groups, 346 matching/1713 differing author groups, original report SHA `740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e`, `author_reproduction_complete=False` and `full_paper_reproduction_complete=False`. New read-only success should be a distinct `PASS_READ_ONLY_LOCAL_SSB_10M_CI_WITH_AUTHOR_MISMATCH`, never accepted by the existing1M or author-strict verifier. Actual original errors append `_WITH_ERRORS` and remain explicit.

## Reuse and minimal training adaptation

After successful1M formal/reverse acceptance, bind the actual source gate (currently source receipt SHA `75fef537963dcbc183a720f2abc1b47b6972550822ba4591dec8f8336183e712`) and successful1M prepared outer receipt/lifecycle, HDF seal, metadata, all main/unmatched HDFs, raw/source/runtime closure, lossless truth projection and exact native moments/helper/process/seals. Rehash all consumed physical files before/after the new model, but do not prepare HDFs or run the moments executable again. No copies/hardlinks/rewrites of these trusted artifacts are needed. Bind actual successful1M report/replay descriptors as lineage; their scientific bytes remain unchanged.

Frozen `full_ssb_model.train_single_models` explicitly rejects cap>1M (line 763). Merely changing a model config cannot work. The preferred minimal adapter is an independently sealed, fresh-worker-only function extracted from that exact pinned function source, replacing **only** the engineering cap condition `100<=sample_cap<=1000000` with `100<=sample_cap<=10000000`. The exact original source SHA, unique replacement count, before/after function-source hashes, new adapter source and fixed original science hashes must be recorded. No sampler, learning formula, RNG action, checkpoint payload or original parameter changes. The misleading legacy exception text can be retained as part of the exact source patch and explained; a second text edit is not necessary for semantics.

Compile this one function against a copy of the frozen module's globals, preserving the frozen module path/source used by component_code_hash. In a fresh process, temporarily route only `core.train_single_models` to the adapted callable while calling frozen `guarded_train`; restore it in `finally`. Record this runtime adaptation independently: the old core hash alone does not describe the executed cap adapter. No frozen file on disk changes. Unlike replacing the complete driver, this retains original bounded reads, per-table RNG checkpoints and all frozen guard layers.

Before formal use, synthetic boundary TDD must reject zero/multiple patch matches and mutations outside the sole cap comparison. A small real golden model at cap<=1M must compare the adapted loop against frozen `train_original_reference`/original naive entry: actual sampled matrices, all five node structures, tuple normalizers and post-table NumPy/Python RNG states must match. A second synthetic boundary gate must exercise cap10M acceptance without allocating10M rows. Failure/interruption/restore tests must prove completed per-table checkpoints are not retrained and source adaptation is restored on exceptions. This is a new code/operational review, not covered by current1M approval.

Use single, RDC .3, seed1, original post_sampling_factor10, .01 minimum-slice fraction, max_table_data20M, original no-bloom/no-incremental learning and one-thread context. Original `generate_n_samples` caps sampling rates at1 and only final-samples if the returned frame exceeds cap; it does **not** allocate a100M post-sample table at a10M requested cap. The largest physical read remains the15M-row customer HDF. Actual training rows must be recorded, not rounded to10M:

| Component, in original schema order | Actual rows with cap10M |
| --- | ---: |
| lineorder | 9,996,946 |
| dwdate | 2,556 |
| customer | 10,000,000 from15M |
| part | 1,800,000 |
| supplier | 1,000,000 |

Retrain **all five** components. The first fact step changes sampling and global NumPy consumption; subsequent data/RDC/KMeans sampling and saved RNG states therefore change. Even a date component with identical input is not a proved interchangeable checkpoint because its saved post-table RNG state belongs to the1M sequence. No1M component reuse is justified without a separate full state equivalence proof, and saving a tiny date fit does not warrant that complexity.

## Configurable validation and CI

Extract only the required-set/stage-validation logic into a new configurable helper: cap, exact per-table actual row counts, input/prepared/moments directories, source descriptors, namespace, report status and scope are parameters. Do not clone the whole model driver or alter frozen1M validators. The10M entry is a thin orchestrator over that validator, frozen prepare-PASS reader, runtime-cap adapter, guarded_train, guarded_evaluate, population_truth_groups and the already sealed moments. Full26 ordered query/seal files, sibling outer guards, checkpoint/RNG files, all runtime/native sources and complete publication links remain required. Never accept a self-resealed subset or substitute author truth.

The fact training frame is the entire actual retained sample, so confidence_sample_size and reference n are both9,996,946. Keep exact cutoff `61482997997673935 / 2**64`, actual learned fact n/p (~2,999,383,738.3738375), exact population N for reference scaling, original central90 intervals/formulas, count<10 exclusion, all13 SQL and missing/extra/zero/error states. Reusing the moments is scientifically appropriate because they were computed from this exact fact sample, not a1M subsample. Point predictions should also be saved for audit, but this phase does not replace the paper's1M AQP accuracy table.

## Memory and storage admission

RDC columns use at most10K sampled rows and KMeans fits at most100K, but KMeans predicts on the **whole** local matrix; variance, projections and row splits also use/copy whole data. These caps do not imply a100K-row memory footprint.

The actual fact count and frozen schema give16 prepared columns and10 training columns. Float64/int64 payload calculations, not RSS measurements:

| Object | Payload |
| --- | ---: |
| fact HDF frame,16 numeric columns | 1,279,609,088B (1.192GiB), plus79,975,568B index |
| fact training matrix,9,996,946×10×8 | 799,755,680B (0.745GiB) |
| customer expected training matrix,10M×3×8 | 240,000,000B (0.224GiB) |
| customer conservative schema bound,10M×6×8 | 480,000,000B (0.447GiB) |
| part upper bound,1.8M×7×8 | 100,800,000B (0.094GiB) |
| supplier upper bound,1M×5×8 | 40,000,000B (0.037GiB) |

The customer3-column expectation follows the existing high-cardinality string removal/FD/multiplier rules; final1M prepared metadata must establish actual columns/dtypes before sealing any estimate. Part/supplier bounds intentionally allow columns that profiling may drop. Date2556 rows is negligible. One full fact-frame copy can transiently cost another1.192GiB; frame+numeric matrix+variance/cluster copies can consume several GiB. The lower-bound working set is therefore already multiple GiB before libraries, model trees and queues. A <=6GiB RSS completion guarantee is **not** proven by this arithmetic.

Retain unchanged owned-job live policy: <=6GiB observed tree RSS, >=1GiB available RAM, >=8GiB free disk, <=16GiB combined SSB storage, same timeouts/scanning/accounting. Minimum existing launch gate remains5GiB; for10M request root admission with at least7GiB free RAM (6GiB owned allowance+1GiB live floor), preferably8GiB. Record actual1M peak and actual HDF/matrix shape first; a root decision may reject or defer if headroom is insufficient. Never loosen thresholds or resize the dataset to obtain a PASS. A stopped10M namespace remains TAINTED, with trusted1M artifacts intact.

A read-only pre1M-completion storage snapshot found7,620,609,370B (~7.097GiB) in data/ssb + output/full/ssb, leaving8.903GiB to16GiB. This is time-specific and excludes future1M preparation/model output. Reuse means those existing bytes are counted **once**; do not apply the default5GiB preparation reserve again. After1M completion, rescan actual combined bytes and file sizes. Proposed new-stage output allowance is2GiB model/checkpoint/ensemble/transient serialization plus64MiB control/logs, explicitly an operational allocation rather than a proven model-size bound. Admission requires actual_total+allowance<=16GiB and free>=8GiB, using check_resources(additional_bytes=that allowance), while the live monitor keeps the unchanged16GiB limit. If actual1M sizes or serialization behavior invalidate the allowance, revise/review the plan before launch; do not claim spare storage based on duplicate-free preparation alone.

Root remains the sole launcher. Begin implementation only after accepting this proposal; perform new pure/golden/operational review, then a physically sealed candidate and explicit reviewed-plan SHA/resource release. Do not run concurrently with Verdict/PG or another model. First1M model/replay acceptance remains the dependency, and this planning task must not delay that stage.
