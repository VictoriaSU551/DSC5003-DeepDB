"""Independent, process-forbidden audit of the accepted SF2 Verdict run.

No database, SQLite, JVM, model inference, compilation or repair is available.
The frozen runner is imported only after checking its exact source SHA.
"""
import argparse
import builtins
from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'output/full/verdict_ssb/runs/sf2_golden_v4'
CORE_SHA='e1416b4201ea22df9ca7abaa2ce5fecb38ee70ee716ede7323acdaeff778b5c8'
FINAL_SHA='44c4dee10977093f2edff72d21d57047a909bc56671cdc5ca37c75184cc8da8f'
HELPER_SHA='a9e9034efad01e258c521934aea43f0f405ff78c42caffb7841a73fd03d96784'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def load_core():
    p=ROOT/'code/full_verdict_ssb_run.py'
    if digest(p)!=CORE_SHA:raise ValueError('Accepted frozen Verdict runner changed')
    spec=importlib.util.spec_from_file_location('frozen_verdict_ssb_audit_core',str(p))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


@contextmanager
def forbid_science(core):
    def forbidden(*args,**kwargs):raise RuntimeError('Forbidden operational call during read-only SF2 audit')
    names=('connect','pg_control','start_owned_server','bounded_process','run_sf2','run_oracle','import_postgres','execute_original','adopt_oracle','adopt_registered_files')
    saved=[(core,n,getattr(core,n)) for n in names if hasattr(core,n)]
    saved += [(subprocess,n,getattr(subprocess,n)) for n in ('run','Popen','call','check_call','check_output')]
    saved += [(os,n,getattr(os,n)) for n in ('system','startfile','popen') if hasattr(os,n)]
    importer=builtins.__import__
    def checked_import(name,*args,**kwargs):
        if name.split('.')[0] in ('psycopg2','sqlite3'):forbidden()
        return importer(name,*args,**kwargs)
    try:
        for obj,name,unused in saved:setattr(obj,name,forbidden)
        builtins.__import__=checked_import
        yield
    finally:
        builtins.__import__=importer
        for obj,name,value in reversed(saved):setattr(obj,name,value)


def load_helper():
    path=ROOT/'code/full_windows_fingerprint.py'
    if digest(path)!=HELPER_SHA:raise ValueError('Reviewed native Windows helper changed')
    spec=importlib.util.spec_from_file_location('verdict_windows_fingerprint',str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def summarize_calls(plan,records):
    expected={c['call_id']:c for c in plan['queries']}
    if len(expected)!=38 or len(records)!=38:raise ValueError('Exactly 38 actual original native calls required')
    seen=set();modes={};per_call=[]
    for receipt in records:
        c=receipt['call'];qid=c['call_id'];r=receipt['result'];p=receipt['process']
        if qid in seen or qid not in expected or c!=expected[qid] or r['call']!=c:raise ValueError('Missing/duplicate/misidentified original native call')
        seen.add(qid)
        if type(r['elapsed_ns']) is not int or r['elapsed_ns']<0 or not finite(p['seconds']) or p['seconds']<0 or type(p['peak_rss_bytes']) is not int or p['peak_rss_bytes']<0:
            raise ValueError('Actual native/process timing or memory malformed')
        keys=set();ci=Counter();points=Counter()
        for row in r['rows']:
            key=tuple(row['key'])
            if key in keys:raise ValueError('Duplicate native group key')
            keys.add(key);points[row['point_status']]+=1;ci[row['ci_status']]+=1
            if row['point_status']=='FINITE' and not finite(row['point']):raise ValueError('Finite native point label hides nonfinite value')
            interval=row.get('interval95')
            if row['ci_status']=='FINITE' and (not isinstance(interval,list) or len(interval)!=2 or not all(finite(x) for x in interval) or interval[0]>interval[1]):
                raise ValueError('Finite native interval label hides unavailable/nonfinite endpoints')
        item=dict(call_id=qid,mode=c['mode'],role=c['role'],query_no=c['query_no'],sql_sha256=c['sql_sha256'],
            status=r['status'],engine_error=r['error'],rows=len(r['rows']),ci_status_counts=dict(ci),point_status_counts=dict(points),
            native_execute_fetch_seconds=r['elapsed_ns']/1e9,process_seconds=p['seconds'],process_peak_rss_bytes=p['peak_rss_bytes'])
        per_call.append(item)
    if seen!=set(expected):raise ValueError('Incomplete native query set')
    for mode in ('nobound','subsampling'):
        rows=[x for x in per_call if x['mode']==mode];ci=Counter();points=Counter()
        for row in rows:ci.update(row['ci_status_counts']);points.update(row['point_status_counts'])
        modes[mode]=dict(calls=len(rows),returned_rows=sum(x['rows'] for x in rows),
            engine_errors=sum(x['engine_error'] is not None for x in rows),empty_calls=[x['call_id'] for x in rows if not x['rows']],
            native_execute_fetch_seconds=sum(x['native_execute_fetch_seconds'] for x in rows),process_seconds=sum(x['process_seconds'] for x in rows),
            process_peak_rss_bytes=max(x['process_peak_rss_bytes'] for x in rows),ci_status_counts=dict(ci),point_status_counts=dict(points))
    return dict(original_calls=38,modes=modes,per_call=sorted(per_call,key=lambda x:x['call_id']),
        interval_scope='Physical original native results including six separate SUM children; adapter has no CI')


def population_counts(rows):
    truth=[r for r in rows if r.get('truth') is not None];missing=[r for r in truth if r['status']=='MISSING_MODEL_GROUP']
    relative=[];finite_ci=[]
    for r in truth:
        value=r.get('missing_penalty_relative_error') if r['status']=='MISSING_MODEL_GROUP' else r.get('relative_error')
        if value is not None:
            if not finite(value):raise ValueError('Nonfinite population error cannot be silently averaged')
            relative.append(value)
        if r.get('native_ci_status')=='FINITE':
            interval=r.get('native_ci95')
            if not isinstance(interval,list) or len(interval)!=2 or not all(finite(x) for x in interval):raise ValueError('Invalid finite population interval')
            if type(r.get('native_ci95_covers_truth')) is not bool:raise ValueError('Missing finite interval coverage indicator')
            finite_ci.append(r)
    covered=sum(r['native_ci95_covers_truth'] for r in finite_ci)
    return dict(truth_groups=len(truth),returned_groups=sum(r['status']!='MISSING_MODEL_GROUP' for r in truth),missing_groups=len(missing),
        extra_groups=sum(r['status']=='EXTRA_MODEL_GROUP' for r in rows),zero_truth_groups=sum(r.get('zero_truth') is True for r in truth),
        nonfinite_or_null_points=sum(r['status']!='MISSING_MODEL_GROUP' and r.get('point_status')!='FINITE' for r in truth),
        finite_ci_groups=len(finite_ci),covered_finite_ci_groups=covered,
        ci_unavailable_truth_groups=len(truth)-len(finite_ci),conditional_finite_ci_coverage=covered/len(finite_ci) if finite_ci else None,
        covered_fraction_all_truth_groups=covered/len(truth) if truth else None,
        mean_relative_error_with_missing_penalty=statistics.mean(relative) if relative else None,
        relative_error_denominator=len(relative),excluded_relative_error_groups=len(truth)-len(relative))


def summarize_population(evaluation):
    raw={};adapters={};per_query=[];unavailable=0
    for c in evaluation['comparisons']:
        call=c['call'];p=c['population_comparison']
        if call['role'] in ('SUM_REVENUE','SUM_SUPPLYCOST'):
            if p!={'status':'UNAVAILABLE_NO_MATCHING_FULL_POPULATION_COMPONENT_TRUTH','groups':None}:raise ValueError('Physical SUM child cannot inherit profit population truth')
            unavailable+=1;continue
        if call['role']!='RAW' or p['status']!='AVAILABLE_EXACT_EXPRESSION_TRUTH':raise ValueError('Unknown population expression contract')
        raw.setdefault(call['mode'],[]).extend(p['groups'])
        per_query.append(dict(query_no=call['query_no'],mode=call['mode'],**population_counts(p['groups'])))
    for a in evaluation['adapters']:adapters.setdefault(a['mode'],[]).extend(a['population_statistics'])
    return dict(raw13={m:population_counts(rows) for m,rows in raw.items()},profit_adapter={m:population_counts(rows) for m,rows in adapters.items()},
        per_query=per_query,physical_component_population_metrics_unavailable_calls=unavailable,
        scope='Full local SF2 integer truth; missing groups retained with 100% error penalty; finite-CI coverage conditional denominator explicit')


def summarize_resources(budget):
    samples=budget['samples']
    if not samples:raise ValueError('Resource history empty')
    lsn=budget.get('wal_lsn_before')
    generated=[x['wal_generated_bytes'] for x in samples if 'wal_generated_bytes' in x]
    return dict(samples=len(samples),peak_total_bytes=budget['peak_total_bytes'],
        python_peak_rss_bytes=max(x['python_rss_bytes'] for x in samples),owned_database_bytes=max(x['owned_database_bytes'] for x in samples),
        positive_physical_wal_growth_bytes=max(x['positive_wal_bytes'] for x in samples),positive_temp_growth_bytes=max(x['positive_temp_bytes'] for x in samples),
        reused_sqlite_bytes=budget['reused_oracle_bytes'],wal_generated_bytes=max(generated) if lsn is not None and generated else None,
        wal_generated_status='RECORDED_LSN_WINDOW' if lsn is not None and generated else 'UNRECORDED_NO_LSN_BASELINE')


def audit():
    core=load_core();helper=load_helper()
    if digest(HOME/'final.json')!=FINAL_SHA:raise ValueError('Accepted SF2 final manifest differs')
    plan=read(HOME/'plan.json')
    with forbid_science(core):
        with helper.verified_platform(plan['runtime']['platform'],plan['runtime']['machine']) as identity:
            verification=core.verify_run(HOME)
    records=[read(HOME/'calls'/c['call_id']/'receipt.json') for c in plan['queries']]
    evaluation=read(HOME/'evaluation.json');final=read(HOME/'final.json');post=read(HOME/'post_run.json');snapshot=read(HOME/'registered_pg_snapshot.json')
    calls=summarize_calls(plan,records);population=summarize_population(evaluation)
    checks=[g for c in evaluation['comparisons'] if c['call']['mode']=='nobound' and c['call']['role']=='RAW' and c['call']['query_no']<10 for g in c['groups']]
    checks += [g for a in evaluation['adapters'] if a['mode']=='nobound' for g in a['groups']]
    if not checks or not all(g['numeric_gate_pass'] for g in checks):raise ValueError('Required actual retained-sample point scaling gate failed')
    raw_profit=[g for c in evaluation['comparisons'] if c['call']['role']=='RAW' and c['call']['mode']=='nobound' and c['call']['query_no']>=10 for g in c['groups']]
    return dict(schema='verdict_ssb_sf2_readonly_audit_v1',status='PASS_ACCEPTED_SF2_READONLY_AUDIT_WITH_EXPLICIT_GAPS',
        source_sha256=CORE_SHA,accepted_final_sha256=FINAL_SHA,audit_source_sha256=digest(__file__),core_verification=verification,
        native_platform_adapter=identity,guard=dict(process_launch='FORBIDDEN',postgres_connect='FORBIDDEN',sqlite_import_connect='FORBIDDEN',java_compile_query='FORBIDDEN',prediction='No model/native prediction; only existing evidence derivation'),
        population_rows=11997996,sample_rows=39587,verdict_sampling_ratio=dict(numerator=39587,denominator=11997996),generator_probability=plan['source_audit']['scaling']['generator_probability'],
        phases=final['steps_reexecuted'],calls=calls,population=population,resources=summarize_resources(read(HOME/'budget.json')),
        retained_sample_scaling=dict(required_groups=len(checks),passed_groups=sum(g['numeric_gate_pass'] for g in checks),raw_profit_nobound_groups=len(raw_profit),raw_profit_nobound_failed_groups=sum(not g['numeric_gate_pass'] for g in raw_profit),adapter_ci='UNSUPPORTED_NO_COVARIANCE_MODEL'),
        native_pg_audit_seconds=snapshot['canonical_reverification_seconds'],share_lock_begin=post['lock_begin'][0],share_lock_end=post['lock_end'][0],
        own_pg_stopped_receipt=read(HOME/'server.json')['status'],physical_closure=dict(result_files=len(final['files']),pg_control_files=len(final['pg_control_files']),source_runtime_input_files=len(plan['source_runtime_files']),registered_adoption_files=len(plan['registered_reuse']['files'])),
        failed_v2_v3_preserved=True,formal_allowed=False,author_population_fidelity_claim=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args(argv)
    p=None
    if args.output:
        p=args.output.resolve();allowed=(ROOT/'output/full/verdict_ssb/audits').resolve()
        if allowed not in p.parents:raise ValueError('Audit output must be inside the independent audits namespace')
        if p.exists():raise FileExistsError('Refuse existing audit output: '+str(p))
    result=audit();encoded=json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n'
    if p is not None:
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('x',encoding='utf-8',newline='\n') as out:out.write(encoded)
    else:print(encoded,end='')


if __name__=='__main__':main()
