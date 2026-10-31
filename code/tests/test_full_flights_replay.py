"""Strict raw-output contracts and once-only Flights reverse replay."""
import importlib
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
import pytest


def module():
    try:return importlib.import_module('full_flights_replay')
    except ModuleNotFoundError:pytest.fail('Independent Flights replay module is missing')


def test_valid_raw_shapes_include_original_scalar_and_grouped_array_pairs():
    import numpy as np
    m=module()
    assert m.normalize_raw(np.array([[3.]]), (np.array([2.]),np.array([4.])),0,[()],True)[()]==dict(prediction=3.,interval=[2.,4.])
    assert m.normalize_raw([('AA',3.),('BB',4.)],[(2.,4.),(3.,5.)],1,[('BB',),('AA',)],True)[('BB',)]['interval']==[3.,5.]
    assert m.normalize_raw([('AA',3.)],None,1,[('AA',)],False)[('AA',)]['prediction']==3.


@pytest.mark.parametrize('predictions,intervals,width,keys,ci',[
    ([('AA',3.)],[(2.,4.),(3.,5.)],1,[('AA',)],True),
    ([('AA',3.),('BB',4.)],[(2.,4.)],1,[('AA',),('BB',)],True),
    ([('AA',3.),('AA',4.)],[(2.,4.),(3.,5.)],1,[('AA',)],True),
    ([('AA',3.)],[(2.,4.)],1,[('BB',)],True),
    ([('AA',3.)],[(2.,4.)],1,[('AA',),('BB',)],True),
    ([('AA',3.,4.)],[(2.,4.)],1,[('AA',)],True),
    ([('AA',3.)],[(2.,3.,4.)],1,[('AA',)],True),
    ([('AA',float('nan'))],[(2.,4.)],1,[('AA',)],True),
    ([('AA',3.)],[(2.,float('inf'))],1,[('AA',)],True),
    ([('AA',3.)],[(4.,2.)],1,[('AA',)],True),
    ([1.,2.],(0.,3.),0,[()],True),
    (3.,(2.,4.),0,[(),()],True),
    ([('AA',3.)],[(2.,4.)],1,[('AA',)],False),
    ([],[],1,[],True),
])
def test_raw_outputs_reject_truncation_duplicates_missing_extra_nonfinite_and_bad_shapes(predictions,intervals,width,keys,ci):
    with pytest.raises(ValueError):module().normalize_raw(predictions,intervals,width,keys,ci)


def test_stored_maps_reject_duplicate_keys_before_dictionary_construction():
    m=module()
    with pytest.raises(ValueError):m.unique_rows([dict(key=['AA']),dict(key=['AA'])],'stored')
    with pytest.raises(ValueError):m.unique_rows([],'stored')


def test_atomic_claim_has_one_concurrent_winner_and_preserves_first_binding(tmp_path):
    m=module();barrier=threading.Barrier(2);path=tmp_path/'claim'
    def claim(value):
        barrier.wait()
        try:m.claim_namespace(path,{'binding':value});return value
        except FileExistsError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,['one','two']))
    assert len([value for value in results if value])==1
    assert m.read_json(path/'claim.json')['binding']['binding']==next(value for value in results if value)


def test_audit_missing_evidence_fails_without_worker(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'OUT',tmp_path)
    def forbidden(*args,**kwargs):pytest.fail('Audit started a worker')
    monkeypatch.setattr(m,'launch_worker',forbidden)
    with pytest.raises(FileNotFoundError):m.audit()


def test_query_replay_grid_rejects_missing_duplicate_nonreverse_or_not_24_calls():
    m=module();work=[dict(query_no=i,sql='q%d'%i,sql_sha256=str(i),expected_groups=1) for i in range(12)]
    rows=[dict(work[i],groups=[{'key':[]}],actual_calls=[{'confidence_intervals':False},{'confidence_intervals':True}]) for i in reversed(range(12))]
    m.require_grid(rows,work)
    for bad in [rows[:-1],rows+[rows[0]],list(reversed(rows)),[dict(rows[0],actual_calls=[])]+rows[1:],
                [dict(rows[0],groups=[])]+rows[1:]]:
        with pytest.raises(ValueError):m.require_grid(bad,work)


def test_original_default_contract_changes_fail_closed():
    m=module()
    def valid(self,query,rdc_spn_selection=False,pairwise_rdc_path=None,dry_run=False,merge_indicator_exp=True,
              max_variants=10,exploit_overlapping=False,debug=False,display_intermediate_results=False,
              exploit_incoming_multipliers=True,confidence_intervals=False,confidence_sample_size=None,return_expectation=False):pass
    m.require_defaults(valid)
    def invalid(self,query,rdc_spn_selection=True):pass
    with pytest.raises(ValueError):m.require_defaults(invalid)


def test_truth_sql_whitespace_is_recorded_while_reference_sql_remains_byte_exact():
    m=module();sql="SELECT COUNT(*) FROM flights WHERE origin='LA' AND  dest='CA';"
    truth=sql.replace('AND  ','AND ')
    identity=m.require_sql_reference(sql,sql,truth)
    assert identity['sql_sha256']!=identity['truth_sql_sha256'] and not identity['truth_sql_byte_equal']
    for reference,wrong_truth in [(truth,truth),(sql,truth.replace("'CA'","'TX'"))]:
        with pytest.raises(ValueError):m.require_sql_reference(sql,reference,wrong_truth)


def test_owned_resource_cap_stops_only_its_child(tmp_path):
    import sys
    m=module()
    report=m.run_guarded([sys.executable,'-B','-c','import time; a=bytearray(4000000); time.sleep(30)'],tmp_path,1024*1024)
    assert report['returncode']!=0 and report['stopped_for_memory']
    assert report['peak_tree_rss_bytes']>1024*1024


def test_internal_worker_also_has_exclusive_once_only_claim(tmp_path):
    m=module();path=tmp_path/'worker'
    m.claim_namespace(path,dict(configuration_sha256='expected',model_sha256=m.MODEL_SHA))
    with pytest.raises(ValueError):m.claim_worker(path,'different')
    m.claim_worker(path,'expected')
    with pytest.raises(FileExistsError):m.claim_worker(path,'expected')


def test_replay_scope_prohibits_sample_data_open_and_restores_readers(tmp_path):
    import builtins
    import numpy as np
    import pandas as pd
    m=module();sample=tmp_path/'sample.npy';sample.write_bytes(b'not read')
    original=(builtins.open,np.load,pd.read_csv,pd.read_hdf)
    with m.prohibit_stages():
        for reader,args in [(builtins.open,(sample,'rb')),(np.load,(sample,)),(pd.read_csv,(sample,)),(pd.read_hdf,(sample,))]:
            with pytest.raises(AssertionError):reader(*args)
    assert (builtins.open,np.load,pd.read_csv,pd.read_hdf)==original


def test_query_record_separates_expected_count_from_group_rows():
    m=module();identity=dict(query_no=11,expected_groups=1)
    record=m.make_query_record(identity,[{'confidence_intervals':False},{'confidence_intervals':True}],[dict(key=['AA'])],0.)
    assert record['expected_groups']==1 and record['groups']==[dict(key=['AA'])]
    with pytest.raises(ValueError):m.make_query_record(identity,[],[],0.)
