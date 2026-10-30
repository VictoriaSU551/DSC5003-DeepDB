# Original VerdictDB SIGMOD18: existing Flights sample execution

Status: completed original-engine **existing uniform-sample** run, with explicit raw compound-SUM error and missing groups. This is a separate baseline scope, not the paper's full original-table sampling experiment, author snapshot, stratified sampler or end-to-end performance result. No existing IMDb/Flights/SSB scientific artifact or `.venv` dependency was changed. Writes were confined to the new `deepdb_verdict` database and Verdict-owned directories.

## Source and executable contract

The original 0.4.7 source is commit `b59209f626d278687ea0a801295b41064c7fecbb`. The preserved ZIP SHA256 is `72b068ce7dc501e065229b2b43eee19bd3777127e973db436256fd9770ae23c9`. All 400 source files, including Apache-2.0 and third-party notices, remain byte-identical under `data/verdict/b/`.

An unchanged root/core build was actually attempted twice and failed resolving 16 unavailable private Cloudera JDBC **test-scope** dependencies. The independent PostgreSQL build tree `data/verdict/p/` removes those 16 test dependencies from `core/pom.xml`; all other source files, including every original Java implementation, match the fixed ZIP. `postgres-test-dependencies.patch` and `output/full/verdict/postgres_build_patch.json` record this build-only change. The original source is untouched. HTTPS Maven Central was used through isolated `data/verdict/settings.xml`, with no global settings/PATH/registry changes.

The adapted build succeeded in 205.235 s, observed Java peak RSS 523,776,000 bytes. The executable fat JAR is `data/verdict/p/jars/verdict-spark-lib-0.4.7.jar` (62,240,731 bytes; SHA256 `05dd0ec816c2c11ec143ff1aa3084a296a5156ec9fc11923b0068bdc3625b0a1`). Execution needs that JAR, the two bridge classes in `data/verdict/bridge_classes/`, the fixed local JDK and PostgreSQL runtime; Maven's download cache and build target are unnecessary. `runtime_dependency_provenance.json` records the fat JAR's 109 embedded Maven coordinate records; `historical_build_dependency_resolution.json` records historical resolved dependencies without making their cache paths mandatory.

Official runtimes and publisher checksums are retained in `data/downloads/verdict_runtime/`:

- [Temurin 8u462-b08 Windows x64 JDK](https://github.com/adoptium/temurin8-binaries/releases/tag/jdk8u462-b08): ZIP SHA256 `c6c2d8e6c2cbf0b4ddb707e6edb9a00d8a7b04e9ed6dda7e62d43dc4d83d342c`, verified against the official release checksum.
- [Apache Maven 3.9.11](https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/): ZIP SHA256 `0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb`, verified against the retained [official SHA512](https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.zip.sha512).
- Existing fixed PostgreSQL 11.5 Windows archive SHA256 `89ec61731231b88b748ae0f923ec02568ede2c008c79f901666ea67de6565f4c`; its selected `bin/lib/share` members are verified against the actual local runtime. No PostgreSQL installation files were modified.

## Completed small gate

A complete 5,000-row synthetic original table was populated with NULLs, strict-boundary cases and groups. The official `CREATE 20% UNIFORM SAMPLE` command produced 1,050 retained rows. Original PostgreSQL logic assigned actual probability **1,050/5,000 = 0.21**, rather than nominal 0.20. That exact sample, including random, probability and partition columns, was copied and registered through the unchanged `VerdictMeta.insertSampleInfo(param,n,N)` for an empty schema-only original.

`golden_gate.json` records actual sample-membership equality via historical `EXCEPT ALL`, empty imported original (0 rows), n/N, all 100 partition indices and **24 successful original engine calls**, each with nonempty complete result groups. The two paths match independent retained-sample arithmetic for COUNT/SUM/AVG, grouping (including NULL), SUM of a product, strict boundaries and the adapter below. COUNT follows the original rounded weighted-count rule on both sides. The retained sample and physical ROW/OK output are sealed; equality of two failed/empty paths is never accepted.

The original configuration value is `verdict.error_bound.method=nobound`. The misleading `no_error_bound` setting caused NPEs; those failed raw logs remain under `output/full/verdict/attempts/`. Metadata catalog bootstrap and refresh use only original public APIs. No original Java scientific source was patched.

The original raw `SUM(x)-SUM(y)` returned an **unscaled sample sum difference** (-7,674.4 versus scaled -36,544.7619). It remains labeled `INCORRECT_RAW_UNSCALED_COMPOUND_SUM`. A minimal projection adapter makes two independent original top-level SUM calls and subtracts their point estimates externally. It is labeled separately, counts two physical calls and never combines child confidence intervals without a covariance model.

## Completed formal Flights run

Only the already materialized uniform sample from our sealed 1B population was imported: **n=9,997,912**, **N=1,000,000,000**, actual probability **0.009997912**. The CSV is 582,074,363 bytes, SHA256 `9d9c78d0e03b403472e34da73af9f3dccde070036c3ed02c649ce4ee880d6f45`. The 1B original table was never materialized in this database; `public.flights` is an empty 12-column schema skeleton. N enters only as prior overall size metadata. The information budget is schema, retained sample, actual n and population N. Query truths are first read after import and metadata registration, solely for evaluation.

The retained sample was COPY-imported in 52.859 s. The original probability/100-partition expression was applied in 36.078 s; import-to-augmented wall time was 102.016 s. The temporary raw COPY table was released after the completed augmented stage. Stage receipts bind actual input bytes, n/N and the exact import function, allowing completed trustworthy stages to resume. `deepdb_job` row-operation counters and relfilenodes matched before/after; these accounting checks are not per-row content hashes.

All 12 fixed SQL queries were executed through the original engine with both `nobound` and native `subsampling`, **14 successful physical calls per mode** (12 raw plus two top-level SUM children for F5.2). The execution plan, raw physical cell outputs, original result columns, per-call time and Java process logs remain sealed. Java envelopes were 45.266 s and 44.547 s, with observed peak RSS 156,504,064 and 155,930,624 bytes. Per-call timings include original rewriting, physical SQL and fetching; they exclude JVM startup/import/aux-column preparation and are neither isolated server SQL time nor paper end-to-end latency. F5.2 adapter wall time sums both original calls; original raw F5.2 remains separately reported.

`flights_evaluation.json` compares each group against our own complete exact 1B streaming truth (`ground_truth.json`, SHA256 `f1cd8591539f8fb04bc0c6582a7cab9d660beecdc2843bcc27dbbcda43e34cb2`). It preserves the union of truth/prediction keys and all zero-truth/error fields. There are **331 unique truth groups, 329 raw predicted groups, 2 missing groups (one each in F3.2 and F5.2), 0 extra groups, 0 engine execution errors**. The F5.2 adapter produces 52 of 53 truth groups, preserving its missing group. Raw F5.2 has the known incorrect unscaled compound-SUM label and must not be ranked as a valid unadapted result.

Native confidence is the original **95%** setting with 100 subsampling partitions. It is not DeepDB's central 90% interval. Original point/error-bound cells and derived bounds are retained, including invalid/unavailable statuses. Adapter CI is `UNSUPPORTED_NO_COVARIANCE_MODEL`; both children's native outputs remain inspectable, with no fabricated combined interval or cross-method CI calibration.

Formal SQL completed before the suggestion to hold an explicit freeze lock arrived; no lock coverage is claimed or reconstructed. The separately executed post-run **READ ONLY REPEATABLE READ** transaction records sample count/probability/100 partition counts, empty original, metadata n/N, relation oid/relfilenode and insert/update/delete counters. It corroborates historical accounting at that snapshot. It does not certify today's database values or provide a per-row content seal. Future default audit does not connect to any database.

## Resource and cleanup evidence

Limits were Java observed RSS at most 1 GiB, total new filesystem + isolated DB + positive WAL growth at most 8 GiB, and bounded SQL statement timeouts (small gate 30 s; formal 120 s). Formal observed new-disk peak was 2,835,384,341 bytes (about 2.64 GiB). The bounded runner samples current and kernel peak working set; no global dependency installation occurred.

Automatic tool policy rejected the verified native PowerShell cleanup action, with stated reason only `blocked by policy`. No deletion occurred and no alternate deletion mechanism was used. The unused `data/verdict/m2/` (246,355,449 bytes) and `data/verdict/p/core/target/` (3,570,910 bytes) remain ignored and explicitly excluded from the mandatory execution/seal closure. `cleanup.json` records those paths, sizes and the rejection. Required JAR/classes/source/patch and all failed scientific evidence are preserved. This cleanup limitation does not invalidate source, inputs, runtime or scientific outputs.

## Strict read-only acceptance

Run from the Deep DB directory:

```powershell
.venv/Scripts/python.exe code/full_verdict_audit.py
```

Or import `code/full_verdict_audit.py` and call `verify()`; the stable successful status is **`PASS_READ_ONLY_ORIGINAL_VERDICT_SAMPLE_ONLY_WITH_GAPS`**. Returned fields include `evaluation_artifact={path,bytes,sha256}`, `verification`, `final_seal`, `historical_physical_calls`, and recomputed `group_coverage`. The API is standard-library-only and has no database client, subprocess, network, repair or write operation. It never samples, trains, connects, reruns SQL, registers metadata or implicitly fills missing receipts. `--help` is also read-only.

The audit requires the fixed 12 names and SQL SHA, indexed/aligned truth, 331 unique truth groups, exact 14+14 successful nonempty physical calls, 24 complete golden calls and the sample-only contract. It independently recalculates outer-group arithmetic, missing/extra counts, raw F5.2 and its two-call adapter, and native confidence records. Empty/subset/duplicate lists remain invalid even if self-resealed. Artifact lists require fixed status, canonical unique physically contained paths and the exact mandatory closure. The closure derives all 400 pristine and 400 build source members, 446 JDK files, 96 Maven files and all 1,436 selected PostgreSQL runtime members from fixed archives, then compares actual bytes. It includes full source/licenses, fixed runtime archives, actual JAR/classes, original plans/results/logs, failed raw evidence and isolated audit/code/tests/docs. Unused Maven cache/targets are excluded.

The external seal writer `code/full_verdict_seal.py --write` only creates outer cleanup/verification/final-seal receipts for existing evidence. It must follow the focused tests; it cannot perform science or DB operations. Default invocation is the same read-only acceptance API. `verification.json` and `final_seal.json` bind the final complete set; only root's independent table/status consumers read these scientific outputs.

Validation: initial 5 expected failures demonstrated the empty/subset/duplicate manifest and checkpoint weaknesses before the fix. The focused suite then passed **28/28** tests, including mutation rejection for query/truth scope, missing groups, physical calls, adapter call count, confidence level and golden metadata. Tests are `code/tests/test_full_verdict.py`, `test_full_verdict_flights.py` and `test_full_verdict_audit.py`. No full-project suite, CPP compilation, model retraining or scientific SQL rerun was used for this closure.
