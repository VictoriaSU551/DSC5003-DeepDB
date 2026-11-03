"""Seal actual prepared IMDb inputs before new training or checkpoint recovery.

This is a current observation, never a retroactive training-time attestation for
legacy components. Complete, sampled, fanout and unmatched-row HDFs are covered.
"""
import argparse
from pathlib import Path
import pickle

from full_common import ROOT, FULL, algorithm_seal, atomic_json, binding_hash, file_sha256, load_json


def file_record(path, root=ROOT):
    path, root = Path(path).resolve(), Path(root).resolve()
    return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=file_sha256(path))


def verify_records(records, root=ROOT):
    root = Path(root).resolve()
    for item in records:
        path = (root / item['path']).resolve()
        if (root not in path.parents or not path.is_file()
                or ('bytes' in item and path.stat().st_size != item['bytes'])
                or file_sha256(path) != item['sha256']):
            raise ValueError('prepared/input artifact differs: ' + item['path'])


def prepared_records(directory, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    paths = set(directory.glob('*.hdf')) | set(directory.glob('*.pkl'))
    if not paths:
        raise ValueError('no prepared artifacts')
    def check_references(value):
        if isinstance(value, dict):
            for item in value.values():
                check_references(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check_references(item)
        elif isinstance(value, str) and value.lower().endswith('.hdf'):
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = directory / candidate
            candidate = candidate.resolve()
            if root not in candidate.parents or not candidate.is_file():
                raise ValueError('metadata referenced HDF is missing or outside project: ' + value)
            paths.add(candidate)
    # These are project-generated, locally trusted metadata pickles.
    for metadata in sorted(directory.glob('meta_data*.pkl')):
        with metadata.open('rb') as stream:
            check_references(pickle.load(stream))
    return [file_record(path, root) for path in sorted(paths)]


def input_binding(profile):
    if profile not in ['joblight', 'public-scale']:
        raise ValueError('unknown preparation profile')
    manifest_path = ROOT / 'data/manifest.json'
    raw = load_json(manifest_path)
    raw_records = []
    for item in raw['files']:
        path = ROOT / 'data' / item['path']
        actual = file_record(path)
        if actual['bytes'] != item['bytes'] or actual['sha256'] != item['sha256']:
            raise ValueError('raw input does not match manifest: ' + item['path'])
        raw_records.append(actual)
    directory = FULL / 'prepared' / ('hdf' if profile == 'joblight' else 'public-scale/hdf')
    artifacts = prepared_records(directory)
    previous = FULL / 'checkpoints/prepared_public-scale.json'
    origin = dict(status='CURRENT_INPUTS_ONLY_NO_LEGACY_TRAINING_TIME_HDF_SEAL')
    if profile == 'public-scale':
        receipt = load_json(previous)
        if receipt is None or receipt.get('status') != 'PASS':
            raise ValueError('public-scale preparation receipt is missing')
        verify_records(receipt['artifacts'])
        from full_common import checkpoint_valid
        binding = dict(profile=profile, raw=file_sha256(manifest_path),
                       original_metadata=file_sha256(FULL / 'prepared/hdf/meta_data.pkl'),
                       preparation=file_sha256(ROOT / 'code/data_preparation/prepare_single_tables.py'),
                       sampling=file_sha256(ROOT / 'code/data_preparation/join_data_preparation.py'),
                       driver=file_sha256(ROOT / 'code/full_prepare.py'))
        if not checkpoint_valid(receipt, binding):
            raise ValueError('public-scale preparation binding differs')
        origin = dict(status='EXISTING_PREPARATION_MANIFEST_MATCHED', receipt=file_record(previous))
    return dict(profile=profile, algorithm=algorithm_seal(), raw_manifest=file_record(manifest_path),
                raw_files=raw_records, prepared=artifacts, preparation_origin=origin,
                helpers={name: file_sha256(ROOT / 'code' / name)
                         for name in ['full_prepared_seal.py', 'full_training.py', 'full_prepare.py', 'full_common.py']})


def seal(profile):
    binding = input_binding(profile)
    identifier = binding_hash(binding)
    result = dict(status='PASS_CURRENT_PREPARED_INPUTS', profile=profile,
                  binding=identifier, configuration=binding,
                  scope='Current actual input integrity; legacy training-time omissions are not retrospectively repaired')
    atomic_json(FULL / 'prepared_seals' / identifier / 'manifest.json', result)
    atomic_json(FULL / 'results' / ('prepared_' + profile + '_current.json'), result)
    print('PREPARED_INPUT_SEAL_PASS', profile, len(binding['prepared']), identifier, flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['joblight', 'public-scale', 'all'], default='all')
    args = parser.parse_args()
    for profile in (['joblight', 'public-scale'] if args.profile == 'all' else [args.profile]):
        seal(profile)


if __name__ == '__main__':
    main()
