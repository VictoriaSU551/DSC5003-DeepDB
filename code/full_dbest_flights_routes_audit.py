"""Strictly read-only original-DBEst routing evidence audit; no model loading."""
import argparse
import builtins
from contextlib import contextmanager
import importlib
import io
import json
import math
import os
from pathlib import Path
import pickle
import subprocess
import full_dbest_flights_routes as routes
import full_dbest_flights_routes_run as ops

ROOT=routes.ROOT
strict_read=ops.strict_read


class DataOnlyUnpickler(pickle.Unpickler):
    def find_class(self,module,name):raise RuntimeError('Model/global pickle loading forbidden during audit')


@contextmanager
def forbid_operations():
    """Permit bytes/read-only evidence and one exactly pinned primitive selection."""
    def forbidden(*args,**kwargs):raise RuntimeError('Forbidden operation during read-only DBEst route audit')
    saved=[]
    def replace(obj,key,value):
        if hasattr(obj,key):saved.append((obj,key,getattr(obj,key)));setattr(obj,key,value)
    opener=builtins.open;io_opener=io.open;os_opener=os.open;importer=builtins.__import__
    def checked_open(original):
        def opening(file,mode='r',*args,**kwargs):
            if not isinstance(mode,str) or any(c in mode for c in 'wax+'):forbidden()
            return original(file,mode,*args,**kwargs)
        return opening
    def raw_open(path,flags,*args,**kwargs):
        if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):forbidden()
        return os_opener(path,flags,*args,**kwargs)
    def selection_only(stream,*args,**kwargs):
        name=Path(getattr(stream,'name','')).resolve();expected=(ROOT/'data/dbest_flights/selected_rows.pkl').resolve()
        if name!=expected or ops.digest(name)!=routes.SELECTION_PICKLE_SHA:forbidden()
        return DataOnlyUnpickler(stream).load()
    def checked_import(name,*args,**kwargs):
        if name.split('.')[0] in ('psycopg2','dbest','numpy','scipy','sklearn'):forbidden()
        return importer(name,*args,**kwargs)
    try:
        replace(builtins,'open',checked_open(opener));replace(io,'open',checked_open(io_opener));replace(os,'open',raw_open)
        replace(builtins,'__import__',checked_import)
        for key in ('run','Popen','call','check_call','check_output'):replace(subprocess,key,forbidden)
        for key in ('system','startfile','popen','replace','rename','remove','unlink','mkdir','rmdir'):replace(os,key,forbidden)
        for key in dir(os):
            if key.startswith(('spawn','exec')):replace(os,key,forbidden)
        replace(pickle,'load',selection_only);replace(pickle,'loads',forbidden);replace(pickle,'Unpickler',forbidden)
        # Also block already-imported DB APIs; do not import a database driver.
        import sys
        for name in ('sqlite3','psycopg2'):
            if name in sys.modules:replace(sys.modules[name],'connect',forbidden)
        yield
    finally:
        for obj,key,value in reversed(saved):setattr(obj,key,value)


def required_files(plan,states=None):
    required=set('plan.json review.json source_before.json source_after.json controller.json stdout.log stderr.log worker.json resource.json'.split())
    if plan['kind']=='CATALOG':
        if plan.get('population',{}).get('name')=='GOLDEN_200K':required.add('selected_rows.json')
        return required|{'catalog.json','sample_scan.json'}
    require=routes.require;jobs=plan['jobs'];ids=[j['job_id'] for j in jobs]
    require(len(ids)==len(set(ids)) and states is not None and set(states)==set(ids),'Independent complete unique job-state set required')
    required|={'queries.json','evaluation.json','support.json'}
    for i,j in enumerate(jobs):
        prefix='jobs/%04d/'%i
        required|={prefix+n for n in ('request.json','fit.json','native.json','result.json','result.seal.json','engine.log')}
        require(states[j['job_id']] in ('PASS','FIT_ERROR','NOT_ATTEMPTED_EMPTY_FIXED_SAMPLE'),'Known original fit state required')
        if states[j['job_id']]=='PASS':required.add(prefix+'model.pkl')
    return required


def check_required(plan,states,files,auxiliary=()):
    routes.require(set(files)==required_files(plan,states)|set(auxiliary),'Exact independent route evidence required set differs')


def decode_number(value):
    if value is None or type(value) in (int,float):return value
    routes.require(isinstance(value,dict) and set(value)=={'nonfinite_float'} and value['nonfinite_float'] in ('nan','inf','-inf'),'Explicit nonfinite native value encoding required')
    return float(value['nonfinite_float'])


def derive_result(job,fit,native):
    routes.require(type(native.get('api_calls')) is int and native['api_calls'] in (0,1),'Exact zero/one original native invocation required')
    if native['api_calls']==0:
        routes.require(native==dict(api_calls=0,kde_calls=0,kde_evaluations=0,seconds=0.,value=None,error=None),'Zero-call gap cannot hide KDE work/native output')
    else:
        routes.require(isinstance(native.get('warnings'),list) and all(isinstance(w,str) for w in native['warnings']) and
            (native.get('error') is None or isinstance(native['error'],dict) and set(native['error'])=={'type','message','traceback'} and all(isinstance(v,str) for v in native['error'].values())),
            'Raw original warning/error diagnostics required')
    result=dict(status='UNAVAILABLE_FIXED_SAMPLE',estimate=None,integral_verified=False,oracle=None)
    if fit['status']=='NOT_ATTEMPTED_EMPTY_FIXED_SAMPLE':
        routes.require(not job['xs'] and native['api_calls']==0,'Nonempty fit cannot become empty-sample gap');return result
    if fit['status']=='FIT_ERROR':
        routes.require(bool(job['xs']) and native['api_calls']==0,'Invalid original fit-error/no-call accounting');return dict(result,status='FIT_ERROR')
    routes.require(fit['status']=='PASS' and bool(job['xs']) and fit.get('attempted') is True and
        all(type(fit.get(k)) in (int,float) and math.isfinite(fit[k]) for k in ('slope','intercept','bandwidth','seconds')) and fit['bandwidth']==1. and fit['seconds']>=0,'Original1D LR/Gaussian fit evidence required')
    lower,upper=min(job['xs'])-12.,max(job['xs'])+12.;result.update(lower=lower,upper=upper)
    if math.ceil((upper-lower)/(4.*fit['bandwidth']))>10000:
        routes.require(native['api_calls']==0,'Numerical-budget gap cannot hide an actual call');return dict(result,status='NUMERICAL_BUDGET_UNSUPPORTED')
    routes.require(native['api_calls']==1 and all(type(native.get(k)) is int and native[k]>0 for k in ('kde_calls','kde_evaluations')) and native['kde_evaluations']>=native['kde_calls'] and
        type(native.get('seconds')) in (int,float) and math.isfinite(native['seconds']) and native['seconds']>=0,'Exact original method-call/time/KDE counters required')
    expected=routes.gaussian_oracle(job['xs'],fit['slope'],fit['intercept'],fit['bandwidth'],lower,upper,job['population_metadata']['Nhat']);result['oracle']=expected
    value=decode_number(native['value']);result['estimate']=value
    if native['error'] is not None:result['status']='NATIVE_ERROR'
    elif value is None:result['status']='NATIVE_NULL'
    elif type(value) not in (int,float) or not math.isfinite(value):result.update(status='NATIVE_NONFINITE',estimate=None,nonfinite_value=repr(value))
    else:
        oracle=expected[job['aggregate']];difference=None if oracle is None else abs(value-oracle)
        passed=difference is not None and difference<=max(1e-5,abs(oracle)*1e-5)
        result.update(status='RETURNED' if passed else 'NUMERICAL_VALIDATION_FAILED',integral_verified=passed,oracle_absolute_error=difference)
    return result


def verify_job(home,job,binding):
    home=Path(home);request=strict_read(home/'request.json');result=strict_read(home/'result.json');fit=strict_read(home/'fit.json');native=strict_read(home/'native.json')
    routes.require(request==dict(job=job,binding=binding) and strict_read(home/'result.seal.json')==dict(sha256=ops.digest(home/'result.json'),request_sha256=ops.digest(home/'request.json')),
        'Exact query/group/component/request self seal differs')
    routes.require(result['backend']==ops.ORIGINAL_BACKEND and result['job']==job and result['native']==native and result['fit_attempted']==bool(job['xs']) and
        all(result[k]==job[k] for k in ('query_no','key','component','parent_sql_sha256')),'Pinned original backend/query/component identity differs')
    if fit['status']=='PASS':routes.require(fit['model_sha256']==ops.digest(home/'model.pkl') and fit['training_binding_sha256']==routes.value_hash(dict(
        job_binding=job['binding_sha256'],training_binding=binding['training_binding_sha256'])),'Actual original model bytes/training binding changed')
    elif fit['status']=='FIT_ERROR':routes.require(fit.get('attempted') is True and isinstance(fit.get('error'),dict) and set(fit['error'])=={'type','message','traceback'},'Original fit failure diagnostic missing')
    else:routes.require(fit==dict(status='NOT_ATTEMPTED_EMPTY_FIXED_SAMPLE',attempted=False),'Empty fit status changed')
    expected=derive_result(job,fit,native)
    if native['api_calls']:
        routes.require(native.get('compatibility_adapter')==ops.compatibility_record(expected['lower'],expected['upper'],fit['bandwidth']),
            'Exact original quadrature adapter/breakpoints/frozen source-failure provenance required')
    for key,value in expected.items():routes.require(result.get(key)==ops.safe_json(value),'Raw native versus independently derived job result differs: '+key)
    allowed={'query_no','key','component','parent_sql_sha256','job','backend','fit_attempted','native'}|set(expected)
    routes.require(set(result)==allowed,'Unaccounted job result fields');return result,fit['status']


def auxiliary_names(home):
    root=Path(home)/'auxiliary';names=set()
    for p in root.rglob('*') if root.exists() else []:
        if p.is_file():
            routes.require(root.resolve() in p.resolve().parents and p.suffix=='.json' and p.stat().st_size<=1024**2,'Only bounded local matplotlib JSON cache is allowed')
            names.add(p.relative_to(home).as_posix())
    return names


def verify(home):return _verify_from_boundary(home)


def _verify_from_boundary(home,boundary=None):
    home=Path(home).resolve();root=(ops.OUT/'runs').resolve();routes.require(root in home.parents,'Own new route namespace required')
    with forbid_operations():
        final=strict_read(home/'final.json');sha=ops.digest(home/'final.json');plan=strict_read(home/'plan.json')
        routes.require(strict_read(home/'final.seal.json')=={'sha256':sha} and strict_read(home/'lifecycle.json')==dict(status='PASS',final_sha256=sha),'Complete final self seal/PASS lifecycle required')
        routes.require(final.get('schema')=='dbest_routes_final_v1' and final.get('binding_sha256')==plan['binding_sha256'] and
            final.get('author_training_configuration_recovered') is False and final.get('full_paper_reproduction_complete') is False,'Independent route result scope changed')
        states={j['job_id']:strict_read(home/'jobs'/('%04d'%i)/'fit.json')['status'] for i,j in enumerate(plan.get('jobs',[]))}
        aux=auxiliary_names(home);check_required(plan,states,final.get('files',{}),aux)
        if boundary is None:boundary=ops._Boundary()
        ops._verify_plan_from_boundary(plan,boundary)
        ops.exact_approval(home/'review.json',final['review_sha256'],plan['binding_sha256'],plan['kind'])
        routes.require(strict_read(home/'source_before.json')==strict_read(home/'source_after.json')==plan['source'],'Original frozen dependency closure changed')
        results=[];states={}
        if plan['kind']=='ROUTES':
            for i,j in enumerate(plan['jobs']):
                r,state=verify_job(home/'jobs'/('%04d'%i),j,dict(evidence_plan_binding_sha256=plan['binding_sha256'],training_binding_sha256=plan['training_binding_sha256']));results.append(r);states[j['job_id']]=state
            queries=routes.assemble_queries(plan['jobs'],results)
            routes.require(strict_read(home/'queries.json')==queries and strict_read(home/'support.json')==routes.support_table(),'Exact new routes/raw4/prior reference support changed')
            truth=ops.read_truth(plan['population'])
            routes.require(strict_read(home/'evaluation.json')==routes.evaluate(queries,truth,plan['population']['population_rows']),'Post-prediction exact rational truth/gaps changed')
        else:
            catalog=strict_read(home/'catalog.json');routes.validate_catalog(catalog)
            scan=strict_read(home/'sample_scan.json')
            p=plan['population'];golden=p['name']=='GOLDEN_200K'
            routes.require(catalog['rows']==p['retained_rows'] and catalog['probability']==p['probability'] and scan['rows']==p['retained_rows'] and
                scan['sha256']==p['sample']['sha256'] and scan['bytes']==p['sample']['bytes'] and scan['aggregate_numeric_values_parsed'] is False and
                scan['aggregate_values_accumulated'] is False and scan['category_scans']==1 and scan['selected_rows']==(20000 if golden else 0) and
                type(scan['seconds']) in (int,float) and math.isfinite(scan['seconds']) and scan['seconds']>=0,
                'One complete same-source category-only scan required')
            if golden:
                selected=strict_read(home/'selected_rows.json');routes.validate_selected(selected)
                routes.require(selected['row_ids']==ops.selection_ids(p),'Golden selection rows must use original seed74031 IDs without additions')
        aux=auxiliary_names(home);check_required(plan,states,final['files'],aux)
        for name,record in final['files'].items():routes.require(ops.descriptor(home/name)==record,'Independent physical artifact differs: '+name)
        actual={p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}
        routes.require(actual==set(final['files'])|{'final.json','final.seal.json','lifecycle.json'},'Extra or missing actual route namespace artifacts')
        ops.validate_execution(home,plan,strict_read(home/'controller.json'),strict_read(home/'worker.json'),strict_read(home/'resource.json'))
        ops.validate_worker_results(plan,strict_read(home/'worker.json'),results)
        routes.require(ops.directory_bytes(home)<=ops.limits()['new_output_bytes'],'Completed own output cap exceeded')
    return dict(status='PASS_READONLY_ORIGINAL_DBEST_ROUTE_EVIDENCE_WITH_GAPS',kind=plan['kind'],final=ops.descriptor(home/'final.json'),
        plan=ops.descriptor(home/'plan.json'),source_complete_inventory_sha256=plan['source']['complete_inventory_sha256'],
        population=plan['population']['name'],native_verified_aggregates=sorted({r['job']['aggregate'] for r in results if r['status']=='RETURNED'}),
        numerical_validation_failures=sum(r['status']=='NUMERICAL_VALIDATION_FAILED' for r in results),
        native_calls=sum(r['native']['api_calls'] for r in results),native_fit_errors=sum(r['status']=='FIT_ERROR' for r in results),
        coverage_gaps=sum(r['status']!='RETURNED' for r in results),author_training_configuration_recovered=False,full_paper_reproduction_complete=False,
        files_written=False,models_loaded=False,scientific_calls_executed=False,processes_executed=False,database_connected=False)


def _verify_catalog_from_boundary(final_path,boundary):
    path=Path(final_path).resolve();routes.require(path.name=='final.json','Exact completed catalog final path required')
    result=_verify_from_boundary(path.parent,boundary)
    routes.require(result['kind']=='CATALOG','Category catalog cannot be replaced with fitted results')
    return dict(result,catalog=strict_read(path.parent/'catalog.json'),population=strict_read(path.parent/'plan.json')['population'])


def verify_catalog(final_path):return _verify_catalog_from_boundary(final_path,None)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['verify']);p.add_argument('--home',type=Path,required=True)
    a=p.parse_args(argv);print(json.dumps(verify(a.home),sort_keys=True,allow_nan=False))


if __name__=='__main__':main()
