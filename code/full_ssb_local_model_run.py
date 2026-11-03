"""Separate local SSB control layer; shared owned-process primitives, no WinAPI copy."""
import sys
sys.dont_write_bytecode=True
import json
import math
import os
from pathlib import Path
import re
import full_ssb_local_model as model
import full_ssb_native_model_run as ops

source=model.source
base=model.base
ROOT=model.ROOT
require=model.require
read=model.read
atomic=model.atomic
digest=model.digest
artifact=model.artifact
value_hash=model.value_hash
JOB_PREFIX='Local\\DeepDB_SSB_NATIVE_LOCAL_'
SELF='code/full_ssb_local_model_run.py'
LOGS=('stdout.log','stderr.log','monitor.json','bootstrap.json','worker_start.json')


def build_plan(source_receipt_sha256,auxiliary_sources=None):
    """Read-only candidate, requiring a prior independent local physical audit."""
    inputs=source.verify_local_source(ROOT)
    require(inputs['receipt_sha256']==source_receipt_sha256,'exact reviewed local source receipt required')
    return dict(schema='ssb_local_sf500_model_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,scope=source.SCOPE,
        root_decision_sha256=source.DECISION_SHA,original_mismatch_sha256=source.NATIVE_REPORT_SHA,author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,source_receipt_sha256=source_receipt_sha256,
        model=dict(model.MODEL),dependencies=model.dependency_snapshot(auxiliary_sources),operational_policy=dict(ops.OPERATIONAL_POLICY))


def seal_plan(source_receipt_sha256,root_reviewed_candidate_sha256,auxiliary_sources=None):
    candidate=build_plan(source_receipt_sha256,auxiliary_sources)
    require(value_hash(candidate)==root_reviewed_candidate_sha256,'local candidate differs from explicit root-reviewed SHA')
    plan=dict(candidate,status='ROOT_REVIEWED_LOCAL_SSB_MODEL_PLAN',executable=True,root_reviewed_candidate_sha256=root_reviewed_candidate_sha256)
    path=ROOT/model.OUTPUT/'plans'/value_hash(plan)[:20]/'plan.json'
    if path.exists() or path.with_suffix('.seal.json').exists():require(read_plan(path,digest(path))==plan,'existing local plan differs; no repair')
    else:atomic(path,plan);atomic(path.with_suffix('.seal.json'),{'sha256':digest(path)})
    return dict(plan=artifact(path),plan_binding_sha256=value_hash(plan))


def read_plan(path,expected_sha,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve();require(digest(path)==expected_sha,'local plan file SHA changed');p=read(path)
    require(path==root/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json' and read(path.with_suffix('.seal.json'))=={'sha256':expected_sha},'local plan namespace/seal differs')
    expected=dict(schema='ssb_local_sf500_model_plan_v1',status='ROOT_REVIEWED_LOCAL_SSB_MODEL_PLAN',executable=True,scope=source.SCOPE,
        root_decision_sha256=source.DECISION_SHA,original_mismatch_sha256=source.NATIVE_REPORT_SHA,author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,model=model.MODEL,operational_policy=ops.OPERATIONAL_POLICY)
    require(all(type(p.get(k)) is type(v) and p[k]==v for k,v in expected.items()),'reviewed local scope/model/operational policy required')
    require(set(p)==set(expected)|{'source_receipt_sha256','dependencies','root_reviewed_candidate_sha256'}
        and re.fullmatch('[a-f0-9]{64}',p['source_receipt_sha256']) is not None,'exact local plan schema required')
    require(set(p['dependencies']['local_sources'])==set(source.LOCAL_FILES)
        and set(p['dependencies']['auxiliary_sources'])<={'code/full_ssb_local_replay.py'},'exact local adapter/explicit auxiliary sources required')
    candidate=dict(p);approved=candidate.pop('root_reviewed_candidate_sha256');candidate.update(status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False)
    require(value_hash(candidate)==approved,'root local candidate approval hash differs')
    return p


def supervisor_binding(report):
    deps=report['plan']['dependencies'];env=deps['environment']
    return dict(scope=source.SCOPE,original_mismatch_sha256=source.NATIVE_REPORT_SHA,author_different_groups=1713,
        plan_binding_sha256=report['plan_binding_sha256'],plan_file_sha256=report['plan_file_sha256'],source_receipt_sha256=report['source_receipt_sha256'],
        bridge_sha256=report['adapter_source_sha256'],launcher_sha256=deps['local_sources'][SELF],
        shared_operational_sha256=source.STRICT_PINS['code/full_ssb_native_model_run.py'],
        bootstrap_executable=env['python_base_executable'],venv_executable=env['python_executable'],policy=ops.OPERATIONAL_POLICY)


def taint_local_tail(directory,error):
    for kind in ('formal','publication'):
        life=Path(directory)/(kind+'_control')/'lifecycle.json'
        if life.exists():
            state=read(life);state.update(status='TAINTED',reason='local supervisor failed: '+repr(error));atomic(life,state)


def run_supervised(plan_path,expected_plan_sha256,memory_approved=False,root=ROOT):
    require(memory_approved,'separate explicit root memory release required');root=Path(root).resolve();require(root==ROOT,'actual local execution requires original root')
    path=Path(plan_path).resolve();plan=read_plan(path,expected_plan_sha256,root);p=value_hash(plan)
    directory=root/model.OUTPUT/'runs'/p[:20];home=directory/'supervisor_control'
    stub=dict(plan=plan,plan_binding_sha256=p,plan_file_sha256=expected_plan_sha256,source_receipt_sha256=plan['source_receipt_sha256'],
        adapter_source_sha256=plan['dependencies']['local_sources']['code/full_ssb_local_model.py'],directory=str(directory))
    binding=supervisor_binding(stub)
    def produce():
        inputs=source.verify_local_source(root);require(inputs['receipt_sha256']==plan['source_receipt_sha256'],'local source audit differs from reviewed plan')
        require(plan['dependencies']==model.dependency_snapshot(plan['dependencies']['auxiliary_sources']),'reviewed complete local dependencies changed')
        probe=ops.operational_resources(root);base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'])
        require(probe['available_memory_bytes']>=ops.OPERATIONAL_POLICY['minimum_launch_available_memory_bytes'],'at least5GiB available RAM required at local launch')
        import secrets
        token=secrets.token_hex(16);job=JOB_PREFIX+token
        require(artifact(ops.base_python_executable(),root)==binding['bootstrap_executable'],'reviewed direct base interpreter changed')
        command=[str(ops.base_python_executable()),str(root/SELF),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',expected_plan_sha256,'--start-token',token,'--job-name',job]
        result=ops.run_owned_child(command,home,binding,root=root,start_payload=dict(start=token,plan_binding_sha256=p),job_name=job,initial_resources=probe)
        result['artifacts'].extend(artifact(home/name,root) for name in LOGS[3:]);result['resources_at_launch']=probe
        verified=model.verify_local_model_publication(root)
        result.update(published_result_sha256=verified['published_result']['sha256'],verification_seal_sha256=verified['verification_seal']['sha256'])
        return result
    def validate(result):verify_supervisor_result(stub,binding,result,root);model.verify_local_model_publication(root)
    with base.controller_lock(root/model.OUTPUT/'supervisor.lock'):
        try:return base.formal_transaction(home,binding,produce,validate,kind='LOCAL_SUPERVISOR')
        except BaseException as error:taint_local_tail(directory,error);raise


def finite_number(x):return type(x) in (int,float) and math.isfinite(x)


def verify_supervisor_result(report,binding,result,root=ROOT):
    """Only existing evidence is read; never query processes, probe resources or launch."""
    root=Path(root);directory=Path(report['directory']);home=directory/'supervisor_control';m=read(home/'monitor.json');policy=ops.OPERATIONAL_POLICY
    expected=[artifact(home/name,root) for name in LOGS]
    require(result['artifacts']==expected and result['returncode']==m['returncode']==0 and m['status']=='PASS' and m['stop_reason'] is None
        and m['binding']==binding and m['policy']==policy and m['owned_process_only'] is True and m['job_object_kill_on_close'] is True
        and type(m['peak_owned_rss_bytes']) is int and 0<m['peak_owned_rss_bytes']==result['peak_owned_rss_bytes']<=policy['maximum_owned_rss_bytes'],'complete local owned monitor evidence required')
    require(result['published_result_sha256']==digest(root/model.RESULT) and result['verification_seal_sha256']==digest(directory/'verification_seal.json'),'local supervisor scientific publication link differs')
    launch=result['resources_at_launch'];base.check_resources(launch['free_disk_bytes'],launch['available_memory_bytes'],launch['existing_ssb_bytes'])
    require(launch['available_memory_bytes']>=policy['minimum_launch_available_memory_bytes'],'local launch RAM evidence insufficient')
    last=m['last_resource_probe']
    require(type(m['checks']) is int and m['checks']>0 and finite_number(m['seconds']) and 0<=m['seconds']<=policy['wall_timeout_seconds']
        and last['available_memory_bytes']>=policy['minimum_live_available_memory_bytes'] and last['free_disk_bytes']>=policy['minimum_free_disk_bytes']
        and 0<=last['existing_ssb_bytes']<=policy['maximum_ssb_bytes'] and finite_number(last['storage_scan_age_seconds'])
        and 0<=last['storage_scan_age_seconds']<=policy['maximum_storage_scan_age_seconds'],'local live resource evidence differs')
    command=m['command'];prefix=[str(root/binding['bootstrap_executable']['path']),str(root/SELF),'_bootstrap','--plan-path',
        str(root/model.OUTPUT/'plans'/binding['plan_binding_sha256'][:20]/'plan.json'),'--plan-file-sha256',binding['plan_file_sha256']]
    require(isinstance(command,list) and len(command)==11 and command[:7]==prefix and command[7]=='--start-token' and re.fullmatch('[a-f0-9]{32}',command[8]) is not None
        and command[9]=='--job-name' and command[10]==JOB_PREFIX+command[8] and digest(root/SELF)==binding['launcher_sha256'],'local direct-base command/source differs')
    bootstrap=read(home/'bootstrap.json');worker=read(home/'worker_start.json')
    require(bootstrap.get('schema')=='ssb_local_sf500_bootstrap_v1' and bootstrap['scope']==source.SCOPE and bootstrap['status']=='PASS' and bootstrap['returncode']==0
        and bootstrap['membership_verified_after_go'] is True and bootstrap['base_executable']==binding['bootstrap_executable'] and bootstrap['named_job']==command[10]
        and bootstrap['plan_binding_sha256']==binding['plan_binding_sha256'],'complete local bootstrap membership required')
    expected_worker=[str(root/binding['venv_executable']['path']),command[1],'_worker']+command[3:]+['--bootstrap-pid',str(bootstrap['pid'])]
    require(bootstrap['worker_command']==expected_worker and type(bootstrap['pid']) is int and bootstrap['pid']>0 and type(bootstrap['worker_launcher_pid']) is int
        and bootstrap['worker_launcher_pid']>0,'local inherited venv command differs')
    require(worker.get('schema')=='ssb_local_sf500_worker_v1' and worker['scope']==source.SCOPE and worker['membership_verified_after_go'] is True
        and worker['named_job']==command[10] and worker['plan_binding_sha256']==binding['plan_binding_sha256'] and worker['bootstrap_pid']==bootstrap['pid']
        and worker['parent_pid']==bootstrap['worker_launcher_pid'] and type(worker['pid']) is int and worker['pid']>0
        and worker['base_executable']==binding['bootstrap_executable'],'actual local nested worker identity differs')
    actual_venv=artifact(root/worker['venv_executable']['path'],root)
    require(actual_venv==worker['venv_executable']
        and (root/actual_venv['path']).resolve()==(root/binding['venv_executable']['path']).resolve()
        and actual_venv['sha256']==binding['venv_executable']['sha256'],'actual local venv path/bytes/hash differs')
    return expected


def verify_supervisor(report,root=ROOT):
    home=Path(report['directory'])/'supervisor_control';b=supervisor_binding(report);life=read(home/'lifecycle.json');receipt=read(home/'receipt.json')
    require(life['status']==receipt['status']=='PASS' and receipt['kind']=='LOCAL_SUPERVISOR' and life['receipt_sha256']==digest(home/'receipt.json')
        and life['binding']==receipt['binding']==b,'complete LOCAL_SUPERVISOR PASS required')
    return verify_supervisor_result(report,b,receipt['result'],root)+[artifact(home/name,root) for name in ('receipt.json','lifecycle.json')]


def start_handshake(args):
    require(os.environ.get('DEEPDB_SSB_NATIVE_MODEL_WORKER')=='1','fresh owned bootstrap environment required')
    line=sys.stdin.readline(4097);require(len(line)<=4096 and line.endswith('\n'),'bounded local supervisor GO required')
    ops.verify_owned_job_membership(args.job_name)
    plan=read_plan(args.plan_path,args.plan_file_sha256);payload=json.loads(line)
    require(payload==dict(start=args.start_token,plan_binding_sha256=value_hash(plan)) and args.job_name==JOB_PREFIX+args.start_token,'local token/plan/job GO differs')
    return plan,payload


def bootstrap_entry(args):
    plan,payload=start_handshake(args);home=ROOT/model.OUTPUT/'runs'/value_hash(plan)[:20]/'supervisor_control'
    command=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/SELF),'_worker','--plan-path',args.plan_path,'--plan-file-sha256',args.plan_file_sha256,
        '--start-token',args.start_token,'--job-name',args.job_name,'--bootstrap-pid',str(os.getpid())]
    launcher_pid,code=ops.launch_inherited_venv_worker(command,payload,args.job_name)
    path=home/'bootstrap.json';require(not path.exists(),'existing local bootstrap evidence cannot be replaced')
    atomic(path,dict(schema='ssb_local_sf500_bootstrap_v1',scope=source.SCOPE,status='PASS' if code==0 else 'FAILED',pid=os.getpid(),returncode=code,
        worker_launcher_pid=launcher_pid,worker_command=command,membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(plan),base_executable=artifact(ops.base_python_executable())))
    require(code==0,'original venv local worker failed');return dict(status='PASS_LOCAL_BOOTSTRAP')


def worker_entry(args):
    plan,payload=start_handshake(args);os.environ.update(DEEPDB_SSB_LOCAL_WORKER='1',DEEPDB_SSB_LOCAL_JOB=args.job_name)
    home=ROOT/model.OUTPUT/'runs'/value_hash(plan)[:20]/'supervisor_control';path=home/'worker_start.json';require(not path.exists(),'existing local worker evidence cannot be replaced')
    atomic(path,dict(schema='ssb_local_sf500_worker_v1',scope=source.SCOPE,pid=os.getpid(),parent_pid=os.getppid(),bootstrap_pid=args.bootstrap_pid,
        membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(plan),base_executable=artifact(ops.base_python_executable()),venv_executable=artifact(sys.executable)))
    result=model.execute_local_formal(plan,memory_approved=True);return dict(status=result['status'],published_result_sha256=digest(ROOT/model.RESULT))


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    audit=sub.add_parser('audit-source');audit.add_argument('--root-decision-sha256',required=True);audit.add_argument('--reviewed-local-codes-sha256',required=True)
    for name in ('candidate-plan','seal-plan'):
        p=sub.add_parser(name);p.add_argument('--source-receipt-sha256',required=True);p.add_argument('--frozen-auxiliary-sources-json')
        if name=='seal-plan':p.add_argument('--root-reviewed-candidate-sha256',required=True)
    p=sub.add_parser('supervise');p.add_argument('--plan-path',required=True);p.add_argument('--plan-file-sha256',required=True);p.add_argument('--root-memory-approved',action='store_true')
    sub.add_parser('verify-formal')
    for kind in ('_bootstrap','_worker'):
        p=sub.add_parser(kind,help=argparse.SUPPRESS)
        for name in ('plan-path','plan-file-sha256','start-token','job-name'):p.add_argument('--'+name,required=True)
        if kind=='_worker':p.add_argument('--bootstrap-pid',required=True,type=int)
    a=parser.parse_args(argv);aux=read(a.frozen_auxiliary_sources_json) if getattr(a,'frozen_auxiliary_sources_json',None) else None
    if a.command=='audit-source':result=source.audit_local_source(a.root_decision_sha256,a.reviewed_local_codes_sha256)
    elif a.command=='candidate-plan':result=build_plan(a.source_receipt_sha256,aux)
    elif a.command=='seal-plan':result=seal_plan(a.source_receipt_sha256,a.root_reviewed_candidate_sha256,aux)
    elif a.command=='supervise':result=run_supervised(a.plan_path,a.plan_file_sha256,a.root_memory_approved)
    elif a.command=='verify-formal':result=model.verify_local_formal()
    elif a.command=='_bootstrap':result=bootstrap_entry(a)
    else:result=worker_entry(a)
    print(json.dumps(result,sort_keys=True,allow_nan=False));return 0


if __name__=='__main__':raise SystemExit(main())
