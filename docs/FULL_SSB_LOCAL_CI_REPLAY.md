# LOCAL 10M CI replay and derived evidence

This is a separate experiment from the five 1M/table accuracy models. It applies
the paper's Figure 11 training-cap policy of 10M/table to the same generated local
population. The actual fact sample contains 9,996,946 rows. The five actual model
training counts must be lineorder 9,996,946, date 2,556, customer 10,000,000,
part 1,800,000 and supplier 1,000,000. A cap is not a claim of exactly ten million
fact training rows. The original generator/author discrepancy remains 1,713 of
2,059 truth groups; all author/full-paper completion flags remain false.

The model provider is `full_ssb_local_ci.verify_local_ci()`, with distinct scope
`LOCAL_SSB_10M_CI`. It must verify accepted 1M formal and reverse parent lineages,
the independent scientific cap-adapter golden experiment, reused complete HDF
inputs and native integer sample moments, five new model checkpoints, and all
formal/publication/owned-supervisor receipts. The two replay modules must have
their exact hashes in the reviewed model plan's auxiliary-source allowlist.
An accepted 1M result, author-gated result, missing parent or partial checkpoint
cannot substitute for this provider.

The new shared `full_ssb_scoped_replay` controls process and publication accounting;
`full_ssb_local_ci_replay` supplies the immutable scope and provider contract. The
frozen 1M replay remains byte-for-byte unchanged. Numerical evaluation, CI
comparison, coverage and Python raw/prepared-reader guards reuse the previously
frozen helpers. No training, sampler or inference formula is rewritten here.

After actual model acceptance, the explicit `replay` command starts one new
process with hash seed 173, Python/NumPy seed 74031 and all four thread limits 1.
It loads the saved ensemble independently for each of the 13 original SQLs, in
reverse order, making 26 original point/CI evaluator calls. Each query's exact
SQL and comparison are sealed. Current complete input/model/runtime snapshots
must match before and after. Tolerance is relative 1e-9 and absolute 1e-5.
The entry, shared helper and scope configuration hashes are part of the binding.
The parent receipt binds that binding, report, namespace, reported worker PID,
exact command/environment, finite wall time and two distinct physical logs.
Failed namespaces remain TAINTED; automatic reruns are refused.

```powershell
.venv/Scripts/python.exe -B code/full_ssb_local_ci_replay.py replay
.venv/Scripts/python.exe -B code/full_ssb_local_ci_replay.py verify
.venv/Scripts/python.exe -B code/full_ssb_local_ci_tables.py
```

`verify` never executes a model, launches a worker, writes or repairs artifacts.
The new CI provider uses the independently checked native Windows/registry
context from birth. The old 1M provider's default CPython 3.8 platform probe can
invoke `cmd/ver`; a separately named current posthoc adapter is available for
strict process-forbidden acceptance of those unchanged historical verifiers:

```powershell
.venv/Scripts/python.exe -B code/full_ssb_local_readonly_audit.py formal --output output/full/ssb/local_readonly_audits/formal_v1.json
.venv/Scripts/python.exe -B code/full_ssb_local_readonly_audit.py reverse --output output/full/ssb/local_readonly_audits/reverse_v1.json
```

These commands fail if the necessary actual publications do not exist. They do
not establish a process-free historical default or an operating-system access
trace. Python process/database/network/write/model-unpickle APIs are forbidden
during delegation, with complete source/run file size/mtime checks before and
after; the independently checked current platform substitution is explicit.
New output files are exclusive and confined to a separate audit directory.

Derived 1M and 10M figures use separate manifests, pointers and public export
bundles. Both show the author-population discrepancy on each PNG and in each
CSV. All group rows, missing/extra/zero truth, invalid intervals and reference
CI exclusions remain available. The reference joins the retained fact sample
to full dimensions; intervals use one realized sample, not repeated-sampling
coverage calibration. A failed author-population gate is never promoted by a
successful local replay or table export.
