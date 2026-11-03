"""Local launcher contracts and tiny owned processes only; no scientific calls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_ssb_local_model_run.py';assert p.exists(),'thin local launcher missing'
    s=importlib.util.spec_from_file_location('local_run_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def candidate(m):
    return dict(schema='ssb_local_sf500_model_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,scope=m.source.SCOPE,
        root_decision_sha256=m.source.DECISION_SHA,original_mismatch_sha256=m.source.NATIVE_REPORT_SHA,author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,source_receipt_sha256='a'*64,
        model=m.model.MODEL,dependencies={'local_sources':{p:'b'*64 for p in m.source.LOCAL_FILES},'auxiliary_sources':{}},operational_policy=m.ops.OPERATIONAL_POLICY)


def plan_fixture(m,root):
    c=candidate(m);plan=dict(c,status='ROOT_REVIEWED_LOCAL_SSB_MODEL_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    path=root/m.model.OUTPUT/'plans'/m.value_hash(plan)[:20]/'plan.json';m.atomic(path,plan);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    return plan,path


def test_missing_actual_source_rejects_candidate_without_outputs(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='missing'):m.build_plan('a'*64)
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('damage',[None,'author_status','scope','author_gap','decision','model','policy','candidate','namespace','extra'])
def test_local_reviewed_plan_exact_scope_policy_and_approval(tmp_path,damage):
    m=module();plan,path=plan_fixture(m,tmp_path)
    if damage is None:
        before=path.stat().st_mtime_ns;assert m.read_plan(path,m.digest(path),tmp_path)==plan;assert before==path.stat().st_mtime_ns;return
    if damage=='author_status':plan['status']='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN'
    elif damage=='scope':plan['scope']='AUTHOR_SSB'
    elif damage=='author_gap':plan['author_different_groups']=0
    elif damage=='decision':plan['root_decision_sha256']='f'*64
    elif damage=='model':plan['model']=dict(plan['model'],rdc_threshold=.15)
    elif damage=='policy':plan['operational_policy']=dict(plan['operational_policy'],minimum_launch_available_memory_bytes=0)
    elif damage=='candidate':plan['root_reviewed_candidate_sha256']='f'*64
    elif damage=='extra':plan['author_reproduction_complete']=True
    m.atomic(path,plan);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    if damage=='namespace':
        wrong=tmp_path/'plan.json';m.atomic(wrong,plan);m.atomic(wrong.with_suffix('.seal.json'),{'sha256':m.digest(wrong)});path=wrong
    with pytest.raises(ValueError):m.read_plan(path,m.digest(path),tmp_path)


def test_root_decision_is_not_memory_or_model_launch_approval(tmp_path):
    m=module();plan,path=plan_fixture(m,tmp_path)
    with pytest.raises(ValueError,match='memory'):m.run_supervised(path,m.digest(path),memory_approved=False,root=tmp_path)
    assert not (tmp_path/m.model.OUTPUT/'runs').exists()


def evidence(m,root):
    plan,path=plan_fixture(m,root);p=m.value_hash(plan);run=root/m.model.OUTPUT/'runs'/p[:20];home=run/'supervisor_control'
    for name in ('base.exe','venv.exe','code/full_ssb_local_model_run.py'):
        f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'pure fake identity')
    env={'python_base_executable':m.artifact(root/'base.exe',root),'python_executable':m.artifact(root/'venv.exe',root)}
    plan['dependencies']['environment']=env;plan['dependencies']['local_sources']['code/full_ssb_local_model_run.py']=m.digest(root/'code/full_ssb_local_model_run.py')
    # Evidence helpers validate physical recorded commands and file hashes;
    # plan structural tests above independently validate approval/namespace.
    r={'directory':str(run),'plan':plan,'plan_binding_sha256':p,'plan_file_sha256':m.digest(path),'adapter_source_sha256':'c'*64,'source_receipt_sha256':'a'*64}
    b=m.supervisor_binding(r);token='1'*32;job=m.JOB_PREFIX+token
    command=[str(root/'base.exe'),str(root/'code/full_ssb_local_model_run.py'),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',m.digest(path),'--start-token',token,'--job-name',job]
    worker=[str(root/'venv.exe'),command[1],'_worker']+command[3:]+['--bootstrap-pid','101']
    m.atomic(home/'bootstrap.json',dict(schema='ssb_local_sf500_bootstrap_v1',scope=m.source.SCOPE,status='PASS',returncode=0,pid=101,worker_launcher_pid=102,
        worker_command=worker,base_executable=env['python_base_executable'],membership_verified_after_go=True,named_job=job,plan_binding_sha256=p))
    m.atomic(home/'worker_start.json',dict(schema='ssb_local_sf500_worker_v1',scope=m.source.SCOPE,pid=103,parent_pid=102,bootstrap_pid=101,
        membership_verified_after_go=True,named_job=job,plan_binding_sha256=p,base_executable=env['python_base_executable'],venv_executable=env['python_executable']))
    resource=dict(available_memory_bytes=6*m.ops.GIB,free_disk_bytes=20*m.ops.GIB,existing_ssb_bytes=2*m.ops.GIB,storage_scan_age_seconds=0)
    m.atomic(home/'monitor.json',dict(status='PASS',returncode=0,stop_reason=None,binding=b,policy=m.ops.OPERATIONAL_POLICY,owned_process_only=True,
        job_object_kill_on_close=True,peak_owned_rss_bytes=10000,checks=2,last_resource_probe=resource,seconds=1,command=command))
    for name in ('stdout.log','stderr.log'):(home/name).write_bytes(b'')
    m.atomic(root/m.model.RESULT,{'fake':'publication'});m.atomic(run/'verification_seal.json',{'fake':'publication'})
    result=dict(returncode=0,peak_owned_rss_bytes=10000,resources_at_launch=resource,published_result_sha256=m.digest(root/m.model.RESULT),
        verification_seal_sha256=m.digest(run/'verification_seal.json'),artifacts=[m.artifact(home/name,root) for name in m.LOGS])
    return r,b,result


@pytest.mark.parametrize('damage',[None,'empty','rss','live_ram','launch_ram','stale_disk','wrong_command','not_owned','worker_parent','bootstrap','scope','publication'])
def test_local_supervisor_complete_physical_evidence(tmp_path,damage):
    m=module();r,b,result=evidence(m,tmp_path);home=Path(r['directory'])/'supervisor_control';monitor=m.read(home/'monitor.json')
    if damage=='empty':result['artifacts']=[]
    elif damage=='rss':monitor['peak_owned_rss_bytes']=7*m.ops.GIB
    elif damage=='live_ram':monitor['last_resource_probe']['available_memory_bytes']=0
    elif damage=='launch_ram':result['resources_at_launch']=dict(result['resources_at_launch'],available_memory_bytes=4*m.ops.GIB)
    elif damage=='stale_disk':monitor['last_resource_probe']['storage_scan_age_seconds']=91
    elif damage=='wrong_command':monitor['command'][1]=str(tmp_path/'old_strict.py')
    elif damage=='not_owned':monitor['owned_process_only']=False
    elif damage=='worker_parent':
        w=m.read(home/'worker_start.json');w['parent_pid']=999;m.atomic(home/'worker_start.json',w)
    elif damage=='bootstrap':
        w=m.read(home/'bootstrap.json');w['membership_verified_after_go']=False;m.atomic(home/'bootstrap.json',w)
    elif damage=='scope':
        w=m.read(home/'worker_start.json');w['scope']='AUTHOR';m.atomic(home/'worker_start.json',w)
    elif damage=='publication':result['published_result_sha256']='f'*64
    m.atomic(home/'monitor.json',monitor)
    if damage not in (None,'empty'):result['artifacts']=[m.artifact(home/name,tmp_path) for name in m.LOGS]
    if damage is None:assert len(m.verify_supervisor_result(r,b,result,tmp_path))==5
    else:
        with pytest.raises(ValueError):m.verify_supervisor_result(r,b,result,tmp_path)


def test_real_snapshot_absolute_twofield_venv_binding_and_relative_worker_descriptor(tmp_path):
    m=module();r,b,result=evidence(m,tmp_path);home=Path(r['directory'])/'supervisor_control'
    actual=m.artifact(tmp_path/'venv.exe',tmp_path)
    # Frozen dependency_snapshot emits this absolute two-field role. Worker
    # artifact(sys.executable) emits the relative three-field descriptor above.
    b['venv_executable']={'path':str((tmp_path/'venv.exe').resolve()),'sha256':actual['sha256']}
    monitor=m.read(home/'monitor.json');monitor['binding']=b;m.atomic(home/'monitor.json',monitor)
    result['artifacts']=[m.artifact(home/name,tmp_path) for name in m.LOGS]
    assert len(m.verify_supervisor_result(r,b,result,tmp_path))==5
    worker=m.read(home/'worker_start.json');worker['venv_executable']['bytes']+=1;m.atomic(home/'worker_start.json',worker)
    result['artifacts']=[m.artifact(home/name,tmp_path) for name in m.LOGS]
    with pytest.raises(ValueError):m.verify_supervisor_result(r,b,result,tmp_path)


def test_handshake_reads_go_before_job_membership(monkeypatch):
    import io
    m=module();calls=[];c=candidate(m);a=SimpleNamespace(job_name=m.JOB_PREFIX+'1'*32,start_token='1'*32,plan_path='fake',plan_file_sha256='a'*64)
    class Input(io.StringIO):
        def readline(self,*a):calls.append('GO');return super().readline(*a)
    monkeypatch.setattr(m.sys,'stdin',Input(json.dumps({'start':a.start_token,'plan_binding_sha256':m.value_hash(c)})+'\n'))
    monkeypatch.setattr(m.ops,'verify_owned_job_membership',lambda n:calls.append('assigned'))
    monkeypatch.setattr(m,'read_plan',lambda *a,**k:c)
    monkeypatch.setenv('DEEPDB_SSB_NATIVE_MODEL_WORKER','1')
    assert m.start_handshake(a)[0]==c and calls==['GO','assigned']


def test_failed_supervisor_taints_only_own_local_tail(tmp_path,monkeypatch):
    m=module();plan,path=plan_fixture(m,tmp_path);run=tmp_path/m.model.OUTPUT/'runs'/m.value_hash(plan)[:20]
    for name in ('formal','publication'):m.atomic(run/(name+'_control')/'lifecycle.json',{'status':'PASS'})
    strict=tmp_path/'output/full/ssb/native_v2/formal500/lifecycle.json';m.atomic(strict,{'status':'TAINTED','historical':True});before=strict.read_bytes()
    m.taint_local_tail(run,RuntimeError('synthetic supervisor interruption'))
    assert all(m.read(run/(name+'_control')/'lifecycle.json')['status']=='TAINTED' for name in ('formal','publication')) and before==strict.read_bytes()


@pytest.mark.skipif(os.name!='nt',reason='actual owned Windows tree proof')
def test_actual_local_bootstrap_delayed_assignment_and_schedule_tiny_owned_tree(tmp_path_factory,monkeypatch):
    """Local entry functions run, with only the scientific function replaced."""
    import secrets,time
    m=module();root=ROOT/'output/tmp'/('lb'+secrets.token_hex(4));root.mkdir(parents=True)
    rel=root.relative_to(ROOT).as_posix();plan={'synthetic_only':True};p=m.value_hash(plan);script=root/'tiny.py';result_path=rel+'/fake_result.json'
    code='''import sys,os,time,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,ROOT_CODE)
import full_ssb_local_model_run as m
m.SELF=SCRIPT_REL
m.model.OUTPUT=MOCK_OUTPUT
m.model.RESULT=MOCK_RESULT
m.read_plan=lambda *a,**k:PLAN
m.model.execute_local_formal=lambda *a,**k:{'status':'SYNTHETIC_NO_SCIENCE'}
a=SimpleNamespace(plan_path='pure-fake-plan',plan_file_sha256='a'*64,start_token=TOKEN,job_name=JOB,bootstrap_pid=int(sys.argv[-1]) if sys.argv[1]=='_worker' else None)
if sys.argv[1]=='_bootstrap':
    time.sleep(.3)
    m.bootstrap_entry(a)
else:
    m.worker_entry(a)
'''
    token=secrets.token_hex(16);job=m.JOB_PREFIX+token
    for name,value in {'ROOT_CODE':str(ROOT/'code'),'SCRIPT_REL':rel+'/tiny.py','MOCK_OUTPUT':rel+'/mock','MOCK_RESULT':result_path,'PLAN':plan,'TOKEN':token,'JOB':job}.items():code=code.replace(name,repr(value))
    script.write_bytes(code.encode('utf-8'));m.atomic(ROOT/result_path,{'synthetic_only':True})
    original=m.ops.OwnedWindowsJob.assign
    def delayed(self,process):time.sleep(.4);original(self,process)
    monkeypatch.setattr(m.ops.OwnedWindowsJob,'assign',delayed)
    policy=dict(m.ops.OPERATIONAL_POLICY,monitor_interval_seconds=.03)
    home=root/'mock/runs'/p[:20]/'supervisor_control'
    resource=lambda:dict(available_memory_bytes=8*m.ops.GIB,free_disk_bytes=30*m.ops.GIB,existing_ssb_bytes=0,storage_scan_age_seconds=0)
    r=m.ops.run_owned_child([str(m.ops.base_python_executable()),str(script),'_bootstrap'],home,{'synthetic_only':True},policy=policy,
        resource_probe=resource,start_payload={'start':token,'plan_binding_sha256':p},job_name=job)
    b=m.read(home/'bootstrap.json');w=m.read(home/'worker_start.json')
    assert r['returncode']==0 and b['status']=='PASS' and w['parent_pid']==b['worker_launcher_pid'] and w['bootstrap_pid']==b['pid']
    assert b['named_job']==w['named_job']==job and w['membership_verified_after_go'] is True
    assert all(not m.ops.windows_process_alive(pid) for pid in (b['pid'],b['worker_launcher_pid'],w['pid']))
