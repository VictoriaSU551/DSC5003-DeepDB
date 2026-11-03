"""Build immutable, source-sealed paper comparison tables and research figures.

Only fully verified canonical v3 predictions enter current comparisons. Author numbers
are a separate series. Public grouped queries are not the unidentified paper200.
No model training or inference is performed by this module.
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import numeric_summary, q_error, workload_files
from full_evaluation_v3 import PROTOCOL
from full_status import verified_current_evaluation

AUTHOR_TABLE1 = {
    'DeepDB': [1.34, 2.50, 3.16, 39.63],
    'DeepDB storage': [1.32, 4.14, 5.74, 72.00],
    'Perfect Selectivities': [2.08, 9, 11, 33],
    'MSCN': [3.22, 65, 143, 717],
    'Wavelets': [7.64, 9839, 15332, 564549],
    'PostgreSQL11.5': [6.84, 162, 817, 3477],
    'IBJS': [1.67, 72, 333, 6949],
    'Random sampling': [5.05, 73, 10371, 49187],
}
QUANTILES = ('median', 'p90', 'p95', 'max')


def checked_errors(rows):
    errors = []
    for row in rows:
        truth, prediction = int(row['cardinality_true']), float(row['cardinality_predict'])
        actual = q_error(prediction, truth)
        recorded = float(row['q_error'])
        if not (actual == recorded or math.isclose(actual, recorded, rel_tol=1e-10, abs_tol=1e-12)):
            raise ValueError('recorded q-error differs from truth and prediction')
        errors.append(actual)
    return errors


def selected_summary(groups, predicate):
    rows = [row for group, values in groups.items() if predicate(group) for row in values]
    if not rows:
        return None
    return dict(queries=len(rows), **numeric_summary(checked_errors(rows)))


def csv_rows(path):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def source_record(path):
    path = Path(path).resolve()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=file_sha256(path))


def historical_v2_comparison(label, current, sources):
    """Compare frozen prediction files; never certify v2 as current inference."""
    path = FULL / 'results' / (label + '_evaluation_v2.json')
    summary = load_json(path)
    if summary is None:
        return None
    source = summary.get('reused_from_label', label)
    previous, changes = {}, {}
    for group, rows in current.items():
        csv = FULL / 'evaluation_v2' / source / (group + '.csv')
        if file_sha256(csv) != summary['groups'][group]['csv_sha256']:
            raise ValueError('historical v2 CSV changed: ' + str(csv))
        old = csv_rows(csv)
        if (len(old) != len(rows) or any(a['query'] != b['query'] or a['query_no'] != b['query_no']
                or a['cardinality_true'] != b['cardinality_true'] for a, b in zip(old, rows))):
            raise ValueError('historical v2/v3 workload identity differs')
        changed, maximum = 0, 0.
        for a, b in zip(old, rows):
            earlier, canonical = float(a['cardinality_predict']), float(b['cardinality_predict'])
            if not math.isclose(earlier, canonical, rel_tol=1e-9, abs_tol=1e-7):
                changed += 1
                maximum = max(maximum, abs(canonical - earlier) / abs(earlier) if earlier else math.inf)
        changes[group] = dict(queries=len(rows), changed_predictions=changed,
                              largest_relative_change_from_v2=maximum)
        previous[group] = old
        sources[csv.relative_to(ROOT).as_posix()] = source_record(csv)
    sources[path.relative_to(ROOT).as_posix()] = source_record(path)
    return dict(scope='Historical v2 file comparison only; current results require canonical four-seed acceptance',
                job_light=selected_summary(previous, lambda g: g == 'job_light'),
                public_3to6=selected_summary(previous, lambda g: g != 'job_light'),
                group_changes=changes)


def sealed_model(label, include_scale, sources):
    count = 753 if include_scale else 70
    stage = verified_current_evaluation(label, count)
    if stage['status'] == 'PENDING':
        return None
    if stage['status'] != 'PASS_LOCAL_VARIANT':
        raise ValueError('invalid evidence for ' + label + ': ' + str(stage))
    summary_path = FULL / 'results' / (label + '_evaluation_v3.json')
    training_path = FULL / 'results' / (label + '_training.json')
    summary, training = load_json(summary_path), load_json(training_path)
    for path in (summary_path, training_path, ROOT / training['model_path']):
        sources[path.relative_to(ROOT).as_posix()] = source_record(path)
    groups = {}
    for group, _, truth_path in workload_files(include_scale):
        path = FULL / 'evaluation_v3' / label / (group + '.csv')
        rows, truths = csv_rows(path), csv_rows(truth_path)
        if len(rows) != len(truths) or any(int(row['cardinality_true']) != int(t['cardinality_true'])
                                         for row, t in zip(rows, truths)):
            raise ValueError('CSV truth alignment differs: ' + str(path))
        checked_errors(rows)
        sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        groups[group] = rows
    unique = {component['binding']: component for component in training['models']}
    learning = sum(float(c.get('learn_seconds', c.get('learning_seconds', 0))) for c in unique.values())
    sampling = sum(float(c.get('sample_seconds', 0)) for c in unique.values())
    result = dict(label=label, profile=training.get('profile', 'joblight'),
                  requested_samples=training['requested_samples'], budget=training.get('budget'),
                  components=len(training['models']), model_bytes=(ROOT / training['model_path']).stat().st_size,
                  actual_rows=[c['actual_samples'] for c in training['models']],
                  component_learning_seconds=learning, component_sampling_seconds=sampling,
                  job_light=selected_summary(groups, lambda g: g == 'job_light'),
                  public_3to6=selected_summary(groups, lambda g: g != 'job_light'),
                  public_4to6=selected_summary(groups, lambda g: g != 'job_light' and int(g[0]) >= 4),
                  group_summaries={g: selected_summary({g: r}, lambda _: True) for g, r in groups.items()},
                  historical_v2=historical_v2_comparison(label, groups, sources),
                  temporal_models=[{k: c[k] for k in ('spec', 'initial_sample_rows', 'updated_sample_rows',
                      'sample_update_fraction', 'initial_population', 'full_population', 'population_update_fraction')}
                      for c in training['models'] if 'sample_update_fraction' in c])
    return result


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows(rows)


def table1_rows(models, sources):
    rows = [dict(method=name, evidence='author_reported_Table1', queries=70,
                 **dict(zip(QUANTILES, values))) for name, values in AUTHOR_TABLE1.items()]
    for label, method in [('rdc_n100000_b0p0', 'DeepDB storage'),
                          ('paper_proxy_joblight_rdc_n10000000_b0p5', 'DeepDB'),
                          ('joblight_single_n10000000', 'DeepDB singles')]:
        if label in models:
            model = models[label]
            rows.append(dict(method=method, evidence='local_canonical_v3', label=label,
                             model_pickle_bytes=model['model_bytes'],
                             component_learning_seconds=model['component_learning_seconds'], **model['job_light']))
    path = FULL / 'results/postgres_job_light_verification.json'
    pg = load_json(path, {})
    csv = FULL / 'results/postgres_job_light.csv'
    if pg.get('status') == 'PASS' and pg.get('queries') == 70 and file_sha256(csv) == pg['result_sha256']:
        sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        sources[csv.relative_to(ROOT).as_posix()] = source_record(csv)
        rows.append(dict(method='PostgreSQL11.5', evidence='local_full_table_explain',
                         queries=70, **numeric_summary(checked_errors(csv_rows(csv)))))
    directory = FULL / 'mscn/table1_job_light_seed1'
    evaluation = load_json(directory / 'evaluation.json', {})
    if evaluation.get('status') == 'TABLE1_LOCAL_RERUN_COMPLETE' and evaluation.get('completed_epochs') == 100:
        for artifact in evaluation['artifacts']:
            path = directory / artifact['path']
            if file_sha256(path) != artifact['sha256']:
                raise ValueError('MSCN evaluation artifact changed')
            sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        path = directory / 'evaluation.json'
        sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        rows.append(dict(method='MSCN', evidence='local_official_100_epochs', queries=70,
                         model_parameter_bytes=evaluation['model_parameter_bytes'],
                         **numeric_summary(checked_errors(csv_rows(directory / 'predictions_job_light.csv')))))
    return rows


def draw_figures(directory, table, models, cpp, rebuilt=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.titleweight': 'bold', 'savefig.dpi': 180})
    blue, gold = '#2166AC', '#C58417'
    def finish(fig, name, note):
        fig.text(.02, .018, note, fontsize=9, color='#444444', va='bottom')
        fig.tight_layout(rect=(0, .08, 1, .98))
        fig.savefig(str(directory / (name + '.png')))
        plt.close(fig)
    fig, axes = plt.subplots(1, 4, figsize=(14, 4.3), sharey=True)
    for ax, method in zip(axes, ['DeepDB', 'DeepDB storage', 'PostgreSQL11.5', 'MSCN']):
        selected = [r for r in table if r['method'] == method]
        for record in selected:
            author = record['evidence'].startswith('author')
            ax.plot(range(4), [record[q] for q in QUANTILES], 'o--' if author else 's-',
                    color=gold if author else blue, label='Author' if author else 'Local')
        ax.set(title=method, yscale='log', xticks=range(4), xticklabels=['Median', '90th', '95th', 'Max'])
        ax.grid(axis='y', color='#DDDDDD', lw=.7); ax.legend(frameon=False)
    axes[0].set_ylabel('q-error (log scale)')
    finish(fig, 'table1_comparison', 'JOB-light70. Local DeepDB uses the recorded B*CBase proxy and seeded samples; author sample/configuration are not recovered.')
    for name, pairs, xlabel in [('sample_size', [(n, 'paper_proxy_public_scale_rdc_n10000000_b0p0' if n == 10000000
                                                        else 'public_scale_rdc_n%d_b0p0' % n)
                              for n in [1000, 10000, 100000, 1000000, 10000000]], 'Requested rows per RSPN'),
                                ('budget', [(b, 'paper_proxy_public_scale_rdc_n10000000_b%s' % str(b).replace('.', 'p'))
                              for b in [0., .5, 1., 2., 3.]], 'Additional budget B (CBase proxy)')]:
        valid = [(x, models[label]) for x, label in pairs if label in models]
        if not valid: continue
        fig, axes = plt.subplots(1, 2, figsize=(10.7, 4.2))
        x = [v[0] for v in valid]
        axes[0].plot(x, [v[1]['public_3to6']['median'] for v in valid], 'o-', color=blue)
        axes[1].plot(x, [v[1]['component_learning_seconds'] for v in valid], 's-', color=gold)
        axes[0].set_ylabel('Median q-error'); axes[1].set_ylabel('Component learning time (s)')
        for ax in axes:
            ax.set_xlabel(xlabel); ax.grid(axis='y', color='#DDDDDD', lw=.7)
            if name == 'sample_size': ax.set_xscale('log')
            else: ax.set_xticks([0, .5, 1, 2, 3])
        axes[0].set_title('Public 683-query accuracy'); axes[1].set_title('Learning time of unique components')
        finish(fig, name + '_study', 'Public683 queries (3--6 tables); not the unidentified paper200. Times exclude preparation and do not use cache assembly time.')
    label = 'paper_proxy_public_scale_rdc_n10000000_b0p5'
    if label in models:
        groups = models[label]['group_summaries']
        names = ['%d_%d_SPN' % (t, p) for t in [4, 5, 6] for p in range(1, 6)]
        fig, ax = plt.subplots(figsize=(11.5, 4.2))
        ax.plot(range(15), [groups[n]['median'] for n in names], 'o-', color=blue, label='DeepDB: ensemble threshold 0.15')
        alternative = models.get('threshold03_public_scale_rdc_n10000000_b0p5')
        if alternative:
            ax.plot(range(15), [alternative['group_summaries'][n]['median'] for n in names], '^--',
                    color=gold, label='DeepDB: ensemble threshold 0.3')
        if rebuilt:
            ax.plot(range(15), [rebuilt['groups'][n]['median'] for n in names], 's:',
                    color='#7C3A5E', label='MSCN: rebuilt consistent samples')
        ax.set(yscale='log', xticks=range(15), xticklabels=[n[:3].replace('_', '-') for n in names],
               xlabel='Tables--predicates', ylabel='Median q-error (log scale)', title='Public 413 queries in 15 generalization cells')
        ax.grid(axis='y', color='#DDDDDD', lw=.7)
        ax.legend(frameon=False)
        finish(fig, 'generalization', 'Public 413 queries; not author 200. MSCN: separate consistent-sample 100-epoch run. Published truths; local-truth metrics are separately retained.')
    if cpp:
        groups = cpp['groups']
        x = np.arange(len(groups)); fig, ax = plt.subplots(figsize=(11.5, 4.2))
        for offset, field, title, color in [(-.18, 'cpp_total_ms', 'Query total', blue),
                                           (.18, 'cpp_physical_native_ms', 'Full native call wall', gold)]:
            ax.bar(x + offset, [g['timing_ms'][field]['mean'] * 1000 for g in groups], .36, label=title,
                   color=color, hatch='///' if field == 'cpp_physical_native_ms' else None)
        ax.set(xticks=x, xticklabels=['%d-%d' % (g['tables'], g['predicates']) for g in groups],
               xlabel='Tables--predicates', ylabel='Mean latency (microseconds)', title='Generated C++ inference on the public 413 queries')
        ax.legend(frameon=False); ax.grid(axis='y', color='#DDDDDD', lw=.7); ax.set_axisbelow(True)
        finish(fig, 'cpp_latency', 'Canonical v3; 3 repetitions after warm-up, cold cache/query. Native wall includes every successful pybind call and conversions.\nShared Windows CPU; query total excludes SQL parsing. Public 413 queries; not author 200 or paper hardware equivalence.')
    cuts = [2019, 2011, 2009, 2004, 1991]
    temporal = [(i, models['temporal_joblight_rdc_n10000000_b0p0_year%d' % cut])
                for i, cut in enumerate(cuts) if 'temporal_joblight_rdc_n10000000_b0p0_year%d' % cut in models]
    if temporal:
        authors = {'median': [1.22, 1.28, 1.31, 1.34, 1.41], 'p90': [3.45, 3.17, 3.23, 3.60, 4.06],
                   'p95': [4.77, 4.30, 3.83, 4.07, 4.35]}
        fig, axes = plt.subplots(1, 3, figsize=(12.2, 4.2))
        for ax, field in zip(axes, ('median', 'p90', 'p95')):
            ax.plot(range(5), authors[field], 'o--', color=gold, label='Author')
            ax.plot([i for i, _ in temporal], [m['job_light'][field] for _, m in temporal], 's-', color=blue, label='Local')
            ax.set(xticks=range(5), xticklabels=list(map(str, cuts)), title=field, xlabel='Initial population: production year < cut')
            ax.grid(axis='y', color='#DDDDDD', lw=.7); ax.legend(frameon=False)
        axes[0].set_ylabel('q-error')
        finish(fig, 'temporal_updates', 'JOB-light70; B=0. Actual local update fractions vary by RSPN and differ from author percentages; see temporal_population_fractions.csv.')


def main():
    sources, models, pending = {}, {}, []
    expectations = [('rdc_n100000_b0p0', False), ('joblight_single_n10000000', False),
                    ('paper_proxy_joblight_rdc_n10000000_b0p5', False)]
    expectations += [('public_scale_rdc_n%d_b%s' % (n, '0p5' if n == 10000000 else '0p0'), True)
                     for n in [1000, 10000, 100000, 1000000, 10000000]]
    expectations += [('paper_proxy_public_scale_rdc_n10000000_b%s' % str(b).replace('.', 'p'), True)
                     for b in [0., .5, 1., 2., 3.]]
    expectations += [('temporal_joblight_rdc_n10000000_b0p0_year%d' % cut, False)
                     for cut in [2019, 2011, 2009, 2004, 1991]]
    expectations += [('paper_proxy_joblight_rdc_n%d_b0p0' % n, False)
                     for n in [1000, 10000, 1000000, 10000000]]
    expectations += [('threshold03_%s_rdc_n10000000_b%s' % (profile, str(b).replace('.', 'p')), profile == 'public_scale')
                     for profile in ['joblight', 'public_scale'] for b in [0., .5, 1., 2., 3.]]
    expectations += [('threshold03_public_scale_rdc_n%d_b0p0' % n, True) for n in [1000, 10000, 100000, 1000000]]
    expectations += [('relationship_n%d_b0p0' % n, False) for n in [100000, 10000000]]
    for label, scale in expectations:
        model = sealed_model(label, scale, sources)
        if model is None: pending.append(label)
        else: models[label] = model
    table = table1_rows(models, sources)
    cpp = None
    seal_path = FULL / 'cpp-v3/final_current_seal.json'
    if seal_path.exists():
        from full_cpp_v3_audit import audit as audit_cpp
        audited = audit_cpp()
        if audited['status'] != 'PASS_READ_ONLY_CURRENT_CANONICAL_NATIVE_AUDIT':
            raise ValueError('Current canonical C++ audit did not pass')
        pointer_path = FULL / 'cpp-v3/latest.json'
        verification_path = ROOT / load_json(pointer_path)['path']
        directory = verification_path.parent
        for path in [seal_path, pointer_path, verification_path,
                     ROOT / 'code/full_cpp_v3_audit.py', directory / 'all_753_repeated.jsonl',
                     directory / 'figure8_grouped_timings.json']:
            sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        cpp = load_json(directory / 'figure8_grouped_timings.json')
    rebuilt = None
    rebuilt_seal = FULL / 'mscn/rebuilt_seed1/results/final_seal.json'
    if rebuilt_seal.exists():
        from full_mscn_rebuilt_audit import verify as verify_rebuilt
        rebuilt = verify_rebuilt()
        for path in [rebuilt_seal, ROOT / 'code/full_mscn_rebuilt_audit.py']:
            sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        for group, _, _ in workload_files(True):
            path = rebuilt_seal.parent / (group + '.csv')
            sources[path.relative_to(ROOT).as_posix()] = source_record(path)
    code = source_record(Path(__file__))
    binding = dict(code=code, inputs=sorted(sources.values(), key=lambda r: r['path']),
                   pending=pending, protocol=PROTOCOL)
    output = FULL / 'figures' / ('cardinality_' + binding_hash(binding)[:16])
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        receipt = load_json(manifest_path)
        for item in receipt['artifacts']:
            path = ROOT / item['path']
            if file_sha256(path) != item['sha256']: raise ValueError('existing figure/table artifact changed')
        print('REUSED_SEALED_TABLES', output.relative_to(ROOT)); return
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / 'models.json', models)
    write_csv(output / 'table1.csv', table)
    rows, temporal, group_rows, variant_changes = [], [], [], []
    for model in models.values():
        common = {key: model[key] for key in ('label', 'profile', 'requested_samples', 'budget', 'components',
            'model_bytes', 'component_learning_seconds', 'component_sampling_seconds')}
        for scope in ('job_light', 'public_3to6', 'public_4to6'):
            if model[scope] is not None: rows.append(dict(common, workload=scope, **model[scope]))
        for group, stats in model['group_summaries'].items():
            group_rows.append(dict(label=model['label'], group=group, **stats))
        if model['historical_v2']:
            for group, values in model['historical_v2']['group_changes'].items():
                variant_changes.append(dict(label=model['label'], group=group, **values))
        for item in model['temporal_models']:
            temporal.append(dict(label=model['label'], tables=';'.join(item['spec']['tables']),
                **{k: v for k, v in item.items() if k != 'spec'}))
    write_csv(output / 'studies.csv', rows); write_csv(output / 'groups.csv', group_rows)
    if rebuilt:
        atomic_json(output / 'mscn_rebuilt_public_metrics.json', rebuilt)
    if variant_changes: write_csv(output / 'inference_variant_changes.csv', variant_changes)
    if temporal: write_csv(output / 'temporal_population_fractions.csv', temporal)
    draw_figures(output, table, models, cpp, rebuilt)
    artifacts = [source_record(p) for p in sorted(output.iterdir()) if p.is_file()]
    atomic_json(manifest_path, dict(status='PASS_AVAILABLE_EVIDENCE_ONLY', binding=binding_hash(binding),
        binding_details=binding, full_paper_complete=False, artifacts=artifacts,
        source_note='Author Table1 values are transcribed from the supplied paper, p999. Local values are independently recomputed from sealed predictions.',
        timing_note='Component learning time is the sum of original unique component learn_seconds; excludes preparation, sample generation, RDC selection and cached assembly.',
        missing_table1_baselines=[name for name in AUTHOR_TABLE1 if not any(r['method'] == name and not r['evidence'].startswith('author') for r in table)]))
    atomic_json(FULL / 'results/cardinality_tables_latest.json', dict(path=output.relative_to(ROOT).as_posix(),
        manifest_sha256=file_sha256(manifest_path), full_paper_complete=False))
    print('PAPER_TABLES_READY', output.relative_to(ROOT), 'pending', len(pending))


if __name__ == '__main__':
    main()
