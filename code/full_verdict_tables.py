"""Derived Flights comparison for the original Verdict engine on an existing sample.

Raw compound-SUM failure and the two-query adapter remain separate results.
No database connection, SQL execution, fitting or inference occurs here.
"""
import csv
import math
from pathlib import Path

import numpy as np

from full_aqp_tables import artifact, csv_table, main as require_flights_tables
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json

NAMES = ('F1.1', 'F1.2', 'F2.1', 'F2.2', 'F2.3', 'F3.1', 'F3.2', 'F3.3', 'F4.1', 'F4.2', 'F5.1', 'F5.2')
OUTPUT_NAMES = {'query_summary.csv', 'all_groups.csv', 'flights_verdict_comparison.png'}


def summarize(query, mode):
    if mode not in ('raw', 'adapted'):
        raise ValueError('unknown Verdict projection mode')
    source = query if mode == 'raw' else query['adapted']
    if source is None:
        raise ValueError('absent adapter cannot be treated as a prediction')
    rows, errors, matched, seen = [], [], [], set()
    missing = extra = zeros = invalid = 0
    for group in source['groups']:
        key = tuple(group['key'])
        if key in seen:
            raise ValueError('duplicate Verdict group identity')
        seen.add(key)
        truth, prediction, status = group['truth'], group['prediction'], group['status']
        if truth is not None and not math.isfinite(truth):
            raise ValueError('nonfinite truth is not a usable reference')
        is_missing, is_extra = status == 'MISSING_MODEL_GROUP', status == 'EXTRA_MODEL_GROUP'
        missing += is_missing; extra += is_extra; zeros += truth == 0
        if is_extra != (truth is None) or (is_missing and prediction is not None):
            raise ValueError('Verdict group presence contract differs')
        bad = not is_missing and (prediction is None or not math.isfinite(prediction))
        invalid += bad and truth is not None
        error = None
        if truth not in (None, 0) and not bad:
            error = 1. if is_missing else abs(prediction / truth - 1.)
            if not is_missing:
                if not math.isclose(error, group['relative_error'], rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError('stored Verdict relative error differs')
                matched.append(error)
            errors.append(error)
        interval = group.get('native_95pct_interval') if mode == 'raw' else None
        if interval is not None and (len(interval) != 2 or not all(math.isfinite(v) for v in interval) or interval[0] > interval[1]):
            raise ValueError('invalid stored native Verdict interval')
        rows.append(dict(query=query['query_name'], mode=mode, key=str(group['key']),
            source_status=query['raw_status'] if mode == 'raw' else source['status'],
            status='MATCHED_WITHOUT_FINITE_PREDICTION' if bad and truth is not None else status,
            truth=truth, prediction=None if bad else prediction,
            relative_error_with_missing_penalty=error, zero_truth=truth == 0,
            native_ci_confidence=query['native_ci_confidence'] if mode == 'raw' else None,
            native_interval=interval,
            native_ci_status=group.get('native_ci_status', 'UNAVAILABLE') if mode == 'raw' else source['ci_status']))
    if missing != source['missing'] or extra != source['extra']:
        raise ValueError('stored Verdict group coverage differs')
    summary = dict(query=query['query_name'], mode=mode,
        source_status=query['raw_status'] if mode == 'raw' else source['status'],
        truth_groups=sum(row['truth'] is not None for row in rows), missing_groups=missing,
        extra_groups=extra, invalid_predictions=invalid, zero_truth_groups=zeros,
        mean_relative_error_with_missing_penalty=float(np.mean(errors)) if errors and not invalid else None,
        matched_mean_relative_error=float(np.mean(matched)) if matched else None,
        physical_sql_calls=1 if mode == 'raw' else source['physical_sql_calls'],
        engine_wall_ms=query['raw']['engine_wall_ms'] if mode == 'raw' else source['engine_wall_ms'],
        native_ci_confidence=query['native_ci_confidence'] if mode == 'raw' else None,
        native_ci_engine_wall_ms=query['native_ci']['engine_wall_ms'] if mode == 'raw' else None)
    return rows, summary


def existing_bundle(receipt, directory, binding):
    if (receipt.get('status') != 'PASS_VERDICT_SAMPLE_ONLY_DERIVED_TABLES'
            or receipt.get('binding_details') != binding or receipt.get('binding') != binding_hash(binding)
            or receipt.get('full_paper_complete') is not False):
        raise ValueError('Verdict figure binding changed')
    records = receipt.get('artifacts', [])
    paths = [(ROOT / row['path']).resolve() for row in records]
    if (len(paths) != 3 or len(set(paths)) != 3 or {p.name for p in paths} != OUTPUT_NAMES
            or any(p.parent != directory.resolve() for p in paths)):
        raise ValueError('complete unique three-artifact Verdict figure bundle required')
    for path, row in zip(paths, records):
        if path.stat().st_size != row['bytes'] or file_sha256(path) != row['sha256']:
            raise ValueError('Verdict derived artifact changed')


def draw(directory, summaries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11,
        'axes.spines.top':False, 'axes.spines.right':False, 'savefig.dpi':180})
    raw = [row for row in summaries if row['mode'] == 'raw']
    fig, ax = plt.subplots(figsize=(12, 5.6))
    for offset, field, label, color, marker in [
        (-.2, 'deepdb_mean_relative_error', 'DeepDB', '#2166AC', 'o'),
        (0, 'uniform_mean_relative_error', 'Uniform reference (same sample)', '#C58417', '^'),
        (.2, 'mean_relative_error_with_missing_penalty', 'Verdict raw (F5.2 incorrect)', '#35704A', 'D')]:
        points = [(i, row[field]) for i, row in enumerate(raw) if row[field] is not None]
        if any(value <= 0 or not math.isfinite(value) for _, value in points):
            raise ValueError('positive finite errors required for this log chart')
        ax.scatter([i+offset for i, _ in points], [100*v for _, v in points], label=label, color=color, marker=marker, s=48)
    adapted = [row for row in summaries if row['mode'] == 'adapted']
    ax.scatter([NAMES.index(row['query'])+.32 for row in adapted],
        [100*row['mean_relative_error_with_missing_penalty'] for row in adapted],
        label='F5.2: two original SUM calls, external difference', color='#7C3A5E', marker='*', s=120)
    ax.set(xticks=np.arange(12), xticklabels=NAMES, yscale='log',
        ylabel='Mean relative error across truth groups (%)')
    fig.suptitle('Flights: existing 9,997,912-row sample of the same 1B-row population', y=.995)
    fig.legend(*ax.get_legend_handles_labels(), frameon=False, fontsize=9,
               loc='upper center', bbox_to_anchor=(.5, .95), ncol=2)
    ax.grid(axis='y', color='#DDDDDD', lw=.7)
    fig.text(.02, .025, 'Sample-only execution: no full 1B PostgreSQL table or original-table sampling cost. Missing groups incur 100% error.\n'
        'Raw F5.2 is unscaled by the original engine; its adapter is separate. Native 95% intervals stay in CSV, distinct from DeepDB 90%.\n'
        'Query wall times are recorded separately; this chart does not rank runtime or reproduce author hardware.', fontsize=9)
    fig.tight_layout(rect=(0, .15, 1, .87)); fig.savefig(str(directory/'flights_verdict_comparison.png')); plt.close(fig)


def main():
    from full_verdict_audit import verify
    require_flights_tables()
    accepted = verify()
    if accepted['status'] != 'PASS_READ_ONLY_ORIGINAL_VERDICT_SAMPLE_ONLY_WITH_GAPS':
        raise ValueError('sealed sample-only Verdict audit required')
    evaluation = ROOT/accepted['evaluation_artifact']['path']
    if artifact(evaluation) != accepted['evaluation_artifact']:
        raise ValueError('Verdict evaluation differs from its audit')
    report = load_json(evaluation)
    if (report['population_prior'] != 1000000000 or report['actual_sample_rows'] != 9997912
            or tuple(q['query_name'] for q in report['queries']) != NAMES
            or report['query_truth_used_for_registration'] is not False):
        raise ValueError('Verdict query/population/information budget differs')
    pointer_path = FULL/'results/flights_tables_latest.json'; pointer = load_json(pointer_path)
    base = ROOT/pointer['path']; manifest = base/'manifest.json'
    if file_sha256(manifest) != pointer['manifest_sha256']:
        raise ValueError('Flights comparison pointer changed')
    with (base/'query_summary.csv').open(newline='', encoding='utf-8') as stream:
        base_rows = list(csv.DictReader(stream))
    if tuple(q['query'] for q in base_rows) != NAMES:
        raise ValueError('all twelve ordered Flights identities required')
    summaries, groups = [], []
    for query, baseline in zip(report['queries'], base_rows):
        for mode in ('raw', 'adapted') if query['adapted'] is not None else ('raw',):
            rows, summary = summarize(query, mode); groups.extend(rows)
            summary.update(deepdb_mean_relative_error=float(baseline['model_mean_relative_error']),
                uniform_mean_relative_error=float(baseline['sample_mean_relative_error_with_missing_penalty']))
            summaries.append(summary)
    sources = [artifact(p) for p in [Path(__file__), ROOT/'code/full_verdict_audit.py', evaluation,
        ROOT/accepted['verification']['path'], ROOT/accepted['final_seal']['path'], manifest, base/'query_summary.csv']]
    binding = dict(sources=sources, scope='Existing uniform sample only; raw compound SUM and adapter kept separate')
    directory = FULL/'figures'/('aqp_flights_verdict_'+binding_hash(binding)[:16])
    final = directory/'manifest.json'
    if final.exists():
        existing_bundle(load_json(final), directory, binding)
    else:
        directory.mkdir(parents=True, exist_ok=False)
        csv_table(directory/'query_summary.csv', summaries); csv_table(directory/'all_groups.csv', groups)
        draw(directory, summaries)
        atomic_json(final, dict(status='PASS_VERDICT_SAMPLE_ONLY_DERIVED_TABLES', binding=binding_hash(binding),
            binding_details=binding, full_paper_complete=False,
            artifacts=[artifact(p) for p in sorted(directory.iterdir()) if p.is_file()],
            ci_scope='Verdict native95%, DeepDB central90%; no adapter CI or calibration/ranking claim',
            execution_scope='Retained sample only, original population table absent; no paper end-to-end claim'))
    atomic_json(FULL/'results/verdict_tables_latest.json', dict(path=directory.relative_to(ROOT).as_posix(),
        manifest_sha256=file_sha256(final), full_paper_complete=False))
    print('VERDICT_SAMPLE_ONLY_TABLES_READY', directory.relative_to(ROOT))


if __name__ == '__main__':
    main()
