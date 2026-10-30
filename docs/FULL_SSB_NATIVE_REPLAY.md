# Native SSB independent replay plan

> For agentic workers: use the executing-plans skill task by task. No formal
> prediction is authorized by the existence of this document alone; the final
> native population and model source gates must pass first.

**Goal:** independently replay the corrected native SF500 model without changing
the previous failed population, the old model protocol, or any sealed helper.

**Architecture:** a new `full_ssb_native_replay.py` consumes the new bridge's
strictly read-only `verify_formal()` API. A fresh worker loads the saved model
once for each of the thirteen SQL statements in reverse order, executes point
and CI paths, and compares complete keyed outputs against the accepted original
order. The frozen `full_ssb_replay.execute_query`, `compare_query`, and `coverage`
routines are reused; their old hard-coded source discovery and output paths are
not used.

**Tech stack:** project Python3.8, existing RSPN/NumPy stack, standard-library
atomic JSON and physical SHA256 checks.

**Spec:** [native model I/O contract](FULL_SSB_NATIVE_MODEL.md) and the frozen
[previous replay protocol](FULL_SSB_REPLAY.md). The final bridge return schema is
still being agreed. This is an implementation plan, not completed evidence.

## Global constraints

- New files: `code/full_ssb_native_replay.py`, the thin derived-output adapter
  `code/full_ssb_native_tables.py`, their focused tests, and this document.
- All new replay evidence belongs to `output/full/ssb/native_v2_replay/`.
- Keep the frozen model, guard, and old replay sources byte-identical.
- Thirteen model loads and twenty-six real evaluator calls, with all thirteen
  exact SQL identities and complete point/CI group grids. Missing, extra,
  nonfinite, and CI-excluded groups remain separate scientific limitations.
- Hash seed173, Python/NumPy seed74031, four numerical thread limits1. Preserve
  the frozen comparison tolerances (`rtol=1e-9`, `atol=1e-5`).
- `verify` must never start a process, predict, repair, write, or fill a missing
  record. `replay` is the only controller entry that may explicitly launch one
  fresh worker. Existing accepted evidence is verified and reused.
- Do not call the old replay's `source_snapshot`, `worker`, `replay`, or `verify`.
- Native row-count/author-query agreement is not proof of byte identity with
  the author's entire raw dataset. One-sample CI comparison is not calibration.

## Review focus

1. A subset or duplicate artifact/query inventory must fail even when resealed.
2. A missing formal PASS must fail before a prediction or new namespace appears.
3. A failed/RUNNING namespace cannot be silently rerun or promoted to PASS.
4. Source, parser, runtime, raw input, HDF, and model snapshots must agree before
   and after execution; the read-only acceptance must recompute the same binding.
5. Point/CI raw lengths and group identity sets must be checked before zipping;
   matching null representations alone do not prove nonfinite point equality.

## Tasks

- [x] Pin the bridge's read-only return schema and write failing tests for
  the exact thirteen identities, twenty-six query artifacts, counts, paths,
  duplicate groups, and changed coverage. No formal prediction in unit tests.
- [x] Implement source binding and unique atomic worker ownership. Only use the
  already accepted formal model. Preserve lifecycle errors and worker logs.
- [x] Implement reverse worker with the frozen per-query executor, full snapshots,
  complete per-query seals, exact call/load accounting, and separate coverage.
- [x] Implement strict read-only acceptance, including complete required output
  sets and recomputed numerical comparisons. Test with execution/write APIs
  forbidden and unchanged artifact hashes/mtimes.
- [ ] After independent review and a real formal model PASS, explicitly execute
  one fresh reverse replay, retain actual output, and independently verify it.

No native SF500 model or replay has been executed at the time this plan is added.

## Implemented gates and derived views

The focused replay suite has28 pure/synthetic passing tests, including an actual
mock worker loop that proves reverse order and reader restrictions, source-change
TAINTED behavior, refusal to reuse the same namespace, strict inventory/coverage
checks, and read-only acceptance with prediction, subprocess and write operations
forbidden. Mock outputs are disposable fixtures under `output/tmp/`; none are
formal scientific evidence. The implementation received independent static and
synthetic review before actual execution.

The bridge API returns `PASS_READ_ONLY_SSB_NATIVE_V2_FORMAL_MODEL`, the original
thirteen `queries`, `model_path/model_sha256`, `sample_rows/population_rows`,
`evaluation_binding`, `dependencies`, and complete physical `artifacts`.
Descriptors for `verification`, `verification_seal`, `published_result`, `plan`,
`formal_receipt`, and `formal_lifecycle` are also part of the source snapshot.
An error-bearing formal report cannot be certified as a successful replay.

After an actual accepted replay, `full_ssb_native_tables.py` reuses the frozen
SSB summarizer and plot routines without predicting. It checks the new source
identity, five actual training budgets, full raw-byte-identity disclaimer, and
model report hash before generating five derived CSV/PNG outputs in
`output/full/figures/aqp_ssb_native_v2_<hash>/`. The pointer is
`output/full/results/ssb_native_v2_tables_latest.json`; old failed/gated SSB paths
are not overwritten. Its ten pure scope tests and eight existing mathematical
summary/cache tests pass. Actual charts still await formal scientific evidence.

```powershell
.venv/Scripts/python.exe -B -m pytest code/tests/test_full_ssb_native_replay.py code/tests/test_full_ssb_native_tables.py -q --basetemp output/tmp/nr
# Only after the native population and formal model are independently accepted:
.venv/Scripts/python.exe -B code/full_ssb_native_replay.py replay
# Daily read-only acceptance; no fallback predictions:
.venv/Scripts/python.exe -B code/full_ssb_native_replay.py verify
.venv/Scripts/python.exe -B code/full_ssb_native_tables.py
```
