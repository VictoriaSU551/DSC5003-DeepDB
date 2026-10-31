"""Recoverable RSPN components and RDC selection for full-paper experiments.

The sampler uses exact star-join population counts and modest oversampling to
avoid expanding the whole join in memory. This is recorded as a local sampling
adaptation, not claimed to recreate the authors' unseeded training sample.
"""
import argparse
import gc
import itertools
import json
import logging
import os
from pathlib import Path
import pickle
import random
import time

import networkx as nx
import numpy as np
import pandas as pd

from aqp_spn.aqp_spn import AQPSPN
from data_preparation.join_data_preparation import JoinDataPreparator
from ensemble_compilation.spn_ensemble import SPNEnsemble, read_ensemble
from ensemble_creation.rdc_based import generate_candidate_solution, candidate_rdc_sum_means, max_rdc
from full_common import ROOT, FULL, algorithm_seal, atomic_json, binding_hash, checkpoint_valid, file_sha256, load_json
from rspn.algorithms.validity.validity import is_valid
from schemas.imdb.schema import gen_job_light_imdb_schema
from full_prepare import schema_for_profile

HDF = FULL / 'prepared/hdf'
SELECTION = FULL / 'checkpoints/rdc_selection.json'
PAIRWISE = FULL / 'models/pairwise_rdc.pkl'
PROFILE = 'joblight'


def exact_star_size(parents, fanout_columns, mask=None):
    selected = parents if mask is None else parents.loc[mask]
    values = np.ones(len(selected), dtype=np.int64)
    for column in fanout_columns:
        counts = np.maximum(selected[column].values, 1).astype(np.int64)
        if len(values) and int(values.max()) * int(counts.max()) > np.iinfo(np.int64).max:
            values = values.astype(object)
        values = values * counts
    return sum(map(int, values))


def temporal_partition(frame, cut, null_value):
    years = frame['title.production_year']
    initial = (years < cut) | years.isna() | (years == null_value)
    if 'title.title_nn' in frame:
        initial |= frame['title.title_nn'] == 0
    return initial, ~initial


def atomic_ensemble(path, ensemble):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    ensemble.save(str(temporary))
    os.replace(str(temporary), str(path))


def schema_and_prep(sampled=False):
    schema = schema_for_profile(PROFILE)
    metadata = HDF / ('meta_data_sampled.pkl' if sampled else 'meta_data.pkl')
    return schema, JoinDataPreparator(str(metadata), schema, max_table_data=100000000)


def selection_binding():
    return dict(algorithm=algorithm_seal(), metadata=file_sha256(HDF / 'meta_data_sampled.pkl'),
                data=file_sha256(ROOT / 'data/manifest.json'), rdc_sample_rows=10000,
                rdc_max_intermediate_rows=100000, selection_threshold=0.15, seed=1)


def select_rdc(budget, random_solutions=10000):
    schema, prep = schema_and_prep(sampled=True)
    binding = selection_binding()
    checkpoint = load_json(SELECTION, {})
    if checkpoint_valid(checkpoint, binding):
        with PAIRWISE.open('rb') as source:
            attributes = pickle.load(source)
        maxima = {tuple(map(int, key.split(','))): value for key, value in checkpoint['maxima'].items()}
    else:
        np.random.seed(1)
        random.seed(1)
        graph = nx.Graph()
        indices = {table.table_name: i for i, table in enumerate(schema.tables)}
        inverse = {i: name for name, i in indices.items()}
        for edge in schema.relationships:
            graph.add_edge(indices[edge.start], indices[edge.end], relationship=edge.identifier)
        paths = dict(nx.all_pairs_shortest_path(graph))
        pairs = [(i, j, paths[i][j]) for i, j in itertools.combinations(range(len(indices)), 2)]
        pairs.sort(key=lambda x: (len(x[2]), x[0], x[1]))
        attributes, maxima = {}, {}
        for i, j, path in pairs:
            relationships = [graph[a][b]['relationship'] for a, b in zip(path, path[1:])]
            frame, meta_types, _ = prep.generate_join_sample(relationship_list=relationships,
                                                             max_intermediate_size=100000)
            value = float(max_rdc(schema, inverse[i], inverse[j], frame, meta_types, attributes,
                                  n_jobs=4, debug=False))
            maxima[(i, j)] = value if value > 0.15 else 0.0
            print('RDC', inverse[i], inverse[j], value, flush=True)
            del frame
            gc.collect()
        PAIRWISE.parent.mkdir(parents=True, exist_ok=True)
        temporary = PAIRWISE.with_suffix('.pkl.tmp')
        with temporary.open('wb') as target:
            pickle.dump(attributes, target, pickle.HIGHEST_PROTOCOL)
        os.replace(str(temporary), str(PAIRWISE))
        atomic_json(SELECTION, dict(status='PASS', binding=binding_hash(binding),
            maxima={','.join(map(str, key)): value for key, value in maxima.items()},
            artifacts=[dict(path=PAIRWISE.relative_to(ROOT).as_posix(), sha256=file_sha256(PAIRWISE))]))
    indices = {table.table_name: i for i, table in enumerate(schema.tables)}
    maximum_cost = budget * sum(prep.column_number(single_table=t.table_name) ** 2 for t in schema.tables)
    random.seed(1)
    candidates = {generate_candidate_solution(maxima, indices, prep, maximum_cost, schema, 3, .15)
                  for _ in range(random_solutions)}
    ranked = [(candidate, costs, candidate_rdc_sum_means(maxima, indices, candidate)) for candidate, costs in candidates]
    ranked.sort(key=lambda row: (-row[2], row[1], repr(sorted((sorted(a), sorted(b)) for a, b in row[0]))))
    selected = sorted(ranked[0][0], key=lambda row: (-len(row[1]), sorted(row[1])))
    serial = [dict(relationships=sorted(relationships), tables=sorted(tables)) for relationships, tables in selected]
    atomic_json(FULL / 'results' / ('rdc_selection_budget_%s.json' % str(budget).replace('.', 'p')),
                dict(budget=budget, cost_limit=maximum_cost, selected_cost=ranked[0][1],
                     score=ranked[0][2], models=serial, random_solutions=random_solutions,
                     note='Public code cost proxy, not an asserted conversion of paper time budget.'))
    return serial


def relation_specs(strategy, budget):
    schema, _ = schema_and_prep()
    if strategy == 'rdc':
        return select_rdc(budget)
    if strategy == 'single':
        return [dict(relationships=[], tables=[table.table_name]) for table in schema.tables]
    return [dict(relationships=[edge.identifier], tables=sorted([edge.start, edge.end])) for edge in schema.relationships]


def component(spec, samples, cut=None, oversampling=1.05):
    schema, prep = schema_and_prep()
    binding = dict(spec=spec, samples=samples, cut=cut, oversampling=oversampling, profile=PROFILE,
                   algorithm=algorithm_seal(), driver=file_sha256(__file__),
                   metadata=file_sha256(HDF / 'meta_data.pkl'), seed_protocol='component_hash_seed_v1',
                   population='exact_full_outer_star', null_year_policy='initial_partition')
    identifier = binding_hash(binding)
    checkpoint_path = FULL / 'checkpoints' / ('component_' + identifier + '.json')
    target = FULL / 'models/components' / (identifier + '.pkl')
    checkpoint = load_json(checkpoint_path, {})
    if checkpoint_valid(checkpoint, binding):
        print('Reused sealed component', identifier[:12], spec['tables'], flush=True)
        return read_ensemble(str(target)).spns[0], checkpoint
    np.random.seed(int(identifier[:8], 16) % (2 ** 31 - 1))
    random.seed(int(identifier[:8], 16) % (2 ** 31 - 1))
    started = time.perf_counter()
    title = pd.read_hdf(HDF / 'title.hdf')
    if spec['relationships']:
        columns = [schema.relationship_dictionary[edge].end + '.' +
                   schema.relationship_dictionary[edge].multiplier_attribute_name for edge in spec['relationships']]
        population = exact_star_size(title, columns)
        if cut is not None:
            null_index = prep.table_meta_data['title']['relevant_attributes_full'].index('title.production_year')
            null_year = prep.table_meta_data['title']['null_values_column'][null_index]
            initial_mask, _ = temporal_partition(title, cut, null_year)
            initial_population = exact_star_size(title, columns, initial_mask)
    else:
        population = int(prep.table_meta_data[spec['tables'][0]]['length'])
        if cut is not None:
            raise ValueError('Temporal experiment requires a title-containing relationship model')
    del title
    gc.collect()
    rate = min(samples * oversampling / population, 1.0)
    sample_options = dict(relationship_list=spec['relationships']) if spec['relationships'] else dict(single_table=spec['tables'][0])
    frame, meta_types, null_values = prep.generate_join_sample(sample_rate=rate, **sample_options)
    if len(frame) > samples:
        frame = frame.sample(samples)
    if len(frame) < 100:
        raise ValueError('Training sample too small')
    sample_seconds = time.perf_counter() - started
    sample_rows = len(frame)
    if cut is not None:
        initial_mask, update_mask = temporal_partition(frame, cut, null_year)
        initial_frame = frame.loc[initial_mask]
        updates = frame.loc[update_mask].values
    else:
        initial_frame, updates = frame, np.empty((0, len(frame.columns)))
        initial_population = population
    model = AQPSPN(meta_types, null_values, initial_population, schema, spec['relationships'],
                   full_sample_size=len(initial_frame), table_set=set(spec['tables']),
                   column_names=list(frame.columns), table_meta_data=prep.table_meta_data)
    learning_start = time.perf_counter()
    model.learn(initial_frame.values, rdc_threshold=.3, min_instances_slice=.01 * len(initial_frame))
    learn_seconds = time.perf_counter() - learning_start
    validation = is_valid(model.mspn, check_ids=True, check_cluster_centers=True)
    assert validation[0], validation[1]
    before = SPNEnsemble(schema, [model])
    if cut is not None:
        initial_target = target.with_name(identifier + '_before.pkl')
        atomic_ensemble(initial_target, before)
    del frame, initial_frame
    gc.collect()
    update_start = time.perf_counter()
    for index, row in enumerate(updates):
        model.add_dataset(row)
        if (index + 1) % 100000 == 0:
            print('Incremental rows', index + 1, '/', len(updates), flush=True)
    # add_dataset counts inserted sample rows; the model normalizer is a full
    # database join population, so reset it to the independently counted size.
    model.full_join_size = population
    update_seconds = time.perf_counter() - update_start
    validation = is_valid(model.mspn, check_ids=True, check_cluster_centers=True)
    assert validation[0], validation[1]
    atomic_ensemble(target, SPNEnsemble(schema, [model]))
    checkpoint = dict(status='PASS', binding=binding_hash(binding), spec=spec,
        requested_samples=samples, actual_samples=sample_rows,
        incremental_samples=len(updates), full_join_size=population, initial_full_join_size=initial_population,
        sample_seconds=sample_seconds, learn_seconds=learn_seconds, update_seconds=update_seconds,
        seed=int(identifier[:8], 16) % (2 ** 31 - 1),
        artifacts=[dict(path=target.relative_to(ROOT).as_posix(), sha256=file_sha256(target))])
    if cut is not None:
        checkpoint['artifacts'].append(dict(path=initial_target.relative_to(ROOT).as_posix(), sha256=file_sha256(initial_target)))
    atomic_json(checkpoint_path, checkpoint)
    print('Saved verified component', identifier[:12], sample_rows, 'population', population, flush=True)
    return model, checkpoint


def train(strategy, samples, budget=0.0, cut=None):
    label = '%s_n%d_b%s' % (strategy, samples, str(budget).replace('.', 'p'))
    if PROFILE != 'joblight':
        label = PROFILE.replace('-', '_') + '_' + label
    if cut is not None:
        label += '_year%d' % cut
    specs = relation_specs(strategy, budget)
    schema, _ = schema_and_prep()
    ensemble = SPNEnsemble(schema)
    receipts = []
    for spec in specs:
        model, receipt = component(spec, samples, cut)
        ensemble.add_spn(model)
        receipts.append(receipt)
    target = FULL / 'models' / label / 'ensemble.pkl'
    atomic_ensemble(target, ensemble)
    atomic_json(FULL / 'results' / (label + '_training.json'), dict(
        status='PASS', label=label, strategy=strategy, requested_samples=samples, budget=budget, cut=cut, profile=PROFILE,
        source_version='public_655ada13_with_recorded_local_adaptations',
        sampling='exact population Bernoulli parent sampling, oversampling 1.05, then uniform row reduction',
        population_normalizer='full outer join, not public candidate_evaluation inner join normalizer',
        models=receipts, model_path=target.relative_to(ROOT).as_posix(), model_sha256=file_sha256(target),
        pairwise_rdc_path=PAIRWISE.relative_to(ROOT).as_posix() if strategy == 'rdc' else None))
    print('ENSEMBLE_READY', label, str(target), flush=True)
    return target


def main():
    global PROFILE, HDF, SELECTION, PAIRWISE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy', choices=['relationship', 'single', 'rdc'], default='rdc')
    parser.add_argument('--samples', type=int, default=10000000)
    parser.add_argument('--budget', type=float, default=.5)
    parser.add_argument('--year-cut', type=int)
    parser.add_argument('--profile', choices=['joblight', 'public-scale'], default='joblight')
    args = parser.parse_args()
    PROFILE = args.profile
    if PROFILE != 'joblight':
        HDF = FULL / 'prepared' / PROFILE / 'hdf'
        SELECTION = FULL / 'checkpoints' / (PROFILE + '_rdc_selection.json')
        PAIRWISE = FULL / 'models' / PROFILE / 'pairwise_rdc.pkl'
    if args.samples < 100 or args.budget < 0:
        parser.error('Invalid samples or budget')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    train(args.strategy, args.samples, args.budget, args.year_cut)


if __name__ == '__main__':
    main()
