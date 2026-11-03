# LOCAL SSB SF500 Verdict: retained-sample results

LOCAL generated population: 3,000,028,242 rows; retained fact sample: 9,996,946 rows.
1,713 of 2,059 author truth groups differ. Author reproduction and full-paper completion remain false.

Verdict registers the realized n/N sampling fraction and scales points by N/n. Original DeepDB retains its n/p normalizer; the two normalizers are not silently equated.
A fresh complete read-only verifier accepted the source run before this export. No native calls, database access, sampling, training or inference are executed by this exporter.
The 38 original physical calls are recorded separately. The 32 query rows contain 26 RAW results and 6 external two-SUM point adapters; adapters reuse child calls and add no physical calls.
The sample scaling gate uses Q1-Q3 RAW nobound results and Q4 point adapters. Original Q4 compound-SUM behavior remains visible as RAW evidence.
Individual component SUM errors are unavailable: retained profit moments do not identify their separate sample sums or population truths.
Verdict native 95% intervals remain distinct from DeepDB central 90%. Composite adapter intervals are unavailable: no covariance model. No repeated-sampling calibration or latency ranking is claimed.
All-truth means assign 100% relative error to missing groups, exclude extra groups from the truth denominator, and are suppressed on engine errors, invalid predictions/metrics, or zero truth (relative error undefined). Zero, missing, extra, nonfinite and failed records remain in the CSVs.
Conditional matched means include only finite matched nonzero truth groups and report their denominator separately. They are not all-truth means.
Q1-Q3 native result bodies/timings are absent from the sealed evaluation; unavailable fields stay empty. Q4 RAW/child bodies are retained in physical_calls.csv. Native error rows remain diagnostics.

Sample gate: True. Evaluation: PASS_LOCAL_VERDICT_SAMPLE_SCALING_WITH_EXPLICIT_GAPS.
Recorded engine-error calls: 0.
Recorded unavailable native CI rows: 807.
Timing scope: Existing retained sample; no original3B sampling/end-to-end measurement
Accepted evaluation SHA256: `3179a5e6efddda9b35ca001b66e324897f126bd7c64a74768e3eff7c7fea3887`.

Files: query_summary.csv, raw_groups.csv, adapter_groups.csv, physical_calls.csv and source_manifest.json.
The public copies use the fullpaper_verdict_ssb_local500_ prefix. Their exact bytes and source identities are recorded in the source manifest.
