from copy import deepcopy

from full_joblight_variants import shared_profile_proof


def test_profile_reuse_requires_identical_scope_metadata_and_data(tmp_path):
    a, b = tmp_path / 'a.hdf', tmp_path / 'b.hdf'
    a.write_bytes(b'same prepared table')
    b.write_bytes(a.read_bytes())
    meta_a = {'title': {'hdf_path': str(a), 'null_values_column': [1992.123], 'length': 2}}
    meta_b = deepcopy(meta_a)
    meta_b['title']['hdf_path'] = str(b)
    spec = {'tables': ['title'], 'relationships': []}
    assert shared_profile_proof(spec, meta_a, meta_b)['status'] == 'PASS'
    b.write_bytes(b'changed')
    assert shared_profile_proof(spec, meta_a, meta_b) is None


def test_changed_cast_scope_or_null_semantics_cannot_be_reused(tmp_path):
    p = tmp_path / 'same.hdf'
    p.write_bytes(b'same')
    a = {'title': {'hdf_path': str(p), 'null_values_column': [1992.123]}}
    b = deepcopy(a)
    b['title']['null_values_column'] = [-1.]
    assert shared_profile_proof({'tables': ['title']}, a, b) is None
    assert shared_profile_proof({'tables': ['cast_info', 'title']}, a, a) is None
