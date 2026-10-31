"""Canonical continuation: adopt an accepted forward, run only a fresh reverse.

Original formal verification is a ROOT/public boundary. The owned worker has
its own explicitly smaller model/inference-input contract, never a fake old F.
"""
import sys
sys.dont_write_bytecode=True
import importlib
import os
from pathlib import Path
import random
import full_ssb_local_canonical as old
import full_ssb_local_canonical_run as prior_run

ROOT=old.ROOT
base=old.base
source=old.source
require=old.require
read=old.read
atomic=old.atomic
digest=old.digest
artifact=old.artifact
value_hash=old.value_hash
THREADS=old.THREADS
SCOPE='LOCAL_SSB_SF500_CANONICAL_CONTINUATION'
PROTOCOL='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
ENVIRONMENT_CONTRACT='ONLY_CURRENT_MODEL_FORWARD_QUERIES_MOMENTS_TRUTH_ALGORITHM_PARSER_RUNTIME;ROOT_FULL_FORMAL_PRE_POST'
OUTPUT='output/full/ssb/local_sf500_continuation'
RESULT='output/full/results/ssb_local_sf500_canonical_aqp_ci.json'  # Previously unpublished stable result alias; contract/scope is new.
API_PASS='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH'
PASS='PASS_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_AQP_CI'
REVERSE_PASS='PASS_CONTINUATION_REVERSE_EVALUATION'
FILES=('code/full_ssb_local_continuation.py','code/full_ssb_local_continuation_run.py')
OLD_SOURCE='code/full_ssb_local_canonical.py'
OLD_RUN='code/full_ssb_local_canonical_run.py'
PINS={**old.PINS,old.ADAPTER:old.ADAPTER_SHA,old.WINDOWS_HELPER:old.WINDOWS_SHA,
    OLD_SOURCE:'9c041ffc8ca40386ad9e3582fd81cb1f0e76fd3db1a337cb97bb686a521ff6b6',
    OLD_RUN:'8d561253786e8acd68e03c3b89fce46c2655f04cdd0c4b34492b369a6d757636'}


def code_snapshot():
    for module,path in ((old,OLD_SOURCE),(prior_run,OLD_RUN)):
        require(Path(module.__file__).resolve()==ROOT/path,'actually imported historical provider differs')
    for path,sha in PINS.items():require(digest(ROOT/path)==sha,'frozen continuation dependency changed: '+path)
    return {p:digest(ROOT/p) for p in FILES}


def collect_parent():
    code_snapshot()
    return old.collect_parent()  # Exactly one original formal F, no failed reverse/root acceptance.


def check_records(records,root=None):
    root=ROOT if root is None else Path(root)
    require(type(records) is list and bool(records) and len(records)==len({d['path'] for d in records}),'nonempty unique physical closure required')
    physical=set()
    for d in records:
        path=(Path(root)/d['path']).resolve();require(os.path.normcase(str(path)) not in physical,'physical closure alias')
        physical.add(os.path.normcase(str(path)));require(artifact(path,root)==d,'physical input changed: '+d['path'])
    return records


def environment_paths(env,root=None):
    root=Path(ROOT if root is None else root).resolve()
    paths=set(env['complete']['sources'])|set(env['frozen_sources'])|set(env['physical_native_libraries'])|set(env['python_base_native_files'])
    paths.update('.venv/Lib/site-packages/'+package+'/'+p for package,field in [('spn','spflow_sources'),('sqlparse','sqlparse_sources')] for p in env['complete'][field])
    paths.update(d['path'] for d in env['actual_module_roots'].values())
    paths.update(env[k]['path'] for k in ('python_executable','python_base_executable','operational_launcher'))
    return {(Path(p).resolve().relative_to(root).as_posix() if Path(p).is_absolute() and root in Path(p).resolve().parents else p) for p in paths}


def worker_environment():
    """Actual inference environment; intentionally excludes generator toolchains."""
    import full_ssb_guard as guard
    with old.native_platform():
        import platform
        package_root=(ROOT/'.venv/Lib/site-packages').resolve();modules={}
        require(Path(sys.prefix).resolve()==(ROOT/'.venv').resolve(),'original isolated venv required')
        for name in ('numpy','pandas','scipy','sklearn','joblib','tables','spn','sqlparse','networkx'):
            p=Path(importlib.import_module(name).__file__).resolve();require(package_root in p.parents,'actual package root differs')
            modules[name]=dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p))
        libraries={p.relative_to(ROOT).as_posix():digest(p) for p in sorted(package_root.rglob('*')) if p.is_file() and p.suffix.lower() in ('.dll','.pyd')}
        return dict(complete=guard.dependencies(),frozen_sources=base.frozen_sources(),
            python_executable=dict(path=str(Path(sys.executable).resolve()),sha256=digest(sys.executable)),
            python_base_native_files=base.base_python_files(sys.base_prefix,sys.prefix,getattr(sys,'_base_executable',sys.executable)),
            actual_module_roots=modules,physical_native_libraries=libraries,operational_launcher=artifact(ROOT/'code/full_ssb_native_model_run.py'),
            python_base_executable=artifact(getattr(sys,'_base_executable',sys.executable)),platform=platform.platform(),bridge_sha256=digest(base.__file__))


def inference_environment(full):
    return {k:v for k,v in full.items() if k!='generator_runtime'}


def accept_forward(old_plan,parent,root=ROOT):
    """Accept only the complete scientific/owned FORWARD, never old ROOT PASS."""
    root=Path(root);run=old.run_directory(old_plan,root)
    require(old_plan['parent']==old.parent_snapshot(parent),'forward original formal parent differs')
    forward=old._verify_phase(old_plan,'FORWARD',parent,root)
    records=old._phase_artifacts(old_plan,forward,parent,root)+prior_run.verify_child(old_plan,'FORWARD',root)
    records.append(artifact(run/'forward/seal.json',root))
    life=read(run/'root_control/lifecycle.json');reverse=read(run/'reverse_control/lifecycle.json');monitor=read(run/'reverse_control/monitor.json')
    require(life['status']==reverse['status']=='TAINTED' and monitor['status']=='STOPPED'
        and 'stale' in str(monitor['stop_reason']).lower() and not (run/'reverse').exists(),
        'only the retained stale-before-reverse failure is eligible; no old root repair')
    provenance=[artifact(run/p,root) for p in ('root_control/lifecycle.json','reverse_control/lifecycle.json','reverse_control/monitor.json')]
    return forward,sorted(records,key=lambda d:d['path']),provenance


def run_directory(plan,root=None):return Path(ROOT if root is None else root)/OUTPUT/'runs'/value_hash(plan)[:20]


def consumer_paths(plan,forward,root=None):
    root=ROOT if root is None else Path(root)
    paths=environment_paths(plan['worker_environment'],root)|set(PINS)|set(FILES)
    paths.add('code/benchmarks/ssb/sql/aqp_queries.sql')
    paths.add(plan['forward']['path'])
    directory=Path(forward['evaluation_directory'])
    paths.update((directory/('query_%02d'%i+s)).relative_to(root).as_posix() for i in range(13) for s in ('.json','.seal.json'))
    paths.update(plan['worker_roles'][k]['path'] for k in ('model','moments','truth'))
    return paths


def consumer_records(plan,forward,root=None):
    root=ROOT if root is None else Path(root)
    return [artifact(Path(root)/p,root) for p in sorted(consumer_paths(plan,forward,root))]


def verify_worker_inputs(plan):
    require(plan['codes']==code_snapshot() and plan['worker_environment']==worker_environment(),'current consumed source/runtime differs')
    forward=read(ROOT/plan['forward']['path'])
    require(forward['phase']=='FORWARD' and forward['status']=='PASS_CANONICAL_FORWARD_EVALUATION'
        and forward['parent']==plan['parent'] and forward['group_order_adapter_sha256']==old.ADAPTER_SHA,'bound adopted forward differs')
    records=consumer_records(plan,forward)
    require(records==plan['worker_artifacts'],'exact consumed closure (not the full historical raw closure) differs')
    check_records(records)
    for i in range(13):
        require(read(Path(forward['evaluation_directory'])/('query_%02d.json'%i))==forward['queries'][i],'consumed forward query alias differs')
    return forward


def candidate_from_parent(old_path,old_sha,parent):
    old_path=Path(old_path).resolve();p=prior_run.read_plan(old_path,old_sha)
    forward,accepted,provenance=accept_forward(p,parent)
    env=inference_environment(p['dependencies']['environment']);require(worker_environment()==env,'accepted actual inference environment changed')
    report=parent['report'];home=Path(report['directory'])
    roles=dict(model=artifact(parent['model_path']),moments=artifact(home/'sample_moments_native/moments.json'),truth=artifact(home/'core_truth_checkpoint.json'))
    candidate=dict(schema='local_ssb_canonical_continuation_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,
        scope=SCOPE,execution_protocol=PROTOCOL,codes=code_snapshot(),parent=old.parent_snapshot(parent),old_plan=artifact(old_path),old_plan_seal=artifact(old_path.with_suffix('.seal.json')),
        forward=artifact(old.run_directory(p)/'forward/verification.json'),accepted_forward_artifacts=accepted,retained_failure_provenance=provenance,
        worker_roles=roles,prepared_directory=report['prepared_directory'],worker_environment=env,
        environment_contract=ENVIRONMENT_CONTRACT,
        hash_seed=173,random_seed=74031,thread_limits={n:'1' for n in THREADS},additional_reserve_bytes=old.RESERVE_BYTES,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,historical_reverse_accepted=False)
    candidate['worker_artifacts']=consumer_records(candidate,forward)
    return candidate


def validate_reverse(r):
    require(r['status']==REVERSE_PASS and r['scope']==SCOPE and r['execution_protocol']==PROTOCOL and r['phase']=='REVERSE','distinct continuation reverse contract required')
    require(type(r['actual_model_loads']) is int and r['actual_model_loads']==13 and type(r['actual_evaluator_calls']) is int and r['actual_evaluator_calls']==26
        and r['execution_order']==list(reversed(range(13))) and all(type(i) is int for i in r['execution_order'])
        and r['evaluator_modes']==[False,True]*13,'actual13 loads/26 original evaluator calls required')
    env=r['environment']
    require(env['PYTHONHASHSEED']=='173' and env['random_seed']==env['numpy_seed']==74031 and env['thread_limits']=={n:'1' for n in THREADS}
        and type(env['process_id']) is int and env['process_id']>0,'fresh hash/seed/thread worker required')
    require(r['author_different_groups']==1713 and all(r[k] is False for k in ('author_reproduction_complete','full_paper_reproduction_complete','historical_reverse_accepted')),'author mismatch/failed historical replay must remain explicit')
    require(len(r['queries'])==13 and [q['query_no'] for q in r['queries']]==list(range(13)) and all(type(q['query_no']) is int and type(q['original_query_evaluator_calls']) is int
        and q['original_query_evaluator_calls']==2 and type(q['model_loads']) is int and q['model_loads']==1 for q in r['queries']),'each exact query requires one load and two actual evaluator calls')


def reverse_binding(plan):return dict(scope=SCOPE,execution_protocol=PROTOCOL,plan_sha256=value_hash(plan),worker_artifacts_sha256=value_hash(plan['worker_artifacts']),hash_seed=173,random_seed=74031,adapter_sha256=old.ADAPTER_SHA)


def _reverse_science(plan,forward):
    import numpy as np
    from full_ssb_group_order import canonical_group_order
    from full_ssb_replay import execute_query,compare_query
    from full_ssb_native_replay import deny_raw_data_access
    home=run_directory(plan)/'reverse/evaluation';queries=[];comparisons={};binding=reverse_binding(plan)
    with canonical_group_order(),old.observe_evaluation() as observed,deny_raw_data_access([ROOT/'data',Path(plan['prepared_directory'])]):
        np.random.seed(74031);random.seed(74031)  # All inference contexts/imports precede the declared RNG state.
        for i in reversed(range(13)):
            ref=forward['queries'][i];actual=execute_query(i,ref['sql'],ref['query_name'],str(ROOT/plan['worker_roles']['model']['path']),source.SAMPLE_ROWS)
            path=home/('query_%02d.json'%i);atomic(path,actual)  # Preserve actual evidence even if comparison fails.
            comparisons[str(i)]=compare_query(ref,actual);atomic(path.with_suffix('.seal.json'),dict(binding=binding,sha256=digest(path)))
            queries.append(actual)
    return dict(status=REVERSE_PASS,scope=SCOPE,execution_protocol=PROTOCOL,phase='REVERSE',binding=binding,directory=str(run_directory(plan)),
        queries=sorted(queries,key=lambda q:q['query_no']),comparisons=comparisons,execution_order=list(reversed(range(13))),actual_model_loads=observed['loads'],
        actual_evaluator_calls=len(observed['modes']),evaluator_modes=observed['modes'],environment=dict(PYTHONHASHSEED=os.environ.get('PYTHONHASHSEED'),random_seed=74031,numpy_seed=74031,
        process_id=os.getpid(),thread_limits={n:os.environ.get(n) for n in THREADS}),coverage=forward['coverage'],group_order_adapter_sha256=old.ADAPTER_SHA,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,historical_reverse_accepted=False)


def reverse_artifacts(plan,r):
    from full_ssb_replay import compare_query
    validate_reverse(r);require(r['binding']==reverse_binding(plan) and r['directory']==str(run_directory(plan)) and r['group_order_adapter_sha256']==old.ADAPTER_SHA,'reverse namespace/adapter/plan differs')
    forward=read(ROOT/plan['forward']['path']);home=run_directory(plan)/'reverse/evaluation'
    records=old.query_artifacts(home,reverse_binding(plan),*old.sql_identities())
    require(r['queries']==[read(home/('query_%02d.json'%i)) for i in range(13)] and r['coverage']==forward['coverage'],'reverse physical queries/coverage differs')
    require(r['comparisons']=={str(i):compare_query(forward['queries'][i],r['queries'][i]) for i in range(13)},'complete forward/reverse comparison differs')
    return records


def execute_reverse(plan):
    import full_ssb_local_continuation_run as runner
    require(os.environ.get('DEEPDB_SSB_CONTINUATION_WORKER')=='1' and os.environ.get('PYTHONHASHSEED')=='173' and all(os.environ.get(n)=='1' for n in THREADS),'fresh dedicated reverse worker required')
    runner.ops.verify_owned_job_membership(os.environ.get('DEEPDB_SSB_CONTINUATION_JOB'))
    path=ROOT/OUTPUT/'plans'/value_hash(plan)[:20]/'plan.json';require(runner.read_plan(path,digest(path))==plan,'reviewed current continuation plan required')
    forward=verify_worker_inputs(plan);probe=runner.ops.fast_resources();runner.validate_worker_resources(probe)
    home=run_directory(plan)/'reverse';require(not home.exists(),'reverse namespace already used; no repair');home.mkdir(parents=True,exist_ok=False)
    def produce():return dict(_reverse_science(plan,forward),resources_at_worker_admission=probe)
    def validate(r):validate_reverse(r);require(r['resources_at_worker_admission']==probe,'actual worker resource receipt differs');runner.validate_worker_resources(r['resources_at_worker_admission']);verify_worker_inputs(plan);reverse_artifacts(plan,r)
    r=base.formal_transaction(home/'science_control',reverse_binding(plan),produce,validate,kind='CONTINUATION_REVERSE')
    atomic(home/'verification.json',r);atomic(home/'seal.json',dict(status='PASS_CONTINUATION_REVERSE',artifacts=reverse_artifacts(plan,r)))
    return r


def verify_reverse(plan):
    import full_ssb_local_continuation_run as runner
    home=run_directory(plan)/'reverse';r=read(home/'verification.json');records=reverse_artifacts(plan,r)
    runner.validate_worker_resources(r['resources_at_worker_admission'])
    require(read(home/'seal.json')==dict(status='PASS_CONTINUATION_REVERSE',artifacts=records),'reverse complete physical seal differs')
    receipt=read(home/'science_control/receipt.json');life=read(home/'science_control/lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='CONTINUATION_REVERSE' and receipt['result']==r and receipt['binding']==life['binding']==reverse_binding(plan)
        and life['receipt_sha256']==digest(home/'science_control/receipt.json'),'reverse scientific lifecycle/receipt differs')
    return r,records+[artifact(home/p) for p in ('verification.json','seal.json','science_control/receipt.json','science_control/lifecycle.json')]


def report_body(plan,path,parent,root_final_resources):
    import full_ssb_local_continuation_run as runner
    runner.validate_root_resources(root_final_resources)
    forward=read(ROOT/plan['forward']['path']);reverse,_=verify_reverse(plan);prior=parent['report'];run=run_directory(plan)
    return dict(status=PASS,stage='LOCAL_SSB_SF500_CANONICAL_CONTINUATION_1M_AQP_CI',scope=SCOPE,execution_protocol=PROTOCOL,
        variant='CANONICAL_PAIRED_DECODED_GROUP_ORDER',evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',group_order_adapter_sha256=old.ADAPTER_SHA,
        directory=str(run),plan=plan,plan_path=Path(path).relative_to(ROOT).as_posix(),plan_file_sha256=digest(path),plan_binding_sha256=value_hash(plan),
        parent=old.parent_snapshot(parent),parent_formal=parent['published_result'],original_mismatch=parent['original_mismatch'],
        inputs=prior['inputs'],prepared_directory=prior['prepared_directory'],moments_directory=str(Path(prior['directory'])/'sample_moments_native'),
        truth_projection_path=str(Path(prior['directory'])/'core_truth_checkpoint.json'),model_path=parent['model_path'],model_sha256=parent['model_sha256'],
        model=prior['model'],spn_count=prior['spn_count'],training_tables=prior['training_tables'],model_training_cap_per_table=1000000,
        paper_figure11_training_budget_reproduced=False,population_rows=source.N,actual_sample_rows=source.SAMPLE_ROWS,fact_normalizer=prior['fact_normalizer'],
        queries=forward['queries'],evaluation_binding=forward['evaluation_binding'],point_query_errors=0,ci_query_errors=0,forward=plan['forward'],reverse=artifact(run/'reverse/verification.json'),
        phase_model_loads=dict(FORWARD=1,REVERSE=13),phase_evaluator_calls=dict(FORWARD=26,REVERSE=26),reverse_comparisons=reverse['comparisons'],coverage=forward['coverage'],
        group_order_adapter=artifact(ROOT/old.ADAPTER),author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        author_population_row_count_and_13_truths_match=False,author_full_row_byte_identity_proven=False,historical_reverse_accepted=False,historical_result_changed=False,
        adopted_forward=True,forward_reexecuted=False,preparation_executed=False,training_executed=False,moments_executed=False,root_final_resources=root_final_resources)


def complete_artifacts(plan,r,parent):
    import full_ssb_local_continuation_run as runner
    path=ROOT/r['plan_path'];require(runner.read_plan(path,r['plan_file_sha256'])==plan and r==report_body(plan,path,parent,r['root_final_resources']),'continuation complete report/parent differs')
    candidate=candidate_from_parent(ROOT/plan['old_plan']['path'],plan['old_plan']['sha256'],parent);candidate['operational_policy']=runner.POLICY
    require(candidate==runner.candidate_part(plan),'current original forward/input closure differs')
    records={d['path']:d for d in parent['artifacts']+plan['accepted_forward_artifacts']+plan['retained_failure_provenance']+plan['worker_artifacts']}
    _,reverse=verify_reverse(plan)
    for d in reverse+runner.verify_child(plan):records[d['path']]=d
    run=run_directory(plan);receipt=read(run/'root_control/receipt.json');life=read(run/'root_control/lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='CONTINUATION_ROOT' and receipt['result']==r and receipt['binding']==life['binding']==runner.root_binding(plan)
        and life['receipt_sha256']==digest(run/'root_control/receipt.json'),'whole continuation ROOT PASS required')
    for p in [path,path.with_suffix('.seal.json'),ROOT/plan['old_plan']['path'],ROOT/plan['old_plan_seal']['path'],run/'root_control/receipt.json',run/'root_control/lifecycle.json',run/'verification.json',ROOT/RESULT]:
        d=artifact(p);records[d['path']]=d
    require(read(run/'verification.json')==read(ROOT/RESULT)==r,'continuation publication aliases changed')
    return [records[p] for p in sorted(records)]


def publication_binding(r):return dict(scope=SCOPE,execution_protocol=PROTOCOL,report_sha256=value_hash(r),root_receipt_sha256=digest(Path(r['directory'])/'root_control/receipt.json'))


def publication_links(r):
    home=Path(r['directory']);return dict(published_result_sha256=digest(ROOT/RESULT),verification_sha256=digest(home/'verification.json'),seal_sha256=digest(home/'verification_seal.json'))


def verify_publication(r,parent,require_publication=True):
    home=Path(r['directory']);records=complete_artifacts(r['plan'],r,parent)
    require(read(home/'verification_seal.json')==dict(status='PASS_CONTINUATION_PUBLICATION',scope=SCOPE,execution_protocol=PROTOCOL,artifacts=records),'complete continuation publication seal differs')
    records.append(artifact(home/'verification_seal.json'))
    if require_publication:
        receipt=read(home/'publication_control/receipt.json');life=read(home/'publication_control/lifecycle.json')
        require(receipt['status']==life['status']=='PASS' and receipt['kind']=='CONTINUATION_PUBLICATION' and receipt['binding']==life['binding']==publication_binding(r)
            and receipt['result']==publication_links(r) and life['receipt_sha256']==digest(home/'publication_control/receipt.json'),'complete continuation publication transaction required')
        records.extend(artifact(home/'publication_control'/n) for n in ('receipt.json','lifecycle.json'))
    return records


def publish(r,parent):
    run=Path(r['directory'])
    def produce():
        require(not (ROOT/RESULT).exists() and not (run/'verification.json').exists(),'continuation publication cannot overwrite')
        atomic(run/'verification.json',r);atomic(ROOT/RESULT,r)
        atomic(run/'verification_seal.json',dict(status='PASS_CONTINUATION_PUBLICATION',scope=SCOPE,execution_protocol=PROTOCOL,artifacts=complete_artifacts(r['plan'],r,parent)))
        return publication_links(r)
    def validate(result):verify_publication(r,parent,False);require(result==publication_links(r),'publication links differ')
    return base.formal_transaction(run/'publication_control',publication_binding(r),produce,validate,kind='CONTINUATION_PUBLICATION')


def _verify_complete(parent):
    r=read(ROOT/RESULT);records=verify_publication(r,parent);run=Path(r['directory'])
    return dict(status=API_PASS,scope=SCOPE,execution_protocol=PROTOCOL,variant=r['variant'],evaluation_variant=r['evaluation_variant'],group_order_adapter_sha256=old.ADAPTER_SHA,
        report=r,parent_snapshot=dict(parent,proof_method='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL'),published_result=artifact(ROOT/RESULT),verification=artifact(run/'verification.json'),
        verification_seal=artifact(run/'verification_seal.json'),plan=artifact(ROOT/r['plan_path']),formal_receipt=artifact(run/'root_control/receipt.json'),formal_lifecycle=artifact(run/'root_control/lifecycle.json'),
        artifacts=records,dependencies=r['plan'],model_path=r['model_path'],model_sha256=r['model_sha256'],sample_rows=source.SAMPLE_ROWS,population_rows=source.N,
        queries=r['queries'],evaluation_binding=r['evaluation_binding'],original_mismatch=r['original_mismatch'],parent_formal=parent['published_result'],forward=r['forward'],reverse=r['reverse'],
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,historical_reverse_accepted=False,
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False)


def verify_canonical():
    require((ROOT/RESULT).is_file(),'completed canonical continuation publication missing')
    return _verify_complete(collect_parent())


verify_continuation=verify_canonical
