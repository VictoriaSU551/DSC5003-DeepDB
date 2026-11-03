# Flights RSPN/AQP/CI Implementation Plan

> **For agentic workers:** Execute this plan inline, with TDD and the existing parent review; do not spawn agents or modify frozen sources.

**Goal:** Fit the original Flights FD/RSPN model and evaluate all 12 AQP queries and central 90% intervals against this exact generated population.

**Architecture:** A local header-aware preparation adapter calls the unchanged upstream FD preparation. Sealed stages bind completed generation, sample bytes and actual rows, query SQL, model driver and upstream algorithms. Exact integer sample sums/squares provide an independent sampling CI reference.

**Tech Stack:** Existing `.venv`, Pandas/NumPy, SPFlow/RSPN, SQLite/Decimal, SciPy normal quantile. No dependency changes.

**Spec:** Parent request plus [paper Sections 5.1/6.2](https://www.vldb.org/pvldb/vol13/p992-hilprecht.pdf), `FULL_REPRODUCTION_PROTOCOL.md`, `FULL_FLIGHTS_STREAMING.md`.

## Global Constraints

- Preserve all frozen generator and original algorithm files; write only the dedicated driver/test/document and `output/full/flights/model*`, `prepared*`, `results/flights_model*.json` outputs.
- Reuse already verified 200K generation and exact 12-query truth. Do not regenerate or re-run its SQLite population gold standard.
- Formal input requires completed 1B generation, exactly 1e9 population normalizer, and a sealed actual sample no larger than10M. Record requested/actual separately if Bernoulli produces fewer rows.
- Only the 200K small model is authorized initially; formal model training waits for parent memory release.
- Read the exact12 uppercase header columns using `header=0`; call unchanged Flights FD preparation and RSPN RDC=.3/minimum cluster=1% actual training rows.
- Use the model-aware factor cache adapter and reset cache before every query. Keep missing/extra groups and zero truths visible.
- Center90% uses `norm.ppf(.95)`; exclude sample filter/group counts<10 explicitly. Keep original model CI and independent reference side by side.
- No commit/push or global installation.

## Review Focus

- Header mismatch/duplicate/header-as-data must fail before numeric preparation.
- A completed-looking source with missing/incomplete or conflicting truth must fail before formal training.
- Changed sample/driver/prepared/model artifacts must refuse reuse; complete trusted stages must retain timestamps.
- Every truth group and every model-only group must appear in results; no silent matching-only mean.
- Difference/product aggregates, SQL NULL and strict bounds must preserve arithmetic and exact sample moments; SUM reference must not mix count and probability units.

## Task1: Input and preparation gate

- [x] Write failing tests for header, completed population/sample pairing, and modified seal refusal; run RED.
- [x] Implement `load_generated_input`, `read_sample_header`, `prepare_input` in `code/full_flights_model.py`; use the original preparation under a scoped local reader override.
- [x] Run input tests GREEN and actual200K preparation; verify numeric columns and FD metadata survive.

## Task2: Recoverable model and all-group AQP

- [x] Write failing tests for all-group alignment, missing/extra/zero truth handling and sealed model reuse.
- [x] Implement atomic `train_model`/`evaluate_model`, normalizer and actual sample size checks; clear cache for each SQL and retain raw model CI/predictions.
- [x] Train the new1993-row golden sample model only; run all12 queries against existing200K truth and record every group/status.

## Task3: Independent sample CI and final gate

- [x] Write failing tests with hand-derived integer moments for AVG/COUNT/SUM/products/differences, NULL, strict bounds and count9/10 threshold.
- [x] Implement exact integer sums/squares using the same actual training sample. AVG variance is `s²/m`; COUNT variance is `N²*p*(1-p)/n`; SUM variance is `(Var(C)+E(C)²)*(Var(AVG)+E(AVG)²)-E(C)²*E(AVG)²`.
- [x] Compare upstream `evaluate_stds` numerically and record its SUM dimensional mismatch; never use it as reference truth.
- [x] Persist group coverage, CI sample exclusion, reference/model coverage and relative half widths. Verify resume reuses prepared/model stages without new learning.
- [x] Run focused tests: 15 passed, including the original numeric leaf's NULL sentinel and strict-bound behavior.
- [ ] Await the already-running project test command; report small-scale completion separately from pending formal1B training.

## Paper interpretation

Section6.2 uses Flights scaled by IDEBench to1B with10M training rows; group query relative errors average over groups. Section5.1 combines factor variances assuming independent estimates and a normal final estimate. Figure11 reports relative half width, not full interval width; remove cells whose sample filter/group count is below10. F5.2 violates the independence approximation because the two SUM terms share correlated quantities, so retain this limitation and the original predicted interval.

The released `confidence_interval_evaluation.evaluate_stds` SUM branch combines a count-scale variance (`n*p*(1-p)`) with a probability-scale mean (`p`) before scaling; the independent reference uses matched count-scale mean and variance and records the released result as a separate comparison.

## Executed200K gate

No generator or population SQLite gold-standard stage was repeated. Input is the already sealed
`golden-200k/continuous`: population200000, actual Bernoulli training sample1993,
sample SHA256 `5a59fd5538a0946cea74accca732f274c2e3e9927c247f32ee14f61d450a7390`.
`requested_training_rows` is the CLI cap (default10M), not a claim that the200K golden run should contain10M samples;
its1% source sampling expectation is2000. Formal training records the actual count below the10M cap honestly.

Original FD preparation removes the two dependent state columns, leaving10 model columns; all6 numeric aggregation/filter columns remain.
Model `full_join_size=200000` and `full_sample_size=1993`. The prepared HDF/metadata/NPY and model are atomically sealed.
Stage bindings hash the relevant driver functions, protocol, original algorithms and runtime so adding an evaluation routine does not redo a trusted preparation/model.
Only the header reader is temporarily replaced while calling the original preparation function, and it is restored in `finally`.

All12 SQLs executed with no query exception. The result retains all296 truth groups and every model-only group:

| Query | Truth | Model | Missing model | Extra model | Reference CI eligible |
|---|---:|---:|---:|---:|---:|
| F1.1 |1|1|0|0|1|
| F1.2 |1|1|0|0|1|
| F2.1 |26|26|0|0|0|
| F2.2 |23|26|0|3|0|
| F2.3 |17|22|0|5|0|
| F3.1 |22|22|0|0|0|
| F3.2 |41|49|0|8|0|
| F3.3 |23|26|0|3|0|
| F4.1 |50|42|8|0|0|
| F4.2 |22|26|0|4|0|
| F5.1 |22|22|0|0|0|
| F5.2 |48|51|0|3|0|

The294 reference-ineligible truth groups remain saved with `EXCLUDED_SAMPLE_COUNT_LT_10`.
This is a pipeline test with a small sample, not a successful reproduction of the paper's error/CI figure.
Missing model aggregates stay null. A matched-only error and an explicitly named unit missing-group penalty are separate fields;
the penalty is not presented as a model prediction. Zero truth retains absolute error and an undefined relative error.

For exact moments, a dedicated SQLite sample table stores numeric tenths as integers. A Python integer aggregate accumulates sums and squared sums without SQLite64-bit SUM overflow.
Unbiased variance is derived with exact rational arithmetic, including a1e12-offset regression test that would suffer floating cancellation.
AVG and product SUM ignore NULL expression values; SUM difference uses per-row zero contributions for nullable components,
with component non-null counts saved and an all-null SUM component marked undefined. This preserves `SUM(out)-SUM(in)` rather than silently replacing its NULL behavior with `SUM(out-in)`.
Native Windows SQLite and JSON paths are kept below MAX_PATH using short digest filenames; the original sources are unchanged.

The hand-check fixture `N=200,n=20,m=10,x=1..10` gives SUM variance24750 under the consistent product formula,
while released `evaluate_stds` gives15606.25. This diagnostic is saved separately in
`output/full/results/flights_model_ci_formula_audit.json` because neither SUM query has10 qualifying rows per group in the1993-row golden sample.

Commands:

```powershell
.venv/Scripts/python.exe -m pytest code/tests/test_full_flights_model.py -q
.venv/Scripts/python.exe code/full_flights_model.py all
.venv/Scripts/python.exe code/full_flights_model.py audit --source flights-1b --paper
```

Only after completed1B generation/truth and parent memory release:

```powershell
.venv/Scripts/python.exe code/full_flights_model.py all --source flights-1b --paper --formal-memory-approved
```

Golden evaluation: `output/full/results/flights_model_9ae3b6a3aec344744cc9aff3e9747a92c1c023c48306b53b24dd0f033176c761_evaluation.json`.
Golden model: `output/full/flights/model_366e080799c63ec3916d75ba6ddab39f1f1f29b6d2b3c273b1d9401ba16d1f93/ensemble.pkl`.
Focused suite currently15 passed, including a guard that fails if a trusted stage calls upstream preparation/learning again.
The full repository test command is recorded separately because it includes other workers' compiled-boundary/resource tests.

The golden handoff seal is `output/full/flights/model_golden_validation.json`. It binds this driver, its tests and protocol,
the completed source generation/truth, prepared/model artifacts and full evaluation. Formal1B preparation/training has not run.
The upstream FD group-by path merges ancestor values with identical translated state groups before returning predictions;
the wrapper therefore retains the original combined state estimates. No upstream grouping algorithm was changed.
