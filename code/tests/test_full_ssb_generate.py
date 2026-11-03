"""Checkpoint protection for the bounded SSB generation/consumption path."""
import hashlib
import importlib
import importlib.util

import pytest


def implementation():
    assert importlib.util.find_spec('full_ssb_generate') is not None, 'SSB streaming runner is missing'
    return importlib.import_module('full_ssb_generate')


def checkpoint(prefix=b'a\n'):
    return {'binding': {'input': 'original', 'sampling_seed': 7}, 'sample_bytes': len(prefix),
            'sample_sha256': hashlib.sha256(prefix).hexdigest(), 'next_shard': 2}


def test_resume_truncates_only_uncommitted_tail(tmp_path):
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(b'a\nuncommitted tail\n')
    module = implementation()
    digest = module.resume_sample(sample, checkpoint(), checkpoint()['binding'])
    assert sample.read_bytes() == b'a\n'
    digest.update(b'b\n')
    assert digest.hexdigest() == hashlib.sha256(b'a\nb\n').hexdigest()


@pytest.mark.parametrize('changed', [{'input': 'changed', 'sampling_seed': 7},
                                     {'input': 'original', 'sampling_seed': 8}])
def test_changed_binding_is_rejected_before_tail_truncation(tmp_path, changed):
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(b'a\nuncommitted tail\n')
    with pytest.raises(ValueError, match='binding'):
        implementation().resume_sample(sample, checkpoint(), changed)
    assert sample.read_bytes() == b'a\nuncommitted tail\n'


@pytest.mark.parametrize('content', [b'a', b'b\n'])
def test_missing_or_corrupt_committed_prefix_is_rejected(tmp_path, content):
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(content)
    with pytest.raises(ValueError):
        implementation().resume_sample(sample, checkpoint(), checkpoint()['binding'])
    assert sample.read_bytes() == content


def test_integer_aggregate_merge_preserves_large_totals():
    merge = implementation().merge_aggregates
    destination = {'0': {'': 9007199254740993}, '3': {'1993\tMFGR#12': 2}}
    merge(destination, {'0': {'': 2}, '3': {'1993\tMFGR#12': 5, '1994\tMFGR#12': 9}})
    assert destination == {'0': {'': 9007199254740995},
                           '3': {'1993\tMFGR#12': 7, '1994\tMFGR#12': 9}}


def test_sf500_gate_cannot_start_generation():
    with pytest.raises(ValueError, match='SF500'):
        implementation().require_generation_gate(500)


def test_committed_raw_file_left_after_checkpoint_is_cleaned_without_replay(tmp_path):
    committed = tmp_path / 'lineorder.tbl.1'
    pending = tmp_path / 'lineorder.tbl.2'
    committed.write_bytes(b'completed shard\n')
    pending.write_bytes(b'uncommitted shard\n')
    state = {'committed_shards': [{'raw_filename': committed.name,
                                  'raw_sha256': hashlib.sha256(committed.read_bytes()).hexdigest()}]}
    implementation().clean_committed_raw(tmp_path, state)
    assert not committed.exists()
    assert pending.read_bytes() == b'uncommitted shard\n'


def test_corrupt_committed_raw_is_rejected_before_cleanup(tmp_path):
    path = tmp_path / 'lineorder.tbl.1'
    path.write_bytes(b'changed bytes')
    state = {'committed_shards': [{'raw_filename': path.name,
                                  'raw_sha256': hashlib.sha256(b'original bytes').hexdigest()}]}
    with pytest.raises(ValueError, match='raw'):
        implementation().clean_committed_raw(tmp_path, state)
    assert path.read_bytes() == b'changed bytes'


def test_chunk_output_matches_original_all_table_reference_bytes():
    module = implementation()
    if not (module.DATA / 'sf1_gold/lineorder.tbl').is_file() or not module.GCC.is_file():
        pytest.skip('Full SF1 reference/toolchain not present; run full_ssb_generate.py sf1 first')
    module.build()
    raw = module.generate_raw_shard(module.DATA / 'regression_chunk', 1, 64, 1)
    with (module.DATA / 'sf1_gold/lineorder.tbl').open('rb') as reference:
        expected = hashlib.sha256(reference.read(raw.stat().st_size)).hexdigest()
    assert module.digest(raw) == expected
