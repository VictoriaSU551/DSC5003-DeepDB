"""Owned reverse-only continuation; no full raw-history F inside the child."""
import sys
sys.dont_write_bytecode=True
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from types import SimpleNamespace
import full_ssb_local_continuation as model

ROOT=model.ROOT
ops=model.prior_run.ops
base=model.base
require=model.require
read=model.read
atomic=model.atomic
digest=model.digest
artifact=model.artifact
value_hash=model.value_hash
SELF='code/full_ssb_local_continuation_run.py'
JOB_PREFIX='Local\\DeepDB_SSB_NATIVE_CONTINUATION_'
LOGS=('stdout.log','stderr.log','monitor.json','bootstrap.json','worker_start.json')
POLICY=dict(ops.OPERATIONAL_POLICY,minimum_worker_available_memory_bytes=4*2**30)
PLAN_FIELDS=set('schema status executable scope execution_protocol codes parent old_plan old_plan_seal forward accepted_forward_artifacts retained_failure_provenance worker_roles prepared_directory worker_environment environment_contract hash_seed random_seed thread_limits additional_reserve_bytes author_different_groups author_reproduction_complete full_paper_reproduction_complete historical_reverse_accepted worker_artifacts operational_policy root_reviewed_candidate_sha256'.split())


def candidate_part(plan):
    p=dict(plan);p.pop('root_reviewed_candidate_sha256');p.update(status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False);return p


def build_candidate(old_plan_path,old_plan_sha256,reviewed_codes_sha256):
    require(value_hash(model.code_snapshot())==reviewed_codes_sha256,'reviewed continuation two-source code set required')
    p=model.candidate_from_parent(old_plan_path,old_plan_sha256,model.collect_parent());p['operational_policy']=POLICY
    return p


def seal_plan(old_plan_path,old_plan_sha256,reviewed_codes_sha256,root_reviewed_candidate_sha256):
    p=build_candidate(old_plan_path,old_plan_sha256,reviewed_codes_sha256)
    require(value_hash(p)==root_reviewed_candidate_sha256,'explicit ROOT-reviewed current candidate required')
    p=dict(p,status='ROOT_REVIEWED_CONTINUATION_PLAN',executable=True,root_reviewed_candidate_sha256=root_reviewed_candidate_sha256)
    path=ROOT/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json'
    require(not path.exists() and not path.with_suffix('.seal.json').exists(),'continuation plan cannot overwrite')
    atomic(path,p);atomic(path.with_suffix('.seal.json'),dict(sha256=digest(path)))
    return dict(plan=artifact(path),plan_binding_sha256=value_hash(p))


def read_plan(path,expected_sha,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve();require(digest(path)==expected_sha,'continuation plan physical SHA differs')
    p=read(path);require(path==root/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json' and read(path.with_suffix('.seal.json'))==dict(sha256=expected_sha),'continuation plan path/seal differs')
    c=candidate_part(p)
    require(set(p)==PLAN_FIELDS and p['schema']=='local_ssb_canonical_continuation_plan_v1'
        and p['additional_reserve_bytes']==model.old.RESERVE_BYTES and p['environment_contract']==model.ENVIRONMENT_CONTRACT
        and set(p['worker_roles'])=={'model','moments','truth'} and all(type(p[k]) is list and p[k] and len(p[k])==len({d['path'] for d in p[k]}) for k in ('worker_artifacts','accepted_forward_artifacts','retained_failure_provenance')),
        'exact continuation schema/consumed-role/required-set contract required')
    require(value_hash(c)==p['root_reviewed_candidate_sha256'] and p['status']=='ROOT_REVIEWED_CONTINUATION_PLAN' and p['executable'] is True
        and p['scope']==model.SCOPE and p['execution_protocol']==model.PROTOCOL and p['operational_policy']==POLICY
        and p['codes']==model.code_snapshot() and p['hash_seed']==173 and p['random_seed']==74031 and p['thread_limits']=={n:'1' for n in model.THREADS}
        and p['author_different_groups']==1713 and all(p[n] is False for n in ('author_reproduction_complete','full_paper_reproduction_complete','historical_reverse_accepted')),
        'exact reviewed continuation policy/source/scope required')
    return p


def root_binding(plan):return dict(scope=model.SCOPE,execution_protocol=model.PROTOCOL,plan_sha256=value_hash(plan),parent=plan['parent'],forward=plan['forward'])


def child_binding(plan):
    path=ROOT/model.OUTPUT/'plans'/value_hash(plan)[:20]/'plan.json';env=plan['worker_environment']
    return dict(scope=model.SCOPE,phase='REVERSE',plan_binding_sha256=value_hash(plan),plan_file_sha256=digest(path),
        bridge_sha256=plan['codes'][model.FILES[0]],launcher_sha256=plan['codes'][SELF],
        bootstrap_executable=env['python_base_executable'],venv_executable=env['python_executable'],policy=ops.OPERATIONAL_POLICY)


def verifier_capsule(plan):
    # Only verifier code is extracted. No old collect/execute/bootstrap function
    # can be reached through this namespace or supplied a fabricated old proof.
    raw=model.prior_run.configured_source('REVERSE')[1]
    nodes={n.name:n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
    text='\n\n'.join(ast.get_source_segment(raw,nodes[n]) for n in ('verify_supervisor_result','verify_supervisor'))
    text=text.replace('CANONICAL_REVERSE_CHILD','CONTINUATION_CHILD').replace('ssb_canonical_reverse_bootstrap_v1','ssb_continuation_bootstrap_v1').replace('ssb_canonical_reverse_worker_v1','ssb_continuation_worker_v1')
    proxy=SimpleNamespace(RESULT=(model.run_directory(plan)/'reverse/verification.json').relative_to(ROOT).as_posix(),OUTPUT=model.OUTPUT,RESERVE_BYTES=model.old.RESERVE_BYTES)
    namespace=dict(vars(model.prior_run),ROOT=ROOT,SELF=SELF,JOB_PREFIX=JOB_PREFIX,source=SimpleNamespace(SCOPE=model.SCOPE),model=proxy,supervisor_binding=lambda r:child_binding(plan))
    exec(compile(text,'<frozen-continuation-verifiers>','exec'),namespace);return namespace


def verify_child(plan):
    run=model.run_directory(plan);records=verifier_capsule(plan)['verify_supervisor'](dict(directory=str(run)))
    home=run/'reverse_control';monitor=read(home/'monitor.json');worker=read(home/'worker_start.json');report=read(run/'reverse/verification.json')
    require(worker.get('hash_seed')==173 and report['environment']['process_id']==worker['pid']
        and monitor['cleanup_errors']==[] and monitor['storage_probe_stopped'] is True and monitor['primary_exception'] is None
        and type(monitor['storage_walks']) is list and type(monitor['storage_heartbeat_age_seconds']) in (int,float)
        and 0<=monitor['storage_heartbeat_age_seconds']<=90,'actual reverse worker/storage/cleanup evidence differs')
    launch=read(home/'receipt.json')['result']['resources_at_launch'];validate_root_resources(launch,model.old.RESERVE_BYTES)
    last=monitor['last_resource_probe']
    require(all(type(last[k]) is int and last[k]>=0 for k in ('available_memory_bytes','free_disk_bytes','existing_ssb_bytes')),'integer physical live resource bytes required')
    for walk in monitor['storage_walks']:
        require(model.prior_run.finite_number(walk['seconds']) and walk['seconds']>=0 and type(walk['completed']) is bool
            and (walk['bytes'] is None or type(walk['bytes']) is int and walk['bytes']>=0)
            and walk['error'] is None and (not walk['completed'] or walk['bytes'] is not None),'valid observed storage walk latency/bytes required')
    require(monitor['seconds']<90 or any(w['completed'] for w in monitor['storage_walks']),'long-running monitor requires a completed fresh storage walk')
    return records


def validate_root_resources(probe,reserve=0):
    require(all(type(probe[k]) is int and probe[k]>=0 for k in ('available_memory_bytes','free_disk_bytes','existing_ssb_bytes')),'integer physical ROOT resource bytes required')
    base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'],additional_bytes=reserve)
    return probe


def validate_worker_resources(probe):
    require(all(type(probe[k]) is int and probe[k]>=0 for k in ('available_memory_bytes','free_disk_bytes')),'integer physical worker resource bytes required')
    require(probe['available_memory_bytes']>=POLICY['minimum_worker_available_memory_bytes'] and probe['free_disk_bytes']>=POLICY['minimum_free_disk_bytes'],'worker admission RAM/disk insufficient')
    return probe


def complete_resources():
    started=time.monotonic();probe=ops.operational_resources()
    # A complete walk may be slow. RAM/free-disk admission must use the fast
    # reading after that walk, not the sample taken before it began.
    probe.update(ops.fast_resources());probe.update(storage_walk_seconds=time.monotonic()-started,storage_scan_age_seconds=0)
    return probe


def failure_reason(error,cleanup):return dict(primary_exception=repr(error),cleanup_errors=list(cleanup))


def stop_owned(process,job):
    errors=[]
    try:job.terminate()
    except BaseException as error:errors.append('terminate: '+repr(error))
    try:process.wait(timeout=10)
    except BaseException as error:
        errors.append('wait: '+repr(error))
        try:process.kill()
        except BaseException as tail:errors.append('kill bootstrap: '+repr(tail))
        try:process.wait(timeout=2)
        except BaseException as tail:errors.append('final wait: '+repr(tail))
    return errors


class StorageProbe(ops.LiveResourceProbe):
    """Original90s fail-closed age, plus observed walk duration/progress."""
    def __init__(self,root,initial):
        self.walks=[];self.heartbeat=time.monotonic()
        super().__init__(root,initial,storage_probe=self.walk)
    def stopped(self):self.heartbeat=time.monotonic();return self.stop.is_set()
    def walk(self):
        start=time.monotonic();result=None;error=None
        try:result=ops.storage_bytes(self.root,self.stopped);return result
        except BaseException as e:error=repr(e);raise
        finally:self.walks.append(dict(seconds=time.monotonic()-start,bytes=result,error=error,completed=result is not None))


@contextmanager
def fresh_environment():
    values=dict(PYTHONHASHSEED='173',DEEPDB_SSB_NATIVE_MODEL_WORKER='1',PYTHONDONTWRITEBYTECODE='1',**{n:'1' for n in model.THREADS})
    saved={n:os.environ.get(n) for n in values};os.environ.update(values)
    try:yield
    finally:
        for n,v in saved.items():
            if v is None:os.environ.pop(n,None)
            else:os.environ[n]=v


def run_owned(command,home,binding,token,job_name,initial):
    """Same kernel primitives; bounded cleanup preserves the first exception."""
    require(Path(command[0]).resolve()==ops.base_python_executable(),'direct project base bootstrap required')
    require(not any((home/n).exists() for n in LOGS),'unused child log namespace required')
    started=time.monotonic();peak=checks=0;last=None;process=job=probe=None;primary=None;cleanup=[]
    try:
        probe=StorageProbe(ROOT,initial);probe.__enter__();job=ops.OwnedWindowsJob(job_name)
        with (home/'stdout.log').open('wb') as out,(home/'stderr.log').open('wb') as err:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,cwd=str(ROOT),env=dict(os.environ),creationflags=subprocess.CREATE_NO_WINDOW)
            job.assign(process)
            process.stdin.write((json.dumps(dict(start=token,plan_binding_sha256=binding['plan_binding_sha256']))+'\n').encode());process.stdin.close()
            while True:
                peak=max(peak,job.working_set_bytes());last=probe.snapshot();checks+=1
                require(peak<=POLICY['maximum_owned_rss_bytes'],'resource owned RSS limit')
                require(last['available_memory_bytes']>=POLICY['minimum_live_available_memory_bytes'],'resource available RAM limit')
                require(last['free_disk_bytes']>=POLICY['minimum_free_disk_bytes'],'resource free disk limit')
                require(last['existing_ssb_bytes']<=POLICY['maximum_ssb_bytes'],'resource combined SSB disk budget')
                require(time.monotonic()-started<=POLICY['wall_timeout_seconds'],'timeout wall-clock limit')
                if process.poll() is not None:
                    require(process.returncode==0,'worker process nonzero exit')
                    require(not ops.live_owned_descendants(job,process.pid),'worker left live owned descendants');break
                time.sleep(POLICY['monitor_interval_seconds'])
    except BaseException as error:
        primary=error
        if process is not None and job is not None:cleanup.extend(stop_owned(process,job))
    finally:
        if job is not None:
            try:job.close()
            except BaseException as error:cleanup.append('close owned job: '+repr(error))
        if process is not None and process.poll() is None:
            try:process.wait(timeout=2)
            except BaseException as error:cleanup.append('post-close wait: '+repr(error))
        if probe is not None:
            try:probe.close()
            except BaseException as error:cleanup.append('storage stop: '+repr(error))
            if probe.thread.is_alive():cleanup.append('storage probe did not stop within2s')
        if primary is None and cleanup:primary=ValueError('owned cleanup incomplete')
        monitor=dict(status='PASS' if primary is None else 'STOPPED',binding=binding,policy=ops.OPERATIONAL_POLICY,command=command,
            returncode=None if process is None else process.returncode,stop_reason=None if primary is None else repr(primary),primary_exception=None if primary is None else repr(primary),
            cleanup_errors=cleanup,peak_owned_rss_bytes=peak,rss_scope='sum of live assigned-tree working sets, sampled at monitor interval',checks=checks,
            last_resource_probe=last,seconds=time.monotonic()-started,owned_process_only=True,job_object_kill_on_close=True,
            storage_walks=[] if probe is None else probe.walks,storage_probe_stopped=probe is not None and not probe.thread.is_alive(),
            storage_heartbeat_age_seconds=0 if probe is None else time.monotonic()-probe.heartbeat)
        try:atomic(home/'monitor.json',monitor)
        except BaseException:
            if primary is not None:raise primary
            raise
    if primary is not None:raise primary
    return dict(returncode=process.returncode,peak_owned_rss_bytes=peak,artifacts=[artifact(home/n) for n in LOGS])


def handshake(args):
    line=sys.stdin.readline(4097);require(len(line)<=4096 and line.endswith('\n'),'bounded GO required')
    require(os.environ.get('PYTHONHASHSEED')=='173' and all(os.environ.get(n)=='1' for n in model.THREADS),'fresh173 one-thread process required')
    ops.verify_owned_job_membership(args.job_name)
    p=read_plan(args.plan_path,args.plan_file_sha256);payload=json.loads(line)
    require(payload==dict(start=args.start_token,plan_binding_sha256=value_hash(p)) and args.job_name==JOB_PREFIX+args.start_token,'token/job/plan GO differs')
    return p,payload


def bootstrap_entry(args):
    plan,payload=handshake(args);home=model.run_directory(plan)/'reverse_control'
    command=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/SELF),'_worker','--plan-path',args.plan_path,'--plan-file-sha256',args.plan_file_sha256,
        '--start-token',args.start_token,'--job-name',args.job_name,'--bootstrap-pid',str(os.getpid())]
    launcher,code=ops.launch_inherited_venv_worker(command,payload,args.job_name)
    require(not (home/'bootstrap.json').exists(),'bootstrap receipt cannot overwrite')
    atomic(home/'bootstrap.json',dict(schema='ssb_continuation_bootstrap_v1',scope=model.SCOPE,status='PASS' if code==0 else 'FAILED',pid=os.getpid(),returncode=code,
        worker_launcher_pid=launcher,worker_command=command,membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(plan),base_executable=artifact(ops.base_python_executable())))
    require(code==0,'original venv continuation worker failed');return dict(status='PASS_CONTINUATION_BOOTSTRAP')


def worker_entry(args):
    p,_=handshake(args);os.environ.update(DEEPDB_SSB_CONTINUATION_WORKER='1',DEEPDB_SSB_CONTINUATION_JOB=args.job_name)
    home=model.run_directory(p)/'reverse_control';require(not (home/'worker_start.json').exists(),'worker evidence cannot overwrite')
    atomic(home/'worker_start.json',dict(schema='ssb_continuation_worker_v1',scope=model.SCOPE,hash_seed=173,pid=os.getpid(),parent_pid=os.getppid(),bootstrap_pid=args.bootstrap_pid,
        membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(p),base_executable=artifact(ops.base_python_executable()),venv_executable=artifact(sys.executable)))
    r=model.execute_reverse(p);return dict(status=r['status'])


def _run_child(plan):
    home=model.run_directory(plan)/'reverse_control';binding=child_binding(plan)
    def produce():
        initial=complete_resources();validate_root_resources(initial,model.old.RESERVE_BYTES)
        require(initial['available_memory_bytes']>=POLICY['minimum_launch_available_memory_bytes'],'at least5GiB launch admission required')
        token=secrets.token_hex(16);job=JOB_PREFIX+token;path=ROOT/model.OUTPUT/'plans'/value_hash(plan)[:20]/'plan.json'
        require(artifact(ops.base_python_executable())==binding['bootstrap_executable'],'bound direct base interpreter differs')
        command=[str(ops.base_python_executable()),str(ROOT/SELF),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',digest(path),'--start-token',token,'--job-name',job]
        with fresh_environment():r=run_owned(command,home,binding,token,job,initial)
        r.update(resources_at_launch=initial,published_result_sha256=digest(model.run_directory(plan)/'reverse/verification.json'),verification_seal_sha256=digest(model.run_directory(plan)/'reverse/seal.json'))
        return r
    def validate(r):verifier_capsule(plan)['verify_supervisor_result'](dict(directory=str(model.run_directory(plan))),binding,r)
    return base.formal_transaction(home,binding,produce,validate,kind='CONTINUATION_CHILD')


def run_supervised(path,sha,memory_approved=False):
    require(memory_approved,'explicit ROOT resource release required')
    return _run_supervised(Path(path).resolve(),sha)


def _run_supervised(path,sha):
    plan=read_plan(path,sha);run=model.run_directory(plan);accepted=None
    def fresh():
        p=model.collect_parent();current=model.candidate_from_parent(ROOT/plan['old_plan']['path'],plan['old_plan']['sha256'],p);current['operational_policy']=POLICY
        require(current==candidate_part(plan),'fresh ROOT complete parent/forward/consumed closure differs');return p
    def produce():
        nonlocal accepted
        fresh();_run_child(plan);accepted=fresh()
        probe=complete_resources();validate_root_resources(probe)
        return model.report_body(plan,path,accepted,probe)
    def validate(r):require(accepted is not None and r==model.report_body(plan,path,accepted,r['root_final_resources']),'fresh post-F required for report acceptance')
    with base.controller_lock(ROOT/model.OUTPUT/'controller.lock'):
        require(not run.exists(),'continuation namespace already used; verify separately, never repair/reexecute')
        try:
            r=base.formal_transaction(run/'root_control',root_binding(plan),produce,validate,kind='CONTINUATION_ROOT')
            model.publish(r,accepted);return dict(status=r['status'],published_result=artifact(ROOT/model.RESULT))
        except BaseException as error:
            p=run/'root_control/lifecycle.json'
            if p.exists():body=read(p);body.update(status='TAINTED',reason=repr(error));atomic(p,body)
            raise


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('candidate-plan','seal-plan'):
        p=sub.add_parser(name)
        for arg in ('old-plan-path','old-plan-sha256','reviewed-codes-sha256'):p.add_argument('--'+arg,required=True)
        if name=='seal-plan':p.add_argument('--root-reviewed-candidate-sha256',required=True)
    p=sub.add_parser('supervise');p.add_argument('--plan-path',required=True);p.add_argument('--plan-file-sha256',required=True);p.add_argument('--root-memory-approved',action='store_true')
    sub.add_parser('verify')
    for name in ('_bootstrap','_worker'):
        p=sub.add_parser(name,help=argparse.SUPPRESS)
        for arg in ('plan-path','plan-file-sha256','start-token','job-name'):p.add_argument('--'+arg,required=True)
        if name=='_worker':p.add_argument('--bootstrap-pid',type=int,required=True)
    a=parser.parse_args(argv)
    if a.command=='candidate-plan':r=build_candidate(a.old_plan_path,a.old_plan_sha256,a.reviewed_codes_sha256)
    elif a.command=='seal-plan':r=seal_plan(a.old_plan_path,a.old_plan_sha256,a.reviewed_codes_sha256,a.root_reviewed_candidate_sha256)
    elif a.command=='supervise':r=run_supervised(a.plan_path,a.plan_file_sha256,a.root_memory_approved)
    elif a.command=='verify':r=model.verify_canonical()
    elif a.command=='_bootstrap':r=bootstrap_entry(a)
    else:r=worker_entry(a)
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0


if __name__=='__main__':raise SystemExit(main())
