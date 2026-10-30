# Official MSCN final audit

Run `.venv-mscn/Scripts/python.exe code/full_mscn_verify.py` after the official
100-epoch training and evaluation. This is the permanent entry point for the
independent checkpoint, official-loader prediction and batch-one timing audit.

If `verification_epoch100.json` already exists, the command verifies its five
sealed artifacts and audit-driver hash, then returns without loading the model,
repeating inference, or replacing timings. An incomplete or changed artifact
causes an error. A fresh completed run uses the same scientific audit as the
original, preserved `output/full/mscn/verify_final.py` driver; its path resolution
is adapted to the permanent `code` directory.

The verified local result uses the official 100K workload and matched sample
bitmaps, 90K training queries, 10K validation queries, 100 epochs and seed 1.
JOB-light q-error is median 3.5356627, p90 50.1622613, p95 120.5918257 and max
1102.0396096. The 70 rounded predictions are exactly reproduced by the original
loader. Mean batch-one forward time is 0.869307 ms; encoding plus forward is
1.730438 ms. These exclude disk reading, SQL parsing and unnormalization and must
not be compared with amortized batch-70 timings as the same measurement.

These are local results, not the paper's MSCN numbers. Generalization to the 683
public grouped queries uses a separate, explicitly rebuilt bitmap dataset and
training run; it does not silently combine unmatched official training bitmaps
with new evaluation bitmaps.
