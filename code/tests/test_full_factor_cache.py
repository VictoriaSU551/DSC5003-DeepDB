import pytest

from ensemble_compilation.probabilistic_query import IndicatorExpectation
from ensemble_compilation.spn_ensemble import evaluate_factors
from full_factor_cache import model_aware_factor_cache


class Model:
    full_join_size = 100
    def __init__(self, value):
        self.value = value
        self.calls = 0
    def evaluate_indicator_expectation(self, *args, **kwargs):
        self.calls += 1
        return None, self.value


def factor(model):
    return IndicatorExpectation([], [('title', 'production_year>2000')], spn=model, table_set=set())


def value(item, cache):
    return evaluate_factors(False, [1., item], cache)[1]


def test_same_formula_on_different_physical_models_never_reuses_other_value():
    a, b = Model(.2), Model(.8)
    first, second = factor(a), factor(b)
    # This is the upstream omission, independent of any particular learned model.
    assert hash(first) == hash(second)
    with model_aware_factor_cache():
        cache = {}
        assert value(first, cache) == .2
        assert value(second, cache) == .8
        assert value(factor(a), cache) == .2
    assert a.calls == b.calls == 1


def test_hash_adapter_restores_original_even_after_failure():
    original = IndicatorExpectation.__hash__
    with pytest.raises(RuntimeError):
        with model_aware_factor_cache():
            assert IndicatorExpectation.__hash__ is not original
            raise RuntimeError('interrupted inference')
    assert IndicatorExpectation.__hash__ is original
