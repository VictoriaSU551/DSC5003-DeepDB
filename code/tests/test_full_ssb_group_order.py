"""The adapter may only permute aligned group rows before prototype selection."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import full_ssb_group_order as target


def test_paired_order_preserves_technical_identity_and_scope_columns():
    first=(99,[4,2]);second=(17,[8,3]);scopes=['date.year','supplier.city']
    result=target.order_group_pairs(scopes,[first,second],[(1998,'B'),(1997,'A')])
    assert result[0] is scopes
    assert result[1][0] is second and result[1][1] is first
    assert result[2]==[(1997,'A'),(1998,'B')]
    assert first[1]==[4,2] and second[1]==[8,3]


@pytest.mark.parametrize('order',[(0,1,2),(2,0,1),(1,2,0)])
def test_input_permutation_cannot_choose_another_prototype(order):
    rows=[('C',),('A',),('B',)];technical=[(30,),(10,),(20,)]
    out=target.order_group_pairs(['x'],[technical[i] for i in order],[rows[i] for i in order])
    assert out[1:]==([(10,),(20,),(30,)],[('A',),('B',),('C',)])


def test_mixed_null_numeric_string_keys_are_deterministic_and_exact():
    large=2**60+1
    labels=[('x',),(large,),(None,),(1.5,),(True,),(-2,)]
    out=target.order_group_pairs(['x'],list(labels),labels)
    assert out[2]==[(None,),(True,),(-2,),(1.5,),(large,),('x',)]
    assert out[2][4][0] is large


@pytest.mark.parametrize('technical,decoded',[
    ([(1,)],[]), ([(1,)],[(1,2)]), ([(1,2)],[(1,)]),
    ([(1,),(2,)],[(1,),(1.0,)]), ([(1,)],[(math.nan,)]),
    ([(1,)],[(math.inf,)]), ([(1,)],[(object(),)])])
def test_malformed_or_ambiguous_groups_fail_closed(technical,decoded):
    with pytest.raises(ValueError):target.order_group_pairs(['x'],technical,decoded)


def test_empty_rows_stay_empty():
    assert target.order_group_pairs(['x'],[],[])==(['x'],[],[])


def test_context_restores_original_on_exception_and_does_not_modify_other_methods():
    class Ensemble:
        def _evaluate_group_by_spn_ensembles(self,q):return ['x'],[(2,),(1,)],[('B',),('A',)]
        def cardinality(self):return 'unchanged'
    original=Ensemble._evaluate_group_by_spn_ensembles
    cardinality=Ensemble.cardinality
    module=SimpleNamespace(SPNEnsemble=Ensemble)
    with pytest.raises(RuntimeError):
        with target.canonical_group_order(module):
            assert Ensemble()._evaluate_group_by_spn_ensembles(None)[2]==[('A',),('B',)]
            assert Ensemble.cardinality is cardinality
            raise RuntimeError('test restoration')
    assert Ensemble._evaluate_group_by_spn_ensembles is original
    assert Ensemble.cardinality is cardinality


def test_nested_context_restores_outer_then_original():
    class Ensemble:
        def _evaluate_group_by_spn_ensembles(self,q):return ['x'],[(1,)],[('A',)]
    module=SimpleNamespace(SPNEnsemble=Ensemble);original=Ensemble._evaluate_group_by_spn_ensembles
    with target.canonical_group_order(module):
        outer=Ensemble._evaluate_group_by_spn_ensembles
        with target.canonical_group_order(module):assert Ensemble()._evaluate_group_by_spn_ensembles(None)[2]==[('A',)]
        assert Ensemble._evaluate_group_by_spn_ensembles is outer
    assert Ensemble._evaluate_group_by_spn_ensembles is original
