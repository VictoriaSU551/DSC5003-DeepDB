# Dependency and recovery audit

The original v2 evaluator and training drivers are frozen so earlier receipts
remain inspectable. Independent review found two recovery weaknesses: v2 reuse
did not check every inference dependency or the pairwise-RDC identity; original
component/RDC bindings did not include the actual prepared HDF contents.

`code/full_evidence_audit.py` reconstructs each original group binding, checks
the RDC file and enabled selection mode for aliases, and performs a fresh
reverse-order replay. Its new receipts bind the parser, inference and schema
sources, installed SPFlow Python sources, package versions, model, workload,
truth and prediction files. Original predictions and timings are preserved.
This first audit exposed a real further failure in the released greedy selector:
the same B2 model, RDC file and query produce 36,099,666.480442 or
11,973,471.088227 depending on Python's hash seed. Both paths select the same
two SPNs but enter the second SPN through a different table. The four-seed
diagnosis is retained under `output/full/audit_diagnostics/`. An audit failure
remains visible and cannot be relabeled as a successful replay.

`full_stable_selection.py` provides a separate canonical traversal variant.
Three selector loops use sorted table names, and RDC columns/pairs use sorted
order with `math.fsum`. Model order, candidate vectors, original factor formulas
and existing RDC NaNs remain unchanged. The source contains two symmetric NaN
column pairs: `title.kind_id` with `movie_keyword.keyword_id`, and with
`movie_companies.company_type_id`. A later NaN repair would require another
explicit model-selection/training variant. `max_variants=1` remains fixed.

`full_evaluation_v3_run.py --all` generates seed0 predictions in a new v3
directory and replays every query in reverse order in fresh seed1/2/3 processes.
It records actual process hash fingerprints. `full_canonical_acceptance.py`
also requires seed0 provenance for every baseline group, matches all four hash
fingerprints against fresh reference interpreters, and checks current
baseline/replay files against their worker contexts. Only this final gate feeds
current status and paper tables. Historical v1/v2 outputs are preserved.

`code/full_prepared_seal.py --profile all` verifies the six raw files against
their download manifest and seals all full/sample HDFs, metadata, title fanouts
and unmatched-row files. The public-scale preparation manifest must also match
its original binding and actual artifacts. A new current seal does not prove
that a legacy driver recorded these hashes at its original training time.

For future training or recovery, use `code/full_training_guard.py`. Its planning
command seals actual input contents and runtime versions. `--execute` requires
the displayed `--plan-sha256` and checks inputs before and after training.
Components, RDC checkpoints and selection receipts use a new namespace under
`output/full/guarded_training/<profile>/<plan-sha256>`. They cannot accidentally
reuse legacy components whose HDF provenance was omitted. The final training
receipt links this input plan and its profile-specific selection receipt.
Legacy results remain historical, read-only artifacts; adding the audit does
not require retraining them.
If guarded training fails, observes changed inputs, or is interrupted, its
namespace is persistently tainted and cannot automatically reuse components.
The public training receipt is released only after the final input check.
