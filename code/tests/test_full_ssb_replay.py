"""Fresh-process reverse replay uses exact identities and explicit tolerances."""
import copy
import importlib
import sys
from contextlib import nullcontext
from types import SimpleNamespace
import pytest


def query():
    return {'query_no':0,'query_name':'S1.1','sql':'select sum(x) from t;',
            'groups':[{'key':['A'],'prediction':100.,'model_interval':[90.,110.],'status':'MATCHED'},
                      {'key':['B'],'prediction':200.,'model_interval':[180.,220.],'status':'EXTRA_MODEL_GROUP'}]}


def test_group_order_does_not_matter_but_actual_values_are_compared():
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    actual['groups'].reverse();actual['groups'][0]['prediction']+=1e-8
    result=module.compare_query(baseline,actual)
    assert result['status']=='PASS' and result['point_values_compared']==2 and result['interval_endpoints_compared']==4
    assert result['max_absolute_difference']>0


@pytest.mark.parametrize('kind',['missing','extra','duplicate'])
def test_group_identity_set_must_be_exact(kind):
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    if kind=='missing':actual['groups'].pop()
    elif kind=='extra':actual['groups'].append({'key':['C'],'prediction':1.,'model_interval':None})
    else:actual['groups'].append(copy.deepcopy(actual['groups'][0]))
    with pytest.raises(ValueError,match='group'):module.compare_query(baseline,actual)


def test_copied_query_identity_or_changed_sql_is_rejected():
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    actual['sql']='select sum(y) from t;'
    with pytest.raises(ValueError,match='identity'):module.compare_query(baseline,actual)


def test_numerical_difference_outside_explicit_tolerance_is_rejected():
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    actual['groups'][0]['prediction']+=.01
    with pytest.raises(ValueError,match='tolerance'):module.compare_query(baseline,actual)


def test_source_or_model_change_is_rejected():
    module=importlib.import_module('full_ssb_replay')
    with pytest.raises(ValueError,match='changed'):
        module.require_same_snapshot({'model':'a','dependencies':'x'},{'model':'b','dependencies':'x'})


def test_verify_is_read_only_and_never_creates_missing_replay(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_replay');monkeypatch.setattr(module,'OUTPUT',tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('Read-only verify must not start replay/inference/preparation')
    monkeypatch.setattr(module,'replay',forbidden)
    with pytest.raises(FileNotFoundError):module.verify()
    assert not list(tmp_path.iterdir())


def test_nonfinite_points_are_never_certified_by_null_equals_null():
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    baseline['groups'][0]['prediction']=None;actual['groups'][0]['prediction']=None
    with pytest.raises(ValueError,match='Nonfinite point'):module.compare_query(baseline,actual)


def test_same_missing_interval_is_explicitly_counted_as_gap():
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    baseline['groups'][0]['model_interval']=None;actual['groups'][0]['model_interval']=None
    result=module.compare_query(baseline,actual)
    assert result['matching_missing_or_nonfinite_interval_groups']==1
    assert result['interval_endpoints_compared']==2


def test_nonfinite_ci_raw_state_must_match_exactly():
    module=importlib.import_module('full_ssb_replay');baseline=query();actual=copy.deepcopy(baseline)
    for item in (baseline,actual):
        item['groups'][0]['model_interval']=None
        item['nonfinite_original_intervals']=[{'key':['A'],'raw':'(nan, nan)'}]
    assert module.compare_query(baseline,actual)['matching_explicit_nonfinite_ci_groups']==1
    actual['nonfinite_original_intervals'][0]['raw']='(-inf, inf)'
    with pytest.raises(ValueError,match='nonfinite CI pattern'):module.compare_query(baseline,actual)


@pytest.mark.parametrize('points,ci_rows,intervals',[
    ([['A',100.]],[['A',100.],['EXTRA',200.]],[(90.,110.)]),
    ([['A',100.]],[['A',100.]],[(90.,110.),(180.,220.)]),
    ([['A',100.],['B',200.]],[['A',100.],['A',100.]],[(90.,110.),(90.,110.)]),
    ([['A',100.],['B',200.]],[['A',100.],['EXTRA',200.]],[(90.,110.),(180.,220.)]),
    ([['A',100.]],[['A',100.],['EXTRA',200.]],None),
])
def test_execute_query_rejects_all_raw_ci_length_and_identity_gaps(monkeypatch,points,ci_rows,intervals):
    module=importlib.import_module('full_ssb_replay')
    class Ensemble:
        schema_graph=object()
        def evaluate_query(self,query,confidence_intervals,**kwargs):
            return (intervals,ci_rows) if confidence_intervals else (None,points)
    monkeypatch.setitem(sys.modules,'ensemble_compilation.spn_ensemble',SimpleNamespace(read_ensemble=lambda *a,**k:Ensemble()))
    monkeypatch.setitem(sys.modules,'evaluation.utils',SimpleNamespace(parse_query=lambda *a:SimpleNamespace(group_bys=['x'])))
    monkeypatch.setitem(sys.modules,'full_factor_cache',SimpleNamespace(model_aware_factor_cache=nullcontext))
    with pytest.raises(ValueError,match='CI'):
        module.execute_query(0,'select x,sum(y) from t group by x;','S1.1','unused.pkl',100)


def test_worker_refuses_preoccupied_namespace_even_without_lifecycle(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_replay')
    monkeypatch.setattr(module,'OUTPUT',tmp_path)
    monkeypatch.setattr(module,'source_snapshot',lambda:{'fixture':'snapshot'})
    monkeypatch.setattr(module,'digest',lambda path:'pinned-source')
    binding={'source_snapshot_sha256':module.value_hash({'fixture':'snapshot'}),'replay_source_sha256':'pinned-source',
             'relative_tolerance':module.RTOL,'absolute_tolerance':module.ATOL,
             'hash_seed':module.HASH_SEED,'random_seed':module.RANDOM_SEED}
    home=tmp_path/'runs'/module.value_hash(binding);home.mkdir(parents=True)
    (home/'preserved.txt').write_text('do not change',encoding='utf-8')
    monkeypatch.setenv('PYTHONHASHSEED',str(module.HASH_SEED))
    def forbidden(*args):raise AssertionError('Preoccupied namespace must fail before reading or inference')
    monkeypatch.setattr(module,'read',forbidden)
    with pytest.raises(ValueError,match='namespace'):module.worker()
    assert sorted(path.name for path in home.iterdir())==['preserved.txt']
    assert not (tmp_path/'last_run.json').exists()
