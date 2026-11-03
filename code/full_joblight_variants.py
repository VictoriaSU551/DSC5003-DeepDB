"""Original JOB-light schema variants, reusing proven identical non-cast models.

The public-scale schema differs only in cast_info.person_id. Components whose
scope excludes cast_info may be reused after table definitions, full metadata
and every referenced prepared HDF are checked. Cast components never cross this
profile boundary. This avoids retraining the same verified non-cast inputs.
"""
import argparse
import gc
import json
from pathlib import Path
import pickle

import numpy as np

from ensemble_compilation.spn_ensemble import SPNEnsemble, read_ensemble
from ensemble_creation.rdc_based import learning_cost
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation_v2 import evaluate
from full_prepare import schema_for_profile
import full_training as training


def shared_profile_proof(spec, original_metadata, public_metadata):
    if 'cast_info' in spec['tables']:
        return None
    files = []
    def normalized(value, key=None):
        if key in ('path', 'hdf_path') and isinstance(value, str):
            path = Path(value)
            checksum = file_sha256(path)
            files.append(dict(path=str(path), sha256=checksum))
            return ['sealed_file', checksum]
        if isinstance(value, dict):
            return [[type(k).__name__ + ':' + repr(k), normalized(v, k)]
                    for k, v in sorted(value.items(), key=lambda item: (type(item[0]).__name__, repr(item[0])))]
        if isinstance(value, (list, tuple, np.ndarray)):
            return [normalized(v) for v in value]
        if isinstance(value, np.generic):
            return value.item()
        return value
    for table in sorted(spec['tables']):
        left, right = normalized(original_metadata[table]), normalized(public_metadata[table])
        if binding_hash(left) != binding_hash(right):
            return None
    return dict(status='PASS', scope=spec['tables'],
                rule='all scope metadata and referenced HDF contents identical; cast_info excluded',
                checked_files=files)


def table_signature(table):
    return {key: getattr(table, key) for key in ['table_name', 'primary_key', 'table_nn_attribute',
            'table_size', 'attributes', 'irrelevant_attributes', 'keep_fk_attributes',
            'sample_rate', 'fd_list', 'no_compression']}


def find_shared_component(spec, samples, original_metadata, public_metadata):
    proof = shared_profile_proof(spec, original_metadata, public_metadata)
    if proof is None:
        return None
    public_schema = schema_for_profile('public-scale')
    original_schema = schema_for_profile('joblight')
    if any(table_signature(public_schema.table_dictionary[t]) != table_signature(original_schema.table_dictionary[t])
           for t in spec['tables']):
        return None
    for path in sorted((FULL / 'results').glob('*_training.json')):
        record = load_json(path)
        if (record.get('profile') != 'public-scale' or record.get('cut') is not None
                or record.get('requested_samples') != samples):
            continue
        for item in record['models']:
            if item['spec'] != spec or item.get('incremental_samples') != 0 or len(item['artifacts']) != 1:
                continue
            artifact = item['artifacts'][0]
            source = ROOT / artifact['path']
            if not source.is_file() or file_sha256(source) != artifact['sha256']:
                raise ValueError('candidate shared component is not sealed')
            model = read_ensemble(str(source)).spns[0]
            if any(column.startswith('cast_info.') for column in model.column_names):
                raise ValueError('cast feature in supposedly cast-free component')
            result = dict(item, cross_profile_reuse=dict(source_training_receipt=path.relative_to(ROOT).as_posix(),
                          source_receipt_sha256=file_sha256(path), proof=proof))
            print('REUSED_IDENTICAL_NONCAST_COMPONENT', spec['tables'], flush=True)
            return model, result
    return None


def run(samples, modes, budget):
    if training.PROFILE != 'joblight':
        raise ValueError('run original JOB-light variants in a fresh process')
    schema, prep = training.schema_and_prep()
    with (FULL / 'prepared/public-scale/hdf/meta_data.pkl').open('rb') as stream:
        public_metadata = pickle.load(stream)
    shared = {}
    for mode in modes:
        if mode == 'single':
            specs = [dict(relationships=[], tables=[t.table_name]) for t in schema.tables]
            label = 'joblight_single_n%d' % samples
            factor, base_cost, single_cost = None, None, None
        else:
            base = training.select_rdc(0.)
            base_cost = sum(learning_cost(prep, [x['relationships']]) if x['relationships'] else
                            learning_cost(prep, None, single_table=x['tables'][0]) for x in base)
            single_cost = sum(prep.column_number(single_table=t.table_name) ** 2 for t in schema.tables)
            factor = budget * base_cost / single_cost
            specs = training.select_rdc(factor)
            label = 'paper_proxy_joblight_rdc_n%d_b%s' % (samples, str(float(budget)).replace('.', 'p'))
        ensemble, receipts = SPNEnsemble(schema), []
        for spec in specs:
            key = binding_hash(spec)
            if key not in shared:
                shared[key] = find_shared_component(spec, samples, prep.table_meta_data, public_metadata)
            result = shared[key]
            if result is None:
                result = training.component(spec, samples)
            model, receipt = result
            ensemble.add_spn(model)
            receipts.append(receipt)
            gc.collect()
        target = FULL / 'models' / label / 'ensemble.pkl'
        existing = load_json(FULL / 'results' / (label + '_training.json'))
        if not (existing and target.exists() and file_sha256(target) == existing['model_sha256']
                and [x['binding'] for x in existing['models']] == [x['binding'] for x in receipts]):
            training.atomic_ensemble(target, ensemble)
        record = dict(status='PASS', label=label, profile='joblight', strategy=mode,
                      requested_samples=samples, budget=budget if mode == 'rdc' else None, cut=None,
                      budget_semantics='paper B*CBase column-squared proxy' if mode == 'rdc' else None,
                      base_cost_columns_squared=base_cost, single_cost_columns_squared=single_cost,
                      released_code_equivalent_factor=factor, models=receipts,
                      model_path=target.relative_to(ROOT).as_posix(), model_sha256=file_sha256(target),
                      pairwise_rdc_path=training.PAIRWISE.relative_to(ROOT).as_posix() if mode == 'rdc' else None,
                      driver_sha256=file_sha256(__file__))
        atomic_json(FULL / 'results' / (label + '_training.json'), record)
        evaluate(label, include_scale=False)
        print('JOBLIGHT_VARIANT_READY', label, flush=True)
        del ensemble
        gc.collect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=10000000)
    parser.add_argument('--modes', nargs='+', choices=['single', 'rdc'], default=['single', 'rdc'])
    parser.add_argument('--budget', type=float, default=.5)
    args = parser.parse_args()
    if args.samples < 100 or args.budget < 0:
        parser.error('invalid sample count or budget')
    run(args.samples, args.modes, args.budget)


if __name__ == '__main__':
    main()
