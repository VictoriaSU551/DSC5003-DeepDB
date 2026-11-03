import pytest

from full_common import binding_hash
from full_truth_arrays_run import fs_path, validate_count_identity, validate_database_identity


def test_database_identity_refuses_same_row_count_updates_and_late_stats_reset():
    imports = {'title': {'rows': 3}}
    assert validate_database_identity([('title', 3, 0, 0)], 1., 2., imports)
    with pytest.raises(ValueError, match='modified'):
        validate_database_identity([('title', 3, 1, 0)], 1., 2., imports)
    with pytest.raises(ValueError, match='reset'):
        validate_database_identity([('title', 3, 0, 0)], 3., 2., imports)


def test_valid_count_receipt_copied_under_another_query_key_is_rejected():
    query = {'tables': ['title'], 'predicates': {'title': []}}
    record = {'snapshot_binding': 'sealed', 'logical_query': query, 'count': 3}
    validate_count_identity(record, binding_hash(query) + '.json')
    with pytest.raises(ValueError, match='query key'):
        validate_count_identity(record, '0' * 64 + '.json')


def test_atomic_checkpoint_handles_windows_max_path_without_registry_change(tmp_path):
    from full_common import atomic_json, load_json
    path = tmp_path / ('a' * 120) / ('b' * 120) / 'count.json'
    atomic_json(fs_path(path), {'count': 2**65})
    assert load_json(fs_path(path)) == {'count': 2**65}
