# Scalar Oracle Derived Tables Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. ROOT explicitly authorized this small design and implementation; no new agents or scientific operations.

**Goal:** Export the independently verified local scalar-oracle's70 predictions and separately bound SQL-confirmed labels as CSV, Markdown and an integrity manifest.

**Architecture:** One standard-library consumer calls the frozen offline verifier once, checks exact70 query-number/SQL identities against fixed official and prior PostgreSQL-confirmed labels, and evaluates the existing exact Fraction predictions. It writes a separate derived namespace and never estimates, collects counts, connects or joins the author comparison tables.

**Tech Stack:** Python3.8 standard library plus the already frozen scalar modules, without importing the heavyweight evaluation/model modules.

## Design and scope

- New files: `code/full_scalar_oracle_tables.py`, its dedicated test file, and this short design/plan. The original eight scalar files and `full_paper_tables.py` stay unchanged.
- ROOT selected a small independent consumer rather than changing an author-series exporter or adding a launcher. There are no plots, cross-method rankings or new scientific calculations.
- Exactly one fresh strict `full_scalar_oracle_audit.verify()` call precedes accepting predictions. Pin all three frozen provider sources independently and verify their actually loaded paths. Its exact seven physical artifacts, binding, receipts and final seal remain part of the derived identity.
- Labels are the fixed official70-row CSV and the prior independently executed PG11.5 `postgres_job_light.csv` with its fixed PASS verification/result hash. Check query numbers, exact SQL strings, equal positive integer truths and the fixed SQL file. Do not use SQL token equivalence or silently reorder rows.
- Raw numerator/denominator strings, including0/1, remain unchanged. Evaluation uses `EVALUATION_ONLY_FLOOR1`: both operands are floored at1 only when computing q-error. Median/p90/p95 use linear interpolation on sorted q-errors; max is the maximum. This differs from the existing DeepDB zero-estimate-to-infinity rule, so no shared ranking or author Perfect Selectivities claim is made.
- The derived binding includes source/label/accepted-artifact descriptors and the explicit metric policy. Output is `output/full/figures/scalar_oracle_<binding-prefix>/predictions_scored.csv`, `RESULTS.md` and self-sealed `manifest.json`; the full binding is retained in the manifest. Exact nonempty unique paths and deterministic bytes are required even on reuse. Incomplete or changed old outputs are refused, never repaired or overwritten.
- Default absence of an accepted run fails. Import is inert. The consumer never calls collect/predictions/model APIs, starts processes, connects to any database or writes outside the new derived directory. Tests use a synthetic verifier and temporary inputs only; no actual verifier is called before independent review.

## Tasks

- [x] Write semantic tests first for exact alignment, zero/Fraction preservation, positive truths, explicit quantiles and malformed/duplicate/incomplete inputs. Observe RED.
- [x] Implement minimal scoring and deterministic display.
- [x] Write full consumer fixtures with one counted offline verification and forbidden process/DB/collect/model APIs; test source/label/receipt/output tampering, reuse and missing results. Observe RED and implement the boundary.
- [x] Run only the dedicated pure/mock test file. Freeze the new candidate and hand it to baseline_sources for independent review. No actual result export, scientific API, sourceF, PG or plot in this task.

## Ledger

- Ruling: implement exact rational arithmetic and standard-library quantile interpolation locally, avoiding imports of numpy/pandas/SPN modules for a tiny exporter. The policy is explicitly independent from DeepDB's existing q_error.
- Ruling: ROOT approved the short proposal directly. This does not authorize a scientific run; any later actual invocation consumes only a separately accepted result.
- Evidence: the initial dedicated file produced34 RED cases for the missing consumer. Three additional observed RED cases rejected a floating query-count field, an overstated source boundary and a redirected output namespace after their guards were implemented. Final dedicated evidence:38 pure/mock tests passed in8.52s, `python -B -m pytest code/tests/test_full_scalar_oracle_tables.py -q -p no:cacheprovider --basetemp output/tmp/sctb --tb=short`.
- No actual scalar audit, database/collect/model/sourceF, accepted-result export or plot was invoked. The tests use a counted synthetic acceptance and temporary70-row labels. Existing production labels were inspected only as small provenance metadata, never passed into estimation.

## Later read-only use after independent review

```powershell
.venv/Scripts/python.exe -B code/full_scalar_oracle_tables.py --directory output/full/scalar_oracle/runs/<accepted-binding-prefix>
```

Default discovery also fails unless exactly one accepted scalar run exists. An unchanged result reuses only byte-identical derived files after a fresh strict offline verification; no raw results or author-series exporter is overwritten. This command is documentation and has not been executed in this implementation task.

Candidate v2 binds the collector v3 host-only PostgreSQL identity fix (`16e95d0a...`). The original three exporter sources and freeze are preserved. Only the runner literal changes in production; arithmetic, raw-zero handling, labels, seven-artifact acceptance and the single offline-verifier call remain unchanged. The old physical-source check correctly failed before this update; it did not invoke the scalar verifier or connect to a database.

Candidate v3 binds collector v4 (`d5d31f34...`), whose per-statement validation cap is 600 seconds after the real 36M-row snapshot exceeded 120 seconds. This exporter changes only that literal; no actual result is accepted or exported by updating the pin. Its original tests and calculation/acceptance rules are unchanged.
