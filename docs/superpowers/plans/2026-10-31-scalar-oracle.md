# Scalar Oracle Local Variant Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. No subagents and no actual database/scientific operations in this implementation task.

**Goal:** Build a local single-table scalar-oracle baseline for the fixed 70 JOB-light queries, executable only with an exact reviewed plan and ROOT approval receipt.

**Architecture:** A standard-library contract/parser and exact Fraction estimator; a separately gated, read-only PostgreSQL collector; an offline verifier that independently recomputes every prediction and validates current physical dependencies. The declared uniform title-key formula is our local variant, not the unidentified author Perfect Selectivities configuration.

**Tech Stack:** Python 3.8 standard library; psycopg2 imported only by an explicitly enabled future execution.

**Spec:** ROOT delegation and docs/FULL_SCALAR_ORACLE_PROTOCOL.md. Formula approved by ROOT: filtered title count times each filtered child count divided by the unfiltered title population once per child.

## Global Constraints

- Own only new scalar-oracle code/tests/docs. Preserve all old scientific sources and results.
- Register exactly 70 pinned SQLs and 50 distinct single-table conjunctions.
- No multi-table truth enters estimation. Raw zero remains zero; metric flooring is evaluation only.
- No PostgreSQL start/connect, raw CSV scan, generation, model operation, installation or scientific query during this task.
- Future actual execution requires a current source-bound reviewed plan and explicit ROOT approval; no hard False switch or fabricated state is needed. Never recover an interrupted namespace as PASS.
- Existing import receipts are historical lineage. A new current query-column snapshot is not a retroactive all-column CSV identity proof.

## Review Focus

- Duplicate/missing joins, aliases, unsupported expressions or changed workload must fail before query generation.
- NULL/duplicate primary keys and NULL/orphan foreign keys must fail the uniform-domain assumptions gate.
- Fraction arithmetic must retain zero and integers above 2**53 exactly.
- A self-resealed subset, stale plan/dependency or incomplete result collection must not pass verification.
- Default offline verification must not connect, launch processes, load models or write files.

### Task 1: Pure scientific contract

- [x] Write tests for pinned inventory, strict parsing, hand-derived correlated toy, zero and malformed counts.
- [x] Observe RED; implement code/full_scalar_oracle.py; verify focused GREEN.
- [x] Declare the variant, assumptions and provenance limits in the protocol.

### Task 2: Gated collector and physical plan

- [x] Write tests for absent/unbound approval rejection, read-only SQL sequence, single-table aggregation, snapshots, exact approval and persistent TAINTED state.
- [x] Observe RED; implement code/full_scalar_oracle_run.py without executing any real database API.
- [x] Implement exact source/runtime/input discovery and before/after physical validation; actual runtime discovery remains for ROOT review, not executed here.

### Task 3: Independent offline acceptance

- [x] Write synthetic receipt tests for arithmetic, exact required file sets, source changes and no-operation verification.
- [x] Observe RED; implement code/full_scalar_oracle_audit.py.
- [x] Run only new explicit pure/mock tests and hand candidate to ROOT for independent review. No commit/index edits by this worker.

## Execution ledger

- Approved inline scope comes directly from ROOT delegation; no additional design approval is required.
- Existing shared reproduction/full-paper checkout is authorized. No worktree or index mutation.
- Full pytest is deliberately excluded by the explicit resource/science restriction; only new file-scoped tests are permitted.
- Ruling: ROOT accepted current query-column snapshots and historic import lineage, and requested a complete plan/approval-gated future execution path instead of permanent False latches. No actual execution occurs in this task.
- Ruling: PostgreSQL temp_file_limit is 1 GiB, not the initial 128 MiB, because exact DISTINCT-id validation on 36M rows can spill more than 128 MiB. Client RAM/free-disk/serial-query/statement/total-window caps remain explicit and require future ROOT approval.
- RED/GREEN: initial API stub produced 20 failed tests, then core 20 passed. Collector stub produced 13 failures. Offline verifier stub produced 18 failures. Additional observed RED failures covered wrong loaded modules, missing/stale monitor evidence, psycopg2 transaction setup, PG environment restoration, total wall cap, empty runtime members, and a new explicit retry attempt.
- Candidate v1 focused evidence: 69 passed in 4.85s with `python -B -m pytest code/tests/test_full_scalar_oracle.py code/tests/test_full_scalar_oracle_run.py code/tests/test_full_scalar_oracle_audit.py -q -p no:cacheprovider --basetemp output/tmp/scall8 --tb=short`.
- Independent v1 review found two Important defects: idle cancellation did not prevent later COPY statements, and an injected SystemRoot could seal a different DLL from the actual loader. Original eight-file bytes were saved before editing under `output/full/scalar_oracle/review/candidate_v1/source_snapshot/`; freeze SHA256 `da804a1d3e03cea3d46251f42dee39b9eed7336309abe945f10c36c86304b2cc`.
- Candidate v2 observed six RED cases, then six GREEN: resource failure before SQL, within/between COPY blocks, after the before-snapshot, failed cancellation, plus the external-DLL path/loader boundary. Guarded cursor operations and per-write checks now stop subsequent work permanently. Monitor finalization failures are separately covered through the actual collector-to-TAINTED control path using synthetic cursors only. DLL inventory and both native loaders use the same absolute literal, with exactly one external whitelist member.
- Candidate v2 complete focused evidence is recorded by its separate freeze manifest; no actual database or native helper operation is part of these tests.
- No actual runtime/source audit, execution plan, approval, PostgreSQL connection/query, raw CSV scan, OS native helper call, model operation or baseline metric was produced. All complete-run examples are synthetic fixtures under output/tmp.
