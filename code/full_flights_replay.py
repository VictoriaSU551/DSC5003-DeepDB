"""Explicit once-only reverse Flights point/CI replay; audit is strictly read-only."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import pickle
import random
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/full/flights-replay'
FORMAL=ROOT/'output/full/flights/model_formal_validation.json'
FORMAL_SHA='65914e4ad6a6fd2b0dea606455c867b97059d35fef636c14b9aeb7d15f4e98c1'
MODEL_SHA='29a09e9ffc928288f192dbec3946eb03e04179e6310e825c820a8b78715ec0fc'
EVALUATION_SHA='991b670b5a7241ce8465a4f8522d7247b8919c1d0f46f41f5106776e482168a7'
PROTOCOL='flights_original_defaults_reverse_point_ci_strict331_v1'
POPULATION=1000000000
SAMPLE=9997912
LIMIT=2*1024**3
RTOL,ATOL=1e-9,1e-7
THREADS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS')
NAMES=('F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2')
DEFAULTS=dict(rdc_spn_selection=False,pairwise_rdc_path=None,dry_run=False,merge_indicator_exp=True,
    max_variants=10,exploit_overlapping=False,debug=False,display_intermediate_results=False,
    exploit_incoming_multipliers=True,confidence_intervals=False,confidence_sample_size=None,return_expectation=False)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):result.update(block)
    return result.hexdigest()


def record(path,root=ROOT):
    path,root=Path(path).resolve(),Path(root).resolve()
    return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=sha(path))


def read_json(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=unique)


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


def seal(value):
    value={key:item for key,item in value.items() if key!='receipt_sha256'}
    return dict(value,receipt_sha256=digest(value))


def require_seal(value):
    if not isinstance(value,dict) or value.get('receipt_sha256')!=digest({k:v for k,v in value.items() if k!='receipt_sha256'}):
        raise ValueError('Replay receipt self-seal differs')


def validate_assets(assets,root=ROOT):
    root=Path(root).resolve()
    if not isinstance(assets,list) or not assets:raise ValueError('Asset map is empty')
    seen=set()
    for item in assets:
        relative=Path(item['path']);path=(root/relative).resolve()
        if relative.is_absolute() or root not in path.parents or item['path'] in seen:
            raise ValueError('Duplicate or escaping artifact path')
        seen.add(item['path'])
        if not path.is_file() or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            raise ValueError('Sealed artifact hash/size mismatch: '+str(path))


def canonical_key(values):
    import numpy as np
    if not isinstance(values,(tuple,list)):raise ValueError('Group key must be an explicit sequence')
    result=[]
    for value in values:
        if isinstance(value,np.generic):value=value.item()
        if isinstance(value,bool) or not isinstance(value,(str,int,float,type(None))):raise ValueError('Invalid group key type')
        if isinstance(value,float):
            if not math.isfinite(value):raise ValueError('Nonfinite group key')
            if value.is_integer():value=int(value)
        result.append(value)
    return tuple(result)


def unique_rows(rows,name):
    if not isinstance(rows,list) or not rows:raise ValueError(name+' rows are empty')
    result={}
    for row in rows:
        key=canonical_key(row['key'])
        if key in result:raise ValueError(name+' duplicate group key')
        result[key]=row
    return result


def scalar(value):
    import numpy as np
    array=np.asarray(value)
    if array.size!=1 or array.dtype.kind not in 'iuf':raise ValueError('Expected one numeric scalar, not a flattened vector')
    result=float(array.reshape(-1)[0])
    if not math.isfinite(result):raise ValueError('Nonfinite prediction or interval')
    return result


def normalize_raw(predicted,intervals,width,expected_keys,with_ci):
    keys=[canonical_key(key) for key in expected_keys]
    if not keys or len(set(keys))!=len(keys) or any(len(key)!=width for key in keys):
        raise ValueError('Expected group keys are empty, duplicate or wrong width')
    if width:
        if not isinstance(predicted,(tuple,list)) or not predicted:raise ValueError('Grouped prediction rows missing')
        if any(not isinstance(row,(tuple,list)) or len(row)!=width+1 for row in predicted):raise ValueError('Grouped prediction row width differs')
        raw=[(canonical_key(row[:width]),scalar(row[-1])) for row in predicted]
    else:
        raw=[((),scalar(predicted))]
    if len({key for key,_ in raw})!=len(raw):raise ValueError('Duplicate raw prediction group key')
    if len(raw)!=len(keys) or {key for key,_ in raw}!=set(keys):raise ValueError('Raw prediction groups differ from full expected set')
    if with_ci:
        if not isinstance(intervals,(tuple,list)) or len(intervals)!=(len(raw) if width else 2):
            raise ValueError('Prediction and CI interval lengths differ')
        pairs=intervals if width else [intervals]
        for pair in pairs:
            if not isinstance(pair,(tuple,list)) or len(pair)!=2:raise ValueError('Interval must have exactly two endpoints')
    else:
        if intervals is not None:raise ValueError('Point-only call unexpectedly returned intervals')
        pairs=[None]*len(raw)
    result={}
    for index,(key,value) in enumerate(raw):
        pair=None if pairs[index] is None else [scalar(endpoint) for endpoint in pairs[index]]
        if pair is not None and pair[0]>pair[1]:raise ValueError('Interval endpoint order differs')
        result[key]=dict(prediction=value,interval=pair)
    return result


def require_defaults(function):
    actual={name:parameter.default for name,parameter in inspect.signature(function).parameters.items() if name not in ('self','query')}
    if actual!=DEFAULTS:raise ValueError('Original evaluate_query default parameter contract differs')


def require_sql_reference(sql,reference_sql,truth_sql):
    from full_inventory import sql_tokens
    if sql!=reference_sql or sql_tokens(sql)!=sql_tokens(truth_sql):
        raise ValueError('Byte-exact reference SQL or token-exact truth SQL differs')
    return dict(sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                truth_sql_sha256=hashlib.sha256(truth_sql.encode()).hexdigest(),truth_sql_byte_equal=sql==truth_sql)


def require_grid(rows,workload):
    if len(workload)!=12 or len(rows)!=12 or [row['query_no'] for row in rows]!=list(reversed(range(12))):
        raise ValueError('Replay must contain exactly twelve reverse queries')
    expected={q['query_no']:q for q in workload}
    if set(expected)!=set(range(12)):raise ValueError('Workload query identities are incomplete/duplicate')
    for row in rows:
        if any(row.get(key)!=value for key,value in expected[row['query_no']].items()):raise ValueError('Exact replay SQL/query identity differs')
        if not row.get('groups') or len(row['groups'])!=expected[row['query_no']]['expected_groups']:
            raise ValueError('Replay group rows differ from the separate expected group count')
        if [call.get('confidence_intervals') for call in row.get('actual_calls',[])]!=[False,True]:
            raise ValueError('Exactly point and CI successful calls are required per SQL')


def make_query_record(identity,calls,groups,maximum):
    if 'groups' in identity or not groups or len(groups)!=identity['expected_groups']:
        raise ValueError('Expected group count and raw group rows must be separate')
    return dict(identity,actual_calls=calls,groups=groups,maximum_relative_difference=maximum)


def claim_namespace(directory,binding):
    directory=Path(directory)
    directory.parent.mkdir(parents=True,exist_ok=True)
    directory.mkdir()  # Atomic cross-process claim. Never overwrite/recover an incomplete claim.
    write_json(directory/'claim.json',seal(dict(binding=binding,claimed_pid=os.getpid(),claimed_utc=datetime.now(timezone.utc).isoformat())))


def claim_worker(directory,configuration_sha256):
    claim=read_json(Path(directory)/'claim.json');require_seal(claim)
    if claim['binding']!=dict(configuration_sha256=configuration_sha256,model_sha256=MODEL_SHA):
        raise ValueError('Worker configuration claim differs')
    with (Path(directory)/'worker_started.json').open('x',encoding='utf-8') as stream:
        json.dump(seal(dict(configuration_sha256=configuration_sha256,pid=os.getpid(),parent_pid=os.getppid(),
                            utc=datetime.now(timezone.utc).isoformat())),stream,indent=2)
        stream.flush();os.fsync(stream.fileno())


def source_records():
    import spn
    paths=[]
    for folder in ['aqp_spn','rspn','ensemble_creation','ensemble_compilation','data_preparation','schemas']:
        paths.extend((ROOT/'code'/folder).rglob('*.py'))
    for name in ['full_flights_replay.py','full_flights_model.py','full_flights_model_run.py','full_common.py',
                 'full_factor_cache.py','full_inventory.py','evaluation/utils.py','evaluation/confidence_interval_evaluation.py',
                 'full_cpp_scale.py','full_cpp.py','full_cpp_range_adapter.py']:
        paths.append(ROOT/'code'/name)
    spn_root=Path(spn.__file__).resolve().parent
    return [record(path) for path in sorted(set(paths))], [record(path,spn_root) for path in sorted(spn_root.rglob('*.py'))],str(spn_root)


def inputs():
    import full_flights_model as original
    from ensemble_compilation.spn_ensemble import SPNEnsemble
    require_defaults(SPNEnsemble.evaluate_query)
    if sha(FORMAL)!=FORMAL_SHA:raise ValueError('Original formal receipt SHA differs')
    formal=read_json(FORMAL)
    if formal.get('validation_sha256')!=original.binding_hash({k:v for k,v in formal.items() if k!='validation_sha256'}):
        raise ValueError('Original formal self-seal differs')
    if len(formal['artifacts'])!=33:raise ValueError('Original thirty-three artifact set differs')
    validate_assets(formal['artifacts'])
    evaluation_path=ROOT/formal['evaluation_path'];evaluation=read_json(evaluation_path)
    trained=read_json(ROOT/formal['model_receipt']);prepared=trained['prepared']
    for item,stage in [(prepared,'prepare'),(trained,'model'),(evaluation,'evaluation')]:
        if item['status']!='PASS' or item['binding']!=original.binding_hash(item['binding_details']) or item['binding_details']['code']!=original.stage_code_seal(stage):
            raise ValueError('Frozen prepared/model/evaluation binding differs')
        validate_assets(item['artifacts'])
    model_path=ROOT/trained['model_path']
    if (sha(model_path)!=MODEL_SHA or sha(evaluation_path)!=EVALUATION_SHA or formal['population_rows']!=POPULATION
            or evaluation['population_rows']!=POPULATION or trained['population_rows']!=POPULATION
            or formal['actual_training_rows']!=SAMPLE or evaluation['actual_training_rows']!=SAMPLE
            or trained['actual_training_rows']!=SAMPLE or evaluation['query_errors']!=0
            or evaluation['binding_details']['model_binding']!=trained['binding']):
        raise ValueError('Original model/population/sample/evaluation identity differs')
    sql_path=original.SQL_PATH;sqls=sql_path.read_text().splitlines()
    truth_path=ROOT/prepared['source']['truth_path'];truth=read_json(truth_path)
    if (not truth['complete'] or truth['population_rows']!=POPULATION or len(sqls)!=12
            or len(evaluation['queries'])!=12 or len(truth['queries'])!=12
            or sha(truth_path)!=evaluation['binding_details']['truth_sha256']
            or sha(sql_path)!=evaluation['binding_details']['sql_sha256']):raise ValueError('Original twelve SQL/truth identity differs')
    workload=[];references={}
    for index,sql in enumerate(sqls):
        ref,actual_truth=evaluation['queries'][index],truth['queries'][index]
        identity=dict(query_no=index,query_name=NAMES[index],sql=sql,
                      **require_sql_reference(sql,ref['sql'],actual_truth['sql']))
        if any(ref.get(key)!=value or actual_truth.get(key)!=value for key,value in identity.items() if key in ('query_no','query_name')):
            raise ValueError('Exact original SQL/query name/number differs')
        ref_map=unique_rows(ref['groups'],'original evaluation');truth_map=unique_rows(actual_truth['groups'],'population truth')
        if set(ref_map)!=set(truth_map) or len(ref_map)!=ref['model_groups'] or len(ref_map)!=ref['truth_groups']:
            raise ValueError('Original stored group set/count differs')
        width=int(original.query_spec(sql)['group'] is not None)
        for key,row in ref_map.items():
            if len(key)!=width or row['status']!='MATCHED' or row['model_interval'] is None:raise ValueError('Original group shape/status differs')
            scalar(row['prediction']);pair=row['model_interval']
            if len(pair)!=2 or scalar(pair[0])>scalar(pair[1]):raise ValueError('Original interval shape/order differs')
            from fractions import Fraction
            exact=float(Fraction(truth_map[key]['numerator'],truth_map[key]['denominator']))
            if row['truth']!=exact:raise ValueError('Original truth value differs')
        references[index]=ref_map;workload.append(dict(identity,group_width=width,expected_groups=len(ref_map)))
    if sum(len(rows) for rows in references.values())!=331:raise ValueError('Exactly331 stored groups are required')
    sources,spn_sources,spn_root=source_records()
    packages={}
    for name in ['numpy','pandas','scipy','networkx','scikit-learn','SPFlow','statsmodels','tables','h5py','joblib','numba','llvmlite']:
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    config=dict(protocol=PROTOCOL,formal_receipt=record(FORMAL),original_artifacts=formal['artifacts'],
        model=record(model_path),evaluation=record(evaluation_path),sql=record(sql_path),truth=record(truth_path),
        sources=sources,spflow_sources=spn_sources,spflow_root=spn_root,runtime=dict(python=sys.version,executable=record(sys.executable),packages=packages),
        default_parameters=DEFAULTS,population=POPULATION,actual_training_rows=SAMPLE,workload=workload,
        order=list(reversed(range(12))),rtol=RTOL,atol=ATOL,random_seed=1,numpy_seed=1,hash_seed='0',threads=1,
        memory_limit_bytes=LIMIT,point_kwargs=dict(confidence_intervals=False),ci_kwargs=dict(confidence_intervals=True,confidence_sample_size=SAMPLE))
    return config,workload,references


def original_stamps(config):
    return {row['path']:(ROOT/row['path']).stat().st_mtime_ns for row in [config['formal_receipt']]+config['original_artifacts']}


def compare_group_results(point,ci,reference):
    if not point or set(point)!=set(ci) or set(point)!=set(reference):raise ValueError('Three-way group map is empty or incomplete')
    rows=[];maximum=0.
    for key in sorted(reference,key=repr):
        p,c,ref=point[key]['prediction'],ci[key]['prediction'],reference[key]['prediction']
        pairs=[(p,c),(p,ref),(c,ref)]
        pairs.extend((ci[key]['interval'][i],reference[key]['model_interval'][i]) for i in range(2))
        if any(not math.isclose(a,b,rel_tol=RTOL,abs_tol=ATOL) for a,b in pairs):
            raise ValueError('Point/CI point/reference prediction or interval differs for '+repr(key))
        relative=max(abs(a-b)/max(abs(b),ATOL) for a,b in pairs)
        maximum=max(maximum,relative)
        rows.append(dict(key=list(key),point_prediction=p,ci_prediction=c,original_prediction=ref,
                         replay_interval=ci[key]['interval'],original_interval=reference[key]['model_interval'],
                         maximum_relative_difference=relative))
    return rows,maximum


@contextmanager
def prohibit_stages():
    import builtins
    import io
    import numpy as np
    import pandas as pd
    import full_flights_model as original
    from aqp_spn.aqp_spn import AQPSPN
    saved=[]
    def forbidden(*args,**kwargs):raise AssertionError('Replay must never prepare/train/generate/rebuild moments')
    for module,names in [(original,['load_generated_input','prepare_input','train_model','evaluate_model','sample_moments']),
                         (AQPSPN,['learn']),(np,['load']),(pd,['read_csv','read_hdf'])]:
        for name in names:saved.append((module,name,getattr(module,name)));setattr(module,name,forbidden)
    def guarded_open(function):
        def call(path,*args,**kwargs):
            if isinstance(path,(str,bytes,os.PathLike)) and Path(os.fsdecode(path)).suffix.lower() in {'.csv','.hdf','.h5','.npy'}:
                return forbidden()
            return function(path,*args,**kwargs)
        return call
    for module in (builtins,io):
        saved.append((module,'open',module.open));module.open=guarded_open(module.open)
    try:yield
    finally:
        for module,name,function in saved:setattr(module,name,function)


def rng_digest():
    import numpy as np
    return dict(python=hashlib.sha256(pickle.dumps(random.getstate(),protocol=4)).hexdigest(),
                numpy=hashlib.sha256(pickle.dumps(np.random.get_state(),protocol=4)).hexdigest())


def worker(directory):
    directory=Path(directory).resolve()
    if OUT not in directory.parents:raise ValueError('Worker directory escapes replay namespace')
    expected=read_json(directory/'input_binding.json')
    if directory.name!='model_'+MODEL_SHA[:16]+'_'+digest(expected)[:16]:raise ValueError('Worker namespace identity differs')
    claim_worker(directory,digest(expected))
    config,workload,references=inputs()
    if expected!=config or os.environ.get('PYTHONHASHSEED')!='0' or any(os.environ.get(key)!='1' for key in THREADS):
        raise ValueError('Worker actual source/runtime/seed/thread binding differs')
    import numpy as np
    from ensemble_compilation.spn_ensemble import read_ensemble,SPNEnsemble
    from evaluation.utils import parse_query
    from full_factor_cache import model_aware_factor_cache
    random.seed(1);np.random.seed(1)
    before=original_stamps(config);rows=[];all_calls=[];current={}
    original_call=SPNEnsemble.evaluate_query;signature=inspect.signature(original_call)
    def actual_call(self,query,**kwargs):
        effective=signature.bind(self,query,**kwargs);effective.apply_defaults()
        parameters={key:value for key,value in effective.arguments.items() if key not in ('self','query')}
        started=time.perf_counter_ns();result=original_call(self,query,**kwargs)
        all_calls.append(dict(current,confidence_intervals=kwargs['confidence_intervals'],passed_kwargs=kwargs,
                              effective_parameters=parameters,successful_wall_ns=time.perf_counter_ns()-started))
        return result
    SPNEnsemble.evaluate_query=actual_call
    rng_before=rng_digest();model_loads=0
    try:
        with prohibit_stages(),model_aware_factor_cache():
            ensemble=read_ensemble(str(ROOT/config['model']['path']),build_reverse_dict=True);model_loads+=1
            if len(ensemble.spns)!=1 or ensemble.spns[0].full_join_size!=POPULATION or ensemble.spns[0].full_sample_size!=SAMPLE or len(ensemble.spns[0].column_names)!=10:
                raise ValueError('Reloaded physical model population/sample/column identity differs')
            if ensemble.spns[0].use_generated_code:raise ValueError('Original Flights model unexpectedly uses generated native code')
            for index in reversed(range(12)):
                identity=workload[index];current=dict(query_no=index,query_name=identity['query_name'],sql_sha256=identity['sql_sha256'])
                maps={};start_calls=len(all_calls)
                for mode,kwargs in [('point',config['point_kwargs']),('ci',config['ci_kwargs'])]:
                    ensemble.cached_expecation_vals={}
                    parsed=parse_query(identity['sql'],ensemble.schema_graph)
                    intervals,predictions=ensemble.evaluate_query(parsed,**kwargs)
                    maps[mode]=normalize_raw(predictions,intervals,identity['group_width'],list(references[index]),mode=='ci')
                groups,maximum=compare_group_results(maps['point'],maps['ci'],references[index])
                row=make_query_record(identity,all_calls[start_calls:],groups,maximum)
                rows.append(row)
                write_json(directory/('query_%02d.json'%index),seal(row))
                print('FLIGHTS_REVERSE_POINT_CI_PASS',index,identity['query_name'],len(groups),flush=True)
    finally:SPNEnsemble.evaluate_query=original_call
    rng_after=rng_digest()
    require_grid(rows,workload)
    if inputs()[0]!=config or before!=original_stamps(config):raise ValueError('Protected artifacts/source/runtime changed during replay')
    result=seal(dict(status='PASS_FRESH_REVERSE_12_POINT_CI_24_SUCCESSFUL_CALLS',protocol=PROTOCOL,
        binding=digest(config),configuration=config,rows=rows,queries=12,groups=331,successful_evaluate_calls=len(all_calls),
        physical_model_loads=model_loads,fresh_pid=os.getpid(),parent_pid=os.getppid(),
        actual_hash_seed=os.environ.get('PYTHONHASHSEED'),hash_fingerprints={key:hash(key) for key in ['flights','F1.1','F5.2','origin_state_abr']},
        random_seed=1,numpy_seed=1,rng_before=rng_before,rng_after=rng_after,rng_unchanged=rng_before==rng_after,
        actual_threads={key:os.environ[key] for key in THREADS},maximum_relative_difference=max(row['maximum_relative_difference'] for row in rows),
        original_artifacts_unchanged=True,original_mtimes_before=before,original_mtimes_after=original_stamps(config),
        sample_parsed=False,population_read=False,trained=False,ci_formula_modified=False,
        inference_sample_access_guard='CSV/HDF/NPY opens and numpy.load/pandas.read_csv/read_hdf prohibited during real model inference',
        full_paper_complete=False))
    write_json(directory/'replay_result.json',result)
    return result


def run_guarded(arguments,directory,memory_limit=LIMIT):
    from full_cpp_scale import WindowsOwnedMemory
    directory=Path(directory);stdout=directory/'worker.stdout.log';stderr=directory/'worker.stderr.log'
    env=dict(os.environ,PYTHONHASHSEED='0',**{key:'1' for key in THREADS})
    started=time.perf_counter();peak=0;stopped=False
    with stdout.open('wb') as output,stderr.open('wb') as errors:
        process=subprocess.Popen([str(arg) for arg in arguments],cwd=str(ROOT),env=env,
            stdout=output,stderr=errors,creationflags=0x08000000|0x20)
        monitor=WindowsOwnedMemory(process.pid)
        try:
            while process.poll() is None:
                peak=max(peak,monitor.sample())
                if peak>memory_limit:stopped=True;monitor.terminate();process.wait(timeout=15);break
                time.sleep(.1)
            returncode=process.wait()
        except BaseException:monitor.terminate();process.wait(timeout=15);raise
        finally:names=dict(monitor.names);monitor.close()
    result=seal(dict(returncode=returncode,elapsed_seconds=time.perf_counter()-started,peak_tree_rss_bytes=peak,
        memory_limit_bytes=memory_limit,stopped_for_memory=stopped,owned_processes=names,monitor_interval_seconds=.1,
        scope='Owned worker and observed descendants only; stable process handles',priority='Normal',
        actual_env={key:env[key] for key in ('PYTHONHASHSEED',)+THREADS},arguments=[str(arg) for arg in arguments]))
    write_json(directory/'resource.json',result)
    return result


def launch_worker(directory):
    return run_guarded([sys.executable,'-B',str(Path(__file__).resolve()),'_worker','--directory',str(directory)],directory)


def audit_directory(directory,current_config=None):
    directory=Path(directory).resolve()
    if OUT not in directory.parents:raise ValueError('Audit directory escapes replay namespace')
    result=read_json(directory/'verification.json');require_seal(result)
    if result.get('status')!='SEALED_FLIGHTS_REVERSE_POINT_CI_PASS':raise ValueError('Replay final status differs')
    expected=[item['path'] for item in result['artifacts']]
    actual={path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file() and path!=directory/'verification.json'}
    if not expected or len(set(expected))!=len(expected) or set(expected)!=actual:raise ValueError('Replay artifact namespace map is empty or incomplete')
    validate_assets(result['artifacts'],directory)
    config,workload,references=inputs()
    if current_config is not None and config!=current_config:raise ValueError('Requested replay input binding differs')
    replay=read_json(directory/'replay_result.json');require_seal(replay)
    if result['configuration']!=config or replay['configuration']!=config or result['binding']!=digest(config) or replay['binding']!=digest(config):
        raise ValueError('Current source/runtime/model/artifact binding differs')
    require_grid(replay['rows'],workload)
    if (replay['status']!='PASS_FRESH_REVERSE_12_POINT_CI_24_SUCCESSFUL_CALLS' or replay['queries']!=12
            or replay['groups']!=331 or sum(len(row['groups']) for row in replay['rows'])!=331
            or replay['maximum_relative_difference']!=max(row['maximum_relative_difference'] for row in replay['rows'])
            or sum(len(row['actual_calls']) for row in replay['rows'])!=24):raise ValueError('Replay aggregate counts/status differ')
    for row in replay['rows']:
        index=row['query_no'];group_map=unique_rows(row['groups'],'replayed')
        snapshot=read_json(directory/('query_%02d.json'%index));require_seal(snapshot)
        if {key:value for key,value in snapshot.items() if key!='receipt_sha256'}!=row:raise ValueError('Per-query successful call snapshot differs')
        point={key:dict(prediction=item['point_prediction'],interval=None) for key,item in group_map.items()}
        ci={key:dict(prediction=item['ci_prediction'],interval=item['replay_interval']) for key,item in group_map.items()}
        rebuilt,maximum=compare_group_results(point,ci,references[index])
        if rebuilt!=row['groups'] or maximum!=row['maximum_relative_difference']:raise ValueError('Stored comparison rows differ')
        for mode,call in enumerate(row['actual_calls']):
            kwargs=config['point_kwargs'] if mode==0 else config['ci_kwargs'];effective=dict(DEFAULTS,**kwargs)
            if (call['passed_kwargs']!=kwargs or call['effective_parameters']!=effective or call['successful_wall_ns']<=0
                    or any(call[key]!=row[key] for key in ['query_no','query_name','sql_sha256'])):
                raise ValueError('Actual successful call parameter/identity contract differs')
    resource=read_json(directory/'resource.json');require_seal(resource)
    started=read_json(directory/'worker_started.json');require_seal(started)
    if (resource['returncode'] or resource['stopped_for_memory'] or resource['peak_tree_rss_bytes']<=0
            or resource['peak_tree_rss_bytes']>LIMIT or resource['memory_limit_bytes']!=LIMIT
            or replay['successful_evaluate_calls']!=24 or replay['physical_model_loads']!=1
            or replay['original_mtimes_before']!=replay['original_mtimes_after']
            or original_stamps(config)!=replay['original_mtimes_after'] or replay['actual_hash_seed']!='0'
            or replay['actual_threads']!={key:'1' for key in THREADS}
            or started['pid']!=replay['fresh_pid'] or started['parent_pid']!=replay['parent_pid']
            or started['configuration_sha256']!=digest(config)
            or str(replay['fresh_pid']) not in resource['owned_processes']):raise ValueError('Replay process/resource/preservation gate differs')
    return dict(status='PASS_READ_ONLY_FLIGHTS_REVERSE_AUDIT',queries=12,groups=331,successful_prior_calls=24,
        actual_new_predictions=0,verification=record(directory/'verification.json'),model_sha256=MODEL_SHA,
        maximum_relative_difference=replay['maximum_relative_difference'],resource=resource)


def audit():
    outer_path=OUT/'final_seal.json';outer=read_json(outer_path);require_seal(outer)
    if outer.get('status')!='SEALED_FLIGHTS_REVERSE_POINT_CI_WITH_READ_ONLY_AUDIT':raise ValueError('Final replay namespace seal differs')
    expected=[item['path'] for item in outer['artifacts']]
    actual={path.relative_to(OUT).as_posix() for path in OUT.rglob('*') if path.is_file() and path!=outer_path}
    if not expected or len(set(expected))!=len(expected) or set(expected)!=actual:raise ValueError('Final replay namespace artifact set differs')
    validate_assets(outer['artifacts'],OUT);validate_assets(outer['sources'])
    pointer=read_json(OUT/'latest.json');require_seal(pointer)
    path=(ROOT/pointer['path']).resolve()
    if OUT not in path.parents or sha(path)!=pointer['sha256']:raise ValueError('Replay final pointer differs')
    return dict(audit_directory(path.parent),final_seal_sha256=sha(outer_path))


def replay():
    config,_,_=inputs();directory=OUT/('model_'+MODEL_SHA[:16]+'_'+digest(config)[:16])
    if (directory/'verification.json').is_file():return dict(audit_directory(directory,config),reused_verified_replay=True)
    claim_namespace(directory,dict(configuration_sha256=digest(config),model_sha256=MODEL_SHA))
    write_json(directory/'input_binding.json',config)
    snapshot=directory/'source_snapshot';snapshot.mkdir()
    for name in ['code/full_flights_replay.py','code/tests/test_full_flights_replay.py','docs/FULL_FLIGHTS_REPLAY.md']:
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
    before=original_stamps(config);resource=launch_worker(directory)
    if resource['returncode'] or resource['stopped_for_memory']:raise RuntimeError('Replay failed/capped; namespace preserved: '+str(directory))
    result=read_json(directory/'replay_result.json');require_seal(result)
    if result['configuration']!=config or inputs()[0]!=config or before!=original_stamps(config):raise ValueError('Final replay input/artifact preservation differs')
    assets=[record(path,directory) for path in sorted(directory.rglob('*')) if path.is_file()]
    final=seal(dict(status='SEALED_FLIGHTS_REVERSE_POINT_CI_PASS',protocol=PROTOCOL,binding=digest(config),configuration=config,
        resource=resource,queries=12,groups=331,actual_successful_calls=24,artifacts=assets,
        original_formal_artifacts=33,original_artifacts_unchanged=True,full_paper_complete=False))
    write_json(directory/'verification.json',final)
    checked=audit_directory(directory,config)
    write_json(OUT/'latest.json',seal(dict(status='PASS',path=(directory/'verification.json').relative_to(ROOT).as_posix(),sha256=sha(directory/'verification.json'))))
    return dict(checked,reused_verified_replay=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['replay','audit','_worker'])
    parser.add_argument('--directory',type=Path);args=parser.parse_args()
    result=worker(args.directory) if args.action=='_worker' else replay() if args.action=='replay' else audit()
    print(json.dumps({key:value for key,value in result.items() if key not in ('configuration','rows')},sort_keys=True))


if __name__=='__main__':main()
