# SSB native v2: compatibility correction and direct fact callback

2026-10-31 design and implementation plan. The original SF500 run is permanently
MISMATCH. Its sources, plans, four thousand committed shards, sample, dimensions,
and supervisor FAIL are evidence and must not be replaced or reclassified.

The parent task selected the direct native callback approach. Work continues in
this directory and branch without commits or global installation. New full-scale
execution is gated on the corrected small experiments, independent review, a new
sealed plan, and resource checks; existing formal-model author gates stay closed.

## Diagnosed failures

* Actual rows 3,000,028,334 versus author 3,000,028,242: DATE and ORDER both have
  table id 4. Stock `-T a` advances each ORDER stream 2,556 positions while making
  dates; stock `-T l` does not. Seed43's first2,556 line counts sum10,161, while
  the 2,556 after750M sum10,253. Their exact difference92 explains the row gap.
* Stock Windows LLP64 writes the15-character `4-NOT SPECIFIED` plus NUL into an
  11-byte lineorder priority buffer. Original-header native `sizeof/offsetof`
  probe: long4, pointer8, priority offset37, ship_priority48, quantity52;
  quantity37 becomes0. LP64 layout oracle has offsets53/64/72 and preserves37.
  This is a generation defect, independent of the consumer and SQL evaluator.
* A new SF0.001 stock probe emits6,005 `-T l` facts: all1,257 priority4 facts have
  quantity0, and the other priorities have no zero quantities. Existing SF1/SF2
  tests verified the same flawed Windows stock output, not Linux equivalence.
* The actual official Cygwin LP64 compiler/original-header probe confirmed the
  layout. Actual unguarded LP64 stock `-T l` generated6,005 facts: numeric fields
  equal the buffer-fixed Windows version, while its legacy priority text is
  truncated to11 bytes by ship_priority clearing. Explicit output serialization
  must preserve these11 bytes while keeping safe16-byte storage.
* Unguarded LP64 stock `-T a` crashes in first PART generation. `P_CAT_SD=97` and
  gen_city's98 exceed MAX_STREAM47. UnifInt locally maps these to0, but dss_random
  subsequently increments Seed[97/98].usage out of bounds. An independent native
  instrumentation trace confirmed the PART/category path. The parent approved
  guarding only invalid usage writes; do not count them toward Seed0, change the
  invalid-to0 value stream, or add new effective RNG streams.
* A fourth independently isolated LLP64 defect is integer range overflow in
  `UnifInt(0,2147483647)`: `nHigh-nLow+1` is computed in signed32-bit long before
  conversion to double. It changes customer/supplier address mapping, although
  the RNG states are identical. The Windows compatibility copy converts each
  bound before subtraction and addition. The LP64 reference retains the original
  expression, providing an independent address oracle. No Seed value or usage
  changes. Actual tiny LP64/Windows facts and all four dimensions now match by
  all fields after line-ending normalization only.

Evidence: `output/full/ssb/diagnosis/native_layout/red_receipt.json`, the two
`stock_sf0p001_*` directories, and the retained original SF500 MISMATCH receipt.
All8,000 committed retained-file hashes, all4,000 integer aggregate merges,
sample/dimension actual hashes, bytes, and rows were independently checked.
The source SQL and author truth are byte-identical to DeepDB upstream655ada13.

## Approaches

The rejected full-CSV approach formats, writes, hashes, reads, and parses all3B
facts and took hours. A named pipe removes disk but retains most formatting and
parsing cost. The selected callback preserves stock RNG and row constructors,
aggregates numeric fields immediately, and formats sampled facts only. A bounded
corrected stock CSV remains the small gate oracle.

Only an independent build copy may change: enlarge the two SSBM priority arrays
from11 to16 bytes, matching the pinned distribution's longest priority plus NUL.
`O_OPRIO_LEN` is8 under SSBM and is unsuitable for this correction. All34 source
files in the original vendor directory retain their pinned bytes. Flat printer
serialization explicitly limits priority to its observed LP64 legacy11 bytes.
The independent copy additionally guards dss_random's usage increment for indices
outside0..47, preserving the original UnifInt call and all valid-stream state.
These four compatibility differences are separately hashed and documented. No RNG,
scaling formula, date rule, retail-price formula, or generated values are edited.

## Components and interfaces

New `code/full_ssb_native_v2.py` owns source-copy verification, compatibility
patching, native builds, diagnosis receipts, small gates, plans, and checkpoints.
New `code/tests/test_full_ssb_native_v2.py` owns pure and bounded native tests.
Self-written callback/driver sources go under `code/vendor/ssb_native_v2/`.
All new generated/build evidence is under `output/full/ssb/native_v2/`; new formal
sample is separate from the failed `data/ssb/sf500_paper/` sample. Dimension reuse
requires physical hash and source/sequence equality, not an assumed name match.

The native driver uses the stock initialization and `gen_tbl`/`mk_order`, replacing
only `tdefs[LINE].loader[0]`. The original Seed array is captured before DATE
initialization and restored before LINE generation. Only nonnegative original
skip counts are used; no negative NthElement undo. This must match
stock `-T l` bytes at beginning, end, and resumed boundaries. Each command covers
a contiguous bounded order range. The callback performs all13 integer aggregates
and stable-key Bernoulli selection, then formats selected rows with a self-written
17-field formatter checked against the stock printer. No original order/line
values are modified, and no long-lived static stock FILE handle is reused.
Selected raw rows are normalized only at their terminal pipe and line ending.
No complete fact CSV is written or retained.

One persistent process loads dimensions once. A fresh recovery process starts
from original seeds and skips to the first uncommitted order, binding source,
compiler, compatibility patch, dimensions, seed, probability, scale, and shards.
Committed shard truths and sample byte prefixes are immutable and SHA verified;
an interrupted sample tail may be truncated to its previously committed offset.
Changing any bound input refuses recovery. Atomic namespace ownership and
persistent RUNNING/TAINTED states prevent silently accepting failed namespaces.

## Tasks and tests

- [x] Task1: TDD source-copy patch guard and native layout RED→GREEN. Assert exact
  pinned input SHA, exactly two SSBM replacements, priority capacity16, quantity37
  unchanged after the15-character copy, and original files unmodified. Refuse
  missing/repeated/context-changed patch locations. Independently pin the legacy
  priority printer difference and the out-of-range usage-write guard.
- [x] Task2: corrected stock `-T l` and independent LP64 reference. Prefer a
  project-local official Cygwin x86_64 compiler/runtime if a bounded pinned package
  set is viable; Cygwin officially uses LP64. No Docker/WSL/global installer.
  Record actual long/pointer sizes; a ctypes layout oracle alone is not an actual
  LP64 generator run. The compiler is now available: gcc14.4.0,26 official packages,
  66,164,325 compressed bytes,420,128,067 regular bytes. The usable generator
  reference requires the approved usage memory-safety guard; unguarded LP64 stock
  is a failed diagnostic, never a claimed working full oracle.
- [x] Task3: native callback TDD. On a tiny retained-all input, normalized callback
  rows equal corrected stock `-T l` byte for byte and integer numeric fields equal
  independent RNG/price constraints. All dimensions compare by bytes; the13 SQL
  sums compare against independent SQLite. Stock and callback are distinct paths.
- [x] Task4: new corrected SF1/SF2 gates, not reruns of obsolete buggy gates. Test
  uninterrupted versus process restart, sample tail truncation, seed/source/dim
  change rejection, exact order boundaries, SQL groups and integer aggregates.
  Keep gate artifacts within the revised combined16GiB SSB limit; cleanup only newly
  generated temporary full CSV/SQLite after recording independent evidence.
  Check active RNG seeds and all17 fields near306M/613M/749M order resume points.
  Classify unused comment-stream overflow explicitly rather than changing RNG.
- [x] Task5: benchmark SF2 direct callback and retain-all stock. Seal measured time,
  RAM, bytes, estimated SF500 time and space, old evidence preservation, and a new
  full-scale plan. Require>=4GiB available RAM and>=8GiB free disk, no competing
  training, and parent review before launching a new full traversal.
- [ ] Task6: only the new native v2 namespace may execute. Final author PASS still
  requires exact3,000,028,242 facts and all2,059 integer truth groups. Any remaining
  sequence/version difference is MISMATCH with evidence; never substitute own truth
  into the author's gate. Formal model preparation is a separate later decision.

Tests run with `.venv/Scripts/python.exe -B -m pytest -q code/tests/test_full_ssb_native_v2.py`.
Actual tiny LP64/Windows and callback17-field/SQLite13-query gates passed.
New corrected SF1 has6,001,215 facts and1,563 nonempty truth groups; SF2 has
11,997,996 facts and1,798 groups. Every fact field equals actual LP64 unprimed
stock output; all four dimensions and48 valid Seed trajectories agree; all13
SQLite integer aggregate results equal the callback. SF1 took499.90s, SF2
1082.85s including independent SQLite. Retain-all callback plus Python byte
comparison took37.26/79.48s, and LP64 stock printing29.80/62.73s. These are
validation costs, not the sparsely sampled formal stream throughput. Full gate
peak RAM was not instrumented; the separate formal-sampling benchmark records
the native process Windows peak working set.

Both original full gate CSVs and SQLite databases were new temporary oracles:
their hashes, row counts, source bindings, exact SQL output and logs were saved
before cleanup. Their removal does not touch any original failed data. The
retained gate receipts are `corrected_sf1_6c34ba3b7ba3246b/receipt.json` and
`corrected_sf2_f31b7c6e2194db66/receipt.json` under native_v2 output.

High-index stock skip probes at1,306,000,001,613,000,001,749,999,937 each cover64
orders against an independent LP64 modular-stride reference. Actual field-reading
streams agree. Unread comment streams12/25 can overflow LLP64 skip multiplication;
unread HVAR39 is not skipped by sd_line. Their different states remain recorded;
there is no claim that all48 high-index Seed structs are equal. A separate audit
harness compiles the exact production C view and `emit_sample` formatter for the
same high ranges, including order keys above2**31; it skips dimensions/aggregates
only for this formatter audit. Production C++ and the SF2 build remain unchanged.

SF1 used retain-all p=1 before the output sampler's integer refinement. SF2 uses
the final exact integer sampler build. Both retain all facts. Formal sampling
uses the public schema's literal0.003333=3333/1,000,000, with explicit integer
cutoff=floor(3333*2**64/1,000,000), accepting H<cutoff. The effective probability
is exactly cutoff/2**64; ALL handles p=1 separately. Floating probabilities are
rejected by the final native interface. Independent compiled probes cover0/1,
cutoff-1/cutoff, uint64 maximum and the complete stablehash calculation.

New controller `code/full_ssb_native_v2_stream.py` checks a complete committed
file inventory, each sample byte segment/row count,13 integer aggregate merge,
all bound sources/runtime/input descriptors and exact order ranges before any
tail truncation. It refuses seed/source/cutoff changes, partial-line offsets and
TAINTED namespaces. It uses an OS execution lock released on process death.
An unlink refusal for an already committed temporary sample is recorded as a
retained non-scientific residual and contributes to the space budget; it does
not invalidate the verified sample prefix. Atomic JSON replacement retries only
Win5/32 for at most1s, acknowledging a remaining short read/close window.

The final CLI is `code/full_ssb_native_v2_formal.py`. `freeze-gates` may complete
bounded gates and benchmark; it cannot start SF500. `verify-readiness` is strictly
read-only. After independent review, the parent launches exactly once:

```powershell
$env:PYTHONPATH='code'
.venv/Scripts/python.exe -B code/full_ssb_native_v2_formal.py run --review-plan-sha256 REVIEWED_SHA --formal-memory-approved
```

An interrupted RUNNING namespace uses the same command plus `--resume`; existing
TAINTED or MISMATCH namespaces stay closed. The CLI checks actual available RAM,
disk, competing training and the combined budget. It generates corrected four
dimensions, compares every field and valid Seed trajectory to the guarded LP64
reference, preserves the old failed dimensions, and streams4,000 original-order
chunks without full fact CSV materialization. Only the new data directory
`data/ssb/sf500_native_v2/` is written.

`output/full/results/ssb_native_v2.json` has schema `ssb_native_v2_final_v1`,
pure64-hex source_id, `canonical_truth` records(query_no,group,value), flat exact
`artifacts`, descriptor-valued plan/checkpoint/raw_sample, and explicit sampling
integers. Shards are0..3999, next_shard=4000 at completion. The seal filename is
`ssb_native_v2_seal.json`. Public `verify_final()`/`verify-final` strictly read
existing evidence and require the outer FINAL_PASS guard; provisional report
bytes or a restored TAINTED namespace cannot become consumable. PASS requires
exact3,000,028,242 facts and all2,059 author integer result groups. It means
"matches author row count and all13 query truths", not raw snapshot identity.
Formal models have not started.

The final formal-probability SF2 benchmark processed11,997,996 facts in6.1893s,
retaining39,587 sample rows. Windows recorded native peak working set13,012,992
bytes at SF2. All13 integer aggregates still equal the independent SQLite golden.
Linear SF500 stream extrapolation is1,547s (25.8min); a deliberately broad
18–62min range includes uncertain dimension generation/load and contention.
This is a forecast, not an executed SF500 result. SF500 dimension-vector memory
is larger than SF2; actual RAM/disk probes remain mandatory at launch.

The project-local real restart gate processed6,005 facts, independently selected
3,024 rows at cutoff2**63, and produced byte-identical uninterrupted/restarted
samples and13 identical integer aggregate sets. Two committed shards were reused,
only the remaining two executed after restart, and the uncommitted partial tail
was discarded after prefix validation. Receipt:
`recovery_e4f52f6ca9be67c2/receipt.json`; benchmark receipt:
`benchmark_sf2_315fee3c562d6361/receipt.json`.

The fixed official Cygwin26-package lock is committed as text; fresh setup reads
its package versions/URLs/bytes/SHA512 directly and never downloads rolling
setup metadata. An unavailable old package is a source gap, not permission to
silently upgrade. Original mirror sources restore using
`code/full_ssb_paper.py setup`; original34 byte checks are mandatory. The separate
portable w64devkit2.0.0 asset checksum is in `SOURCES.json` here and
`docs/FULL_CPP_PROTOCOL.md`; Windows `tar` can list/extract this fixed SFX archive
into the project `.runtime` directory. Native v2 never installs a global toolchain.

Actual MinGW executable direct PE imports are only KERNEL32.dll and msvcrt.dll;
their System32 bytes and Windows platform identity are read-only bound in the
materialized stream plan. libgcc/libstdc++ are statically linked. This describes
direct imports and does not claim to seal every transitive Windows DLL.
Public `verify_final()` additionally returns the outer final_guard descriptor
with report/review SHA bindings, for the model bridge's before/after snapshots.

The revised16GiB combined SSB budget was explicitly approved by the parent task:
old failed data and output already occupy about4.20GiB and must remain preserved;
corrected dimensions, sample and later prepared HDF cannot fit the old10GiB
ceiling. The previous frozen10GiB plan and its failed results remain unchanged.

Official LP64 reference: [Cygwin FAQ6.4](https://cygwin.com/faq.html#faq.programming.64bitporting).
Pinned mirror source provenance remains in `code/vendor/ssb_dbgen/SOURCES.json`;
it is not proven to be the DeepDB author's exact generator version.
