"""Thin10M controller reusing sealed operational functions and owned-job primitives."""
import sys
sys.dont_write_bytecode=True
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import full_ssb_local_ci as model
import full_ssb_local_model_run as frozen

ROOT=model.ROOT
base=model.base
ops=frozen.ops
source=SimpleNamespace(**dict(vars(model.source),SCOPE=model.SCOPE))
require=model.require
digest=model.digest
atomic=model.atomic
read=model.read
artifact=model.artifact
value_hash=model.value_hash
SELF='code/full_ssb_local_ci_run.py'
JOB_PREFIX='Local\\DeepDB_SSB_NATIVE_LOCAL_CI10M_'
LOGS=frozen.LOGS
finite_number=frozen.finite_number
FUNCTIONS=('verify_supervisor_result','verify_supervisor','start_handshake','bootstrap_entry','taint_local_tail')
MAPPINGS={'ssb_local_sf500_bootstrap_v1':'ssb_local_ci10m_bootstrap_v1','ssb_local_sf500_worker_v1':'ssb_local_ci10m_worker_v1',
    'LOCAL_SUPERVISOR':'LOCAL_CI_SUPERVISOR',
    "base.check_resources(launch['free_disk_bytes'],launch['available_memory_bytes'],launch['existing_ssb_bytes'])":
        "base.check_resources(launch['free_disk_bytes'],launch['available_memory_bytes'],launch['existing_ssb_bytes'],additional_bytes=model.OPERATIONAL_RESERVE_BYTES)"}


def configured_operational_source():
    path=Path(frozen.__file__);require(digest(path)==model.PRIOR_PINS['code/full_ssb_local_model_run.py'],'frozen operational capsule changed')
    raw=path.read_text(encoding='utf-8');nodes={n.name:n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS}
    require(set(nodes)==set(FUNCTIONS),'complete operational function set required');a='\n\n'.join(ast.get_source_segment(raw,nodes[n]) for n in FUNCTIONS)+'\n';b=a
    for old,new in MAPPINGS.items():require(old in b,'operational schema mapping absent');b=b.replace(old,new)
    return a,b


def capsule_binding():
    a,b=configured_operational_source();return dict(frozen_operational_sha256=model.PRIOR_PINS['code/full_ssb_local_model_run.py'],functions=list(FUNCTIONS),
        source_sha256=hashlib.sha256(a.encode()).hexdigest(),configured_source_sha256=hashlib.sha256(b.encode()).hexdigest(),mappings=MAPPINGS,scope=model.SCOPE)


def capsule(kind='FORMAL'):
    proxy=SimpleNamespace(**dict(vars(model),RESULT=model.result_path(kind)))
    namespace=dict(globals());namespace['model']=proxy
    exec(compile(configured_operational_source()[1],'<sealed-local-ci-operational-capsule>','exec'),namespace);return namespace


def candidate_body(kind,codes_sha256,golden,dependencies,lineage):
    require(kind in ('GOLDEN','FORMAL'),'known10M experiment kind required')
    return dict(schema='ssb_local_ci10m_plan_v2_canonical',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,scope=model.SCOPE,kind=kind,
        reviewed_codes_sha256=codes_sha256,model=dict(model.PARAMETERS),actual_training_rows_per_table=dict(model.EXPECTED_ROWS),
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        budget_metadata=dict(model.BUDGET_METADATA),
        original_mismatch_sha256=model.source.NATIVE_REPORT_SHA,source_receipt_sha256=model.SOURCE_RECEIPT_SHA,
        root_decision_sha256=model.source.DECISION_SHA,golden=golden,dependencies=dependencies,lineage=lineage,
        operational_policy=dict(ops.OPERATIONAL_POLICY),operational_capsule=capsule_binding(),
        resource_admission=dict(minimum_launch_memory_bytes=model.MINIMUM_LAUNCH_MEMORY_BYTES,additional_bytes=model.OPERATIONAL_RESERVE_BYTES),**model.EVALUATION_METADATA)


def build_candidate(kind,reviewed_codes_sha256,auxiliary_sources=None):
    require(reviewed_codes_sha256==value_hash(model.code_snapshot()),'matching root-reviewed10M sources required')
    full,checked=model._verify_prerequisites(kind);lineage=model.lineage_snapshot(full)
    golden=checked if kind=='GOLDEN' else model.golden_snapshot(checked)
    return candidate_body(kind,reviewed_codes_sha256,golden,model.dependency_snapshot(auxiliary_sources),lineage)


def seal_plan(kind,reviewed_codes_sha256,root_reviewed_candidate_sha256,auxiliary_sources=None):
    c=build_candidate(kind,reviewed_codes_sha256,auxiliary_sources);require(value_hash(c)==root_reviewed_candidate_sha256,'explicit root-reviewed10M candidate SHA differs')
    p=dict(c,status='ROOT_REVIEWED_LOCAL_SSB_10M_CI_PLAN',executable=True,root_reviewed_candidate_sha256=root_reviewed_candidate_sha256)
    path=ROOT/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json'
    if path.exists() or path.with_suffix('.seal.json').exists():require(read_plan(path,digest(path))==p,'existing10M plan differs; no repair')
    else:atomic(path,p);atomic(path.with_suffix('.seal.json'),{'sha256':digest(path)})
    return dict(plan=artifact(path),plan_binding_sha256=value_hash(p))


def read_plan(path,expected_sha,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve();require(digest(path)==expected_sha,'10M reviewed plan file SHA differs');p=read(path)
    template=candidate_body('GOLDEN','',{}, {},{})
    require(set(p)==set(template)|{'root_reviewed_candidate_sha256'},'complete exact10M reviewed plan schema required')
    require(path==root/model.OUTPUT/'plans'/value_hash(p)[:20]/'plan.json' and read(path.with_suffix('.seal.json'))=={'sha256':expected_sha},'10M plan namespace/seal differs')
    expected=candidate_body(p['kind'],p['reviewed_codes_sha256'],p['golden'],p['dependencies'],p['lineage'])
    candidate=dict(p);approved=candidate.pop('root_reviewed_candidate_sha256');candidate.update(status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False)
    require(candidate==expected and value_hash(candidate)==approved and p['status']=='ROOT_REVIEWED_LOCAL_SSB_10M_CI_PLAN' and p['executable'] is True,'exact reviewed10M scope/model/resources/approval required')
    sources=p['dependencies']['ci_sources'];require(set(sources)==set(model.FILES)
        and p['reviewed_codes_sha256']==value_hash(sources),'complete reviewed10M code-set source map required')
    lineage=p['lineage'];require(all(lineage.get(k)==v for k,v in model.EVALUATION_METADATA.items())
        and lineage.get('historical_reverse_accepted') is False,'canonical parent variant with failed historical reverse rejected required')
    for key in ('parent_formal','parent_reverse','parent_canonical'):
        d=lineage.get(key,{})
        require(set(d)=={'path','bytes','sha256'} and type(d.get('path')) is str and type(d.get('bytes')) is int and d['bytes']>0
            and type(d.get('sha256')) is str and re.fullmatch('[a-f0-9]{64}',d['sha256']) is not None,'complete canonical parent lineage descriptor required')
    require(lineage['parent_formal']['path']==model.previous.RESULT and lineage['parent_formal']['sha256']==model.PARENT_RESULT_SHA
        and lineage['parent_canonical']['path']==model.PARENT_CANONICAL_RESULT
        and re.fullmatch('output/full/ssb/local_sf500_canonical/runs/[a-f0-9]{20}/reverse/verification.json',lineage['parent_reverse']['path']) is not None,
        'canonical1M original/new reverse/result identity required; raw or failed9c lineage cannot authorize a plan')
    return p


def supervisor_binding(report):
    deps=report['plan']['dependencies'];env=deps['environment']
    return dict(scope=model.SCOPE,original_mismatch_sha256=model.source.NATIVE_REPORT_SHA,author_different_groups=1713,
        plan_binding_sha256=report['plan_binding_sha256'],plan_file_sha256=report['plan_file_sha256'],source_receipt_sha256=report['source_receipt_sha256'],
        bridge_sha256=report['adapter_source_sha256'],launcher_sha256=deps['ci_sources'][SELF],shared_operational_sha256=model.source.STRICT_PINS['code/full_ssb_native_model_run.py'],
        bootstrap_executable=env['python_base_executable'],venv_executable=env['python_executable'],policy=ops.OPERATIONAL_POLICY)


def verify_supervisor_result(report,binding,result,root=ROOT):
    records=capsule(report['plan'].get('kind','FORMAL'))['verify_supervisor_result'](report,binding,result,root)
    require(result['resources_at_launch']['available_memory_bytes']>=model.MINIMUM_LAUNCH_MEMORY_BYTES,'at least7GiB local10M launch RAM evidence required')
    return records


def verify_supervisor(report,root=ROOT):
    # Route nested validator to the extra7GiB admission check, rather than the
    # extracted5GiB baseline function; all live limits remain unchanged.
    n=capsule();n['verify_supervisor_result']=verify_supervisor_result
    return n['verify_supervisor'](report,root)


def taint_local_tail(directory,error):return capsule()['taint_local_tail'](directory,error)
def start_handshake(args):return capsule()['start_handshake'](args)
def bootstrap_entry(args):return capsule()['bootstrap_entry'](args)


def run_supervised(plan_path,expected_plan_sha256,memory_approved=False,root=ROOT):
    require(memory_approved,'separate explicit10M root memory release required');require(Path(root).resolve()==ROOT,'actual10M run requires original root')
    path=Path(plan_path).resolve();p=read_plan(path,expected_plan_sha256);key=value_hash(p);run=ROOT/model.OUTPUT/'runs'/key[:20];home=run/'supervisor_control'
    report=dict(plan=p,plan_binding_sha256=key,plan_file_sha256=expected_plan_sha256,source_receipt_sha256=p['source_receipt_sha256'],
        adapter_source_sha256=p['dependencies']['ci_sources']['code/full_ssb_local_ci.py'],directory=str(run))
    binding=supervisor_binding(report)
    postflight=None
    def produce():
        nonlocal postflight
        require(p['dependencies']==model.dependency_snapshot(p['dependencies']['auxiliary_sources']),'reviewed10M source/runtime changed')
        full,golden=model._verify_prerequisites(p['kind'])
        require(p['lineage']==model.lineage_snapshot(full),'10M complete1M prerequisites changed')
        require(p['golden']==(golden if p['kind']=='GOLDEN' else model.golden_snapshot(golden)),'10M cap-golden prerequisite changed')
        probe=ops.operational_resources();base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'],additional_bytes=model.OPERATIONAL_RESERVE_BYTES)
        require(probe['available_memory_bytes']>=model.MINIMUM_LAUNCH_MEMORY_BYTES,'at least7GiB10M launch RAM required')
        import secrets
        token=secrets.token_hex(16);job=JOB_PREFIX+token
        require(artifact(ops.base_python_executable())==binding['bootstrap_executable'],'reviewed direct base interpreter differs')
        command=[str(ops.base_python_executable()),str(ROOT/SELF),'_bootstrap','--plan-path',str(path),'--plan-file-sha256',expected_plan_sha256,'--start-token',token,'--job-name',job]
        result=ops.run_owned_child(command,home,binding,start_payload=dict(start=token,plan_binding_sha256=key),job_name=job,initial_resources=probe)
        result['artifacts'].extend(artifact(home/n) for n in LOGS[3:]);result['resources_at_launch']=probe
        postflight=model.verify_scientific_publication(p['kind']);result.update(published_result_sha256=postflight['published_result']['sha256'],verification_seal_sha256=postflight['verification_seal']['sha256'])
        return result
    def validate(r):
        verify_supervisor_result(report,binding,r)
        # Only this producer's just-completed postflight can be shared. When a
        # previous PASS is adopted, producer never runs and full verification is fresh.
        verified=postflight if postflight is not None else model.verify_scientific_publication(p['kind'])
        for key,link in (('published_result','published_result_sha256'),('verification_seal','verification_seal_sha256')):
            d=verified[key]
            require(model.artifact(ROOT/d['path'],ROOT)==d and r[link]==d['sha256'],'same-stack postflight publication changed')
    with base.controller_lock(ROOT/model.OUTPUT/'supervisor.lock'):
        try:return base.formal_transaction(home,binding,produce,validate,kind='LOCAL_CI_SUPERVISOR')
        except BaseException as error:taint_local_tail(run,error);raise


def worker_entry(args):
    p,_=start_handshake(args);os.environ.update(DEEPDB_SSB_LOCAL_CI_WORKER='1',DEEPDB_SSB_LOCAL_CI_JOB=args.job_name)
    home=ROOT/model.OUTPUT/'runs'/value_hash(p)[:20]/'supervisor_control';path=home/'worker_start.json';require(not path.exists(),'existing10M worker evidence cannot be replaced')
    atomic(path,dict(schema='ssb_local_ci10m_worker_v1',scope=model.SCOPE,pid=os.getpid(),parent_pid=os.getppid(),bootstrap_pid=args.bootstrap_pid,
        membership_verified_after_go=True,named_job=args.job_name,plan_binding_sha256=value_hash(p),base_executable=artifact(ops.base_python_executable()),venv_executable=artifact(sys.executable)))
    r=model.execute_worker(p);return dict(status=r['status'])


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('candidate-plan','seal-plan'):
        p=sub.add_parser(name);p.add_argument('--kind',choices=('GOLDEN','FORMAL'),required=True);p.add_argument('--reviewed-codes-sha256',required=True);p.add_argument('--frozen-auxiliary-sources-json')
        if name=='seal-plan':p.add_argument('--root-reviewed-candidate-sha256',required=True)
    p=sub.add_parser('supervise');p.add_argument('--plan-path',required=True);p.add_argument('--plan-file-sha256',required=True);p.add_argument('--root-memory-approved',action='store_true')
    sub.add_parser('verify-golden');sub.add_parser('verify-formal')
    for name in ('_bootstrap','_worker'):
        p=sub.add_parser(name,help=argparse.SUPPRESS)
        for n in ('plan-path','plan-file-sha256','start-token','job-name'):p.add_argument('--'+n,required=True)
        if name=='_worker':p.add_argument('--bootstrap-pid',required=True,type=int)
    a=parser.parse_args(argv);aux=read(a.frozen_auxiliary_sources_json) if getattr(a,'frozen_auxiliary_sources_json',None) else None
    if a.command=='candidate-plan':r=build_candidate(a.kind,a.reviewed_codes_sha256,aux)
    elif a.command=='seal-plan':r=seal_plan(a.kind,a.reviewed_codes_sha256,a.root_reviewed_candidate_sha256,aux)
    elif a.command=='supervise':r=run_supervised(a.plan_path,a.plan_file_sha256,a.root_memory_approved)
    elif a.command=='verify-golden':r=model.verify_golden()
    elif a.command=='verify-formal':r=model.verify_local_ci()
    elif a.command=='_bootstrap':r=bootstrap_entry(a)
    else:r=worker_entry(a)
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0


if __name__=='__main__':raise SystemExit(main())
