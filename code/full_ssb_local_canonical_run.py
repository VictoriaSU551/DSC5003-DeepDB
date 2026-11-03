"""One ROOT transaction, two owned canonical evaluation-only children."""
import sys
sys.dont_write_bytecode=True
import ast
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
import full_ssb_local_canonical as model
import full_ssb_local_model_run as frozen

ROOT=model.ROOT
base=model.base
ops=frozen.ops
require=model.require
digest=model.digest
read=model.read
atomic=model.atomic
artifact=model.artifact
value_hash=model.value_hash
SELF='code/full_ssb_local_canonical_run.py'
LOGS=frozen.LOGS
finite_number=frozen.finite_number
source=SimpleNamespace(**dict(vars(model.source),SCOPE=model.SCOPE))
FUNCTIONS=('verify_supervisor_result','verify_supervisor','start_handshake','bootstrap_entry')


def configured_source(phase):
    require(phase in model.PHASES,'known canonical child phase required')
    path=Path(frozen.__file__);require(digest(path)==model.PINS['code/full_ssb_local_model_run.py'],'frozen canonical operational capsule changed')
    raw=path.read_text(encoding='utf-8');nodes={n.name:n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS}
    require(set(nodes)==set(FUNCTIONS),'complete operational capsule required')
    before='\n\n'.join(ast.get_source_segment(raw,nodes[n]) for n in FUNCTIONS)+'\n'
    mappings={'supervisor_control':phase.lower()+'_control','LOCAL_SUPERVISOR':'CANONICAL_'+phase+'_CHILD',
        'ssb_local_sf500_bootstrap_v1':'ssb_canonical_'+phase.lower()+'_bootstrap_v1',
        'ssb_local_sf500_worker_v1':'ssb_canonical_'+phase.lower()+'_worker_v1',
        "directory/'verification_seal.json'":"directory/'"+phase.lower()+"'/'seal.json'",
        "base.check_resources(launch['free_disk_bytes'],launch['available_memory_bytes'],launch['existing_ssb_bytes'])":
        "base.check_resources(launch['free_disk_bytes'],launch['available_memory_bytes'],launch['existing_ssb_bytes'],additional_bytes=model.RESERVE_BYTES)"}
    after=before
    for a,b in mappings.items():require(a in after,'operational phase mapping absent');after=after.replace(a,b)
    return before,after,mappings


def capsule_binding():
    records={}
    for phase in model.PHASES:
        a,b,m=configured_source(phase);records[phase]=dict(original_sha256=hashlib.sha256(a.encode()).hexdigest(),configured_sha256=hashlib.sha256(b.encode()).hexdigest(),mappings=m)
    return dict(frozen_source_sha256=model.PINS['code/full_ssb_local_model_run.py'],functions=list(FUNCTIONS),phases=records)


def capsule(phase,plan):
    key=value_hash(plan);relative=model.OUTPUT+'/runs/'+key[:20]+'/'+phase.lower()+'/verification.json'
    proxy=SimpleNamespace(**dict(vars(model),RESULT=relative))
    n=dict(globals(),model=proxy,JOB_PREFIX='Local\\DeepDB_SSB_NATIVE_CANONICAL_'+phase+'_')
    exec(compile(configured_source(phase)[1],'<sealed-canonical-operational-capsule>','exec'),n);return n


@contextmanager
def phase_environment(phase):
    require(phase in model.PHASES,'known canonical process phase required')
    values={'PYTHONHASHSEED':str(model.HASH_SEEDS[phase]),'DEEPDB_SSB_CANONICAL_PHASE':phase}
    saved={k:os.environ.get(k) for k in values};os.environ.update(values)
    try:yield
    finally:
        for k,v in saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def child_report(plan,phase):
    key=value_hash(plan);path=ROOT/model.OUTPUT/'plans'/key[:20]/'plan.json'
    return dict(plan=plan,phase=phase,directory=str(model.run_directory(plan)),plan_binding_sha256=key,
        plan_file_sha256=digest(path),source_receipt_sha256=model.SOURCE_SHA,adapter_source_sha256=plan['dependencies']['canonical_sources']['code/full_ssb_local_canonical.py'])


def supervisor_binding(report):
    env=report['plan']['dependencies']['environment']
    return dict(scope=model.SCOPE,phase=report['phase'],original_mismatch_sha256=model.source.NATIVE_REPORT_SHA,author_different_groups=1713,
        plan_binding_sha256=report['plan_binding_sha256'],plan_file_sha256=report['plan_file_sha256'],source_receipt_sha256=model.SOURCE_SHA,
        bridge_sha256=report['adapter_source_sha256'],launcher_sha256=report['plan']['dependencies']['canonical_sources'][SELF],
        shared_operational_sha256=model.source.STRICT_PINS['code/full_ssb_native_model_run.py'],bootstrap_executable=env['python_base_executable'],venv_executable=env['python_executable'],policy=ops.OPERATIONAL_POLICY)


def verify_child(plan,phase,root=ROOT):
    require(Path(root).resolve()==ROOT,'actual canonical child acceptance requires original root')
    r=child_report(plan,phase);records=capsule(phase,plan)['verify_supervisor'](r,root)
    home=model.run_directory(plan)/ (phase.lower()+'_control')
    for name in ('bootstrap.json','worker_start.json'):
        item=read(home/name)
        require(item['phase']==phase and item['hash_seed']==model.HASH_SEEDS[phase],'actual canonical bootstrap/worker phase/hash differs')
    worker=read(home/'worker_start.json');science=read(model.run_directory(plan)/phase.lower()/'verification.json')
    producer_pid=science.get('environment',{}).get('process_id')
    require(type(producer_pid) is int and producer_pid==worker['pid'],'canonical scientific report did not originate in recorded owned worker')
    return records


def start_handshake(args):
    phase=os.environ.get('DEEPDB_SSB_CANONICAL_PHASE');plan=read_plan(args.plan_path,args.plan_file_sha256)
    require(phase in model.PHASES and os.environ.get('PYTHONHASHSEED')==str(model.HASH_SEEDS[phase]),'fresh canonical phase hash required before GO')
    return capsule(phase,plan)['start_handshake'](args)


def bootstrap_entry(args):
    phase=os.environ.get('DEEPDB_SSB_CANONICAL_PHASE');plan=read_plan(args.plan_path,args.plan_file_sha256)
    require(phase in model.PHASES and os.environ.get('PYTHONHASHSEED')==str(model.HASH_SEEDS[phase]),'fresh canonical bootstrap phase/hash required')
    n=capsule(phase,plan);n['start_handshake']=start_handshake;result=n['bootstrap_entry'](args)
    path=model.run_directory(plan)/(phase.lower()+'_control')/'bootstrap.json';body=read(path)
    body.update(phase=phase,hash_seed=model.HASH_SEEDS[phase]);atomic(path,body);return result


def worker_entry(args):
    plan,_=start_handshake(args);phase=os.environ['DEEPDB_SSB_CANONICAL_PHASE']
    os.environ.update(DEEPDB_SSB_CANONICAL_WORKER='1',DEEPDB_SSB_CANONICAL_JOB=args.job_name)
    home=model.run_directory(plan)/(phase.lower()+'_control');path=home/'worker_start.json'
    require(not path.exists(),'canonical worker namespace already used')
    atomic(path,dict(schema='ssb_canonical_'+phase.lower()+'_worker_v1',scope=model.SCOPE,phase=phase,hash_seed=model.HASH_SEEDS[phase],
        pid=os.getpid(),parent_pid=os.getppid(),bootstrap_pid=args.bootstrap_pid,membership_verified_after_go=True,named_job=args.job_name,
        plan_binding_sha256=value_hash(plan),base_executable=artifact(ops.base_python_executable()),venv_executable=artifact(sys.executable)))
    r=model.execute_worker(plan,phase);return dict(status=r['status'])


def candidate_body(code_sha,parent,dependencies):
    return dict(schema='local_ssb_canonical_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,scope=model.SCOPE,
        reviewed_codes_sha256=code_sha,parent=parent,dependencies=dependencies,hash_seeds=dict(model.HASH_SEEDS),random_seed=model.RANDOM_SEED,
        phase_evaluator_calls=26,phase_model_loads=dict(FORWARD=1,REVERSE=13),relative_tolerance=model.RTOL,absolute_tolerance=model.ATOL,
        additional_reserve_bytes=model.RESERVE_BYTES,operational_policy=dict(ops.OPERATIONAL_POLICY),author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False)


def build_candidate(reviewed_codes_sha256):
    require(reviewed_codes_sha256==value_hash(model.code_snapshot()),'reviewed canonical source set required')
    parent=model.collect_parent();return candidate_body(reviewed_codes_sha256,model.parent_snapshot(parent),model.dependency_snapshot())


def seal_plan(reviewed_codes_sha256,root_reviewed_candidate_sha256):
    c=build_candidate(reviewed_codes_sha256);require(value_hash(c)==root_reviewed_candidate_sha256,'root-reviewed canonical candidate changed')
    p=dict(c,status='ROOT_REVIEWED_LOCAL_CANONICAL_PLAN',executable=True,root_reviewed_candidate_sha256=root_reviewed_candidate_sha256)
    path=ROOT/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json'
    require(not path.exists() and not path.with_suffix('.seal.json').exists(),'existing canonical plan cannot be replaced')
    atomic(path,p);atomic(path.with_suffix('.seal.json'),{'sha256':digest(path)});return dict(plan=artifact(path),plan_binding_sha256=value_hash(p))


def read_plan(path,expected_sha,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve();require(digest(path)==expected_sha,'canonical plan bytes changed');p=read(path)
    require(path==root/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json' and read(path.with_suffix('.seal.json'))=={'sha256':expected_sha},'canonical plan namespace/seal differs')
    c=dict(p);approved=c.pop('root_reviewed_candidate_sha256');c.update(status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False)
    require(c==candidate_body(p['reviewed_codes_sha256'],p['parent'],p['dependencies']) and approved==value_hash(c)
        and p['status']=='ROOT_REVIEWED_LOCAL_CANONICAL_PLAN' and p['executable'] is True,'exact canonical plan policy/approval required')
    require(isinstance(p['dependencies'].get('canonical_sources'),dict)
        and p['reviewed_codes_sha256']==value_hash(p['dependencies']['canonical_sources']),'reviewed canonical code-set SHA differs from exact source map')
    return p


def run_supervised(plan_path,expected_plan_sha256,memory_approved=False,root=ROOT):
    require(memory_approved,'separate root canonical memory release required')
    require(Path(root).resolve()==ROOT,'actual canonical run requires original root')
    return _run_supervised(Path(plan_path).resolve(),expected_plan_sha256)


def _run_child(plan,phase):
    import secrets
    r=child_report(plan,phase);binding=supervisor_binding(r);home=model.run_directory(plan)/(phase.lower()+'_control')
    def produce():
        probe=ops.operational_resources();base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'],additional_bytes=model.RESERVE_BYTES)
        require(probe['available_memory_bytes']>=ops.OPERATIONAL_POLICY['minimum_launch_available_memory_bytes'],'at least5GiB canonical admission required')
        token=secrets.token_hex(16);job='Local\\DeepDB_SSB_NATIVE_CANONICAL_'+phase+'_'+token
        path=ROOT/model.OUTPUT/'plans'/value_hash(plan)[:20]/'plan.json'
        require(artifact(ops.base_python_executable())==binding['bootstrap_executable'],'canonical direct base executable differs')
        command=[str(ops.base_python_executable()),str(ROOT/SELF),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',digest(path),'--start-token',token,'--job-name',job]
        with phase_environment(phase):result=ops.run_owned_child(command,home,binding,start_payload=dict(start=token,plan_binding_sha256=value_hash(plan)),job_name=job,initial_resources=probe)
        result['artifacts'].extend(artifact(home/name) for name in LOGS[3:]);result['resources_at_launch']=probe
        result.update(published_result_sha256=digest(model.run_directory(plan)/phase.lower()/'verification.json'),verification_seal_sha256=digest(model.run_directory(plan)/phase.lower()/'seal.json'))
        return result
    def validate(result):capsule(phase,plan)['verify_supervisor_result'](r,binding,result)
    return base.formal_transaction(home,binding,produce,validate,kind='CANONICAL_'+phase+'_CHILD')


def _run_supervised(path,expected_sha):
    p=read_plan(path,expected_sha);run=model.run_directory(p);home=run/'root_control';accepted=None
    def produce():
        nonlocal accepted
        before=model.collect_parent();require(model.parent_snapshot(before)==p['parent'] and model.dependency_snapshot()==p['dependencies'],'canonical ROOTpre fresh parent/source differs')
        for phase in model.PHASES:_run_child(p,phase)
        accepted=model.collect_parent();require(model.parent_snapshot(accepted)==p['parent'],'canonical ROOTpost fresh parent changed')
        return model.report_body(p,path,accepted)
    def validate(r):
        nonlocal accepted
        if accepted is None:accepted=model.collect_parent()
        model.refresh_parent(accepted);model.validate_report(r,accepted)
    with base.controller_lock(ROOT/model.OUTPUT/'controller.lock'):
        try:
            # A crash between science and publication cannot silently repair a
            # prior namespace. Completed adoption requires both controls PASS.
            if (home/'lifecycle.json').exists():
                require((run/'publication_control/lifecycle.json').is_file() and read(run/'publication_control/lifecycle.json')['status']=='PASS','existing canonical namespace has incomplete publication; no repair')
            r=base.formal_transaction(home,model.root_binding(p),produce,validate,kind='CANONICAL_ROOT')
            model.publish_report(r,accepted);return dict(status=r['status'],published_result=artifact(ROOT/model.RESULT))
        except BaseException as error:
            if (home/'lifecycle.json').exists():
                body=read(home/'lifecycle.json');body.update(status='TAINTED',reason=repr(error));atomic(home/'lifecycle.json',body)
            raise


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('candidate-plan','seal-plan'):
        p=sub.add_parser(name);p.add_argument('--reviewed-codes-sha256',required=True)
        if name=='seal-plan':p.add_argument('--root-reviewed-candidate-sha256',required=True)
    p=sub.add_parser('supervise');p.add_argument('--plan-path',required=True);p.add_argument('--plan-file-sha256',required=True);p.add_argument('--root-memory-approved',action='store_true')
    sub.add_parser('verify')
    for name in ('_bootstrap','_worker'):
        p=sub.add_parser(name,help=argparse.SUPPRESS)
        for n in ('plan-path','plan-file-sha256','start-token','job-name'):p.add_argument('--'+n,required=True)
        if name=='_worker':p.add_argument('--bootstrap-pid',type=int,required=True)
    a=parser.parse_args(argv)
    if a.command=='candidate-plan':r=build_candidate(a.reviewed_codes_sha256)
    elif a.command=='seal-plan':r=seal_plan(a.reviewed_codes_sha256,a.root_reviewed_candidate_sha256)
    elif a.command=='supervise':r=run_supervised(a.plan_path,a.plan_file_sha256,a.root_memory_approved)
    elif a.command=='verify':r=model.verify_canonical()
    elif a.command=='_bootstrap':r=bootstrap_entry(a)
    else:r=worker_entry(a)
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0


if __name__=='__main__':raise SystemExit(main())
