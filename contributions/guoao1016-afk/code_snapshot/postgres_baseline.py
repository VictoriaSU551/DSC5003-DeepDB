"""Local PostgreSQL JOB-light estimate baseline; never executes workload queries."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime
import psycopg2
from psycopg2 import sql
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
PG = Path(os.environ.get('DEEPDB_PG_HOME', str(ROOT / 'tools/postgresql')))
BIN = PG / 'pgsql/bin'
DATA = PG / 'data'
OUT = PROJECT / 'output/postgresql_baseline_20261015'
OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / 'run.json'
started = time.perf_counter()
record = {'status': 'RUNNING', 'started_at': datetime.now().astimezone().isoformat(),
          'scope': 'PostgreSQL estimates only; official truth; no workload execution or RDC training',
          'port': 55432, 'tables': {}, 'stages': {}}
record['postgres_home']=str(PG)
record['invocation']='python -u code/postgres_baseline.py (DEEPDB_PG_HOME points to local PostgreSQL directory)'
if STATE.exists():
    old = json.loads(STATE.read_text(encoding='utf-8'))
    if old.get('status') == 'PASS':
        print('Already complete. No experiment rerun.', flush=True)
        sys.exit(0)
    record['previous_attempt'] = old

def save():
    record['elapsed_seconds'] = time.perf_counter() - started
    STATE.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')

def progress(message):
    record['stage'] = message
    save()
    print(datetime.now().strftime('%H:%M:%S'), message, flush=True)
    with (OUT/'progress.log').open('a', encoding='utf-8') as f:
        f.write(datetime.now().isoformat()+' '+message+'\n')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(4*1024*1024), b''): h.update(part)
    return h.hexdigest()

def command(args, name, timeout=180):
    with (OUT/(name+'.log')).open('wb') as f:
        p=subprocess.run([str(x) for x in args], stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode:
        raise RuntimeError(name+' failed: '+(OUT/(name+'.log')).read_text(encoding='utf-8', errors='replace')[-3000:])

def connect(database):
    c=psycopg2.connect(host='127.0.0.1',port=55432,user='deepdb_local',password=password,dbname=database,connect_timeout=10)
    c.autocommit=True
    return c

class CopyProgress:
    def __init__(self, f, name):
        self.f=f; self.name=name; self.last=time.monotonic(); self.total=os.fstat(f.fileno()).st_size
    def read(self, size):
        chunk=self.f.read(size)
        if time.monotonic()-self.last>10:
            print('  Import %s: %.1f%%'%(self.name,100*self.f.tell()/self.total),flush=True)
            self.last=time.monotonic()
        return chunk

try:
    progress('1/6 Check program, dataset hashes and saved DeepDB results')
    record['script_sha256']=sha(Path(__file__))
    manifest=json.loads((PROJECT/'data/manifest.json').read_text(encoding='utf-8'))
    expected=json.loads((PROJECT/'output/results/data_audit.json').read_text(encoding='utf-8'))['row_counts']
    for item in manifest['files']:
        path=PROJECT/'data'/item['path']
        assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256'], str(path)
    record['manifest_sha256']=sha(PROJECT/'data/manifest.json')
    cfg_path=PG/'local_credentials.json'
    if cfg_path.exists():
        password=json.loads(cfg_path.read_text(encoding='utf-8'))['password']
    else:
        password=secrets.token_urlsafe(32)
        cfg_path.write_text(json.dumps({'user':'deepdb_local','password':password,'port':55432}),encoding='utf-8')
    if not (DATA/'PG_VERSION').exists():
        progress('2/6 Initialize isolated local database (localhost only)')
        pw=PG/'init_password.tmp'
        pw.write_text(password+'\n',encoding='utf-8')
        try:
            command([BIN/'initdb.exe','-D',DATA,'-U','deepdb_local','--encoding=UTF8','--locale=C','-A','scram-sha-256','--pwfile',pw], 'initdb')
        finally: pw.unlink(missing_ok=True)
        with (DATA/'postgresql.conf').open('a',encoding='utf-8') as f:
            f.write("\n# Dedicated DSC5003 local experiment\nlisten_addresses='127.0.0.1'\nport=55432\nshared_buffers='512MB'\nwork_mem='16MB'\nmaintenance_work_mem='256MB'\nmax_connections=10\nmax_parallel_workers_per_gather=0\nmax_parallel_maintenance_workers=0\ndefault_statistics_target=100\njit=off\nautovacuum=off\n")
    check=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(DATA),'status'],capture_output=True)
    if check.returncode:
        progress('2/6 Start database on 127.0.0.1:55432')
        command([BIN/'pg_ctl.exe','-D',DATA,'-l',PG/'server.log','-w','start'],'start_server')
    admin=connect('postgres')
    with admin.cursor() as cur:
        cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',('deepdb_joblight',))
        if not cur.fetchone(): cur.execute('CREATE DATABASE deepdb_joblight')
    admin.close()
    conn=connect('deepdb_joblight')
    schema=(PROJECT/'code/benchmarks/job-light/setup-sql/alternative_schema.sql').read_text()
    blocks=re.findall(r'CREATE TABLE (\w+)\s*\(.*?\n\);',schema,re.S)
    assert set(expected).issubset(set(blocks))
    table_sql={m.group(1):m.group(0) for m in re.finditer(r'CREATE TABLE (\w+)\s*\(.*?\n\);',schema,re.S)}
    record['schema_source']='code/benchmarks/job-light/setup-sql/alternative_schema.sql; six tables only'
    load_start=time.perf_counter()
    for i,table in enumerate(manifest['tables'],1):
        progress('3/6 Import table %d/6: %s'%(i,table))
        stage_start=time.perf_counter()
        with conn.cursor() as cur:
            cur.execute('SET statement_timeout=1800000')
            cur.execute('SELECT to_regclass(%s)',('public.'+table,))
            exists=cur.fetchone()[0] is not None
            if exists:
                cur.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
                count=cur.fetchone()[0]
                if count==0: exists=False
                elif count!=expected[table]: raise RuntimeError('Existing table count mismatch; inspect before changing '+table)
            if not exists:
                cur.execute('SELECT to_regclass(%s)',('public.'+table,))
                if cur.fetchone()[0] is None:
                    # Add primary keys after loading, to keep bulk COPY efficient.
                    cur.execute(table_sql[table].replace(' PRIMARY KEY',''))
                with (PROJECT/'data/imdb'/(table+'.csv')).open('rb') as f:
                    copy_sql=sql.SQL('COPY {} FROM STDIN WITH (FORMAT CSV, ESCAPE {}, ENCODING \'UTF8\')').format(sql.Identifier(table),sql.Literal('\\'))
                    cur.copy_expert(copy_sql.as_string(conn), CopyProgress(f,table),size=1024*1024)
                    count=cur.rowcount
                assert count==expected[table], (table,count,expected[table])
            record['tables'][table]={'rows':count,'expected_rows':expected[table],'seconds':time.perf_counter()-stage_start}
            save()
    record['stages']['import_seconds']=time.perf_counter()-load_start
    progress('4/6 Create primary keys and repository-defined indexes; collect statistics')
    index_start=time.perf_counter()
    with conn.cursor() as cur:
        for table in manifest['tables']:
            cur.execute('SELECT 1 FROM pg_constraint WHERE conrelid=%s::regclass AND contype=\'p\'',(table,))
            if not cur.fetchone():
                progress('4/6 Primary key: '+table)
                cur.execute(sql.SQL('ALTER TABLE {} ADD PRIMARY KEY (id)').format(sql.Identifier(table)))
        index_text=(PROJECT/'code/benchmarks/job-light/setup-sql/fk.sql').read_text()
        selected=[]
        for name,table,col in re.findall(r'create index (\w+) on (\w+)\((\w+)\);',index_text):
            if table in expected:
                progress('4/6 Index: '+name)
                cur.execute(sql.SQL('CREATE INDEX IF NOT EXISTS {} ON {} ({})').format(sql.Identifier(name),sql.Identifier(table),sql.Identifier(col)))
                selected.append({'name':name,'table':table,'column':col})
        record['indexes']=selected
        record['foreign_keys']='No foreign-key constraints added; six-table schema primary keys and selected fk.sql indexes only.'
        for table in manifest['tables']:
            progress('4/6 ANALYZE: '+table)
            cur.execute(sql.SQL('ANALYZE {}').format(sql.Identifier(table)))
            cur.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
            assert cur.fetchone()[0]==expected[table]
        cur.execute('SELECT version()')
        record['postgresql_version']=cur.fetchone()[0]
        keys=['shared_buffers','work_mem','maintenance_work_mem','default_statistics_target','max_parallel_workers_per_gather','max_parallel_maintenance_workers','jit','autovacuum','random_page_cost','effective_cache_size','seq_page_cost','cpu_tuple_cost','geqo_threshold','server_encoding']
        record['settings']={}
        for key in keys:
            cur.execute('SHOW '+key);record['settings'][key]=cur.fetchone()[0]
        cur.execute('SELECT pg_database_size(current_database())')
        record['database_bytes']=cur.fetchone()[0]
    record['stages']['indexes_analyze_and_counts_seconds']=time.perf_counter()-index_start
    progress('5/6 Estimate 70 JOB-light queries; no query execution')
    truth_path=PROJECT/'code/benchmarks/job-light/sql/job_light_true_cardinalities.csv'
    sql_path=PROJECT/'code/benchmarks/job-light/sql/job_light_queries.sql'
    record['query_file_sha256']=sha(sql_path)
    record['truth_file_sha256']=sha(truth_path)
    with truth_path.open(newline='',encoding='utf-8') as f: truths=list(csv.DictReader(f))
    queries=[q.strip()+';' for q in sql_path.read_text().split(';') if q.strip()]
    assert len(queries)==len(truths)==70
    results=[]; plans=[]
    with conn.cursor() as cur:
        cur.execute('SET statement_timeout=30000')
        for i,(query,truth) in enumerate(zip(queries,truths)):
            assert int(truth['query_no'])==i and query==truth['query'].strip()
            # COUNT(*) returns one output row. Estimate its input rows, not Aggregate's rows=1.
            statement='EXPLAIN (FORMAT JSON, SUMMARY ON) '+query
            cur.execute(statement);warm=cur.fetchone()[0][0]
            repeats=[];planning=[];estimated=[]
            for repeat in range(5):
                begin=time.perf_counter();cur.execute(statement);plan=cur.fetchone()[0][0]
                repeats.append((time.perf_counter()-begin)*1000)
                rootplan=plan['Plan']
                assert rootplan['Node Type']=='Aggregate' and len(rootplan['Plans'])==1
                child=rootplan['Plans'][0]
                assert 'Workers Planned' not in json.dumps(rootplan)
                estimated.append(float(child['Plan Rows']))
                planning.append(float(plan['Planning Time']))
            assert len(set(estimated))==1 and estimated[0]>0
            actual=int(truth['cardinality_true']); assert actual>0
            q=max(estimated[0]/actual,actual/estimated[0])
            results.append(dict(query_no=i,query=query,cardinality_predict=estimated[0],cardinality_true=actual,q_error=q,
                planning_ms_median=float(np.median(planning)),client_explain_ms_median=float(np.median(repeats)),
                input_node_type=child['Node Type'],aggregate_rows=rootplan['Plan Rows']))
            plans.append({'query_no':i,'query':query,'explain':warm,'planning_ms_repeats':planning,'client_ms_repeats':repeats})
            if (i+1)%10==0: progress('5/6 Estimates saved in memory: %d/70'%(i+1))
    with (OUT/'postgresql_estimates.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    (OUT/'explain_plans.json').write_text(json.dumps(plans,indent=2),encoding='utf-8')
    q=np.array([r['q_error'] for r in results])
    record['summary']={'queries':70,'q_error':{str(p):float(np.percentile(q,p)) for p in [50,90,95,99,100]},
        'planning_ms_mean_of_per_query_medians':float(np.mean([r['planning_ms_median'] for r in results])),
        'client_ms_mean_of_per_query_medians':float(np.mean([r['client_explain_ms_median'] for r in results]))}
    record['method']='Original COUNT(*) EXPLAIN JSON; Plan Rows of sole child below top Aggregate; parallel workers disabled; default stats target 100; one ANALYZE snapshot; 1 warmup + 5 repeats per query.'
    record['timing_limit']='PostgreSQL planning and client EXPLAIN time differ from DeepDB Python estimator latency; no direct speedup claim.'
    conn.close()
    progress('6/6 Save baseline; generate bilingual comparison report')
    record['status']='PASS';record['ended_at']=datetime.now().astimezone().isoformat();save()
    print(json.dumps(record['summary'],indent=2),flush=True)
except BaseException as exc:
    record['status']='FAILED_OR_STOPPED';record['error']=str(exc);save()
    print('ERROR:',str(exc),flush=True)
    raise
