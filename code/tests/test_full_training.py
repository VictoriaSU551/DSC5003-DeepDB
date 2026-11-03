import pandas as pd

from full_training import exact_star_size, temporal_partition


def test_exact_outer_join_counts_missing_children_and_correlated_fanouts():
    parents = pd.DataFrame({'title.production_year': [1990, 2010, 1992.1234],
                            'title.mul_a.movie_id': [2, 0, 3],
                            'title.mul_b.movie_id': [4, 5, 0]})
    assert exact_star_size(parents, ['title.mul_a.movie_id', 'title.mul_b.movie_id']) == 16


def test_temporal_partition_keeps_null_years_initial_and_loses_no_rows():
    frame = pd.DataFrame({'title.production_year': [1990, 2011, 1992.1234, 2005]})
    initial, updates = temporal_partition(frame, 2004, 1992.1234)
    assert initial.tolist() == [True, False, True, False]
    assert updates.tolist() == [False, True, False, True]
    assert (initial | updates).all() and not (initial & updates).any()
