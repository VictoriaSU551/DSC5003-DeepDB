# Native v2 source and binary notice

The native_api.h, native_driver.c, native_callback.cpp, native_sampling.h,
native_dimensions.c and native_field_probe.cpp files are this project's own
adapters and audit harness. They call upstream constructors; they do not include
copies of the upstream generator implementation. Repository MIT terms apply to
these additions without granting any new license to the upstream generator.

The original34 files come from electrum/ssb-dbgen commit
219403ad7d1dd32ae1f97b5553abf92129fccd7f. No LICENSE/COPYING was found there.
They remain local, ignored, byte-pinned in ../ssb_dbgen/SOURCES.json, and can be
restored from its fixed ZIP. Do not publish the compatibility build copies.
This mirror is not proven to be the exact DeepDB author's generator release.

cygwin.lock.json contains only official package versions, URLs, lengths and
checksums from the recorded official metadata snapshot. It does not redistribute
the Cygwin/GCC runtime, change their upstream licenses, or run an installer.
The project-local official packages are subject to their own package terms.
The w64devkit compiler is the separately downloaded official v2.0.0 release;
docs/FULL_CPP_PROTOCOL.md records its fixed asset checksum and provenance.

Compatibility copies change exactly two priority capacities, the legacy priority
serializer, invalid RNG usage-counter writes and LLP64 range conversion order.
Original random value updates, scaling formulas and row constructors stay intact.
The direct callback and formatter are independently tested against the guarded
LP64 reference. These tests establish the stated field/query equivalences, not
an unpublished complete author raw snapshot SHA.
