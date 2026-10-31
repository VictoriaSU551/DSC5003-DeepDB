"""Additive inference provenance audit; preserves frozen v2 results and models.

Checks original per-group bindings, including the actual RDC selection input.
Fresh reverse-order inference seals the complete current parser/inference source
and runtime dependencies. Existing training receipts are never retrospectively
represented as having sealed HDF contents that they did not record.
"""
import argparse
import csv
import gc
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np

from ensemble_compilation.spn_ensemble import read_ensemble
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import workload_files
from full_evaluation_v2 import helper_seal, infer, PROTOCOL
from full_factor_cache import model_aware_factor_cache
from full_paper_budget import same_ordered_components
from schemas.imdb.schema import gen_job_light_imdb_schema

AUDIT_PROTOCOL = 'current_dependency_reverse_replay_v1'


def pairwise_identity(training, root=ROOT):
    path = training.get('pairwise_rdc_path')
    return dict(enabled=bool(path), sha256=file_sha256(Path(root) / path) if path else None)


def require_alias_identity(training, source, root=ROOT):
    if not same_ordered_components(training, source):
        raise ValueError('alias ordered components or schema profile differ')
    if pairwise_identity(training, root) != pairwise_identity(source, root):
        raise ValueError('alias pairwise RDC content or selection mode differs')


def original_binding(training, query_path, truth_path, root=ROOT):
    return dict(protocol=PROTOCOL, model_sha256=training['model_sha256'],
                pairwise_sha256=pairwise_identity(training, root)['sha256'],
                query_sha256=file_sha256(query_path), truth_sha256=file_sha256(truth_path),
                helpers=helper_seal())


def require_original_binding(record, training, query_path, truth_path, root=ROOT):
    if record.get('binding') != binding_hash(original_binding(training, query_path, truth_path, root)):
        raise ValueError('original evaluation binding differs, including model/RDC/workload/helpers')


def dependency_seal():
    paths = []
    for folder in ['aqp_spn', 'rspn', 'ensemble_creation', 'ensemble_compilation', 'data_preparation', 'schemas']:
        paths.extend((ROOT / 'code' / folder).rglob('*.py'))
    paths.extend(ROOT / 'code' / name for name in [
        'evaluation/utils.py', 'full_evidence_audit.py', 'full_evaluation_v2.py',
        'full_evaluation.py', 'full_factor_cache.py', 'full_inventory.py',
        'full_common.py', 'full_paper_budget.py', 'full_training.py', 'full_prepare.py'])
    versions = {'python': platform.python_version()}
    for name in ['numpy', 'scipy', 'pandas', 'spflow', 'sqlparse', 'scikit-learn', 'networkx']:
        versions[name] = importlib.metadata.version(name)
    import spn
    spflow_root = Path(spn.__file__).resolve().parent
    return dict(sources={p.relative_to(ROOT).as_posix(): file_sha256(p) for p in sorted(set(paths))},
                spflow_sources={p.relative_to(spflow_root).as_posix(): file_sha256(p)
                                for p in sorted(spflow_root.rglob('*.py'))}, versions=versions)


def record(path):
    path = Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=file_sha256(path))


def evaluation_inputs(label, queries):
    training_path = FULL / 'results' / (label + '_training.json')
    result_path = FULL / 'results' / (label + '_evaluation_v2.json')
    training, result = load_json(training_path), load_json(result_path)
    if (training is None or training.get('status') != 'PASS' or result is None
            or result.get('status') != 'PASS' or result.get('protocol') != PROTOCOL
            or result.get('queries') != queries
            or result.get('model_sha256') != training.get('model_sha256')):
        raise ValueError('missing or inconsistent completed training/evaluation receipt')
    model = ROOT / training['model_path']
    if file_sha256(model) != training['model_sha256']:
        raise ValueError('model artifact hash differs')
    source_label = result.get('reused_from_label', label)
    source_path = FULL / 'results' / (source_label + '_training.json')
    source = load_json(source_path)
    if source is None:
        raise ValueError('missing source training receipt')
    require_alias_identity(training, source)
    inputs = [record(p) for p in [training_path, result_path, source_path, model]]
    pairwise = ROOT / training['pairwise_rdc_path'] if training.get('pairwise_rdc_path') else None
    if pairwise:
        inputs.append(record(pairwise))
    groups = []
    for group, query_path, truth_path in workload_files(queries != 70):
        summary = result['groups'][group]
        require_original_binding(summary, source, query_path, truth_path)
        prediction = FULL / 'evaluation_v2' / source_label / (group + '.csv')
        if summary['csv_sha256'] != file_sha256(prediction):
            raise ValueError('prediction CSV hash differs')
        inputs.extend(record(p) for p in [query_path, truth_path, prediction])
        groups.append((group, query_path, truth_path, prediction))
    return training, groups, dict(protocol=AUDIT_PROTOCOL, label=label, queries=queries,
                                  dependencies=dependency_seal(), inputs=inputs,
                                  pairwise=pairwise_identity(training))


def group_identity(binding, group, query, truth, prediction):
    count = len([line for line in query.read_text().splitlines() if line.strip()])
    return dict(binding=binding, group=group, queries=count, query_sha256=file_sha256(query),
                truth_sha256=file_sha256(truth), prediction_sha256=file_sha256(prediction))


def require_group_receipt(saved, identity):
    unsigned = {key: value for key, value in saved.items() if key != 'receipt_sha256'}
    if saved.get('receipt_sha256') != binding_hash(unsigned):
        raise ValueError('audit group receipt seal differs')
    if saved.get('status') != 'PASS' or any(saved.get(key) != value for key, value in identity.items()):
        raise ValueError('audit group identity, inputs or expected query count differs')
    if saved.get('order') != 'reverse; fresh ensemble; cold cache for every query':
        raise ValueError('audit group replay protocol differs')


def require_group_set(actual, expected):
    if not expected or len(actual) != len(expected) or len(set(actual)) != len(actual) or set(actual) != set(expected):
        raise ValueError('audit group set is incomplete, duplicated or unexpected')


def require_audit(result, binding, groups):
    identifier = binding_hash(binding)
    unsigned = {key: value for key, value in result.items() if key != 'audit_sha256'}
    if (result.get('audit_sha256') != binding_hash(unsigned)
            or result.get('status') != 'PASS_CURRENT_DEPENDENCIES'
            or result.get('binding') != identifier or result.get('configuration') != binding
            or result.get('label') != binding['label'] or result.get('queries') != binding['queries']):
        raise ValueError('current parser/inference audit seal or binding differs')
    directory = FULL / 'evidence_audit' / identifier
    expected = {(directory / (g + '.json')).relative_to(ROOT).as_posix(): (g, q, t, p)
                for g, q, t, p in groups}
    artifacts = result.get('artifacts', [])
    require_group_set([r['path'] for r in artifacts], list(expected))
    total = 0
    for artifact in artifacts:
        path = ROOT / artifact['path']
        if path.stat().st_size != artifact['bytes'] or file_sha256(path) != artifact['sha256']:
            raise ValueError('audit group artifact changed')
        identity = group_identity(identifier, *expected[artifact['path']])
        require_group_receipt(load_json(path), identity)
        total += identity['queries']
    if total != binding['queries']:
        raise ValueError('audit group total differs from expected workload')


def audit(label):
    result = load_json(FULL / 'results' / (label + '_evaluation_v2.json'))
    if result is None:
        raise ValueError('missing v2 evaluation')
    count = result['queries']
    training, groups, binding = evaluation_inputs(label, count)
    identifier = binding_hash(binding)
    directory = FULL / 'evidence_audit' / identifier
    final_path = directory / 'audit.json'
    existing = load_json(final_path, {})
    if existing.get('status') == 'PASS_CURRENT_DEPENDENCIES' and existing.get('binding') == identifier:
        require_audit(existing, binding, groups)
        atomic_json(FULL / 'results' / (label + '_dependency_audit.json'), existing)
        print('REUSED_CURRENT_DEPENDENCY_AUDIT', label, count, flush=True)
        return existing
    ensemble = read_ensemble(str(ROOT / training['model_path']), build_reverse_dict=True)
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    pairwise = ROOT / training['pairwise_rdc_path'] if training.get('pairwise_rdc_path') else None
    artifacts, completed = [], 0
    with model_aware_factor_cache():
        for group, query_path, truth_path, prediction_path in groups:
            path = directory / (group + '.json')
            saved = load_json(path, {})
            identity = group_identity(identifier, group, query_path, truth_path, prediction_path)
            if saved:
                require_group_receipt(saved, identity)
                artifacts.append(record(path)); completed += saved['queries']
                continue
            queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
            with prediction_path.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            with truth_path.open(newline='', encoding='utf-8') as stream:
                truths = list(csv.DictReader(stream))
            if (len(rows) != len(queries) or len(truths) != len(queries)
                    or [int(r['query_no']) for r in rows] != list(range(len(queries)))
                    or [r['query'] for r in rows] != queries
                    or [int(r['cardinality_true']) for r in rows] != [int(r['cardinality_true']) for r in truths]):
                raise ValueError('prediction query identity or truth alignment differs')
            max_relative = 0.
            for index in reversed(range(len(queries))):
                value, _ = infer(ensemble, queries[index], schema, pairwise)
                old = float(rows[index]['cardinality_predict'])
                np.testing.assert_allclose(value, old, rtol=1e-9, atol=1e-7)
                max_relative = max(max_relative, abs(value - old) / max(abs(old), 1e-300))
            saved = dict(identity, status='PASS', max_relative_prediction_difference=max_relative,
                         order='reverse; fresh ensemble; cold cache for every query')
            saved['receipt_sha256'] = binding_hash(saved)
            atomic_json(path, saved)
            artifacts.append(record(path)); completed += len(rows)
            print('CURRENT_DEPENDENCY_REPLAY_PASS', label, group, len(rows), flush=True)
    if completed != count:
        raise ValueError('audit query count differs')
    if evaluation_inputs(label, count)[2] != binding:
        raise ValueError('dependencies or inputs changed during replay')
    final = dict(status='PASS_CURRENT_DEPENDENCIES', binding=identifier, label=label, queries=count,
                 configuration=binding, artifacts=artifacts,
                 scope='Fresh inference correctness and current source/runtime provenance; no training replay or retrospective HDF training seal')
    final['audit_sha256'] = binding_hash(final)
    require_audit(final, binding, groups)
    atomic_json(final_path, final)
    atomic_json(FULL / 'results' / (label + '_dependency_audit.json'), final)
    return final


def require_current_audit(label, queries):
    path = FULL / 'results' / (label + '_dependency_audit.json')
    result = load_json(path)
    if result is None:
        raise ValueError('current parser/inference dependency audit is pending')
    _, groups, binding = evaluation_inputs(label, queries)
    require_audit(result, binding, groups)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', nargs='*')
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    labels = args.labels
    if args.all:
        labels = [load_json(p)['label'] for p in sorted((FULL / 'results').glob('*_evaluation_v2.json'))]
    if not labels:
        parser.error('provide labels or --all')
    for label in labels:
        audit(label)
        gc.collect()


if __name__ == '__main__':
    main()
