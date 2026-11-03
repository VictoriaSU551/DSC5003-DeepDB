# Canonical-group LOCAL10M CI replay

This is the new replay consumer for the future canonical-group10M experiment, not an acceptance of the failed historical1M replay. No10M model, golden, query run or formal plan has executed at this code checkpoint. The current10M v2 provider lacks the new canonical fields, so this consumer rejects it.

`code/full_ssb_local_ci_group_replay.py` uses the unchanged scope-bound helper `full_ssb_scoped_replay.py` (SHA256 `f2514ac1e35cfea892096a7c9c338ab7c3aad6d905b4b35bfe6025f9ebca200c`) and frozen original numerical/guard helpers. The old replay entry and helper bytes are preserved.

The executor first checks the exact group adapter SHA256 `48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c` and imported path, then enters `canonical_group_order()` around the original `execute_query`. The adapter restores on exceptions; no inference is possible if its pin differs. The new output is `output/full/ssb/local_sf500_ci10m_group_replay`.

The complete future `verify_local_ci()` boundary must prove actual10M models and the accepted canonical1M parent. This thin consumer additionally requires:

- `evaluation_variant=CANONICAL_DECODED_GROUP_PROTOTYPE_V1` and the exact adapter SHA.
- `lineage.parent_canonical` naming `output/full/results/ssb_local_sf500_canonical_aqp_ci.json`, alongside the complete original formal and canonical reverse lineage.
- All three inference sources (this entry, frozen generic helper, group adapter) in the model plan's exact allowed auxiliary closure.
- Exact metadata types/values, including10M cap, actual fact9,996,946/date2556/customer10M/part1.8M/supplier1M rows, applied training-budget policy and the false exact10M-fact claim.
- Original author mismatch report bytes/SHA, all13 exact SQL/name identities, author/full flags false and1713 differing groups.

The frozen orchestration retains13 reverse queries,26 original evaluator calls,13 model loads, HASH173/seed74031/one thread and relative1e-9/absolute1e-5 comparison tolerances. It verifies complete query/seal sets, source snapshots, fresh-process command/environment/PID/two distinct logs and immutable PASS/TAINTED namespaces. Public `verify` is read-only; it never invokes the executor. Parent descriptor header checks in the thin layer are not substitutes for the real provider's full physical acceptance.

Fourteen pure tests passed, including exception restoration, pre-inference pin rejection, stale original-parent rejection, missing auxiliary source, and a provider policy flag altered while keeping the rest of its header plausible. The latter test was first observed failing and then fixed by checking every metadata field. Independent review found no Critical/Important. No actual provider validation, training, native inference or database operation occurred in those tests.
