"""Reload every SPN, recompute all 70 predictions, and independently summarize q-errors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=1000000)
    args = parser.parse_args()
    if os.environ.get('PYTHONHASHSEED') != '1':
        import subprocess
        env = dict(os.environ, PYTHONHASHSEED='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        subprocess.run([sys.executable, __file__, '--samples', str(args.samples)], env=env, check=True)
        return

    import numpy as np
    import pandas as pd
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.utils import parse_query
    from rspn.algorithms.validity.validity import is_valid
    from schemas.imdb.schema import gen_job_light_imdb_schema

    root = Path(__file__).resolve().parents[1]
    benchmark = root / 'code/benchmarks/job-light/sql'
    results = root / 'output/results'
    frame = pd.read_csv(results / ('job_light_%d.csv' % args.samples))
    truth = pd.read_csv(benchmark / 'job_light_true_cardinalities.csv')
    queries = (benchmark / 'job_light_queries.sql').read_text().splitlines()
    assert len(frame) == len(truth) == len(queries) == 70
    assert frame.query_no.tolist() == list(range(70))
    assert truth.query_no.tolist() == list(range(70))
    assert frame['query'].str.strip().tolist() == [q.strip() for q in queries]
    assert truth['query'].str.strip().tolist() == [q.strip() for q in queries]
    np.testing.assert_array_equal(frame.cardinality_true, truth.cardinality_true)
    values = frame[['cardinality_predict', 'cardinality_true', 'latency_ms']].values
    assert np.isfinite(values).all() and (values[:, :2] > 0).all() and (values[:, 2] >= 0).all()

    model = root / 'output/models' / ('ensemble_relationships_imdb-light_%d.pkl' % args.samples)
    ensemble = read_ensemble(str(model), build_reverse_dict=True)
    schema = gen_job_light_imdb_schema(str(root / 'data/imdb/{}.csv'))
    assert len(ensemble.spns) == 5
    for spn in ensemble.spns:
        validity = is_valid(spn.mspn, check_ids=True)
        assert validity[0] if isinstance(validity, tuple) else validity
        assert spn.full_join_size > 0 and spn.full_sample_size > 0
    covered = set().union(*(spn.relationship_set for spn in ensemble.spns))
    assert covered == set(schema.relationship_dictionary)
    replayed = []
    for sql in queries:
        _, _, prediction, _ = ensemble.cardinality(parse_query(sql.strip(), schema), max_variants=1,
                                                   merge_indicator_exp=True, exploit_overlapping=True,
                                                   return_factor_values=True)
        replayed.append(prediction)
    np.testing.assert_allclose(replayed, frame.cardinality_predict, rtol=1e-9, atol=1e-7)
    q = np.maximum(frame.cardinality_predict / frame.cardinality_true,
                   frame.cardinality_true / frame.cardinality_predict)
    report = dict(status='PASS', queries=70, spns=5, replayed_predictions=70,
                  samples_per_spn=args.samples,
                  q_error={str(p): float(np.percentile(q, p)) for p in [50, 90, 95, 99, 100]},
                  q_error_mean=float(q.mean()), latency_mean_ms=float(frame.latency_ms.mean()),
                  latency_median_ms=float(frame.latency_ms.median()),
                  model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                  scope='JOB-light official relationship baseline. Not full paper or optimized RDC reproduction.',
                  ground_truth='Official benchmark counts, checked query-by-query; see separate raw-data audit.')
    (results / ('verification_%d.json' % args.samples)).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
