"""Paper B*CBase cost-proxy normalization, alongside the released-code factor.

The paper also estimates relative training cost by columns squared times rows.
With a common requested row count, rows cancel. The released driver instead
normalizes its factor to all single-table costs. Both variants remain explicit.
"""
import argparse
import gc
import json
from pathlib import Path

from ensemble_compilation.spn_ensemble import SPNEnsemble
from ensemble_creation.rdc_based import learning_cost
from full_common import ROOT, FULL, atomic_json, file_sha256, load_json
from full_evaluation import evaluate, workload_files
import full_training as training


def code_factor_for_base_budget(factor, base_cost, single_cost):
    if factor < 0 or base_cost <= 0 or single_cost <= 0:
        raise ValueError('budget factor must be nonnegative and both costs positive')
    return factor * base_cost / single_cost


def same_ordered_components(a, b):
    def components(record):
        return [(model['binding'], [artifact['sha256'] for artifact in model['artifacts']])
                for model in record['models']]
    return a.get('profile') == b.get('profile') and components(a) == components(b)


def equivalent_evaluation(receipt):
    import pandas as pd
    workloads = {group: (query, truth) for group, query, truth in workload_files()}
    for path in sorted((FULL / 'results').glob('*_training.json')):
        other = load_json(path)
        if not other or 'models' not in other or not same_ordered_components(receipt, other):
            continue
        evaluation_path = path.with_name(other['label'] + '_evaluation.json')
        previous = load_json(evaluation_path)
        if previous is None or previous.get('status') != 'PASS' or previous.get('queries') != 753:
            continue
        # Reuse only original per-query results with unmodified recorded CSVs.
        source_label = previous.get('reused_from_label', other['label'])
        source = load_json(FULL / 'results' / (source_label + '_evaluation.json'))
        if source is None or source.get('reused_from_label'):
            continue
        valid = True
        for group, value in source['groups'].items():
            csv_path = FULL / 'results' / source_label / (group + '.csv')
            if group not in workloads or not csv_path.exists() or file_sha256(csv_path) != value['csv_sha256']:
                valid = False
                break
            query_path, truth_path = workloads[group]
            actual = pd.read_csv(csv_path)
            truth = pd.read_csv(truth_path)
            queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
            if (actual['query'].tolist() != queries
                    or actual.cardinality_true.tolist() != truth.cardinality_true.tolist()):
                valid = False
                break
        if valid and set(source['groups']) == set(workloads):
            return source_label, source
    return None


def run(samples, factors):
    training.PROFILE = 'public-scale'
    training.HDF = FULL / 'prepared/public-scale/hdf'
    training.SELECTION = FULL / 'checkpoints/public-scale_rdc_selection.json'
    training.PAIRWISE = FULL / 'models/public-scale/pairwise_rdc.pkl'
    schema, prep = training.schema_and_prep()
    base_specs = training.select_rdc(0.)
    base_cost = sum(learning_cost(prep, [spec['relationships']]) if spec['relationships'] else
                    learning_cost(prep, None, single_table=spec['tables'][0]) for spec in base_specs)
    single_cost = sum(prep.column_number(single_table=table.table_name) ** 2 for table in schema.tables)
    for factor in factors:
        effective = code_factor_for_base_budget(factor, base_cost, single_cost)
        specs = training.select_rdc(effective)
        label = 'paper_proxy_public_scale_rdc_n%d_b%s' % (samples, str(float(factor)).replace('.', 'p'))
        receipts, ensemble = [], SPNEnsemble(schema)
        for spec in specs:
            model, receipt = training.component(spec, samples)
            receipts.append(receipt)
            ensemble.add_spn(model)
            gc.collect()
        target = FULL / 'models' / label / 'ensemble.pkl'
        existing = load_json(FULL / 'results' / (label + '_training.json'))
        current = dict(status='PASS', label=label, strategy='rdc', requested_samples=samples,
                       budget=float(factor), cut=None, profile='public-scale', models=receipts,
                       budget_semantics='paper B times base ensemble cost proxy; equal requested row counts',
                       base_cost_columns_squared=base_cost, single_cost_columns_squared=single_cost,
                       released_code_equivalent_factor=effective,
                       model_path=target.relative_to(ROOT).as_posix(),
                       pairwise_rdc_path=training.PAIRWISE.relative_to(ROOT).as_posix(),
                       driver_sha256=file_sha256(__file__),
                       sampling='component sampler: exact population Bernoulli parent sampling, oversampling1.05, row reduction',
                       population_normalizer='exact full outer star size')
        if (existing and same_ordered_components(existing, current) and target.exists()
                and file_sha256(target) == existing['model_sha256']):
            current['model_sha256'] = existing['model_sha256']
        else:
            training.atomic_ensemble(target, ensemble)
            current['model_sha256'] = file_sha256(target)
        atomic_json(FULL / 'results' / (label + '_training.json'), current)
        alias = equivalent_evaluation(current)
        if alias:
            source_label, result = alias
            result = dict(result, label=label, model_sha256=current['model_sha256'],
                          reused_from_label=source_label,
                          reuse_proof='same profile and identically ordered sealed component bindings and artifact hashes',
                          source_evaluation_sha256=file_sha256(FULL / 'results' / (source_label + '_evaluation.json')))
            atomic_json(FULL / 'results' / (label + '_evaluation.json'), result)
            print('REUSED_IDENTICAL_MODEL_PREDICTIONS', label, source_label, flush=True)
        else:
            evaluate(label)
        print('PAPER_PROXY_BUDGET_READY', label, effective, flush=True)
        del ensemble
        gc.collect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=10000000)
    parser.add_argument('--budgets', type=float, nargs='+', default=[0., .5, 1., 2., 3.])
    args = parser.parse_args()
    if args.samples < 100:
        parser.error('samples must be at least100')
    run(args.samples, args.budgets)


if __name__ == '__main__':
    main()
