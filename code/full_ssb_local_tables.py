"""Derived LOCAL SF500 figures; author-population mismatch remains explicit."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    from full_ssb_local_replay import verify
    return dict(stage='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI',scope='LOCAL_SSB_SF500',
        cap=1000000,training_rows=dict(lineorder=1000000,dwdate=2556,customer=1000000,part=1000000,supplier=1000000),
        verify=verify,result='ssb_local_sf500_model_aqp_ci.json',prefix='aqp_ssb_local_sf500_',
        pointer='ssb_local_sf500_tables_latest.json',policy_applied=False,
        helpers=['code/full_ssb_local_replay.py','code/full_ssb_local_model.py'])


def validate_formal_report(report, sample_rows, config=None):
    config=configuration() if config is None else config
    if (report['stage'] != config['stage']
            or report['scope'] != config['scope']
            or report['author_reproduction_complete'] is not False
            or report['author_different_groups'] != 1713
            or report['spn_count'] != 5 or report['population_rows'] != 3000028242
            or sample_rows != 9996946 or report['actual_sample_rows'] != sample_rows
            or report['full_paper_reproduction_complete'] is not False
            or report['author_population_row_count_and_13_truths_match'] is not False
            or report['author_full_row_byte_identity_proven'] is not False
            or report['point_query_errors'] != 0 or report['ci_query_errors'] != 0):
        raise ValueError('complete LOCAL SF500 scope, retained author mismatch and successful model required')
    tables = report['training_tables']
    expected = config['training_rows']
    if (len(tables) != 5 or len({t['table'] for t in tables}) != 5
            or {t['table']:t['actual_training_rows'] for t in tables} != expected):
        raise ValueError('complete five-model original training budget required')


def draw_local(directory, queries, groups, actual_n, model_cap=1000000):
    """Both PNGs visibly retain the population boundary when shared alone."""
    import math
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
        'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
    warning = 'LOCAL population: 1,713 of 2,059 author truth groups differ; not author-population reproduction.'
    fig, ax = plt.subplots(figsize=(12,5.3))
    values=[]
    for offset, field, label, color, marker in [(-.12,'model_mean_relative_error_with_missing_penalty',
        'DeepDB (cap '+str(model_cap//1000000)+'M/table)','#2166AC','o'),(.12,'sample_mean_relative_error_with_missing_penalty',
        'Uniform reference ('+format(actual_n,',')+' fact rows)','#C58417','^')]:
        points=[(i,100*q[field]) for i,q in enumerate(queries) if q[field] is not None]
        values.extend(v for _,v in points)
        ax.scatter([i+offset for i,_ in points],[v for _,v in points],label=label,color=color,marker=marker,s=45)
    ax.set_yscale('log' if values and min(values)>0 else 'symlog',
        **({} if values and min(values)>0 else {'linthresh':1e-6}))
    ax.set(xticks=np.arange(13),xticklabels=[q['query'] for q in queries],
        ylabel='Mean relative error across local truth groups (%)',
        title='LOCAL SSB SF500: exact 3,000,028,242-row generated population')
    ax.legend(frameon=False,fontsize=9);ax.grid(axis='y',color='#DDDDDD',lw=.7)
    fig.text(.02,.02,warning+'\nModel uses original n/p; reference uses exact N. Different sample budgets; not a timed baseline.\n'
        'Missing groups incur 100% error; invalid points suppress query means. All groups remain in CSV.',fontsize=9)
    fig.tight_layout(rect=(0,.15,1,.98));fig.savefig(str(directory/'ssb_relative_error.png'));plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,6.8));positive=[]
    for family,color,marker in [('S1','#2166AC','o'),('S2','#C58417','s'),('S3','#7C8330','^'),('S4','#7C3A5E','D')]:
        pairs=[(r['reference_relative_half_width'],r['model_relative_half_width']) for r in groups
            if r['truth'] is not None and r['ci_eligible'] and r['query'].startswith(family)]
        points=[(a,b) for a,b in pairs if a is not None and b is not None
            and min(a,b)>0 and math.isfinite(a) and math.isfinite(b)]
        positive.extend(v for pair in points for v in pair)
        ax.scatter([100*a for a,_ in points],[100*b for _,b in points],label=family,color=color,marker=marker,s=28,alpha=.75)
    if positive:
        low,high=min(positive)*80,max(positive)*120
        ax.plot([low,high],[low,high],'--',color='#777777',lw=1)
        ax.set(xscale='log',yscale='log',xlim=(low,high),ylim=(low,high))
    ax.set(xlabel='Independent local sample reference half width (%)',
        ylabel='Original RSPN half width (%)',title='LOCAL SSB: central 90% intervals, one realized sample')
    ax.legend(frameon=False);ax.grid(color='#DDDDDD',lw=.6)
    budget_note=('Model cap is 1M/table; paper Figure 11 uses 10M training.' if model_cap==1000000 else
        'Figure 11 cap policy: 10M/table; actual fact rows 9,996,946. Author population still differs.')
    fig.text(.02,.02,warning+'\nFact sample joins full dimensions; count<10 excluded. Only positive finite widths plotted.\n'
        +budget_note+' S4 differences may violate independence.\n'
        'Bernoulli reference; not repeated-sampling calibration.',fontsize=8)
    fig.tight_layout(rect=(0,.14,1,.98));fig.savefig(str(directory/'ssb_ci_half_width.png'));plt.close(fig)


def main(config=None):
    from full_common import FULL, atomic_json, binding_hash, file_sha256, load_json
    from full_aqp_tables import artifact, csv_table
    from full_ssb_local_replay import validate_query_identities, QUERY_NAMES
    from full_ssb_tables import summarize, require_existing_figures, OUTPUT_NAMES
    config=configuration() if config is None else config
    scope=config['scope']
    accepted = config['verify']()  # No fallback execution; missing evidence must fail.
    source = accepted['source_snapshot']['published_result']
    path = ROOT/source['path']
    if path.resolve() != (FULL/'results'/config['result']).resolve():
        raise ValueError('separate LOCAL model result path required')
    payload = path.read_bytes()
    if len(payload) != source['bytes'] or hashlib.sha256(payload).hexdigest() != source['sha256']:
        raise ValueError('LOCAL model result changed since strict replay acceptance')
    report = json.loads(payload)
    actual_n = accepted['source_snapshot']['sample_rows']
    validate_formal_report(report, actual_n, config)
    validate_query_identities(report['queries'], (ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines(), QUERY_NAMES)
    helpers = [Path(__file__),ROOT/'code/full_ssb_tables.py',ROOT/'code/full_aqp_tables.py']+[ROOT/p for p in config['helpers']]
    binding = dict(readonly_acceptance=accepted, sources=[source]+[artifact(p) for p in helpers],
                   full_paper_complete=False, scope=scope,model_training_cap_per_table=config['cap'],
                   author_reproduction_complete=False, author_different_groups=1713)
    directory = FULL/'figures'/(config['prefix']+binding_hash(binding)[:16])
    manifest_path = directory/'manifest.json'
    pointer = FULL/'results'/config['pointer']
    def publish_pointer():
        atomic_json(pointer, dict(path=directory.relative_to(ROOT).as_posix(),
            manifest_sha256=file_sha256(manifest_path), full_paper_complete=False,
            scope=scope, author_reproduction_complete=False, author_different_groups=1713))
    if manifest_path.exists():
        require_existing_figures(load_json(manifest_path), directory, binding)
        publish_pointer()
        print('REUSED_SEALED_LOCAL_SSB_TABLES', directory.relative_to(ROOT))
        return
    queries, groups = [], []
    for query in report['queries']:
        rows, summary = summarize(query, report['population_rows'], actual_n)
        for row in rows+[summary]:
            row.update(scope=scope, model_training_cap_per_table=config['cap'],author_different_groups=1713,
                       author_reproduction_complete=False)
        queries.append(summary); groups.extend(rows)
    directory.mkdir(parents=True, exist_ok=False)
    csv_table(directory/'query_summary.csv', queries)
    csv_table(directory/'all_groups.csv', groups)
    training_rows=[dict({key:t[key] for key in
        ('table','actual_training_rows','full_join_estimate','learning_seconds')},
        scope=scope,model_training_cap_per_table=config['cap'],author_different_groups=1713,author_reproduction_complete=False)
        for t in report['training_tables']]
    csv_table(directory/'training_tables.csv',training_rows)
    draw_local(directory, queries, groups, actual_n, config['cap'])
    outputs = [directory/name for name in sorted(OUTPUT_NAMES)]
    # Bind the existing scientific files; this entry only computes derived views.
    for entry in binding['sources']:
        if file_sha256(ROOT/entry['path']) != entry['sha256']:
            raise ValueError('LOCAL derived source changed during rendering')
    atomic_json(manifest_path, dict(status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES',
        binding=binding_hash(binding), binding_details=binding,
        scope=scope, author_reproduction_complete=False, author_different_groups=1713,
        artifacts=[artifact(p) for p in outputs], full_paper_complete=False,
        group_truth_rows=sum(q['truth_groups'] for q in queries),
        training_rows_per_table={t['table']:t['actual_training_rows'] for t in report['training_tables']},
        confidence_fact_sample_rows=actual_n, normalizer_scope=(config['normalizer_scope']
            if 'normalizer_scope' in config else report['normalizer_scope']),
        ci_scope=report['ci_scope'], author_full_row_byte_identity_proven=False,
        paper_figure11_training_budget_reproduced=False,model_training_cap_per_table=config['cap'],
        paper_figure11_training_budget_policy_applied=config['policy_applied'],exact10000000_fact_training_rows_claimed=False,
        missing_group_policy='Missing truth groups incur100pct error; invalid predictions suppress the '
            'query mean. Extras, zero truths, missing/nonfinite intervals and CI exclusions remain explicit.'))
    publish_pointer()
    print('LOCAL_SSB_TABLES_READY', directory.relative_to(ROOT))


if __name__ == '__main__':
    main()
