from types import SimpleNamespace

from ensemble_compilation.spn_ensemble import SPNEnsemble
from full_stable_selection import canonical_greedy_selection


def test_equal_scoring_neighbours_use_lexical_table_order_and_restore():
    spn = SimpleNamespace(table_set={'movie_keyword', 'movie_companies', 'title'},
                          compute_mergeable_relationships=lambda query, neighbour: [])
    ensemble = SPNEnsemble(None, [spn])
    query = SimpleNamespace(table_where_condition_dict={})
    original = SPNEnsemble._greedily_select_next_table
    with canonical_greedy_selection():
        selected = ensemble._greedily_select_next_table(
            query, query, {'movie_keyword', 'movie_companies'}, False, {'title'})
        assert selected[1] == 'movie_companies'
    assert SPNEnsemble._greedily_select_next_table is original


def test_rdc_sum_uses_canonical_pairs_and_accurate_summation():
    ensemble = SPNEnsemble(None)
    query = SimpleNamespace(table_where_condition_dict={'c': ['x=1'], 'a': ['x=1'], 'b': ['x=1']})
    values = {('a.x', 'b.x'): 1e16, ('a.x', 'c.x'): 1., ('b.x', 'c.x'): -1e16}
    with canonical_greedy_selection():
        assert ensemble.merged_rdc_sum({'a', 'b', 'c'}, query, values) == 1.
