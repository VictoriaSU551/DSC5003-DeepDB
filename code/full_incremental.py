"""Fixed-structure RSPN updates with sealed samples and recoverable batches.

The vectorized parameter pooling is checked against the original scalar update;
it leaves routing prototypes and tree structure unchanged. Table 2 variants use
one fixed full-data sample per base model, then partition it by production year.
"""
import argparse
import copy
from contextlib import contextmanager
import gc
import json
import logging
import os
from pathlib import Path
import pickle
import random
import time

import numpy as np
import pandas as pd
from scipy.spatial import distance
from spn.structure.Base import Product, get_nodes_by_type
from spn.structure.StatisticalTypes import MetaType

from aqp_spn.aqp_spn import AQPSPN
from ensemble_compilation.spn_ensemble import SPNEnsemble, read_ensemble
from full_common import ROOT, FULL, algorithm_seal, atomic_json, binding_hash, file_sha256, load_json
from full_training import atomic_ensemble, exact_star_size, schema_and_prep
from rspn.algorithms.validity.validity import is_valid
from rspn.structure.base import Sum
from rspn.structure.leaves import Categorical, IdentityNumericLeaf
from rspn.updates.top_down_updates import cluster_center_update_dataset

CUTS = (2019, 2011, 2009, 2004, 1991)
SAMPLES = ROOT / 'data/imdb/temporal_samples'


def nearest_children(rows, centers):
    centers = np.asarray(centers, dtype=float)
    distances = distance.cdist(rows, centers, metric='euclidean')
    chosen = distances.argmin(axis=1)
    if len(centers) > 1:
        best_two = np.partition(distances, 1, axis=1)[:, :2]
        ambiguous = np.isclose(best_two[:, 0], best_two[:, 1], rtol=1e-12, atol=1e-12)
        # Reproduce the author's strict '<' and scipy.euclidean at a routing tie,
        # including cases where two distance algorithms differ by one ulp.
        for i in np.flatnonzero(ambiguous):
            chosen[i] = min(range(len(centers)), key=lambda j: distance.euclidean(centers[j], rows[i]))
    return chosen


def batch_update(node, rows):
    rows = np.asarray(rows)
    if not len(rows):
        return
    if not np.isfinite(rows).all():
        raise ValueError('updates must use the prepared finite NULL sentinels')
    count = len(rows)
    if isinstance(node, Categorical):
        values = rows[:, node.scope[0]]
        indices = values.astype(np.int64)
        if np.any(values != indices) or indices.min() < 0 or indices.max() >= len(node.p):
            raise ValueError('categorical update outside the sealed metadata domain')
        histogram = node.p * node.cardinality + np.bincount(indices, minlength=len(node.p))
        node.cardinality += count
        node.p = histogram / histogram.sum()
    elif isinstance(node, IdentityNumericLeaf):
        values, counts = np.unique(rows[:, node.scope[0]], return_counts=True)
        domain = np.union1d(node.unique_vals, values)
        histogram = np.zeros(len(domain))
        histogram[np.searchsorted(domain, node.unique_vals)] = node.return_histogram() * node.cardinality
        histogram[np.searchsorted(domain, values)] += counts
        node.unique_vals = domain
        node.update_unique_vals_idx()
        node.cardinality += count
        node.update_from_new_probabilities(histogram / histogram.sum())
    elif isinstance(node, Sum):
        selected = nearest_children(rows[:, node.scope], node.cluster_centers)
        counts = np.bincount(selected, minlength=len(node.children))
        node.weights = ((np.asarray(node.weights) * node.cardinality + counts) /
                        (node.cardinality + count)).tolist()
        for i, child in enumerate(node.children):
            if counts[i]:
                batch_update(child, rows[selected == i])
        node.cardinality += count
    elif isinstance(node, Product):
        for child in node.children:
            batch_update(child, rows)
        node.cardinality += count
    else:
        raise TypeError('unsupported update node: ' + str(type(node)))


def partition_years(years, cut, null_value):
    years = np.asarray(years)
    initial = (years < cut) | ~np.isfinite(years) | (years == null_value)
    return initial, ~initial


def require_sample_size(actual, requested, population):
    target = min(requested, population)
    if actual != target:
        raise ValueError('sample target not met: actual=%d required=%d' % (actual, target))
    return target


def dependency_seal(spec):
    helpers = ['full_training.py', 'full_prepare.py', 'full_common.py']
    tables = set(spec['tables']) | {'title'}
    return dict(helpers={name: file_sha256(ROOT / 'code' / name) for name in helpers},
                raw_manifest=file_sha256(ROOT / 'data/manifest.json'),
                prepared_hdfs={table: file_sha256(FULL / 'prepared/hdf' / (table + '.hdf'))
                               for table in sorted(tables)})


def scalar_update_gate(model, rows):
    expected, pooled = copy.deepcopy(model.mspn), copy.deepcopy(model.mspn)
    for row in rows:
        cluster_center_update_dataset(expected, row)
    batch_update(pooled, rows)
    max_absolute = 0.
    for a, b in zip(get_nodes_by_type(expected), get_nodes_by_type(pooled)):
        if type(a) is not type(b) or a.scope != b.scope or a.cardinality != b.cardinality:
            raise ValueError('pooled/scalar structure or cardinality mismatch')
        for attr in ['weights', 'p', 'unique_vals', 'prob_sum', 'mean', 'inverted_mean',
                     'square_mean', 'inverted_square_mean', 'null_value_prob']:
            if hasattr(a, attr):
                x, y = np.asarray(getattr(a, attr)), np.asarray(getattr(b, attr))
                np.testing.assert_allclose(x, y, rtol=1e-8, atol=1e-10)
                finite = np.isfinite(x) & np.isfinite(y)
                if np.any(finite):
                    max_absolute = max(max_absolute, float(np.max(np.abs(x[finite] - y[finite]))))
    return dict(status='PASS', checked_rows=len(rows), nodes=len(get_nodes_by_type(expected)),
                rtol=1e-8, atol=1e-10, max_absolute_parameter_difference=max_absolute,
                reference='unmodified author cluster_center_update_dataset')


def save_update_checkpoint(directory, model, completed, binding, history):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ('model_%010d.pkl' % completed)
    temp = target.with_suffix('.pkl.tmp')
    with temp.open('wb') as stream:
        pickle.dump(model, stream, pickle.HIGHEST_PROTOCOL)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temp), str(target))
    record = dict(binding=binding_hash(binding), completed_rows=completed, history=history,
                  model_file=target.name, model_sha256=file_sha256(target))
    record['receipt_sha256'] = binding_hash(record)
    atomic_json(directory / 'checkpoint.json', record)
    return record


def load_update_checkpoint(directory, binding):
    directory = Path(directory).resolve()
    record = load_json(directory / 'checkpoint.json')
    if record is None:
        return None
    seal = record.pop('receipt_sha256', None)
    if seal != binding_hash(record):
        raise ValueError('checkpoint receipt hash mismatch')
    if record['binding'] != binding_hash(binding):
        raise ValueError('checkpoint binding mismatch')
    model_path = (directory / record['model_file']).resolve()
    if directory != model_path.parent or file_sha256(model_path) != record['model_sha256']:
        raise ValueError('checkpoint model hash mismatch')
    with model_path.open('rb') as stream:
        return pickle.load(stream), record['completed_rows'], record['history']


@contextmanager
def run_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'run.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def save_array(path, values):
    temp = Path(path).with_suffix('.npy.tmp')
    with temp.open('wb') as stream:
        np.save(stream, values, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temp), str(path))


def population_sizes(title, spec, prep, null_year):
    hdf = FULL / 'prepared/hdf'
    if spec['relationships']:
        schema = prep.schema_graph
        multipliers = [schema.relationship_dictionary[edge].end + '.' +
                       schema.relationship_dictionary[edge].multiplier_attribute_name
                       for edge in spec['relationships']]
        full = exact_star_size(title, multipliers)
        initial = {str(cut): exact_star_size(title, multipliers,
                     partition_years(title['title.production_year'].values, cut, null_year)[0]) for cut in CUTS}
    elif spec['tables'] == ['title']:
        full = len(title)
        initial = {str(cut): int(partition_years(title['title.production_year'].values, cut, null_year)[0].sum())
                   for cut in CUTS}
    else:
        table = spec['tables'][0]
        frame = pd.read_hdf(hdf / (table + '.hdf'))
        years = frame[table + '.movie_id'].map(title.set_index('title.id')['title.production_year'])
        if years.isna().any():
            raise ValueError('unmatched title key; temporal population cannot be assigned')
        full = len(frame)
        initial = {str(cut): int(partition_years(years.values, cut, null_year)[0].sum()) for cut in CUTS}
    return full, initial


def prepare_sample(spec, requested_samples):
    schema, prep = schema_and_prep()
    binding = dict(spec=spec, requested_samples=requested_samples, algorithm=algorithm_seal(),
                   driver=file_sha256(__file__), metadata=file_sha256(FULL / 'prepared/hdf/meta_data.pkl'),
                   inputs=dependency_seal(spec), oversampling=2., protocol='fixed_sample_all_cuts_v2')
    identifier = binding_hash(binding)
    directory = SAMPLES / identifier
    receipt = load_json(directory / 'sample.json')
    if receipt is not None:
        if receipt['binding'] != binding_hash(binding):
            raise ValueError('temporal sample binding differs')
        for record in receipt['artifacts']:
            if file_sha256(directory / record['name']) != record['sha256']:
                raise ValueError('temporal sample hash differs')
        return directory, receipt
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('unsealed temporal sample files; inspect before recovery')
    directory.mkdir(parents=True, exist_ok=True)
    seed = int(identifier[:8], 16) % (2 ** 31 - 1)
    np.random.seed(seed)
    random.seed(seed)
    title = pd.read_hdf(FULL / 'prepared/hdf/title.hdf')
    md = prep.table_meta_data['title']
    null_year = md['null_values_column'][md['relevant_attributes_full'].index('title.production_year')]
    population, initial_populations = population_sizes(title, spec, prep, null_year)
    sample_rate = min(1., requested_samples * 2. / population)
    started = time.perf_counter()
    if spec['relationships']:
        frame, meta_types, null_values = prep.generate_join_sample(
            relationship_list=spec['relationships'], sample_rate=sample_rate)
        if len(frame) > requested_samples:
            frame = frame.sample(requested_samples)
        years = frame['title.production_year'].values.copy()
    else:
        table = spec['tables'][0]
        frame, meta_types, null_values = prep.generate_join_sample(
            single_table=table, sample_rate=sample_rate, drop_redundant_columns=False)
        if len(frame) > requested_samples:
            frame = frame.sample(requested_samples)
        years = (frame['title.production_year'].values.copy() if table == 'title' else
                 frame[table + '.movie_id'].map(title.set_index('title.id')['title.production_year']).values)
        drop = {table + '.' + pk for pk in schema.table_dictionary[table].primary_key}
        drop.update(table + '.' + edge.start_attr for edge in schema.table_dictionary[table].outgoing_relationships
                    if edge.start_attr not in schema.table_dictionary[table].keep_fk_attributes)
        if table == 'title':
            drop.update(edge.end + '.' + edge.multiplier_attribute_name_nn for edge in schema.relationships)
        keep = [i for i, column in enumerate(frame.columns) if column not in drop]
        frame = frame.iloc[:, keep]
        meta_types = [meta_types[i] for i in keep]
        null_values = [null_values[i] for i in keep]
    values = frame.values.astype(np.float64, copy=False)
    target_rows = require_sample_size(len(values), requested_samples, population)
    if not np.isfinite(values).all() or not np.isfinite(years).all():
        raise ValueError('unexpected unprepared values or unassigned production year')
    save_array(directory / 'values.npy', values)
    save_array(directory / 'years.npy', years)
    receipt = dict(status='PASS', binding=binding_hash(binding), binding_details=binding, spec=spec,
                   rows=len(values), requested_samples=requested_samples, seed=seed,
                   required_sample_rows=target_rows, sample_size_target_met=True,
                   columns=list(frame.columns), meta_types=[t.name for t in meta_types],
                   null_values=null_values, null_year=float(null_year), full_population=population,
                   initial_populations=initial_populations, sampling_seconds=time.perf_counter() - started,
                   artifacts=[dict(name=name, sha256=file_sha256(directory / name))
                              for name in ['values.npy', 'years.npy']])
    atomic_json(directory / 'sample.json', receipt)
    print('TEMPORAL_SAMPLE_READY', identifier[:12], len(values), flush=True)
    return directory, receipt


def update_component(sample_directory, sample, cut, batch_size):
    values = np.load(str(sample_directory / 'values.npy'), mmap_mode='r')
    years = np.load(str(sample_directory / 'years.npy'), mmap_mode='r')
    initial, later = partition_years(years, cut, sample['null_year'])
    initial_indices, update_indices = np.flatnonzero(initial), np.flatnonzero(later)
    binding = dict(sample_sha256=file_sha256(sample_directory / 'sample.json'), cut=cut,
                   batch_size=batch_size, algorithm=algorithm_seal(), driver=file_sha256(__file__),
                   inputs=dependency_seal(sample['spec']),
                   update_protocol='pooled_author_fixed_structure_parameters_v1')
    identifier = binding_hash(binding)
    directory = FULL / 'incremental/components' / identifier
    with run_lock(directory):
        finished = load_json(directory / 'result.json')
        if finished is not None:
            if finished['binding'] != binding_hash(binding):
                raise ValueError('incremental result binding mismatch')
            for record in finished['artifacts']:
                if file_sha256(ROOT / record['path']) != record['sha256']:
                    raise ValueError('incremental result artifact changed')
            return read_ensemble(str(ROOT / finished['model_path'])).spns[0], finished
        restored = load_update_checkpoint(directory, binding)
        schema, prep = schema_and_prep()
        if restored is None:
            if len(initial_indices) < 100:
                raise ValueError('initial temporal sample too small')
            seed = sample['seed']
            np.random.seed(seed)
            random.seed(seed)
            spec = sample['spec']
            model = AQPSPN([MetaType[name] for name in sample['meta_types']], sample['null_values'],
                           sample['initial_populations'][str(cut)], schema, spec['relationships'],
                           full_sample_size=len(initial_indices), table_set=set(spec['tables']),
                           column_names=sample['columns'], table_meta_data=prep.table_meta_data)
            started = time.perf_counter()
            model.learn(np.asarray(values[initial_indices]), rdc_threshold=.3,
                        min_instances_slice=.01 * len(initial_indices))
            learning_seconds = time.perf_counter() - started
            valid, reason = is_valid(model.mspn, check_ids=True, check_cluster_centers=True)
            if not valid:
                raise ValueError(reason)
            before = directory / 'before.pkl'
            atomic_ensemble(before, SPNEnsemble(schema, [model]))
            history = [dict(stage='initial_training', rows=len(initial_indices), seconds=learning_seconds)]
            done = 0
            save_update_checkpoint(directory, model, done, binding, history)
        else:
            model, done, history = restored
        if not 0 <= done <= len(update_indices):
            raise ValueError('checkpoint update cursor outside the sealed sample')
        gate_path = directory / 'scalar_update_gate.json'
        if not gate_path.exists():
            # Check actual data at both ends of the update partition before
            # accepting the faster parameter pooling for this learned tree.
            remaining = update_indices[done:]
            positions = np.unique(np.linspace(0, max(0, len(remaining) - 1), min(128, len(remaining))).astype(int))
            gate = scalar_update_gate(model, np.asarray(values[remaining[positions]]))
            gate.update(binding=binding_hash(binding), update_indices=remaining[positions].tolist())
            atomic_json(gate_path, gate)
        elif load_json(gate_path).get('binding') != binding_hash(binding):
            raise ValueError('scalar update gate binding mismatch')
        for start in range(done, len(update_indices), batch_size):
            indices = update_indices[start:start + batch_size]
            started = time.perf_counter()
            batch_update(model.mspn, np.asarray(values[indices]))
            model.full_sample_size += len(indices)
            model.full_join_size += len(indices)
            elapsed = time.perf_counter() - started
            valid, reason = is_valid(model.mspn, check_ids=True, check_cluster_centers=True)
            if not valid:
                raise ValueError(reason)
            done = start + len(indices)
            history.append(dict(stage='updates', completed_rows=done, rows=len(indices), seconds=elapsed))
            save_update_checkpoint(directory, model, done, binding, history)
            print('UPDATED', identifier[:12], done, '/', len(update_indices), flush=True)
        model.full_join_size = sample['full_population']
        if model.full_sample_size != len(values):
            raise ValueError('initial/update sample accounting is not exhaustive')
        after = directory / 'after.pkl'
        atomic_ensemble(after, SPNEnsemble(schema, [model]))
        result = dict(status='PASS', binding=binding_hash(binding), cut=cut, spec=sample['spec'],
                      requested_samples=sample['requested_samples'], actual_samples=len(values),
                      initial_sample_rows=len(initial_indices), updated_sample_rows=len(update_indices),
                      sample_update_fraction=len(update_indices) / len(values),
                      full_population=sample['full_population'],
                      initial_population=sample['initial_populations'][str(cut)],
                      population_update_fraction=1 - sample['initial_populations'][str(cut)] / sample['full_population'],
                      learning_seconds=history[0]['seconds'],
                      update_seconds=sum(item['seconds'] for item in history if item['stage'] == 'updates'),
                      update_batch_size=batch_size, model_path=after.relative_to(ROOT).as_posix(),
                      sample_size_target_met=sample['sample_size_target_met'],
                      artifacts=[dict(path=p.relative_to(ROOT).as_posix(), sha256=file_sha256(p))
                                 for p in [directory / 'before.pkl', after, gate_path]])
        atomic_json(directory / 'result.json', result)
        return model, result


def run(samples, cuts, batch_size):
    base_path = FULL / 'results/rdc_n100000_b0p0_training.json'
    reference = load_json(base_path)
    # The preserved first JOB-light receipt predates the explicit profile field.
    # Its fixed label/path and sealed model identify that original schema.
    if (reference is None or reference.get('profile', 'joblight') != 'joblight'
            or reference.get('label') != 'rdc_n100000_b0p0'
            or file_sha256(ROOT / reference['model_path']) != reference['model_sha256']):
        raise ValueError('missing sealed JOB-light B=0 model-selection reference')
    sample_records = [prepare_sample(item['spec'], samples) for item in reference['models']]
    schema, _ = schema_and_prep()
    for cut in cuts:
        ensemble, records = SPNEnsemble(schema), []
        for sample_directory, sample in sample_records:
            model, record = update_component(sample_directory, sample, cut, batch_size)
            ensemble.add_spn(model)
            records.append(record)
            gc.collect()
        label = 'temporal_joblight_rdc_n%d_b0p0_year%d' % (samples, cut)
        target = FULL / 'models' / label / 'ensemble.pkl'
        atomic_ensemble(target, ensemble)
        atomic_json(FULL / 'results' / (label + '_training.json'),
                    dict(status='PASS', label=label, strategy='rdc', requested_samples=samples,
                         budget=0., cut=cut, profile='joblight', models=records,
                         selection_reference=dict(path=base_path.relative_to(ROOT).as_posix(), sha256=file_sha256(base_path)),
                         model_path=target.relative_to(ROOT).as_posix(), model_sha256=file_sha256(target),
                         pairwise_rdc_path=reference['pairwise_rdc_path'],
                         sampling='one sealed full-data sample per model, shared across all temporal cuts',
                         updates='fixed structure/centers, parameter pooling checked against author scalar updates',
                         null_year_policy='initial partition', population_normalizer='exact full outer star size'))
        print('TEMPORAL_ENSEMBLE_READY', label, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=10000000)
    parser.add_argument('--cuts', type=int, nargs='+', default=list(CUTS))
    parser.add_argument('--update-batch-size', type=int, default=100000)
    args = parser.parse_args()
    if args.samples < 100 or args.update_batch_size < 1 or not set(args.cuts).issubset(CUTS):
        parser.error('invalid sample count, batch size or temporal cut')
    logging.basicConfig(level=logging.INFO)
    with run_lock(FULL / 'incremental'):
        run(args.samples, args.cuts, args.update_batch_size)


if __name__ == '__main__':
    main()
