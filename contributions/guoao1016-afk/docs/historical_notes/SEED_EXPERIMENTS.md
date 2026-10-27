# Repeated training-seed experiments

Original seed-1 runs are preserved in `output/results` and `output/models`.
New seed-2 and seed-3 runs use `output/seed_experiments/seed_S/samples_N/`.

Run from the repository root:

```powershell
.venv/Scripts/python.exe code/repeat_seeds.py --seed 2
.venv/Scripts/python.exe code/repeat_seeds.py --seed 3
```

Each command trains 10,000, 100,000 and 1,000,000 samples per model sequentially.
Each setting has a 900-second limit covering training, evaluation and replay verification.
Completed settings are skipped; incomplete settings require inspection before rerunning.

`maqp.py --seed` sets the global NumPy and Python RNGs; default 1 preserves the original configuration.
The full prepared HDF data, thread settings, Python hash seed (1), evaluation seed (1), model strategy,
queries and official ground-truth files remain fixed. The author's internal KMeans seed 17 and
dedicated RandomState(17) are retained. These experiments measure sensitivity to global training
randomness, including sampling, rather than varying every internal RNG.

Each run records its command, timestamps, phase durations, script and data-manifest hashes,
model hash, isolated logs, and a fresh replay of all 70 query predictions. Verification reads the
new model and results via `verify_results.py --output-root`; the default still checks the original output.

Seed-1 timings were collected in an earlier session on the same computer. Timing comparisons are
descriptive, not controlled throughput benchmarks. Three seeds permit an initial stability check,
not a statistical-significance or universal-monotonicity claim. Original query ground truths are reused.
