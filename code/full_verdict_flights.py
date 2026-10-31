"""Existing-sample-only original Verdict execution in an isolated PostgreSQL DB."""
import argparse
import base64
import csv
from fractions import Fraction
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import re
import time

from full_common import binding_hash as bhash
import full_verdict as v
from full_verdict import ROOT,DATA,OUT,digest,atomic_json

COLUMNS=('YEAR_DATE','UNIQUE_CARRIER','ORIGIN','ORIGIN_STATE_ABR','DEST','DEST_STATE_ABR',
         'DEP_DELAY','TAXI_OUT','TAXI_IN','ARR_DELAY','AIR_TIME','DISTANCE')
SQL_PATH=ROOT/'code/benchmarks/flights/sql/aqp_queries.sql'
NAMES=('F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2')
SAMPLE_TABLE='public_verdict.vs_flights_uf_0_0100'


def projection_plan(sql):
    match=re.search(r'SUM\((\w+)\)\s*-\s*SUM\((\w+)\)',sql,re.I)
    children=[] if match is None else [sql[:match.start()]+'SUM('+column+')'+sql[match.end():] for column in match.groups()]
    return dict(raw_sql=sql,adapter_sqls=children,adapter_ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL' if children else None)


def source_contract(report_path,checkpoint_path,sample):
    report=json.loads(Path(report_path).read_text());checkpoint=json.loads(Path(checkpoint_path).read_text())
    sealed=checkpoint.pop('checkpoint_sha256',None)
    if sealed!=bhash(checkpoint) or checkpoint['binding']!=bhash(checkpoint['binding_details']):raise ValueError('generation seal differs')
    expected=checkpoint['files']['sample.csv'];n=report['sample_rows'];N=report['rows_generated']
    if (report['status']!='PASS' or N!=1000000000 or checkpoint['rows_generated']!=N or
        checkpoint['binding_details']['config']['rows']!=N or checkpoint['sample_rows']!=n or
        report['binding']!=checkpoint['binding'] or not report['paper_scale_reached'] or
        not 0<n<=10000000 or report['files']['sample.csv']!=expected):raise ValueError('generation incomplete or population/sample differs')
    if Path(sample).stat().st_size!=expected['offset'] or digest(sample)!=expected['sha256']:raise ValueError('sealed sample changed')
    with Path(sample).open(newline='',encoding='utf-8') as stream:
        if tuple(next(csv.reader(stream)))!=COLUMNS:raise ValueError('sample header differs')
    return dict(population_rows=N,sample_rows=n,sample_sha256=expected['sha256'],sample_bytes=expected['offset'],
                generation_binding=checkpoint['binding'],generation_checkpoint_sha256=sealed,
                query_truth_used_for_registration=False,information_budget=['schema','uniform sample','actual n','population N'])


def compare_groups(truth,predictions,error=None):
    true={tuple(g['key']):float(Fraction(int(g['numerator']),int(g['denominator']))) for g in truth}
    result=[]
    for key in sorted(set(true)|set(predictions),key=repr):
        actual=true.get(key);pred=predictions.get(key)
        status='EXTRA_MODEL_GROUP' if key not in true else 'MISSING_MODEL_GROUP' if key not in predictions else 'MATCHED'
        ae=abs(pred-actual) if pred is not None and actual is not None else None
        result.append(dict(key=list(key),truth=actual,prediction=pred,status=status,zero_truth=actual==0,
                           absolute_error=ae,relative_error=ae/abs(actual) if ae is not None and actual!=0 else None,engine_error=error))
    return result


def connect(db='deepdb_verdict',readonly=False):
    import psycopg2
    connection=psycopg2.connect(host='localhost',port=55432,user='postgres',dbname=db,connect_timeout=10,
        options='-c statement_timeout=120000 -c work_mem=16384',application_name='deepdb_verdict_sample_only')
    connection.set_session(readonly=readonly);return connection


def job_identity():
    connection=connect('deepdb_job',True)
    try:
        with connection.cursor() as c:
            c.execute('SELECT relname,n_tup_ins,n_tup_upd,n_tup_del FROM pg_stat_user_tables ORDER BY relname');stats=c.fetchall()
            c.execute("SELECT relname,oid,relfilenode FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' ORDER BY relname");files=c.fetchall()
        return dict(statistics=stats,relation_files=files)
    finally:connection.close()


def budget(connection,base_files,wal_initial):
    with connection.cursor() as c:
        c.execute('SELECT pg_database_size(current_database())');db_bytes=c.fetchone()[0]
        c.execute('SHOW data_directory');wal=Path(c.fetchone()[0])/'pg_wal'
    wal_bytes=sum(p.stat().st_size for p in wal.iterdir() if p.is_file())
    total=base_files+db_bytes+max(0,wal_bytes-wal_initial)
    if total>8*v.GIB:raise ValueError('Verdict filesystem+database+new WAL exceeds8GiB')
    return dict(filesystem_bytes=base_files,database_bytes=db_bytes,new_wal_bytes=max(0,wal_bytes-wal_initial),total_new_bytes=total)


def import_sample():
    gate=json.loads((OUT/'golden_gate.json').read_text())
    if gate['status']!='PASS_STANDARD_AND_REGISTERED_SAMPLE_EQUIVALENCE' or gate['successful_engine_queries']!=24:
        raise ValueError('complete original-engine small gate required')
    source=ROOT/'data/flights/generated/flights-1b/sample.csv'
    generation=ROOT/'output/full/flights/flights-1b'
    contract=source_contract(generation/'generation_result.json',generation/'checkpoint.json',source)
    binding=dict(source=contract,columns=COLUMNS,nominal_sampling_ratio=.01,actual_probability='actual_n/1000000000',
                 partition='original mod(round(random()*100)::integer,100); PostgreSQL setseed0.271828',
                 import_function=hashlib.sha256(inspect.getsource(import_sample).encode()).hexdigest())
    key=bhash(binding);connection=connect();monitor=connect(readonly=True)
    try:
        with connection.cursor() as c:
            c.execute('CREATE SCHEMA IF NOT EXISTS verdict_input')
            c.execute('CREATE TABLE IF NOT EXISTS verdict_input.stages(stage text PRIMARY KEY,binding text NOT NULL,receipt jsonb NOT NULL)')
        connection.commit()
        with connection.cursor() as c:
            c.execute('SELECT binding,receipt FROM verdict_input.stages WHERE stage=%s',('augmented',));saved=c.fetchone()
        if saved:
            if saved[0]!=key:raise ValueError('completed import binding differs; refuse overwrite')
            receipt=saved[1];atomic_json(OUT/'flights_import.json',receipt);return receipt
        before=job_identity()
        with monitor.cursor() as c:
            c.execute('SHOW data_directory');wal=Path(c.fetchone()[0])/'pg_wal'
        wal_initial=sum(p.stat().st_size for p in wal.iterdir() if p.is_file());base=v.owned_disk_bytes()
        memory=[];started=time.monotonic();raw_stage=None
        with connection.cursor() as c:
            c.execute('SELECT binding,receipt FROM verdict_input.stages WHERE stage=%s',('raw',));saved=c.fetchone()
            if saved:
                if saved[0]!=key:raise ValueError('raw sample import binding differs')
                raw_stage=saved[1]
            else:
                ddl=','.join(name.lower()+(' integer' if i==0 else ' text' if 1<=i<=5 else ' double precision') for i,name in enumerate(COLUMNS))
                c.execute('CREATE TABLE verdict_input.flights_retained_raw('+ddl+')')
                copied=0;import_started=time.monotonic()
                with source.open('rb') as stream:
                    header=stream.readline()
                    while True:
                        lines=[]
                        for _ in range(100000):
                            line=stream.readline()
                            if not line:break
                            lines.append(line)
                        if not lines:break
                        c.copy_expert('COPY verdict_input.flights_retained_raw FROM STDIN WITH CSV',io.BytesIO(b''.join(lines)))
                        copied+=len(lines)
                        usage=budget(monitor,base,wal_initial);memory.append(dict(rows=copied,seconds=time.monotonic()-import_started,**usage))
                        print('VERDICT_IMPORTED_ROWS',copied,flush=True)
                c.execute('SELECT COUNT(*) FROM verdict_input.flights_retained_raw');actual=c.fetchone()[0]
                if actual!=contract['sample_rows'] or copied!=actual:raise ValueError('actual imported sample row count differs')
                raw_stage=dict(actual_rows=actual,copy_seconds=time.monotonic()-import_started,source_sha256=contract['sample_sha256'])
                c.execute('INSERT INTO verdict_input.stages VALUES(%s,%s,%s)',('raw',key,json.dumps(raw_stage)))
                connection.commit()
            c.execute('CREATE SCHEMA IF NOT EXISTS public_verdict')
            c.execute('CREATE TABLE IF NOT EXISTS public.flights(LIKE verdict_input.flights_retained_raw)')
            c.execute('SELECT COUNT(*) FROM public.flights')
            if c.fetchone()[0]!=0:raise ValueError('original Flights must remain schema-only')
            c.execute('SELECT setseed(0.271828)')
            augment_started=time.monotonic()
            augment_sql=('CREATE TABLE '+SAMPLE_TABLE+' AS SELECT *, '
                'CAST('+str(contract['sample_rows'])+' AS double precision)/CAST(1000000000 AS double precision) AS verdict_vprob, '
                'mod(CAST(round(random()*100) AS integer),100) AS verdict_vpart FROM verdict_input.flights_retained_raw')
            c.execute(augment_sql);augment_seconds=time.monotonic()-augment_started
            usage=budget(monitor,base,wal_initial);memory.append(dict(stage='augmented',**usage))
            c.execute('SELECT COUNT(*),MIN(verdict_vprob),MAX(verdict_vprob),MIN(verdict_vpart),MAX(verdict_vpart) FROM '+SAMPLE_TABLE)
            actual,lo,hi,pmin,pmax=c.fetchone()
            if actual!=contract['sample_rows'] or lo!=hi or not math.isclose(lo,actual/1e9,rel_tol=1e-12):raise ValueError('actual augmented sample/probability differs')
            c.execute('SELECT verdict_vpart,COUNT(*) FROM '+SAMPLE_TABLE+' GROUP BY verdict_vpart ORDER BY verdict_vpart');parts=c.fetchall()
            c.execute('DROP TABLE verdict_input.flights_retained_raw')
            after=job_identity()
            if before!=after:raise ValueError('protected IMDb database identity changed')
            receipt=dict(status='PASS_EXISTING_UNIFORM_SAMPLE_IMPORTED',binding=binding,binding_sha256=key,source=contract,
                actual_sample_rows=actual,original_rows=0,population_prior=1000000000,probability=lo,partition_histogram=parts,
                copy_seconds=raw_stage['copy_seconds'],probability_partition_build_seconds=augment_seconds,
                import_to_augmented_wall_seconds=time.monotonic()-started,augment_sql=augment_sql,raw_copy_released=True,
                budget_samples=memory,budget_peak_bytes=max(r['total_new_bytes'] for r in memory),
                statement_timeout_ms=120000,work_mem_kib=16384,protected_job_before=before,protected_job_after=after,
                scope='Already materialized uniform sample only; no1B original table or original-table sampling cost')
            c.execute('INSERT INTO verdict_input.stages VALUES(%s,%s,%s)',('augmented',key,json.dumps(receipt)))
            connection.commit()
        atomic_json(OUT/'flights_import.json',receipt);return receipt
    finally:connection.close();monitor.close()


def compile_bridge():
    java=next((ROOT/'.runtime/java').glob('*/bin/java.exe'));classes=DATA/'bridge_classes'
    record=v.run_bounded([java.with_name('javac.exe'),'-J-Xmx256m','-encoding','UTF-8','-cp',str(classes)+os.pathsep+str(v.runtime_jar()),
                          '-d',classes,ROOT/'code/full_verdict_flights.java'],'flights_bridge_compile',90)
    if record['exit_code']!=0:raise ValueError('formal Verdict bridge compile failed')
    return java,classes


def register_sample():
    prepared_path=OUT/'flights_import.json'
    prepared=json.loads(prepared_path.read_text()) if prepared_path.exists() else import_sample()
    receipt=OUT/'flights_registration.json'
    if receipt.exists():
        result=json.loads(receipt.read_text())
        if result['import_binding']!=prepared['binding_sha256']:raise ValueError('registration binding differs')
        return result
    java,classes=compile_bridge()
    result=v.run_bounded([java,'-Xmx384m','-XX:MaxMetaspaceSize=192m','-cp',str(classes)+os.pathsep+str(v.runtime_jar()),
                          'full_verdict_flights','register',str(prepared['actual_sample_rows'])],'flights_register',120)
    if result['exit_code']!=0:raise ValueError('original metadata registration failed')
    result.update(status='PASS_ORIGINAL_METADATA_REGISTERED',import_binding=prepared['binding_sha256'],
                  population_prior=1000000000,actual_sample_rows=prepared['actual_sample_rows'],query_truth_used_for_registration=False)
    atomic_json(receipt,result);return result


def execute_queries():
    register_sample();java=next((ROOT/'.runtime/java').glob('*/bin/java.exe'));classes=DATA/'bridge_classes'
    sqls=SQL_PATH.read_text().splitlines();plans=[]
    for name,sql in zip(NAMES,sqls):
        plans.append((name+'.raw',sql))
        for i,child in enumerate(projection_plan(sql)['adapter_sqls']):plans.append((name+'.adapter'+str(i),child))
    input_path=OUT/'flights_engine_sql.tsv';payload=''.join(name+'\t'+base64.b64encode(sql.encode()).decode()+'\n' for name,sql in plans)
    if input_path.exists() and input_path.read_text()!=payload:raise ValueError('formal SQL input plan changed')
    if not input_path.exists():input_path.write_text(payload)
    for method in ['nobound','subsampling']:
        record=v.run_bounded([java,'-Xmx384m','-XX:MaxMetaspaceSize=192m','-cp',str(classes)+os.pathsep+str(v.runtime_jar()),
            'full_verdict_flights','query',method,input_path,OUT/('flights_'+method+'.tsv')],'flights_'+method,1200)
        if record['exit_code']!=0:raise ValueError('formal engine process failed; completed query checkpoints retained')
    return evaluate()


def read_engine(path):
    result={}
    def decode(value):return None if value=='N' else base64.b64decode(value[1:]).decode()
    for line in Path(path).read_text().splitlines():
        fields=line.split('\t');kind,qid=fields[:2];item=result.setdefault(qid,dict(rows=[],columns=[],error=None))
        if kind=='ROW':item['rows'].append([decode(v) for v in fields[2:]])
        elif kind=='META':item['columns']=[decode(v) for v in fields[2:]]
        elif kind=='ERROR':item['error']=decode(fields[2])
        elif kind=='TIME':item['engine_wall_ms']=float(fields[2])/1e6;item['complete']=True
    return result


def evaluate():
    # Truth is first read after sample import and original metadata registration.
    registration=json.loads((OUT/'flights_registration.json').read_text())
    if registration['status']!='PASS_ORIGINAL_METADATA_REGISTERED':raise ValueError('registration not complete')
    truth_path=ROOT/'output/full/flights/flights-1b/ground_truth.json';truth=json.loads(truth_path.read_text())
    if not truth['complete'] or truth['population_rows']!=1000000000:raise ValueError('evaluation truth incomplete')
    point=read_engine(OUT/'flights_nobound.tsv');ci=read_engine(OUT/'flights_subsampling.tsv');queries=[]
    def key_value(row,grouped):
        k=row[:1] if grouped else [];value=row[1 if grouped else 0]
        key=tuple(int(x) if x is not None and re.fullmatch(r'-?\d+',x) else x for x in k)
        return key,None if value is None else float(value)
    for name,sql,true in zip(NAMES,SQL_PATH.read_text().splitlines(),truth['queries']):
        if re.sub(r'\s+','',sql)!=re.sub(r'\s+','',true['sql']):raise ValueError('truth SQL alignment differs')
        grouped='GROUP BY' in sql.upper();raw=point[name+'.raw'];raw_map=dict(key_value(r,grouped) for r in raw['rows'])
        rows=compare_groups(true['groups'],raw_map,raw['error']);plan=projection_plan(sql)
        intervals={};native_details={};native_ci=ci[name+'.raw'];position=2 if grouped else 1
        for r in native_ci['rows']:
            key,value=key_value(r,grouped)
            if len(r)>position and r[position] is not None:
                half=float(r[position])
                native_details[key]=dict(point=value,error_bound=half)
                if value is not None and math.isfinite(half) and half>=0:intervals[key]=[value-half,value+half]
        for row in rows:
            bounds=intervals.get(tuple(row['key']));row['native_95pct_interval']=bounds
            row['native_ci_original_values']=native_details.get(tuple(row['key']))
            row['native_ci_status']=('UNSUPPORTED_RAW_COMPOUND_SUM' if plan['adapter_sqls'] else
                'ENGINE_ERROR' if native_ci['error'] else 'AVAILABLE_ORIGINAL_NATIVE95' if bounds else 'UNAVAILABLE_NULL_ABSENT_OR_INVALID_BOUND')
            row['native_ci_covers_truth']=(bounds[0]<=row['truth']<=bounds[1]) if bounds and row['truth'] is not None else None
        adapted=None
        if plan['adapter_sqls']:
            left,right=point[name+'.adapter0'],point[name+'.adapter1']
            lm=dict(key_value(r,grouped) for r in left['rows']);rm=dict(key_value(r,grouped) for r in right['rows'])
            amap={k:v.compound_sum_adapter(lm[k],rm[k]) for k in set(lm)&set(rm)}
            adapted=dict(status='ADAPTED_TWO_ORIGINAL_TOP_LEVEL_SUMS',groups=compare_groups(true['groups'],amap,left['error'] or right['error']),
                physical_sql_calls=2,engine_wall_ms=left.get('engine_wall_ms',0)+right.get('engine_wall_ms',0),
                ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL',children=dict(left=left,right=right),
                native_ci_children=dict(left=ci[name+'.adapter0'],right=ci[name+'.adapter1']))
            adapted['missing']=sum(r['status']=='MISSING_MODEL_GROUP' for r in adapted['groups'])
            adapted['extra']=sum(r['status']=='EXTRA_MODEL_GROUP' for r in adapted['groups'])
        queries.append(dict(query_name=name,sql=sql,raw_status='INCORRECT_RAW_UNSCALED_COMPOUND_SUM' if adapted else
                    'ENGINE_ERROR' if raw['error'] else 'EXECUTED_RAW_ORIGINAL',raw=raw,groups=rows,
                    native_ci=native_ci,native_ci_confidence=.95,adapted=adapted,
                    missing=sum(r['status']=='MISSING_MODEL_GROUP' for r in rows),extra=sum(r['status']=='EXTRA_MODEL_GROUP' for r in rows)))
    result=dict(status='COMPLETED_SAMPLE_ONLY_ORIGINAL_ENGINE_WITH_EXPLICIT_RAW_COMPOUND_LIMITATION',
        scope='Existing9997912-row uniform sample; original table schema-only; N1B is prior metadata',
        population_prior=1000000000,actual_sample_rows=9997912,queries=queries,
        native_ci_method='Original subsampling100 partitions, original default95pct; no adapter CI composition',
        query_truth_used_for_registration=False,truth_sha256=digest(truth_path),sql_sha256=digest(SQL_PATH),
        timing='Java engine call wall includes rewriting, physical SQL and result fetching; excludes process startup, import and aux-column building. Not pure server SQL or paper end-to-end latency.')
    atomic_json(OUT/'flights_evaluation.json',result);return result


def capture_post_run_snapshot():
    connection=connect(readonly=True)
    connection.set_session(readonly=True,isolation_level='REPEATABLE READ')
    try:
        with connection.cursor() as c:
            c.execute("SELECT clock_timestamp()::text,txid_current_snapshot()::text,current_setting('transaction_read_only'),current_setting('transaction_isolation')")
            begin=c.fetchone()
            c.execute('SELECT COUNT(*) FROM public.flights');empty=c.fetchone()[0]
            c.execute('SELECT COUNT(*),MIN(verdict_vprob),MAX(verdict_vprob),MIN(verdict_vpart),MAX(verdict_vpart) FROM '+SAMPLE_TABLE);account=c.fetchone()
            c.execute('SELECT verdict_vpart,COUNT(*) FROM '+SAMPLE_TABLE+' GROUP BY verdict_vpart ORDER BY verdict_vpart');parts=c.fetchall()
            c.execute("SELECT c.oid,c.relfilenode,s.n_tup_ins,s.n_tup_upd,s.n_tup_del FROM pg_class c JOIN pg_stat_user_tables s ON c.oid=s.relid WHERE c.oid=%s::regclass",(SAMPLE_TABLE,));identity=c.fetchone()
            c.execute('SELECT * FROM public_verdict.verdict_meta_size WHERE tablename=%s',('vs_flights_uf_0_0100',));size_meta=c.fetchall()
            c.execute('SELECT * FROM public_verdict.verdict_meta_name WHERE originaltablename=%s',('flights',));name_meta=c.fetchall()
            c.execute('SELECT clock_timestamp()::text,pg_database_size(current_database())');end=c.fetchone()
        if (empty!=0 or account[:3]!=(9997912,.009997912,.009997912) or len(parts)!=100 or
            sum(n for _,n in parts)!=9997912 or identity[3:]!=(0,0)):
            raise ValueError('post-run sample accounting or modification identity differs')
        result=dict(status='PASS_POST_RUN_READ_ONLY_RR_ACCOUNTING_SNAPSHOT',transaction_begin=begin,transaction_end=end[0],
            original_rows=empty,sample_count_probability_partition_range=account,partition_histogram=parts,
            sample_relation_identity_and_insert_update_delete_stats=identity,native_size_metadata=size_meta,native_name_metadata=name_meta,
            database_bytes=end[1],filesystem_bytes=v.owned_disk_bytes(),protected_job_identity=job_identity(),
            evidence_scope='Post-run RR snapshot and historical import/runtime evidence. Initial completed SQL calls did not hold an explicit freeze lock. This is not a current per-row content hash or a proof that relstats alone certify data values.')
        atomic_json(OUT/'flights_post_run_snapshot.json',result);return result
    finally:connection.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','register','evaluate','snapshot','all'])
    args=parser.parse_args()
    result=(import_sample() if args.action=='prepare' else register_sample() if args.action=='register' else evaluate() if args.action=='evaluate'
            else capture_post_run_snapshot() if args.action=='snapshot' else execute_queries())
    print(json.dumps({k:r for k,r in result.items() if k not in ['queries','budget_samples','binding']},default=str))


if __name__=='__main__':main()
