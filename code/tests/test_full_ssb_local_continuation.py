"""Synthetic continuation contracts; never verify real parents or run models."""
import copy
from contextlib import contextmanager
import importlib
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))


def module():
    return importlib.import_module('full_ssb_local_continuation')


def candidate_fixture(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    env={'actual_inference':'unchanged'};forward={'queries':'unchanged'}
    parent=dict(report=dict(directory=str(tmp_path/'parent'),prepared_directory='prepared'),model_path='model.pkl')
    monkeypatch.setattr(m.prior_run,'read_plan',lambda *a:dict(dependencies={'environment':env}))
    monkeypatch.setattr(m,'accept_forward',lambda *a:(forward,[{'path':'accepted-forward'}],[{'path':'old-failure'}]))
    monkeypatch.setattr(m,'worker_environment',lambda:env)
    monkeypatch.setattr(m.old,'parent_snapshot',lambda p:{'original_formal':'unchanged'})
    monkeypatch.setattr(m.old,'run_directory',lambda p:tmp_path/'old')
    monkeypatch.setattr(m,'artifact',lambda p:dict(path=str(p),bytes=1,sha256='a'*64))
    monkeypatch.setattr(m,'code_snapshot',lambda:{'two_sources':'fixture'})
    monkeypatch.setattr(m,'consumer_records',lambda *a:[{'path':'consumed-unchanged'}])
    return m,parent


def test_reviewed_attempts_change_namespace_without_changing_scientific_inputs(tmp_path,monkeypatch):
    m,parent=candidate_fixture(tmp_path,monkeypatch)
    a=m.candidate_from_parent(tmp_path/'old-plan.json','sha',parent,attempt_id='initial')
    b=m.candidate_from_parent(tmp_path/'old-plan.json','sha',parent,attempt_id='ram_retry_02')
    assert a['schema']==b['schema']=='local_ssb_canonical_continuation_plan_v2'
    assert a['attempt_id']=='initial' and b['attempt_id']=='ram_retry_02'
    review=lambda c:dict(c,status='ROOT_REVIEWED_CONTINUATION_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    assert m.run_directory(review(a))!=m.run_directory(review(b))
    assert {k:v for k,v in a.items() if k!='attempt_id'}=={k:v for k,v in b.items() if k!='attempt_id'}


@pytest.mark.parametrize('bad',['','../retry','retry/a','with space','retry.1','\u00e9','a'*33,None,True,1])
def test_invalid_attempt_is_rejected_before_prior_plan_or_scientific_source_access(tmp_path,monkeypatch,bad):
    m=module();monkeypatch.setattr(m.prior_run,'read_plan',lambda *a:pytest.fail('invalid attempt reached input audit'))
    with pytest.raises(ValueError,match='attempt'):
        m.candidate_from_parent(tmp_path/'old-plan.json','sha',{},attempt_id=bad)


def test_public_complete_result_retains_operational_attempt_without_second_parent_F(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);run=tmp_path/'run'
    d=lambda p:dict(path=str(p),bytes=1,sha256='a'*64)
    r=dict(directory=str(run),attempt_id='ram_retry_02',variant='variant',evaluation_variant='evaluation',
        plan={'attempt_id':'ram_retry_02'},plan_path='plan.json',model_path='model',model_sha256='c'*64,
        queries=[],evaluation_binding={},original_mismatch=d('mismatch'),forward=d('forward'),reverse=d('reverse'))
    monkeypatch.setattr(m,'read',lambda p:r);monkeypatch.setattr(m,'artifact',d)
    monkeypatch.setattr(m,'verify_publication',lambda report,parent:[])
    monkeypatch.setattr(m,'collect_parent',lambda:pytest.fail('private reconstruction cannot add an F'))
    p={'published_result':d('original')}
    checked=m._verify_complete(p)
    assert checked['attempt_id']==r['attempt_id']==checked['dependencies']['attempt_id']


def test_public_artifact_reconstruction_rebuilds_the_same_reviewed_attempt(tmp_path,monkeypatch):
    m=module();runner=importlib.import_module('full_ssb_local_continuation_run')
    monkeypatch.setattr(m,'ROOT',tmp_path);calls=[]
    plan=dict(attempt_id='ram_retry_02',old_plan=dict(path='old.json',sha256='oldsha'))
    r=dict(plan_path='plan.json',plan_file_sha256='plansha',root_final_resources={},root_admission_resources={})
    monkeypatch.setattr(runner,'read_plan',lambda *a:plan)
    monkeypatch.setattr(m,'report_body',lambda *a:r)
    class Rebuilt(Exception):pass
    def rebuild(path,sha,parent,attempt_id='initial'):
        calls.append(attempt_id);raise Rebuilt('stop after real reconstruction dispatch')
    monkeypatch.setattr(m,'candidate_from_parent',rebuild)
    with pytest.raises(Rebuilt):m.complete_artifacts(plan,r,{'original_parent':'fixture'})
    assert calls==['ram_retry_02']


def query(i):
    return dict(query_no=i,query_name='Q'+str(i),sql='SQL'+str(i),groups=[dict(key=[i],prediction=10,model_interval=[8,12])],
        nonfinite_original_intervals=[],original_query_evaluator_calls=2,model_loads=1)


def result(m):
    return dict(status=m.REVERSE_PASS,scope=m.SCOPE,execution_protocol=m.PROTOCOL,phase='REVERSE',queries=[query(i) for i in range(13)],
        execution_order=list(reversed(range(13))),actual_model_loads=13,actual_evaluator_calls=26,evaluator_modes=[False,True]*13,
        environment=dict(PYTHONHASHSEED='173',random_seed=74031,numpy_seed=74031,process_id=55,thread_limits={k:'1' for k in m.THREADS}),
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,historical_reverse_accepted=False)


def test_reverse_accounting_preserves_original_calls_and_exact_scope():
    m=module();r=result(m);m.validate_reverse(r)
    assert r['actual_model_loads']==13 and r['actual_evaluator_calls']==26


@pytest.mark.parametrize('field,value',[
    ('actual_model_loads',12),('actual_evaluator_calls',25),('actual_evaluator_calls',True),('execution_order',list(range(13))),
    ('evaluator_modes',[True,False]*13),('author_different_groups',0),('author_reproduction_complete',True),
    ('historical_reverse_accepted',True),('full_paper_reproduction_complete',True),('scope','AUTHOR_SSB'),('execution_protocol','old')])
def test_wrong_reverse_accounting_or_author_claim_is_rejected(field,value):
    m=module();r=result(m);r[field]=value
    with pytest.raises(ValueError):m.validate_reverse(r)


@pytest.mark.parametrize('change',['hash','seed','thread','pid','query_count','query_order','per_query_calls','per_query_loads'])
def test_fresh_worker_and_per_query_counts_are_required(change):
    m=module();r=result(m)
    if change=='hash':r['environment']['PYTHONHASHSEED']='0'
    if change=='seed':r['environment']['numpy_seed']=1
    if change=='thread':r['environment']['thread_limits'][m.THREADS[0]]='2'
    if change=='pid':r['environment']['process_id']=True
    if change=='query_count':r['queries'].pop()
    if change=='query_order':r['queries'].reverse()
    if change=='per_query_calls':r['queries'][0]['original_query_evaluator_calls']=1
    if change=='per_query_loads':r['queries'][0]['model_loads']=0
    with pytest.raises(ValueError):m.validate_reverse(r)


def test_consumer_paths_have_exact_runtime_roles_and_no_raw_history(tmp_path):
    m=module();env=dict(complete=dict(sources={'code/a.py':'x'},spflow_sources={'a.py':'x'},sqlparse_sources={'b.py':'x'}),
        frozen_sources={'code/b.py':'x'},physical_native_libraries={'.venv/a.dll':'x'},python_base_native_files={'.runtime/python/python.exe':'x'},
        actual_module_roots={'numpy':dict(path='.venv/numpy/__init__.py')},python_executable=dict(path=str(tmp_path/'.venv/Scripts/python.exe')),
        python_base_executable=dict(path='.runtime/python/python.exe'),operational_launcher=dict(path='code/ops.py'))
    paths=m.environment_paths(env,tmp_path)
    assert paths=={'code/a.py','code/b.py','.venv/a.dll','.runtime/python/python.exe','.venv/numpy/__init__.py','.venv/Scripts/python.exe',
        '.venv/Lib/site-packages/spn/a.py','.venv/Lib/site-packages/sqlparse/b.py','code/ops.py'}
    assert not any('/data/' in p or '/chunks/' in p for p in paths)


def test_closure_rejects_empty_duplicate_missing_changed_and_extra_records(tmp_path):
    m=module();p=tmp_path/'a';p.write_text('a');r=m.artifact(p,tmp_path)
    assert m.check_records([r],tmp_path)==[r]
    for records in [[],[r,r],[dict(r,sha256='0'*64)],[dict(r,path='absent')]]:
        with pytest.raises((ValueError,FileNotFoundError)):m.check_records(records,tmp_path)


def test_public_verify_refuses_absence_before_parent_F(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'collect_parent',lambda:pytest.fail('missing result must not trigger F'))
    with pytest.raises(ValueError):m.verify_canonical()


def test_public_verify_delegates_one_parent_and_never_executes_worker(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);path=tmp_path/m.RESULT;path.parent.mkdir(parents=True);path.write_text('{}')
    calls=[];proof=object();monkeypatch.setattr(m,'collect_parent',lambda:calls.append('F') or proof)
    monkeypatch.setattr(m,'_verify_complete',lambda parent:dict(parent=parent))
    monkeypatch.setattr(m,'execute_reverse',lambda *a:pytest.fail('verify must not infer'))
    assert m.verify_canonical()==dict(parent=proof) and calls==['F']


def adopted(tmp_path,monkeypatch):
    m=module();run=tmp_path/'old';run.mkdir();parent={'summary':'original'};plan={'parent':parent};forward={'accepted':'FORWARD'};calls=[]
    monkeypatch.setattr(m.old,'run_directory',lambda plan,root=tmp_path:run)
    monkeypatch.setattr(m.old,'parent_snapshot',lambda p:p)
    def phase(p,which,full,root):calls.append(('science',which));assert p==plan and full==parent;return forward
    monkeypatch.setattr(m.old,'_verify_phase',phase)
    monkeypatch.setattr(m.old,'_phase_artifacts',lambda *a:[])
    monkeypatch.setattr(m.prior_run,'verify_child',lambda p,which,root:calls.append(('owned',which)) or [])
    for name,value in [('forward/seal.json',{}),('root_control/lifecycle.json',dict(status='TAINTED')),
        ('reverse_control/lifecycle.json',dict(status='TAINTED')),('reverse_control/monitor.json',dict(status='STOPPED',stop_reason='storage scan stale'))]:m.atomic(run/name,value)
    return m,run,parent,plan,forward,calls


def test_adopt_only_complete_forward_and_keep_old_root_tainted(tmp_path,monkeypatch):
    m,run,parent,p,f,calls=adopted(tmp_path,monkeypatch)
    before=(run/'root_control/lifecycle.json').read_bytes()
    actual,records,history=m.accept_forward(p,parent,tmp_path)
    assert actual==f and calls==[('science','FORWARD'),('owned','FORWARD')]
    assert len(records)==1 and len(history)==3 and before==(run/'root_control/lifecycle.json').read_bytes()


@pytest.mark.parametrize('bad',['root_pass','reverse_pass','not_stale','has_reverse','wrong_parent'])
def test_ineligible_history_cannot_be_adopted_or_repaired(tmp_path,monkeypatch,bad):
    m,run,parent,p,f,calls=adopted(tmp_path,monkeypatch)
    if bad=='root_pass':m.atomic(run/'root_control/lifecycle.json',dict(status='PASS'))
    if bad=='reverse_pass':m.atomic(run/'reverse_control/lifecycle.json',dict(status='PASS'))
    if bad=='not_stale':m.atomic(run/'reverse_control/monitor.json',dict(status='STOPPED',stop_reason='different failure'))
    if bad=='has_reverse':(run/'reverse').mkdir()
    if bad=='wrong_parent':p['parent']={'other':True}
    with pytest.raises(ValueError):m.accept_forward(p,parent,tmp_path)


def consumed(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'PINS',{'code/frozen.py':'x'})
    env=dict(complete=dict(sources={'code/algorithm.py':'x'},spflow_sources={'a.py':'x'},sqlparse_sources={'b.py':'x'}),
        frozen_sources={},physical_native_libraries={'.venv/a.dll':'x'},python_base_native_files={'.runtime/python/python.exe':'x'},actual_module_roots={},
        python_executable=dict(path='.venv/Scripts/python.exe'),python_base_executable=dict(path='.runtime/python/python.exe'),operational_launcher=dict(path='code/ops.py'),
        generator_runtime={'artifacts':[dict(path='data/raw.csv')]})
    forward=dict(phase='FORWARD',status='PASS_CANONICAL_FORWARD_EVALUATION',parent={},group_order_adapter_sha256=m.old.ADAPTER_SHA,
        evaluation_directory=str(tmp_path/'forward_queries'),queries=[query(i) for i in range(13)])
    for i,q in enumerate(forward['queries']):
        m.atomic(tmp_path/'forward_queries'/('query_%02d.json'%i),q);m.atomic(tmp_path/'forward_queries'/('query_%02d.seal.json'%i),{})
    m.atomic(tmp_path/'forward.json',forward)
    plan=dict(codes={'synthetic':'v'},worker_environment=env,parent={},forward=m.artifact(tmp_path/'forward.json',tmp_path),worker_roles={k:dict(path=k+'.bin') for k in ('model','moments','truth')})
    for p in m.consumer_paths(plan,forward,tmp_path):
        path=tmp_path/p
        if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_text('tiny fixture')
    plan['worker_artifacts']=m.consumer_records(plan,forward,tmp_path)
    monkeypatch.setattr(m,'code_snapshot',lambda:plan['codes']);monkeypatch.setattr(m,'worker_environment',lambda:env)
    return m,plan,forward


def test_worker_hashes_exact_consumed_closure_without_full_parent_or_raw_history(tmp_path,monkeypatch):
    m,p,f=consumed(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'collect_parent',lambda:pytest.fail('worker cannot recurse into full F'))
    assert m.verify_worker_inputs(p)==f
    paths={d['path'] for d in p['worker_artifacts']}
    assert all(k+'.bin' in paths for k in ('model','moments','truth'))
    assert 'data/raw.csv' not in paths and not any('/reverse_control/' in x or '/chunks/' in x for x in paths)


@pytest.mark.parametrize('bad',['missing','extra','duplicate','model','runtime','query_alias','environment'])
def test_worker_consumed_subset_superset_or_changed_input_is_rejected(tmp_path,monkeypatch,bad):
    m,p,f=consumed(tmp_path,monkeypatch)
    if bad=='missing':p['worker_artifacts'].pop()
    if bad=='extra':extra=tmp_path/'extra';extra.write_text('x');p['worker_artifacts'].append(m.artifact(extra,tmp_path))
    if bad=='duplicate':p['worker_artifacts'].append(p['worker_artifacts'][0])
    if bad=='model':(tmp_path/'model.bin').write_text('changed')
    if bad=='runtime':(tmp_path/'.venv/a.dll').write_text('changed')
    if bad=='query_alias':m.atomic(tmp_path/'forward_queries/query_00.json',query(1))
    if bad=='environment':monkeypatch.setattr(m,'worker_environment',lambda:{})
    with pytest.raises(ValueError):m.verify_worker_inputs(p)


def test_reverse_enters_import_contexts_before_seed_and_calls_thirteen_in_reverse(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    import numpy as np
    import full_ssb_group_order as adapter
    import full_ssb_replay as helper
    import full_ssb_native_replay as native
    observed={'loads':0,'modes':[]};events=[]
    @contextmanager
    def order():events.append('adapter entered');np.random.seed(1);yield
    @contextmanager
    def observing():events.append('observer entered');yield observed
    @contextmanager
    def guarding(roots):events.append('guard entered');yield
    def execute(i,sql,name,path,rows):
        assert events[:3]==['adapter entered','observer entered','guard entered']
        assert np.random.get_state()[1][0]==74031
        events.append(i);observed['loads']+=1;observed['modes'].extend([False,True]);return query(i)
    monkeypatch.setattr(adapter,'canonical_group_order',order);monkeypatch.setattr(m.old,'observe_evaluation',observing)
    monkeypatch.setattr(native,'deny_raw_data_access',guarding);monkeypatch.setattr(helper,'execute_query',execute)
    p=dict(worker_artifacts=[],worker_roles=dict(model=dict(path='model.pkl')),prepared_directory=str(tmp_path/'prepared'))
    f=dict(queries=[query(i) for i in range(13)],coverage={'groups':13})
    monkeypatch.setenv('PYTHONHASHSEED','173')
    for n in m.THREADS:monkeypatch.setenv(n,'1')
    r=m._reverse_science(p,f);m.validate_reverse(r)
    assert events[3:]==list(reversed(range(13)))
    assert r['actual_model_loads']==13 and r['actual_evaluator_calls']==26


