"""Separate canonical GROUP BY evaluation; old models/results/replay stay frozen."""
import sys
sys.dont_write_bytecode=True
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import full_ssb_local_model as previous

source=previous.source
base=source.base
ROOT=source.ROOT
SCOPE='LOCAL_SSB_SF500_CANONICAL_CI'
OUTPUT='output/full/ssb/local_sf500_canonical'
RESULT='output/full/results/ssb_local_sf500_canonical_aqp_ci.json'
API_PASS='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH'
PASS='PASS_LOCAL_SSB_SF500_CANONICAL_AQP_CI'
PHASES=('FORWARD','REVERSE')
HASH_SEEDS={'FORWARD':0,'REVERSE':173}
RANDOM_SEED=74031
RTOL,ATOL=1e-9,1e-5
THREADS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')
RESERVE_BYTES=512*2**20
PARENT_RESULT_SHA='da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82'
SOURCE_SHA='75fef537963dcbc183a720f2abc1b47b6972550822ba4591dec8f8336183e712'
ADAPTER='code/full_ssb_group_order.py'
ADAPTER_SHA='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'
WINDOWS_HELPER='code/full_windows_fingerprint.py'
WINDOWS_SHA='a9e9034efad01e258c521934aea43f0f405ff78c42caffb7841a73fd03d96784'
FILES=('code/full_ssb_local_canonical.py','code/full_ssb_local_canonical_run.py')
PINS=dict(source.STRICT_PINS,**{
 'code/full_ssb_local_source.py':'699f85ec4d24c326a7b491cd4cbf9c5746a98e7947d5b79db60200d08c0e3ca3',
 'code/full_ssb_local_model.py':'0b736cb30e7f1e93c66d2ac632c9b8a0ac0023595440c46b8d9215962184bced',
 'code/full_ssb_local_model_run.py':'fd676fb41780ae96074a08f2478a7cef9820b7c55a65717b9b8e28ea9545dee3',
 'code/full_ssb_replay.py':'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab',
 'code/full_ssb_native_replay.py':'6c8de16e03a8ba20448121fd4659c092c668d4db0f7214b932a40bf20d30302d',
 'code/full_ssb_local_replay.py':'9c2211af6b6385944010e079eef2fbc1f1dae381ccd39590f4acef9479c98aac',
 'code/full_ssb_model.py':'5b6d31a15884cf09ba29c19d3c49db2c5a79d82a5fba40e4aa1d7e714f23aa27',
 'code/full_ssb_guard.py':'fc19133d00216ceac72198eed747107d81e82f224804c69440290931a201f842'})
require=source.require
digest=source.digest
artifact=source.artifact
atomic=source.atomic
read=source.read
value_hash=source.value_hash


@contextmanager
def native_platform():
    require(digest(ROOT/WINDOWS_HELPER)==WINDOWS_SHA and digest(ROOT/source.RESULT)==SOURCE_SHA,'fixed native platform/source changed')
    from full_windows_fingerprint import verified_platform
    with verified_platform(read(ROOT/source.RESULT)['dependencies']['platform'],'AMD64') as proof:yield proof


def code_snapshot():
    for path,sha in dict(PINS,**{ADAPTER:ADAPTER_SHA,WINDOWS_HELPER:WINDOWS_SHA}).items():
        require(digest(ROOT/path)==sha,'frozen canonical dependency source pin changed: '+path)
    return {p:digest(ROOT/p) for p in FILES}


def collect_parent(root=ROOT):
    """One direct complete formal F; never asks failed9c to certify anything."""
    require(Path(root).resolve()==ROOT,'actual parent verifier requires original root')
    code_snapshot()
    with native_platform():p=previous.verify_local_formal(root)
    require(p['status']==previous.API_PASS and p['scope']==source.SCOPE and p['sample_rows']==source.SAMPLE_ROWS
        and p['population_rows']==source.N and p['author_different_groups']==1713 and p['author_reproduction_complete'] is False
        and p['full_paper_reproduction_complete'] is False and p['published_result']['sha256']==PARENT_RESULT_SHA
        and p['report']['plan']['model']==previous.MODEL,'exact complete historical1M formal prerequisite required')
    records={d['path']:d for d in p['artifacts']}
    for path in dict(PINS,**{ADAPTER:ADAPTER_SHA,WINDOWS_HELPER:WINDOWS_SHA}):
        d=artifact(ROOT/path);records[d['path']]=d
    records=[records[n] for n in sorted(records)]
    p=dict(p,artifacts=records,closure_sha256=value_hash(records))
    refresh_parent(p,root);return p


def refresh_parent(parent,root=ROOT):
    """Private current-entry closure refresh, not an external proof-accepting API."""
    records=parent['artifacts'];require(bool(records) and len(records)==len({d['path'] for d in records})
        and value_hash(records)==parent['closure_sha256'],'complete current-entry parent physical closure required')
    for d in records:require(artifact(Path(root)/d['path'],root)==d,'parent physical artifact changed: '+d['path'])
    require(parent['published_result'] in records,'parent publication alias not in complete physical closure')
    if 'report' in parent:require(read(Path(root)/parent['published_result']['path'])==parent['report'],'parent current published header changed')
    return records


def parent_snapshot(parent):
    fields=('published_result','verification','verification_seal','formal_receipt','formal_lifecycle','plan','model_path','model_sha256','sample_rows','population_rows','original_mismatch','closure_sha256')
    return {k:parent[k] for k in fields}


def dependency_snapshot():
    with native_platform() as proof:env=base.dependency_snapshot()
    import full_ssb_local_canonical_run as runner
    return dict(environment=env,canonical_sources=code_snapshot(),frozen_sources=PINS,group_order_adapter=artifact(ROOT/ADAPTER),
        windows_fingerprint=dict(adapter=artifact(ROOT/WINDOWS_HELPER),proof=proof),operational_capsule=runner.capsule_binding())


def validate_execution(r):
    phase=r['phase'];require(phase in PHASES and r['scope']==SCOPE,'distinct canonical phase/scope required')
    require(r['execution_order']==(list(range(13)) if phase=='FORWARD' else list(reversed(range(13))))
        and r['actual_model_loads']==(1 if phase=='FORWARD' else 13) and r['actual_evaluator_calls']==26
        and r['evaluator_modes']==[False,True]*13,'complete canonical actual load/evaluator accounting required')
    e=r['environment'];require(e['PYTHONHASHSEED']==str(HASH_SEEDS[phase]) and e['random_seed']==e['numpy_seed']==RANDOM_SEED
        and e['thread_limits']=={n:'1' for n in THREADS} and r['author_different_groups']==1713
        and r['author_reproduction_complete'] is False and r['full_paper_reproduction_complete'] is False,'canonical fresh hash/seed/thread/author boundary differs')


@contextmanager
def observe_evaluation(module=None):
    if module is None:
        import ensemble_compilation.spn_ensemble as module
    original_load=module.read_ensemble;cls=module.SPNEnsemble;original_call=cls.evaluate_query;count=dict(loads=0,modes=[])
    def load(*a,**k):count['loads']+=1;return original_load(*a,**k)
    def call(self,*a,**k):count['modes'].append(k.get('confidence_intervals',False));return original_call(self,*a,**k)
    module.read_ensemble=load;cls.evaluate_query=call
    try:yield count
    finally:module.read_ensemble=original_load;cls.evaluate_query=original_call


def query_artifacts(directory,binding,sqls,names,root=ROOT):
    directory=Path(directory);needed={'query_%02d'%i+s for i in range(13) for s in ('.json','.seal.json')}
    require(len(sqls)==len(names)==13 and {p.name for p in directory.glob('query_*.json')}==needed,'complete canonical13-query/26-file set required')
    records=[]
    for i,(sql,name) in enumerate(zip(sqls,names)):
        path=directory/('query_%02d.json'%i);q=read(path);seal=read(path.with_suffix('.seal.json'))
        require(q.get('query_no')==i and q.get('query_name')==name and q.get('sql')==sql
            and seal=={'binding':binding,'sha256':digest(path)},'canonical exact query identity/binding differs')
        records.extend(artifact(p,root) for p in (path,path.with_suffix('.seal.json')))
    return records


def sql_identities():
    from full_ssb_native_replay import QUERY_NAMES
    sqls=(ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines()
    require(len(sqls)==len(QUERY_NAMES)==13,'frozen13 SQL/name identities required');return sqls,QUERY_NAMES


def run_directory(plan,root=ROOT):return Path(root)/OUTPUT/'runs'/value_hash(plan)[:20]


def phase_binding(plan,phase):
    return dict(scope=SCOPE,phase=phase,plan_sha256=value_hash(plan),parent=plan['parent'],adapter_sha256=ADAPTER_SHA,
        hash_seed=HASH_SEEDS[phase],random_seed=RANDOM_SEED,relative_tolerance=RTOL,absolute_tolerance=ATOL)


def compare_forward_query(old,new):
    from full_ssb_replay import key,compare_query
    counts=('truth_groups','model_groups','missing_model_groups','extra_model_groups','reference_ci_eligible_groups')
    require(all(type(new.get(f)) is int and new[f]==old[f] for f in counts),'canonical forward parent coverage counts differ')
    left={key(g['key']):g for g in old['groups']};right={key(g['key']):g for g in new['groups']}
    require(len(left)==len(old['groups']) and len(right)==len(new['groups']) and set(left)==set(right),'canonical forward complete parent group identities differ')
    fields=('truth','status','sample_moments','reference_ci','released_ci_comparison')
    require(all(all(left[k].get(f)==right[k].get(f) for f in fields) for k in left),'canonical forward exact local truth/reference changed')
    def points(q):return dict(q,groups=[dict(g,model_interval=None) for g in q['groups']],nonfinite_original_intervals=[])
    return compare_query(points(old),points(new))


def phase_coverage(phase,queries,forward=None):
    from full_ssb_replay import coverage
    if phase=='FORWARD':return coverage({'queries':queries})
    require(phase=='REVERSE' and forward is not None,'validated forward truth coverage required for raw reverse rows')
    return forward['coverage']


def _scientific_phase(plan,phase,parent):
    """Only the dedicated owned worker reaches original inference callbacks."""
    import random
    import numpy as np
    from full_ssb_group_order import canonical_group_order
    from full_ssb_replay import execute_query,compare_query,coverage
    from full_ssb_native_replay import deny_raw_data_access
    import full_ssb_guard as guard
    run=run_directory(plan);home=run/phase.lower();old=parent['report'];sqls,names=sql_identities();binding=phase_binding(plan,phase)
    order=list(range(13)) if phase=='FORWARD' else list(reversed(range(13)));queries=[];comparisons={}
    protected=[ROOT/'data',Path(old['prepared_directory'])]
    with canonical_group_order(),observe_evaluation() as observed,deny_raw_data_access(protected):
        # The released spn_ensemble import seeds NumPy(1). All contexts and
        # their inference imports must be entered before the declared seed.
        np.random.seed(RANDOM_SEED);random.seed(RANDOM_SEED)
        if phase=='FORWARD':
            # Truth/moments are already sealed JSON. No generator/helper is invoked.
            truth=guard.core.population_truth_groups(Path(old['directory'])/'core_truth_checkpoint.json')
            moments=read(Path(old['directory'])/'sample_moments_native/moments.json')
            evaluated=guard.core.evaluate_ssb(old['model'],truth,moments['queries'],home/'evaluation')
            queries=evaluated['queries'];evaluation_directory=evaluated['directory'];query_binding=evaluated['binding']
            require(evaluated['point_query_errors']==evaluated['ci_query_errors']==0,'canonical original evaluator recorded errors; new phase cannot PASS')
        else:
            forward=_verify_phase(plan,'FORWARD',parent)
            evaluation_directory=str(home/'evaluation');query_binding=binding
            for i in order:
                actual=execute_query(i,sqls[i],names[i],old['model_path'],source.SAMPLE_ROWS)
                comparisons[str(i)]=compare_query(forward['queries'][i],actual)
                path=Path(evaluation_directory)/('query_%02d.json'%i);atomic(path,actual);atomic(path.with_suffix('.seal.json'),dict(binding=binding,sha256=digest(path)))
                queries.append(actual)
            queries.sort(key=lambda q:q['query_no'])
    r=dict(status='PASS_CANONICAL_'+phase+'_EVALUATION',scope=SCOPE,phase=phase,plan_binding_sha256=value_hash(plan),binding=binding,
        directory=str(run),evaluation_directory=evaluation_directory,evaluation_binding=query_binding,queries=queries,comparisons=comparisons,
        execution_order=order,actual_model_loads=observed['loads'],actual_evaluator_calls=len(observed['modes']),evaluator_modes=observed['modes'],
        environment=dict(PYTHONHASHSEED=os.environ.get('PYTHONHASHSEED'),random_seed=RANDOM_SEED,numpy_seed=RANDOM_SEED,
            process_id=os.getpid(),thread_limits={n:os.environ.get(n) for n in THREADS}),parent=parent_snapshot(parent),
        group_order_adapter_sha256=ADAPTER_SHA,coverage=phase_coverage(phase,queries,None if phase=='FORWARD' else forward),author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False)
    validate_execution(r);return r


def _phase_query_records(plan,r,parent,root=ROOT):
    validate_execution(r);phase=r['phase'];run=run_directory(plan,root);home=run/phase.lower();sqls,names=sql_identities()
    require(r['status']=='PASS_CANONICAL_'+phase+'_EVALUATION' and Path(r['directory']).resolve()==run and r['plan_binding_sha256']==value_hash(plan)
        and r['binding']==phase_binding(plan,phase) and r['parent']==plan['parent']==parent_snapshot(parent)
        and r['group_order_adapter_sha256']==ADAPTER_SHA,'canonical phase source/plan/namespace differs')
    directory=Path(r['evaluation_directory']).resolve()
    if phase=='FORWARD':
        expected=hashlib.sha256(json.dumps(r['evaluation_binding'],sort_keys=True).encode()).hexdigest()[:16]
        require(directory==home/'evaluation'/expected,'canonical forward original binding directory differs')
    else:require(directory==home/'evaluation' and r['evaluation_binding']==r['binding'],'canonical reverse directory/binding differs')
    records=query_artifacts(directory,r['evaluation_binding'],sqls,names,root)
    queries=[read(directory/('query_%02d.json'%i)) for i in range(13)]
    require(queries==r['queries'],'canonical phase report differs from complete physical queries')
    from full_ssb_replay import coverage,compare_query
    if phase=='FORWARD':
        require(r['coverage']==phase_coverage(phase,queries),'canonical actual group/CI coverage changed')
        require(not r['comparisons'] and all(q['point_error'] is None and q['ci_error'] is None for q in queries),'successful canonical forward with all errors explicit required')
        for i,q in enumerate(queries):compare_forward_query(parent['report']['queries'][i],q)
    else:
        forward=_verify_phase(plan,'FORWARD',parent,root)
        require(r['coverage']==phase_coverage(phase,queries,forward),'canonical reverse inherited truth coverage changed')
        comparisons={str(i):compare_query(forward['queries'][i],q) for i,q in enumerate(queries)}
        require(r['comparisons']==comparisons and all(q['original_query_evaluator_calls']==2 and q['model_loads']==1 for q in queries),'canonical fresh reverse actual comparisons changed')
    return records


def execute_worker(plan,phase):
    import full_ssb_local_canonical_run as runner
    require(phase in PHASES and os.environ.get('DEEPDB_SSB_CANONICAL_WORKER')=='1'
        and os.environ.get('DEEPDB_SSB_CANONICAL_PHASE')==phase and os.environ.get('PYTHONHASHSEED')==str(HASH_SEEDS[phase])
        and all(os.environ.get(n)=='1' for n in THREADS),'dedicated canonical hash/thread/phase worker required')
    runner.ops.verify_owned_job_membership(os.environ.get('DEEPDB_SSB_CANONICAL_JOB'))
    key=value_hash(plan);path=ROOT/OUTPUT/'plans'/key[:20]/'plan.json'
    require(runner.read_plan(path,digest(path))==plan and plan['dependencies']==dependency_snapshot(),'root-reviewed canonical source/runtime plan required')
    parent=collect_parent();require(parent_snapshot(parent)==plan['parent'],'fresh complete original formal parent changed')
    probe=runner.ops.operational_resources();base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'],additional_bytes=RESERVE_BYTES)
    run=run_directory(plan);home=run/phase.lower();binding=phase_binding(plan,phase)
    def validate(r):
        with native_platform():refresh_parent(parent)
        require(plan['dependencies']==dependency_snapshot(),'canonical worker source/runtime changed')
        _phase_query_records(plan,r,parent)
    try:
        r=base.formal_transaction(home/'science_control',binding,lambda:_scientific_phase(plan,phase,parent),validate,kind='CANONICAL_'+phase)
        require(not (home/'verification.json').exists() and not (home/'seal.json').exists(),'canonical phase publication cannot replace existing files')
        atomic(home/'verification.json',r)
        atomic(home/'seal.json',dict(status='PASS_CANONICAL_PHASE',phase=phase,artifacts=_phase_artifacts(plan,r,parent)))
        return r
    except BaseException as error:
        state=home/'science_control/lifecycle.json'
        if state.exists():body=read(state);body.update(status='TAINTED',reason=repr(error));atomic(state,body)
        raise


def _phase_artifacts(plan,r,parent,root=ROOT):
    home=run_directory(plan,root)/r['phase'].lower();records=_phase_query_records(plan,r,parent,root)
    control=home/'science_control';receipt=read(control/'receipt.json');life=read(control/'lifecycle.json')
    require(life['status']==receipt['status']=='PASS' and receipt['kind']=='CANONICAL_'+r['phase'] and receipt['result']==r
        and life['receipt_sha256']==digest(control/'receipt.json') and life['binding']==receipt['binding']==phase_binding(plan,r['phase']),'complete canonical scientific phase transaction required')
    require(read(home/'verification.json')==r,'canonical phase publication alias differs')
    records.extend(artifact(p,root) for p in (control/'receipt.json',control/'lifecycle.json',home/'verification.json'))
    return sorted(records,key=lambda d:d['path'])


def _verify_phase(plan,phase,parent,root=ROOT):
    home=run_directory(plan,root)/phase.lower();r=read(home/'verification.json')
    require(r['phase']==phase and read(home/'seal.json')==dict(status='PASS_CANONICAL_PHASE',phase=phase,artifacts=_phase_artifacts(plan,r,parent,root)),'canonical phase complete physical seal differs')
    return r


def root_binding(plan):
    return dict(scope=SCOPE,plan_sha256=value_hash(plan),parent=plan['parent'],dependencies_sha256=value_hash(plan['dependencies']),adapter_sha256=ADAPTER_SHA)


def report_body(plan,plan_path,parent,root=ROOT):
    forward=_verify_phase(plan,'FORWARD',parent,root);reverse=_verify_phase(plan,'REVERSE',parent,root)
    run=run_directory(plan,root);old=parent['report'];path=Path(plan_path)
    return dict(status=PASS,stage='LOCAL_SSB_SF500_CANONICAL_1M_AQP_CI',scope=SCOPE,variant='CANONICAL_PAIRED_DECODED_GROUP_ORDER',
        evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',group_order_adapter_sha256=ADAPTER_SHA,
        directory=str(run),plan=plan,plan_path=path.relative_to(root).as_posix(),plan_file_sha256=digest(path),plan_binding_sha256=value_hash(plan),
        parent=parent_snapshot(parent),parent_formal=parent['published_result'],original_mismatch=parent['original_mismatch'],
        inputs=old['inputs'],prepared_directory=old['prepared_directory'],moments_directory=str(Path(old['directory'])/'sample_moments_native'),
        truth_projection_path=str(Path(old['directory'])/'core_truth_checkpoint.json'),model_path=parent['model_path'],model_sha256=parent['model_sha256'],
        model=old['model'],spn_count=old['spn_count'],training_tables=old['training_tables'],model_training_cap_per_table=1000000,
        paper_figure11_training_budget_reproduced=False,population_rows=source.N,actual_sample_rows=source.SAMPLE_ROWS,fact_normalizer=old['fact_normalizer'],
        queries=forward['queries'],evaluation_binding=forward['evaluation_binding'],point_query_errors=0,ci_query_errors=0,
        forward=artifact(run/'forward/verification.json',root),reverse=artifact(run/'reverse/verification.json',root),
        phase_model_loads={'FORWARD':1,'REVERSE':13},phase_evaluator_calls={'FORWARD':26,'REVERSE':26},
        reverse_comparisons=reverse['comparisons'],coverage=forward['coverage'],group_order_adapter=plan['dependencies']['group_order_adapter'],
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        author_population_row_count_and_13_truths_match=False,author_full_row_byte_identity_proven=False,
        historical_reverse_accepted=False,historical_result_changed=False,preparation_executed=False,training_executed=False,moments_executed=False)


def validate_report(r,parent,root=ROOT):
    import full_ssb_local_canonical_run as runner
    path=Path(root)/r['plan_path'];p=runner.read_plan(path,r['plan_file_sha256'],root)
    require(p==r['plan'] and p['parent']==parent_snapshot(parent) and p['dependencies']==dependency_snapshot()
        and r==report_body(p,path,parent,root),'complete canonical report/current source/parent differs')
    for phase in PHASES:runner.verify_child(p,phase,root)
    return p


def complete_artifacts(r,parent,root=ROOT):
    plan=validate_report(r,parent,root);run=run_directory(plan,root);records={d['path']:d for d in parent['artifacts']}
    def add(path):
        d=artifact(path,root);records[d['path']]=d
    import full_ssb_local_canonical_run as runner
    for phase in PHASES:
        phase_report=_verify_phase(plan,phase,parent,root)
        for d in _phase_artifacts(plan,phase_report,parent,root)+runner.verify_child(plan,phase,root):records[d['path']]=d
        add(run/phase.lower()/'seal.json')
    deps=plan['dependencies']
    for d in source.environment_artifacts(deps['environment'],root):records[d['path']]=d
    require(deps['frozen_sources']==PINS and deps['canonical_sources']==code_snapshot() and deps['group_order_adapter']==artifact(Path(root)/ADAPTER,root),'exact canonical source closure changed')
    for path in list(PINS)+list(FILES)+[ADAPTER,WINDOWS_HELPER]:add(Path(root)/path)
    path=Path(root)/r['plan_path'];add(path);add(path.with_suffix('.seal.json'))
    control=run/'root_control';receipt=read(control/'receipt.json');life=read(control/'lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='CANONICAL_ROOT' and receipt['result']==r
        and life['binding']==receipt['binding']==root_binding(plan) and life['receipt_sha256']==digest(control/'receipt.json'),'whole canonical ROOT transaction missing/changed')
    for path in (control/'receipt.json',control/'lifecycle.json',run/'verification.json',Path(root)/RESULT):add(path)
    require(read(run/'verification.json')==read(Path(root)/RESULT)==r,'canonical published result aliases changed')
    return [records[p] for p in sorted(records)]


def publication_binding(r):return dict(scope=SCOPE,report_sha256=value_hash(r),root_receipt_sha256=digest(Path(r['directory'])/'root_control/receipt.json'))


def publication_links(r,root=ROOT):
    return dict(published_result_sha256=digest(Path(root)/RESULT),verification_sha256=digest(Path(r['directory'])/'verification.json'),seal_sha256=digest(Path(r['directory'])/'verification_seal.json'))


def verify_publication(r,parent,root=ROOT,require_publication=True):
    run=Path(r['directory']);records=complete_artifacts(r,parent,root)
    require(read(run/'verification_seal.json')==dict(status='PASS_CANONICAL_PUBLICATION',scope=SCOPE,artifacts=records),'canonical full required artifact set changed')
    records.append(artifact(run/'verification_seal.json',root))
    if require_publication:
        home=run/'publication_control';receipt=read(home/'receipt.json');life=read(home/'lifecycle.json')
        require(receipt['status']==life['status']=='PASS' and receipt['kind']=='CANONICAL_PUBLICATION' and life['receipt_sha256']==digest(home/'receipt.json')
            and life['binding']==receipt['binding']==publication_binding(r) and receipt['result']==publication_links(r,root),'complete canonical publication transaction required')
        records.extend(artifact(p,root) for p in (home/'receipt.json',home/'lifecycle.json'))
    require(len(records)==len({d['path'] for d in records}),'duplicate canonical artifact identity');return records


def publish_report(r,parent,root=ROOT):
    run=Path(r['directory'])
    def produce():
        require(not (Path(root)/RESULT).exists() and not (run/'verification.json').exists(),'canonical publication cannot replace previous files')
        atomic(run/'verification.json',r);atomic(Path(root)/RESULT,r)
        atomic(run/'verification_seal.json',dict(status='PASS_CANONICAL_PUBLICATION',scope=SCOPE,artifacts=complete_artifacts(r,parent,root)))
        return publication_links(r,root)
    def validate(result):
        verify_publication(r,parent,root,False);require(result==publication_links(r,root),'canonical publication links changed')
    try:return base.formal_transaction(run/'publication_control',publication_binding(r),produce,validate,kind='CANONICAL_PUBLICATION')
    except BaseException as error:
        path=run/'root_control/lifecycle.json';body=read(path);body.update(status='TAINTED',reason='canonical publication failed: '+repr(error));atomic(path,body);raise


def _verify_complete(parent,root=ROOT):
    r=read(Path(root)/RESULT);records=verify_publication(r,parent,root);run=Path(r['directory'])
    return dict(status=API_PASS,scope=SCOPE,variant=r['variant'],evaluation_variant=r['evaluation_variant'],group_order_adapter_sha256=ADAPTER_SHA,
        report=r,parent_snapshot=dict(parent,proof_method='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL'),
        published_result=artifact(Path(root)/RESULT,root),verification=artifact(run/'verification.json',root),verification_seal=artifact(run/'verification_seal.json',root),
        plan=artifact(Path(root)/r['plan_path'],root),formal_receipt=artifact(run/'root_control/receipt.json',root),formal_lifecycle=artifact(run/'root_control/lifecycle.json',root),
        artifacts=records,dependencies=r['plan']['dependencies'],model_path=r['model_path'],model_sha256=r['model_sha256'],
        sample_rows=source.SAMPLE_ROWS,population_rows=source.N,queries=r['queries'],evaluation_binding=r['evaluation_binding'],original_mismatch=r['original_mismatch'],
        parent_formal=parent['published_result'],forward=r['forward'],reverse=r['reverse'],author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,historical_reverse_accepted=False,
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False)


def verify_canonical(root=ROOT):
    require((Path(root)/RESULT).is_file(),'completed canonical publication missing')
    parent=collect_parent(root)
    return _verify_complete(parent,root)
