import pickle

import pytest

from full_prepared_seal import prepared_records, verify_records


def test_prepared_records_cover_values_samples_and_unmatched_rows(tmp_path):
    directory = tmp_path / 'hdf'; directory.mkdir()
    names = ['title.hdf', 'title_sampled.hdf', 'title.hdfchildmovie_id.hdf']
    for name in names:
        (directory / name).write_bytes(name.encode())
    (directory / 'meta_data.pkl').write_bytes(pickle.dumps({'title': {'hdf_path': str(directory / names[0])}}))
    records = prepared_records(directory, tmp_path)
    assert {r['path'] for r in records} == {'hdf/' + n for n in names + ['meta_data.pkl']}
    verify_records(records, tmp_path)
    (directory / 'title.hdf').write_bytes(b'x' * len('title.hdf'))
    with pytest.raises(ValueError, match='prepared'):
        verify_records(records, tmp_path)


def test_missing_metadata_referenced_hdf_is_rejected(tmp_path):
    (tmp_path / 'meta_data.pkl').write_bytes(pickle.dumps({'title': {'hdf_path': str(tmp_path / 'missing.hdf')}}))
    with pytest.raises(ValueError, match='referenced'):
        prepared_records(tmp_path, tmp_path)
