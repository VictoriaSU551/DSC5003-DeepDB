# SSB GROUP BY prototype and CI reproducibility

The five completed LOCAL1M models and their original13-query report are preserved. Formal/publication/supervisor closure passed, but fresh reverse replay9c failed on S4.3. This is a real scientific acceptance failure, not a reason to relax numerical tolerances or retrain the models. The author-source mismatch remains1713 groups, and full-paper reproduction remains incomplete.

## Retained evidence

- Historical report: `output/full/results/ssb_local_sf500_model_aqp_ci.json`, SHA256 `da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82`.
- Model: SHA256 `7c9b9d4213ac660066ef974456128305db5369c8c216e98f14afdde82c45e912`. No training, preparation or sample-moment pass was repeated.
- Failed replay: `output/full/ssb/local_sf500_replay/runs/65d2b8a4fcd7899bd212`, TAINTED. Its old frozen verifier is never made to return PASS for this run.
- Targeted raw diagnostic: `output/full/ssb/local_sf500_replay_diagnostic/q12_v1/`. All800 point estimates matched, but all800 intervals differed.
- Observational traces: `trace2_original_0/` and `trace2_original_173/` below the diagnostic directory. Same model, SQL, random seed74031 and one thread; only the process hash seed differed.

The first S4.3 group `[1997,"UNITED ST0","MFGR#141"]` had point estimate1,329,300,065.031677 in both runs. HASH0 reproduced the historical interval `[-625436577.4079976,3284036707.4713516]`; HASH173 gave `[-686907314.5664053,3345507444.6297593]`. This is much larger than rounding noise.

## Mechanism and separate variant

The released `AQPSPN.evaluate_group_by_combinations` converts decoded groups through a set. `SPNEnsemble.evaluate_query` then constructs a prototype query from the first returned decoded tuple and uses the resulting cardinality factors for all group rows. In the observed original traces, HASH0 starts with supplier city ST7/brand146 and selects the supplier factorization (constant1,000,000); HASH173 starts with ST2/brand141 and selects the date factorization (constant2556). These decompositions have different uncertainty factors even when their final point predictions agree. In this five-single-table model, the `len(possible_starts)>max_variants` shuffle is not the applicable explanation. The earlier canonical greedy adapter alone did not resolve this CI difference.

`code/full_ssb_group_order.py` is a separate evaluation-only variant. It sorts paired technical/decoded rows by a fixed typed decoded key before prototype selection. It preserves scope columns, group membership, technical values and nested FD code lists. It changes no model, candidate score, cache, point formula or variance formula. Invalid/nonfinite/duplicate decoded keys fail closed. Exact integer keys are preserved. Context hooks restore on exceptions and nested use.

The adapter SHA256 is `48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c`. All15 pure tests and an independent code review passed. New formal receipts must bind this source and use their own namespace; the historical report is never overwritten.

## All13 diagnostic, not formal acceptance

`all13_group_forward0/` and `all13_group_reverse173/` retain all raw query outputs. Both used the new adapter and the original two evaluator calls per SQL, with a fresh ensemble per SQL, random seed74031 and one thread. The two processes executed52 evaluator calls and26 model loads in total. The original raw/prepared-data read guard was active.

`all13_group_comparison.json` checks2059 point values and4118 CI endpoints using the frozen relative1e-9/absolute1e-5 tolerances. Maximum relative difference between the two new runs was0. All points also matched the historical report within those tolerances:896 values differ in their last floating-point bits, with maximum absolute difference0.000244140625 and relative difference7.7062e-16. Relative to that report, intervals changed for600 S3.2 groups,100 S4.2 groups and800 S4.3 groups. The changes are retained, not presented as the old result passing replay.

An independent saved-array audit in `review/prototype_mediation_v1/audit.json` additionally checks the prototype-only intervention `trace4_proto_0/` versus `trace4_proto_173/`: move the same minimum decoded pair to the first position while retaining each process's remaining original batch order. The other799 positions differed between processes. Pair multisets were unchanged;12 candidate scores (including float.hex),3 selected factorizations/values, and all keyed CI means/stds agreed exactly. Independent recomputation of both product-variance stages agreed exactly, and all800 resulting points/1600 endpoints agreed. The audit read48 retained inputs without modifying their bytes or mtimes and made no model calls. This supports the prototype-to-factorization-to-variance mechanism for the observed S4.3 failure, independently of the remaining batch order.

These diagnostics do not replace formal acceptance. The planned canonical transaction uses the original forward evaluator with one ensemble, then a separate reverse process with13 ensemble loads, complete parent/artifact closure, owned-process monitors and distinct logs. The10M/table CI and LOCAL Verdict experiments must wait for that accepted parent. Existing Flights CI and earlier verified experiments are not repeated.
