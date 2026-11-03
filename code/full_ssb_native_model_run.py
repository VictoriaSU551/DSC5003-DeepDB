"""Closed native SSB model launcher: owned child job and live resource policy."""
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import full_ssb_native_model as bridge
from full_ssb_native_model import (ROOT,GIB,MODEL,OUTPUT_REL,RESULT_REL,require,digest,value_hash,read,atomic,
    artifact_record,check_resources,verify_generation,dependency_snapshot,controller_lock,formal_transaction)

OPERATIONAL_POLICY=dict(minimum_launch_available_memory_bytes=5*GIB,minimum_live_available_memory_bytes=GIB,
    minimum_free_disk_bytes=8*GIB,maximum_ssb_bytes=16*GIB,maximum_owned_rss_bytes=6*GIB,
    monitor_interval_seconds=2,storage_scan_interval_seconds=30,maximum_storage_scan_age_seconds=90,wall_timeout_seconds=48*60*60)


def windows_api():
    import ctypes
    from ctypes import wintypes as w
    require(os.name=='nt','Windows Job Object required; no uncontrolled process fallback')
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    for name,args,result in [
        ('CreateJobObjectW',[w.LPVOID,w.LPCWSTR],w.HANDLE),
        ('SetInformationJobObject',[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD],w.BOOL),
        ('QueryInformationJobObject',[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD,w.LPVOID],w.BOOL),
        ('AssignProcessToJobObject',[w.HANDLE,w.HANDLE],w.BOOL),
        ('OpenJobObjectW',[w.DWORD,w.BOOL,w.LPCWSTR],w.HANDLE),
        ('IsProcessInJob',[w.HANDLE,w.HANDLE,w.LPVOID],w.BOOL),
        ('TerminateJobObject',[w.HANDLE,w.UINT],w.BOOL),('CloseHandle',[w.HANDLE],w.BOOL),
        ('OpenProcess',[w.DWORD,w.BOOL,w.DWORD],w.HANDLE),('GetExitCodeProcess',[w.HANDLE,w.LPVOID],w.BOOL)]:
        function=getattr(k,name);function.argtypes=args;function.restype=result
    return ctypes,w,k


def base_python_executable():
    path=Path(getattr(sys,'_base_executable',sys.executable)).resolve()
    require((ROOT/'.runtime').resolve() in path.parents and path.is_file(),'direct project base interpreter required')
    return path


def windows_process_alive(pid):
    c,w,k=windows_api();handle=k.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        code=w.DWORD();return bool(k.GetExitCodeProcess(handle,c.byref(code))) and code.value==259
    finally:k.CloseHandle(handle)


def live_owned_descendants(job,parent_pid):
    # Job accounting may briefly retain a dead venv base-interpreter PID after
    # the waiting launcher exits. Only genuinely live descendants are leaks.
    return [pid for pid in job.process_ids() if pid!=parent_pid and windows_process_alive(pid)]


class OwnedWindowsJob:
    """Kernel-owned tree; child must wait for stdin until assignment succeeds."""
    def __init__(self,name=None):
        c,w,k=windows_api();self.c,self.w,self.k=c,w,k;self.handle=k.CreateJobObjectW(None,name)
        if not self.handle:raise c.WinError(c.get_last_error())
        if name and c.get_last_error()==183:
            self.close();raise ValueError('named owned job already exists; no adoption')
        class Basic(c.Structure):
            _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),
                ('minimum_ws',c.c_size_t),('maximum_ws',c.c_size_t),('active_processes',w.DWORD),
                ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Io(c.Structure):_fields_=[(name,c.c_ulonglong) for name in ('read','write','other','read_bytes','write_bytes','other_bytes')]
        class Extended(c.Structure):
            _fields_=[('basic',Basic),('io',Io)]+[(name,c.c_size_t) for name in ('process_memory','job_memory','peak_process_memory','peak_job_memory')]
        limits=Extended();limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle,9,c.byref(limits),c.sizeof(limits)):
            error=c.get_last_error();self.close();raise c.WinError(error)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None
    def assign(self,process):
        if not self.k.AssignProcessToJobObject(self.handle,int(process._handle)):
            raise self.c.WinError(self.c.get_last_error())
    def process_ids(self):
        c,w,k=self.c,self.w,self.k;capacity=256;buffer=c.create_string_buffer(8+capacity*c.sizeof(c.c_size_t))
        if not k.QueryInformationJobObject(self.handle,3,buffer,c.sizeof(buffer),None):raise c.WinError(c.get_last_error())
        count=w.DWORD.from_buffer(buffer,4).value;require(count<=capacity,'owned process tree exceeds bounded PID buffer')
        return list((c.c_size_t*count).from_buffer(buffer,8))
    def working_set_bytes(self):
        c,w,k=self.c,self.w,self.k
        class Counters(c.Structure):
            _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(name,c.c_size_t) for name in
                ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        k.K32GetProcessMemoryInfo.argtypes=[w.HANDLE,w.LPVOID,w.DWORD];k.K32GetProcessMemoryInfo.restype=w.BOOL
        total=0
        for pid in self.process_ids():
            handle=k.OpenProcess(0x0410,False,pid)
            if not handle:
                require(not windows_process_alive(pid),'cannot read owned live process memory');continue
            try:
                value=Counters();value.cb=c.sizeof(value)
                if k.K32GetProcessMemoryInfo(handle,c.byref(value),value.cb):total+=value.ws
                else:require(not windows_process_alive(pid),'cannot probe owned live process memory')
            finally:k.CloseHandle(handle)
        return total
    def terminate(self):
        if not self.k.TerminateJobObject(self.handle,137):raise self.c.WinError(self.c.get_last_error())


def verify_owned_job_membership(name):
    require(isinstance(name,str) and name.startswith('Local\\DeepDB_SSB_NATIVE_'),'invalid owned job name')
    c,w,k=windows_api();job=k.OpenJobObjectW(4,False,name)
    require(bool(job),'named assigned job is missing')
    try:
        assigned=w.BOOL()
        require(k.IsProcessInJob(w.HANDLE(-1),job,c.byref(assigned)) and assigned.value,'worker is not assigned to its supervisor job')
    finally:k.CloseHandle(job)


def fast_resources(root=ROOT):
    c,w,k=windows_api()
    class Memory(c.Structure):
        _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(name,c.c_ulonglong) for name in
            ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','extended')]
    value=Memory();value.length=c.sizeof(value)
    require(k.GlobalMemoryStatusEx(c.byref(value)),'Windows available-memory probe failed')
    return dict(available_memory_bytes=int(value.avail_phys),free_disk_bytes=shutil.disk_usage(root).free)


def storage_bytes(root=ROOT,stopped=lambda:False):
    """Full physical walk; DirEntry metadata avoids repeated Windows stat calls."""
    total=0;stack=[Path(root)/folder for folder in ('data/ssb','output/full/ssb') if (Path(root)/folder).exists()]
    while stack:
        if stopped():return None
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                if stopped():return None
                require(not entry.is_symlink(),'SSB resource inventory symlink refused')
                if entry.is_dir(follow_symlinks=False):stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):total+=entry.stat(follow_symlinks=False).st_size
    return total


def operational_resources(root=ROOT):
    result=fast_resources(root);result.update(existing_ssb_bytes=storage_bytes(root),storage_scan_age_seconds=0);return result


class LiveResourceProbe:
    """A slow complete disk walk never delays the fast RSS/RAM/free-disk loop."""
    def __init__(self,root,initial,fast_probe=None,storage_probe=None,interval=None,maximum_age=None):
        import threading
        self.root=root;self.stop=threading.Event();self.error=None;self.latest=(initial['existing_ssb_bytes'],time.monotonic())
        self.fast_probe=fast_probe or (lambda:fast_resources(root))
        self.storage_probe=storage_probe or (lambda:storage_bytes(root,self.stop.is_set))
        self.interval=interval if interval is not None else OPERATIONAL_POLICY['storage_scan_interval_seconds']
        self.maximum_age=maximum_age if maximum_age is not None else OPERATIONAL_POLICY['maximum_storage_scan_age_seconds']
        self.thread=threading.Thread(target=self.loop,daemon=True,name='native-ssb-owned-storage-probe')
    def loop(self):
        while not self.stop.wait(self.interval):
            try:
                value=self.storage_probe()
                if value is not None:self.latest=(value,time.monotonic())
            except BaseException as error:self.error=repr(error);return
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.close()
    def close(self):self.stop.set();self.thread.join(timeout=2)
    def snapshot(self):
        require(self.error is None,'background storage scan failed: '+str(self.error))
        used,stamp=self.latest;age=time.monotonic()-stamp
        require(age<=self.maximum_age,'background storage scan is stale; refusing unmonitored worker')
        value=self.fast_probe();value.update(existing_ssb_bytes=used,storage_scan_age_seconds=age);return value
    def complete(self):
        self.close();require(not self.thread.is_alive(),'background storage probe did not stop')
        return operational_resources(self.root)


def run_owned_child(command,directory,binding,policy=None,resource_probe=None,root=ROOT,start_payload=None,job_name=None,initial_resources=None):
    """Operational primitive; production command is only the sealed waiting worker."""
    policy=dict(policy or OPERATIONAL_POLICY);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    require(Path(command[0]).resolve()==base_python_executable(),'only direct base bootstrap may be assigned; venv redirector refused')
    started=time.monotonic();peak=0;checks=0;reason=None;process=None;assigned=False;last=None;live=None
    require(not any((directory/name).exists() for name in ('stdout.log','stderr.log','monitor.json')),'owned child log namespace already used')
    env=dict(os.environ,DEEPDB_SSB_NATIVE_MODEL_WORKER='1')
    env.update({name:'1' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
    try:
        if resource_probe is None:
            live=LiveResourceProbe(root,initial_resources or operational_resources(root));live.__enter__();probe=live.snapshot
        else:probe=resource_probe
        with (directory/'stdout.log').open('wb') as out,(directory/'stderr.log').open('wb') as err,OwnedWindowsJob(job_name) as job:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,cwd=str(root),env=env,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                job.assign(process);assigned=True
                process.stdin.write((json.dumps(start_payload or {'start':'synthetic operational gate'})+'\n').encode());process.stdin.close()
                while True:
                    rss=job.working_set_bytes();peak=max(peak,rss);last=probe();checks+=1;elapsed=time.monotonic()-started
                    if rss>policy['maximum_owned_rss_bytes']:reason='resource owned RSS limit'
                    elif last['available_memory_bytes']<policy['minimum_live_available_memory_bytes']:reason='resource available RAM limit'
                    elif last['free_disk_bytes']<policy['minimum_free_disk_bytes']:reason='resource free disk limit'
                    elif last['existing_ssb_bytes']>policy['maximum_ssb_bytes']:reason='resource combined SSB disk budget'
                    elif elapsed>policy['wall_timeout_seconds']:reason='timeout wall-clock limit'
                    if reason:job.terminate();process.wait(timeout=10);break
                    if process.poll() is not None:
                        if live_owned_descendants(job,process.pid):reason='worker left live owned descendants';job.terminate()
                        break
                    time.sleep(policy['monitor_interval_seconds'])
            finally:
                # Before assignment the waiting bootstrap cannot spawn children.
                # Afterwards closing the job kills its complete assigned tree.
                if not assigned and process.poll() is None:process.kill()
        if process.poll() is None:process.wait(timeout=10)
        if process.returncode!=0 and reason is None:reason='worker process nonzero exit'
        if reason is None and live is not None:
            last=live.complete()
            if last['existing_ssb_bytes']>policy['maximum_ssb_bytes'] or last['free_disk_bytes']<policy['minimum_free_disk_bytes']:
                reason='resource final complete disk budget'
    except BaseException as error:
        reason=reason or 'operational exception: '+repr(error)
        if process is not None and process.poll() is None:process.wait(timeout=10)
        raise
    finally:
        if live is not None:live.close()
        atomic(directory/'monitor.json',dict(status='PASS' if reason is None else 'STOPPED',binding=binding,policy=policy,
            command=command,returncode=process.returncode if process is not None else None,stop_reason=reason,
            peak_owned_rss_bytes=peak,rss_scope='sum of live assigned-tree working sets, sampled at monitor interval',checks=checks,
            last_resource_probe=last,seconds=time.monotonic()-started,owned_process_only=True,job_object_kill_on_close=True))
    require(reason is None,'owned worker stopped: '+str(reason))
    return dict(returncode=process.returncode,peak_owned_rss_bytes=peak,
        artifacts=[artifact_record(directory/name,root) for name in ('stdout.log','stderr.log','monitor.json')])


def require_execution_review():
    require(bridge.FINAL_RECEIPT_INTERFACE_FROZEN and bridge.GENERATOR_CLOSURE_INTERFACE_FROZEN and bridge.FORMAL_PUBLICATION_REVIEW_COMPLETE,
            'native model source/closure/publication execution review remains closed')


def build_model_plan(source_receipt_sha256,root=ROOT):
    """Read-only candidate, never an approval or a scientific receipt."""
    require_execution_review();root=Path(root);require(root==ROOT,'actual model candidate requires project root')
    inputs=verify_generation(expected_receipt_sha256=source_receipt_sha256,root=root)
    return dict(schema='ssb_native_v2_model_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,
        source_receipt_sha256=inputs['receipt_sha256'],model=dict(MODEL),dependencies=dependency_snapshot(),operational_policy=dict(OPERATIONAL_POLICY))


def seal_reviewed_plan(source_receipt_sha256,root_reviewed_candidate_sha256,root=ROOT):
    candidate=build_model_plan(source_receipt_sha256,root)
    require(value_hash(candidate)==root_reviewed_candidate_sha256,'actual candidate differs from root-reviewed SHA')
    plan=dict(candidate,status='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN',executable=True,root_reviewed_candidate_sha256=root_reviewed_candidate_sha256)
    path=Path(root)/OUTPUT_REL/'plans'/value_hash(plan)[:20]/'plan.json'
    if path.exists() or path.with_suffix('.seal.json').exists():
        require(read_reviewed_plan(path,digest(path),root)==plan,'existing reviewed plan differs; preserve')
    else:atomic(path,plan);atomic(path.with_suffix('.seal.json'),{'sha256':digest(path)})
    return dict(plan=artifact_record(path,root),plan_binding_sha256=value_hash(plan))


def read_reviewed_plan(path,expected_sha,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve()
    require(digest(path)==expected_sha,'reviewed plan file SHA differs');plan=read(path)
    require(path==root/OUTPUT_REL/'plans'/value_hash(plan)[:20]/'plan.json'
            and read(path.with_suffix('.seal.json'))=={'sha256':expected_sha},'reviewed model plan namespace/seal differs')
    require(plan.get('schema')=='ssb_native_v2_model_plan_v1' and plan.get('status')=='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN'
            and plan.get('executable') is True and plan.get('model')==MODEL
            and plan.get('operational_policy')==OPERATIONAL_POLICY,'reviewed operational/model plan required')
    candidate=dict(plan);approved=candidate.pop('root_reviewed_candidate_sha256');candidate.update(status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False)
    require(value_hash(candidate)==approved,'reviewed candidate approval hash differs')
    return plan


def run_supervised(plan_path,expected_plan_sha256,memory_approved=False,root=ROOT):
    require_execution_review();require(memory_approved,'root memory release required');root=Path(root).resolve();path=Path(plan_path).resolve()
    require(root==ROOT,'reviewed physical plan root differs');plan=read_reviewed_plan(path,expected_plan_sha256,root);p=value_hash(plan)
    directory=root/OUTPUT_REL/'runs'/p[:20];home=directory/'supervisor_control'
    binding=supervisor_binding(dict(plan_binding_sha256=p,plan_file_sha256=expected_plan_sha256,
        adapter_source_sha256=digest(bridge.__file__),plan=plan))
    def produce():
        probe=operational_resources(root)
        check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'])
        require(probe['available_memory_bytes']>=OPERATIONAL_POLICY['minimum_launch_available_memory_bytes'],'at least5GiB available RAM required at launch')
        import secrets
        token=secrets.token_hex(16);job_name='Local\\DeepDB_SSB_NATIVE_'+token
        require(artifact_record(base_python_executable(),root)==binding['bootstrap_executable'],'reviewed direct base interpreter changed')
        command=[str(base_python_executable()),str(root/'code/full_ssb_native_model_run.py'),'_bootstrap',
                 '--plan-path',str(path),'--plan-file-sha256',expected_plan_sha256,'--start-token',token,'--job-name',job_name]
        result=run_owned_child(command,home,binding,root=root,start_payload=dict(start=token,plan_binding_sha256=p),job_name=job_name,initial_resources=probe)
        result['artifacts'].extend(artifact_record(home/name,root) for name in ('bootstrap.json','worker_start.json'))
        result['resources_at_launch']=probe
        verified=bridge.verify_formal_publication(root)
        result.update(published_result_sha256=verified['published_result']['sha256'],verification_seal_sha256=verified['verification_seal']['sha256'])
        return result
    def validate(result):verify_supervisor_result(directory,binding,result,root);bridge.verify_formal_publication(root)
    with controller_lock(root/OUTPUT_REL/'supervisor.lock'):
        try:return formal_transaction(home,binding,produce,validate,kind='SUPERVISOR')
        except BaseException as error:
            # A live resource stop may occur after child publication. Invalidate
            # any whole-run PASS instead of leaving a reusable successful tail.
            for kind in ('formal','publication'):
                control=directory/(kind+'_control');life=control/'lifecycle.json'
                if life.exists():
                    state=read(life);state.update(status='TAINTED',reason='supervisor failed: '+repr(error));atomic(life,state)
            raise


def verify_supervisor_result(directory,binding,result,root=ROOT):
    home=Path(directory)/'supervisor_control';monitor=read(home/'monitor.json')
    expected=[artifact_record(home/name,root) for name in ('stdout.log','stderr.log','monitor.json','bootstrap.json','worker_start.json')]
    require(result['artifacts']==expected and result['returncode']==0 and monitor['returncode']==0
            and monitor['status']=='PASS' and monitor['stop_reason'] is None and monitor['binding']==binding
            and monitor['policy']==OPERATIONAL_POLICY and monitor['owned_process_only'] is True
            and monitor['job_object_kill_on_close'] is True and monitor['peak_owned_rss_bytes']==result['peak_owned_rss_bytes']
            and 0<monitor['peak_owned_rss_bytes']<=OPERATIONAL_POLICY['maximum_owned_rss_bytes'],'complete owned supervisor monitor/result required')
    require(result['published_result_sha256']==digest(Path(root)/RESULT_REL)
            and result['verification_seal_sha256']==digest(Path(directory)/'verification_seal.json'),'supervisor scientific publication link differs')
    launch=result['resources_at_launch'];check_resources(launch['free_disk_bytes'],launch['available_memory_bytes'],launch['existing_ssb_bytes'])
    require(launch['available_memory_bytes']>=OPERATIONAL_POLICY['minimum_launch_available_memory_bytes'],'supervisor launch RAM evidence insufficient')
    last=monitor['last_resource_probe']
    require(type(monitor['checks']) is int and monitor['checks']>0 and 0<=monitor['seconds']<=OPERATIONAL_POLICY['wall_timeout_seconds']
            and last['available_memory_bytes']>=OPERATIONAL_POLICY['minimum_live_available_memory_bytes']
            and last['free_disk_bytes']>=OPERATIONAL_POLICY['minimum_free_disk_bytes']
            and last['existing_ssb_bytes']<=OPERATIONAL_POLICY['maximum_ssb_bytes'],'supervisor live resource evidence differs')
    command=monitor['command'];root=Path(root);import re
    expected_command=[str(root/binding['bootstrap_executable']['path']),str(root/'code/full_ssb_native_model_run.py'),'_bootstrap','--plan-path',
        str(root/OUTPUT_REL/'plans'/binding['plan_binding_sha256'][:20]/'plan.json'),'--plan-file-sha256',binding['plan_file_sha256']]
    require(isinstance(command,list) and len(command)==11 and command[:7]==expected_command and command[7]=='--start-token'
            and re.fullmatch('[a-f0-9]{32}',command[8]) is not None and command[9]=='--job-name'
            and command[10]=='Local\\DeepDB_SSB_NATIVE_'+command[8],'supervisor sealed waiting-worker command differs')
    require(binding['launcher_sha256']==digest(root/'code/full_ssb_native_model_run.py'),'supervisor launcher source changed')
    bootstrap=read(home/'bootstrap.json');worker=read(home/'worker_start.json')
    require(bootstrap.get('schema')=='ssb_native_v2_model_bootstrap_v1' and bootstrap['status']=='PASS' and bootstrap['returncode']==0 and bootstrap['membership_verified_after_go'] is True
            and bootstrap['base_executable']==binding['bootstrap_executable'] and bootstrap['named_job']==command[10]
            and bootstrap['plan_binding_sha256']==binding['plan_binding_sha256'],'complete direct-base bootstrap evidence required')
    expected_worker=[str(root/'.venv/Scripts/python.exe'),command[1],'_worker']+command[3:]+['--bootstrap-pid',str(bootstrap['pid'])]
    require(bootstrap['worker_command']==expected_worker and type(bootstrap['pid']) is int and bootstrap['pid']>0
            and type(bootstrap['worker_launcher_pid']) is int and bootstrap['worker_launcher_pid']>0,'bootstrap/venv worker command nesting differs')
    require(worker.get('schema')=='ssb_native_v2_model_worker_start_v1' and worker['membership_verified_after_go'] is True and worker['named_job']==command[10]
            and worker['plan_binding_sha256']==binding['plan_binding_sha256'] and worker['bootstrap_pid']==bootstrap['pid']
            and worker['parent_pid']==bootstrap['worker_launcher_pid'] and type(worker['pid']) is int and worker['pid']>0
            and worker['base_executable']==binding['bootstrap_executable'],'actual inherited venv worker identity differs')
    require((root/worker['venv_executable']['path']).resolve()==(root/'.venv/Scripts/python.exe').resolve()
            and worker['venv_executable']['sha256']==binding['venv_executable']['sha256'],'actual original venv executable differs')
    return expected


def supervisor_binding(report):
    return dict(plan_binding_sha256=report['plan_binding_sha256'],plan_file_sha256=report['plan_file_sha256'],
        bridge_sha256=report['adapter_source_sha256'],launcher_sha256=report['plan']['dependencies']['operational_launcher']['sha256'],
        bootstrap_executable=report['plan']['dependencies']['python_base_executable'],venv_executable=report['plan']['dependencies']['python_executable'],policy=OPERATIONAL_POLICY)


def verify_supervisor(report,root=ROOT):
    """No process launch/probe/repair; validate complete prior operational evidence."""
    directory=Path(report['directory']);home=directory/'supervisor_control';binding=supervisor_binding(report)
    state=read(home/'lifecycle.json');receipt=read(home/'receipt.json')
    require(state['status']==receipt['status']=='PASS' and receipt['kind']=='SUPERVISOR'
            and state['binding']==receipt['binding']==binding and state['receipt_sha256']==digest(home/'receipt.json'),
            'complete whole SUPERVISOR PASS required')
    records=verify_supervisor_result(directory,binding,receipt['result'],root)
    return records+[artifact_record(home/'receipt.json',root),artifact_record(home/'lifecycle.json',root)]


def start_handshake(args):
    require_execution_review()
    require(os.environ.get('DEEPDB_SSB_NATIVE_MODEL_WORKER')=='1','fresh supervised worker environment required')
    line=sys.stdin.readline(4097);require(len(line)<=4096 and line.endswith('\n'),'bounded supervisor start handshake required')
    verify_owned_job_membership(args.job_name)
    payload=json.loads(line);plan=read_reviewed_plan(args.plan_path,args.plan_file_sha256)
    require(payload==dict(start=args.start_token,plan_binding_sha256=value_hash(plan)),'supervisor start token/plan handshake differs')
    require(args.job_name=='Local\\DeepDB_SSB_NATIVE_'+args.start_token,'worker job/start binding differs')
    return plan,payload


def bootstrap_entry(args):
    plan,payload=start_handshake(args);home=ROOT/OUTPUT_REL/'runs'/value_hash(plan)[:20]/'supervisor_control'
    command=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'code/full_ssb_native_model_run.py'),'_worker','--plan-path',args.plan_path,
        '--plan-file-sha256',args.plan_file_sha256,'--start-token',args.start_token,'--job-name',args.job_name,'--bootstrap-pid',str(os.getpid())]
    launcher_pid,code=launch_inherited_venv_worker(command,payload,args.job_name)
    atomic(home/'bootstrap.json',dict(schema='ssb_native_v2_model_bootstrap_v1',status='PASS' if code==0 else 'FAILED',pid=os.getpid(),
        base_executable=artifact_record(base_python_executable()),worker_launcher_pid=launcher_pid,worker_command=command,returncode=code,
        membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(plan)))
    require(code==0,'original venv worker failed inside assigned bootstrap')
    return dict(status='PASS_BOOTSTRAP',worker_returncode=code)


def launch_inherited_venv_worker(command,payload,job_name):
    """Called only after GO by the direct base process already inside the job."""
    require(Path(command[0]).resolve()==(ROOT/'.venv/Scripts/python.exe').resolve(),'original venv worker executable required')
    verify_owned_job_membership(job_name)
    worker=subprocess.Popen(command,stdin=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    worker.stdin.write((json.dumps(payload)+'\n').encode());worker.stdin.close()
    return worker.pid,worker.wait()


def worker_entry(args):
    plan,payload=start_handshake(args)
    os.environ['DEEPDB_SSB_NATIVE_MODEL_JOB']=args.job_name
    home=ROOT/OUTPUT_REL/'runs'/value_hash(plan)[:20]/'supervisor_control';path=home/'worker_start.json'
    require(not path.exists(),'worker-start namespace already used; no replacement')
    atomic(path,dict(schema='ssb_native_v2_model_worker_start_v1',pid=os.getpid(),parent_pid=os.getppid(),bootstrap_pid=args.bootstrap_pid,
        membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(plan),
        base_executable=artifact_record(base_python_executable()),venv_executable=artifact_record(sys.executable)))
    report=bridge.execute_formal(plan,memory_approved=True)
    return dict(status=report['status'],directory=report['directory'],published_result_sha256=digest(ROOT/RESULT_REL))


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    candidate=sub.add_parser('candidate-plan');candidate.add_argument('--source-receipt-sha256',required=True)
    seal=sub.add_parser('seal-plan');seal.add_argument('--source-receipt-sha256',required=True);seal.add_argument('--root-reviewed-candidate-sha256',required=True)
    run=sub.add_parser('supervise');run.add_argument('--plan-path',required=True);run.add_argument('--plan-file-sha256',required=True)
    run.add_argument('--root-memory-approved',action='store_true')
    for kind in ('_bootstrap','_worker'):
        worker=sub.add_parser(kind,help=argparse.SUPPRESS)
        for name in ('plan-path','plan-file-sha256','start-token','job-name'):worker.add_argument('--'+name,required=True)
        if kind=='_worker':worker.add_argument('--bootstrap-pid',required=True,type=int)
    args=parser.parse_args(argv)
    if args.command=='candidate-plan':result=build_model_plan(args.source_receipt_sha256)
    elif args.command=='seal-plan':result=seal_reviewed_plan(args.source_receipt_sha256,args.root_reviewed_candidate_sha256)
    elif args.command=='supervise':result=run_supervised(args.plan_path,args.plan_file_sha256,args.root_memory_approved)
    elif args.command=='_bootstrap':result=bootstrap_entry(args)
    else:result=worker_entry(args)
    print(json.dumps(result,sort_keys=True,allow_nan=False));return 0


if __name__=='__main__':raise SystemExit(main())
