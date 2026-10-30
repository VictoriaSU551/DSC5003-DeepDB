from fractions import Fraction

from full_aqp_tables import sample_estimate, group_error_summary


def test_sample_estimate_uses_actual_rows_and_keeps_avg_count_and_sum_distinct():
    moments = dict(count=1, filter_count=1, sum_integer=30, scale=10)
    assert sample_estimate(moments, 'SUM', 1000, 3) == Fraction(1000)
    assert sample_estimate(moments, 'COUNT', 1000, 3) == Fraction(1000, 3)
    assert sample_estimate(moments, 'AVG', 1000, 3) == Fraction(3)


def test_group_mean_retains_missing_groups_with_explicit_penalty():
    rows = [dict(truth=1000., sample_prediction=1000., sample_group_present=True),
            dict(truth=1., sample_prediction=None, sample_group_present=False)]
    result = group_error_summary(rows)
    assert result['mean_relative_error_with_missing_penalty'] == .5
    assert result['matched_mean_relative_error'] == 0.
    assert result['missing_groups'] == 1
