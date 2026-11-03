"""Canonical greedy-selection inference, separate from historical v1/v2.

No training. Preserves all models and earlier predictions. Complete source and
runtime seals, per-group self-seals, and fresh-process hash-seed reverse replays
are required for a current verified result.
"""
import argparse
import csv
import gc
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from ensemble_compilation.spn_ensemble import read_ensemble
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import numeric_summary, q_error, workload_files
from full_evaluation_v2 import infer
from full_evidence_audit import dependency_seal, record, require_group_set
from full_factor_cache import model_aware_factor_cache
from full_inventory import sql_tokens
from full_stable_selection import canonical_greedy_selection
from schemas.imdb.schema import gen_job_light_imdb_schema

PROTOCOL = 'physical_model_cold_cache_canonical_greedy_v3'


def seal(value):
    result = {k: v for k, v in value.items() if k != 'receipt_sha256'}
    result['receipt_sha256'] = binding_hash(result)
    return result


def require_sealed(value, identity):
    if value.get('receipt_sha256') != binding_hash({k: v for k, v in value.items() if k != 'receipt_sha256'}):
        raise ValueError('receipt self-seal differs')
    if any(value.get(k) != v for k, v in identity.items()):
        raise ValueError('receipt identity differs')


def inputs(label):
    training_path = FULL / 'results' / (label + '_training.json')
    training = load_json(training_path)
    if training is None or training.get('status') != 'PASS':
        raise ValueError('missing completed training receipt')
    model_path = ROOT / training['model_path']
    if file_sha256(model_path) != training['model_sha256']:
        raise ValueError('model artifact differs')
    profile = training.get('profile', 'joblight')
    include_scale = profile == 'public-scale'
    groups = list(workload_files(include_scale))
    pairwise = ROOT / training['pairwise_rdc_path'] if training.get('pairwise_rdc_path') else None
    dependencies = dependency_seal()
    dependencies['sources'].update({p.relative_to(ROOT).as_posix(): file_sha256(p)
                                    for p in [Path(__file__).resolve(), ROOT / 'code/full_stable_selection.py']})
    config = dict(protocol=PROTOCOL, label=label, profile=profile, dependencies=dependencies,
                  training_receipt=record(training_path), model=record(model_path),
                  rdc_selection_enabled=bool(pairwise), pairwise=record(pairwise) if pairwise else None,
                  workloads={g: dict(query=record(q), truth=record(t)) for g, q, t in groups},
                  max_variants=1, canonical_start_and_next_table_order='lexical',
                  rdc_sum='lexical attribute pairs and math.fsum; existing NaN values retained')
    return training, groups, config


def group_identity(config, group, query, truth):
    return dict(status='PASS', protocol=PROTOCOL, binding=binding_hash(config), group=group,
                queries=len([line for line in query.read_text().splitlines() if line.strip()]),
                query_sha256=file_sha256(query), truth_sha256=file_sha256(truth))


def checked_summary(label):
    training, groups, config = inputs(label)
    path = FULL / 'results' / (label + '_evaluation_v3.json')
    result = load_json(path)
    if result is None:
        raise ValueError('canonical v3 evaluation is pending')
    expected_count = sum(group_identity(config, g, q, t)['queries'] for g, q, t in groups)
    require_sealed(result, dict(status='PASS', protocol=PROTOCOL, label=label,
                                binding=binding_hash(config), queries=expected_count))
    if result.get('configuration') != config:
        raise ValueError('complete inference dependencies differ')
    require_group_set(list(result.get('groups', {})), [g for g, _, _ in groups])
    for group, query, truth in groups:
        saved = result['groups'][group]
        require_sealed(saved, group_identity(config, group, query, truth))
        csv_path = FULL / 'evaluation_v3' / label / (group + '.csv')
        if file_sha256(csv_path) != saved['csv_sha256']:
            raise ValueError('canonical prediction CSV differs')
    return result


def verify(label, queries, seeds=(1, 2, 3)):
    result = checked_summary(label)
    if result['queries'] != queries:
        raise ValueError('canonical workload count differs')
    summary_path = FULL / 'results' / (label + '_evaluation_v3.json')
    for seed in seeds:
        replay = load_json(FULL / 'results' / (label + '_replay_v3_seed%d.json' % seed), {})
        require_sealed(replay, dict(status='PASS', protocol=PROTOCOL, label=label,
                                    binding=result['binding'], queries=queries, hash_seed=str(seed),
                                    baseline_summary_sha256=file_sha256(summary_path),
                                    order='reverse within every group; fresh model; cold cache per query'))
        if replay.get('groups') != {g: s['queries'] for g, s in result['groups'].items()}:
            raise ValueError('hash-seed replay group identities or counts differ')
    return result


def evaluate(label, replay=False):
    training, groups, config = inputs(label)
    identifier = binding_hash(config)
    summary_path = FULL / 'results' / (label + '_evaluation_v3.json')
    if replay:
        baseline = checked_summary(label)
        baseline_hash = file_sha256(summary_path)
    else:
        baseline = None
        if summary_path.exists():
            existing = checked_summary(label)
            print('REUSED_CANONICAL_EVALUATION', label, existing['queries'], flush=True)
            return existing
    model = read_ensemble(str(ROOT / training['model_path']), build_reverse_dict=True)
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    pairwise = ROOT / training['pairwise_rdc_path'] if training.get('pairwise_rdc_path') else None
    summaries, total, maximum = {}, 0, 0.
    with canonical_greedy_selection(), model_aware_factor_cache():
        for group, query_path, truth_path in groups:
            identity = group_identity(config, group, query_path, truth_path)
            destination = FULL / 'evaluation_v3' / label / (group + '.csv')
            receipt_path = destination.with_suffix('.verification.json')
            saved = load_json(receipt_path, {})
            if not replay and saved:
                require_sealed(saved, identity)
                if file_sha256(destination) != saved['csv_sha256']:
                    raise ValueError('existing canonical group CSV changed')
                summaries[group] = saved; total += saved['queries']
                continue
            queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
            with truth_path.open(newline='', encoding='utf-8') as stream:
                truths = list(csv.DictReader(stream))
            if len(queries) != len(truths) or any(sql_tokens(q) != sql_tokens(t['query']) for q, t in zip(queries, truths)):
                raise ValueError('query and published truth alignment differs')
            old_rows = None
            if replay:
                with destination.open(newline='', encoding='utf-8') as stream:
                    old_rows = list(csv.DictReader(stream))
                if (len(old_rows) != len(queries) or [r['query'] for r in old_rows] != queries
                        or [int(r['query_no']) for r in old_rows] != list(range(len(queries)))
                        or [int(r['cardinality_true']) for r in old_rows] != [int(t['cardinality_true']) for t in truths]):
                    raise ValueError('canonical replay query identity differs')
            rows = {}
            for index in (reversed(range(len(queries))) if replay else range(len(queries))):
                predicted, latency = infer(model, queries[index], schema, pairwise)
                actual = int(truths[index]['cardinality_true'])
                if replay:
                    old = float(old_rows[index]['cardinality_predict'])
                    np.testing.assert_allclose(predicted, old, rtol=1e-9, atol=1e-7)
                    maximum = max(maximum, abs(predicted - old) / max(abs(old), 1e-300))
                else:
                    rows[index] = dict(query_no=index, query=queries[index], cardinality_true=actual,
                                       cardinality_predict=predicted, q_error=q_error(predicted, actual), latency_ms=latency)
            total += len(queries)
            if not replay:
                destination.parent.mkdir(parents=True, exist_ok=True)
                ordered = [rows[i] for i in range(len(queries))]
                temporary = destination.with_suffix('.csv.tmp')
                pd.DataFrame(ordered).to_csv(temporary, index=False)
                os.replace(str(temporary), str(destination))
                saved = seal(dict(identity, csv_sha256=file_sha256(destination),
                                  q_error=numeric_summary([r['q_error'] for r in ordered]),
                                  latency_mean_ms=float(np.mean([r['latency_ms'] for r in ordered])),
                                  generation_hash_seed=os.environ.get('PYTHONHASHSEED', 'UNSPECIFIED')))
                atomic_json(receipt_path, saved)
                summaries[group] = saved
            else:
                summaries[group] = len(queries)
            print('CANONICAL_REPLAY_PASS' if replay else 'CANONICAL_EVALUATED',
                  label, group, len(queries), os.environ.get('PYTHONHASHSEED'), flush=True)
    if inputs(label)[2] != config:
        raise ValueError('inference dependencies changed during run')
    if replay:
        if file_sha256(summary_path) != baseline_hash:
            raise ValueError('baseline summary changed during replay')
        result = seal(dict(status='PASS', protocol=PROTOCOL, label=label, binding=identifier,
                           queries=total, groups=summaries, hash_seed=os.environ.get('PYTHONHASHSEED', 'UNSPECIFIED'),
                           baseline_summary_sha256=baseline_hash, max_relative_prediction_difference=maximum,
                           order='reverse within every group; fresh model; cold cache per query'))
        atomic_json(FULL / 'results' / (label + '_replay_v3_seed%s.json' % os.environ.get('PYTHONHASHSEED')), result)
    else:
        result = seal(dict(status='PASS', protocol=PROTOCOL, label=label, binding=identifier,
                           queries=total, groups=summaries, model_sha256=training['model_sha256'], configuration=config,
                           variant='Canonical released greedy traversal; existing RDC NaNs retained; historical v1/v2 preserved'))
        atomic_json(summary_path, result)
        checked_summary(label)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--hash-seed', type=int, default=0)
    args = parser.parse_args()
    if os.environ.get('PYTHONHASHSEED') != str(args.hash_seed):
        env = dict(os.environ, PYTHONHASHSEED=str(args.hash_seed), OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__)), *sys.argv[1:]], env=env, cwd=str(ROOT)))
    labels = args.labels
    if args.all:
        labels = [load_json(p)['label'] for p in sorted((FULL / 'results').glob('*_evaluation_v2.json'))]
    if not labels:
        parser.error('provide labels or --all')
    for label in labels:
        evaluate(label, args.replay)
        gc.collect()


if __name__ == '__main__':
    main()
