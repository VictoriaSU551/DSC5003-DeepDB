import hashlib
import copy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_verdict_audit.py'
    assert path.exists(),'Strictly read-only Verdict handoff audit is missing'
    spec=importlib.util.spec_from_file_location('full_verdict_audit',str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_manifest_audit_is_read_only_and_rejects_changed_bytes(tmp_path,monkeypatch):
    m=module();artifact=tmp_path/'runtime.jar';artifact.write_bytes(b'sealed byte artifact')
    body=dict(status='SEALED_EXISTING_SAMPLE_ONLY_VERDICT',artifacts=[dict(path='runtime.jar',bytes=artifact.stat().st_size,sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())])
    body['seal_sha256']=m.bhash(body);manifest=tmp_path/'seal.json';manifest.write_text(json.dumps(body))
    before={p.name:p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    def forbidden(*args,**kwargs):raise AssertionError('Read-only audit attempted execution or network')
    monkeypatch.setattr(subprocess,'run',forbidden);monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(socket,'create_connection',forbidden)
    result=m.verify_manifest(manifest,tmp_path)
    assert result['status']=='PASS_CURRENT_FILES_AND_HISTORICAL_EVIDENCE_ONLY'
    assert before=={p.name:p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifact'):m.verify_manifest(manifest,tmp_path)


def test_default_named_api_rejects_empty_query_subset_even_with_fresh_self_seal(tmp_path):
    m=module()
    assert hasattr(m,'verify'),'Named read-only Verdict contract is missing'
    evaluation=tmp_path/'evaluation.json'
    evaluation.write_text(json.dumps(dict(actual_sample_rows=9997912,population_prior=1000000000,queries=[])))
    record=dict(path=evaluation.name,bytes=evaluation.stat().st_size,sha256=hashlib.sha256(evaluation.read_bytes()).hexdigest())
    body=dict(status='SEALED_EXISTING_SAMPLE_ONLY_VERDICT',artifacts=[record],result_path=evaluation.name,
              historical_physical_calls=dict(point=14,native_ci=14))
    body['seal_sha256']=m.bhash(body);manifest=tmp_path/'seal.json';manifest.write_text(json.dumps(body))
    with pytest.raises(ValueError):m.verify(manifest,tmp_path)


@pytest.mark.parametrize('status,paths',[('WRONG',['a']),('SEALED_EXISTING_SAMPLE_ONLY_VERDICT',[]),('SEALED_EXISTING_SAMPLE_ONLY_VERDICT',['a','a'])])
def test_manifest_rejects_wrong_status_empty_and_duplicate_resealed_lists(tmp_path,status,paths):
    m=module();(tmp_path/'a').write_bytes(b'a')
    record=dict(path='a',bytes=1,sha256=hashlib.sha256(b'a').hexdigest())
    body=dict(status=status,artifacts=[record for _ in paths]);body['seal_sha256']=m.bhash(body)
    manifest=tmp_path/'seal.json';manifest.write_text(json.dumps(body))
    with pytest.raises(ValueError):m.verify_manifest(manifest,tmp_path)


def test_engine_checkpoint_parser_rejects_duplicate_and_missing_physical_calls(tmp_path):
    m=module();assert hasattr(m,'read_physical_calls'),'Strict physical-call completeness checker missing'
    p=tmp_path/'calls.tsv';p.write_text('META\tq\tVeA==\nROW\tq\tVMQ==\nTIME\tq\t1\nTIME\tq\t2\n')
    with pytest.raises(ValueError):m.read_physical_calls(p,{'q'})
    p.write_text('META\tq\tVeA==\nROW\tq\tVMQ==\nTIME\tq\t1\n')
    with pytest.raises(ValueError):m.read_physical_calls(p,{'q','missing'})


def real_evidence():
    m=module()
    paths=[ROOT/m.SQL,ROOT/m.TRUTH,ROOT/(m.OUT+'flights_evaluation.json')]
    if not all(p.exists() for p in paths):pytest.skip('sealed local integration evidence unavailable')
    sqls=paths[0].read_text().splitlines();plans=m.expected_plans(sqls)
    point=m.read_physical_calls(ROOT/(m.OUT+'flights_nobound.tsv'),plans)
    ci=m.read_physical_calls(ROOT/(m.OUT+'flights_subsampling.tsv'),plans)
    return m,json.loads(paths[2].read_text()),json.loads(paths[1].read_text()),sqls,point,ci


def test_real_evaluation_recomputed_complete_scope():
    m,e,t,s,p,c=real_evidence();coverage=m.validate_evaluation(e,t,s,p,c)
    assert len(coverage)==12 and sum(q['truth_groups'] for q in coverage)==331
    assert sum(q['missing'] for q in coverage)==2 and sum(q['extra'] for q in coverage)==0


@pytest.mark.parametrize('mutation',['subset','duplicate','truth_group','missing_flag','adapter_calls','confidence','point_call','ci_call'])
def test_self_resealed_evaluation_cannot_hide_scope_or_call_gaps(mutation):
    m,e,t,s,p,c=real_evidence();e=copy.deepcopy(e);t=copy.deepcopy(t);p=copy.deepcopy(p);c=copy.deepcopy(c)
    if mutation=='subset':e['queries']=e['queries'][:1]
    elif mutation=='duplicate':e['queries'][1]=e['queries'][0]
    elif mutation=='truth_group':t['queries'][2]['groups'].pop()
    elif mutation=='missing_flag':e['queries'][6]['missing']=0
    elif mutation=='adapter_calls':e['queries'][-1]['adapted']['physical_sql_calls']=1
    elif mutation=='confidence':e['queries'][0]['native_ci_confidence']=.9
    elif mutation=='point_call':p.pop('F5.2.adapter1')
    elif mutation=='ci_call':c.pop('F1.1.raw')
    with pytest.raises(ValueError):m.validate_evaluation(e,t,s,p,c)


@pytest.mark.parametrize('field,value',[('successful_engine_queries',23),('same_sample_membership',False),('imported_original_rows',1),('probability',.2)])
def test_golden_receipt_cannot_hide_incomplete_sample_only_contract(monkeypatch,field,value):
    m=module();path=ROOT/(m.OUT+'golden_gate.json')
    if not path.exists():pytest.skip('sealed local golden evidence unavailable')
    receipt=json.loads(path.read_text());receipt[field]=value
    original=m.load
    monkeypatch.setattr(m,'load',lambda root,path:receipt if path==m.OUT+'golden_gate.json' else original(root,path))
    with pytest.raises(ValueError):m.validate_gate(ROOT)
