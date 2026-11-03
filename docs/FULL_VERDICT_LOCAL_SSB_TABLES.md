# LOCAL SSB SF500 Verdict derived tables

`code/full_verdict_ssb_local_tables.py` exports a completed LOCAL Verdict run.
It accepts a run name rather than a particular attempt/version. Failed or
unfinished attempts remain ineligible. The exporter never resumes them.

The CLI calls `full_verdict_ssb_local_run.verify(home)` exactly once. That is
one fresh complete read-only source/plan/runtime/parent/receipt verification,
including the original source F. There is no acceptance cache, verifier skip,
fallback, replay, database connection or native execution in this entry point.
Even reusing an existing identical derived bundle requires the fresh verifier.
The exporter then reads the accepted `evaluation.json` descriptor, checks its
exact namespace/path, integer byte length and SHA256, and derives only from
those checked bytes. It checks the same evaluation bytes again before writing
derived outputs. It never calls a scientific evaluator or a second source F.

Run from the project ROOT only after the named formal run has completed:

```powershell
.\.venv\Scripts\python.exe -B code/full_verdict_ssb_local_tables.py --name COMPLETED_RUN_NAME
```

This is an actual complete read-only verification command, not a cheap status
probe. Do not run it alongside an unfinished scientific transaction or use a
failed attempt name. ROOT owns scheduling the actual acceptance/export.

## Files and provenance

The deterministic derived directory is
`output/full/figures/local_verdict_ssb_sf500_<binding-prefix>/`. Its binding
includes the fresh acceptance result and the exporter source bytes. An existing
directory must contain exactly the expected unchanged files; mismatches fail
instead of repairing or overwriting that archived bundle.

| File | Content |
| --- | --- |
| `query_summary.csv` | 32 rows: 26 original RAW results and 6 external two-SUM point adapters |
| `raw_groups.csv` | Population truth/prediction union for all 26 RAW results; normally 4,118 truth rows plus any extras |
| `adapter_groups.csv` | Separate Q4 truth/prediction unions for the 6 point adapters |
| `physical_calls.csv` | All 38 original call identities, SQL hashes and separate RAW/SUM_REVENUE/SUM_SUPPLYCOST roles |
| `RESULTS.md` | Explicit scope, gate, missing/zero/error/interval and timing limitations |
| `source_manifest.json` | Accepted source descriptors, exporter hash, row counts and derived artifact hashes |

The six public files are copied byte-for-byte to `output/results/` with the
`fullpaper_verdict_ssb_local500_` prefix. These public paths represent the latest
explicit export; prior binding-specific derived directories remain unchanged.
The source manifest records the five other derived artifact identities; the
CLI result records the manifest itself and every public/source byte identity.
There is no raw table, model, environment or original scientific receipt copy.

## Metrics and unavailable evidence

The LOCAL population has 3,000,028,242 rows and 9,996,946 retained fact rows.
The author comparison still differs in 1,713 of 2,059 truth groups. Both author
reproduction and full-paper completion remain false in the manifest and report.

Verdict registers the realized `n/N` fraction and scales points by `N/n`.
Original DeepDB retains its `n/p` normalizer. These are separate policies;
sharing the retained sample does not equate the two normalizers.

Missing population groups receive 100% relative-error penalties. Extra groups
remain records outside the truth denominator. An all-truth mean is suppressed
on engine errors, invalid predictions/metrics or zero truth, for which relative
error is undefined. Zero, missing, extra, NULL, nonfinite and engine-error
records remain visible. Nonfinite diagnostic values use explicit string tokens
in derived cells; they never become a finite estimate. Conditional matched means
use finite matched nonzero truth groups only and give their own denominator.

The scaling gate uses the Q1-Q3 original `nobound` results and the Q4 external
point adapters. It excludes the original Q4 compound-SUM outputs from that gate
while preserving their native behavior and their separate RAW errors. The
adapters consume two already recorded native child SUM calls; they execute no
additional calls. The report preserves a failed point gate as negative evidence
rather than requiring a scientifically successful outcome to export it.

Separate component SUM sample/population errors are unavailable: retained
profit moments do not identify either individual component. Their physical
identities and retained native result bodies remain separate in
`physical_calls.csv`; no component accuracy is fabricated. The sealed evaluation
retains Q4 native RAW/child bodies but not Q1-Q3 native result bodies or elapsed
times. Those unavailable Q1-Q3 fields remain empty.

Verdict's original native 95% intervals stay separate from DeepDB's central 90%
intervals. This exporter adds no DeepDB interval, composite adapter interval or
covariance model. Failed/invalid native rows remain diagnostics. A single
realized sample does not establish repeated-sampling coverage calibration, and
these records do not establish author hardware, sampling cost, end-to-end
latency or a runtime ranking.

## Pure tests

The tests substitute only the outer complete verifier and return synthetic
accepted descriptors. No actual source F, model, database, JVM, process scanner,
training or scientific inference is invoked. Synthetic temporary roots work
with pytest's default temporary directory outside this repository.

```powershell
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider code/tests/test_full_verdict_ssb_local_tables.py
```

The tests cover the 2,059-group/4,118-RAW-row shape, all 38 roles and 32 query
rows, the Q4 RAW/adapter split and sample-gate membership, unavailable component
errors/composite CI/timing, missing penalties, conditional denominators,
zero/nonfinite/error records, malformed matrices/scope/gates, descriptor changes,
exactly one verifier call including repeated exports, byte-exact public copies,
immutable bundle changes, and failure propagation before output creation.
