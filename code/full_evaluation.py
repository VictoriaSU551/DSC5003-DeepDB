"""Evaluate sealed full-paper models on the actual published workloads."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from ensemble_compilation.spn_ensemble import read_ensemble
from evaluation.utils import parse_query
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_inventory import sql_tokens
from schemas.imdb.schema import gen_job_light_imdb_schema


def q_error(predicted, actual):
    if actual <= 0 or predicted < 0 or not math.isfinite(predicted):
        raise ValueError('q-error requires positive truth and finite nonnegative estimate')
    return math.inf if predicted == 0 else max(predicted / actual, actual / predicted)


def numeric_summary(values):
    array = np.asarray(values, dtype=float)
    def finite_json(value):
        return float(value) if math.isfinite(value) else 'inf'
    # Quantiles use order statistics with interpolation, explicitly propagating
    # an infinite endpoint instead of producing JSON NaN through inf-inf.
    ordered = np.sort(array)
    def quantile(p):
        index = (len(ordered) - 1) * p
        low, high = int(math.floor(index)), int(math.ceil(index))
        if not np.isfinite(ordered[high]):
            return 'inf'
        return float(ordered[low] + (index - low) * (ordered[high] - ordered[low]))
    return dict(median=quantile(.5), p90=quantile(.9), p95=quantile(.95), p99=quantile(.99),
                max=finite_json(array.max()), mean=finite_json(array.mean()),
                infinite_count=int((~np.isfinite(array)).sum()))


def workload_files(include_scale=True):
    benchmark = ROOT / 'code/benchmarks/job-light'
    pairs = [('job_light', benchmark / 'sql/job_light_queries.sql',
              benchmark / 'sql/job_light_true_cardinalities.csv')]
    if include_scale:
        for tables in range(3, 7):
            for predicates in range(1, 6):
                stem = '%d_%d_SPN' % (tables, predicates)
                pairs.append((stem, benchmark / 'scale_sql' / (stem + '.sql'),
                              benchmark / 'scale_sql' / (stem + '.csv')))
    return pairs


def evaluate(label, include_scale=True, replay=False):
    training = load_json(FULL / 'results' / (label + '_training.json'))
    if training is None:
        raise ValueError('Missing training receipt for ' + label)
    model = ROOT / training['model_path']
    if file_sha256(model) != training['model_sha256']:
        raise ValueError('Model hash differs from training receipt')
    ensemble = read_ensemble(str(model), build_reverse_dict=True)
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    pairwise = ROOT / training['pairwise_rdc_path'] if training['pairwise_rdc_path'] else None
    summaries = {}
    total = 0
    for group, query_path, truth_path in workload_files(include_scale):
        queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
        truth = pd.read_csv(truth_path)
        assert len(queries) == len(truth)
        for query, row in zip(queries, truth.to_dict('records')):
            assert sql_tokens(query) == sql_tokens(row['query']), (group, row)
        destination = FULL / 'results' / label / (group + '.csv')
        receipt_path = destination.with_suffix('.verification.json')
        binding = dict(model_sha256=training['model_sha256'], query_sha256=file_sha256(query_path),
                       truth_sha256=file_sha256(truth_path), driver_sha256=file_sha256(__file__),
                       pairwise_sha256=file_sha256(pairwise) if pairwise else None,
                       max_variants=1, merge_indicator_exp=True, exploit_overlapping=True)
        previous = load_json(receipt_path, {})
        if (not replay and destination.exists() and previous.get('binding') == binding_hash(binding)
                and previous.get('csv_sha256') == file_sha256(destination)):
            print('Reused verified predictions', label, group, flush=True)
            summaries[group] = previous
            total += len(queries)
            continue
        rows = []
        for index, (query, row) in enumerate(zip(queries, truth.to_dict('records'))):
            canonical = query if query.endswith(';') else query + ';'
            parsed = parse_query(canonical, schema)
            started = time.perf_counter()
            _, _, prediction, _ = ensemble.cardinality(parsed, rdc_spn_selection=bool(pairwise),
                pairwise_rdc_path=str(pairwise) if pairwise else None,
                max_variants=1, merge_indicator_exp=True, exploit_overlapping=True,
                return_factor_values=True)
            elapsed = (time.perf_counter() - started) * 1000
            prediction = float(prediction)
            actual = int(row['cardinality_true'])
            error = q_error(prediction, actual)
            rows.append(dict(query_no=index, query=query, cardinality_true=actual,
                             cardinality_predict=prediction, q_error=error, latency_ms=elapsed))
        if replay:
            old = pd.read_csv(destination)
            assert old['query'].tolist() == [r['query'] for r in rows]
            np.testing.assert_allclose(old.cardinality_predict, [r['cardinality_predict'] for r in rows],
                                       rtol=1e-9, atol=1e-7)
            print('Replayed predictions match', group, len(rows), flush=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.csv.tmp')
        pd.DataFrame(rows).to_csv(temporary, index=False)
        os.replace(str(temporary), str(destination))
        summary = dict(status='PASS', binding=binding_hash(binding), queries=len(rows),
                       csv_sha256=file_sha256(destination), q_error=numeric_summary([r['q_error'] for r in rows]),
                       latency_mean_ms=float(np.mean([r['latency_ms'] for r in rows])),
                       missing_semicolon_normalized=sum(not q.endswith(';') for q in queries),
                       ground_truth='Published truth, independently rechecked only where separately recorded.')
        atomic_json(receipt_path, summary)
        summaries[group] = summary
        total += len(rows)
        print('Evaluated', label, group, summary['q_error']['median'], flush=True)
    if not replay:
        atomic_json(FULL / 'results' / (label + '_evaluation.json'), dict(status='PASS', label=label,
                    queries=total, workload=('70 JOB-light + 683 public grouped queries; not the unidentified 200'
                                            if include_scale else '70 JOB-light'),
                    groups=summaries, model_sha256=training['model_sha256']))
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('--job-only', action='store_true')
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    evaluate(args.label, not args.job_only, args.replay)


if __name__ == '__main__':
    main()
