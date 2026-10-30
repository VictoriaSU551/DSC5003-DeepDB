# Flights reverse point and CI replay

This independent gate preserves the original Flights model, 33 sealed artifacts,
full_flights_model.py/full_flights_model_run.py and every CI formula. It does not
prepare/train/generate, parse the 10M-row sample, reconstruct moments or read the
1B-row population. Full artifact verification streams bytes for SHA256 only.

Plan: (1) RED/GREEN tests for scalar/row/interval shape, exact lengths, unique and
complete group keys, finite numbers and atomic namespace claims; (2) bind current
source/runtime, 33 original artifacts, original 1B truth/SQL/model and reference;
(3) explicitly replay once in a fresh process, SQL 11 through 0, with separate
cold-cache point and CI calls; (4) compare both point estimates and original CI
endpoints against all 331 stored groups; (5) seal, then audit without inference.

The original call defaults remain: rdc_spn_selection=False, merge_indicator_exp=True,
max_variants=10, exploit_overlapping=False, exploit_incoming_multipliers=True.
CI calls explicitly set confidence_intervals=True and confidence_sample_size=9997912;
point calls set confidence_intervals=False. The original population normalizer is
1,000,000,000, the actual training sample is 9,997,912, one SPN has ten columns.
Both calls use the original parser and model-aware factor cache, cleared before
each call. No canonical-selection or formula patch is introduced.

An atomic mkdir claims a digest namespace before any worker starts. A completed
matching seal may be verified/reused; an incomplete claim fails rather than
silently repeating the replay. Audit never starts a worker and fails on missing
evidence. Resource control covers only its owned process tree using stable Windows
handles, a 2GiB RSS cap, normal priority and process-local numerical thread limits.

This checks replay correctness of the existing local original-population-scale
Flights component. A single realized sample and the original independence-based
CI are preserved; the gate does not establish repeated-sample calibration or
complete the paper. Results will be recorded only after actual execution.

## Executed gate and preserved development failure

The first actual attempt in model_29a09e9ffc928288_74f1903616db7d70 completed
point/CI comparison for all twelve SQLs (all twelve PASS lines remain in stdout),
then failed its final identity grid because the wrapper reused `groups` for both
the expected count and the group-row list. No PASS receipt was committed. Its
source snapshot, logs, resource receipt and exclusive claim remain unchanged.
The fix separated `expected_groups` from `groups`, added failing-then-passing
count/serialization regression tests, and persisted each completed query as an
atomic JSON snapshot before final validation. No original algorithm was changed.

The successful namespace is model_29a09e9ffc928288_53023563b5829cd5. Its new process
loaded the original model once and executed query numbers 11,10,...,0, with point
then CI and a cleared model-aware cache before each call. All 331 groups, both
point estimates and both interval endpoints exactly match the original stored
values: maximum difference zero (the gate allows rtol=1e-9, atol=1e-7). There are
24 actual successful calls in this committed run. Across development there were
48 calls including the 24 in the preserved failed attempt; we do not label that
first failed wrapper gate a successfully sealed replay.

Resource cap: 2GiB; observed peak tree RSS 168,984,576 bytes (161.15625MiB),
elapsed 22.726004s, no cap breach. Successful call wall totals 3,800,425,700ns.
Python and NumPy seed1 state digests were equal before/after; actual process
PYTHONHASHSEED=0 and its four hash fingerprints, package versions, numerical
thread environment and original function defaults are recorded. During actual
inference, CSV/HDF/NPY opens plus NumPy load and pandas CSV/HDF readers were
blocked; original preparation/training/generation/moment construction entry
points were also blocked. The 33 old files and formal receipt retain identical
SHA256 and mtime_ns before/after. Binary integrity hashing is the only sample or
prepared-data access; no ten-million-row parsing or population scan occurred.

Source SQL identity stays byte-exact against the old evaluation. F2.2's generated
truth SQL contains one space after AND while the source has two; both byte hashes
are saved, and the truth SQL must be token-identical with quoted literals retained.
No source SQL or truth file was rewritten.

Key hashes:

- Frozen replay module: e4c97c63c74e64edb6cb404f3c9e35f249bdf94653df2d4026769d8a7bab4762.
- Original model: 29a09e9ffc928288f192dbec3946eb03e04179e6310e825c820a8b78715ec0fc.
- Original formal receipt: 65914e4ad6a6fd2b0dea606455c867b97059d35fef636c14b9aeb7d15f4e98c1.
- Original evaluation: 991b670b5a7241ce8465a4f8522d7247b8919c1d0f46f41f5106776e482168a7.
- New scientific verification: 49a534196321f53ee66cb06a220b2942b087dcf7c00c394db4f82b72a06244ec.
- New real replay result: da7e4015919b55f31a497a41197c1b1f43d23825a3390074489bcdeeaa05147f.

The focused replay/cache regression suite has 27 passing tests. Its TDD logs,
the earlier contract-implementation fixture failure, SQL-whitespace diagnostic,
the failed real attempt and all source snapshots are preserved. The cache proof
forbids model loading, evaluate_query and worker launch, then reuses the committed
result with zero new calls. No scientific replay is repeated after this gate.

## Permanent commands and integration contract

From the project root, use the existing Python3.8 environment:

```powershell
.\.venv\Scripts\python.exe -B code/full_flights_replay.py audit
.\.venv\Scripts\python.exe -B -m pytest code/tests/test_full_flights_replay.py code/tests/test_full_factor_cache.py -q
```

`audit()` requires output/full/flights-replay/final_seal.json and latest.json,
fails on missing evidence, verifies the exact complete nonempty namespace map,
current source/runtime and all original 33 artifacts, and reads saved predictions
only. It never starts a worker, unpickles a model, parses sample rows, or rewrites
any output. It returns status=PASS_READ_ONLY_FLIGHTS_REVERSE_AUDIT,
actual_new_predictions=0 and `verification={path,bytes,sha256}` for the formal new
receipt. The original formal binding fields are in that verified receipt's
`configuration.formal_receipt={path,bytes,sha256}`; the outer final seal also
provides `original_formal_receipt`. Original model/SQL/truth/evaluation records,
all 33 artifacts and the current source/package binding are in `configuration`.
The final-seal SHA is returned by audit, so no circular SHA is embedded here.

`replay` is the explicit once-only execution entry; a trusted completed matching
namespace is audited/reused, while any incomplete claim fails. Internal `_worker`
also requires its own exclusive `worker_started.json`, so it cannot silently
repeat an attempt. Re-running tests after final sealing must save any logs outside
the sealed namespace. Review should use stdout or an independent review directory.
