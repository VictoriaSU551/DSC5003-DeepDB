"""Separate paper-described0.3 ensemble threshold from released default0.15.

The public CLI's RDC argument controls learning within each RSPN; its ensemble
selection function has a separate0.15 default. Paper Section3.3 says to use the
standard SPN threshold for inter-table independence. This module records that
interpretation separately, retaining every previously trained component.
"""
import argparse
import gc
import pickle
import random

from ensemble_compilation.spn_ensemble import SPNEnsemble
from ensemble_creation.rdc_based import generate_candidate_solution, candidate_rdc_sum_means, learning_cost
from full_common import ROOT, FULL, atomic_json, file_sha256, load_json, checkpoint_valid
from full_evaluation_v2 import evaluate
from full_joblight_variants import find_shared_component
import full_training as training


def thresholded_pairs(values, threshold):
    if threshold < .15: raise ValueError('cached maxima below0.15 were not retained')
    return {pair: value if value > threshold else 0. for pair, value in values.items()}


def choose(schema, prep, maxima, threshold, budget):
    indices = {table.table_name: i for i, table in enumerate(schema.tables)}
    def search(limit, count):
        random.seed(1)
        candidates = {generate_candidate_solution(maxima, indices, prep, limit, schema, 3, threshold)
                      for _ in range(count)}
        ranked = [(candidate, cost, candidate_rdc_sum_means(maxima, indices, candidate))
                  for candidate, cost in candidates]
        ranked.sort(key=lambda row: (-row[2], row[1], repr(sorted((sorted(a), sorted(b)) for a, b in row[0]))))
        return ranked[0]
    base, _, _ = search(0., 1)
    base_cost = sum(learning_cost(prep, [list(rel)]) if rel else
                    learning_cost(prep, None, single_table=list(tables)[0]) for rel, tables in base)
    selected, cost, score = search(budget * base_cost, 10000)
    ordered = sorted(selected, key=lambda row: (-len(row[1]), sorted(row[1])))
    return dict(models=[dict(relationships=sorted(rel), tables=sorted(tables)) for rel, tables in ordered],
                base_cost_columns_squared=base_cost, additional_cost_columns_squared=cost,
                additional_cost_limit=budget * base_cost, score=score)


def run(profile, samples, budgets, train=False):
    training.PROFILE = profile
    if profile == 'public-scale':
        training.HDF = FULL / 'prepared/public-scale/hdf'
        training.SELECTION = FULL / 'checkpoints/public-scale_rdc_selection.json'
        training.PAIRWISE = FULL / 'models/public-scale/pairwise_rdc.pkl'
    checkpoint = load_json(training.SELECTION)
    if not checkpoint_valid(checkpoint, training.selection_binding()):
        raise ValueError('existing pairwise RDC source is not valid')
    raw = {tuple(map(int, pair.split(','))): value for pair, value in checkpoint['maxima'].items()}
    maxima = thresholded_pairs(raw, .3)
    schema, prep = training.schema_and_prep(sampled=True)
    if profile == 'joblight':
        _, full_prep = training.schema_and_prep()
        with (FULL / 'prepared/public-scale/hdf/meta_data.pkl').open('rb') as stream:
            public_metadata = pickle.load(stream)
    else: public_metadata = None
    for budget in budgets:
        selection = choose(schema, prep, maxima, .3, budget)
        label = 'threshold03_%s_rdc_n%d_b%s' % (profile.replace('-', '_'), samples, str(float(budget)).replace('.', 'p'))
        record = dict(status='SELECTION_ONLY', label=label, profile=profile,
                      strategy='rdc', requested_samples=samples, budget=budget, cut=None,
                      ensemble_rdc_threshold=.3, intra_rspn_rdc_threshold=.3,
                      source_default_ensemble_threshold=.15, scientific_scope='separate Section3.3 threshold interpretation',
                      source_selection_sha256=file_sha256(training.SELECTION), driver_sha256=file_sha256(__file__),
                      pairwise_rdc_path=training.PAIRWISE.relative_to(ROOT).as_posix(), **selection)
        atomic_json(FULL / 'results' / (label + '_selection.json'), record)
        print('THRESHOLD_SELECTION', label, selection, flush=True)
        if not train: continue
        ensemble, receipts = SPNEnsemble(schema), []
        for spec in selection['models']:
            reused = find_shared_component(spec, samples, full_prep.table_meta_data, public_metadata) if profile == 'joblight' else None
            model, receipt = reused if reused is not None else training.component(spec, samples)
            ensemble.add_spn(model); receipts.append(receipt); gc.collect()
        target = FULL / 'models' / label / 'ensemble.pkl'
        previous = load_json(FULL / 'results' / (label + '_training.json'), {})
        if not (target.exists() and previous.get('model_sha256') == file_sha256(target)
                and [c['binding'] for c in previous['models']] == [c['binding'] for c in receipts]):
            training.atomic_ensemble(target, ensemble)
        record.update(status='PASS', models=receipts, selected_specs=selection['models'],
                      model_path=target.relative_to(ROOT).as_posix(), model_sha256=file_sha256(target))
        atomic_json(FULL / 'results' / (label + '_training.json'), record)
        evaluate(label, include_scale=profile == 'public-scale')
        del ensemble; gc.collect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['joblight', 'public-scale'], default='joblight')
    parser.add_argument('--samples', type=int, default=10000000)
    parser.add_argument('--budgets', type=float, nargs='+', default=[0., .5, 1., 2., 3.])
    parser.add_argument('--train', action='store_true')
    args = parser.parse_args()
    if args.samples < 100 or any(b < 0 for b in args.budgets): parser.error('invalid sample count/budget')
    run(args.profile, args.samples, args.budgets, args.train)
