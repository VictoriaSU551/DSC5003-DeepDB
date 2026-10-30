"""Pure plan and configurable operational capsule tests, no scientific worker."""
import copy
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_ssb_local_ci_run.py';assert path.exists(),'10M CI runner missing'
    s=importlib.util.spec_from_file_location('ci_run_test',str(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def plan_fixture(m,root,kind='FORMAL'):
    c=m.candidate_body(kind,'a'*64,{}, {'ci_sources':{p:'b'*64 for p in m.model.FILES}}, {'parent_formal':{'path':'old-formal','sha256':'c'*64},'parent_reverse':{'path':'old-reverse','sha256':'d'*64}})
    p=dict(c,status='ROOT_REVIEWED_LOCAL_SSB_10M_CI_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    path=root/m.model.OUTPUT/'plans'/m.value_hash(p)[:20]/'plan.json';m.atomic(path,p);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    return p,path


@pytest.mark.parametrize('kind',['FORMAL','GOLDEN'])
@pytest.mark.parametrize('damage',[None,'scope','cap','rows','reserve','ram','policy','approval'])
def test_ci_plan_scope_cap_resources_exact_approval(tmp_path,kind,damage):
    m=module();p,path=plan_fixture(m,tmp_path,kind)
    if damage is None:assert m.read_plan(path,m.digest(path),tmp_path)==p;return
    if damage=='scope':p['scope']='LOCAL_SSB_SF500'
    elif damage=='cap':p['model']['samples_per_spn']=1000000
    elif damage=='rows':p['actual_training_rows_per_table']['lineorder']=10000000
    elif damage=='reserve':p['resource_admission']['additional_bytes']=5*2**30
    elif damage=='ram':p['resource_admission']['minimum_launch_memory_bytes']=5*2**30
    elif damage=='policy':p['operational_policy']['maximum_owned_rss_bytes']=8*2**30
    else:p['root_reviewed_candidate_sha256']='f'*64
    m.atomic(path,p);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    with pytest.raises(ValueError):m.read_plan(path,m.digest(path),tmp_path)


def test_ci_execution_without_explicit_memory_release_creates_nothing(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='memory'):m.run_supervised('none','a'*64,memory_approved=False,root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_operational_capsule_binds_exact_frozen_implementation_and_distinct_schemas():
    m=module();b=m.capsule_binding()
    assert b['frozen_operational_sha256']==m.model.PRIOR_PINS['code/full_ssb_local_model_run.py']
    assert b['source_sha256']!=b['configured_source_sha256'] and b['scope']==m.model.SCOPE
    assert {'verify_supervisor_result','verify_supervisor','start_handshake','bootstrap_entry','taint_local_tail'}==set(b['functions'])


def test_ci_supervisor_reuses_complete_evidence_checks_and_adds7gib_launch(tmp_path):
    import test_full_ssb_local_model_run as fixtures
    m=module();real_binding=m.supervisor_binding
    def fixture_binding(r):
        r['plan']['dependencies']['ci_sources']={m.SELF:r['plan']['dependencies']['local_sources']['code/full_ssb_local_model_run.py']}
        return real_binding(r)
    m.supervisor_binding=fixture_binding
    r,b,result=fixtures.evidence(m,tmp_path);m.supervisor_binding=real_binding;home=Path(r['directory'])/'supervisor_control'
    # The shared fixture makes1M schema and commands; change only local labels.
    mon=m.read(home/'monitor.json');mon['command'][1]=str(tmp_path/m.SELF)
    boot=m.read(home/'bootstrap.json');boot['schema']='ssb_local_ci10m_bootstrap_v1';boot['worker_command'][1]=str(tmp_path/m.SELF)
    worker=m.read(home/'worker_start.json');worker['schema']='ssb_local_ci10m_worker_v1'
    path=tmp_path/m.SELF;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'pure fake identity');b['launcher_sha256']=m.digest(path)
    mon['binding']=b
    for name,body in [('monitor.json',mon),('bootstrap.json',boot),('worker_start.json',worker)]:m.atomic(home/name,body)
    result['artifacts']=[m.artifact(home/name,tmp_path) for name in m.LOGS]
    with pytest.raises(ValueError,match='7GiB'):m.verify_supervisor_result(r,b,result,tmp_path)
    result['resources_at_launch']['available_memory_bytes']=8*2**30
    assert len(m.verify_supervisor_result(r,b,result,tmp_path))==5
    # Reused HDFs already count in the12GiB observed total. The old5GiB
    # preparation reserve would reject despite the reviewed2GiB+64MiB budget.
    result['resources_at_launch']['existing_ssb_bytes']=12*2**30
    assert len(m.verify_supervisor_result(r,b,result,tmp_path))==5


def test_actual_ci_waiting_bootstrap_tiny_owned_tree_no_scientific_call(monkeypatch):
    import os,secrets,time
    if os.name!='nt':pytest.skip('owned Windows micro gate')
    m=module();root=ROOT/'output/tmp'/('cb'+secrets.token_hex(4));root.mkdir(parents=True);rel=root.relative_to(ROOT).as_posix()
    token=secrets.token_hex(16);job=m.JOB_PREFIX+token;plan={'synthetic_only':True,'kind':'GOLDEN'};p=m.value_hash(plan);script=root/'tiny.py'
    code='''import sys,os,time
from types import SimpleNamespace
sys.path.insert(0,ROOT_CODE)
import full_ssb_local_ci_run as m
m.SELF=SCRIPT_REL
m.model.OUTPUT=MOCK_OUTPUT
m.read_plan=lambda *a,**k:PLAN
m.model.execute_worker=lambda *a,**k:{'status':'SYNTHETIC_NO_SCIENCE'}
a=SimpleNamespace(plan_path='pure-fake-plan',plan_file_sha256='a'*64,start_token=TOKEN,job_name=JOB,bootstrap_pid=int(sys.argv[-1]) if sys.argv[1]=='_worker' else None)
if sys.argv[1]=='_bootstrap':
    time.sleep(.3)
    m.bootstrap_entry(a)
else:m.worker_entry(a)
'''
    for name,value in {'ROOT_CODE':str(ROOT/'code'),'SCRIPT_REL':rel+'/tiny.py','MOCK_OUTPUT':rel+'/mock','PLAN':plan,'TOKEN':token,'JOB':job}.items():code=code.replace(name,repr(value))
    script.write_bytes(code.encode());original=m.ops.OwnedWindowsJob.assign
    def delayed(self,process):time.sleep(.4);original(self,process)
    monkeypatch.setattr(m.ops.OwnedWindowsJob,'assign',delayed)
    home=root/'mock/runs'/p[:20]/'supervisor_control';policy=dict(m.ops.OPERATIONAL_POLICY,monitor_interval_seconds=.03)
    resources=lambda:dict(available_memory_bytes=8*2**30,free_disk_bytes=30*2**30,existing_ssb_bytes=0,storage_scan_age_seconds=0)
    result=m.ops.run_owned_child([str(m.ops.base_python_executable()),str(script),'_bootstrap'],home,{'synthetic_only':True},policy=policy,
        resource_probe=resources,start_payload={'start':token,'plan_binding_sha256':p},job_name=job)
    b=m.read(home/'bootstrap.json');w=m.read(home/'worker_start.json')
    assert result['returncode']==0 and b['status']=='PASS' and b['schema']=='ssb_local_ci10m_bootstrap_v1' and w['schema']=='ssb_local_ci10m_worker_v1'
    assert w['parent_pid']==b['worker_launcher_pid'] and w['bootstrap_pid']==b['pid'] and w['named_job']==job
    assert all(not m.ops.windows_process_alive(pid) for pid in (b['pid'],b['worker_launcher_pid'],w['pid']))
