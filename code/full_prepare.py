"""Extend only the columns required by the published scale workloads."""
import argparse
import copy
import os
import pickle
from pathlib import Path

from data_preparation.join_data_preparation import prepare_sample_hdf
from data_preparation.prepare_single_tables import prepare_single_table
from full_common import ROOT, FULL, atomic_json, checkpoint_valid, file_sha256, load_json, binding_hash
from schemas.imdb.schema import gen_job_light_imdb_schema


def schema_for_profile(profile='joblight'):
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    if profile == 'public-scale':
        cast = schema.table_dictionary['cast_info']
        cast.irrelevant_attributes.remove('person_id')
        cast.no_compression.append('person_id')
    elif profile != 'joblight':
        raise ValueError('Unknown schema profile')
    return schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['public-scale'], default='public-scale')
    profile = parser.parse_args().profile
    source = FULL / 'prepared/hdf'
    target = FULL / 'prepared' / profile / 'hdf'
    target.mkdir(parents=True, exist_ok=True)
    binding = dict(profile=profile, raw=file_sha256(ROOT / 'data/manifest.json'),
                   original_metadata=file_sha256(source / 'meta_data.pkl'),
                   preparation=file_sha256(ROOT / 'code/data_preparation/prepare_single_tables.py'),
                   sampling=file_sha256(ROOT / 'code/data_preparation/join_data_preparation.py'),
                   driver=file_sha256(__file__))
    receipt_path = FULL / 'checkpoints' / ('prepared_' + profile + '.json')
    receipt = load_json(receipt_path, {})
    if checkpoint_valid(receipt, binding):
        print('Reused sealed public-scale preparation.', flush=True)
        return
    for path in source.glob('*.hdf'):
        if path.name == 'cast_info.hdf' or '_sampled' in path.name:
            continue
        destination = target / path.name
        if not destination.exists():
            os.link(str(path), str(destination))
    with (source / 'meta_data.pkl').open('rb') as stream:
        metadata = pickle.load(stream)
    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, str):
            return value.replace(str(source), str(target)).replace(source.as_posix(), target.as_posix())
        return value
    metadata = relocate(metadata)
    schema = schema_for_profile(profile)
    metadata['cast_info'] = prepare_single_table(schema, 'cast_info', str(target / 'cast_info.hdf'),
                                                max_table_data=100000000)
    with (target / 'meta_data.pkl').open('wb') as stream:
        pickle.dump(metadata, stream, pickle.HIGHEST_PROTOCOL)
    import numpy as np
    import random
    np.random.seed(1)
    random.seed(1)
    prepare_sample_hdf(schema, str(target), 100000000, 10000)
    artifacts = [dict(path=path.relative_to(ROOT).as_posix(), sha256=file_sha256(path))
                 for path in sorted(target.glob('*')) if path.is_file()]
    atomic_json(receipt_path, dict(status='PASS', binding=binding_hash(binding), profile=profile,
                                  artifacts=artifacts, note='Other full HDFs shared as project-local hard links; cast_info retains person_id.'))
    print('Prepared required person_id column and sampled HDFs.', flush=True)


if __name__ == '__main__':
    main()
