"""Pure canonical supervisor planning, no actual Job/model execution."""
import importlib.util
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
    r=m.child_report(p,phase);binding=m.supervisor_binding(r);home=Path(r['directory'])/(phase.lower()+'_control');token='1'*32;job='Local\\DeepDB_SSB_CANONICAL_'+phase+'_'+token
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
