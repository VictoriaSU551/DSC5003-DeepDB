import pytest

from full_local_truth_eval import align_and_score


def test_relabeling_preserves_prediction_and_exact_integer_truth():
    source = [{'query_no': '0', 'query': 'select count(*) from title t;', 'cardinality_true': '9007199254740993',
               'cardinality_predict': '9007199254740000'}]
    truth = [{'query_no': '0', 'query': 'select count(*) from title t;',
              'cardinality_true': '9007199254740995', 'cardinality_published': '9007199254740993'}]
    rows = align_and_score(source, truth)
    assert rows[0]['local_truth'] == 9007199254740995
    assert rows[0]['published_truth'] == 9007199254740993
    assert source[0]['cardinality_predict'] == '9007199254740000'


def test_equal_row_counts_do_not_permit_wrong_sql_or_reordered_query_id():
    source = [{'query_no': '0', 'query': 'select count(*) from title t;', 'cardinality_true': '3', 'cardinality_predict': '4'}]
    truth = [{'query_no': '0', 'query': 'select count(*) from movie_info m;', 'cardinality_true': '3', 'cardinality_published': '3'}]
    with pytest.raises(ValueError, match='alignment'):
        align_and_score(source, truth)
