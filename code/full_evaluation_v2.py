"""Model-aware, per-query cold-cache inference in a separate result namespace.

Preserves every v1 CSV. No model training is performed. Inference factor formulas
and the original SPN files remain unchanged; the cache adapter prevents reuse
of another physical model's factor. Replay reverses query order to check this.
"""
import argparse
import gc
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from ensemble_compilation.spn_ensemble import read_ensemble
from evaluation.utils import parse_query
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import numeric_summary, q_error, workload_files
from full_factor_cache import model_aware_factor_cache
from full_inventory import sql_tokens
from full_paper_budget import same_ordered_components
from schemas.imdb.schema import gen_job_light_imdb_schema

PROTOCOL = 'model_identity_factor_hash_and_cold_query_cache_v2'


def infer(ensemble, query, schema, pairwise):
    ensemble.cached_expecation_vals = {}
    parsed = parse_query(query if query.endswith(';') else query + ';', schema)
    started = time.perf_counter()
    _, _, predicted, _ = ensemble.cardinality(
        parsed, rdc_spn_selection=bool(pairwise), pairwise_rdc_path=str(pairwise) if pairwise else None,
        max_variants=1, merge_indicator_exp=True, exploit_overlapping=True, return_factor_values=True)
    return float(predicted), (time.perf_counter() - started) * 1000


def alias_for(training, include_scale):
    if not all('binding' in item for item in training['models']):
        return None
    for p in sorted((FULL / 'results').glob('*_evaluation_v2.json')):
        summary = load_json(p)
        if (summary.get('status') != 'PASS' or summary.get('protocol') != PROTOCOL
                or summary.get('reused_from_label') or summary.get('label') == training['label']
                or summary.get('queries') != (753 if include_scale else 70)):
            continue
        other = load_json(FULL / 'results' / (summary['label'] + '_training.json'))
        if other is None or not same_ordered_components(training, other):
            continue
        valid = True
        for group, query_path, truth_path in workload_files(include_scale):
            record = summary['groups'].get(group)
            csv = FULL / 'evaluation_v2' / summary['label'] / (group + '.csv')
            if (record is None or record['query_sha256'] != file_sha256(query_path)
                    or record['truth_sha256'] != file_sha256(truth_path)
                    or record['helpers'] != helper_seal() or not csv.is_file()
                    or file_sha256(csv) != record['csv_sha256']):
                valid = False
                break
        if valid:
            return summary
    return None


def helper_seal():
    return {name: file_sha256(ROOT / 'code' / name) for name in
            ['full_evaluation_v2.py', 'full_evaluation.py', 'full_factor_cache.py',
             'full_inventory.py', 'full_common.py', 'full_paper_budget.py']}


def evaluate(label, include_scale=True, replay=False):
    training = load_json(FULL / 'results' / (label + '_training.json'))
    if training is None:
        raise ValueError('missing training receipt')
    model_path = ROOT / training['model_path']
    if file_sha256(model_path) != training['model_sha256']:
        raise ValueError('trained model hash mismatch')
    output_path = FULL / 'results' / (label + '_evaluation_v2.json')
    if not replay:
        aliased = alias_for(training, include_scale)
        if aliased:
            result = dict(aliased, label=label, model_sha256=training['model_sha256'],
                          reused_from_label=aliased['label'],
                          reuse_proof='identical profile and ordered component bindings/artifact hashes; input and helper seals checked')
            atomic_json(output_path, result)
            print('V2_REUSED_IDENTICAL_MODEL', label, aliased['label'], flush=True)
            return result
    ensemble = read_ensemble(str(model_path), build_reverse_dict=True)
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    pairwise = ROOT / training['pairwise_rdc_path'] if training.get('pairwise_rdc_path') else None
    all_groups, total = {}, 0
    old_output = load_json(output_path, {})
    source_label = old_output.get('reused_from_label', label) if replay else label
    with model_aware_factor_cache():
        for group, query_path, truth_path in workload_files(include_scale):
            queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
            truth = pd.read_csv(truth_path)
            if len(queries) != len(truth) or any(sql_tokens(q) != sql_tokens(t) for q, t in zip(queries, truth['query'])):
                raise ValueError('workload SQL/truth alignment mismatch')
            binding = dict(protocol=PROTOCOL, model_sha256=training['model_sha256'],
                           pairwise_sha256=file_sha256(pairwise) if pairwise else None,
                           query_sha256=file_sha256(query_path), truth_sha256=file_sha256(truth_path),
                           helpers=helper_seal())
            destination = FULL / 'evaluation_v2' / source_label / (group + '.csv')
            receipt_path = destination.with_suffix('.verification.json')
            previous = load_json(receipt_path, {})
            if (not replay and destination.is_file() and previous.get('binding') == binding_hash(binding)
                    and previous.get('csv_sha256') == file_sha256(destination)):
                all_groups[group] = previous
                total += len(queries)
                continue
            results = {}
            order = reversed(range(len(queries))) if replay else range(len(queries))
            for i in order:
                prediction, latency = infer(ensemble, queries[i], schema, pairwise)
                actual = int(truth.iloc[i]['cardinality_true'])
                results[i] = dict(query_no=i, query=queries[i], cardinality_true=actual,
                                  cardinality_predict=prediction, q_error=q_error(prediction, actual), latency_ms=latency)
            rows = [results[i] for i in range(len(queries))]
            if replay:
                old = pd.read_csv(destination)
                if old['query'].tolist() != queries or old.cardinality_true.tolist() != truth.cardinality_true.tolist():
                    raise ValueError('replay SQL/truth differs')
                np.testing.assert_allclose(old.cardinality_predict, [r['cardinality_predict'] for r in rows], rtol=1e-9, atol=1e-7)
                print('V2_REVERSE_ORDER_REPLAY_PASS', label, group, len(rows), flush=True)
                total += len(rows)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_suffix('.csv.tmp')
            pd.DataFrame(rows).to_csv(temp, index=False)
            os.replace(str(temp), str(destination))
            summary = dict(status='PASS', protocol=PROTOCOL, binding=binding_hash(binding), queries=len(rows),
                           query_sha256=binding['query_sha256'], truth_sha256=binding['truth_sha256'],
                           helpers=binding['helpers'], csv_sha256=file_sha256(destination),
                           q_error=numeric_summary([r['q_error'] for r in rows]),
                           latency_mean_ms=float(np.mean([r['latency_ms'] for r in rows])))
            atomic_json(receipt_path, summary)
            all_groups[group] = summary
            total += len(rows)
            print('V2_EVALUATED', label, group, summary['q_error']['median'], flush=True)
    if replay:
        result = dict(status='PASS', label=label, protocol=PROTOCOL, queries=total,
                      order='reversed within each group, fresh model, empty cache per query',
                      source_label=source_label, model_sha256=training['model_sha256'])
        atomic_json(FULL / 'results' / (label + '_replay_v2.json'), result)
    else:
        result = dict(status='PASS', label=label, protocol=PROTOCOL, queries=total, groups=all_groups,
                      model_sha256=training['model_sha256'],
                      supersedes_policy='v1 CSV preserved; v1 IndicatorExpectation cache can mix physical RSPNs')
        atomic_json(output_path, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', nargs='+')
    parser.add_argument('--job-only', action='store_true')
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    for label in args.labels:
        evaluate(label, not args.job_only, args.replay)
        gc.collect()


if __name__ == '__main__':
    main()
