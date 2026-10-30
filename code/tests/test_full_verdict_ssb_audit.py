"""Pure semantic and forbidden-operation checks; frozen experiment untouched."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[2]


def audit_module():
    p=ROOT/'code/full_verdict_ssb_audit.py'
    assert p.exists(),'Independent read-only SF2 audit is missing'
    spec=importlib.util.spec_from_file_location('verdict_ssb_audit_test',str(p))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def fixture_calls(m):
    core=m.load_core();queries=core.candidate().call_plan(core.candidate().load_queries())
    records=[dict(call=c,process=dict(seconds=.01,peak_rss_bytes=1000),result=dict(call=c,status='RETURNED',rows=[],elapsed_ns=100,error=None)) for c in queries]
    return {'queries':queries},records


def test_call_summary_rejects_missing_duplicate_and_misidentified_native_calls():
    m=audit_module();plan,records=fixture_calls(m)
    assert m.summarize_calls(plan,records)['original_calls']==38
    for bad in (records[:-1],records[:-1]+[records[0]]):
        with pytest.raises(ValueError):m.summarize_calls(plan,bad)
    changed=copy.deepcopy(records);changed[0]['result']['call']['sql']='SELECT 1'
    with pytest.raises(ValueError):m.summarize_calls(plan,changed)


def test_null_intervals_are_visible_and_finite_label_cannot_hide_nan():
    m=audit_module();plan,records=fixture_calls(m)
    selected=next(x for x in records if x['call']['mode']=='subsampling')
    selected['result']['rows']=[dict(key=[],point=1.,point_status='FINITE',ci_status='NULL',interval95=None)]
    result=m.summarize_calls(plan,records)
    assert result['modes']['subsampling']['ci_status_counts']=={'NULL':1}
    selected['result']['rows'][0].update(ci_status='FINITE',interval95=[float('nan'),2.])
    with pytest.raises(ValueError):m.summarize_calls(plan,records)


def test_forbidden_guard_blocks_connection_and_process_launch_and_restores_them():
    m=audit_module();sentinel=lambda *a,**k:None;core=SimpleNamespace(connect=sentinel)
    import subprocess
    original=subprocess.run
    with m.forbid_science(core):
        with pytest.raises(RuntimeError,match='Forbidden'):core.connect()
        with pytest.raises(RuntimeError,match='Forbidden'):subprocess.run(['never-execute'])
        with pytest.raises(RuntimeError,match='Forbidden'):__import__('sqlite3')
    assert core.connect is sentinel and subprocess.run is original


def test_population_summary_preserves_missing_groups_and_component_truth_gap():
    m=audit_module()
    row=dict(key=['A'],status='MISSING_MODEL_GROUP',truth=10,prediction=None,relative_error=None,missing_penalty_relative_error=1.,native_ci95_covers_truth=None,native_ci_status='MISSING_GROUP',point_status='MISSING_GROUP',zero_truth=False)
    comparison=dict(call={'query_no':0,'mode':'subsampling','role':'RAW'},groups=[],population_comparison={'status':'AVAILABLE_EXACT_EXPRESSION_TRUTH','groups':[row]})
    evaluation={'comparisons':[comparison],'adapters':[]}
    result=m.summarize_population(evaluation)
    assert result['raw13']['subsampling']['missing_groups']==1
    assert result['raw13']['subsampling']['mean_relative_error_with_missing_penalty']==1.
    bad={'comparisons':[dict(call={'query_no':10,'mode':'nobound','role':'SUM_REVENUE'},groups=[],population_comparison={'status':'AVAILABLE_EXACT_EXPRESSION_TRUTH','groups':[row]})],'adapters':[]}
    with pytest.raises(ValueError):m.summarize_population(bad)


def test_unrecorded_wal_lsn_is_unavailable_never_zero_bytes():
    m=audit_module()
    budget={'samples':[dict(total_bytes=10,python_rss_bytes=5,owned_database_bytes=3,positive_wal_bytes=0,positive_temp_bytes=0)],'peak_total_bytes':10,'reused_oracle_bytes':2,'wal_lsn_before':None}
    result=m.summarize_resources(budget)
    assert result['wal_generated_bytes'] is None
    assert result['wal_generated_status']=='UNRECORDED_NO_LSN_BASELINE'


def test_cli_output_only_independent_audits_tree_never_sealed_runs(tmp_path,monkeypatch):
    m=audit_module();monkeypatch.setattr(m,'ROOT',tmp_path);calls=[]
    monkeypatch.setattr(m,'audit',lambda:calls.append('audit') or {'status':'FIXTURE'})
    for path in (tmp_path/'output/full/verdict_ssb/runs/sf2_golden_v4/new.json',tmp_path/'output/full/verdict_ssb/new.json',tmp_path/'outside.json'):
        path.parent.mkdir(parents=True,exist_ok=True)
        with pytest.raises(ValueError):m.main(['--output',str(path)])
    assert calls==[]
    allowed=tmp_path/'output/full/verdict_ssb/audits/new.json'
    m.main(['--output',str(allowed)])
    import json
    assert json.loads(allowed.read_text())=={'status':'FIXTURE'} and calls==['audit']
    with pytest.raises(FileExistsError):m.main(['--output',str(allowed)])
    assert calls==['audit']
