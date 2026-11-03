"""The offline verifier must reject self-resealed scientific/evidence subsets."""
from fractions import Fraction
import builtins
import copy
import importlib
import io
from pathlib import Path
import socket
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import full_scalar_oracle as core
import full_scalar_oracle_run as run


@pytest.fixture
def audit():return importlib.import_module('full_scalar_oracle_audit')


def receipt():
    c=core.workload();pop=dict(core.EXPECTED_ROWS)
    counts={p['id']:0 if p['conditions'] else pop[p['table']] for p in c['predicates']}
    assumptions={t:dict(rows=n,distinct_ids=n,null_ids=0,null_movie_ids=0,orphan_movie_ids=0) for t,n in pop.items()}
    snapshots={t:dict(schema=dict(table=t,oid=i+1,relkind='r',relfilenode=i+1,inherits=False,primary_key=['id'],valid_primary_key=True,
                    columns=[[n,23] for n in run.projection(c,t)]),projection=run.projection(c,t),binary_copy=dict(bytes=100,sha256='a'*64))
               for i,t in enumerate(c['tables'])}
    operations=[]
    for req in run.requests(c):
        if req['kind']=='scalar_aggregate':values=[pop[req['table']],pop[req['table']],0]+[counts[k] for k in req['predicate_ids']]
        else:values=[0,0]
        operations.append(dict(request=req,returned_counts=values,seconds=.1))
    resources=dict(available_memory_bytes=6*1024**3,process_rss_bytes=1024**2,free_disk_bytes=20*1024**3)
    return c,dict(scope=core.SCOPE,population=pop,scalar_counts=counts,assumptions=assumptions,operations=operations,
                  before=snapshots,after=snapshots,resources=[resources]*12,resource_monitor_errors=[],resource_monitor_stopped=True,
                  seconds=2.0,client_pid=123,new_model_calls=0,server_started_or_stopped=False,
                  database_identity=dict(database='deepdb_job',server_version_num='110005',address='127.0.0.1',port=55432,
                       data_directory=str((core.ROOT/'data/postgresql/cluster').resolve()),backend_pid=456,read_only='on',isolation='repeatable read',
                       postmaster_start='synthetic-start',image=str((core.ROOT/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve())),
                  source_boundary='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY')


def test_exact_fraction_predictions_are_recomputed_without_target_labels(audit):
    c,r=receipt();pred=core.predictions(c,r['scalar_counts'],r['population'],r['assumptions'])
    audit.validate_receipt(c,r)
    audit.verify_predictions(c,r,pred)
    pred[0]['estimate']={'numerator':'1','denominator':'1'}
    with pytest.raises(ValueError):audit.verify_predictions(c,r,pred)


@pytest.mark.parametrize('mutation',['subset','extra','duplicate_operation','wrong_sql','wrong_count','snapshot','missing_table','bad_schema','negative_seconds','nonfinite_seconds','wrong_db','readonly','source_claim','author_claim'])
def test_receipt_tampering_fails_even_if_its_outer_json_is_resealed(audit,mutation):
    c,r=receipt()
    if mutation=='subset':r['scalar_counts'].pop(next(iter(r['scalar_counts'])))
    if mutation=='extra':r['scalar_counts']['made-up']=0
    if mutation=='duplicate_operation':r['operations'][1]=r['operations'][0]
    if mutation=='wrong_sql':r['operations'][0]['request']=dict(r['operations'][0]['request'],sql='SELECT 0')
    if mutation=='wrong_count':r['operations'][0]['returned_counts'][0]+=1
    if mutation=='snapshot':r['after']=dict(r['after']);r['after']['title']=dict(r['after']['title'],binary_copy=dict(bytes=99,sha256='b'*64))
    if mutation=='missing_table':r['before']=dict(r['before']);r['before'].pop('title')
    if mutation=='bad_schema':r['before']['title']['schema']['relkind']='v'
    if mutation=='negative_seconds':r['operations'][0]['seconds']=-1
    if mutation=='nonfinite_seconds':r['seconds']=float('nan')
    if mutation=='wrong_db':r['database_identity']['database']='deepdb_verdict'
    if mutation=='readonly':r['database_identity']['read_only']='off'
    if mutation=='source_claim':r['source_boundary']='ORIGINAL_CSV_FULL_IDENTITY'
    if mutation=='author_claim':r['scope']=dict(r['scope'],author_Perfect_Selectivities_reproduction_complete=True)
    with pytest.raises(ValueError):audit.validate_receipt(c,r)


def test_qerror_floor_is_separate_and_zero_estimate_remains_zero(audit):
    assert audit.qerror(Fraction(0),10,floor=1)==10
    assert audit.qerror(Fraction(0),0,floor=1)==1
    assert audit.qerror(Fraction(1,2),10,floor=1)==10
    with pytest.raises(ValueError):audit.qerror(Fraction(0),10,floor=0)


def test_default_verify_missing_result_is_read_only_and_never_imports_database(audit,tmp_path,monkeypatch):
    def forbidden(*a,**k):pytest.fail('Forbidden operation during offline verification')
    monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(socket,'socket',forbidden)
    monkeypatch.setattr(run,'connect',forbidden);monkeypatch.setattr(run,'atomic',forbidden)
    with pytest.raises((ValueError,FileNotFoundError)):audit.verify(tmp_path/'missing',root=tmp_path)


def test_required_result_set_is_not_accepted_as_empty_or_partial(audit,tmp_path):
    for name in ('final_seal.json','lifecycle.json'):(tmp_path/name).write_text('{}')
    with pytest.raises(ValueError):audit.verify(tmp_path,root=tmp_path)


@pytest.mark.parametrize('mutation',['short','monitor_failed','monitor_running'])
def test_resource_phase_or_monitor_evidence_cannot_be_omitted(audit,mutation):
    c,r=receipt();r['resources']=r['resources']*12
    r['resource_monitor_errors']=[];r['resource_monitor_stopped']=True
    if mutation=='short':r['resources']=r['resources'][:1]
    if mutation=='monitor_failed':r['resource_monitor_errors']=['cancelled late memory violation']
    if mutation=='monitor_running':r['resource_monitor_stopped']=False
    with pytest.raises(ValueError):audit.validate_receipt(c,r)


def test_elapsed_total_cannot_exceed_declared_window(audit):
    c,r=receipt();r['seconds']=1801
    with pytest.raises(ValueError):audit.validate_receipt(c,r)


@pytest.fixture
def complete_run(audit,tmp_path,monkeypatch):
    # All metadata/source bytes are real; only external runtime discovery and
    # scientific collection are replaced by a tiny explicit synthetic fixture.
    original=core.ROOT
    for name in list(run.SOURCES)+[core.QUERY_FILE]+list(run.INPUTS):
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((original/name).read_bytes())
    runtime=tmp_path/'.runtime/synthetic.dll';runtime.parent.mkdir(exist_ok=True);runtime.write_bytes(b'synthetic runtime fixture')
    monkeypatch.setattr(core,'__file__',str(tmp_path/'code/full_scalar_oracle.py'))
    monkeypatch.setattr(run,'__file__',str(tmp_path/'code/full_scalar_oracle_run.py'))
    monkeypatch.setattr(audit,'__file__',str(tmp_path/'code/full_scalar_oracle_audit.py'))
    monkeypatch.setattr(run,'runtime_paths',lambda root:[runtime])
    plan=run.build_plan(tmp_path);p=tmp_path/run.BASE/'plans/candidate.json';p.parent.mkdir(parents=True);run.atomic(p,plan)
    approval=run.approval_template(plan,p,tmp_path);approval.update(status='APPROVED_BY_ROOT_FOR_SINGLE_SCALAR_ORACLE_RUN',root_review_reference='SYNTHETIC_TEST_ONLY_NOT_SCIENCE')
    a=tmp_path/'approval.json';run.atomic(a,approval)
    _,r=receipt();r['database_identity']['data_directory']=str(tmp_path/'data/postgresql/cluster')
    r['database_identity']['image']=str(tmp_path/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe')
    monkeypatch.setattr(run,'collect',lambda *_:copy.deepcopy(r))
    run.execute(p,a,root=tmp_path)
    return tmp_path/run.BASE/'runs'/plan['binding'][:20],tmp_path,runtime


def reseal(directory,root):
    v=run.read(directory/'verification.json');v.update(counts=run.artifact(directory/'counts.json',root),predictions=run.artifact(directory/'predictions.json',root));run.atomic(directory/'verification.json',v)
    life=run.read(directory/'lifecycle.json');life['verification_sha256']=run.digest(directory/'verification.json');run.atomic(directory/'lifecycle.json',life)
    seal=dict(schema='scalar-oracle-final-v1',binding=life['binding'],files={n:run.artifact(directory/n,root) for n in run.FILES})
    run.atomic(directory/'final_seal.json',dict(seal,self_sha256=core.object_hash(seal)))


def test_complete_public_verifier_uses_no_process_database_network_or_write(audit,complete_run,monkeypatch):
    directory,root,_=complete_run
    before={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    def forbidden(*a,**k):pytest.fail('Forbidden operation during complete offline audit')
    monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(socket,'socket',forbidden)
    monkeypatch.setattr(run,'connect',forbidden);monkeypatch.setattr(run,'atomic',forbidden);monkeypatch.setattr(run,'collect',forbidden)
    original_import=builtins.__import__;original_open=io.open
    def checked_import(name,*a,**k):
        if name.startswith(('psycopg2','sqlite3','pickle')):forbidden()
        return original_import(name,*a,**k)
    def readonly_open(file,mode='r',*a,**k):
        if any(c in mode for c in 'wax+'):forbidden()
        return original_open(file,mode,*a,**k)
    monkeypatch.setattr(builtins,'__import__',checked_import);monkeypatch.setattr(io,'open',readonly_open)
    verified=audit.verify(root=root)
    assert verified['status']=='PASS_READ_ONLY_LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY'
    assert verified['queries']==70 and verified['scalar_predicates']==50
    assert verified['new_model_calls']==verified['new_database_calls']==0
    assert verified['scope']['author_Perfect_Selectivities_reproduction_complete'] is False
    after={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert before==after


@pytest.mark.parametrize('mutation',['result_subset','query_subset','tainted','runtime_changed','source_changed','scope_bool_to_int','unexpected_file'])
def test_full_public_verifier_refuses_tampering_after_all_results_resealed(audit,complete_run,mutation):
    directory,root,runtime=complete_run
    if mutation=='result_subset':
        seal=run.read(directory/'final_seal.json');seal['files'].pop('counts.json');body={k:v for k,v in seal.items() if k!='self_sha256'};seal['self_sha256']=core.object_hash(body);run.atomic(directory/'final_seal.json',seal)
    if mutation=='query_subset':
        pred=run.read(directory/'predictions.json');pred['queries'].pop();run.atomic(directory/'predictions.json',pred);reseal(directory,root)
    if mutation=='tainted':
        life=run.read(directory/'lifecycle.json');life['status']='TAINTED';run.atomic(directory/'lifecycle.json',life);reseal(directory,root)
    if mutation=='runtime_changed':runtime.write_bytes(b'mutated installed runtime')
    if mutation=='source_changed':(root/'code/full_scalar_oracle.py').write_bytes(b'mutated actual source')
    if mutation=='scope_bool_to_int':
        pred=run.read(directory/'predictions.json');pred['scope']['full_paper_reproduction_complete']=0;run.atomic(directory/'predictions.json',pred);reseal(directory,root)
    if mutation=='unexpected_file':(directory/'unexpected.json').write_text('{}')
    with pytest.raises(ValueError):audit.verify(directory,root=root)


def test_new_reviewed_attempt_can_use_new_namespace_without_changing_method(audit,complete_run):
    directory,root,_=complete_run;prior=run.read(directory/'plan.json')
    next_plan=run.build_plan(root,attempt='retry_after_tainted_01')
    assert next_plan['binding']!=prior['binding']
    assert next_plan['contract']==prior['contract'] and next_plan['dependencies']==prior['dependencies']
    assert {k:v for k,v in next_plan.items() if k not in {'binding','attempt'}}=={k:v for k,v in prior.items() if k not in {'binding','attempt'}}
    for bad in ['../old','',True,'A'*100]:
        with pytest.raises(ValueError):run.build_plan(root,attempt=bad)
