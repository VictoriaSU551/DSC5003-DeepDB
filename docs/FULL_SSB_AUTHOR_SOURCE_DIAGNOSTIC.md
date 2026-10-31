# Read-only customer-source diagnostic after native SF500 mismatch

This note does not change or reopen any generator, model, readiness, final FAIL or TAINTED evidence. No executable, database query, new dimension/fact generation or 3B-row traversal was run for this investigation.

## Newly obtainable primary source

On this attempt, normal verified TLS successfully downloaded the [SSB authors' current dbgen.zip](https://www.cs.umb.edu/~poneil/dbgen.zip), linked by their [publication list](https://cs.umb.edu/~poneil/publist.html). The 102,995-byte ZIP is retained only locally at `data/downloads/ssb_customer_diagnostic/author_dbgen.zip`, SHA256 `284118b10f066fd0d5b8e4e77b150d0b6176510f84a2f54f93c3a439ac312bc3`. No `--insecure` or TLS bypass was used. The archive was inspected in memory; no original vendor file was replaced or extracted over.

There are 34 regular archive members. Thirty match the existing pinned electrum mirror byte for byte. The four differences are: `config.h` (the mirror adds a MAC platform branch), `makefile` (original `MACHINE=LINUX`, mirror `MAC`), `varsub.c` (mirror adds `#include "config.h"`) and original-only `debug.txt`. In particular, the complete `build.c`, `rnd.c`, `rnd.h`, `dss.h`, `driver.c`, `bm_utils.c` and distributions bytes match. The per-member audit is `output/full/results/ssb_author_zip_source_audit_20261031.json`, SHA256 `48d64f0a095185eda321e398b5a6e48b06b5827460f57735f9b1498b0f2da679`.

This establishes agreement with the **currently published SSB-author scientific source**. It does not establish which historical generator/build/flags/parameters or physical customer data were used for DeepDB's distributed 500GB truth pickle. The frozen mirror provenance and all previous mismatch records remain unchanged.

## Narrowing the customer branch from code

The completed report `output/full/results/ssb_native_v2.json` retains MISMATCH. Queries 0–5 do not use customer attributes or `lo_custkey`; their agreement cannot validate the author customer FK stream. Full query truth agreement remains the mandatory author-population gate.

The current published source has:

- `build.c:103–111`: customer nation/region use `C_NTRG_SD` only; nation index maps directly through the distributions. `rnd.h:59` gives stream 27 initial value 1489529863 and one call per customer row. This nation/region stream does not depend on part/supplier generation order or the invalid city stream 98. Therefore a discrepancy in Q3.1 and Q4.1, which do not use `c_city`, cannot be explained solely by city or address serialization.
- `build.c:229–236`, `dss.h:371,422`, `rnd.h:72`: fact customer FK uses stream 40, initial 851767375, range `1..tdefs[CUST].base*scale`, and the retained TPC-H mortality loop excludes keys divisible by three (normally moving such a key up by one, with clamping at the upper endpoint). `driver.c:229` gives customer base 30,000, hence SF500 upper bound 15,000,000. This range and the stream-40 one-call order skip stay below LLP64 signed-long overflow limits.
- `build.c:599–614`: customer and supplier city suffixes use invalid stream 98, which original `UnifInt` redirects to stream zero. Its table-order dependency is a separate matter from nation/region stream 27. Previously measured full-dimension/LP64 checks remain evidence of local compatibility, not proof of the DeepDB historical customer snapshot.

The SSB [Revision 3 specification](https://www.cs.umb.edu/~poneil/StarSchemaB.PDF), section 2.5, specifies SF×30,000 customers; the TPC-H appendix separately describes the one-third customer mortality rule. The current SSB source retains that rule. A possible historical change to FK range, stream initialization, mortality mapping or customer input remains a **hypothesis**, not an identified fix. No parameters should be selected merely to fit the published query answers and then reported as a recovered author snapshot.

The defensible current boundary is local source/LP64/SQL compatibility plus an explicitly failed author-truth gate. The independently authorized local-population model must retain that different scope. More precise historical provenance or independently testable customer/FK evidence is needed before any further corrected author-scale traversal is justified.
