"""Read-only SSB SF500 derived tables; requires independent formal replay first."""
import math
from pathlib import Path

import numpy as np

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_aqp_tables import artifact, csv_table, group_error_summary, sample_estimate

NAMES = ['S1.1', 'S1.2', 'S1.3', 'S2.1', 'S2.2', 'S2.3', 'S3.1', 'S3.2', 'S3.3', 'S3.4', 'S4.1', 'S4.2', 'S4.3']
OUTPUT_NAMES = {'query_summary.csv', 'all_groups.csv', 'training_tables.csv',
                'ssb_relative_error.png', 'ssb_ci_half_width.png'}


def summarize(query, population, actual_sample_rows):
    kind = 'DIFF' if query['query_no'] >= 10 else 'SUM'
    rows, model_errors, eligible, covered, reference_covered, missing_ci = [], [], 0, 0, 0, 0
    invalid_points = 0
    seen = set()
    for group in query['groups']:
        key = tuple(group['key'])
        if key in seen:
            raise ValueError('duplicate SSB group identity')
        seen.add(key)
        truth, prediction = group['truth'], group['prediction']
        invalid_point = (group['status'] != 'MISSING_MODEL_GROUP'
                         and (prediction is None or not math.isfinite(prediction)))
        if invalid_point and truth is not None:
            invalid_points += 1
        moments, ci = group['sample_moments'], group['reference_ci']
        point = float(sample_estimate(moments, kind, population, actual_sample_rows))
        if ci['eligible'] and not math.isclose(point, ci['point'], rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError('uniform point differs from existing exact-moment reference')
        error = None
        if truth not in (None, 0):
            if invalid_point:
                pass
            elif group['status'] == 'MISSING_MODEL_GROUP':
                error = 1.
            else:
                error = abs(prediction / truth - 1.)
                if not math.isfinite(error) or not math.isclose(error, group['relative_error'], rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError('stored model relative error differs')
            if error is not None:
                model_errors.append(error)
        if truth is not None and ci['eligible']:
            eligible += 1
            covered += group['model_covers_truth'] is True
            reference_covered += ci.get('covers_population_truth') is True
            missing_ci += group['model_covers_truth'] is None
        rows.append(dict(query=query['query_name'], key=str(group['key']), aggregate=kind,
            status='MATCHED_WITHOUT_FINITE_PREDICTION' if invalid_point and truth is not None else group['status'],
            source_status=group['status'], invalid_model_point=invalid_point,
            truth=truth, model_prediction=None if invalid_point else prediction,
            model_relative_error_with_missing_penalty=error,
            sample_prediction=point, sample_group_present=moments['filter_count'] > 0,
            sample_count=moments['count'], sample_filter_count=moments['filter_count'],
            ci_eligible=ci['eligible'], ci_status=ci['status'],
            model_relative_half_width=group['model_relative_half_width'],
            reference_relative_half_width=ci.get('relative_half_width'),
            model_covers_truth=group['model_covers_truth'],
            reference_covers_truth=ci.get('covers_population_truth')))
    actual = [row for row in rows if row['truth'] is not None]
    missing = sum(row['status'] == 'MISSING_MODEL_GROUP' for row in rows)
    extra = sum(row['truth'] is None for row in rows)
    if (missing != query['missing_model_groups'] or extra != query['extra_model_groups']):
        raise ValueError('stored group coverage differs')
    uniform = group_error_summary(actual)
    summary = dict(query=query['query_name'], query_no=query['query_no'],
        truth_groups=len(actual), missing_model_groups=missing, extra_model_groups=extra,
        invalid_model_points=invalid_points,
        nonzero_truth_groups_for_relative_error=sum(r['truth'] not in (None, 0) for r in rows),
        model_mean_relative_error_with_missing_penalty=float(np.mean(model_errors)) if model_errors and not invalid_points else None,
        reference_ci_eligible=eligible, reference_ci_excluded=len(actual)-eligible,
        model_missing_intervals_among_eligible=missing_ci,
        model_ci_coverage_all_eligible=covered/eligible if eligible else None,
        reference_ci_coverage=reference_covered/eligible if eligible else None,
        point_seconds=query['point_seconds'], ci_seconds=query['ci_seconds'],
        point_error=query['point_error'], ci_error=query['ci_error'],
        original_nonfinite_intervals=len(query['nonfinite_original_intervals']),
        **{'sample_' + k: v for k, v in uniform.items()})
    return rows, summary


def require_existing_figures(receipt, directory, binding):
    if (receipt.get('binding') != binding_hash(binding) or receipt.get('binding_details') != binding
            or receipt.get('status') != 'PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES'
            or receipt.get('full_paper_complete') is not False):
        raise ValueError('SSB figure manifest binding differs')
    records = receipt.get('artifacts', [])
    paths = [(ROOT / item['path']).resolve() for item in records]
    if (len(paths) != 5 or len(set(paths)) != 5 or {p.name for p in paths} != OUTPUT_NAMES
            or any(p.parent != directory.resolve() for p in paths)):
        raise ValueError('complete unique five-artifact SSB figure inventory required')
    for path, item in zip(paths, records):
        if path.stat().st_size != item['bytes'] or file_sha256(path) != item['sha256']:
            raise ValueError('sealed SSB table/figure changed')


def draw(directory, queries, groups, actual_n):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
        'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 180})
    fig, ax = plt.subplots(figsize=(12, 4.9))
    for offset, field, label, color, marker in [(-.12, 'model_mean_relative_error_with_missing_penalty',
        'DeepDB (cap 1M per table)', '#2166AC', 'o'), (.12, 'sample_mean_relative_error_with_missing_penalty',
        'Uniform reference (' + format(actual_n, ',') + ' fact rows)', '#C58417', '^')]:
        points = [(i, 100*q[field]) for i, q in enumerate(queries) if q[field] is not None]
        ax.scatter([i+offset for i, _ in points], [v for _, v in points], label=label, color=color, marker=marker, s=50)
    values = [q[f] for q in queries for f in ['model_mean_relative_error_with_missing_penalty',
               'sample_mean_relative_error_with_missing_penalty'] if q[f] is not None]
    ax.set_yscale('log' if values and min(values) > 0 else 'symlog', **({} if values and min(values) > 0 else {'linthresh':1e-6}))
    ax.set(xticks=np.arange(13), xticklabels=NAMES, ylabel='Mean relative error across truth groups (%)',
           title='SSB SF500: exact 3,000,028,242-row population')
    ax.legend(frameon=False, fontsize=9); ax.grid(axis='y', color='#DDDDDD', lw=.7)
    fig.text(.02, .025, 'Model uses original n/p fact normalizer; exact N is reserved for truth/uniform reference. Different sample budgets.\n'
             'Missing groups incur 100% error; invalid points suppress the full query mean. Extras/zeros remain separate. Not a timed baseline.', fontsize=9)
    fig.tight_layout(rect=(0, .12, 1, .98)); fig.savefig(str(directory/'ssb_relative_error.png')); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.4, 6.4)); positive = []
    for family, color, marker in [('S1', '#2166AC', 'o'), ('S2', '#C58417', 's'),
                                   ('S3', '#7C8330', '^'), ('S4', '#7C3A5E', 'D')]:
        pairs = [(r['reference_relative_half_width'], r['model_relative_half_width']) for r in groups
                 if r['truth'] is not None and r['ci_eligible'] and r['query'].startswith(family)]
        points = [(a, b) for a, b in pairs if a is not None and b is not None and min(a, b) > 0
                  and math.isfinite(a) and math.isfinite(b)]
        positive.extend(v for pair in points for v in pair)
        ax.scatter([100*a for a, _ in points], [100*b for _, b in points], label=family,
                   color=color, marker=marker, s=30, alpha=.75)
    if positive:
        low, high = min(positive)*80, max(positive)*120
        ax.plot([low, high], [low, high], '--', color='#777777', lw=1)
        ax.set(xscale='log', yscale='log', xlim=(low, high), ylim=(low, high))
    ax.set(xlabel='Independent sample reference half width (%)', ylabel='Original RSPN half width (%)',
           title='SSB: central 90% intervals, one realized sample')
    ax.legend(frameon=False); ax.grid(color='#DDDDDD', lw=.6)
    fig.text(.02, .02, 'Reference uses the retained fact sample joined to complete dimensions; count<10 groups excluded.\n'
             'Only positive finite widths are plotted; all groups remain in CSV. S4 SUM differences can violate independence.\n'
             'Bernoulli reference differs from released SYSTEM sampling. This is not repeated-sampling calibration.', fontsize=9)
    fig.tight_layout(rect=(0, .12, 1, .98)); fig.savefig(str(directory/'ssb_ci_half_width.png')); plt.close(fig)


def main():
    from full_ssb_replay import verify
    accepted = verify()  # Strictly read-only, missing replay evidence must fail.
    report_path = FULL / 'results/ssb_model_aqp_ci.json'
    if (accepted.get('status') != 'PASS_INDEPENDENT_REVERSE_REPLAY_CURRENT_DEPENDENCIES'
            or file_sha256(report_path) != accepted['source_snapshot']['formal_result_sha256']):
        raise ValueError('formal report differs from its independent replay acceptance')
    report = load_json(report_path)
    if (report['stage'] != 'SSB_SF500_SINGLE_1M_AQP_CI' or report['spn_count'] != 5
            or report['inputs']['population_rows'] != 3000028242 or len(report['queries']) != 13
            or [(q['query_no'], q['query_name']) for q in report['queries']] != list(enumerate(NAMES))):
        raise ValueError('full SF500/13-query contract required')
    binding = dict(readonly_acceptance=accepted, sources=[artifact(p) for p in [Path(__file__), report_path,
        ROOT/'code/full_aqp_tables.py', ROOT/'code/full_ssb_replay.py']], full_paper_complete=False)
    directory = FULL/'figures'/('aqp_ssb_'+binding_hash(binding)[:16])
    manifest_path = directory/'manifest.json'
    if manifest_path.exists():
        require_existing_figures(load_json(manifest_path), directory, binding)
        atomic_json(FULL/'results/ssb_tables_latest.json', dict(path=directory.relative_to(ROOT).as_posix(),
            manifest_sha256=file_sha256(manifest_path), full_paper_complete=False))
        print('REUSED_SEALED_SSB_TABLES', directory.relative_to(ROOT)); return
    queries, groups = [], []
    for query in report['queries']:
        rows, summary = summarize(query, report['inputs']['population_rows'], report['inputs']['sample_rows'])
        queries.append(summary); groups.extend(rows)
    directory.mkdir(parents=True, exist_ok=True)
    csv_table(directory/'query_summary.csv', queries); csv_table(directory/'all_groups.csv', groups)
    csv_table(directory/'training_tables.csv', [{k: t[k] for k in ['table', 'actual_training_rows',
        'full_join_estimate', 'learning_seconds']} for t in report['training_tables']])
    draw(directory, queries, groups, report['inputs']['sample_rows'])
    atomic_json(manifest_path, dict(status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES', binding=binding_hash(binding),
        binding_details=binding, artifacts=[artifact(p) for p in sorted(directory.iterdir()) if p.is_file()],
        full_paper_complete=False, group_truth_rows=sum(q['truth_groups'] for q in queries),
        training_rows_per_table={t['table']: t['actual_training_rows'] for t in report['training_tables']},
        confidence_fact_sample_rows=report['inputs']['sample_rows'], normalizer_scope=report['normalizer_scope'],
        ci_scope=report['ci_scope'], missing_group_policy='100pct relative-error penalty; extras/zero truth separate. '
        'A matched group without a finite prediction is invalid and makes the complete-query mean unavailable.'))
    atomic_json(FULL/'results/ssb_tables_latest.json', dict(path=directory.relative_to(ROOT).as_posix(),
        manifest_sha256=file_sha256(manifest_path), full_paper_complete=False))
    print('SSB_TABLES_READY', directory.relative_to(ROOT))


if __name__ == '__main__':
    main()
