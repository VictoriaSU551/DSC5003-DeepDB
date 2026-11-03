"""Pure canonical supervisor planning, no actual Job/model execution."""
import importlib.util
import os
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_ssb_local_canonical_run.py';assert p.exists(),'canonical supervisor missing'
    s=importlib.util.spec_from_file_location('canonical_runner_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


@pytest.mark.parametrize('damage',[None,'reserve','hash','calls','scope','approval'])
def test_exact_canonical_plan_cannot_reseal_changed_policy(tmp_path,damage):
    m=module();deps={'runtime':'proof','canonical_sources':{'code/example.py':'b'*64}}
    c=m.candidate_body(m.value_hash(deps['canonical_sources']),{'parent':'proof'},deps)
    p=dict(c,status='ROOT_REVIEWED_LOCAL_CANONICAL_PLAN',executable=True,root_reviewed_candidate_sha256=m.model.value_hash(c))
    if damage=='reserve':p['additional_reserve_bytes']=5*2**30
    elif damage=='hash':p['hash_seeds']['FORWARD']=173
    elif damage=='calls':p['phase_evaluator_calls']=25
    elif damage=='scope':p['scope']='LOCAL_SSB_SF500'
    elif damage=='approval':p['root_reviewed_candidate_sha256']='b'*64
    path=tmp_path/m.model.OUTPUT/'plans'/m.model.value_hash(p)[:20]/'plan.json';m.model.atomic(path,p);m.model.atomic(path.with_suffix('.seal.json'),{'sha256':m.model.digest(path)})
    if damage is None:assert m.read_plan(path,m.model.digest(path),tmp_path)==p
    else:
        with pytest.raises(ValueError):m.read_plan(path,m.model.digest(path),tmp_path)


def test_supervisor_denies_unapproved_execution_without_files(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='memory|release'):m.run_supervised('none','0'*64,False,tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
def test_capsule_routes_each_phase_to_disjoint_control_and_scientific_alias(phase):
    m=module();p={'proof':'plan'};namespace=m.capsule(phase,p)
    assert namespace['JOB_PREFIX'].endswith(phase+'_')
    assert namespace['model'].RESULT.endswith('/'+phase.lower()+'/verification.json')
    assert namespace['model'].OUTPUT==m.model.OUTPUT
    a,b,mappings=m.configured_source(phase)
    assert phase.lower()+'_control' in b and 'supervisor_control' not in b
    assert "directory/'"+phase.lower()+"'/'seal.json'" in b


def test_child_phase_environment_restores_even_after_exception(monkeypatch):
    import os
    m=module();monkeypatch.setenv('PYTHONHASHSEED','original');monkeypatch.delenv('DEEPDB_SSB_CANONICAL_PHASE',raising=False)
    with pytest.raises(RuntimeError):
        with m.phase_environment('REVERSE'):
            assert os.environ['PYTHONHASHSEED']=='173' and os.environ['DEEPDB_SSB_CANONICAL_PHASE']=='REVERSE'
            raise RuntimeError('tiny')
    assert os.environ['PYTHONHASHSEED']=='original' and 'DEEPDB_SSB_CANONICAL_PHASE' not in os.environ


def test_resealed_plan_cannot_relabel_reviewed_code_set_without_matching_source_map(tmp_path):
    m=module();deps={'canonical_sources':{'code/example.py':'b'*64}}
    c=m.candidate_body('f'*64,{'parent':'fixed'},deps)
    p=dict(c,status='ROOT_REVIEWED_LOCAL_CANONICAL_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    path=tmp_path/m.model.OUTPUT/'plans'/m.value_hash(p)[:20]/'plan.json';m.atomic(path,p);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    with pytest.raises(ValueError,match='reviewed|code'):m.read_plan(path,m.digest(path),tmp_path)


@pytest.mark.parametrize('existing_pass',[False,True])
def test_actual_root_controller_counts_four_independent_formal_boundaries_and_existing_pass_one(tmp_path,monkeypatch,existing_pass):
    import contextlib
    m=module();calls=[];monkeypatch.setattr(m,'ROOT',tmp_path)
    p={'parent':{'accepted':True},'dependencies':{}};parent={'full_current_entry_proof':True}
    monkeypatch.setattr(m,'read_plan',lambda *a:p);monkeypatch.setattr(m.model,'parent_snapshot',lambda *a:p['parent'])
    monkeypatch.setattr(m.model,'collect_parent',lambda *a:calls.append('F') or parent)
    monkeypatch.setattr(m.model,'dependency_snapshot',lambda:{})
    monkeypatch.setattr(m.model,'run_directory',lambda *a,**k:tmp_path/'run')
    monkeypatch.setattr(m.model,'refresh_parent',lambda *a:calls.append('physical_refresh'))
    monkeypatch.setattr(m.model,'validate_report',lambda *a:None);monkeypatch.setattr(m.model,'root_binding',lambda *a:{})
    monkeypatch.setattr(m.model,'report_body',lambda *a:{'status':m.model.PASS})
    monkeypatch.setattr(m.model,'publish_report',lambda *a:calls.append('publication'))
    monkeypatch.setattr(m,'artifact',lambda *a:{})
    def child(p,phase):
        calls.append(phase);m.model.collect_parent() # actual worker boundary is tested separately; no science here.
    monkeypatch.setattr(m,'_run_child',child)
    monkeypatch.setattr(m.base,'controller_lock',lambda *a:contextlib.nullcontext())
    def transaction(home,binding,producer,validator,**k):
        r={'status':m.model.PASS} if existing_pass else producer();validator(r);return r
    monkeypatch.setattr(m.base,'formal_transaction',transaction)
    m._run_supervised(tmp_path/'plan.json','a'*64)
    assert calls.count('F')==(1 if existing_pass else 4)
    assert calls.count('physical_refresh')==1 and calls[-1]=='publication'


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
@pytest.mark.parametrize('damage',[None,'hash','worker_parent','publication','rss','absolute_venv','scientific_pid','scientific_pid_missing'])
def test_phase_owned_evidence_uses_actual_paths_commands_hash_and_phase(tmp_path,monkeypatch,phase,damage):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);old_run=m.model.run_directory
    monkeypatch.setattr(m.model,'run_directory',lambda p,root=tmp_path:old_run(p,root))
    for name in ('base.exe','venv.exe',m.SELF):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'pure identity')
    env=dict(python_base_executable=m.artifact(tmp_path/'base.exe',tmp_path),python_executable=m.artifact(tmp_path/'venv.exe',tmp_path))
    deps=dict(environment=env,canonical_sources={m.SELF:m.digest(tmp_path/m.SELF),'code/full_ssb_local_canonical.py':'a'*64})
    if damage=='absolute_venv':env['python_executable']={'path':str((tmp_path/'venv.exe').resolve()),'sha256':env['python_executable']['sha256']}
    c=m.candidate_body(m.value_hash(deps['canonical_sources']),{},deps);p=dict(c,status='ROOT_REVIEWED_LOCAL_CANONICAL_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    key=m.value_hash(p);path=tmp_path/m.model.OUTPUT/'plans'/key[:20]/'plan.json';m.atomic(path,p);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    r=m.child_report(p,phase);binding=m.supervisor_binding(r);home=Path(r['directory'])/(phase.lower()+'_control');token='1'*32;job='Local\\DeepDB_SSB_NATIVE_CANONICAL_'+phase+'_'+token
    command=[str(tmp_path/'base.exe'),str(tmp_path/m.SELF),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',m.digest(path),'--start-token',token,'--job-name',job]
    worker=[str(tmp_path/'venv.exe'),command[1],'_worker']+command[3:]+['--bootstrap-pid','101']
    common=dict(scope=m.model.SCOPE,phase=phase,hash_seed=m.model.HASH_SEEDS[phase],membership_verified_after_go=True,named_job=job,plan_binding_sha256=key,base_executable=env['python_base_executable'])
    boot=dict(common,schema='ssb_canonical_'+phase.lower()+'_bootstrap_v1',status='PASS',returncode=0,pid=101,worker_launcher_pid=102,worker_command=worker)
    child=dict(common,schema='ssb_canonical_'+phase.lower()+'_worker_v1',pid=103,parent_pid=102,bootstrap_pid=101,venv_executable=m.artifact(tmp_path/'venv.exe',tmp_path))
    resource=dict(available_memory_bytes=6*2**30,free_disk_bytes=20*2**30,existing_ssb_bytes=2*2**30,storage_scan_age_seconds=0)
    mon=dict(status='PASS',binding=binding,policy=m.ops.OPERATIONAL_POLICY,command=command,returncode=0,stop_reason=None,peak_owned_rss_bytes=1000,checks=2,last_resource_probe=resource,seconds=1.,owned_process_only=True,job_object_kill_on_close=True)
    if damage=='hash':child['hash_seed']=99
    elif damage=='worker_parent':child['parent_pid']=999
    elif damage=='rss':mon['peak_owned_rss_bytes']=7*2**30
    for name,body in [('bootstrap.json',boot),('worker_start.json',child),('monitor.json',mon)]:m.atomic(home/name,body)
    for name in ('stdout.log','stderr.log'):(home/name).write_bytes(b'')
    report=Path(r['directory'])/phase.lower()/'verification.json';seal=report.with_name('seal.json')
    m.atomic(report,{'environment':{} if damage=='scientific_pid_missing' else {'process_id':999 if damage=='scientific_pid' else 103}});m.atomic(seal,{'fake':'scientific seal'})
    result=dict(returncode=0,peak_owned_rss_bytes=mon['peak_owned_rss_bytes'],resources_at_launch=resource,artifacts=[m.artifact(home/n,tmp_path) for n in m.LOGS],
        published_result_sha256=m.digest(report),verification_seal_sha256=m.digest(seal))
    if damage=='publication':result['published_result_sha256']='f'*64
    m.atomic(home/'receipt.json',dict(status='PASS',kind='CANONICAL_'+phase+'_CHILD',binding=binding,result=result));m.atomic(home/'lifecycle.json',dict(status='PASS',binding=binding,receipt_sha256=m.digest(home/'receipt.json')))
    if damage in (None,'absolute_venv'):assert len(m.verify_child(p,phase,tmp_path))==7
    else:
        with pytest.raises(ValueError):m.verify_child(p,phase,tmp_path)


def fake_native_membership_api(monkeypatch,m):
    """Mock only OS calls; the frozen real name/membership verifier still runs."""
    import ctypes
    from ctypes import wintypes
    opened=[]
    class Kernel:
        def OpenJobObjectW(self,access,inherit,name):opened.append(name);return 123
        def IsProcessInJob(self,process,job,assigned):assigned._obj.value=True;return True
        def CloseHandle(self,handle):return True
    monkeypatch.setattr(m.ops,'windows_api',lambda:(ctypes,wintypes,Kernel()))
    return opened


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
def test_phase_capsule_job_name_passes_the_unmodified_native_verifier(monkeypatch,phase):
    m=module();opened=fake_native_membership_api(monkeypatch,m)
    prefix=m.capsule(phase,{'synthetic_only':True})['JOB_PREFIX'];job=prefix+'1'*32
    m.ops.verify_owned_job_membership(job)
    assert prefix=='Local\\DeepDB_SSB_NATIVE_CANONICAL_'+phase+'_' and opened==[job]


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
def test_actual_child_command_job_matches_capsule_and_unmodified_native_guard(tmp_path,monkeypatch,phase):
    m=module();opened=fake_native_membership_api(monkeypatch,m);observed=[];plan={'synthetic_only':True}
    prefix=m.capsule(phase,plan)['JOB_PREFIX'];monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'child_report',lambda *a:{})
    monkeypatch.setattr(m,'artifact',lambda p:dict(path=str(p),bytes=1,sha256='a'*64))
    monkeypatch.setattr(m,'digest',lambda p:'a'*64)
    monkeypatch.setattr(m.ops,'base_python_executable',lambda:tmp_path/'base.exe')
    monkeypatch.setattr(m,'supervisor_binding',lambda r:dict(bootstrap_executable=m.artifact(m.ops.base_python_executable())))
    monkeypatch.setattr(m.model,'run_directory',lambda p:tmp_path/'synthetic_run')
    monkeypatch.setattr(m.ops,'operational_resources',lambda:dict(free_disk_bytes=20*2**30,available_memory_bytes=8*2**30,existing_ssb_bytes=0))
    def child(command,home,binding,**kwargs):
        job=kwargs['job_name'];m.ops.verify_owned_job_membership(job)
        assert command[-2:]==['--job-name',job] and job==prefix+kwargs['start_payload']['start']
        assert os.environ['DEEPDB_SSB_CANONICAL_PHASE']==phase and os.environ['PYTHONHASHSEED']==str(m.model.HASH_SEEDS[phase])
        observed.append(command);return dict(artifacts=[])
    monkeypatch.setattr(m.ops,'run_owned_child',child)
    monkeypatch.setattr(m,'capsule',lambda *a:{'verify_supervisor_result':lambda *a:None})
    def transaction(home,binding,producer,validator,**kw):
        value=producer();validator(value);return value
    monkeypatch.setattr(m.base,'formal_transaction',transaction)
    m._run_child(plan,phase)
    assert len(observed)==len(opened)==1 and opened[0].startswith('Local\\DeepDB_SSB_NATIVE_CANONICAL_'+phase+'_')


@pytest.mark.skipif(os.name!='nt' or os.environ.get('DEEPDB_CANONICAL_NO_SCIENCE_GATE')!='1',
    reason='ROOT opt-in only: real owned bootstrap/venv micro gate, never science')
@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
def test_actual_no_science_canonical_base_to_venv_owned_bootstrap(phase,monkeypatch):
    """ROOT runs explicitly after review; scientific and full-F APIs are replaced."""
    import secrets,time
    m=module();home=ROOT/'output/tmp'/('cnj2_'+phase.lower()+'_'+secrets.token_hex(3));home.mkdir(parents=True)
    rel=home.relative_to(ROOT).as_posix();plan=dict(synthetic_only=True,scope='NO_SCIENCE_CANONICAL_JOB_GATE',phase=phase)
    token=secrets.token_hex(16);job=m.capsule(phase,plan)['JOB_PREFIX']+token;script=home/'entry.py'
    definitions=dict(ROOT_CODE=str(ROOT/'code'),SCRIPT_REL=rel+'/entry.py',MOCK_OUTPUT=rel+'/mock',PLAN=plan,PHASE=phase,MARKER=str(home/'no_science.json'))
    code='\n'.join(k+'='+repr(v) for k,v in definitions.items())+'''
import sys,os
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,ROOT_CODE)
import full_ssb_local_canonical_run as m
def forbidden(*a,**k):raise AssertionError('NO_SCIENCE gate attempted full parent/source/scientific API')
m.SELF=SCRIPT_REL
m.model.OUTPUT=MOCK_OUTPUT
m.read_plan=lambda *a,**k:PLAN
m.model.collect_parent=forbidden
m.model.dependency_snapshot=forbidden
m.model.previous.verify_local_formal=forbidden
m.model.previous.execute_local_formal=forbidden
m.base.formal_transaction=forbidden
def no_science(plan,phase):
    assert plan==PLAN and phase==PHASE
    assert os.environ['DEEPDB_SSB_CANONICAL_PHASE']==PHASE
    assert os.environ['PYTHONHASHSEED']==str(m.model.HASH_SEEDS[PHASE])
    m.atomic(Path(MARKER),dict(status='PASS_NO_SCIENCE_WORKER',scope='NO_SCIENCE_CANONICAL_JOB_GATE',phase=PHASE,
        parent_verifier_calls=0,model_calls=0,database_calls=0,pid=os.getpid(),parent_pid=os.getppid()))
    return dict(status='PASS_NO_SCIENCE_WORKER')
m.model.execute_worker=no_science
raise SystemExit(m.main())
'''
    script.write_bytes(code.encode('utf-8'));control=home/'mock/runs'/m.value_hash(plan)[:20]/(phase.lower()+'_control')
    original=m.ops.OwnedWindowsJob.assign
    def delayed_assignment(self,process):time.sleep(.2);original(self,process)
    monkeypatch.setattr(m.ops.OwnedWindowsJob,'assign',delayed_assignment)
    resource=lambda:dict(available_memory_bytes=8*2**30,free_disk_bytes=30*2**30,existing_ssb_bytes=0,storage_scan_age_seconds=0)
    command=[str(m.ops.base_python_executable()),str(script),'_bootstrap','--plan-path','NO_SCIENCE_NOT_A_FORMAL_PLAN',
        '--plan-file-sha256','a'*64,'--start-token',token,'--job-name',job]
    print('NO_SCIENCE_GATE_DIRECTORY='+str(home),flush=True)
    with m.phase_environment(phase):
        result=m.ops.run_owned_child(command,control,dict(scope='NO_SCIENCE_CANONICAL_JOB_GATE',phase=phase),
            policy=dict(m.ops.OPERATIONAL_POLICY,monitor_interval_seconds=.05,wall_timeout_seconds=30),resource_probe=resource,
            start_payload=dict(start=token,plan_binding_sha256=m.value_hash(plan)),job_name=job)
    boot=m.read(control/'bootstrap.json');worker=m.read(control/'worker_start.json');marker=m.read(home/'no_science.json')
    assert result['returncode']==0 and boot['status']=='PASS' and boot['returncode']==0
    assert boot['phase']==worker['phase']==marker['phase']==phase and boot['hash_seed']==worker['hash_seed']==m.model.HASH_SEEDS[phase]
    assert boot['named_job']==worker['named_job']==job and worker['membership_verified_after_go'] is True
    assert worker['bootstrap_pid']==boot['pid'] and worker['parent_pid']==boot['worker_launcher_pid']==marker['parent_pid']
    assert worker['pid']==marker['pid'] and boot['worker_command'][0]==str(ROOT/'.venv/Scripts/python.exe')
    assert all(not m.ops.windows_process_alive(pid) for pid in (boot['pid'],boot['worker_launcher_pid'],worker['pid']))
    assert marker['parent_verifier_calls']==marker['model_calls']==marker['database_calls']==0
    assert not any(p.name in ('evaluation','forward','reverse') for p in home.rglob('*'))
    receipt=dict(status='PASS_NO_SCIENCE_CANONICAL_OWNED_BOOTSTRAP_GATE',scope='NO_SCIENCE_CANONICAL_JOB_GATE',phase=phase,
        runner_sha256=m.digest(ROOT/m.SELF),canonical_provider_sha256=m.digest(ROOT/'code/full_ssb_local_canonical.py'),
        frozen_native_runner_sha256=m.digest(ROOT/'code/full_ssb_native_model_run.py'),synthetic_resource_probe=True,
        actual_parent_calls=0,actual_model_calls=0,actual_database_calls=0,actual_training_calls=0,actual_inference_calls=0,
        bootstrap=m.artifact(control/'bootstrap.json'),worker=m.artifact(control/'worker_start.json'),marker=m.artifact(home/'no_science.json'),
        monitor=m.artifact(control/'monitor.json'),result=result)
    m.atomic(home/'gate_receipt.json',receipt)
