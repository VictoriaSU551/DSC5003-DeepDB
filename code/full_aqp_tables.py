"""Export source-sealed Flights AQP and same-sample uniform-estimate figures.

Uses already computed exact sample moments; does not rescan, retrain or run
inference. The uniform reference is not the paper's timed TABLESAMPLE baseline.
"""
import csv
from fractions import Fraction
import math
from pathlib import Path

import numpy as np

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_flights_model import query_spec


def sample_estimate(moments, kind, population, actual_sample_rows):
    if not 0 < actual_sample_rows <= population: raise ValueError('invalid sample/population sizes')
    if kind == 'COUNT':
        return Fraction(population * moments['filter_count'], actual_sample_rows)
    if kind == 'AVG':
        return Fraction(moments['sum_integer'], moments['scale'] * moments['count']) if moments['count'] else None
    if kind in ('SUM', 'DIFF'):
        return Fraction(population * moments['sum_integer'], moments['scale'] * actual_sample_rows)
    raise ValueError('unsupported aggregate')


def group_error_summary(rows):
    matched, all_errors, missing, zero = [], [], 0, 0
    for row in rows:
        if row['truth'] == 0:
            zero += 1; continue
        present = row['sample_group_present'] and row['sample_prediction'] is not None
        if present:
            error = abs(row['sample_prediction'] / row['truth'] - 1.)
            matched.append(error); all_errors.append(error)
        else:
            missing += 1; all_errors.append(1.)
    return dict(matched_mean_relative_error=float(np.mean(matched)) if matched else None,
                mean_relative_error_with_missing_penalty=float(np.mean(all_errors)) if all_errors else None,
                missing_groups=missing, zero_truth_groups=zero, truth_groups=len(rows))


def artifact(path):
    path = Path(path).resolve()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=file_sha256(path))


def csv_table(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, keys); writer.writeheader(); writer.writerows(rows)


def draw(directory, queries, groups):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 180})
    x = np.arange(12); blue, gold = '#2166AC', '#C58417'
    fig, ax = plt.subplots(figsize=(11.7, 4.6))
    for offset, field, label, color, marker in [(-.12, 'model_mean_relative_error', 'DeepDB', blue, 'o'),
        (.12, 'sample_mean_relative_error_with_missing_penalty', 'Retained uniform sample', gold, '^')]:
        ax.scatter(x + offset, [100 * q[field] for q in queries], label=label, color=color, marker=marker, s=50)
    ax.set(xticks=x, xticklabels=[q['query'] for q in queries], yscale='log',
           ylabel='Mean relative error across groups (%)', title='Flights: own 1B-row population and 9,997,912-row sample')
    ax.legend(frameon=False); ax.grid(axis='y', color='#DDDDDD', lw=.7); ax.set_axisbelow(True)
    fig.text(.02,.02,'Uniform reference reuses exact sample moments, with N/n scaling; missing groups incur 100% error. This is not the timed TABLESAMPLE baseline.',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.98)); fig.savefig(str(directory/'flights_relative_error.png')); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6.9, 6.0))
    families = [('AVG', 'AVG', blue, 'o'), ('COUNT', 'COUNT', gold, 's'), ('SUM', 'SUM / difference', '#7C8330', '^')]
    positive = []
    for family, label, color, marker in families:
        chosen = [r for r in groups if r['ci_eligible'] and ('SUM' if r['aggregate'] == 'DIFF' else r['aggregate']) == family]
        a, b = [100*r['reference_relative_half_width'] for r in chosen], [100*r['model_relative_half_width'] for r in chosen]
        if not all(v > 0 and math.isfinite(v) for v in a+b): raise ValueError('CI plot requires positive finite relative widths')
        ax.scatter(a,b,s=22,c=color,marker=marker,alpha=.75,label=label); positive.extend(a+b)
    lo,hi=min(positive)*.8,max(positive)*1.2
    ax.plot([lo,hi],[lo,hi], '--',color='#555555',lw=1,label='Equal half widths')
    ax.set(xscale='log',yscale='log',xlim=(lo,hi),ylim=(lo,hi),xlabel='Same-sample reference half width (%)',
           ylabel='Original RSPN half width (%)',title='Flights: central 90% intervals, 322 eligible groups')
    ax.legend(frameon=False,fontsize=9); ax.grid(color='#DDDDDD',lw=.6)
    fig.text(.02,.018,'9 groups with sample count<10 excluded; one sample, not coverage calibration.\nThe independent reference retains covariance for F5.2; the original RSPN interval is unchanged.',fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.98)); fig.savefig(str(directory/'flights_ci_half_width.png')); plt.close(fig)


def main():
    validation_path = FULL / 'flights/model_formal_validation.json'
    validation = load_json(validation_path)
    contents = dict(validation); checksum = contents.pop('validation_sha256')
    if checksum != binding_hash(contents): raise ValueError('formal Flights validation seal changed')
    sources = [artifact(validation_path), artifact(Path(__file__))]
    for record in validation['artifacts']:
        path = ROOT / record['path']
        if path.stat().st_size != record['bytes'] or file_sha256(path) != record['sha256']:
            raise ValueError('formal input/model/evaluation changed: ' + record['path'])
    result_path = ROOT / validation['evaluation_path']; result = load_json(result_path)
    sources.append(artifact(result_path))
    if result['query_errors'] or result['population_rows'] != 1000000000 or len(result['queries']) != 12:
        raise ValueError('formal complete Flights evaluation required')
    binding = dict(sources=sources, population=result['population_rows'], actual_n=result['actual_training_rows'],
                   method='conditional_on_actual_sample_size_uniform_N_over_n_v1')
    directory = FULL / 'figures' / ('aqp_flights_' + binding_hash(binding)[:16])
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists():
        previous = load_json(manifest_path)
        if any(file_sha256(ROOT / a['path']) != a['sha256'] for a in previous['artifacts']):
            raise ValueError('previous figure/table changed')
        print('REUSED_SEALED_FLIGHTS_FIGURES', directory.relative_to(ROOT)); return
    directory.mkdir(parents=True, exist_ok=True)
    queries, groups = [], []
    for query in result['queries']:
        spec = query_spec(query['sql']); current = []
        for group in query['groups']:
            if group['truth'] is None: raise ValueError('extra model group cannot be silently omitted')
            moments, reference = group['sample_moments'], group['reference_ci']
            point = sample_estimate(moments, spec['kind'], result['population_rows'], result['actual_training_rows'])
            if reference['eligible'] and not math.isclose(float(point), reference['point'],rel_tol=1e-12,abs_tol=1e-9):
                raise ValueError('uniform estimate differs from existing independently computed CI reference point')
            row = dict(query=query['query_name'], key=str(group['key']), aggregate=spec['kind'],
                truth=group['truth'], model_prediction=group['prediction'], model_relative_error=group['relative_error'],
                sample_prediction=float(point) if point is not None else None,
                sample_group_present=not spec['group'] or moments['filter_count'] > 0,
                sample_count=moments['count'], sample_filter_count=moments['filter_count'],
                ci_eligible=reference['eligible'], ci_status=reference['status'],
                model_relative_half_width=group['model_relative_half_width'],
                reference_relative_half_width=reference.get('relative_half_width'),
                model_covers_truth=group['model_covers_truth'], reference_covers_truth=reference.get('covers_population_truth'))
            current.append(row); groups.append(row)
        sample_summary = group_error_summary(current)
        queries.append(dict(query=query['query_name'], aggregate=spec['kind'],
            model_mean_relative_error=query['coverage_penalized_mean_relative_error'],
            ci_eligible=query['ci_eligible_truth_groups'], ci_excluded=query['ci_excluded_groups'],
            model_ci_coverage=query['model_ci_coverage_all_eligible'],
            reference_ci_coverage=query['reference_ci_coverage'],
            **{'sample_'+key:value for key,value in sample_summary.items()}))
    csv_table(directory / 'query_summary.csv', queries); csv_table(directory / 'all_groups.csv', groups)
    draw(directory, queries, groups)
    atomic_json(manifest_path,dict(status='PASS_LOCAL_SAME_SAMPLE_COMPARISON',binding=binding_hash(binding),
        binding_details=binding, artifacts=[artifact(p) for p in sorted(directory.iterdir()) if p.is_file()],
        full_paper_complete=False, count_and_sum='N/n times sample aggregate; known population and actual retained sample size',
        missing_group_policy='All truth groups retained. Absent grouped results have no SQL output and incur100pct relative-error penalty.',
        baseline_scope='Uniform materialized sample; not the paper timed PostgreSQL TABLESAMPLE/VerdictDB/XDB baseline',
        ci_scope='Central90pct, exclude count<10, single realized sample; no repeated-sampling calibration claim'))
    atomic_json(FULL / 'results/flights_tables_latest.json', dict(path=directory.relative_to(ROOT).as_posix(),
        manifest_sha256=file_sha256(manifest_path), full_paper_complete=False))
    print('FLIGHTS_TABLES_READY', directory.relative_to(ROOT))


if __name__ == '__main__': main()
