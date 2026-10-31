# Original Verdict 0.4.7 SSB existing-sample candidate

Status: **CANDIDATE; no SSB database or engine execution authorized by this entry point.** This is a new comparison namespace. Previous Verdict/Flights and SSB generator/model files remain frozen. This document records the design accepted by the root task before implementation; the module initially exposes only pure planning and read-only inspection.

## Scope and information budget

Use the eventual accepted corrected SF500 fact sample and the complete customer, supplier, part and date dimensions. The fact population is 3,000,028,242 rows. No 3B-row original table is materialized, no original-table sample is created by Verdict, and no original-table sampling or end-to-end preparation cost can be reported. The original `public.lineorder` is an empty schema skeleton; the four dimension tables are full, ordinary, unsampled tables, without `verdict_vpart` or `verdict_vprob`. Preserve fact duplicates; the official schema explicitly omits a fact primary key.

Register the existing uniform fact sample through original Verdict `insertSampleInfo(param,n,N)`, with `SampleParam` ratio and per-row `verdict_vprob` both equal to actual retained `n/N`. Record that value, inverse `N/n`, generator integer-cutoff probability, requested probability, and DeepDB `n/p` separately. The generator probability must not silently replace Verdict's actual retained fraction. Full-query truth is excluded from registration and query rewriting; it is available only for statistical error evaluation after predictions.

The four unsampled dimension relations contribute probability one. Original `ApproxJoinedRelation` multiplies relation probabilities; `ApproxSingleRelation` omits inverse-probability factors for `nosample`. Original `JoinedRelation.partitionColumn()` chooses the first available partition column. Giving full dimensions random partitions could select a dimension partition (SSB4 starts with `dwdate`), so only the retained fact sample has `verdict_vpart`. This is a feasibility argument from source, **not** an executed SSB join/CI support result.

## Fixed original implementation and evidence

Reuse Verdict commit `b59209f626d278687ea0a801295b41064c7fecbb`, version 0.4.7, and the existing fixed JAR SHA256 `05dd0ec816c2c11ec143ff1aa3084a296a5156ec9fc11923b0068bdc3625b0a1`. Scientific Java source is unchanged. The existing isolated Temurin 8, PostgreSQL 11.5 and JDBC machinery is described in [FULL_VERDICT_PROTOCOL.md](FULL_VERDICT_PROTOCOL.md).

Primary source pointers at that commit:

- [ApproxSingleRelation.java](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/relation/ApproxSingleRelation.java): lines 197–217 and 319–349, sampled versus `nosample` factors.
- [ApproxJoinedRelation.java](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/relation/ApproxJoinedRelation.java): lines 125–152, 224–240 and 319–355, original join conditions and probability products.
- [JoinedRelation.java](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/relation/JoinedRelation.java): lines 524–532, partition choice.
- [VerdictMeta.java](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/VerdictMeta.java): lines 202–211, public existing-sample metadata API.
- [DbmsPostgreSQL.java](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/dbms/DbmsPostgreSQL.java): lines 71–75, original partition expression.

Local pristine sources are under `data/verdict/b/`. The new plan pins the existing 13 SQL file (SHA256 `37bf231b917f5c5995decb576566596acfc37722ed08e554252e68e91f839e32`) and schema (SHA256 `250abfbb28d74a8ded09110be6b16c2b472d6541691621b88e7a562ddb5a85dd`). Group widths are 0,0,0,2,2,2,3,3,3,3,2,3,3.

## Calls, raw errors and confidence intervals

Run the original 13 SQLs unchanged in each of `nobound` and `subsampling`. Retain raw rows, metadata, SQL identity, errors, timings, missing/extra groups, NULL and nonfinite values. No failed query is relabeled supported. Native subsampling uses 100 partitions and 95% confidence, kept distinct from DeepDB's 90% intervals.

For each of Q4.1–Q4.3 additionally execute the two separate original top-level SUM projections with the same FROM/WHERE/GROUP/ORDER. Keep all raw compound predictions. Externally subtract child points and label them `TWO_ORIGINAL_SUM_POINT_ADAPTER`. Do not construct a combined CI: the child covariance is unavailable (`UNSUPPORTED_NO_COVARIANCE_MODEL`). There are 19 physical calls per mode, 38 total. This candidate performs none of them.

## Reviewed implementation sequence

1. Add standard-library-only pure planner, exact rational scaling, strict multi-column result decoder, two-SUM adapter, and bounded pipe-record normalizer. First run failing tests, then implement. The CLI has no database/Java/SQLite execution command.
2. Read-only inspect the **already sealed SF2** formal-p benchmark, checking exact receipts, the benchmark→golden source relation, source/build identity, full contiguous checkpoint, original 1,798 truth groups, and current sample/dimension bytes, hashes and row widths. Do not regenerate or recreate removed full facts/SQLite files.
3. After root review and explicit go, use only PostgreSQL database `deepdb_verdict_ssb`; verify protected `deepdb_job` and `deepdb_verdict` identities before/after. Independently compute all 13 retained-sample SQL aggregates in a new bounded SQLite namespace. Record both integer sample SUM × generator `1/p` and SUM × actual `N/n` as separate exact-rational oracles. The expected Verdict no-bound prediction is **retained-sample integer SUM × N/n**, not the full-population answer; these two weights differ because retained n is random. Full truth is only a statistical comparator. Assert the physical rewrite uses the fact sample, full dimension tables, and fact partitions; test the original native grouped joins/CI and preserve any failures.
4. Measure SF2 PostgreSQL heap/index/catalog/WAL growth, JVM RSS, import/metadata/call times and relation counts before requesting a separate formal PG allowance. Keep direct COPY into the augmented fact sample as a candidate storage optimization; prove the imported 17 values and duplicate multiplicities first. Bind original auxiliary partition expression and `setseed`, actual registration fields, original-table row count zero, and full dimension counts. Hold explicit input locks during scientific calls; preserve rollback/error diagnostics.
5. Only after accepted final native SF500 population, successful SF2 engine gate and reviewed storage/resource allowance may a separate formal runner be implemented/used. Bind all raw descriptors, native outer final guard/lifecycle/stderr/time/peak, source/runtime, SQL, registration and every query receipt before/after. Use a new immutable namespace, atomic claim and per-call receipts; no cache based only on a TIME line. Publish point/error/CI95 counts and raw gaps, and a strict read-only verifier. This stage is currently absent.

## Existing SF2 inputs (future small gate)

The benchmark is `output/full/ssb/native_v2/benchmark_sf2_315fee3c562d6361/receipt.json`, SHA256 `b0c904816a21d38edfb83db1969bd796146670d5108aa0b32f4560a1921b25a7`. It binds golden receipt SHA256 `f9c30ce9d9a017ba8eeabffc7878a2a1e865056ab6ba8d2e19a079d6a7879146`, under `corrected_sf2_f31b7c6e2194db66`. N=11,997,996, n=39,587. The retained sample is 3,909,082 bytes, SHA256 `2ccbfc5d5c32f3c6bb792b292fbed38f33af4e05df0c7fbe306c0eaee325bc5a`; complete dimensions are reused from that golden namespace. This is the nearby benchmark probability 61,482,997,997,673,935/2^64, **not** formal SF500 requested 3333/1,000,000. All full fact temporary files were intentionally removed after sealed proof and must not be recreated.

## Resource boundary and current limitations

SSB data/output combined allowance remains 16 GiB including preserved old failed data, new samples/dimensions/HDF. PostgreSQL extra storage is separate and unapproved pending measured small-gate allowance; no additive large database is implicitly authorized by the 16 GiB file-tree budget. Formal full dimensions include 15M customers, 1M suppliers, 1.8M parts and 2,556 dates; their heap, PK indexes and WAL cannot be estimated reliably from raw bytes alone. Use streaming imports and bounded memory; do not load complete dimensions in Python. No PG startup/connect, Java compilation/execution, SQLite aggregate computation, native SSB inference or live growing sample access occurred in the candidate stage. Passing pure gates means candidate correctness only, not SSB engine support or completed baseline.

New candidate artifacts use `output/full/verdict_ssb/` and future staging uses `data/verdict_ssb/`, outside the SSB file tree. No copies of existing dimensions or samples are needed for candidate inspection. These namespaces do not grant additional database space.

## Executed candidate evidence

`code/full_verdict_ssb.py plan` emits 38 fixed original calls and keeps `formal_allowed=false`, `engine_calls_executed=0`. `inspect-sf2` is strictly a fixed-source, read-only check: it cannot choose a live SF500 path, connect to a database, execute a process, rebuild or compute SQL aggregates. Output creation is restricted to new files under `output/full/verdict_ssb/`; existing files are refused.

The executed SF2 source inspection reports `PASS_READ_ONLY_SOURCE_LINK_ONLY`: 115 physically hashed descriptors, exact benchmark/golden receipt pins, all 16 contiguous shards, 1,798 equal complete population truth groups, 39,587 physical 17-column sample rows and full 60,000/4,000/400,000/2,556 dimension rows. Sample plus dimension raw bytes total 45,012,393. This is a raw-input size, **not** a PostgreSQL storage estimate. The source inspection does not compute sample SQL or execute the original engine.

TDD logs retain the initial 24 failing missing-candidate tests, later failing lineage/adapter/formal-gate cases, and the final **42 passing pure tests**. A fixture originally aliased its checkpoint aggregates and independent truth; the diagnostic and intermediate failure remain recorded, and the fixture now owns an independent copy. The pure suite covers mismatched source/seed/probability/checkpoint/truth relations, required artifact-set omission, raw record fidelity and duplicate multiplicities, complete call accounting, multi-key rows, NULL/nonfinite results, error-before-TIME handling, and refusal to use partial failed child rows as adapter points. Full repository tests were not rerun: the task restricts execution to this independent pure candidate and forbids repeating frozen scientific work.

Commands (all project-local Python; no engine/DB command exists here):

```powershell
.venv/Scripts/python.exe -m pytest code/tests/test_full_verdict_ssb.py -q --tb=short --basetemp=output/full/verdict_ssb/test_runs/final
.venv/Scripts/python.exe code/full_verdict_ssb.py plan --output output/full/verdict_ssb/candidate_plan_v1.json
.venv/Scripts/python.exe code/full_verdict_ssb.py inspect-sf2 --output output/full/verdict_ssb/sf2_source_audit_v1.json
```

The two output commands deliberately fail if those immutable filenames already exist. Read the existing JSON for review; do not rerun them into the same names. Root source/model/replay acceptance, the original SF2 engine gate and protected-database/resource review remain mandatory before formal Verdict SSB work.
