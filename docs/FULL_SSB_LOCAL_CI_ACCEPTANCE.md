# Read-only 10M CI consumer acceptance

The successful local 10M CI reverse replay was launched from the project ROOT
with `code\full_ssb_local_ci_group_replay.py` as its relative worker entry.
`ScopedReplay` retains the spelling of the entry passed to its constructor.
Running the provider script directly therefore records a relative `command[2]`,
while importing the same provider gives its engine an absolute `__file__`.
The original complete verifier compares the recorded command with its generated
worker command exactly. That invocation difference made the table and status
consumers reject the already recorded worker receipt.

`code/full_ssb_local_ci_acceptance.py` is a consumer adapter for that one known
invocation. It requires the current working directory to be the project ROOT,
checks the exact physical provider and helper paths, and independently hashes
both files against these frozen pins:

| Source | SHA256 |
| --- | --- |
| `code/full_ssb_local_ci_group_replay.py` | `4b73cf6bed9bb001ec1bf289fadb6950bdd4f0c644e1837406eaef402b0a827c` |
| `code/full_ssb_scoped_replay.py` | `f2514ac1e35cfea892096a7c9c338ab7c3aad6d905b4b35bfe6025f9ebca200c` |

The adapter creates a fresh original provider engine, verifies its entry's
physical identity, sets only that instance's `ENTRY` to the fixed relative
`Path('code/full_ssb_local_ci_group_replay.py')`, then calls its full original
`verify()` exactly once. It does not choose arguments from a receipt. The
original source snapshot, golden and prior lineage, native and runtime checks,
model evidence, every seal and lifecycle, query comparison, worker environment,
remaining command arguments, process accounting, and physical logs are checked
by the unchanged verifier. Failures propagate; there is no fallback or replay.

Both `full_ssb_local_ci_tables.configuration()['verify']` and
`full_local_ssb_status.ci10m_stage()` use this adapter. The table configuration
also includes the adapter source in its derived-artifact binding. The adapter
does not edit frozen sources, mutate their module globals, rewrite receipts,
cache acceptance, load models, run inference, connect to a database, or launch a
worker. Author reproduction and full-paper completion remain false, and the
1,713 author truth differences remain explicit.

Pure regressions use the original `ScopedReplay.verify()` against complete
synthetic sealed replay files, with a test-only scientific source callback.
Each receipt fixture has its own synthetic ROOT containing byte-exact copies of
the pinned provider and helper sources. Temporary directories can be outside the
checkout, including pytest's default temporary location; no pytest configuration
forces temporary files into the project.
They reproduce the imported-entry rejection, check successful relative-entry
acceptance, reject changes to all command positions and other receipt fields,
check physical logs and query files, and test source pins, module identities,
working directory, error propagation, and the read-only operation guard.
The scientific source provider and actual replay are not executed by these
tests.

Run the scoped tests from ROOT:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider code/tests/test_full_ssb_local_ci_acceptance.py code/tests/test_full_local_ssb_status.py code/tests/test_full_ssb_local_tables.py code/tests/test_full_ssb_local_ci_group_replay.py
```

The initial red regression log is retained at
`output/tmp/root_ci_acceptance_red_20261103.log`; the first adapter green run is
`output/tmp/root_ci_acceptance_green_20261103.log`. These tests establish the
consumer invocation fix, not a fresh scientific replay or new scientific result.
The external-temp portability regression is retained at
`output/tmp/root_ci_acceptance_portability_red_20261103.log` and its corrected
run at `output/tmp/root_ci_acceptance_portability_green_20261103.log`.
