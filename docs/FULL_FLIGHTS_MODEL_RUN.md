# Flights model operational runner

Run from the Deep DB root in Windows PowerShell using the existing `.venv`:

```powershell
.venv/Scripts/python.exe code/full_flights_model_run.py --help
```

For an authorized, unfinished formal run, select only its unfinished stages:

```powershell
.venv/Scripts/python.exe code/full_flights_model_run.py prepare train evaluate
```

The runner calls the frozen `full_flights_model.py` with `source=flights-1b`, `paper`,
the formal memory approval flag, cap10000000 and seed1. Its use therefore requires
the parent task's explicit formal memory release. It fixes OMP/BLAS threads to1,
runs each stage in a separate process, and waits for exit before the next stage.
Every2 seconds it records the owned process tree's RSS and available physical memory.
It stops only its owned stage if RSS exceeds6GiB or free memory falls below1GiB,
retaining already sealed prepared/model artifacts. It refuses stages whose execution
receipt already records `PASS_STAGE_EXIT0`.

The completed formal run must be reused, not repeated. Its receipt is
`output/full/flights/model_formal_validation.json`; actual sample9997912, population1e9.
The original executed monitor at `output/full/flights/model_formal_supervisor.py` and
its logs/seals stay unchanged. This permanent copy differs only in ROOT discovery:
`parents[1]` for `code/`, versus `parents[3]` for the original output directory.

`--help`, ROOT/native memory self-checks and a byte comparison of the one permitted
replacement validated this permanent entry point. No preparation, learning or
evaluation stage was repeated for this relocation.
