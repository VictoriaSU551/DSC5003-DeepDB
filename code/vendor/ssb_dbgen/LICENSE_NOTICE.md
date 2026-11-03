# Fixed-source notice

Source: electrum/ssb-dbgen commit 219403ad7d1dd32ae1f97b5553abf92129fccd7f.
The original author HTTPS archive failed normal TLS certificate verification;
verification was not disabled. This mirror is not established as the exact
DeepDB authors' generator version.

The pinned mirror tree has no LICENSE or COPYING file. Its executable reports
Copyright Transaction Processing Performance Council 1994 - 2000.
All original headers, README, TPCH_README and history documents are retained
byte-for-byte; SOURCES.json records their digests. No MIT or other license grant
is inferred for this vendor code. This notice does not replace upstream terms.

full_consumer.cpp is a separately added output consumer. full_chunk_driver.c is
a separate continuation adapter calling unmodified upstream date generation,
sd_order/sd_line and gen_tbl. It is accepted only after comparing every byte of
the complete SF1 fact stream to original -T a output. No RNG, distributions,
row-construction code, logarithm formula, or upstream source file is patched.
Compiler flags and provenance are recorded. The two historic part scaling
formulas remain intact.

full_dimension_driver.c is another separately added output adapter. It calls
the unchanged original part generation followed by supplier, customer and date
in the same sequence as stock -T a, without generating facts. This preserves
the upstream city/phone shared-stream behavior. Its four SF2 outputs and the
chunk adapter's complete SF2 fact byte stream were compared against unmodified
stock -T a via a Windows named pipe; all byte comparisons passed. This does not
establish that the mirror is the exact DeepDB authors' version.

The original 34 files remain local and should not be publicly committed without
an established license. The project can distribute its three own adapter files,
SOURCES.json and this notice; full_ssb_paper.py setup restores the fixed ZIP only
after archive and per-file original-byte verification, without overwriting
modified original sources.
