# LOCAL SSB canonical-continuation derived tables

`code/full_ssb_local_continuation_tables.py` is a separate derived consumer for
`LOCAL_SSB_SF500_CANONICAL_CONTINUATION` and protocol
`ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1`. It does not
certify the earlier TAINTED canonical ROOT transaction or the failed historical
reverse replay. The earlier accepted forward is adopted; the continuation must
already have accepted its own fresh reverse. No preparation, model fitting,
moments calculation, or predictions occur in this consumer.

Before any derived write it checks literal source hashes, then calls the frozen
continuation's public `verify_canonical()` exactly once. That verifier performs
one complete original formal physical verification. Missing or invalid evidence
is an error; the consumer has no execution fallback. It requires the complete
original parent proof and its unique artifact subset in the accepted union,
current continuation/adapter sources, nonempty publication descriptors, exact
old-forward/new-reverse paths, read-only flags, and explicit adoption accounting
(forward: one load/26 prior calls; reverse: 13 loads/26 new calls). The result
alias remains `output/full/results/ssb_local_sf500_canonical_aqp_ci.json`, with
the new scope, protocol, and transaction directory required inside it.

The derived binding records the publication, plan, lifecycle and both phase
descriptors, the complete parent-proof digest, and complete artifact-list digest.
It does not copy the original large closure into every figure manifest or
perform a second physical scan. The frozen generic consumer reads the accepted
published result once, verifies its bytes/SHA, checks all 13 exact SQL identities,
and retains all 2,059 truth groups. Frozen summarization and rendering functions
are reused without numerical changes. Integer sample moments still determine
the uniform reference using exact N/n. Missing groups, invalid predictions,
extras, zero truths, nonfinite or missing intervals, and count<10 exclusions
remain explicit; conditional coverage is not calibration.

Both PNGs and every CSV retain the LOCAL boundary: N=3,000,028,242, retained
fact n=9,996,946, and 1,713 author truth groups differing. The five saved models
have a 1M/table training cap (date has 2,556 rows); this is not the Figure 11
10M training experiment. The model retains its original n/p normalizer; the
reference uses exact N. Author and full-paper completion remain false.

Only after ROOT accepts the real continuation, ROOT may run:

```powershell
.venv/Scripts/python.exe -B code/full_ssb_local_continuation_tables.py
```

The five derived files are `query_summary.csv`, `all_groups.csv`,
`training_tables.csv`, `ssb_relative_error.png`, and `ssb_ci_half_width.png` in
`output/full/figures/aqp_ssb_local_continuation_<binding16>/`, with a manifest and
`output/full/results/ssb_local_continuation_tables_latest.json` pointer. An
existing output must pass the frozen exact five-artifact cache check. Reuse
still performs one fresh public verification. Existing scientific results and
legacy derived namespaces are unchanged. No real continuation verification or
export was performed while implementing this consumer.

Dedicated pure/mock checks (synthetic fixture outputs only):

```powershell
.venv/Scripts/python.exe -B -m pytest code/tests/test_full_ssb_local_continuation_tables.py -q -p no:cacheprovider --basetemp output/tmp/ct_review
```
