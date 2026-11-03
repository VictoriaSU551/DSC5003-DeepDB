"""Quiet operational controller; frozen SSB science is called only after gates.

The existing generator is never started, stopped or restarted here. Checkpoint
reads request Windows share7 and close the handle before parsing. A remaining
short binary-read window is covered by the already running generator's bounded
WinError5/32 retry adapter; share7 alone is not a zero-conflict guarantee.
"""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/full/ssb/supervisor'
MODELS=ROOT/'output/full/ssb/models'
PLAN_SHA256='6c4dbad583371c8cee01f7ccd4d9045071f73273cca1f9ffb3d8138ff56a6aca'
READINESS_SHA256='23c998881c15775449eb0d1c7cfccc1c732459bc803f2c72d046b24498431fc7'
OUTER_SHA256='b6aecc212ba4e1b436456729ba6c82bed2f715e3394e31d4e15f6a08818d150d'
GIB=1024**3
LAST_READS={}


def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def read_shared(path):
    started=time.perf_counter()
    if os.name!='nt':
        with Path(path).open('rb') as stream:data=stream.read(32*1024**2+1)
        if len(data)>32*1024**2:raise ValueError('Operational JSON exceeds32MiB read bound')
        LAST_READS[str(path)]={'bytes':len(data),'handle_read_seconds':time.perf_counter()-started}
        return json.loads(data.decode('utf-8'))
    import msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,
                                 wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    handle=kernel.CreateFileW(str(Path(path).resolve()),0x80000000,7,None,3,128,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except BaseException:
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle);raise
    with os.fdopen(fd,'rb') as stream:data=stream.read(32*1024**2+1)
    # Closing before json.loads materially shortens the reader lifetime. It does
    # not pretend to eliminate every possible overlap during the binary read.
    if len(data)>32*1024**2:raise ValueError('Operational JSON exceeds32MiB read bound')
    LAST_READS[str(path)]={'bytes':len(data),'handle_read_seconds':time.perf_counter()-started}
    return json.loads(data.decode('utf-8'))


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temp),str(path))


def generation_decision(result,checkpoint):
    if result.get('status')=='MISMATCH':raise ValueError('Final generator author truth/row MISMATCH; no formal model may start')
    if result.get('status')!='PASS' or result.get('complete') is not True:return 'WAIT_GENERATION'
    if (result.get('rows')!=3000028242 or checkpoint.get('rows')!=3000028242 or
        result.get('row_count_matches_author') is not True or result.get('author_truth_comparison',{}).get('match') is not True or
        checkpoint.get('next_shard')!=4001 or
        [x['shard'] for x in checkpoint.get('committed_shards',[])]!=list(range(1,4001)) or
        result.get('sample_rows')!=checkpoint.get('sample_rows')):
        raise ValueError('Final generation completion/4000shards/author truth/row contract failed')
    return 'GENERATION_CANDIDATE_COMPLETE'


def available_memory():
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(x,ctypes.c_uint64) for x in
                   ['total_physical','available_physical','total_page','available_page','total_virtual','available_virtual','extended']]
    record=Memory();record.length=ctypes.sizeof(record)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(record)):raise ctypes.WinError()
    return record.available_physical


def mscn_complete():
    paths=[ROOT/'output/full/mscn/table1_job_light_seed1/training_state.json',
           ROOT/'output/full/mscn/rebuilt_seed1/results/training_state.json']
    records=[read_shared(path) for path in paths]
    completed=all(r.get('completed_epochs')==r.get('target_epochs')==100 and
                  r.get('checkpoint',{}).get('completed_epochs')==100 and
                  r.get('checkpoint',{}).get('status')=='COMMITTED' for r in records)
    script="@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'mscn' } | Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress"
    process=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,errors='replace',timeout=30)
    if process.returncode:raise RuntimeError('Cannot establish MSCN process completion: '+process.stderr)
    live=json.loads(process.stdout) if process.stdout.strip() else []
    if isinstance(live,dict):live=[live]
    return completed,bool(live),{'training_receipts':{str(p.relative_to(ROOT)):digest(p) for p in paths},'live_mscn_processes':live}


def resources_ready(memory,disk,mscn_done,mscn_active):
    return memory>=4*GIB and disk>=6*GIB and mscn_done and not mscn_active


def frozen_sources():
    if digest(MODELS/'formal_plan.json')!=PLAN_SHA256 or digest(MODELS/'readiness_verification.json')!=READINESS_SHA256:
        raise ValueError('Reviewed formal plan/readiness bytes changed')
    if digest(MODELS/'sf2_outer_guard_verification.json')!=OUTER_SHA256:raise ValueError('Reviewed tiny outer seal changed')
    readiness=read_shared(MODELS/'readiness_verification.json');seal=read_shared(MODELS/'readiness_verification.seal.json')
    required={'code/full_ssb_model.py','code/full_ssb_guard.py','code/tests/test_full_ssb_model.py',
              'code/tests/test_full_ssb_guard.py','docs/FULL_SSB_MODEL_PROTOCOL.md'}
    if (seal.get('sha256')!=READINESS_SHA256 or set(readiness['code_files_sha256'])!=required or
        set(seal['required_code_files'])!=required):raise ValueError('Frozen source exact inventory changed')
    for path,sha in readiness['code_files_sha256'].items():
        if digest(ROOT/path)!=sha:raise ValueError('Frozen scientific source changed: '+path)
    return {'plan_sha256':PLAN_SHA256,'readiness_sha256':READINESS_SHA256,'outer_sha256':OUTER_SHA256,
            'supervisor_source_sha256':digest(__file__),
            'running_generator_retry_adapter_sha256':digest(ROOT/'code/full_ssb_run.py'),
            'running_generator_retry_helper_sha256':digest(ROOT/'code/full_flights_run.py')}


class Lock:
    def __enter__(self):
        import msvcrt
        OUTPUT.mkdir(parents=True,exist_ok=True);self.stream=(OUTPUT/'supervisor.lock').open('a+b')
        if self.stream.seek(0,2)==0:self.stream.write(b'0');self.stream.flush()
        self.stream.seek(0);msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1);return self
    def __exit__(self,*args):self.stream.close()


def save_state(status,**extra):
    state={'status':status,'checked_at_utc':utc(),'supervisor_pid':os.getpid(),**extra}
    atomic(OUTPUT/'state.json',state);return state


def command(action,formal=False,interval=60):
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    args=[str(ROOT/'.venv/Scripts/python.exe'),'-B',str(ROOT/'code/full_ssb_model.py'),action]
    if formal:args.append('--formal-memory-approved')
    stdout=OUTPUT/(stamp+'_'+action+'.stdout.log');stderr=OUTPUT/(stamp+'_'+action+'.stderr.log')
    started=time.perf_counter()
    with stdout.open('xb') as out,stderr.open('xb') as err:
        process=subprocess.Popen(args,cwd=str(ROOT),stdout=out,stderr=err,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        if formal:save_state('FORMAL_RUNNING',formal_pid=process.pid,stdout=str(stdout),stderr=str(stderr),command=args)
        while process.poll() is None:
            try:process.wait(timeout=interval)
            except subprocess.TimeoutExpired:pass
    result={'action':action,'returncode':process.returncode,'wall_seconds':time.perf_counter()-started,
            'stdout':str(stdout),'stderr':str(stderr),'command':args,'finished_at_utc':utc()}
    atomic(OUTPUT/(stamp+'_'+action+'.process.json'),result)
    if process.returncode:raise RuntimeError('Frozen '+action+' failed; retained logs: '+str(stderr))
    return result


def final_summary():
    result=read_shared(ROOT/'output/full/results/ssb_model_aqp_ci.json')
    directory=Path(result['directory']);seal=read_shared(directory/'verification_seal.json')
    if (seal['sha256']!=digest(directory/'verification.json') or result['status']!='PASS' or
        result.get('stage')!='SSB_SF500_SINGLE_1M_AQP_CI' or result.get('paper_population_exact') is not True or
        result['spn_count']!=5 or result['point_query_errors'] or result['ci_query_errors'] or len(result['queries'])!=13 or
        result['inputs']['population_rows']!=3000028242):raise ValueError('Formal model/evaluation completion contract failed')
    global_home=MODELS/'formal_runs'/result['plan_sha256'];lifecycle=read_shared(global_home/'lifecycle.json')
    global_receipt=read_shared(global_home/'receipt.json')
    if (lifecycle['status']!='PASS' or lifecycle['receipt_sha256']!=digest(global_home/'receipt.json') or
        seal['formal_outer_receipt_sha256']!=digest(global_home/'receipt.json') or global_receipt['result']!=result):
        raise ValueError('Formal durable publication receipt mismatch')
    for path,sha in result['outer_stage_receipts_sha256'].items():
        if digest(path)!=sha:raise ValueError('Formal stage receipt changed')
    return {'status':'FORMAL_COMPLETE_PENDING_ROOT_REVIEW','formal_result_sha256':digest(directory/'verification.json'),
            'formal_result_path':str(directory/'verification.json'),'population_rows':3000028242,
            'sample_rows':result['inputs']['sample_rows'],'point_errors':0,'ci_errors':0,'queries':13,
            'missing_groups':sum(q['missing_model_groups'] for q in result['queries']),
            'extra_groups':sum(q['extra_model_groups'] for q in result['queries']),
            'reference_ci_eligible_groups':sum(q['reference_ci_eligible_groups'] for q in result['queries']),
            'learning_seconds':result['historical_learning_seconds'],'formal_wall_seconds':result['wall_seconds'],
            'peak_working_set_bytes':result['process_peak_working_set_bytes'],
            'ssb_disk_bytes':sum(p.stat().st_size for folder in [ROOT/'data/ssb',ROOT/'output/full/ssb'] for p in folder.rglob('*') if p.is_file()),
            'all_old_scientific_seals_preserved':True,'formal_full_paper_complete':False}


def run(interval=60):
    if interval<60:raise ValueError('Checkpoint monitoring interval must be at least60 seconds')
    with Lock():
        binding=frozen_sources();state_path=OUTPUT/'state.json'
        if state_path.exists() and read_shared(state_path).get('status')=='FORMAL_COMPLETE_PENDING_ROOT_REVIEW':
            return final_summary()
        if state_path.exists() and read_shared(state_path).get('status') in ('FORMAL_RUNNING','FAIL'):
            raise ValueError('Previous formal launch/failure requires review; never restart a formal namespace automatically')
        while True:
            result=read_shared(ROOT/'output/full/results/ssb_paper.json')
            checkpoint=read_shared(ROOT/'output/full/ssb/paper/sf500/checkpoint.json')
            decision=generation_decision(result,checkpoint)
            progress={'rows':checkpoint['rows'],'sample_rows':checkpoint['sample_rows'],
                      'committed_shards':len(checkpoint['committed_shards']),'binding':binding,
                      'checkpoint_read':LAST_READS.get(str(ROOT/'output/full/ssb/paper/sf500/checkpoint.json'))}
            if decision=='WAIT_GENERATION':
                save_state(decision,**progress);time.sleep(interval);continue
            done,active,proof=mscn_complete();memory=available_memory();disk=shutil.disk_usage(str(ROOT)).free
            resources={'available_memory_bytes':memory,'free_disk_bytes':disk,'mscn_done':done,'mscn_active':active,'mscn_proof':proof}
            if not resources_ready(memory,disk,done,active):
                save_state('WAIT_RESOURCES',**progress,resources=resources);time.sleep(interval);continue
            frozen_sources();atomic(OUTPUT/'prelaunch_resources.json',{'checked_at_utc':utc(),**resources})
            command('formal-gate',interval=interval)  # Frozen exact truth + physical SHA/row-count pass.
            gate=read_shared(MODELS/'formal_generation_gate.json')
            if gate['status']!='PASS':raise ValueError('Frozen final physical generation gate did not pass')
            atomic(OUTPUT/'accepted_generation_gate.json',gate)
            # Physical validation can take time: establish resources again immediately before launch.
            done,active,proof=mscn_complete();memory=available_memory();disk=shutil.disk_usage(str(ROOT)).free
            if not resources_ready(memory,disk,done,active):
                save_state('WAIT_RESOURCES_AFTER_PHYSICAL_GATE',**progress);time.sleep(interval);continue
            atomic(OUTPUT/'launch_resources.json',{'checked_at_utc':utc(),'available_memory_bytes':memory,
                   'free_disk_bytes':disk,'mscn_done':done,'mscn_active':active,'mscn_proof':proof,
                   'accepted_generation_gate_sha256':digest(OUTPUT/'accepted_generation_gate.json')})
            command('formal-all',formal=True,interval=interval)
            summary=final_summary();atomic(OUTPUT/'verification.json',summary)
            atomic(OUTPUT/'verification_seal.json',{'sha256':digest(OUTPUT/'verification.json'),'binding':binding})
            save_state(summary['status'],verification_sha256=digest(OUTPUT/'verification.json'))
            print(json.dumps(summary),flush=True);return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--interval',type=int,default=60)
    args=parser.parse_args()
    try:run(args.interval)
    except BaseException as error:
        save_state('FAIL',error=repr(error),science_automatically_restarted=False)
        raise
