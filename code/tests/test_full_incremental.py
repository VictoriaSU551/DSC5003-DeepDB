import copy

import numpy as np
import pytest
from scipy.spatial import distance
from spn.structure.Base import Product, assign_ids, get_nodes_by_type

from rspn.structure.base import Sum
from rspn.structure.leaves import Categorical, IdentityNumericLeaf
from rspn.updates.top_down_updates import cluster_center_update_dataset
from full_incremental import (batch_update, nearest_children, partition_years,
                              save_update_checkpoint, load_update_checkpoint)


def tree():
    children = []
    for values in ([-9999., 1., 2.], [-9999., 8., 10.]):
        leaves = [Categorical([.2, .3, .5], 0, [0], cardinality=10),
                  IdentityNumericLeaf(values, [.1, .4, .5], -9999., [1], cardinality=10)]
        child = Product(children=leaves)
        child.scope = [0, 1]
        child.cardinality = 10
        children.append(child)
    root = Sum([.5, .5], children, [[1., 1.5], [1., 9.]], cardinality=20)
    root.scope = [0, 1]
    assign_ids(root)
    return root


def assert_same(a, b):
    for x, y in zip(get_nodes_by_type(a), get_nodes_by_type(b)):
        assert type(x) is type(y) and x.scope == y.scope
        assert x.cardinality == y.cardinality
        for attr in ('weights', 'unique_vals', 'prob_sum', 'p', 'mean',
                     'inverted_mean', 'square_mean', 'inverted_square_mean', 'null_value_prob'):
            if hasattr(x, attr):
                np.testing.assert_allclose(getattr(x, attr), getattr(y, attr), rtol=1e-10, atol=1e-10)


def test_pooled_updates_match_author_scalar_routing_histograms_and_nulls():
    original, pooled = tree(), tree()
    data = np.array([[i % 3, [-9999., 0., 1.5, 5.25, 12.][i % 5]] for i in range(211)])
    for row in data:
        cluster_center_update_dataset(original, row)
    batch_update(pooled, data)
    assert_same(original, pooled)
    # The structure and routing prototypes remain fixed, as in the paper.
    assert pooled.cluster_centers == [[1., 1.5], [1., 9.]]


def test_routing_preserves_first_minimum_and_author_euclidean_near_ties():
    centers = np.array([[0., 0.], [2., 0.], [1., 5.]])
    rows = np.array([[1., 0.], [1. + 1e-15, 0.], [1. - 1e-15, 0.], [1., 5.]])
    expected = [min(range(3), key=lambda i: distance.euclidean(centers[i], row)) for row in rows]
    assert nearest_children(rows, centers).tolist() == expected


def test_empty_batch_does_not_modify_model():
    model = tree()
    before = copy.deepcopy(model)
    batch_update(model, np.empty((0, 2)))
    assert_same(model, before)


def test_year_partition_keeps_unknown_initial_and_is_exhaustive():
    years = np.array([1990., 2004., 2009., np.nan, 1992.1234])
    initial, later = partition_years(years, 2004, 1992.1234)
    assert initial.tolist() == [True, False, False, True, True]
    assert np.array_equal(initial, ~later)


def test_sealed_batch_resume_matches_continuous_and_rejects_changed_binding(tmp_path):
    data = np.array([[i % 3, float(i % 17)] for i in range(100)])
    expected, resumed = tree(), tree()
    batch_update(expected, data)
    batch_update(resumed, data[:40])
    save_update_checkpoint(tmp_path, resumed, 40, {'input': 'fixed'}, [{'rows': 40}])
    loaded, done, history = load_update_checkpoint(tmp_path, {'input': 'fixed'})
    assert done == 40 and history == [{'rows': 40}]
    batch_update(loaded, data[done:])
    assert_same(expected, loaded)
    with pytest.raises(ValueError, match='binding'):
        load_update_checkpoint(tmp_path, {'input': 'changed'})


def test_checkpoint_model_tampering_is_rejected(tmp_path):
    record = save_update_checkpoint(tmp_path, tree(), 0, {'input': 'fixed'}, [])
    with (tmp_path / record['model_file']).open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='hash'):
        load_update_checkpoint(tmp_path, {'input': 'fixed'})


def test_checkpoint_cursor_tampering_is_rejected(tmp_path):
    import json
    save_update_checkpoint(tmp_path, tree(), 40, {'input': 'fixed'}, [])
    path = tmp_path / 'checkpoint.json'
    record = json.loads(path.read_text())
    record['completed_rows'] = 41
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='receipt hash'):
        load_update_checkpoint(tmp_path, {'input': 'fixed'})
