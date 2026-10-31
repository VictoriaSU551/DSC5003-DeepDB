"""Inspectably partial Flights comparison, using completed sealed predictions.

No fitting, integration or model inference. DBEst has a 20K fitting budget and
four supported SQL classes; unsupported queries remain absent from the chart.
"""
import csv
from fractions import Fraction
import math
from pathlib import Path

import numpy as np

from full_aqp_tables import artifact, csv_table, main as verify_flights_tables
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_dbest_flights_audit import verify as verify_dbest


def group_key(key):
    if not key:
        return 'all'
    if len(key) != 1:
        raise ValueError('DBEst comparison only supports its verified one-column grouping')
    return str(key[0])


def dbest_summary(query, truth_groups):
    if query['status'] == 'UNSUPPORTED':
        if query['predictions']:
            raise ValueError('unsupported query unexpectedly contains predictions')
        return dict(status='UNSUPPORTED', mean_relative_error_with_missing_penalty=None,
                    matched_mean_relative_error=None, missing_groups=None, extra_groups=None,
                    truth_groups=len(truth_groups), zero_truth_groups=None)
    truth = {group_key(r['key']): r['truth'] for r in truth_groups}
    predictions = {str(r['group']): r for r in query['predictions']}
    if len(truth) != len(truth_groups) or len(predictions) != len(query['predictions']):
        raise ValueError('duplicate comparison group identity')
    errors, matched, missing, zero = [], [], 0, 0
    for key, actual in truth.items():
        if actual == 0:
            zero += 1; continue
        prediction = predictions.get(key)
        if prediction is None:
            missing += 1; errors.append(1.); continue
        source_truth = float(Fraction(prediction['truth_numerator'], prediction['truth_denominator']))
        if not prediction['truth_group_present'] or not math.isclose(source_truth, actual, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError('DBEst truth does not match the sealed Flights population')
        error = abs(float(prediction['estimate']) / actual - 1.)
        errors.append(error); matched.append(error)
    return dict(status=query['status'],
                mean_relative_error_with_missing_penalty=float(np.mean(errors)) if errors else None,
                matched_mean_relative_error=float(np.mean(matched)) if matched else None,
                missing_groups=missing, extra_groups=len(set(predictions) - set(truth)),
                truth_groups=len(truth), zero_truth_groups=zero)


def main():
    verify_flights_tables()
    dbest_audit = verify_dbest()
    pointer = load_json(FULL / 'results/flights_tables_latest.json')
    base = ROOT / pointer['path']
    if file_sha256(base / 'manifest.json') != pointer['manifest_sha256']:
        raise ValueError('sealed Flights table pointer changed')
    for item in load_json(base / 'manifest.json')['artifacts']:
        if file_sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('sealed Flights comparison source changed')
    with (base / 'query_summary.csv').open(newline='', encoding='utf-8') as stream:
        base_rows = list(csv.DictReader(stream))
    validation = load_json(FULL / 'flights/model_formal_validation.json')
    evaluation_path = ROOT / validation['evaluation_path']
    formal = load_json(evaluation_path)
    dbest_path = FULL / 'dbest_flights/verification.json'
    if file_sha256(dbest_path) != dbest_audit['source_report_sha256']:
        raise ValueError('DBEst source report differs from its independent audit')
    dbest = load_json(dbest_path)
    if len(base_rows) != 12 or len(formal['queries']) != 12 or len(dbest['queries']) != 12:
        raise ValueError('all twelve original query identities are required')
    rows = []
    for i, (base_row, actual, model) in enumerate(zip(base_rows, formal['queries'], dbest['queries'])):
        if base_row['query'] != actual['query_name'] or model['name'] != actual['query_name'] or model['query_no'] != i:
            raise ValueError('comparison query identity differs')
        summary = dbest_summary(model, actual['groups'])
        rows.append(dict(query=base_row['query'],
            deepdb_mean_relative_error=float(base_row['model_mean_relative_error']),
            uniform_mean_relative_error=float(base_row['sample_mean_relative_error_with_missing_penalty']),
            **{'dbest_' + key: value for key, value in summary.items()},
            deepdb_sample_rows=9997912, uniform_sample_rows=9997912, dbest_unique_fit_rows=20000))
    sources = [artifact(p) for p in [Path(__file__), ROOT / 'code/full_aqp_tables.py',
        ROOT / 'code/full_dbest_flights_audit.py', base / 'manifest.json', base / 'query_summary.csv',
        evaluation_path, dbest_path, FULL / 'dbest_flights_audit/verification.json',
        FULL / 'dbest_flights_audit/verification_seal.json']]
    binding = dict(sources=sources, missing_group_policy='100pct relative-error penalty; unsupported query remains null')
    directory = FULL / 'figures' / ('aqp_flights_comparisons_' + binding_hash(binding)[:16])
    manifest = directory / 'manifest.json'
    if manifest.exists():
        for item in load_json(manifest)['artifacts']:
            if file_sha256(ROOT / item['path']) != item['sha256']:
                raise ValueError('existing partial comparison artifact changed')
        print('REUSED_PARTIAL_FLIGHTS_COMPARISON', directory.relative_to(ROOT)); return
    directory.mkdir(parents=True, exist_ok=True)
    csv_table(directory / 'query_comparison.csv', rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 180})
    fig, ax = plt.subplots(figsize=(12, 4.9))
    series = [(-.18, 'deepdb_mean_relative_error', 'DeepDB (9,997,912 rows)', '#2166AC', 'o'),
              (0, 'uniform_mean_relative_error', 'Uniform reference (same sample)', '#C58417', '^'),
              (.18, 'dbest_mean_relative_error_with_missing_penalty', 'DBEst (20,000 fit rows; partial)', '#7C3A5E', 'D')]
    for offset, field, label, color, marker in series:
        points = [(i, row[field]) for i, row in enumerate(rows) if row[field] is not None]
        if any(value <= 0 or not math.isfinite(value) for _, value in points):
            raise ValueError('log error plot needs positive finite values')
        ax.scatter([i + offset for i, _ in points], [100 * value for _, value in points],
                   s=48, color=color, marker=marker, label=label)
    ax.set(xticks=np.arange(12), xticklabels=[r['query'] for r in rows], yscale='log',
           ylabel='Mean relative error across truth groups (%)',
           title='Flights: partial baseline comparison on the same 1B-row population')
    ax.grid(axis='y', color='#DDDDDD', lw=.7); ax.legend(frameon=False, fontsize=9, loc='upper left')
    fig.text(.02, .025, 'Different fitting budgets and query information: not the paper configuration or a matched-budget comparison.\n'
             'DBEst: four supported SQL classes; eight unsupported remain unplotted. Missing F4.1/DE incurs 100% error. No runtime ranking.', fontsize=9)
    fig.tight_layout(rect=(0, .11, 1, .98))
    fig.savefig(str(directory / 'flights_partial_baselines.png')); plt.close(fig)
    atomic_json(manifest, dict(status='PASS_EXPLICITLY_PARTIAL_LOCAL_COMPARISON', binding=binding_hash(binding),
        binding_details=binding, artifacts=[artifact(p) for p in sorted(directory.iterdir()) if p.is_file()],
        full_paper_complete=False, unsupported_dbest_queries=8, note='No new inference or integration; no paper-original training configuration claim'))
    atomic_json(FULL / 'results/flights_comparisons_latest.json', dict(path=directory.relative_to(ROOT).as_posix(),
        manifest_sha256=file_sha256(manifest), full_paper_complete=False))
    print('PARTIAL_FLIGHTS_COMPARISON_READY', directory.relative_to(ROOT))


if __name__ == '__main__':
    main()
