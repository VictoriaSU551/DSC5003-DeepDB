import math
import pytest

from full_evaluation import q_error, numeric_summary


def test_zero_prediction_does_not_become_a_perfect_estimate():
    assert math.isinf(q_error(0, 9))
    assert q_error(18, 9) == 2
    with pytest.raises(ValueError):
        q_error(4, 0)


def test_summary_preserves_infinite_failures():
    result = numeric_summary([1, 2, math.inf])
    assert result['infinite_count'] == 1
    assert result['max'] == 'inf'
