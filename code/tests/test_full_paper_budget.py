import pytest

from full_paper_budget import code_factor_for_base_budget, same_ordered_components


def test_paper_extra_budget_uses_base_ensemble_cost_in_same_proxy_units():
    assert code_factor_for_base_budget(.5, 539., 123.) == pytest.approx(2.1910569105691056)
    assert code_factor_for_base_budget(0., 539., 123.) == 0.
    assert code_factor_for_base_budget(1., 100., 25.) * 25 == 100


@pytest.mark.parametrize('factor,base,single', [(-1, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_invalid_budget_units_are_rejected(factor, base, single):
    with pytest.raises(ValueError):
        code_factor_for_base_budget(factor, base, single)


def test_prediction_equivalence_requires_identical_order_and_component_artifacts():
    a = {'profile': 'public-scale', 'models': [
        {'binding': 'x', 'artifacts': [{'sha256': 'modelx'}]},
        {'binding': 'y', 'artifacts': [{'sha256': 'modely'}]}]}
    import copy
    b = copy.deepcopy(a)
    assert same_ordered_components(a, b)
    b['models'].reverse()
    assert not same_ordered_components(a, b)
    b = copy.deepcopy(a)
    b['models'][0]['artifacts'][0]['sha256'] = 'changed'
    assert not same_ordered_components(a, b)
    b = copy.deepcopy(a)
    b['profile'] = 'joblight'
    assert not same_ordered_components(a, b)
