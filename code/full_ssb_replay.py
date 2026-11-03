"""Independent reverse replay; verify() is strictly read-only, never a runner."""
import argparse
from collections import Counter
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time
import warnings

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/full/ssb/replay'
RTOL,ATOL=1e-9,1e-5
HASH_SEED,RANDOM_SEED=173,74031
PLAN_SHA256='6c4dbad583371c8cee01f7ccd4d9045071f73273cca1f9ffb3d8138ff56a6aca'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):
    def pairs(items):
        result={}
        for name,value in items:
            if name in result:raise ValueError('Duplicate replay JSON key: '+name)
            result[name]=value
        return result
    def invalid(value):raise ValueError('Unencoded nonfinite JSON value: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def value_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temp),str(path))


def key(value):
    result=[]
    for item in value:
        if hasattr(item,'item'):item=item.item()
        if isinstance(item,float) and not math.isfinite(item):item=None
        if isinstance(item,float) and item.is_integer():item=int(item)
        result.append(item)
    return json.dumps(result,separators=(',',':'))


def group_map(groups):
    result={}
    for row in groups:
        if row.get('status')=='MISSING_MODEL_GROUP':continue
        group=key(row['key'])
        if group in result:raise ValueError('Duplicate replay group identity')
        result[group]=row
    return result


def compare_query(baseline,actual):
    if any(baseline.get(field)!=actual.get(field) for field in ('query_no','query_name','sql')):
        raise ValueError('Replay query identity/index/exactSQL mismatch')
    expected,observed=group_map(baseline['groups']),group_map(actual['groups'])
    if set(expected)!=set(observed):raise ValueError('Replay group key set missing/extra')
    differences=[];point_count=0;interval_count=0;missing_interval=0
    for group in expected:
        left,right=expected[group],observed[group]
        a,b=left['prediction'],right['prediction']
        # The frozen baseline converts all nonfinite points to None and loses
        # their NaN/Inf kind. Do not certify equality of that unrecorded state.
        if a is None or b is None:raise ValueError('Nonfinite point cannot be certified from baseline null representation')
        if not math.isfinite(a) or not math.isfinite(b):raise ValueError('Unencoded nonfinite replay point')
        if not math.isclose(a,b,rel_tol=RTOL,abs_tol=ATOL):raise ValueError('Replay point outside numerical tolerance: '+group)
        differences.append((abs(a-b),abs(a-b)/max(abs(a),abs(b),1.)));point_count+=1
        a,b=left.get('model_interval'),right.get('model_interval')
        if a is None or b is None:
            if a is not None or b is not None:raise ValueError('Replay CI missing/nonfinite state changed: '+group)
            missing_interval+=1;continue
        if len(a)!=2 or len(b)!=2:raise ValueError('Replay interval shape changed')
        for x,y in zip(a,b):
            if not math.isfinite(x) or not math.isfinite(y):raise ValueError('Unencoded nonfinite interval endpoint')
            if not math.isclose(x,y,rel_tol=RTOL,abs_tol=ATOL):raise ValueError('Replay interval outside numerical tolerance: '+group)
            differences.append((abs(x-y),abs(x-y)/max(abs(x),abs(y),1.)));interval_count+=1
    def nonfinite_map(query):
        result={}
        for row in query.get('nonfinite_original_intervals',[]):
            identity=key(row['key'])
            if identity in result:raise ValueError('Duplicate nonfinite CI group')
            result[identity]=row['raw']
        return result
    nonfinite=nonfinite_map(baseline)
    if nonfinite!=nonfinite_map(actual):raise ValueError('Replay explicit nonfinite CI pattern changed')
    return {'status':'PASS','point_values_compared':point_count,'interval_endpoints_compared':interval_count,
            'matching_missing_or_nonfinite_interval_groups':missing_interval,'matching_explicit_nonfinite_ci_groups':len(nonfinite),
            'max_absolute_difference':max((x[0] for x in differences),default=0.),
            'max_relative_difference':max((x[1] for x in differences),default=0.)}


def require_same_snapshot(before,after):
    if before!=after:raise ValueError('Model/source/dependency/physical artifact snapshot changed')


def source_snapshot():
    """Only read/hash/json operations; no model unpickle, inference or mutation."""
    import full_ssb_guard as guard
    core=guard.core;path=ROOT/'output/full/results/ssb_model_aqp_ci.json'
    report=read(path);directory=Path(report['directory']);files={}
    def add(candidate,expected=None):
        candidate=Path(candidate).resolve()
        if ROOT.resolve() not in candidate.parents:raise ValueError('Replay source outside project')
        sha=digest(candidate)
        if expected is not None and sha!=expected:raise ValueError('Source artifact checksum changed: '+str(candidate))
        files[candidate.relative_to(ROOT).as_posix()]=sha;return sha
    if (report.get('status')!='PASS' or report.get('stage')!='SSB_SF500_SINGLE_1M_AQP_CI' or
        report.get('paper_population_exact') is not True or report.get('spn_count')!=5 or
        report.get('point_query_errors')!=0 or report.get('ci_query_errors')!=0 or report['inputs']['population_rows']!=3000028242):
        raise ValueError('Formal SSB result is not a completed executable13-query run')
    plan_path=core.OUTPUT/'formal_plan.json';add(plan_path,PLAN_SHA256)
    seal=read(directory/'verification_seal.json');report_sha=add(directory/'verification.json',seal['sha256'])
    add(path,report_sha);add(directory/'verification_seal.json')
    deps=guard.dependencies()
    if report['complete_dependencies']!=deps or read(plan_path)['complete_dependencies']!=deps:
        raise ValueError('Complete original/parser/SPFlow/runtime dependencies changed')
    add(guard.__file__,report['outer_guard_source_sha256'])
    global_home=core.OUTPUT/'formal_runs'/report['plan_sha256']
    global_state=read(global_home/'lifecycle.json');global_receipt=read(global_home/'receipt.json')
    add(global_home/'receipt.json',seal['formal_outer_receipt_sha256']);add(global_home/'lifecycle.json')
    if (global_state['status']!='PASS' or global_state['receipt_sha256']!=digest(global_home/'receipt.json') or
        global_receipt['status']!='PASS' or global_receipt['result']!=report or global_receipt.get('kind')!='FORMAL' or
        global_state['binding']!=global_receipt['binding'] or report['plan_sha256']!=PLAN_SHA256 or
        global_receipt['binding']['complete_dependencies']!=deps):raise ValueError('Formal outer publication incomplete')
    expected_receipts={str(guard.home_for(directory/name,kind)/'receipt.json') for name,kind in
                       [('prepared','prepared'),('model','model'),('evaluation','evaluation')]}
    if set(report['outer_stage_receipts_sha256'])!=expected_receipts:raise ValueError('Exact3 outer stage receipt set required')
    stages={}
    for receipt_path,sha in report['outer_stage_receipts_sha256'].items():
        receipt_path=Path(receipt_path);add(receipt_path,sha);state_path=receipt_path.parent/'lifecycle.json';add(state_path)
        receipt,state=read(receipt_path),read(state_path)
        if (state['status']!='PASS' or state['receipt_sha256']!=sha or receipt['status']!='PASS' or
            state['binding']!=receipt['binding'] or receipt['binding']['dependencies']!=deps):
            raise ValueError('Prepared/model/evaluation outer lifecycle/complete dependency mismatch')
        stages[receipt['kind']]=receipt
    if set(stages)!= {'PREPARED','MODEL','EVALUATION'}:raise ValueError('Outer stage kinds are incomplete')
    prepared=directory/'prepared';prepared_seal=read(prepared/'seal.json')
    artifact=stages['PREPARED']['result']['core_input_artifacts']
    recorded=artifact['prepared_files_sha256']
    required={'meta_data.pkl','binding.json'}|{name+'.hdf' for name in ('lineorder','dwdate','customer','part','supplier')}
    if (not required.issubset(recorded) or prepared_seal['files_sha256']!=recorded or
        {p.name for p in prepared.glob('*.hdf')}!={name for name in recorded if name.endswith('.hdf')}):
        raise ValueError('Prepared full/unmatched HDF inventory missing/extra')
    add(prepared/'seal.json',stages['PREPARED']['result']['core_seal_sha256'])
    for name,sha in recorded.items():add(prepared/name,sha)
    for table,entry in report['inputs']['files'].items():
        if artifact['raw_files'][table]['sha256']!=entry['sha256']:raise ValueError('Prepared raw hash binding changed')
        add(entry['path'],entry['sha256'])
    for name,field in [('output/full/results/ssb_paper.json','generation_result_sha256'),
                       ('output/full/ssb/paper/sf500/checkpoint.json','checkpoint_sha256'),
                       ('data/ssb/sf500_paper/dimensions/dimensions.json','dimension_receipt_sha256'),
                       ('output/full/ssb/paper/sf500_plan.json','generation_plan_sha256')]:add(ROOT/name,report['inputs'][field])
    model_path=Path(report['model_path']);model=read(model_path.parent/'model.json')
    if stages['MODEL']['result']!=model:raise ValueError('Model outer/core report mismatch')
    expected_training={'lineorder':1000000,'dwdate':2556,'customer':1000000,'part':1000000,'supplier':1000000}
    if (model['binding']['samples_per_spn']!=1000000 or
        {r['table']:r['actual_training_rows'] for r in report['training_tables']}!=expected_training or
        report['evaluation_binding']['confidence_sample_size']!=report['inputs']['sample_rows']):
        raise ValueError('Formal1M training and actual CI fact sample sizes must remain separate')
    guard.verify_core_model(model)  # Pure read-only verification, unlike reject_tainted/require_*.
    add(model_path,report['model_sha256'])
    core_model_guard=read(model_path.parent/'model_guard.json');add(model_path.parent/'model_guard.json',report['input_artifact_guard_sha256'])
    for name,sha in core_model_guard['model_files_sha256'].items():add(model_path.parent/name,sha)
    identities=guard.query_bundle(report['evaluation_directory'],report['evaluation_binding'])
    evaluation=stages['EVALUATION']['result']
    if evaluation['identities']!=identities or evaluation['queries']!=report['queries']:raise ValueError('Final exact13 query identity/result changed')
    sqls=core.SQL_PATH.read_text().splitlines()
    if len(sqls)!=13 or len(report['queries'])!=13:raise ValueError('Exactly13 released queries required')
    for index,(query,sql) in enumerate(zip(report['queries'],sqls)):
        if (query['query_no'],query['query_name'],query['sql'])!=(index,core.QUERY_NAMES[index],sql):raise ValueError('Formal exactSQL/index/name mismatch')
        qpath=Path(report['evaluation_directory'])/('query_%02d.json'%index)
        add(qpath,identities[index]['result_sha256']);add(qpath.with_suffix('.seal.json'),identities[index]['core_seal_sha256'])
        if read(qpath)!=query:raise ValueError('Formal summary/per-query content differs')
    moments=directory/'sample_moments_native';moment_seal=read(moments/'seal.json')
    add(moments/'moments.json',moment_seal['sha256']);add(moments/'moments.tsv',moment_seal['tsv_sha256']);add(moments/'seal.json')
    if read(moments/'moments.json')['sample_rows']!=report['inputs']['sample_rows']:raise ValueError('CI fact sample size mismatch')
    return {'formal_result_sha256':report_sha,'model_sha256':report['model_sha256'],'dependencies':deps,
            'dependencies_sha256':value_hash(deps),'files_sha256':files,'population_rows':3000028242,
            'fact_sample_rows':report['inputs']['sample_rows'],'training_rows':{x['table']:x['actual_training_rows'] for x in report['training_tables']}}


def coverage(report):
    rows=[r for q in report['queries'] for r in q['groups']]
    truth_rows=[r for r in rows if r['status']!='EXTRA_MODEL_GROUP']
    model_rows=[r for r in rows if r['status']!='MISSING_MODEL_GROUP']
    return {'truth_groups_total':sum(q['truth_groups'] for q in report['queries']),
            'model_groups_total':sum(q['model_groups'] for q in report['queries']),
            'missing_model_groups_total':sum(q['missing_model_groups'] for q in report['queries']),
            'extra_model_groups_total':sum(q['extra_model_groups'] for q in report['queries']),
            'nonfinite_point_groups':sum(r['prediction'] is None for r in model_rows),
            'nonfinite_original_ci_groups':sum(len(q['nonfinite_original_intervals']) for q in report['queries']),
            'missing_or_nonfinite_model_interval_groups':sum(r['model_interval'] is None for r in model_rows),
            'zero_truth_groups':sum(r['zero_truth'] for r in truth_rows),
            'reference_ci_eligible_truth_groups':sum(r['reference_ci']['eligible'] for r in truth_rows),
            'reference_ci_excluded_truth_groups':sum(not r['reference_ci']['eligible'] for r in truth_rows),
            'reference_ci_status_counts_all_union':dict(Counter(r['reference_ci']['status'] for r in rows))}


def execute_query(index,sql,name,model_path,sample_rows):
    import numpy as np
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.utils import parse_query
    from full_factor_cache import model_aware_factor_cache
    ensemble=read_ensemble(str(model_path),build_reverse_dict=True);query=parse_query(sql,ensemble.schema_graph)
    arguments={'rdc_spn_selection':False,'merge_indicator_exp':False,'max_variants':5,'exploit_overlapping':False}
    def scalar(value):
        value=float(np.asarray(value).reshape(-1)[0]);return value if math.isfinite(value) else None
    with model_aware_factor_cache():
        ensemble.cached_expecation_vals={};started=time.perf_counter()
        _,predicted=ensemble.evaluate_query(query,confidence_intervals=False,**arguments);point_seconds=time.perf_counter()-started
        ensemble.cached_expecation_vals={};started=time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            intervals,ci_predictions=ensemble.evaluate_query(query,confidence_intervals=True,confidence_sample_size=sample_rows,**arguments)
        ci_seconds=time.perf_counter()-started
    points={};bounds={};nonfinite=[]
    if query.group_bys:
        for row in predicted:
            identity=key(row[:-1])
            if identity in points:raise ValueError('Duplicate replay evaluator group')
            points[identity]=scalar(row[-1])
        ci_predictions=list(ci_predictions)
        ci_keys=[key(row[:-1]) for row in ci_predictions]
        if len(set(ci_keys))!=len(ci_keys) or set(ci_keys)!=set(points):
            raise ValueError('Point/CI group identity sets differ in fresh replay')
        if intervals is not None:
            intervals=list(intervals)
            if len(ci_predictions)!=len(intervals):raise ValueError('CI prediction/interval lengths differ in fresh replay')
            for identity,interval in zip(ci_keys,intervals):
                pair=[scalar(x) for x in interval]
                if None in pair:nonfinite.append({'key':json.loads(identity),'raw':repr(interval)});bounds[identity]=None
                else:bounds[identity]=pair
    elif not isinstance(predicted,list) or predicted:
        points[key([])]=scalar(predicted)
        if intervals is not None:
            pair=[scalar(x) for x in intervals]
            if None in pair:nonfinite.append({'key':[],'raw':repr(intervals)});bounds[key([])]=None
            else:bounds[key([])]=pair
    result={'query_no':index,'query_name':name,'sql':sql,'groups':[{'key':json.loads(identity),'prediction':value,
            'model_interval':bounds.get(identity)} for identity,value in sorted(points.items())],
            'nonfinite_original_intervals':nonfinite,'ci_warnings':list(dict.fromkeys(str(w.message) for w in caught)),
            'point_seconds':point_seconds,'ci_seconds':ci_seconds,'original_query_evaluator_calls':2,'model_loads':1}
    del ensemble;gc.collect();return result


def worker():
    import numpy as np
    before=source_snapshot();binding={'source_snapshot_sha256':value_hash(before),'replay_source_sha256':digest(__file__),
            'relative_tolerance':RTOL,'absolute_tolerance':ATOL,'hash_seed':HASH_SEED,'random_seed':RANDOM_SEED}
    home=OUTPUT/'runs'/value_hash(binding);home.parent.mkdir(parents=True,exist_ok=True)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise ValueError('Prior replay namespace exists; no automatic rerun or failure washing') from error
    state=home/'lifecycle.json'
    atomic(state,{'status':'RUNNING','binding':binding})
    atomic(OUTPUT/'last_run.json',{'status':'RUNNING','directory':str(home),'binding':binding})
    try:
        if os.environ.get('PYTHONHASHSEED')!=str(HASH_SEED):raise ValueError('Fresh replay must have explicit recorded hash seed')
        np.random.seed(RANDOM_SEED);random.seed(RANDOM_SEED)
        baseline=read(ROOT/'output/full/results/ssb_model_aqp_ci.json');comparisons={};files={};started=time.perf_counter()
        for index in reversed(range(13)):
            expected=baseline['queries'][index]
            actual=execute_query(index,expected['sql'],expected['query_name'],baseline['model_path'],baseline['inputs']['sample_rows'])
            comparison=compare_query(expected,actual);path=home/('query_%02d.json'%index)
            atomic(path,{'actual':actual,'comparison':comparison})
            atomic(path.with_suffix('.seal.json'),{'binding':binding,'query_no':index,'exact_sql_sha256':hashlib.sha256(expected['sql'].encode()).hexdigest(),'sha256':digest(path)})
            comparisons[str(index)]=comparison
        require_same_snapshot(before,source_snapshot())
        for path in home.glob('query_*.json'):files[path.name]=digest(path)
        result={'status':'PASS_INDEPENDENT_REVERSE_REPLAY_CURRENT_DEPENDENCIES','stage':'SSB_SF500_FORMAL_REVERSE_REPLAY',
                'source_snapshot':before,'binding':binding,'directory':str(home),'execution_order':list(reversed(range(13))),
                'queries':13,'original_query_evaluator_calls':26,'model_loads':13,'comparisons':comparisons,
                'query_files_sha256':files,'coverage':coverage(baseline),'wall_seconds':time.perf_counter()-started,
                'environment':{'PYTHONHASHSEED':os.environ.get('PYTHONHASHSEED'),'random_seed':RANDOM_SEED,
                    'numpy_seed':RANDOM_SEED,'process_id':os.getpid(),'hash_probe':hash('DeepDB SSB independent replay'),
                    'thread_limits':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
                    'baseline_hash_environment':'Not recorded by the frozen runner; no claim to recover its process hash secret'},
                'scope':'Independent behavior replay only. Missing/extra/nonfinite/excluded-CI groups remain explicit; this PASS is not complete AQP/CI coverage.'}
        atomic(home/'verification.json',result)
        seal={'report_sha256':digest(home/'verification.json'),'binding':binding,'query_files_sha256':files}
        atomic(home/'verification_seal.json',seal);atomic(state,{'status':'PASS','binding':binding,'report_sha256':seal['report_sha256']})
        atomic(OUTPUT/'verification.json',result);atomic(OUTPUT/'verification_seal.json',seal)
        atomic(OUTPUT/'last_run.json',{'status':'PASS','directory':str(home),'report_sha256':seal['report_sha256']})
        return result
    except BaseException as error:
        atomic(state,{'status':'FAIL','binding':binding,'error':repr(error)})
        atomic(OUTPUT/'last_run.json',{'status':'FAIL','directory':str(home),'binding':binding,'error':repr(error)});raise


def verify():
    """Strict read-only acceptance. Missing evidence fails; never run a fallback."""
    path=OUTPUT/'verification.json';result=read(path);seal=read(OUTPUT/'verification_seal.json')
    binding=result['binding'];home=Path(result['directory']);state=read(home/'lifecycle.json')
    if (seal.get('report_sha256')!=digest(path) or seal.get('binding')!=binding or
        binding.get('replay_source_sha256')!=digest(__file__) or state.get('status')!='PASS' or
        state.get('report_sha256')!=digest(path) or state.get('binding')!=binding or
        digest(home/'verification.json')!=digest(path) or read(home/'verification_seal.json')!=seal):
        raise ValueError('Replay final self/source/lifecycle seal changed')
    if (result.get('status')!='PASS_INDEPENDENT_REVERSE_REPLAY_CURRENT_DEPENDENCIES' or result.get('queries')!=13 or
        result.get('original_query_evaluator_calls')!=26 or result.get('model_loads')!=13 or
        result.get('execution_order')!=list(reversed(range(13))) or binding.get('hash_seed')!=HASH_SEED or
        binding.get('relative_tolerance')!=RTOL or binding.get('absolute_tolerance')!=ATOL or
        binding.get('random_seed')!=RANDOM_SEED or result['environment'].get('PYTHONHASHSEED')!=str(HASH_SEED) or
        result['environment'].get('random_seed')!=RANDOM_SEED or result['environment'].get('numpy_seed')!=RANDOM_SEED):
        raise ValueError('Replay completion/environment contract changed')
    require_same_snapshot(result['source_snapshot'],source_snapshot())
    if binding['source_snapshot_sha256']!=value_hash(result['source_snapshot']):raise ValueError('Replay source snapshot binding changed')
    required={'query_%02d'%index+suffix for index in range(13) for suffix in ('.json','.seal.json')}
    if (set(result['query_files_sha256'])!=required or seal['query_files_sha256']!=result['query_files_sha256'] or
        {p.name for p in home.glob('query_*.json')}!=required):raise ValueError('Exact26 replay query artifact set required')
    baseline=read(ROOT/'output/full/results/ssb_model_aqp_ci.json')
    for index in range(13):
        path=home/('query_%02d.json'%index);qseal=read(path.with_suffix('.seal.json'));query=read(path)
        for candidate in (path,path.with_suffix('.seal.json')):
            if digest(candidate)!=result['query_files_sha256'][candidate.name]:raise ValueError('Replay query artifact checksum changed')
        if (qseal['binding']!=binding or qseal['query_no']!=index or qseal['sha256']!=digest(path) or
            qseal['exact_sql_sha256']!=hashlib.sha256(baseline['queries'][index]['sql'].encode()).hexdigest()):
            raise ValueError('Replay per-query identity/seal changed')
        expected=compare_query(baseline['queries'][index],query['actual'])
        if query['comparison']!=expected or result['comparisons'][str(index)]!=expected:raise ValueError('Replay numeric comparison changed')
    if result['coverage']!=coverage(baseline):raise ValueError('Replay coverage/gap counters changed')
    return result


def replay():
    """Explicit execution entry; existing accepted evidence is only verified."""
    if (OUTPUT/'verification.json').exists():return verify()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    environment=dict(os.environ,PYTHONHASHSEED=str(HASH_SEED),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    logs=OUTPUT/'logs';logs.mkdir(exist_ok=True);stem=str(time.time_ns())+'_'+digest(__file__)[:16]
    stdout,stderr=logs/(stem+'.stdout.log'),logs/(stem+'.stderr.log')
    with stdout.open('xb') as out,stderr.open('xb') as err:
        result=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B',__file__,'worker'],cwd=str(ROOT),env=environment,stdout=out,stderr=err)
    atomic(OUTPUT/'last_process.json',{'returncode':result.returncode,'stdout':str(stdout),'stderr':str(stderr),'replay_source_sha256':digest(__file__)})
    if result.returncode:raise RuntimeError('Independent reverse replay failed; retained worker logs and FAIL namespace: '+str(stderr))
    return verify()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['replay','worker','verify'])
    args=parser.parse_args();result={'replay':replay,'worker':worker,'verify':verify}[args.action]()
    print(json.dumps({field:result[field] for field in ('status','queries','coverage') if field in result}))
