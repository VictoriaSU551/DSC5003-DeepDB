"""Regression checks for memory-bounded CSV preparation and join semantics."""
from unittest.mock import patch

import pandas as pd
import pytest

from data_preparation.prepare_single_tables import read_table_csv, prepare_single_table
from ensemble_compilation.graph_representation import SchemaGraph, Table


def make_schema(tmp_path, sample_rate=1.0):
    (tmp_path / 'parent.csv').write_text('1,2000,unused\n2,2001,unused\n3,2002,unused\n', encoding='utf-8')
    (tmp_path / 'child.csv').write_text('10,1,7\n11,1,8\n12,2,9\n13,,10\n', encoding='utf-8')
    schema = SchemaGraph()
    schema.add_table(Table('parent', attributes=['id', 'year', 'text'], irrelevant_attributes=['text'],
                           csv_file_location=str(tmp_path / 'parent.csv'), table_size=3))
    schema.add_table(Table('child', attributes=['id', 'parent_id', 'value'],
                           csv_file_location=str(tmp_path / 'child.csv'), table_size=4,
                           sample_rate=sample_rate))
    schema.add_relationship('child', 'parent_id', 'parent', 'id')
    return schema


def test_unused_text_columns_are_not_materialized(tmp_path):
    schema = make_schema(tmp_path)
    original_read = pd.read_csv

    def bounded_read(*args, **kwargs):
        assert kwargs.get('usecols') == [0, 1], 'Unused text columns would inflate memory on full IMDb'
        return original_read(*args, **kwargs)

    with patch('data_preparation.prepare_single_tables.pd.read_csv', side_effect=bounded_read):
        frame = read_table_csv(schema.tables[0])
    assert list(frame.columns) == ['parent.id', 'parent.year']
    assert frame['parent.id'].tolist() == [1, 2, 3]


@pytest.mark.parametrize('sample_rate', [1.0, 0.5])
def test_multipliers_and_parent_without_children(tmp_path, sample_rate):
    schema = make_schema(tmp_path, sample_rate)
    path = str(tmp_path / 'parent.hdf')
    meta = prepare_single_table(schema, 'parent', path)
    frame = pd.read_hdf(path).set_index('parent.id')
    assert frame['parent.mul_child.parent_id'].tolist() == [2 / sample_rate, 1 / sample_rate, 0]
    assert frame['parent.mul_child.parent_id_nn'].tolist() == [2 / sample_rate, 1 / sample_rate, 1]
    edge = schema.relationships[0].identifier
    assert meta[edge]['length'] == 1
    assert pd.read_hdf(meta[edge]['path'])['parent.id'].tolist() == [3]
    child_meta = prepare_single_table(schema, 'child', str(tmp_path / 'child.hdf'))
    assert child_meta[edge]['length'] == 1 / sample_rate


def test_sampled_hdfs_handle_named_indices(tmp_path):
    import pickle
    from data_preparation.prepare_single_tables import prepare_all_tables
    from data_preparation.join_data_preparation import prepare_sample_hdf
    schema = make_schema(tmp_path)
    prepare_all_tables(schema, str(tmp_path))
    prepare_sample_hdf(schema, str(tmp_path), 100000000, 3)
    with (tmp_path / 'meta_data_sampled.pkl').open('rb') as source:
        metadata = pickle.load(source)
    assert set(metadata) == {'parent', 'child'}
    child = pd.read_hdf(metadata['child']['hdf_path'])
    assert len(child) == 3
    assert child['child.parent_id'].isin([1, 2]).all()
