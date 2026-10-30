# Current posthoc Flights parser binding

The original accepted 12-SQL reverse point/CI replay and its 54-file namespace
are frozen. This layer never retrains, regenerates or repeats those 24 accepted
calls. Frozen full_flights_replay.py SHA256:
e4c97c63c74e64edb6cb404f3c9e35f249bdf94653df2d4026769d8a7bab4762.
Original outer seal SHA256:
c6bd2cea5f75d8a7c57f8fc7228854babf405bd35d6822662b15558aa0b70ee6.

The original replay recorded parser-facing project source and other runtime
packages, but omitted the sqlparse distribution version and package Python source
set. This independent layer binds the **current posthoc** sqlparse version, loaded
module version/location, and its exact complete nonempty unique Python source
inventory. It binds its own module/tests/protocol and the frozen outer audit code.
Version mismatch, empty/duplicate inventory, added/deleted/changed Python files,
changed outer source, missing evidence or an incomplete output namespace fails.

Current observed sqlparse is0.3.1 with22 Python source files. The existing canonical
record binds version0.3.1 but has no sqlparse source collection. An existing sealed
SSB prepared dependency record includes the full Python source collection and can
be compared against current files. Such agreement proves current package equality
with those records. It does **not** prove that the original Flights replay used
these exact parser bytes: the historical Flights parser binding remains absent.
No historical claim is inferred from file timestamps or matching current results.

Permanent read-only entry:

```powershell
.\.venv\Scripts\python.exe -B code/full_flights_replay_audit.py verify
```

Python API: `full_flights_replay_audit.verify()`. It requires this new namespace's
verification.json and final_seal.json, validates every recorded file and current
parser/outer-source binding, then calls the frozen old audit() and compares its
complete saved result. A final current-binding check detects changes during the
audit. It cannot create receipts, launch a worker or infer with a model. Initial
capture is a separate explicit evidence-creation script, never a verify fallback.

The return preserves legacy verification/path/SHA, maximum_relative_difference,
successful_prior_calls, resource, model and actual_new_predictions fields. Its
new status is PASS_READ_ONLY_FLIGHTS_REPLAY_WITH_CURRENT_PARSER_BINDING, with
parser_binding_status=PASS_CURRENT_POSTHOC_PARSER_BINDING,
parser_bound_during_original_inference=false, the full parser binding, and new
posthoc_verification/posthoc_final_seal records. The old final_seal_sha256 keeps
its original meaning; it is not silently replaced by the posthoc seal hash.

New artifacts live only in output/full/flights-replay-audit/. Source snapshots,
focused RED/GREEN tamper tests and current peer comparisons are retained there.
After final sealing, audit/review must use stdout or a separate log directory.
This is an additional current dependency gate, not a new model experiment or a
claim of complete paper reproduction.
