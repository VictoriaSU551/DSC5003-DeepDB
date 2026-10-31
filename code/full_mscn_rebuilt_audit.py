"""Parent audit of the sealed completed rebuilt-MSCN reference run.

Pins the delivered final inventory, checks all 165 artifacts, and independently
aligns/recalculates the 753 saved predictions. No model loading or inference.
New experimental runs need their own reference audit, not replacement pins.
"""
import csv
import hashlib
from pathlib import Path

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import numeric_summary, q_error, workload_files
from full_inventory import sql_tokens

DIRECTORY = FULL / 'mscn/rebuilt_seed1/results'
FINAL_SEAL_SHA256 = '9940f798082156164fe6b1474026f60343b692115f0590e5220c0dcce4d70114'
EXPECTED_COUNTS = {'job_light': 70}
for _tables, _counts in [(3, [97, 73, 49, 37, 14]), (4, [70, 69, 56, 43, 22]),
                          (5, [13, 23, 17, 21, 10]), (6, [12, 23, 13, 11, 10])]:
    EXPECTED_COUNTS.update({'%d_%d_SPN' % (_tables, p): n for p, n in enumerate(_counts, 1)})


def require_inventory(records, count):
    paths = [record['path'] for record in records]
    if len(paths) != count or len(set(paths)) != count:
        raise ValueError('final artifact inventory is incomplete or duplicated')


def check_records(records, base):
    base = Path(base).resolve()
    for record in records:
        path = (base / record['path']).resolve()
        if (base not in path.parents or not path.is_file() or path.stat().st_size != record['bytes']
                or file_sha256(path) != record['sha256']):
            raise ValueError('sealed rebuilt MSCN artifact differs: ' + record['path'])


def check_helper_sources(records):
    snapshots = {r['path']: r for r in records}
    for name in ['full_common.py', 'full_evaluation.py', 'full_inventory.py']:
        expected = snapshots.get('source_snapshot/code/' + name)
        current = ROOT / 'code' / name
        if (expected is None or current.stat().st_size != expected['bytes']
                or file_sha256(current) != expected['sha256']):
            raise ValueError('current audit helper source differs: ' + name)


def require_workload_grid(pairs):
    pairs = list(pairs)
    names = [item[0] for item in pairs]
    benchmark = ROOT / 'code/benchmarks/job-light'
    if len(names) != 21 or len(set(names)) != 21 or set(names) != set(EXPECTED_COUNTS):
        raise ValueError('complete unique 21-group workload grid required')
    for name, sql, truth in pairs:
        if name == 'job_light':
            expected = [benchmark / 'sql/job_light_queries.sql', benchmark / 'sql/job_light_true_cardinalities.csv']
        else:
            expected = [benchmark / 'scale_sql' / (name + '.sql'), benchmark / 'scale_sql' / (name + '.csv')]
        if [Path(sql).resolve(), Path(truth).resolve()] != [p.resolve() for p in expected]:
            raise ValueError('workload grid SQL/truth path differs')
    return pairs


def require_query_totals(groups):
    if (set(groups) != set(EXPECTED_COUNTS)
            or any(groups[name]['queries'] != count for name, count in EXPECTED_COUNTS.items())
            or sum(g['queries'] for g in groups.values()) != 753):
        raise ValueError('actual per-group query totals differ')
    return sum(g['queries'] for g in groups.values())


def verify(write=False):
    final_path = DIRECTORY / 'final_seal.json'
    if file_sha256(final_path) != FINAL_SEAL_SHA256:
        raise ValueError('delivered rebuilt MSCN final seal changed')
    final = load_json(final_path)
    if (final['status'] != 'PASS' or final['completed_epochs'] != 100 or final['checkpoint_count'] != 100
            or final['published_queries'] != 753 or final['local_truth_rescored_queries'] != 683):
        raise ValueError('completed rebuilt MSCN contract differs')
    require_inventory(final['output_artifacts'], 165)
    check_records(final['output_artifacts'], DIRECTORY)
    check_helper_sources(final['output_artifacts'])
    check_records(final['protected_original_root_and_cpp_artifacts'], ROOT)
    check_records([final['rebuilt_data_manifest']], ROOT)
    data_manifest = load_json(ROOT / final['rebuilt_data_manifest']['path'])
    check_records(data_manifest['artifacts'], ROOT / 'data/mscn/rebuilt')
    check_records(data_manifest['binding']['queries'], ROOT)
    for name, expected in [('full_mscn_rebuilt.py', final['frozen_training_source_sha256']),
                           ('full_mscn_local_truth.py', final['permanent_local_entry_sha256'])]:
        if file_sha256(ROOT / 'code' / name) != expected:
            raise ValueError('frozen rebuilt MSCN source differs')
    verification_path = DIRECTORY / 'final_verification.json'
    if file_sha256(verification_path) != final['verification_sha256']:
        raise ValueError('completed verification report changed')
    evaluation = load_json(DIRECTORY / 'evaluation.json')
    if evaluation['completed_epochs'] != 100 or evaluation['queries'] != 753:
        raise ValueError('full evaluation not complete')
    groups, pooled = {}, []
    for group, query_path, truth_path in require_workload_grid(workload_files(True)):
        queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
        with truth_path.open(newline='', encoding='utf-8') as stream:
            truths = list(csv.DictReader(stream))
        with (DIRECTORY / (group + '.csv')).open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != EXPECTED_COUNTS[group] or len(rows) != len(queries) or len(truths) != len(queries):
            raise ValueError('rebuilt MSCN evaluation count differs')
        errors = []
        for index, (row, query, truth) in enumerate(zip(rows, queries, truths)):
            if (int(row['query_no']) != index or row['group'] != group
                    or sql_tokens(row['query']) != sql_tokens(query)
                    or int(row['cardinality_true']) != int(truth['cardinality_true'])
                    or row['samples_manifest_sha256'] != final['samples_manifest_sha256']
                    or row['source_sql_sha256'] != hashlib.sha256(row['query'].encode()).hexdigest()):
                raise ValueError('rebuilt MSCN SQL/truth/sample identity differs')
            error = q_error(int(row['cardinality_predict']), int(row['cardinality_true']))
            import math
            if not math.isclose(error, float(row['q_error']), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError('rebuilt MSCN q-error differs')
            errors.append(error)
            if group != 'job_light':
                pooled.append((group, error))
        groups[group] = dict(queries=len(rows), **numeric_summary(errors))
    result = dict(status='PASS_PARENT_ARTIFACT_AND_PREDICTION_AUDIT', final_seal_sha256=FINAL_SEAL_SHA256,
                  completed_epochs=100, checkpoint_count=100, verified_output_artifacts=165,
                  queries=require_query_totals(groups), groups=groups,
                  public_3to6=dict(queries=len(pooled), **numeric_summary([e for _, e in pooled])),
                  public_4to6=dict(queries=sum(int(g[0]) >= 4 for g, _ in pooled),
                                    **numeric_summary([e for g, e in pooled if int(g[0]) >= 4])),
                  no_model_loading_or_inference=True, audit_source_sha256=file_sha256(__file__),
                  full_paper_reproduction_complete=False)
    result['receipt_sha256'] = binding_hash(result)
    if write:
        target = FULL / 'mscn/rebuilt_parent_audits' / result['audit_source_sha256'] / 'verification.json'
        atomic_json(target, result)
        atomic_json(FULL / 'results/mscn_rebuilt_parent_audit_latest.json',
                    dict(path=target.relative_to(ROOT).as_posix(), sha256=file_sha256(target)))
    return result


if __name__ == '__main__':
    result = verify(write=True)
    print(result['status'], result['queries'], result['public_4to6']['median'])
