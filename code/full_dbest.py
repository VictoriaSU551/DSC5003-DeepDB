"""Small, sealed original DBEstPy gate; no paper-scale training is authorized here."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import csv
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import shutil
import sqlite3
import subprocess
import sys
import time
import types
import warnings
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA, OUTPUT = ROOT / 'data/dbest', ROOT / 'output/full/dbest'
SOURCE = DATA / 'source'
PRIVATE_PYTHON = ROOT / '.venv-dbest/Scripts/python.exe'
GOLD_CSV = ROOT / 'data/flights/generated/golden-200k/original.csv'
GOLD_OUTPUT = ROOT / 'output/full/flights/golden-200k'
GOLD_DATABASE = GOLD_OUTPUT / 'reference.sqlite'
QUERIES = ROOT / 'code/benchmarks/flights/sql/aqp_queries.sql'
SOURCE_SEAL = ROOT / 'data/downloads/baselines/dbpy/seal.json'
SOURCE_COMMIT = '2220a937b5eef358eb42a715da328915048b7250'
SOURCE_ARCHIVE_SHA256 = '532902dce2c0f598c71583bfb31085037eea9fac71c588393812a63de899e2bf'
FIT_ROWS, SEED = 20000, 74031
NUMERIC = {'DEP_DELAY', 'TAXI_OUT', 'TAXI_IN', 'ARR_DELAY', 'AIR_TIME', 'DISTANCE'}
CATEGORICAL = {'UNIQUE_CARRIER','ORIGIN','ORIGIN_STATE_ABR','DEST','DEST_STATE_ABR','YEAR_DATE'}
PINS = {'numpy':'1.19.5','scipy':'1.4.1','pandas':'1.0.3','scikit-learn':'0.22.2.post1',
        'matplotlib':'3.2.1','xgboost':'1.0.2','joblib':'0.14.1','python-dateutil':'2.8.1',
        'pytz':'2020.1','cycler':'0.10.0','kiwisolver':'1.3.1','pyparsing':'2.4.7',
        'six':'1.16.0','Pillow':'8.4.0','setuptools':'59.8.0','sqlparse':'0.3.1'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def check_file(path, expected):
    if digest(path) != expected: raise ValueError('Input/source checksum changed: ' + str(path))


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def require_fit_size(rows):
    if type(rows) is not int or not 0 < rows <= FIT_ROWS:
        raise ValueError('Original DBEst gate requires 1--20K fit rows')


def exact_range(connection, column, lower, upper, lower_closed=False, upper_closed=True, conditions=None):
    if column not in NUMERIC: raise ValueError('Unsupported numeric column')
    predicates, values = [], []
    for name, value in (conditions or {}).items():
        if name not in CATEGORICAL: raise ValueError('Unsupported condition column')
        predicates.append(name + ' = ?'); values.append(value)
    if math.isfinite(lower):
        predicates.append(column + (' >= ?' if lower_closed else ' > ?')); values.append(float(Decimal(str(lower)) * 10))
    if math.isfinite(upper):
        predicates.append(column + (' <= ?' if upper_closed else ' < ?')); values.append(float(Decimal(str(upper)) * 10))
    sql = 'SELECT COUNT(*),COALESCE(SUM(' + column + '),0) FROM flights'
    if predicates: sql += ' WHERE ' + ' AND '.join(predicates)
    count, total = connection.execute(sql, values).fetchone()
    return {'count': count, 'sum_tenths': total, 'avg_numerator': total,
            'avg_denominator': 10 * count if count else None}


def query_support():
    names = ['F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2']
    supported = {0:'AVG of dep_delay after released categorical prefilter, full one-dimensional support',
                 1:'AVG of distance after released categorical prefilter, full one-dimensional support',
                 5:'SUM of distance by year after released categorical prefilter; declared population group counts',
                 8:'COUNT by destination state with distance > 2500; one numeric range'}
    reasons = {2:'Pure categorical COUNT would disclose evaluated target through prefilter group-count metadata; excluded from this gate',
               3:'Pure categorical COUNT would disclose evaluated target through prefilter group-count metadata; excluded from this gate',
               4:'Pure categorical COUNT would disclose evaluated target through prefilter group-count metadata; excluded from this gate',
               6:'Rare prefilter/group coverage and a second SUM routing not implemented in this bounded gate',
               7:'Numeric equality on year requires discrete mass handling absent from continuous one-dimensional range engine',
               9:'Two numeric filter attributes; original multidimensional path requires separate failure/compatibility gate',
               10:'Aggregate expression/product projection not routed by this bounded gate',
               11:'Difference of two SUM models not routed by this bounded gate'}
    return [{'query_no': i, 'name': name, 'status':'SUPPORTED' if i in supported else 'UNSUPPORTED',
             'reason': supported.get(i, reasons.get(i))} for i,name in enumerate(names)]


def gaussian_moments(xs, slope, intercept, bandwidth, lower, upper, population):
    """Independent closed-form oracle for the fitted official Gaussian+LR only."""
    def phi(z): return 0.0 if not math.isfinite(z) else math.exp(-z*z/2) / math.sqrt(2*math.pi)
    def cdf(z): return (1 + math.erf(z / math.sqrt(2))) / 2
    probabilities, first = [], []
    for x in xs:
        a, b = (lower - x) / bandwidth, (upper - x) / bandwidth
        probability = cdf(b) - cdf(a)
        probabilities.append(probability)
        first.append(x * probability + bandwidth * (phi(a) - phi(b)))
    p = math.fsum(probabilities) / len(xs)
    weighted = slope * math.fsum(first) / len(xs) + intercept * p
    return {'count': population * p, 'sum': population * weighted, 'avg': weighted / p if p else None}


def run_command(arguments, log, timeout=600):
    environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       NUMEXPR_NUM_THREADS='1', MPLBACKEND='Agg', PYTHONDONTWRITEBYTECODE='1')
    start = time.perf_counter()
    process=subprocess.Popen([str(x) for x in arguments],cwd=str(ROOT),env=environment,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,errors='replace')
    try: stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # On Windows venv python is a launcher: terminate this bounded command's
        # child tree as well, so a timed-out fit cannot keep consuming resources.
        if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
        else: process.kill()
        stdout,stderr=process.communicate()
        atomic(log,{'arguments':list(map(str,arguments)),'returncode':'TIMEOUT','stdout':stdout,'stderr':stderr,
                    'seconds':time.perf_counter()-start,'timeout_seconds':timeout})
        raise RuntimeError('Bounded DBEst command timed out; process tree terminated')
    result=subprocess.CompletedProcess(arguments,process.returncode,stdout,stderr)
    atomic(log, {'arguments':list(map(str, arguments)), 'returncode':result.returncode,
                 'stdout':result.stdout, 'stderr':result.stderr, 'seconds':time.perf_counter()-start})
    return result


def restore_source():
    seal = json.loads(SOURCE_SEAL.read_text())
    if seal['commit'] != SOURCE_COMMIT: raise ValueError('DBEst source commit changed')
    if seal['archive_sha256']!=SOURCE_ARCHIVE_SHA256: raise ValueError('DBEst pinned archive checksum changed')
    archive = ROOT / seal['archive_path']; check_file(archive, seal['archive_sha256'])
    expected = {}
    with zipfile.ZipFile(str(archive)) as source:
        for item in source.infolist():
            parts = Path(item.filename).parts
            if item.is_dir(): continue
            name = '/'.join(parts[1:])
            if '..' in parts or name.startswith('/') or '\\' in item.filename: raise ValueError('Unsafe source path')
            if name.startswith('dbest/') and name.endswith('.py') or name in ['LICENSE','README.rst','requirements.txt','setup.py']:
                content = source.read(item)
                target = SOURCE / name
                expected[name] = hashlib.sha256(content).hexdigest()
                if target.exists(): check_file(target, expected[name])
                else:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    atomic(OUTPUT / 'source_binding.json', {'commit': SOURCE_COMMIT, 'archive_sha256':seal['archive_sha256'], 'files_sha256':expected})
    return expected


def download_wheel(pair):
    name, version = pair
    directory = DATA / 'wheels'; directory.mkdir(parents=True, exist_ok=True)
    metadata_path = directory / (name + '-' + version + '.json')
    if metadata_path.exists(): info = json.loads(metadata_path.read_text())
    else:
        url = 'https://pypi.org/pypi/' + name + '/' + version + '/json'
        info = json.load(urllib.request.urlopen(url, timeout=60)); atomic(metadata_path, info)
    def eligible(item):
        filename = item['filename']
        return filename.endswith('.whl') and (('cp38-cp38-win_amd64' in filename) or
            ('py3-none-win_amd64' in filename) or filename.endswith('py3-none-any.whl') or filename.endswith('py2.py3-none-any.whl'))
    candidates = [x for x in info['urls'] if eligible(x)]
    if not candidates: raise ValueError('No pinned CPython38 Windows wheel: ' + name)
    item = sorted(candidates, key=lambda x:x['filename'])[0]
    path = directory / item['filename']
    if not path.exists():
        temporary = path.with_suffix('.download.tmp')
        with urllib.request.urlopen(item['url'], timeout=60) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source,target)
        check_file(temporary, item['digests']['sha256']); os.replace(str(temporary),str(path))
    check_file(path,item['digests']['sha256'])
    return {'package':name,'version':version,'path':str(path),'sha256':item['digests']['sha256'],'bytes':path.stat().st_size}


def setup_environment():
    restore_source()
    probe = "import sys;sys.path.insert(0," + repr(str(SOURCE)) + ");from dbest.query_engine import QueryEngine;print(QueryEngine.__module__)"
    if not (OUTPUT/'import_before_environment.json').exists():
        run_command([ROOT/'.venv/Scripts/python.exe','-B','-c',probe],OUTPUT/'import_before_environment.json')
    if not PRIVATE_PYTHON.exists():
        result=run_command([ROOT/'.venv/Scripts/python.exe','-m','venv',ROOT/'.venv-dbest','--without-pip'],OUTPUT/'create_environment.json')
        if result.returncode: raise RuntimeError('Cannot create independent DBEst environment')
    receipt = OUTPUT/'environment.json'
    if not receipt.exists():
        with ThreadPoolExecutor(max_workers=3) as pool: wheels=list(pool.map(download_wheel,PINS.items()))
        result=run_command(['python','-m','pip','--python',PRIVATE_PYTHON,'install','--no-index','--no-deps','--no-cache-dir']
                           +[x['path'] for x in wheels],OUTPUT/'install_environment.json')
        if result.returncode: raise RuntimeError('Pinned environment install failed')
        atomic(receipt,{'packages':PINS,'wheels':wheels,'independent_venv':str(PRIVATE_PYTHON)})
    result=run_command([PRIVATE_PYTHON,'-B','-c',probe],OUTPUT/'import_after_environment.json')
    if result.returncode: raise RuntimeError('Official engine import still failed')
    return {'status':'PASS','stage':'ISOLATED_ENVIRONMENT_ONLY'}


def engine_modules():
    restore_source()
    sys.path.insert(0,str(SOURCE))
    import numpy as np
    from dbest.qreg import CRegression
    from dbest.query_engine import QueryEngine
    from dbest import logs, tools
    return np, CRegression, QueryEngine, logs, tools


def fit_original(xs, ys, population, name):
    require_fit_size(len(xs))
    if len(xs) != len(ys) or population < len(xs): raise ValueError('Invalid population/sample sizes')
    np, CRegression, QueryEngine, logs, tools = engine_modules()
    logger=logs.QueryLogs(log=str(OUTPUT/(name+'.log'))); logger.set_no_output()
    training=tools.DataSource()
    training.features=np.asarray(xs,dtype=float).reshape(len(xs),-1)
    training.labels=np.asarray(ys,dtype=float)
    training.headers=['X','Y']; training.file=name
    start=time.perf_counter()
    regression=CRegression(logger_object=logger,base_models=[tools.app_linear],n_cores=1)
    regression.fit(training)
    engine=QueryEngine(regression,logger_object=logger,num_training_points=population,b_print_time_cost=False)
    engine.density_estimation()
    return engine, time.perf_counter()-start


def invoke_native(engine, lower, upper, aggregates=('count','sum','avg'), stabilize=False):
    """Calls unmodified official methods; records native KDE work and warnings."""
    counter={'calls':0,'evaluated_points':0}
    original=engine.kde.score_samples
    query_module=sys.modules[engine.__class__.__module__]
    original_integrator=query_module.integrate
    adapter={'enabled':False,'kde_and_regression_unchanged':True}
    if stabilize:
        evidence=OUTPUT/'numerical_failure_F1.2_all.json'
        if not evidence.exists() or json.loads(evidence.read_text())['integral_verified']:
            raise ValueError('Numerical adapter requires preserved original failure evidence')
        spacing=4.*float(engine.kde.bandwidth)
        count=math.ceil((upper-lower)/spacing)
        if count>10000: raise ValueError('Numerical range exceeds bounded integration budget')
        points=[lower+spacing*i for i in range(1,count) if lower+spacing*i<upper]
        def quad(function,a,b,**options):
            # Same scipy QUADPACK algorithm and original integrands, with explicit
            # subinterval boundaries so narrow Gaussian modes cannot be skipped.
            options.update(points=points,limit=max(50,2*len(points)+50))
            return original_integrator.quad(function,a,b,**options)
        query_module.integrate=types.SimpleNamespace(quad=quad,nquad=original_integrator.nquad)
        adapter.update(enabled=True,spacing=spacing,interior_breakpoints=len(points),
                       scipy_backend='Original scipy.integrate.quad; points/limit only',
                       failure_evidence=str(evidence.relative_to(ROOT)))
    def score(values):
        counter['calls']+=1; counter['evaluated_points']+=len(values)
        return original(values)
    engine.kde.score_samples=score
    values={}; timings={}
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            for aggregate in aggregates:
                result, seconds=getattr(engine,'approximate_'+aggregate+'_from_to')(
                    lower,upper,0,epsabs=1e-8,epsrel=1e-8)
                values[aggregate]=float(result) if result is not None else None
                timings[aggregate]=seconds
        return {'values':values,'seconds':timings,'native_method_calls':len(aggregates),
                'native_kde_evaluations':counter['evaluated_points'],'native_kde_calls':counter['calls'],
                'warnings':list(dict.fromkeys(str(item.message) for item in caught)),
                'numerical_adapter':adapter}
    finally:
        engine.kde.score_samples=original
        query_module.integrate=original_integrator


def probe_worker():
    xs=[-3.,-2.,-1.,0.,1.,2.,3.,4.]
    engine,seconds=fit_original(xs,[2*x+3 for x in xs],80,'probe')
    results=[]
    for population in [80,800]:
        engine.num_training_points=population
        actual=invoke_native(engine,-20.,20.)
        expected=gaussian_moments(xs,2.,3.,1.,-20.,20.,population)
        actual.update(population=population,expected=expected)
        results.append(actual)
    default=engine.__class__(engine.cregression,logger_object=types.SimpleNamespace(logger=engine.logger),b_print_time_cost=False)
    default.density_estimation()
    unscaled=invoke_native(default,-20.,20.)
    engine.num_training_points=80
    boundary_result=invoke_native(engine,0.,20.,('count',))
    boundary_probe={'query':'X > 0 versus X >= 0, upper bound 20, N=80 and n=8',
                    'exact_strict':40,'exact_closed':50,'atom_training_rows':1,
                    'same_continuous_estimate_for_both':boundary_result,
                    'status':'CONTINUOUS_KDE_DOES_NOT_MODEL_DISCRETE_ATOM_BOUNDARIES'}
    multidimensional={'status':'UNSUPPORTED'}
    try:
        fit_original([[x,x*x] for x in xs],[2*x+3 for x in xs],80,'multidimensional_probe')
        multidimensional.update(status='NOT_FAILED_AT_CONSTRUCTOR',reason='No verified multidimensional integral gate')
    except Exception as error:
        multidimensional.update(exception_type=type(error).__name__,message=str(error),
                               stage='Official QueryEngine constructor before density estimation')
    summary={'status':'PASS','stage':'OFFICIAL_ENGINE_ANALYTIC_PROBE','training_rows':8,
             'population_counts':[80,800],'fit_seconds':seconds,'results':results,
             'native_method_calls':sum(x['native_method_calls'] for x in results)+unscaled['native_method_calls']+boundary_result['native_method_calls'],
             'native_kde_evaluations':sum(x['native_kde_evaluations'] for x in results)+unscaled['native_kde_evaluations']+boundary_result['native_kde_evaluations'],
             'max_count_absolute_error':max(abs(x['values']['count']-x['expected']['count']) for x in results),
             'max_sum_relative_error':max(abs(x['values']['sum']/x['expected']['sum']-1) for x in results),
             'max_avg_absolute_error':max(abs(x['values']['avg']-x['expected']['avg']) for x in results),
             'native_count_semantics':'Official method truncates real estimate with int(result)',
             'default_population_if_N_omitted':default.num_training_points,'sample_as_population':unscaled,
             'explicit_population_sum_multiplier':results[0]['values']['sum']/unscaled['values']['sum'],
             'boundary_probe':boundary_probe,
             'multidimensional':multidimensional,
             'source_bytes_unchanged':bool(restore_source())}
    if summary['max_count_absolute_error']>1 or summary['max_sum_relative_error']>1e-7 or summary['max_avg_absolute_error']>1e-7:
        summary['status']='FAIL'
    atomic(OUTPUT/'probe.json',summary)
    return summary


def run_probe():
    if not (OUTPUT/'environment.json').exists(): raise RuntimeError('Run setup before the real engine probe')
    result=run_command([PRIVATE_PYTHON,'-B',__file__,'probe-worker'],OUTPUT/'probe_process.json')
    if result.returncode: raise RuntimeError('Official probe failed: '+result.stderr[-3000:])
    return json.loads((OUTPUT/'probe.json').read_text())


def gold_binding():
    receipt=json.loads((GOLD_OUTPUT/'golden_validation.json').read_text())
    if receipt['status']!='PASS' or receipt['population_rows']!=200000:
        raise ValueError('Frozen 200K golden gate is not PASS')
    check_file(GOLD_CSV,receipt['reference_sha256'])
    paths=[GOLD_CSV,GOLD_DATABASE,QUERIES,GOLD_OUTPUT/'sqlite_exact_state.json',GOLD_OUTPUT/'golden_validation.json']
    binding={str(path.relative_to(ROOT)):digest(path) for path in paths}
    seal=OUTPUT/'input_binding.json'
    if seal.exists():
        if json.loads(seal.read_text())!=binding: raise ValueError('Frozen input binding changed')
    else: atomic(seal,binding)
    return binding


def read_gold_truth():
    # Parse literals only: do not import or alter the actively used generator module.
    tree=ast.parse((ROOT/'code/full_flights_generate.py').read_text(encoding='utf-8'))
    literals={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ['ORIGINAL_SQL','EXACT_SQL']:
                    literals[target.id]=ast.literal_eval(node.value)
    normalized=lambda value: ''.join(value.lower().split())
    if list(map(normalized,QUERIES.read_text().splitlines()))!=list(map(normalized,literals['ORIGINAL_SQL'])):
        raise ValueError('Original 12 SQLs changed')
    state=json.loads((GOLD_OUTPUT/'sqlite_exact_state.json').read_text())
    if len(literals['EXACT_SQL'])!=12 or len(state['aggregates'])!=12:
        raise ValueError('Exactly 12 SQL/truth states are required')
    if [(x['query_no'],x['query_name']) for x in state['aggregates']]!=[(x['query_no'],x['name']) for x in query_support()]:
        raise ValueError('Original 12 SQL/truth identities are misaligned')
    connection=sqlite3.connect(GOLD_DATABASE.as_uri()+'?mode=ro',uri=True)
    try:
        if connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0]!=200000: raise ValueError('Golden row count changed')
        for query,reference in zip(literals['EXACT_SQL'],state['aggregates']):
            actual=[{'key':list(row[:-2]),'sum':row[-2] or 0,'count':row[-1]} for row in connection.execute(query)]
            if actual!=reference['groups']: raise ValueError('SQLite SQL/truth group mismatch')
    finally: connection.close()
    return state


def sample_cohorts():
    identifiers=sorted(random.Random(SEED).sample(range(200000),FIT_ROWS)); selected=set(identifiers)
    cohorts={}
    def add(name,key,row_no,value):
        item=cohorts.setdefault((name,str(key)),{'population':0,'xs':[],'ids':[]})
        item['population']+=1
        if row_no in selected: item['xs'].append(float(value)); item['ids'].append(row_no)
    with GOLD_CSV.open(newline='') as stream:
        for i,row in enumerate(csv.DictReader(stream)):
            if row['ORIGIN']=='ATL': add('F1.1','all',i,row['DEP_DELAY'])
            if row['UNIQUE_CARRIER']=='TW': add('F1.2','all',i,row['DISTANCE'])
            if row['UNIQUE_CARRIER']=='9E': add('F3.1',row['YEAR_DATE'],i,row['DISTANCE'])
            add('F4.1',row['DEST_STATE_ABR'],i,row['DISTANCE'])
    if i+1!=200000: raise ValueError('Golden CSV row count changed')
    atomic(DATA/'training_selection.json',{'seed':SEED,'row_ids_zero_based':identifiers,
           'sampling':'Uniform without replacement; no aggregate answer used for row selection'})
    metadata=[{'query':name,'key':key,'population_count':value['population'],'sample_count':len(value['xs'])}
              for (name,key),value in sorted(cohorts.items())]
    atomic(DATA/'group_counts.json',{'source':'One pass through frozen raw CSV, counting only prefilter/group membership before numeric range',
           'counts':metadata})
    return cohorts


def cached_model(name,key,data,binding):
    identity={'inputs':binding,'source_commit':SOURCE_COMMIT,'pins':PINS,'base_models':['LR'],
              'bandwidth':1.,'sample_row_ids':data['ids'],'population_count':data['population'],'version':1}
    encoded=json.dumps(identity,sort_keys=True,separators=(',',':')).encode()
    model_id=hashlib.sha256(encoded).hexdigest()
    directory=OUTPUT/'models'; directory.mkdir(parents=True,exist_ok=True)
    path=directory/(name+'_'+key+'.pkl'); manifest=path.with_suffix('.json')
    engine_modules()
    if path.exists():
        seal=json.loads(manifest.read_text())
        if seal['binding_sha256']!=model_id: raise ValueError('Model input binding changed')
        check_file(path,seal['model_sha256'])
        with path.open('rb') as stream: engine=pickle.load(stream)
        return engine,seal
    engine,seconds=fit_original(data['xs'],data['xs'],data['population'],name+'_'+key)
    temporary=path.with_suffix('.tmp')
    with temporary.open('wb') as stream: pickle.dump(engine,stream,protocol=4)
    os.replace(str(temporary),str(path))
    seal={'binding_sha256':model_id,'model_sha256':digest(path),'fit_seconds':seconds,'fit_rows':len(data['xs']),
          'population_rows':data['population'],'configuration':identity,'path':str(path.relative_to(ROOT))}
    atomic(manifest,seal)
    return engine,seal


def verified_integral(engine,xs,lower,upper,aggregates,name):
    model=engine.cregression.apps_deployed[0]
    slope=float(model.coef_[0]); intercept=float(model.intercept_)
    expected=gaussian_moments(xs,slope,intercept,float(engine.kde.bandwidth),lower,upper,engine.num_training_points)
    configuration={'xs':xs,'slope':slope,'intercept':intercept,'bandwidth':float(engine.kde.bandwidth),
                   'population':engine.num_training_points,'lower':lower,'upper':upper,'aggregates':aggregates,
                   'source_archive':SOURCE_ARCHIVE_SHA256,'integration_version':1}
    binding=hashlib.sha256(json.dumps(configuration,sort_keys=True).encode()).hexdigest()
    cache=OUTPUT/'integrals'/(name+'.json')
    previous=json.loads(cache.read_text()) if cache.exists() else None
    if previous and previous['binding_sha256']==binding:
        actual=previous['actual']; actual['verified_integral_reused']=True
    else: actual=invoke_native(engine,lower,upper,aggregates,stabilize=True)
    errors={key:abs(actual['values'][key]-expected[key]) if actual['values'][key] is not None and expected[key] is not None else None
            for key in aggregates}
    passed=all(error is not None and error<=(1.00001 if key=='count' else max(1e-5,abs(expected[key])*1e-5))
               for key,error in errors.items())
    actual.update(oracle=expected,oracle_absolute_errors=errors,integral_verified=passed,lower=lower,upper=upper)
    if not passed:
        evidence=OUTPUT/('numerical_failure_'+name+'.json')
        if not evidence.exists(): atomic(evidence,actual)
        raise ArithmeticError('Official integral disagrees with independent analytic oracle: '+name)
    if not previous: atomic(cache,{'binding_sha256':binding,'actual':actual})
    elif previous['binding_sha256']!=binding: raise ValueError('Verified integral binding changed; retain old receipt')
    return actual


def ensure_original_numerical_failure(cohorts,binding):
    """Makes the before/after experiment reproducible in a fresh local setup."""
    data=cohorts[('F1.2','all')]
    engine,seal=cached_model('F1.2','all',data,binding)
    path=OUTPUT/'numerical_failure_F1.2_all.json'; bound=OUTPUT/'numerical_failure_binding.json'
    identity={'model_sha256':seal['model_sha256'],'inputs':binding,'source_archive':SOURCE_ARCHIVE_SHA256}
    if bound.exists():
        previous=json.loads(bound.read_text())
        if previous['binding']!=identity: raise ValueError('Original failure model/input binding changed')
        check_file(path,previous['failure_sha256']); return
    lower,upper=min(data['xs'])-12.,max(data['xs'])+12.
    model=engine.cregression.apps_deployed[0]
    expected=gaussian_moments(data['xs'],float(model.coef_[0]),float(model.intercept_),1.,lower,upper,data['population'])
    if not path.exists():
        actual=invoke_native(engine,lower,upper,('avg',))
        error=abs(actual['values']['avg']-expected['avg'])
        actual.update(oracle=expected,oracle_absolute_errors={'avg':error},integral_verified=error<1e-5,
                      lower=lower,upper=upper)
        atomic(path,actual)
    failure=json.loads(path.read_text())
    if failure['integral_verified'] or abs(failure['oracle']['avg']-expected['avg'])>1e-8:
        raise ValueError('Pinned original failure was not reproduced; adapter requires a new diagnosis')
    atomic(bound,{'binding':identity,'failure_sha256':digest(path)})


def small_worker():
    start=time.perf_counter(); binding=gold_binding(); truth=read_gold_truth(); cohorts=sample_cohorts()
    ensure_original_numerical_failure(cohorts,binding)
    queries=[]; models=[]
    for query_no,aggregate in [(0,'avg'),(1,'avg'),(5,'sum'),(8,'count')]:
        spec=query_support()[query_no]; predictions=[]; unavailable=[]
        expected_groups={str(x['key'][0]) if x['key'] else 'all':x for x in truth['aggregates'][query_no]['groups']}
        selected=[(key,value) for (name,key),value in cohorts.items() if name==spec['name']]
        for key,data in sorted(selected):
            if not data['xs']:
                unavailable.append({'group':key,'status':'UNSUPPORTED_INSUFFICIENT_SAMPLE',
                                    'population_N':data['population'],'fit_n':0,'estimate':None,
                                    'truth_group_present':key in expected_groups})
                continue
            engine,seal=cached_model(spec['name'],key,data,binding); models.append(seal)
            lower=2500. if query_no==8 else min(data['xs'])-12.
            upper=max(max(data['xs'])+12.,lower+12.)
            actual=verified_integral(engine,data['xs'],lower,upper,(aggregate,),spec['name']+'_'+key)
            reference=expected_groups.get(key)
            exact=(reference['count'] if aggregate=='count' else reference['sum']/10. if aggregate=='sum'
                   else reference['sum']/(10*reference['count'])) if reference else 0.
            value=actual['values'][aggregate]
            predictions.append({'group':key,'population_N':data['population'],'fit_n':len(data['xs']),
                                'exact':exact,'estimate':value,'absolute_error':abs(value-exact),
                                'relative_error':abs(value/exact-1) if exact else None,'native':actual})
        queries.append(dict(spec,predictions=predictions,all_native_integrals_verified=True,
                            coverage_complete=not unavailable,unavailable_groups=unavailable,
                            missing_truth_groups=sorted(set(expected_groups)-{x['group'] for x in predictions}),
                            extra_prediction_groups=sorted({x['group'] for x in predictions}-set(expected_groups))))
    connection=sqlite3.connect(GOLD_DATABASE.as_uri()+'?mode=ro',uri=True)
    try:
        strict=exact_range(connection,'DISTANCE',2500.,float('inf'))
        closed=exact_range(connection,'DISTANCE',2500.,float('inf'),lower_closed=True)
        auxiliary_truth=exact_range(connection,'DISTANCE',500.,1500.,conditions={'DEST_STATE_ABR':'CA'})
    finally: connection.close()
    data=cohorts[('F4.1','CA')]; engine,_=cached_model('F4.1','CA',data,binding)
    auxiliary=verified_integral(engine,data['xs'],500.,1500.,('count','sum','avg'),'auxiliary_CA')
    auxiliary['exact_sqlite']=auxiliary_truth
    all_actual=[p['native'] for q in queries for p in q['predictions']]+[auxiliary]
    report={'status':'PASS','stage':'OFFICIAL_DBESTPY_SMALL_GATE_ONLY','paper_scale_reached':False,
            'source_commit':SOURCE_COMMIT,'population_rows':200000,'unique_fit_rows':FIT_ROWS,
            'seed':SEED,'queries':queries,'query_support':query_support(),'auxiliary_numeric_range':auxiliary,
            'boundary':{'strict_count':strict['count'],'closed_count':closed['count'],'point_mass_at_2500':closed['count']-strict['count'],
                        'native_semantics':'Continuous KDE gives identical open/closed boundary integrals; discrete atom is not explicitly modeled'},
            'native_method_calls':sum(x['native_method_calls'] for x in all_actual),
            'native_kde_evaluations':sum(x['native_kde_evaluations'] for x in all_actual),
            'fit_seconds':sum(x['fit_seconds'] for x in models),'wall_seconds':time.perf_counter()-start,
            'model_files':[{key:x[key] for key in ['path','model_sha256','fit_rows','population_rows','fit_seconds']} for x in models],
            'all_12_sqlite_states_match_sealed_truth':True,'input_bytes_unchanged':gold_binding()==binding,
            'coverage_gaps':[x for q in queries for x in q['unavailable_groups']],
            'support_table_scope':'Route capability; actual group coverage is reported separately in queries',
            'native_call_count_scope':'Total calls whose original results are bound in verified receipts, including cache reuse',
            'native_method_calls_this_invocation':sum(x['native_method_calls'] for x in all_actual if not x.get('verified_integral_reused')),
            'verified_integrals_reused':sum(bool(x.get('verified_integral_reused')) for x in all_actual),
            'total_verified_query_seconds':sum(sum(x['seconds'].values()) for x in all_actual),
            'source_bytes_unchanged':bool(restore_source()),'wrapper_sha256':digest(__file__)}
    atomic(OUTPUT/'small_gate.json',report)
    first=OUTPUT/'small_gate_first_success.json'
    if not first.exists(): atomic(first,report)
    protected=[OUTPUT/'small_gate.json']+[ROOT/x['path'] for x in report['model_files']]+list((OUTPUT/'integrals').glob('*.json'))
    atomic(OUTPUT/'small_gate_seal.json',{'files_sha256':{str(path.relative_to(ROOT)):digest(path) for path in protected}})
    return report


def run_small():
    binding=gold_binding(); restore_source()
    cached=OUTPUT/'small_gate.json'
    if cached.exists():
        report=json.loads(cached.read_text())
        seal=OUTPUT/'small_gate_seal.json'
        if report.get('wrapper_sha256')==digest(__file__) and report['status']=='PASS' and seal.exists():
            for name,sha in json.loads(seal.read_text())['files_sha256'].items(): check_file(ROOT/name,sha)
            for item in report['model_files']: check_file(ROOT/item['path'],item['model_sha256'])
            report['verified_receipt_reused']=True
            return report
    result=run_command([PRIVATE_PYTHON,'-B',__file__,'small-worker'],OUTPUT/'small_process.json',timeout=600)
    if result.returncode: raise RuntimeError('Original small gate failed: '+result.stderr[-3000:])
    return json.loads(cached.read_text())


def one_billion_plan():
    report=run_small()
    if report['status']!='PASS': raise ValueError('Small original-engine gate is not PASS')
    plan={'status':'PLAN_ONLY_NOT_EXECUTED','paper_baseline_recovered':False,'population_rows':1000000000,
          'small_gate_sha256':digest(OUTPUT/'small_gate.json'),'fit_rows_hard_cap':FIT_ROWS,
          'input':'Use only finalized Flights 1B sample, exact full-stream truth and their matching SHA/seed/config binding',
          'sampling':'Stream finalized approximately 10M-row Bernoulli sample; deterministic reservoir of at most 20K unique sample rows; never read entire sample into pandas',
          'population_counts':'N=1B known. Prefilter/group counts are separate training metadata. Existing truth COUNTs for evaluated filtered groups may not be used to fill missing prefilter counts',
          'N_group_gap':'F4.1 requires state counts BEFORE distance>2500. With full population discarded, estimate N_group=n_group/p from the retained uniform sample and label extra sampling error, or require an independently authorized exact catalog collected during original generation',
          'supported_initial_routes':['F1.1','F1.2','F3.1','F4.1 (subject to group coverage and population-count source)'],
          'unsupported_routes':[x['name'] for x in query_support() if x['status']=='UNSUPPORTED'],
          'discrete_boundary_gap':'Strict versus closed SQL truth is preserved, but Gaussian KDE has no atom mass semantics; equality queries remain outside the gate',
          'resources':{'retained_input_csv_estimated_bytes':600000000,'extra_subset_and_models_budget_bytes':100000000,
                       'existing_isolated_environment_bytes':sum(x.stat().st_size for x in (ROOT/'.venv-dbest').rglob('*') if x.is_file()),
                       'existing_downloads_bytes':sum(x.stat().st_size for x in DATA.rglob('*') if x.is_file()),
                       'single_process_rss_budget_bytes':536870912,
                       'small_gate_first_success_wall_seconds':json.loads((OUTPUT/'small_gate_first_success.json').read_text())['wall_seconds'],
                       'verified_native_query_seconds':report['total_verified_query_seconds'],
                       'initial_20K_fit_and_query_budget_seconds':900,
                       'sample_scan_budget_seconds':600,
                       'timing_note':'Conservative budgets, not measurements on 1B input. Training size stays <=20K; do not extrapolate 20K timing to 10M KDE or claim original-scale performance'},
          'paper_configuration_gaps':['DeepDB Figure13 uses the released 12 Flights query classes and prior workload information',
                                      'Figure12 left varies 1/2/3 numeric filter attributes; precise microbenchmark SQL and per-model training rows not identified',
                                      'DeepDB 10M Flights training rows are not evidence of the same DBEst training size',
                                      'LR + default Gaussian bandwidth1 is an official selectable configuration, not proven DeepDB author hyperparameters'],
          'execution_authorized_here':False}
    atomic(OUTPUT/'one_billion_plan.json',plan)
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','probe','probe-worker','small','small-worker','plan'])
    args=parser.parse_args()
    result={'setup':setup_environment,'probe':run_probe,'probe-worker':probe_worker,'small':run_small,'small-worker':small_worker,'plan':one_billion_plan}[args.action]()
    print(json.dumps({k:v for k,v in result.items() if k in ['status','stage','population_rows','native_method_calls','wall_seconds']}))


if __name__=='__main__': main()
