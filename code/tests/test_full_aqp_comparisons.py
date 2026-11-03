import pytest

from full_aqp_comparisons import dbest_summary


def test_dbest_missing_truth_group_gets_explicit_penalty():
    groups = [dict(key=['A'], truth=10.), dict(key=['B'], truth=20.)]
    query = dict(status='SUPPORTED_WITH_COVERAGE_GAPS', predictions=[
        dict(group='A', estimate=10., truth_group_present=True, truth_numerator=10, truth_denominator=1)])
    result = dbest_summary(query, groups)
    assert result['missing_groups'] == 1
    assert result['matched_mean_relative_error'] == 0.
    assert result['mean_relative_error_with_missing_penalty'] == .5
    query['predictions'][0]['truth_numerator'] = 11
    with pytest.raises(ValueError, match='truth'):
        dbest_summary(query, groups)


def test_unsupported_query_is_not_a_zero_error_result():
    result = dbest_summary(dict(status='UNSUPPORTED', predictions=[]), [dict(key=[], truth=10.)])
    assert result['mean_relative_error_with_missing_penalty'] is None
