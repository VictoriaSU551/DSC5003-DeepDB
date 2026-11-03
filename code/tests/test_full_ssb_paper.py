"""Safety and exactness of the distinct SF500 entry; no SF500 is generated."""
import hashlib
import importlib
import importlib.util
import json
import zipfile

import pytest


def implementation():
    assert importlib.util.find_spec('full_ssb_paper') is not None, 'Paper-scale SSB entry is missing'
    return importlib.import_module('full_ssb_paper')


def fixture_archive(tmp_path, extra=None, wrong_file=False):
    archive = tmp_path / 'fixed.zip'
    with zipfile.ZipFile(str(archive), 'w') as stream:
        stream.writestr('pinned/a.c', b'upstream\r\n')
        stream.writestr('pinned/rnd.h', b'fixed seed\n')
        if extra:
            stream.writestr(extra, b'escape')
    pins = {'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files_sha256': {'a.c': hashlib.sha256(b'upstream\r\n').hexdigest(),
                             'rnd.h': hashlib.sha256(b'wrong' if wrong_file else b'fixed seed\n').hexdigest()}}
    return archive, pins


def test_setup_restores_only_exact_missing_bytes(tmp_path):
    archive, pins = fixture_archive(tmp_path)
    destination = tmp_path / 'vendor'
    destination.mkdir()
    adapter = destination / 'full_chunk_driver.c'
    adapter.write_bytes(b'our adapter')
    result = implementation().restore_sources(archive, destination, pins)
    assert (destination / 'a.c').read_bytes() == b'upstream\r\n'
    assert (destination / 'rnd.h').read_bytes() == b'fixed seed\n'
    assert adapter.read_bytes() == b'our adapter'
    assert sorted(result['restored']) == ['a.c', 'rnd.h']
    assert implementation().restore_sources(archive, destination, pins)['restored'] == []


@pytest.mark.parametrize('bad', ['changed_archive', 'wrong_file', 'traversal'])
def test_invalid_zip_never_partially_restores_sources(tmp_path, bad):
    archive, pins = fixture_archive(tmp_path, '../escape' if bad == 'traversal' else None,
                                    wrong_file=bad == 'wrong_file')
    if bad == 'changed_archive':
        archive.write_bytes(archive.read_bytes() + b'changed')
    destination = tmp_path / 'vendor'
    with pytest.raises(ValueError):
        implementation().restore_sources(archive, destination, pins)
    assert not destination.exists()
    assert not (tmp_path / 'escape').exists()


def test_setup_refuses_to_overwrite_modified_original(tmp_path):
    archive, pins = fixture_archive(tmp_path)
    destination = tmp_path / 'vendor'
    destination.mkdir()
    (destination / 'rnd.h').write_bytes(b'edited seed')
    with pytest.raises(ValueError, match='changed'):
        implementation().restore_sources(archive, destination, pins)
    assert (destination / 'rnd.h').read_bytes() == b'edited seed'
    assert not (destination / 'a.c').exists()


def test_shards_cover_all_orders_once_including_remainder():
    ranges = implementation().order_ranges(2, 7)
    assert ranges[0] == (1, 428571)
    assert ranges[-1] == (2571427, 428574)
    assert sum(count for start, count in ranges) == 3000000
    assert all(a + n == b for (a, n), (b, _) in zip(ranges, ranges[1:]))


def test_truth_comparison_is_integer_exact_and_detects_missing_or_moved_groups():
    compare = implementation().compare_truth
    expected = {'0': {'': 9007199254740993}, '3': {'1992\tMFGR#121': 5}}
    assert compare(expected, expected)['match']
    report = compare({'0': {'': 9007199254740992}, '3': {'1993\tMFGR#121': 5}}, expected)
    assert not report['match']
    assert report['different_values'] == [{'query': '0', 'group': '', 'actual': 9007199254740992, 'expected': 9007199254740993}]
    assert report['missing_groups'] == [{'query': '3', 'group': '1992\tMFGR#121'}]
    assert report['extra_groups'] == [{'query': '3', 'group': '1993\tMFGR#121'}]


def test_checkpoint_rejects_seed_or_source_before_sample_mutation(tmp_path):
    module = implementation()
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(b'a\ncrash-tail')
    state = {'binding': {'seed': 7, 'source': 'original'}, 'sample_bytes': 0, 'sample_rows': 0,
             'sample_sha256': hashlib.sha256(b'').hexdigest(), 'next_shard': 1,
             'committed_shards': [], 'aggregates': {str(q): {} for q in range(13)}, 'rows': 0}
    for binding in [{'seed': 8, 'source': 'original'}, {'seed': 7, 'source': 'changed'}]:
        with pytest.raises(ValueError, match='binding'):
            module.restore_checkpoint(sample, state, binding, tmp_path)
        assert sample.read_bytes() == b'a\ncrash-tail'
    module.restore_checkpoint(sample, state, state['binding'], tmp_path)
    assert sample.read_bytes() == b''


def test_checkpoint_rejects_noncontiguous_shards_before_truncation(tmp_path):
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(b'a\ncrash-tail')
    state = {'binding': {}, 'sample_bytes': 2, 'sample_sha256': hashlib.sha256(b'a\n').hexdigest(),
             'next_shard': 3, 'committed_shards': [{'shard': 2}], 'rows': 1}
    with pytest.raises(ValueError, match='contiguous'):
        implementation().restore_checkpoint(sample, state, {}, tmp_path)
    assert sample.read_bytes() == b'a\ncrash-tail'


def test_large_run_cannot_start_without_reviewed_matching_plan(tmp_path):
    module = implementation()
    plan = {'status': 'READY_FOR_ROOT_REVIEW', 'binding': {'scale': 500}}
    with pytest.raises(ValueError, match='execute'):
        module.require_execution(plan, None, False, 20 * 1024 ** 3)
    with pytest.raises(ValueError, match='reviewed'):
        module.require_execution(plan, 'changed', True, 20 * 1024 ** 3)
    with pytest.raises(ValueError, match='disk'):
        module.require_execution(plan, module.object_sha(plan), True, 1)
    module.require_execution(plan, module.object_sha(plan), True, 20 * 1024 ** 3)


def test_dimension_resume_reuses_complete_table_and_rejects_changed_bytes(tmp_path):
    module = implementation()
    completed = tmp_path / 'customer.tbl'
    completed.write_bytes(b'1|customer|\n')
    state = {'files': {'customer': {'rows': 1, 'sha256': hashlib.sha256(completed.read_bytes()).hexdigest()}}}
    assert module.pending_dimensions(tmp_path, state, {'customer': 1, 'date': 2}) == ['date']
    completed.write_bytes(b'1|changed!|\n')
    with pytest.raises(ValueError, match='dimension'):
        module.pending_dimensions(tmp_path, state, {'customer': 1, 'date': 2})


def test_committed_aggregate_corruption_fails_before_tail_is_truncated(tmp_path):
    module = implementation()
    aggregate = tmp_path / 'aggregates.tsv'
    aggregate.write_bytes(b'0\t4\n')
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(b'a\ncrash-tail')
    state = {'binding': {}, 'next_shard': 2, 'rows': 1,
             'sample_bytes': 2, 'sample_sha256': hashlib.sha256(b'a\n').hexdigest(),
             'committed_shards': [{'shard': 1, 'rows': 1, 'aggregate_file': 'aggregates.tsv',
                                  'retained_sha256': {'aggregates.tsv': hashlib.sha256(aggregate.read_bytes()).hexdigest()}}],
             'aggregates': {str(q): {'': 5} if q == 0 else {} for q in range(13)}}
    with pytest.raises(ValueError, match='aggregate'):
        module.restore_checkpoint(sample, state, {}, tmp_path)
    assert sample.read_bytes() == b'a\ncrash-tail'


def test_os_lock_refuses_a_second_writer_and_releases_after_close(tmp_path):
    module = implementation()
    path = tmp_path / 'run.lock'
    with module.RunLock(path):
        with pytest.raises(OSError):
            with module.RunLock(path):
                pytest.fail('Second writer entered the locked stream')
    with module.RunLock(path):
        pass


def test_dimension_group_matches_existing_sf2_stock_all_table_sequence():
    module = implementation()
    reference = module.DATA / 'sf2_gate/stock_pipe'
    if not (reference / 'stock_pipe.json').is_file() or not module.sf1.GCC.is_file():
        pytest.skip('Requires the retained independent SF2 stock pipe reference')
    target = module.DATA / 'sf2_dimension_regression'
    module.generate_dimension_group(2, target)
    for name in ['customer', 'supplier', 'part', 'date']:
        assert module.digest(target / (name + '.tbl')) == module.digest(reference / (name + '.tbl'))


def test_completed_dimension_copy_is_cleaned_but_changed_copy_is_retained(tmp_path):
    module = implementation()
    work = tmp_path / 'building_group'
    work.mkdir()
    path = work / 'customer.tbl'
    path.write_bytes(b'complete')
    files = {'customer': {'sha256': hashlib.sha256(b'complete').hexdigest()}}
    module.cleanup_dimension_copies(work, files)
    assert not path.exists()
    path.write_bytes(b'changed!')
    with pytest.raises(ValueError, match='dimension'):
        module.cleanup_dimension_copies(work, files)
    assert path.read_bytes() == b'changed!'


def test_sample_count_tampering_is_rejected_before_tail_truncation(tmp_path):
    sample = tmp_path / 'sample.csv'
    sample.write_bytes(b'uncommitted tail')
    state = {'binding': {}, 'sample_bytes': 0, 'sample_rows': 1,
             'sample_sha256': hashlib.sha256(b'').hexdigest(), 'next_shard': 1,
             'committed_shards': [], 'aggregates': {str(q): {} for q in range(13)}, 'rows': 0}
    with pytest.raises(ValueError, match='sample'):
        implementation().restore_checkpoint(sample, state, {}, tmp_path)
    assert sample.read_bytes() == b'uncommitted tail'
