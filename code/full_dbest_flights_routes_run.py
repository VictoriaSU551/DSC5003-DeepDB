"""Independent original1D DBEst routes; only explicit reviewed actions execute."""
import argparse
import ast
from contextlib import contextmanager
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pickle
import random
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import types
import warnings
import full_dbest_flights_routes as routes

DATA_UNPICKLER=pickle.Unpickler

sys.dont_write_bytecode=True
ROOT=routes.ROOT
OUT=ROOT/'output/full/dbest_flights_routes'
DATA=ROOT/'data/dbest_flights_routes'
PRIVATE=ROOT/'.venv-dbest/Scripts/python.exe'
SAMPLE=ROOT/'data/flights/generated/flights-1b/sample.csv'
MEMORY=512*1024**2
MAX_SECONDS=900
COMMON_PINS={
 'code/full_ssb_native_model_run.py':'117b507a95c9333828e7d0069327d9771395e5fd42a62bc398862059a78d23f0',
 'code/full_ssb_native_model.py':'7c50feb8d9248ae5f8bfc7f29aac39d86ecc687b38c407ca380fb3bef4558312'}
SOURCES=('code/full_dbest_flights_routes.py','code/full_dbest_flights_routes_run.py','code/full_dbest_flights_routes_audit.py',
    'code/tests/test_full_dbest_flights_routes.py','code/tests/test_full_dbest_flights_routes_run.py','code/tests/test_full_dbest_flights_routes_audit.py','docs/FULL_DBEST_FLIGHTS_ROUTES.md')
FROZEN={
 'code/full_dbest.py':'8fe1269a2601aad2f981c44800b63d8a70d65c0cbad5dd6a05d01c966aefad0a',
 'code/full_dbest_flights.py':'2c690c33c8b875a9794addaf2143f2b6e1d8f0e2da145cef9a5da4ee13e54073',
 'code/full_dbest_flights_audit.py':'9029a1732bd312e3fbea902ae1480119dbba159b210429f96512dfb651651cc8',
 'code/benchmarks/flights/sql/aqp_queries.sql':'5400031e656041bbe2d374d40a68b6817196c7ca777100dbfeaf666efa70c823',
 'data/dbest_flights/selection_seal.json':'1e8b32da2f2a78ed9f291f1ddc30937bd6e984aa241340b301b53b2e7ba5cceb',
 'output/full/dbest/numerical_failure_F1.2_all.json':'3fe06d26087b4f59f5e5ad87a4d54e44289970995dca6579d773aef3dad555c0',
 'output/full/dbest/source_binding.json':'0570c0ef54dbb22e07fbe3b8158069418271621058fc7f042566cef12f6d58f3'}
ORIGINAL_BACKEND='PINNED_ORIGINAL_DBESTPY_PUBLIC_API'
COLUMNS=('YEAR_DATE','UNIQUE_CARRIER','ORIGIN','ORIGIN_STATE_ABR','DEST','DEST_STATE_ABR','DEP_DELAY','TAXI_OUT','TAXI_IN','ARR_DELAY','AIR_TIME','DISTANCE')


def population_spec(name):
    require(name in ('GOLDEN_200K','FORMAL_1B'),'Known sealed population required')
    if name=='FORMAL_1B':
        return dict(name=name,population_rows=routes.N,retained_rows=routes.RETAINED,fit_rows=routes.FIT_ROWS,seed=routes.SEED,
            probability=dict(routes.PROBABILITY),sample=dict(path='data/flights/generated/flights-1b/sample.csv',bytes=582074363,sha256=routes.SAMPLE_SHA),
            selection=dict(path='data/dbest_flights/selected_rows.pkl',sha256=routes.SELECTION_PICKLE_SHA),row_ids_sha256=routes.IDS_SHA,
            truth=dict(path='output/full/flights/flights-1b/ground_truth.json',format='EXACT_RATIONAL_12_SQL'),scope='NEW_1D_ROUTES_ORIGINAL_1B_POPULATION')
    return dict(name=name,population_rows=200000,retained_rows=200000,fit_rows=20000,seed=74031,probability=dict(numerator=1,denominator=1),
        sample=dict(path='data/flights/generated/golden-200k/original.csv',bytes=11643759,sha256='c9df154be75aebc047ce7c11c5efc55c2e81e13b85e5b2a5fc26f219d312992d'),
        selection=dict(path='data/dbest/training_selection.json',sha256='dda62e197accba5901df1ad7b70a6bcee9150d1ce83b2682366f11a94b49800d'),
        truth=dict(path='output/full/flights/golden-200k/sqlite_exact_state.json',sha256='06d09e947538441dc4478bf012f4de11319c862756b32af1baa4e3670a29a744',format='SEALED_SQLITE_INTEGER_AGGREGATES'),
        validation=dict(path='output/full/flights/golden-200k/golden_validation.json',sha256='d857d47ba93595c25c70bac1dde11022658ba46b0ddd35def50970381488ddff'),
        row_ids_sha256=routes.value_hash(sorted(random.Random(74031).sample(range(200000),20000))),scope='ORIGINAL_200K_SMALL_GOLDEN_ONLY_NOT_1B')


def selection_ids(population):
    record=population['selection'];require(digest(ROOT/record['path'])==record['sha256'],'Population-specific frozen selection changed')
    if population['name']=='FORMAL_1B':return selected_rows()['row_ids']
    body=strict_read(ROOT/record['path']);ids=body['row_ids_zero_based']
    require(body['seed']==74031 and ids==sorted(random.Random(74031).sample(range(200000),20000)) and routes.value_hash(ids)==population['row_ids_sha256'],'Exact original200K seed74031 IDs required')
    return ids


def golden_truth(state):
    require([(q['query_no'],q['query_name']) for q in state['aggregates']]==list(zip(range(12),routes.QUERY_NAMES)),'Complete ordered golden12 SQL truth required')
    queries=[]
    for i,item in enumerate(state['aggregates']):
        groups=[]
        for g in item['groups']:
            require(type(g['sum']) is int and type(g['count']) is int and g['count']>=0,'Exact golden integer sum/count required')
            numerator=g['count'] if i in (2,3,4,8,9) else g['sum']
            denominator=1 if i in (2,3,4,8,9) else 10*g['count'] if i in (0,1,7) else 100 if i==10 else 10
            require(denominator>0,'NULL golden AVG must remain unsupported, never zero-filled')
            groups.append(dict(key=g['key'],numerator=numerator,denominator=denominator))
        queries.append(dict(query_no=i,query_name=routes.QUERY_NAMES[i],sql=routes.SQLS[i],groups=groups))
    return dict(complete=True,population_rows=200000,queries=queries)


def read_truth(population):
    data=strict_read(ROOT/population['truth']['path'])
    return golden_truth(data) if population['name']=='GOLDEN_200K' else data


def require(value,message):routes.require(value,message)


def limits():return dict(process_rss_bytes=MEMORY,wall_seconds=MAX_SECONDS,new_output_bytes=100*1024**2,minimum_available_ram_bytes=1024**3,minimum_free_disk_bytes=512*1024**2)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def strict_read(path):
    def pairs(values):
        result={}
        for k,v in values:require(k not in result,'Duplicate JSON key');result[k]=v
        return result
    def invalid(v):raise ValueError('Nonfinite JSON literal '+v)
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def safe_json(value):
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite_float':repr(value)}
    if isinstance(value,dict):return {k:safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe_json(v) for v in value]
    return value


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(safe_json(value),f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(str(temporary),str(path))


def descriptor(path):
    path=Path(path).resolve();require(ROOT.resolve() in path.parents and path.is_file(),'Project artifact required')
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=digest(path))


def load_module(path,name,expected):
    require(digest(path)==expected,'Frozen delegated source differs before import: '+str(path))
    spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def source_proof():
    for name,sha in FROZEN.items():require(digest(ROOT/name)==sha,'Frozen original dependency changed: '+name)
    old=load_module(ROOT/'code/full_dbest_flights_audit.py','routes_original_final_audit',FROZEN['code/full_dbest_flights_audit.py'])
    evidence=old.verify() # This is a later explicitly requested complete file audit, never import-time.
    require(evidence['verified_native_calls']==76 and evidence['unique_fit_rows']==20000 and evidence['population_rows']==routes.N,'Frozen original scientific evidence changed')
    return {k:evidence[k] for k in ('complete_inventory_sha256','files_sha256','source_report_sha256','frozen_wrapper_sha256','verified_native_calls','unique_fit_rows','population_rows')}


def runtime_snapshot():
    cfg=ROOT/'.venv-dbest/pyvenv.cfg';require(PRIVATE.is_file() and cfg.is_file(),'Existing isolated original DBEst runtime required; no install/repair')
    values={k.strip():v.strip() for k,v in (line.split('=',1) for line in cfg.read_text().splitlines() if '=' in line)};base=Path(values['home']).resolve()
    require(ROOT.resolve() in base.parents and base.is_dir(),'Project-local base interpreter required')
    roots=[ROOT/'.venv-dbest',base];records={}
    for root in roots:
        for p in root.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() not in ('.pyc','.pyo'):records[p.relative_to(ROOT).as_posix()]=descriptor(p)
    require(bool(records),'Nonempty independent actual runtime set required')
    return records


def selected_rows():
    path=ROOT/'data/dbest_flights/selected_rows.pkl';require(digest(path)==routes.SELECTION_PICKLE_SHA,'Frozen20K selection changed before unpickle')
    class PrimitiveOnly(DATA_UNPICKLER):
        def find_class(self,module,name):raise ValueError('Only fixed primitive selected-row data may be unpickled')
    with path.open('rb') as f:data=PrimitiveOnly(f).load()
    routes.validate_selected(data,formal=True);return data


def own_snapshot():
    for p,sha in COMMON_PINS.items():require(digest(ROOT/p)==sha,'Pinned shared Windows ownership source differs')
    return {p:descriptor(ROOT/p) for p in SOURCES+tuple(COMMON_PINS)}


def training_identity(catalog,official_sources,runtime,population=None,route_sources=None):
    # Evaluation/parent result hashes belong to evidence plans, never this
    # scientific identity or the features/labels/count metadata passed to fit.
    p=population or population_spec('FORMAL_1B')
    return dict(population=p['name'],selection_sha256=p['selection']['sha256'],row_ids_sha256=p['row_ids_sha256'],seed=p['seed'],
        category_catalog_sha256=routes.value_hash(catalog),official_sources=official_sources,runtime=runtime,route_sources=route_sources or {},
        model_configuration=dict(base_models=['LR'],kernel='gaussian',bandwidth=1.,dimensions=1,n_cores=1,feature_labels='Same scalar original-unit projection'))


class _Boundary:
    def __init__(self):
        self.source=source_proof();self.own=own_snapshot();self.runtime=runtime_snapshot()


def validate_golden_gate(report):
    require(report.get('population')=='GOLDEN_200K' and set(report.get('native_verified_aggregates',[]))=={'sum','avg'} and
        report.get('numerical_validation_failures')==0 and type(report.get('native_calls')) is int and report['native_calls']>0,
        'Actual original SUM and AVG golden with verified integrals required before formal routes')


def _plan_from_boundary(kind,catalog_final,boundary,population_name='FORMAL_1B',golden_final=None):
    require(type(boundary) is _Boundary,'Private same-entry complete dependency proof required')
    require(kind in ('CATALOG','ROUTES'),'Known independent plan kind required')
    population=population_spec(population_name);ids=selection_ids(population)
    routes.validate_sqls((ROOT/'code/benchmarks/flights/sql/aqp_queries.sql').read_text().splitlines())
    inputs={population['selection']['path']:descriptor(ROOT/population['selection']['path']),population['truth']['path']:descriptor(ROOT/population['truth']['path'])}
    # The original frozen auditor has freshly hashed the formal CSV. Golden
    # bytes are separately hashed; neither preflight parses categorical rows.
    raw=ROOT/population['sample']['path'];require(raw.is_file() and raw.stat().st_size==population['sample']['bytes'],'Sealed raw sample size differs')
    if population_name=='GOLDEN_200K':require(digest(raw)==population['sample']['sha256'],'Pinned original200K raw CSV bytes differ')
    else:require(boundary.source['files_sha256'].get(population['sample']['path'])==population['sample']['sha256'],'Actual parent proof must include the formal raw sample')
    inputs[population['sample']['path']]=dict(population['sample'])
    for key in ('truth','validation'):
        if key in population and 'sha256' in population[key]:
            r=population[key];require(digest(ROOT/r['path'])==r['sha256'],'Pinned population truth/validation differs');inputs[r['path']]=descriptor(ROOT/r['path'])
    if 'validation' in population:
        validation=strict_read(ROOT/population['validation']['path']);require(validation['status']=='PASS' and validation['population_rows']==200000,'Old200K golden input not accepted')
    cfg={k.strip():v.strip() for k,v in (line.split('=',1) for line in (ROOT/'.venv-dbest/pyvenv.cfg').read_text().splitlines() if '=' in line)}
    base=Path(cfg['home'])/'python.exe'
    body=dict(schema='dbest_flights_routes_plan_v1',kind=kind,source=boundary.source,own_sources=boundary.own,runtime=boundary.runtime,support=routes.support_table(),
        population=population,population_inputs=inputs,limits=limits(),base_python=descriptor(base),private_python=descriptor(PRIVATE),
        original_four_classes_reexecuted=False,original_training_configuration_recovered=False)
    if kind=='ROUTES':
        require(catalog_final is not None,'Completed separately approved catalog required')
        import full_dbest_flights_routes_audit as audit
        catalog=audit._verify_catalog_from_boundary(catalog_final,boundary);body['catalog_final']=descriptor(catalog_final);body['catalog']=catalog['catalog']
        require(catalog['population']==population,'Catalog belongs to a different population/selection/seed')
        selected=selected_rows() if population_name=='FORMAL_1B' else strict_read(Path(catalog_final).parent/'selected_rows.json')
        routes.validate_selected(selected);require(selected['row_ids']==ids,'Same frozen population selection required')
        body['jobs']=routes.make_jobs(selected,body['catalog'])
        source=strict_read(ROOT/'output/full/dbest/source_binding.json')
        body['training_identity']=training_identity(body['catalog'],source,boundary.runtime,population,{k:boundary.own[k] for k in SOURCES[:3]})
        body['training_binding_sha256']=routes.value_hash(body['training_identity'])
        if population_name=='FORMAL_1B':
            require(golden_final is not None and Path(golden_final).name=='final.json','Separately completed approved200K routes golden final required')
            golden=audit._verify_from_boundary(Path(golden_final).parent,boundary);validate_golden_gate(golden)
            body['golden_final']=descriptor(golden_final)
    return dict(body,binding_sha256=routes.value_hash(body))


def plan(kind,catalog_final=None,population='FORMAL_1B',golden_final=None):
    return _plan_from_boundary(kind,catalog_final,_Boundary(),population,golden_final)


def verify_plan(body):
    return _verify_plan_from_boundary(body,_Boundary())


def _verify_plan_from_boundary(body,boundary):
    require(body.get('schema')=='dbest_flights_routes_plan_v1' and body.get('kind') in ('CATALOG','ROUTES'),'Complete frozen route plan required')
    actual=_plan_from_boundary(body['kind'],None if body['kind']=='CATALOG' else ROOT/body['catalog_final']['path'],boundary,body['population']['name'],
        ROOT/body['golden_final']['path'] if 'golden_final' in body else None)
    require(actual==body,'Plan/source/runtime/fixed20K/catalog changed');return body


def exact_approval(path,sha,binding=None,kind=None):
    require(path and sha and Path(path).is_file() and digest(path)==sha,'Exact ROOT approval bytes required before source/fit/scan')
    body=strict_read(path)
    if binding is not None:require(body.get('status')=='APPROVED_DBEST_ROUTES_'+kind and body.get('binding_sha256')==binding and
        body.get('limits')==limits(),'ROOT plan/kind/resource approval differs')
    return body


def compatibility_record(lower,upper,bandwidth):
    spacing=4.*bandwidth;count=math.ceil((upper-lower)/spacing)
    points=[lower+spacing*i for i in range(1,count) if lower+spacing*i<upper]
    return dict(kind='Original scipy.quad points/limit only',breakpoints=len(points),
        source_failure=descriptor(ROOT/'output/full/dbest/numerical_failure_F1.2_all.json'),
        source_failure_scope='Previously verified original200K failure; not a new native failure')


class OriginalAPI:
    """Only actual public original classes; no repair-capable helper loader."""
    BACKEND=ORIGINAL_BACKEND
    def __init__(self,seed):
        require(Path(sys.executable).resolve()==PRIVATE.resolve(),'Fresh isolated original DBEst interpreter required')
        require(all(os.environ.get(k)=='1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')),'One-thread environment required')
        binding=strict_read(ROOT/'output/full/dbest/source_binding.json');source=ROOT/'data/dbest/source'
        for name,sha in binding['files_sha256'].items():require(digest(source/name)==sha,'Pinned official source byte changed before import')
        sys.path.insert(0,str(source))
        import numpy as np
        from dbest.qreg import CRegression
        from dbest.query_engine import QueryEngine
        from dbest import logs,tools
        self.np,self.CRegression,self.QueryEngine,self.logs,self.tools=np,CRegression,QueryEngine,logs,tools
        require(seed in (74031,74131),'Population-specific fixed seed required');random.seed(seed);np.random.seed(seed)
        self.failure=ROOT/'output/full/dbest/numerical_failure_F1.2_all.json'
        require(strict_read(self.failure)['integral_verified'] is False,'Preserved old actual quadrature failure required for compatibility adapter')
    def fit(self,job,path):
        logger=self.logs.QueryLogs(log=str(path.with_name('engine.log')));logger.set_no_output()
        training=self.tools.DataSource();training.features=self.np.asarray(job['xs'],dtype=float).reshape(-1,1);training.labels=self.np.asarray(job['xs'],dtype=float)
        training.headers=['X','Y'];training.file=job['job_id'];started=time.perf_counter()
        regression=self.CRegression(logger_object=logger,base_models=[self.tools.app_linear],n_cores=1);regression.fit(training)
        engine=self.QueryEngine(regression,logger_object=logger,num_training_points=job['population_metadata']['Nhat'],b_print_time_cost=False);engine.density_estimation()
        model=regression.apps_deployed[0];details=dict(slope=float(model.coef_[0]),intercept=float(model.intercept_),bandwidth=float(engine.kde.bandwidth),seconds=time.perf_counter()-started)
        require(all(math.isfinite(details[k]) for k in ('slope','intercept','bandwidth','seconds')) and details['bandwidth']==1.,'Actual original LR/Gaussian configuration differs')
        temporary=path.with_name(path.name+'.tmp')
        with temporary.open('xb') as f:pickle.dump(engine,f,protocol=4);f.flush();os.fsync(f.fileno())
        os.replace(str(temporary),str(path));return engine,details
    def invoke(self,engine,job,lower,upper):
        started=time.perf_counter();module=sys.modules[engine.__class__.__module__];integrator=module.integrate;score=engine.kde.score_samples
        stats=dict(api_calls=0,kde_calls=0,kde_evaluations=0);spacing=4.*float(engine.kde.bandwidth);count=math.ceil((upper-lower)/spacing)
        require(count<=10000,'Uniform quadrature breakpoint budget exceeded')
        points=[lower+spacing*i for i in range(1,count) if lower+spacing*i<upper]
        def quad(function,a,b,**options):
            options.update(points=points,limit=max(50,2*len(points)+50));return integrator.quad(function,a,b,**options)
        def scored(values):stats['kde_calls']+=1;stats['kde_evaluations']+=len(values);return score(values)
        value=None;error=None
        try:
            module.integrate=types.SimpleNamespace(quad=quad,nquad=integrator.nquad);engine.kde.score_samples=scored
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always');stats['api_calls']+=1
                try:value,unused=getattr(engine,'approximate_'+job['aggregate']+'_from_to')(lower,upper,0,epsabs=1e-8,epsrel=1e-8)
                except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
                messages=list(dict.fromkeys(str(w.message) for w in caught))
            return dict(stats,value=None if value is None else float(value),seconds=time.perf_counter()-started,warnings=messages,error=error,
                compatibility_adapter=compatibility_record(lower,upper,float(engine.kde.bandwidth)))
        finally:module.integrate=integrator;engine.kde.score_samples=score


def execute_job(job,driver,home,binding):
    """One unmodified original public API call, or a preserved explicit gap."""
    home=Path(home);home.mkdir(parents=True,exist_ok=False);atomic(home/'request.json',dict(job=job,binding=binding))
    (home/'engine.log').touch(exist_ok=False)
    result=dict(query_no=job['query_no'],key=job['key'],component=job['component'],parent_sql_sha256=job['parent_sql_sha256'],
        job=job,backend=driver.BACKEND,fit_attempted=bool(job['xs']),estimate=None,status='UNAVAILABLE_FIXED_SAMPLE',integral_verified=False,
        native=dict(api_calls=0,kde_calls=0,kde_evaluations=0,seconds=0.,value=None,error=None),oracle=None)
    fit=dict(status='NOT_ATTEMPTED_EMPTY_FIXED_SAMPLE',attempted=False)
    if job['xs']:
        try:
            engine,details=driver.fit(job,home/'model.pkl');fit=dict(details,status='PASS',attempted=True,model_sha256=digest(home/'model.pkl'),
                training_binding_sha256=routes.value_hash(dict(job_binding=job['binding_sha256'],training_binding=binding.get('training_binding_sha256','PURE_FAKE_FIXTURE'))))
        except Exception as error:
            fit=dict(status='FIT_ERROR',attempted=True,error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()));result['status']='FIT_ERROR'
        else:
            lower,upper=min(job['xs'])-12.,max(job['xs'])+12.;result['lower']=lower;result['upper']=upper
            if math.ceil((upper-lower)/(4.*fit['bandwidth']))>10000:result['status']='NUMERICAL_BUDGET_UNSUPPORTED'
            else:
                native=driver.invoke(engine,job,lower,upper);result['native']=native
                require(native['api_calls']==1,'Exactly one original SUM/AVG invocation required')
                oracle=routes.gaussian_oracle(job['xs'],fit['slope'],fit['intercept'],fit['bandwidth'],lower,upper,job['population_metadata']['Nhat']);result['oracle']=oracle
                value=native['value'];result['estimate']=value
                if native['error'] is not None:result['status']='NATIVE_ERROR'
                elif value is None:result['status']='NATIVE_NULL'
                elif type(value) not in (int,float) or not math.isfinite(value):result.update(status='NATIVE_NONFINITE',estimate=None,nonfinite_value=repr(value))
                else:
                    expected=oracle[job['aggregate']];passed=expected is not None and abs(value-expected)<=max(1e-5,abs(expected)*1e-5)
                    result.update(status='RETURNED' if passed else 'NUMERICAL_VALIDATION_FAILED',integral_verified=passed,
                        oracle_absolute_error=None if expected is None else abs(value-expected))
    atomic(home/'fit.json',fit);atomic(home/'native.json',result['native']);atomic(home/'result.json',result)
    atomic(home/'result.seal.json',{'sha256':digest(home/'result.json'),'request_sha256':digest(home/'request.json')})
    return result


def job_name(token):
    require(isinstance(token,str) and len(token)==32 and all(c in '0123456789abcdef' for c in token),'Exact owned job token required')
    return 'Local\\DeepDB_DBEST_ROUTES_'+token


def bootstrap_command(body,home,review_sha,token):
    return [ROOT/body['base_python']['path'],'-B',ROOT/'code/full_dbest_flights_routes_run.py','_bootstrap',
        '--plan',Path(home)/'plan.json','--review',Path(home)/'review.json','--review-sha256',review_sha,'--home',home,'--token',token]


def worker_command(body,home,review_sha,token):
    return [PRIVATE,'-B',ROOT/'code/full_dbest_flights_routes_run.py','_worker',
        '--plan',Path(home)/'plan.json','--review',Path(home)/'review.json','--review-sha256',review_sha,'--home',home,'--token',token]


def worker_identity(plan,home,review_sha,token):
    env={k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE')}
    env.update(PYTHONHASHSEED=str(plan['population']['seed']),MPLBACKEND='Agg',MPLCONFIGDIR=str(Path(home)/'auxiliary/matplotlib'))
    return dict(executable=str(PRIVATE),command=list(map(str,worker_command(plan,home,review_sha,token))),environment=env,
        absent_environment=['PYTHONPATH','PYTHONHOME','PYTHONSTARTUP'])


def validate_execution(home,plan,controller,worker,resource):
    cap=limits();token=controller['token'];expected=list(map(str,bootstrap_command(plan,home,controller['review_sha256'],token)))
    require(controller.get('status')=='PASS' and controller.get('command')==expected and controller.get('worker_command')==list(map(str,worker_command(plan,home,controller['review_sha256'],token))) and
        controller.get('job_name')==job_name(token) and controller.get('exit_code')==0 and controller.get('reason') is None and
        type(controller.get('seconds')) in (int,float) and math.isfinite(controller['seconds']) and 0<=controller['seconds']<=cap['wall_seconds']+15 and
        controller.get('owned_job_assigned_before_go') is True and controller.get('live_owned_descendants_after_exit')==[],
        'Exact owned bootstrap/private-worker command, completion and resource ownership required')
    require(worker.get('status')=='PASS' and worker.get('kind')==plan['kind'] and worker.get('binding_sha256')==plan['binding_sha256'] and
        worker.get('owned_job_verified') is True and worker.get('go_verified') is True and worker.get('original_prior_classes_reexecuted') is False and
        type(worker.get('process_id')) is int and worker['process_id']>0 and type(worker.get('worker_peak_bytes')) is int and 0<worker['worker_peak_bytes']<=MEMORY,
        'Actual worker phase/ownership/peak contract differs')
    require(resource.get('limits')==cap and type(resource.get('minimum_available_ram_at_start_bytes')) is int and resource['minimum_available_ram_at_start_bytes']>=cap['minimum_available_ram_bytes'] and
        type(resource.get('free_disk_at_start_bytes')) is int and resource['free_disk_at_start_bytes']>=cap['minimum_free_disk_bytes'] and bool(resource['samples']),'Startup/resource history missing')
    previous=-1.
    for sample in resource['samples']:
        require(type(sample.get('monotonic')) in (int,float) and math.isfinite(sample['monotonic']) and sample['monotonic']>=max(0,previous) and
            all(type(sample.get(k)) is int and 0<=sample[k]<=cap[c] for k,c in [('owned_rss_bytes','process_rss_bytes'),('own_output_bytes','new_output_bytes')]),'Resource sample/time cap differs')
        previous=sample['monotonic']
    require(resource['peak_owned_rss_bytes']==max(s['owned_rss_bytes'] for s in resource['samples']) and
        resource['peak_output_bytes']==max(s['own_output_bytes'] for s in resource['samples']),'Actual sampled owned resource peaks differ')
    if 'population' in plan:
        require(worker.get('identity')==worker_identity(plan,home,controller['review_sha256'],token),'Actual private interpreter/argv/thread environment differs')


def scan_category_file(path,expected_rows,expected_sha,expected_bytes,probability=None,selection_ids=None,with_selection=False):
    probability=probability or dict(routes.PROBABILITY)
    ids=[] if selection_ids is None else selection_ids
    routes.validate_selected(dict(row_ids=ids,rows=[{} for unused in ids]));wanted=set(ids);selected=[];seen=0
    h=hashlib.sha256();seen_bytes=0;started=time.perf_counter()
    with Path(path).open('rb') as f:
        def lines():
            nonlocal seen_bytes
            for raw in f:
                h.update(raw);seen_bytes+=len(raw);yield raw.decode('utf-8')
        reader=csv.DictReader(lines());require(tuple(reader.fieldnames or ())==COLUMNS,'Exact original12 CSV columns required')
        def rows():
            nonlocal seen
            for index,row in enumerate(reader):
                require(set(row)==set(COLUMNS) and all(isinstance(v,str) for v in row.values()),'Complete unmodified raw CSV fields required')
                require(all(v!='' for v in row.values()),'Empty-string raw CSV NULL encoding has not been verified; refuse ambiguous input')
                if index in wanted:selected.append(dict(row))
                seen+=1
                # No numeric parsing/value accumulation here: only null-state
                # membership and the explicitly declared year category predicate.
                yield row
        catalog=routes.build_catalog(rows(),probability['numerator'],probability['denominator'],expected_rows)
    require(h.hexdigest()==expected_sha and seen_bytes==expected_bytes,'Same-pass retained CSV byte/hash seal differs')
    require(len(selected)==len(ids),'Frozen selected IDs outside the sealed population')
    proof=dict(rows=expected_rows,bytes=seen_bytes,sha256=h.hexdigest(),seconds=time.perf_counter()-started,category_scans=1,selected_rows=len(selected),
        aggregate_numeric_values_parsed=False,aggregate_values_accumulated=False,scope='Raw CSV bytes are hashed and decoded; category predicates/group keys/nonNULL masks only; no numeric aggregate parsing, multiplication or target truth')
    return (catalog,proof,dict(row_ids=ids,rows=selected)) if with_selection else (catalog,proof)


def validate_worker_results(plan,worker,results):
    p=plan['population'];is_routes=plan['kind']=='ROUTES'
    require(worker.get('new_original_api_calls')==sum(r['native']['api_calls'] for r in results) and
        worker.get('new_fit_attempts')==sum(r['fit_attempted'] for r in results) and worker.get('new_query_evaluation_only_after_raw_predictions') is True and
        worker.get('selected_ids_sha256')==p['row_ids_sha256'] and worker.get('backend')==(ORIGINAL_BACKEND if is_routes else 'CATEGORY_MEMBERSHIP_ONLY'),
        'Actual original worker backend/selection/call/fit/answer boundary differs')


def owned_ops():
    for p,sha in COMMON_PINS.items():require(digest(ROOT/p)==sha,'Frozen shared owned-Windows implementation changed before import')
    path=ROOT/'code/full_ssb_native_model_run.py';names={'windows_api','windows_process_alive','OwnedWindowsJob'}
    tree=ast.parse(path.read_text(encoding='utf-8'));nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    require({n.name for n in nodes}==names and len(nodes)==3,'Exact original Windows process-only AST required')
    scope=dict(os=os,require=require)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return types.SimpleNamespace(**{name:scope[name] for name in names})


def verify_membership(token):
    common=owned_ops();c,w,k=common.windows_api();handle=k.OpenJobObjectW(4,False,job_name(token));require(bool(handle),'Owned DBEst Job Object missing')
    process=k.OpenProcess(0x1000,False,os.getpid());require(bool(process),'Cannot inspect own worker process')
    try:
        inside=w.BOOL();require(k.IsProcessInJob(process,handle,c.byref(inside)) and inside.value,'Fresh worker not in the ROOT-launched owned job')
    finally:k.CloseHandle(process);k.CloseHandle(handle)


def worker_peak():
    old=load_module(ROOT/'code/full_dbest_flights.py','dbest_routes_peak_utility',FROZEN['code/full_dbest_flights.py'])
    return old.peak_bytes() # Native current-process peak-only utility; no old worker/source/fit call.


def directory_bytes(home):return sum(p.stat().st_size for p in Path(home).rglob('*') if p.is_file())


def available_ram():
    import ctypes
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    value=Memory();value.length=ctypes.sizeof(value)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)),'Cannot inspect actual available RAM');return value.available


def _owned_start(args):
    raw=sys.stdin.readline(4097);require(len(raw)<=4096 and raw.endswith('\n'),'Bounded ROOT-owned GO handshake required')
    body=strict_read(args.plan);exact_approval(args.review,args.review_sha256,body['binding_sha256'],body['kind']);verify_membership(args.token)
    require(json.loads(raw)==dict(token=args.token,binding_sha256=body['binding_sha256']),'Exact owned GO/plan identity differs')
    home=Path(args.home).resolve();require(home==(OUT/'runs'/home.name).resolve(),'Only fresh own DBEst run namespace allowed')
    life=strict_read(home/'lifecycle.json');require(life['status']=='RUNNING' and life['binding_sha256']==body['binding_sha256'],'Fresh RUNNING namespace required before any science')
    return body,home


def bootstrap(args):
    body,home=_owned_start(args);cmd=worker_command(body,home,args.review_sha256,args.token)
    # This direct base interpreter was assigned before GO. The venv launcher and
    # its real Python child inherit that same kernel job before receiving GO.
    p=subprocess.Popen(list(map(str,cmd)),stdin=subprocess.PIPE,env=os.environ.copy())
    p.stdin.write((json.dumps(dict(token=args.token,binding_sha256=body['binding_sha256']))+'\n').encode());p.stdin.close()
    return p.wait(timeout=MAX_SECONDS)


def spawn_owned(job,command,env,stdout,stderr,payload):
    """GO follows assignment; stop only the handle-created process if assignment fails."""
    process=subprocess.Popen(list(map(str,command)),cwd=str(ROOT),stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,env=env,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));assigned=False
    try:
        job.assign(process);assigned=True
        process.stdin.write((json.dumps(payload)+'\n').encode());process.stdin.close();return process
    except BaseException:
        if process.stdin is not None and not process.stdin.closed:process.stdin.close()
        if assigned:job.terminate()
        else:process.terminate() # Direct child has never received GO, so cannot have spawned its private worker.
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=15) # Exact Popen handle created here, never a discovered/unowned PID.
        raise


def worker(args):
    body,home=_owned_start(args);verify_plan(body);atomic(home/'source_before.json',body['source']);peak=worker_peak();population=body['population']
    if body['kind']=='CATALOG':
        raw=population['sample'];golden=population['name']=='GOLDEN_200K'
        result=scan_category_file(ROOT/raw['path'],population['retained_rows'],raw['sha256'],raw['bytes'],probability=population['probability'],
            selection_ids=selection_ids(population) if golden else None,with_selection=golden)
        catalog,scan=result[:2]
        if golden:atomic(home/'selected_rows.json',result[2])
        atomic(home/'catalog.json',catalog);atomic(home/'sample_scan.json',scan);new_calls=0;fit_attempts=0
    else:
        selected=selected_rows() if population['name']=='FORMAL_1B' else strict_read((ROOT/body['catalog_final']['path']).parent/'selected_rows.json')
        require(routes.make_jobs(selected,body['catalog'])==body['jobs'],'Exact fixed20K route cohorts differ')
        driver=OriginalAPI(population['seed']);results=[]
        binding=dict(evidence_plan_binding_sha256=body['binding_sha256'],training_binding_sha256=body['training_binding_sha256'])
        for i,j in enumerate(body['jobs']):
            results.append(execute_job(j,driver,home/'jobs'/('%04d'%i),binding));peak=max(peak,worker_peak())
        queries=routes.assemble_queries(body['jobs'],results);atomic(home/'queries.json',queries);atomic(home/'support.json',routes.support_table())
        # All raw per-model/native/query receipts are now sealed. Only this
        # separate evaluation step receives full-stream target aggregate values.
        truth=read_truth(population);atomic(home/'evaluation.json',routes.evaluate(queries,truth,population['population_rows']))
        new_calls=sum(r['native']['api_calls'] for r in results);fit_attempts=sum(r['fit_attempted'] for r in results)
    exit_boundary=_Boundary();_verify_plan_from_boundary(body,exit_boundary);atomic(home/'source_after.json',exit_boundary.source);peak=max(peak,worker_peak())
    result=dict(status='PASS',kind=body['kind'],binding_sha256=body['binding_sha256'],process_id=os.getpid(),owned_job_verified=True,go_verified=True,
        worker_peak_bytes=peak,original_prior_classes_reexecuted=False,new_original_api_calls=new_calls,new_fit_attempts=fit_attempts,
        new_query_evaluation_only_after_raw_predictions=True,selected_ids_sha256=population['row_ids_sha256'],backend=ORIGINAL_BACKEND if body['kind']=='ROUTES' else 'CATEGORY_MEMBERSHIP_ONLY')
    expected=worker_identity(body,home,args.review_sha256,args.token)
    actual=dict(executable=str(Path(sys.executable)),command=[sys.executable]+sys.argv,environment={k:os.environ.get(k) for k in expected['environment']},
        absent_environment=[k for k in expected['absent_environment'] if k not in os.environ])
    require(actual==expected,'Actual fresh worker executable, arguments or thread environment differs');result['identity']=actual
    atomic(home/'worker.json',result);return 0


def run(plan_path,review_path,review_sha,name):
    exact_approval(review_path,review_sha) # Must precede plan parsing, full-source IO and scientific imports.
    body=strict_read(plan_path);exact_approval(review_path,review_sha,body['binding_sha256'],body['kind']);verify_plan(body)
    require(isinstance(name,str) and name and len(name)<=16 and all(c.isascii() and (c.isalnum() or c in '_-') for c in name),'Short fresh ASCII namespace required')
    cap=limits();ram=available_ram();free=shutil.disk_usage(ROOT).free
    require(ram>=cap['minimum_available_ram_bytes'] and free>=cap['minimum_free_disk_bytes'],'Actual DBEst startup memory/disk gate failed')
    home=OUT/'runs'/name;home.parent.mkdir(parents=True,exist_ok=True);home.mkdir(exist_ok=False)
    atomic(home/'lifecycle.json',dict(status='RUNNING',binding_sha256=body['binding_sha256']))
    samples=[];common=owned_ops();token=secrets.token_hex(16);command=bootstrap_command(body,home,review_sha,token);started=time.monotonic();reason=None
    try:
        atomic(home/'plan.json',body);shutil.copyfile(str(review_path),str(home/'review.json'))
        env={k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP')}
        env.update({k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE')})
        env.update(PYTHONHASHSEED=str(body['population']['seed']),MPLBACKEND='Agg',MPLCONFIGDIR=str(home/'auxiliary/matplotlib'))
        with common.OwnedWindowsJob(job_name(token)) as job,(home/'stdout.log').open('xb') as out,(home/'stderr.log').open('xb') as err:
            p=spawn_owned(job,command,env,out,err,dict(token=token,binding_sha256=body['binding_sha256']))
            try:
                while p.poll() is None:
                    sample=dict(monotonic=time.monotonic(),owned_rss_bytes=job.working_set_bytes(),own_output_bytes=directory_bytes(home));samples.append(sample)
                    require(sample['owned_rss_bytes']<=MEMORY and sample['own_output_bytes']<=cap['new_output_bytes'],'Owned worker tree memory/output cap exceeded')
                    if time.monotonic()-started>MAX_SECONDS:raise TimeoutError('Owned DBEst operation deadline exceeded')
                    time.sleep(.25)
                require(p.returncode==0,'Owned original DBEst stage failed; preserve namespace')
                alive=[pid for pid in job.process_ids() if common.windows_process_alive(pid)]
                require(not alive,'Owned DBEst descendants remain alive after bootstrap exit')
                samples.append(dict(monotonic=time.monotonic(),owned_rss_bytes=job.working_set_bytes(),own_output_bytes=directory_bytes(home)))
            except BaseException as error:
                reason=repr(error);job.terminate();p.wait(timeout=15);raise
        controller=dict(status='PASS',command=list(map(str,command)),worker_command=list(map(str,worker_command(body,home,review_sha,token))),review_sha256=review_sha,token=token,
            job_name=job_name(token),exit_code=p.returncode,reason=reason,seconds=time.monotonic()-started,owned_job_assigned_before_go=True,live_owned_descendants_after_exit=[])
        resource=dict(limits=cap,samples=samples,peak_owned_rss_bytes=max(s['owned_rss_bytes'] for s in samples),peak_output_bytes=max(s['own_output_bytes'] for s in samples),
            minimum_available_ram_at_start_bytes=ram,free_disk_at_start_bytes=free)
        atomic(home/'controller.json',controller);atomic(home/'resource.json',resource)
        import full_dbest_flights_routes_audit as audit
        states={j['job_id']:strict_read(home/'jobs'/('%04d'%i)/'fit.json')['status'] for i,j in enumerate(body.get('jobs',[]))}
        required=audit.required_files(body,states)|audit.auxiliary_names(home)
        final=dict(schema='dbest_routes_final_v1',binding_sha256=body['binding_sha256'],review_sha256=review_sha,
            files={n:descriptor(home/n) for n in sorted(required)},author_training_configuration_recovered=False,full_paper_reproduction_complete=False)
        atomic(home/'final.json',final);atomic(home/'final.seal.json',{'sha256':digest(home/'final.json')});atomic(home/'lifecycle.json',dict(status='PASS',final_sha256=digest(home/'final.json')))
        return audit.verify(home)
    except BaseException as error:
        atomic(home/'failed_resource.json',dict(samples=samples,reason=repr(error)));atomic(home/'lifecycle.json',dict(status='TAINTED',error=repr(error)));raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',nargs='?',default='describe',choices=['describe','plan','run','verify','_bootstrap','_worker'])
    parser.add_argument('--kind',choices=['CATALOG','ROUTES']);parser.add_argument('--catalog-final',type=Path);parser.add_argument('--plan',type=Path)
    parser.add_argument('--population',choices=['GOLDEN_200K','FORMAL_1B'],default='FORMAL_1B')
    parser.add_argument('--golden-final',type=Path)
    parser.add_argument('--review',type=Path);parser.add_argument('--review-sha256');parser.add_argument('--name');parser.add_argument('--home',type=Path);parser.add_argument('--token');parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if args.output:
        target=args.output.resolve();require(any((OUT/n).resolve() in target.parents for n in ('plans','audits')) and not target.exists(),'New plans/audits output only; never overwrite sealed runs')
    if args.action=='describe':result=dict(status='CODE_ONLY_NO_SCIENTIFIC_EXECUTION',support=routes.support_table(),actual_native_calls=0)
    elif args.action=='plan':require(args.kind,'Explicit plan kind required');result=plan(args.kind,args.catalog_final,args.population,args.golden_final)
    elif args.action=='run':result=run(args.plan,args.review,args.review_sha256,args.name)
    elif args.action=='verify':
        import full_dbest_flights_routes_audit as audit
        require(args.home,'Explicit completed own namespace required');result=audit.verify(args.home)
    elif args.action=='_bootstrap':return bootstrap(args)
    else:return worker(args)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    else:print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':sys.exit(main())
