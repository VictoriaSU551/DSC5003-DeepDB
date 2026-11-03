"""Owned continuation control tests; actual Job micro gate is separately opt-in."""
import importlib
import contextlib
import io
import os
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))


def module():return importlib.import_module('full_ssb_local_continuation_run')


def test_frozen_policy_is_preserved_without_extending_stale_age():
    m=module();p=m.POLICY
    assert p['minimum_launch_available_memory_bytes']==5*2**30
    assert p['minimum_worker_available_memory_bytes']==4*2**30
    assert p['maximum_owned_rss_bytes']==6*2**30
    assert p['minimum_live_available_memory_bytes']==2**30
    assert p['minimum_free_disk_bytes']==8*2**30 and p['maximum_ssb_bytes']==16*2**30
    assert p['maximum_storage_scan_age_seconds']==90 and p['wall_timeout_seconds']==172800


def test_cleanup_error_cannot_replace_first_operational_failure():
    m=module();failures=[]
    class Process:
        def poll(self):return None
        def wait(self,timeout):assert timeout<=10;raise TimeoutError('late wait')
        def kill(self):failures.append('kill')
    class Job:
        def terminate(self):failures.append('terminate');raise OSError('late termination')
    errors=m.stop_owned(Process(),Job())
    assert failures==['terminate','kill'] and len(errors)==3
    reason=m.failure_reason(ValueError('original stale failure'),errors)
    assert reason['primary_exception']=="ValueError('original stale failure')" and len(reason['cleanup_errors'])==3


def test_absent_reviewed_plan_never_launches_anything(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'_run_supervised',lambda *a:pytest.fail('unapproved launcher reached'))
    with pytest.raises(ValueError):m.run_supervised(tmp_path/'missing','x',False)


def test_early_launch_admission_failure_cannot_claim_namespace_or_call_F(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m.model,'ROOT',tmp_path)
    plan=dict(attempt_id='ram_retry_02',parent={},forward={});run=m.model.run_directory(plan)
    monkeypatch.setattr(m,'read_plan',lambda *a:plan)
    monkeypatch.setattr(m.base,'controller_lock',lambda *a:contextlib.nullcontext())
    monkeypatch.setattr(m,'complete_resources',lambda:dict(available_memory_bytes=9*2**29,free_disk_bytes=20*2**30,existing_ssb_bytes=2*2**30))
    monkeypatch.setattr(m.model,'collect_parent',lambda:pytest.fail('early admission must precede F'))
    monkeypatch.setattr(m.base,'formal_transaction',lambda *a,**k:pytest.fail('early admission must precede namespace claim'))
    monkeypatch.setattr(m,'_run_child',lambda *a:pytest.fail('no owned process'))
    with pytest.raises(ValueError,match='5GiB'):m._run_supervised(tmp_path/'plan.json','sha')
    assert not run.exists()


def test_invalid_attempt_cannot_trigger_candidate_parent_F(monkeypatch):
    m=module();monkeypatch.setattr(m.model,'collect_parent',lambda:pytest.fail('invalid attempt reached F'))
    monkeypatch.setattr(m.model,'code_snapshot',lambda:pytest.fail('invalid attempt reached source audit'))
    with pytest.raises(ValueError,match='attempt'):m.build_candidate('old','sha','codes','../retry')


def test_late_preworker_launch_gate_still_refuses_RAM_that_fell_after_F(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.model,'ROOT',tmp_path)
    monkeypatch.setattr(m,'child_binding',lambda *a:{})
    monkeypatch.setattr(m,'complete_resources',lambda:dict(available_memory_bytes=9*2**29,free_disk_bytes=20*2**30,existing_ssb_bytes=2*2**30))
    monkeypatch.setattr(m.base,'formal_transaction',lambda home,binding,produce,validate,**kw:produce())
    monkeypatch.setattr(m,'run_owned',lambda *a:pytest.fail('late gate must precede owned launch'))
    with pytest.raises(ValueError,match='5GiB'):m._run_child({'attempt_id':'ram_retry_02'})


@pytest.mark.parametrize('attempt_id',['initial','ram_retry_02'])
def test_cli_forwards_explicit_or_default_attempt_without_parent_access(monkeypatch,attempt_id):
    m=module();calls=[]
    monkeypatch.setattr(m,'build_candidate',lambda *args,**kw:calls.append((args,kw)) or {'fixture':True})
    args=['candidate-plan','--old-plan-path','old','--old-plan-sha256','sha','--reviewed-codes-sha256','codes']
    if attempt_id!='initial':args+=['--attempt-id',attempt_id]
    assert m.main(args)==0
    assert calls==[(('old','sha','codes',attempt_id),{})]


def test_stale_exception_is_preserved_even_when_owned_cleanup_times_out(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);exe=tmp_path/'base.exe';exe.write_text('tiny');events=[]
    class Process:
        stdin=io.BytesIO();returncode=None;pid=101
        def poll(self):return None
        def wait(self,timeout):assert timeout<=10;raise TimeoutError('cleanup wait')
        def kill(self):events.append('kill bootstrap')
    class Job:
        def __init__(self,name):events.append('job created')
        def assign(self,p):events.append('assigned')
        def working_set_bytes(self):return 100
        def terminate(self):events.append('terminate owned');raise OSError('cleanup terminate')
        def close(self):events.append('closed owned')
    class Probe:
        def __init__(self,*a):self.thread=type('Thread',(),{'is_alive':lambda s:False})();self.walks=[];self.heartbeat=m.time.monotonic()
        def __enter__(self):return self
        def snapshot(self):raise ValueError('original stale failure')
        def close(self):events.append('probe stopped')
    monkeypatch.setattr(m.ops,'base_python_executable',lambda:exe);monkeypatch.setattr(m.ops,'OwnedWindowsJob',Job)
    monkeypatch.setattr(m,'StorageProbe',Probe);monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:Process())
    with pytest.raises(ValueError,match='original stale failure'):m.run_owned([str(exe)],tmp_path,{'plan_binding_sha256':'p'},'t','job',{})
    monitor=m.read(tmp_path/'monitor.json')
    assert monitor['status']=='STOPPED' and monitor['primary_exception']=="ValueError('original stale failure')"
    assert 'closed owned' in events and 'probe stopped' in events and len(monitor['cleanup_errors'])>=3


def owned_fixture(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m.model,'ROOT',tmp_path)
    for n in ['base.exe','venv.exe',m.SELF]:
        p=tmp_path/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
    env=dict(python_base_executable=m.artifact(tmp_path/'base.exe',tmp_path),python_executable=m.artifact(tmp_path/'venv.exe',tmp_path))
    plan=dict(codes={m.SELF:m.digest(tmp_path/m.SELF),m.model.FILES[0]:'b'*64},worker_environment=env)
    path=tmp_path/m.model.OUTPUT/'plans'/m.value_hash(plan)[:20]/'plan.json';m.atomic(path,plan)
    binding=m.child_binding(plan);home=m.model.run_directory(plan)/'reverse_control';home.mkdir(parents=True)
    token='1'*32;job=m.JOB_PREFIX+token
    command=[str(tmp_path/'base.exe'),str(tmp_path/m.SELF),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',m.digest(path),'--start-token',token,'--job-name',job]
    worker_command=[str(tmp_path/'venv.exe'),command[1],'_worker']+command[3:]+['--bootstrap-pid','101']
    common=dict(scope=m.model.SCOPE,membership_verified_after_go=True,named_job=job,plan_binding_sha256=m.value_hash(plan),base_executable=env['python_base_executable'])
    boot=dict(common,schema='ssb_continuation_bootstrap_v1',status='PASS',returncode=0,pid=101,worker_launcher_pid=102,worker_command=worker_command)
    worker=dict(common,schema='ssb_continuation_worker_v1',hash_seed=173,pid=103,parent_pid=102,bootstrap_pid=101,venv_executable=m.artifact(tmp_path/'venv.exe',tmp_path))
    resource=dict(available_memory_bytes=6*2**30,free_disk_bytes=20*2**30,existing_ssb_bytes=2*2**30,storage_scan_age_seconds=0)
    monitor=dict(status='PASS',binding=binding,policy=m.ops.OPERATIONAL_POLICY,command=command,returncode=0,stop_reason=None,primary_exception=None,cleanup_errors=[],
        peak_owned_rss_bytes=1000,checks=2,last_resource_probe=resource,seconds=1.,owned_process_only=True,job_object_kill_on_close=True,
        storage_walks=[],storage_probe_stopped=True,storage_heartbeat_age_seconds=0.)
    for n,v in [('bootstrap.json',boot),('worker_start.json',worker),('monitor.json',monitor)]:m.atomic(home/n,v)
    for n in ('stdout.log','stderr.log'):(home/n).write_text('fixture')
    run=m.model.run_directory(plan);m.atomic(run/'reverse/verification.json',dict(environment=dict(process_id=103)));m.atomic(run/'reverse/seal.json',{})
    result=dict(artifacts=[m.artifact(home/n,tmp_path) for n in m.LOGS],returncode=0,peak_owned_rss_bytes=1000,resources_at_launch=resource,
        published_result_sha256=m.digest(run/'reverse/verification.json'),verification_seal_sha256=m.digest(run/'reverse/seal.json'))
    m.atomic(home/'receipt.json',dict(status='PASS',kind='CONTINUATION_CHILD',binding=binding,result=result))
    m.atomic(home/'lifecycle.json',dict(status='PASS',binding=binding,receipt_sha256=m.digest(home/'receipt.json')))
    return m,plan,home


@pytest.mark.parametrize('bad',[None,'job_prefix','bootstrap_parent','worker_pid','hash','runtime','stale','cleanup','storage_alive','publication','nonfinite_seconds','fractional_bytes','bad_walk'])
def test_owned_resealed_evidence_still_requires_real_nesting_sources_resources_and_scientific_pid(tmp_path,monkeypatch,bad):
    m,p,home=owned_fixture(tmp_path,monkeypatch)
    if bad=='runtime':(tmp_path/m.SELF).write_text('changed')
    if bad=='publication':m.atomic(home.parent/'reverse/verification.json',dict(environment=dict(process_id=999)))
    if bad in ('job_prefix','stale','cleanup','storage_alive','nonfinite_seconds','fractional_bytes','bad_walk'):
        mon=m.read(home/'monitor.json')
        if bad=='job_prefix':mon['command'][-1]='Local\\unsupported'
        if bad=='stale':mon['last_resource_probe']['storage_scan_age_seconds']=91
        if bad=='cleanup':mon['cleanup_errors']=['ignored failure']
        if bad=='storage_alive':mon['storage_probe_stopped']=False
        if bad=='nonfinite_seconds':mon['seconds']=True
        if bad=='fractional_bytes':mon['last_resource_probe']['available_memory_bytes']=6*2**30+.5
        if bad=='bad_walk':mon['storage_walks']=[dict(seconds=-1,bytes=10,error=None,completed=True)]
        m.atomic(home/'monitor.json',mon)
    if bad in ('bootstrap_parent','worker_pid','hash'):
        w=m.read(home/'worker_start.json');w[{'bootstrap_parent':'parent_pid','worker_pid':'pid','hash':'hash_seed'}[bad]]=999;m.atomic(home/'worker_start.json',w)
    # Re-sealing the outer receipt is not sufficient to evade semantic gates.
    r=m.read(home/'receipt.json');r['result']['artifacts']=[m.artifact(home/n,tmp_path) for n in m.LOGS]
    if bad=='publication':r['result']['published_result_sha256']=m.digest(home.parent/'reverse/verification.json')
    m.atomic(home/'receipt.json',r);m.atomic(home/'lifecycle.json',dict(status='PASS',binding=r['binding'],receipt_sha256=m.digest(home/'receipt.json')))
    if bad is None:assert len(m.verify_child(p))==7
    else:
        with pytest.raises(ValueError):m.verify_child(p)


@pytest.mark.parametrize('change',[None,'fraction','negative','storage','ram'])
def test_final_root_resource_receipt_is_exact_and_budget_checked(change):
    m=module();p=dict(available_memory_bytes=6*2**30,free_disk_bytes=20*2**30,existing_ssb_bytes=2*2**30)
    if change=='fraction':p['free_disk_bytes']+=.5
    if change=='negative':p['existing_ssb_bytes']=-1
    if change=='storage':p['existing_ssb_bytes']=17*2**30
    if change=='ram':p['available_memory_bytes']=3*2**30
    if change is None:assert m.validate_root_resources(p)==p
    else:
        with pytest.raises(ValueError):m.validate_root_resources(p)


@pytest.mark.parametrize('failure',[None,'post_F','publication'])
def test_root_boundary_has_two_fresh_Fs_one_reverse_and_no_repair(tmp_path,monkeypatch,failure):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m.model,'ROOT',tmp_path);events=[]
    c=dict(status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,attempt_id='ram_retry_02',scope=m.model.SCOPE,execution_protocol=m.model.PROTOCOL,old_plan=dict(path='old.json',sha256='x'),parent={},forward={},operational_policy=m.POLICY)
    p=dict(c,status='ROOT_REVIEWED_CONTINUATION_PLAN',executable=True,root_reviewed_candidate_sha256='review')
    monkeypatch.setattr(m,'read_plan',lambda *a:p)
    def parent():
        events.append('F')
        if failure=='post_F' and events.count('F')==2:raise RuntimeError('post F failed')
        return {'fresh':True}
    monkeypatch.setattr(m.model,'collect_parent',parent)
    def rebuild(*a):
        assert a[-1]=='ram_retry_02'
        return {k:v for k,v in c.items() if k!='operational_policy'}
    monkeypatch.setattr(m.model,'candidate_from_parent',rebuild)
    monkeypatch.setattr(m,'_run_child',lambda *a:events.append('REVERSE_ONLY'))
    probe=dict(available_memory_bytes=6*2**30,free_disk_bytes=20*2**30,existing_ssb_bytes=2*2**30)
    monkeypatch.setattr(m.ops,'operational_resources',lambda:probe)
    monkeypatch.setattr(m.ops,'fast_resources',lambda:{k:probe[k] for k in ('available_memory_bytes','free_disk_bytes')})
    monkeypatch.setattr(m.model,'report_body',lambda p,path,parent,resources,admission:dict(status=m.model.PASS,root_final_resources=resources,root_admission_resources=admission))
    def publish(*a):
        events.append('PUBLICATION')
        if failure=='publication':raise RuntimeError('publication failed')
    monkeypatch.setattr(m.model,'publish',publish);monkeypatch.setattr(m,'artifact',lambda *a:{})
    monkeypatch.setattr(m.base,'controller_lock',lambda *a:contextlib.nullcontext())
    if failure:
        with pytest.raises(RuntimeError):m._run_supervised(tmp_path/'plan.json','x')
    else:assert m._run_supervised(tmp_path/'plan.json','x')['status']==m.model.PASS
    assert events.count('F')==2 and events.count('REVERSE_ONLY')==1
    life=m.read(m.model.run_directory(p)/'root_control/lifecycle.json');assert life['status']==('TAINTED' if failure else 'PASS')
    before=list(events)
    with pytest.raises(ValueError,match='already used'):m._run_supervised(tmp_path/'plan.json','x')
    assert events==before


def test_complete_resource_probe_refreshes_fast_memory_after_storage_walk(monkeypatch):
    m=module();events=[]
    monkeypatch.setattr(m.ops,'operational_resources',lambda:events.append('storage') or dict(available_memory_bytes=99,free_disk_bytes=100,existing_ssb_bytes=10))
    monkeypatch.setattr(m.ops,'fast_resources',lambda:events.append('fresh fast') or dict(available_memory_bytes=80,free_disk_bytes=90))
    p=m.complete_resources()
    assert events==['storage','fresh fast'] and p['available_memory_bytes']==80 and p['free_disk_bytes']==90 and p['existing_ssb_bytes']==10
    assert p['storage_scan_age_seconds']==0 and p['storage_walk_seconds']>=0


@pytest.mark.parametrize('damage',[None,'schema','v1_schema','reserve','contract','empty_closure','roles','extra','missing_attempt','empty_attempt','bad_attempt','non_ascii_attempt','long_attempt','bool_attempt'])
def test_reviewed_plan_rejects_changed_execution_contract_even_when_resealed(tmp_path,monkeypatch,damage):
    m=module();codes={m.SELF:'x',m.model.FILES[0]:'y'};monkeypatch.setattr(m.model,'code_snapshot',lambda:codes)
    c=dict(schema='local_ssb_canonical_continuation_plan_v2',attempt_id='ram_retry_02',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,scope=m.model.SCOPE,execution_protocol=m.model.PROTOCOL,
        codes=codes,parent={},old_plan={},old_plan_seal={},forward={},accepted_forward_artifacts=[{'path':'forward'}],retained_failure_provenance=[{'path':'history'}],
        worker_roles={n:{'path':n} for n in ('model','moments','truth')},prepared_directory='prepared',worker_environment={},
        environment_contract='ONLY_CURRENT_MODEL_FORWARD_QUERIES_MOMENTS_TRUTH_ALGORITHM_PARSER_RUNTIME;ROOT_FULL_FORMAL_PRE_POST',
        hash_seed=173,random_seed=74031,thread_limits={n:'1' for n in m.model.THREADS},additional_reserve_bytes=512*2**20,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,historical_reverse_accepted=False,worker_artifacts=[{'path':'model'}],operational_policy=m.POLICY)
    if damage=='schema':c['schema']='old'
    if damage=='v1_schema':c['schema']='local_ssb_canonical_continuation_plan_v1'
    if damage=='reserve':c['additional_reserve_bytes']=0
    if damage=='contract':c['environment_contract']='FAKE_FULL_F'
    if damage=='empty_closure':c['worker_artifacts']=[]
    if damage=='roles':c['worker_roles'].pop('truth')
    if damage=='extra':c['skip_parent_F']=True
    if damage=='missing_attempt':c.pop('attempt_id')
    if damage=='empty_attempt':c['attempt_id']=''
    if damage=='bad_attempt':c['attempt_id']='../retry'
    if damage=='non_ascii_attempt':c['attempt_id']='\u00e9'
    if damage=='long_attempt':c['attempt_id']='a'*33
    if damage=='bool_attempt':c['attempt_id']=True
    p=dict(c,status='ROOT_REVIEWED_CONTINUATION_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    path=tmp_path/m.model.OUTPUT/'plans'/m.value_hash(p)[:20]/'plan.json';m.atomic(path,p);m.atomic(path.with_suffix('.seal.json'),dict(sha256=m.digest(path)))
    if damage is None:assert m.read_plan(path,m.digest(path),tmp_path)==p
    else:
        with pytest.raises(ValueError):m.read_plan(path,m.digest(path),tmp_path)


@pytest.mark.skipif(os.name!='nt' or os.environ.get('DEEPDB_CONTINUATION_NO_SCIENCE_GATE')!='1',reason='ROOT opt-in only: real Job bootstrap/venv; synthetic resource probe and no science')
def test_actual_no_science_continuation_base_to_venv_owned_bootstrap(monkeypatch):
    import secrets,time
    m=module();home=ROOT/'output/tmp'/('cntj_'+secrets.token_hex(3));home.mkdir(parents=True)
    rel=home.relative_to(ROOT).as_posix();plan=dict(synthetic_only=True,scope='NO_SCIENCE_CONTINUATION_JOB_GATE');token=secrets.token_hex(16);job=m.JOB_PREFIX+token
    script=home/'entry.py';definitions=dict(ROOT_CODE=str(ROOT/'code'),SCRIPT_REL=rel+'/entry.py',MOCK_OUTPUT=rel+'/mock',PLAN=plan,MARKER=str(home/'no_science.json'))
    code='\n'.join(k+'='+repr(v) for k,v in definitions.items())+'''
import sys,os
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,ROOT_CODE)
import full_ssb_local_continuation_run as m
def forbidden(*a,**k):raise AssertionError('NO_SCIENCE gate reached parent/source/scientific API')
m.SELF=SCRIPT_REL
m.model.OUTPUT=MOCK_OUTPUT
m.read_plan=lambda *a,**k:PLAN
m.model.collect_parent=forbidden
m.model.verify_worker_inputs=forbidden
m.model.old.collect_parent=forbidden
m.model.old.previous.verify_local_formal=forbidden
def no_science(plan):
    assert plan==PLAN and os.environ['PYTHONHASHSEED']=='173'
    assert all(os.environ[k]=='1' for k in m.model.THREADS)
    m.atomic(Path(MARKER),dict(status='PASS_NO_SCIENCE_CONTINUATION_WORKER',parent_verifier_calls=0,model_calls=0,database_calls=0,pid=os.getpid(),parent_pid=os.getppid()))
    return dict(status='PASS_NO_SCIENCE_WORKER')
m.model.execute_reverse=no_science
raise SystemExit(m.main())
'''
    script.write_bytes(code.encode());control=home/'mock/runs'/m.value_hash(plan)[:20]/'reverse_control';control.mkdir(parents=True)
    original=m.ops.OwnedWindowsJob.assign
    def delayed(self,process):time.sleep(.2);original(self,process)
    monkeypatch.setattr(m.ops.OwnedWindowsJob,'assign',delayed)
    class Probe:
        def __init__(self,*a):self.thread=type('Thread',(),{'is_alive':lambda s:False})();self.walks=[];self.heartbeat=time.monotonic()
        def __enter__(self):return self
        def snapshot(self):return dict(available_memory_bytes=8*2**30,free_disk_bytes=30*2**30,existing_ssb_bytes=0,storage_scan_age_seconds=0)
        def close(self):pass
    monkeypatch.setattr(m,'StorageProbe',Probe);monkeypatch.setattr(m,'POLICY',dict(m.POLICY,monitor_interval_seconds=.05,wall_timeout_seconds=30))
    command=[str(m.ops.base_python_executable()),str(script),'_bootstrap','--plan-path','NO_SCIENCE_NOT_FORMAL','--plan-file-sha256','a'*64,'--start-token',token,'--job-name',job]
    print('NO_SCIENCE_GATE_DIRECTORY='+str(home),flush=True)
    with m.fresh_environment():out=m.run_owned(command,control,dict(plan_binding_sha256=m.value_hash(plan)),token,job,{})
    boot=m.read(control/'bootstrap.json');worker=m.read(control/'worker_start.json');marker=m.read(home/'no_science.json')
    assert out['returncode']==boot['returncode']==0 and boot['status']=='PASS'
    assert boot['named_job']==worker['named_job']==job and worker['hash_seed']==173
    assert worker['bootstrap_pid']==boot['pid'] and worker['parent_pid']==boot['worker_launcher_pid']==marker['parent_pid']
    assert worker['pid']==marker['pid'] and boot['worker_command'][0]==str(ROOT/'.venv/Scripts/python.exe')
    assert all(not m.ops.windows_process_alive(pid) for pid in (boot['pid'],boot['worker_launcher_pid'],worker['pid']))
    assert marker['parent_verifier_calls']==marker['model_calls']==marker['database_calls']==0
    assert not any(p.name in ('evaluation','forward','reverse') for p in home.rglob('*'))
    m.atomic(home/'gate_receipt.json',dict(status='PASS_NO_SCIENCE_CONTINUATION_OWNED_BOOTSTRAP_GATE',synthetic_resource_probe=True,actual_parent_calls=0,
        actual_model_calls=0,actual_database_calls=0,runner_sha256=m.digest(ROOT/m.SELF),provider_sha256=m.digest(ROOT/'code/full_ssb_local_continuation.py'),result=out,
        bootstrap=m.artifact(control/'bootstrap.json'),worker=m.artifact(control/'worker_start.json'),marker=m.artifact(home/'no_science.json'),monitor=m.artifact(control/'monitor.json')))

