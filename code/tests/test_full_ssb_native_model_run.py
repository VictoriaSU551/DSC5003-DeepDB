"""Operational subprocess tests only; no generator/model/preparation calls."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import time
import pytest
ROOT=Path(__file__).resolve().parents[2]

def module():
    if str(ROOT/'code') not in sys.path:sys.path.insert(0,str(ROOT/'code'))
    path=ROOT/'code/full_ssb_native_model_run.py'
    spec=importlib.util.spec_from_file_location('native_ssb_model_run',str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_owned_windows_job_closes_only_its_waiting_process_tree(tmp_path):
    m=module();grandchild=tmp_path/'grandchild.txt'
    code="import sys,subprocess,time;sys.stdin.readline();p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);open(sys.argv[1],'w').write(str(p.pid));time.sleep(60)"
    proc=subprocess.Popen([str(m.base_python_executable()),'-c',code,str(grandchild)],stdin=subprocess.PIPE)
    try:
        with m.OwnedWindowsJob() as job:
            job.assign(proc);proc.stdin.write(b'GO\n');proc.stdin.close()
            deadline=time.monotonic()+5
            while not grandchild.exists() and time.monotonic()<deadline:time.sleep(.05)
            assert grandchild.exists()
            ids=job.process_ids();child_pid=int(grandchild.read_text())
            assert proc.pid in ids and child_pid in ids and __import__('os').getpid() not in ids
            assert job.working_set_bytes()>0
        proc.wait(timeout=5)
        assert not m.windows_process_alive(proc.pid)
        assert not m.windows_process_alive(child_pid)
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=5)


@pytest.mark.parametrize('violation',[None,'ram','disk','budget','rss','timeout'])
def test_bounded_child_records_real_process_and_policy_failures(tmp_path,violation):
    m=module();policy=dict(m.OPERATIONAL_POLICY,monitor_interval_seconds=.01,wall_timeout_seconds=5)
    snapshot=dict(available_memory_bytes=8*m.GIB,free_disk_bytes=30*m.GIB,existing_ssb_bytes=0)
    if violation=='ram':snapshot['available_memory_bytes']=m.GIB-1
    elif violation=='disk':snapshot['free_disk_bytes']=8*m.GIB-1
    elif violation=='budget':snapshot['existing_ssb_bytes']=16*m.GIB+1
    elif violation=='rss':policy['maximum_owned_rss_bytes']=1
    elif violation=='timeout':policy['wall_timeout_seconds']=.01
    code="import sys,time;sys.stdin.readline();print('SYNTHETIC worker only',flush=True);time.sleep(.15)"
    run=lambda:m.run_owned_child([str(m.base_python_executable()),'-c',code],tmp_path,{'synthetic_only':True},policy,lambda:snapshot,root=tmp_path)
    if violation is None:
        result=run();assert result['returncode']==0 and result['peak_owned_rss_bytes']>0
    else:
        with pytest.raises(ValueError,match='resource|timeout'):run()
    monitor=m.read(tmp_path/'monitor.json')
    assert monitor['status']==('PASS' if violation is None else 'STOPPED')
    assert monitor['binding']=={'synthetic_only':True} and monitor['owned_process_only'] is True
    assert (tmp_path/'stdout.log').is_file() and (tmp_path/'stderr.log').is_file()


def test_operational_plan_and_supervisor_stay_closed_without_scientific_approval(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.bridge,'FINAL_RECEIPT_INTERFACE_FROZEN',False)
    with pytest.raises(ValueError,match='closed|review|frozen'):m.build_model_plan('0'*64)
    with pytest.raises(ValueError,match='closed|review|frozen'):m.run_supervised(tmp_path/'plan.json','0'*64,True)


def test_terminate_owned_job_proves_active_zero_and_unrelated_parent_survives():
    m=module();proc=subprocess.Popen([str(m.base_python_executable()),'-c','import sys,time;sys.stdin.readline();time.sleep(60)'],stdin=subprocess.PIPE)
    try:
        with m.OwnedWindowsJob() as job:
            job.assign(proc);proc.stdin.write(b'GO\n');proc.stdin.close();assert proc.pid in job.process_ids()
            job.terminate();proc.wait(timeout=5)
            assert job.process_ids()==[] and m.windows_process_alive(__import__('os').getpid())
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=5)


def test_named_job_membership_refuses_supervisor_and_accepts_only_assigned_child(tmp_path):
    m=module();name='Local\\DeepDB_SSB_NATIVE_pure_'+str(__import__('os').getpid())
    with m.OwnedWindowsJob(name):
        with pytest.raises(ValueError,match='assigned'):m.verify_owned_job_membership(name)
    code="import sys;sys.stdin.readline();sys.path.insert(0,sys.argv[1]);import full_ssb_native_model_run as m;m.verify_owned_job_membership(sys.argv[2]);print('ASSIGNED',flush=True)"
    policy=dict(m.OPERATIONAL_POLICY,monitor_interval_seconds=.01)
    probe=lambda:dict(available_memory_bytes=8*m.GIB,free_disk_bytes=30*m.GIB,existing_ssb_bytes=0)
    result=m.run_owned_child([str(m.base_python_executable()),'-c',code,str(ROOT/'code'),name],tmp_path,{'synthetic_only':True},policy,probe,root=tmp_path,job_name=name)
    assert result['returncode']==0 and b'ASSIGNED' in (tmp_path/'stdout.log').read_bytes()


def test_reviewed_plan_sealing_is_bound_to_reviewed_candidate_and_reuses_exact_bytes(tmp_path,monkeypatch):
    m=module();candidate=dict(schema='ssb_native_v2_model_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,
        source_receipt_sha256='a'*64,model=m.MODEL,dependencies={'synthetic_only':True},operational_policy=m.OPERATIONAL_POLICY)
    monkeypatch.setattr(m,'build_model_plan',lambda *a,**k:candidate)
    with pytest.raises(ValueError,match='reviewed'):m.seal_reviewed_plan('a'*64,'0'*64,tmp_path)
    assert list(tmp_path.iterdir())==[]
    result=m.seal_reviewed_plan('a'*64,m.value_hash(candidate),tmp_path);path=tmp_path/result['plan']['path'];stamp=path.stat().st_mtime_ns
    assert m.seal_reviewed_plan('a'*64,m.value_hash(candidate),tmp_path)==result
    assert path.stat().st_mtime_ns==stamp
    plan=m.read(path);assert m.read_reviewed_plan(path,m.digest(path),tmp_path)==plan
    path.with_suffix('.seal.json').unlink()
    with pytest.raises((ValueError,OSError)):m.seal_reviewed_plan('a'*64,m.value_hash(candidate),tmp_path)


def test_operational_cli_help_and_closed_worker_fail_without_input_or_science(monkeypatch):
    script=ROOT/'code/full_ssb_native_model_run.py'
    help_run=subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True,timeout=10)
    assert help_run.returncode==0 and 'supervise' in help_run.stdout and 'candidate-plan' in help_run.stdout
    m=module();monkeypatch.setattr(m.bridge,'FINAL_RECEIPT_INTERFACE_FROZEN',False)
    with pytest.raises(ValueError,match='closed'):
        m.main(['_worker','--plan-path','missing','--plan-file-sha256','0'*64,
            '--start-token','a'*32,'--job-name','Local\\DeepDB_SSB_NATIVE_'+'a'*32,'--bootstrap-pid','1'])


def synthetic_supervisor(m,root):
    source=root/'code/full_ssb_native_model_run.py';source.parent.mkdir();source.write_bytes(Path(m.__file__).read_bytes())
    base=root/'.runtime/python/python.exe';base.parent.mkdir(parents=True);base.write_bytes(b'SYNTHETIC base executable')
    venv=root/'.venv/Scripts/python.exe';venv.parent.mkdir(parents=True);venv.write_bytes(b'SYNTHETIC venv redirector')
    run=root/m.OUTPUT_REL/'runs'/('a'*20);home=run/'supervisor_control';home.mkdir(parents=True)
    output=root/m.RESULT_REL;output.parent.mkdir(parents=True);output.write_bytes(b'SYNTHETIC scientific report bytes\n')
    (run/'verification_seal.json').write_bytes(b'SYNTHETIC scientific seal bytes\n')
    report=dict(directory=str(run),plan_binding_sha256='a'*64,plan_file_sha256='b'*64,adapter_source_sha256='c'*64,
        plan={'dependencies':{'operational_launcher':m.artifact_record(source,root),'python_base_executable':m.artifact_record(base,root),
            'python_executable':{'path':str(venv),'sha256':m.digest(venv)}}})
    binding=m.supervisor_binding(report);token='d'*32
    command=[str(base),str(source),'_bootstrap','--plan-path',str(root/m.OUTPUT_REL/'plans'/('a'*20)/'plan.json'),
        '--plan-file-sha256','b'*64,'--start-token',token,'--job-name','Local\\DeepDB_SSB_NATIVE_'+token]
    for name in ('stdout.log','stderr.log'):(home/name).write_bytes(b'SYNTHETIC operational log\n')
    probe=dict(available_memory_bytes=8*m.GIB,free_disk_bytes=30*m.GIB,existing_ssb_bytes=0)
    m.atomic(home/'monitor.json',dict(status='PASS',binding=binding,policy=m.OPERATIONAL_POLICY,command=command,returncode=0,
        stop_reason=None,peak_owned_rss_bytes=10,checks=1,last_resource_probe=probe,seconds=.2,owned_process_only=True,job_object_kill_on_close=True))
    m.atomic(home/'bootstrap.json',dict(schema='ssb_native_v2_model_bootstrap_v1',status='PASS',returncode=0,membership_verified_after_go=True,base_executable=m.artifact_record(base,root),
        named_job=command[10],plan_binding_sha256='a'*64,pid=111,worker_launcher_pid=222,
        worker_command=[str(venv),str(source),'_worker']+command[3:]+['--bootstrap-pid','111']))
    m.atomic(home/'worker_start.json',dict(schema='ssb_native_v2_model_worker_start_v1',membership_verified_after_go=True,named_job=command[10],plan_binding_sha256='a'*64,
        bootstrap_pid=111,parent_pid=222,pid=333,base_executable=m.artifact_record(base,root),venv_executable=m.artifact_record(venv,root)))
    result=dict(returncode=0,peak_owned_rss_bytes=10,artifacts=[m.artifact_record(home/name,root) for name in ('stdout.log','stderr.log','monitor.json','bootstrap.json','worker_start.json')],
        resources_at_launch=probe,published_result_sha256=m.digest(output),verification_seal_sha256=m.digest(run/'verification_seal.json'))
    m.formal_transaction(home,binding,lambda:result,lambda r:m.verify_supervisor_result(run,binding,r,root),kind='SUPERVISOR')
    return report


@pytest.mark.parametrize('damage',[None,'running','omit_log','monitor_stop','command','publication','launch_ram','bootstrap_subset','worker_parent'])
def test_supervisor_readonly_complete_receipt_and_publication_link(tmp_path,damage):
    m=module();report=synthetic_supervisor(m,tmp_path);home=Path(report['directory'])/'supervisor_control'
    if damage=='running':m.atomic(home/'lifecycle.json',dict(status='RUNNING'))
    elif damage=='omit_log':(home/'stdout.log').unlink()
    elif damage in ('monitor_stop','command'):
        path=home/'monitor.json';monitor=m.read(path)
        if damage=='monitor_stop':monitor['stop_reason']='resource RSS stop';monitor['status']='STOPPED'
        else:monitor['command'][1]='unowned_launcher.py'
        m.atomic(path,monitor)
    elif damage=='publication':(tmp_path/m.RESULT_REL).write_bytes(b'changed')
    elif damage=='launch_ram':
        receipt=m.read(home/'receipt.json');receipt['result']['resources_at_launch']['available_memory_bytes']=4*m.GIB
        m.atomic(home/'receipt.json',receipt);state=m.read(home/'lifecycle.json');state['receipt_sha256']=m.digest(home/'receipt.json');m.atomic(home/'lifecycle.json',state)
    elif damage in ('bootstrap_subset','worker_parent'):
        path=home/('bootstrap.json' if damage=='bootstrap_subset' else 'worker_start.json');record=m.read(path)
        if damage=='bootstrap_subset':record.pop('base_executable')
        else:record['parent_pid']=999
        m.atomic(path,record)
        receipt=m.read(home/'receipt.json');receipt['result']['artifacts']=[m.artifact_record(home/name,tmp_path) for name in ('stdout.log','stderr.log','monitor.json','bootstrap.json','worker_start.json')]
        m.atomic(home/'receipt.json',receipt);state=m.read(home/'lifecycle.json');state['receipt_sha256']=m.digest(home/'receipt.json');m.atomic(home/'lifecycle.json',state)
    if damage is None:
        before={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}
        assert len(m.verify_supervisor(report,tmp_path))==7
        assert before=={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}
    else:
        with pytest.raises((ValueError,OSError,KeyError)):m.verify_supervisor(report,tmp_path)


def test_background_storage_scan_cannot_block_fast_rss_ram_loop():
    import threading
    m=module();entered=threading.Event();release=threading.Event()
    def slow():entered.set();release.wait(3);return 123
    fast=lambda:dict(available_memory_bytes=8*m.GIB,free_disk_bytes=30*m.GIB)
    with m.LiveResourceProbe(ROOT,{'existing_ssb_bytes':0},fast_probe=fast,storage_probe=slow,interval=.01,maximum_age=.2) as probe:
        assert entered.wait(1)
        started=time.monotonic();assert probe.snapshot()['existing_ssb_bytes']==0
        assert time.monotonic()-started<.1
        time.sleep(.21)
        with pytest.raises(ValueError,match='stale'):probe.snapshot()
        release.set()


def test_background_storage_failure_refuses_next_snapshot():
    m=module()
    def fail():raise OSError('synthetic stat failure')
    with m.LiveResourceProbe(ROOT,{'existing_ssb_bytes':0},fast_probe=lambda:{},storage_probe=fail,interval=.01) as probe:
        deadline=time.monotonic()+1
        while probe.error is None and time.monotonic()<deadline:time.sleep(.01)
        with pytest.raises(ValueError,match='storage'):probe.snapshot()


def test_storage_byte_scan_is_complete_and_stops_only_its_readonly_walk(tmp_path):
    m=module();(tmp_path/'data/ssb/a').mkdir(parents=True);(tmp_path/'output/full/ssb/b').mkdir(parents=True)
    (tmp_path/'data/ssb/a/one').write_bytes(b'123');(tmp_path/'output/full/ssb/b/two').write_bytes(b'12345')
    assert m.storage_bytes(tmp_path)==8
    assert m.storage_bytes(tmp_path,stopped=lambda:True) is None


def test_real_default_resource_probe_completes_tiny_child_and_final_storage_scan(tmp_path):
    m=module();policy=dict(m.OPERATIONAL_POLICY,monitor_interval_seconds=.01)
    result=m.run_owned_child([str(m.base_python_executable()),'-c','import sys,time;sys.stdin.readline();time.sleep(.05)'],tmp_path,{'synthetic_only':True},policy,root=tmp_path)
    assert result['returncode']==0
    monitor=m.read(tmp_path/'monitor.json')
    assert monitor['last_resource_probe']['existing_ssb_bytes']==0 and monitor['last_resource_probe']['storage_scan_age_seconds']==0


def test_parent_success_with_leaked_owned_descendant_is_refused(tmp_path):
    m=module();policy=dict(m.OPERATIONAL_POLICY,monitor_interval_seconds=.01)
    code="import sys,subprocess;sys.stdin.readline();subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])"
    probe=lambda:dict(available_memory_bytes=8*m.GIB,free_disk_bytes=30*m.GIB,existing_ssb_bytes=0)
    with pytest.raises(ValueError,match='descendants'):
        m.run_owned_child([str(m.base_python_executable()),'-c',code],tmp_path,{'synthetic_only':True},policy,probe,root=tmp_path)
    assert m.read(tmp_path/'monitor.json')['status']=='STOPPED'


def test_dead_post_exit_job_accounting_entry_is_not_a_live_descendant(monkeypatch):
    m=module();job=type('FakeJob',(),{'process_ids':lambda self:[1,2,3]})()
    monkeypatch.setattr(m,'windows_process_alive',lambda pid:pid==3)
    assert m.live_owned_descendants(job,1)==[3]
    monkeypatch.setattr(m,'windows_process_alive',lambda pid:False)
    assert m.live_owned_descendants(job,1)==[]


@pytest.mark.parametrize('assignment_delay,child_delay',[(.5,0),(0,.5),(.5,.5)])
def test_delayed_assignment_base_bootstrap_then_nested_real_venv_are_all_owned(tmp_path,monkeypatch,assignment_delay,child_delay):
    m=module();base=m.base_python_executable();name='Local\\DeepDB_SSB_NATIVE_delay_'+str(__import__('os').getpid())
    original=m.OwnedWindowsJob.assign
    def delayed(job,process):time.sleep(assignment_delay);original(job,process)
    monkeypatch.setattr(m.OwnedWindowsJob,'assign',delayed)
    worker="import sys,os;sys.stdin.readline();sys.path.insert(0,sys.argv[1]);import full_ssb_native_model_run as m;m.verify_owned_job_membership(sys.argv[2]);print('VENV_MEMBER',os.getpid(),os.getppid())"
    bootstrap="import sys,time;sys.stdin.readline();time.sleep(float(sys.argv[4]));sys.path.insert(0,sys.argv[1]);import full_ssb_native_model_run as m;pid,rc=m.launch_inherited_venv_worker([sys.argv[3],'-c',sys.argv[5],sys.argv[1],sys.argv[2]],{'synthetic_only':True},sys.argv[2]);print('LAUNCHER_PID',pid);raise SystemExit(rc)"
    probe=lambda:dict(available_memory_bytes=8*m.GIB,free_disk_bytes=30*m.GIB,existing_ssb_bytes=0)
    policy=dict(m.OPERATIONAL_POLICY,monitor_interval_seconds=.01)
    result=m.run_owned_child([str(base),'-c',bootstrap,str(ROOT/'code'),name,sys.executable,str(child_delay),worker],tmp_path,
        {'synthetic_only':True},policy,probe,root=tmp_path,job_name=name)
    assert result['returncode']==0 and b'VENV_MEMBER' in (tmp_path/'stdout.log').read_bytes()
    lines=(tmp_path/'stdout.log').read_text().splitlines();worker_line=next(x for x in lines if x.startswith('VENV_MEMBER')).split()
    launcher_line=next(x for x in lines if x.startswith('LAUNCHER_PID')).split()
    assert worker_line[2]==launcher_line[1] and worker_line[1]!=launcher_line[1]
