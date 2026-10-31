"""Reviewed SF2-only original Verdict controller; default command is planning.

No import-time database, SQLite or subprocess operation. Execution requires an
external root approval whose bytes and exact plan binding are supplied by CLI.
"""
import argparse
import base64
import ctypes
from ctypes import wintypes
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/full/verdict_ssb'
DATA = ROOT / 'data/verdict_ssb'
DB = 'deepdb_verdict_ssb'
SAMPLE_TABLE = 'public_verdict.vs_lineorder_uf_0_0033'
PG = ROOT / '.runtime/postgresql-11.5/pgsql/bin'
CLUSTER = ROOT / 'data/postgresql/cluster'
JAVA = ROOT / '.runtime/java/jdk8u462-b08/bin/java.exe'
JAVAC = JAVA.with_name('javac.exe')
JAR = ROOT / 'data/verdict/p/jars/verdict-spark-lib-0.4.7.jar'
PG_START_OPTIONS = '-h 127.0.0.1 -p 55432 -c shared_buffers=256MB -c work_mem=64MB -c maintenance_work_mem=256MB -c max_parallel_workers_per_gather=0'
GIB = 1024**3
CANDIDATE_SHA = '2068722a30f99f40ddc3be17a5663322300c2eb48b7218da426dfea568058082'
LIMITS = dict(total_new_bytes=GIB, minimum_available_ram_bytes=4*GIB,
              minimum_free_disk_bytes=4*GIB, java_rss_bytes=GIB, python_rss_bytes=512*1024**2,
              statement_timeout_ms=120000, work_mem_kib=16384, temp_file_limit_kib=131072)
ORACLE_REUSE_NAME='sf2_golden_v2'
ORACLE_REUSE_SHA={
 'plan.json':'c1e8c09d2ca7e0c81f4ee5c3aac0d19a2e5148d31d057fd26c3a2421bffeeb08',
 'oracle.json':'99ad7f54450252b7a05b5206438918d41153dbc1bed5b284cd12bcdc4511f361',
 'oracle_execution.json':'79f2712ac216fe69a954cfd6e8d43de9643d7424c0c6795cdc3be2e5a2219a30',
 'lifecycle.json':'bae8f9d86bc12bab544a0187d4ecf0d4282bee5c9ae99e52fad972e77c2184ea',
 'root_start_hang_diagnostic.json':'7b54f2a172c1731fdf25ccda55a3e74fc797026c0c8e7c3d9d09ff37fbdeaaa0'}
ORACLE_DATABASE=dict(path='data/verdict_ssb/sf2_golden_v2/oracle.sqlite',bytes=43941888,
    sha256='f0e1cb60ecfff25bc30ffb5d6c06d54d5ed8d09dbfa1ea95403837f3f3a4f908')
ORACLE_OLD_SOURCES={
 'full_verdict_ssb_run.py':'737c6c559615b1e2769335691cede77070d519df25638b08545dec895dcf112b',
 'test_full_verdict_ssb_run.py':'2ff1c7639f1dc5ff12514ae44c9e19c10e86f8c6345957def74f7701f54478dc',
 'FULL_VERDICT_SSB_RUN.md':'8033ed8cb5b322e8f47f1a54ad6773f2679b5eb7394453366d91563f46b2e26a'}
REGISTERED_REUSE_NAME='sf2_golden_v3'
REGISTERED_MANIFEST='output/full/verdict_ssb/registered_pg_adoption_source_v4.json'
REGISTERED_MANIFEST_SHA='8c4df1062d75468688ff4b6d295ac4799e91adadf80633b9f642fc5ba32d9ec3'
REGISTERED_OLD_SOURCES={
 'code/full_verdict_ssb_run.py':'full_verdict_ssb_run.py',
 'code/tests/test_full_verdict_ssb_run.py':'test_full_verdict_ssb_run.py',
 'docs/FULL_VERDICT_SSB_RUN.md':'FULL_VERDICT_SSB_RUN.md'}
ARCHIVES = {
 'data/downloads/baselines/verdict18/b59209f626d278687ea0a801295b41064c7fecbb.zip':
 '72b068ce7dc501e065229b2b43eee19bd3777127e973db436256fd9770ae23c9',
 'data/downloads/verdict_runtime/OpenJDK8U-jdk_x64_windows_hotspot_8u462b08.zip':
 'c6c2d8e6c2cbf0b4ddb707e6edb9a00d8a7b04e9ed6dda7e62d43dc4d83d342c',
 'data/downloads/postgresql-11.5-1-windows-x64-binaries.zip':
 '89ec61731231b88b748ae0f923ec02568ede2c008c79f901666ea67de6565f4c'}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def bhash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def atomic_json(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as out:
        json.dump(value,out,sort_keys=True,indent=2,allow_nan=False);out.write('\n');out.flush();os.fsync(out.fileno())
    os.replace(str(tmp),str(path))


def candidate():
    path=ROOT/'code/full_verdict_ssb.py'
    if digest(path)!=CANDIDATE_SHA:raise ValueError('Frozen candidate source changed')
    spec=importlib.util.spec_from_file_location('verdict_ssb_frozen_candidate',str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def schema_contract(text):
    text=re.sub(r'--[^\n]*','',text)
    schema={}
    for table,body in re.findall(r'create table\s+(\w+)\s*\((.*?)\);',text,re.I|re.S):
        cols=[];primary=[]
        for line in body.splitlines():
            line=line.strip().rstrip(',')
            if not line:continue
            if re.match('primary key',line,re.I):
                primary=[x.strip() for x in re.search(r'\((.*?)\)',line).group(1).split(',')];continue
            match=re.fullmatch(r'(\w+)\s+(BIGINT|integer|varchar\(\d+\))\s+not null',line,re.I)
            if not match:raise ValueError('Unsupported original schema declaration: '+line)
            cols.append([match.group(1),match.group(2)])
        if table in schema:raise ValueError('Duplicate schema table')
        schema[table]=dict(columns=cols,primary_key=primary)
    if {k:len(v['columns']) for k,v in schema.items()}!={'dwdate':17,'customer':8,'part':9,'supplier':7,'lineorder':17}:
        raise ValueError('Original SSB schema shape changed')
    if schema['lineorder']['primary_key']:raise ValueError('Fact duplicates must not be removed')
    return schema


def create_table_sql(name,table,engine):
    if not re.fullmatch('[a-z_]+',name) or engine not in ('postgres','sqlite'):raise ValueError('Unsafe DDL target')
    fields=[]
    for col,kind in table['columns']:
        if not re.fullmatch('[a-z_0-9]+',col):raise ValueError('Unsafe source column')
        if engine=='sqlite':kind='INTEGER' if kind.lower() in ('integer','bigint') else 'TEXT'
        fields.append('"{}" {} NOT NULL'.format(col,kind))
    if table['primary_key']:fields.append('PRIMARY KEY ('+','.join('"'+x+'"' for x in table['primary_key'])+')')
    return 'CREATE TABLE '+('public.' if engine=='postgres' else '')+name+' ('+','.join(fields)+')'


def oracle_records(rows,width,n,N,cutoff):
    seen=set();out=[]
    for row in rows:
        if len(row)!=width+1:raise ValueError('Independent sample SQL arity mismatch')
        key=tuple(None if x is None else str(x) for x in row[:width]);value=row[-1]
        if key in seen:raise ValueError('Duplicate independent sample SQL group')
        if value is not None and type(value) is not int:raise ValueError('SQLite sample SUM is not an exact integer')
        seen.add(key)
        def ratio(v):return dict(numerator=v.numerator,denominator=v.denominator)
        out.append(dict(key=list(key),sample_sum=value,
                        verdict_expected=None if value is None else ratio(Fraction(value*N,n)),
                        native_p_expected=None if value is None else ratio(Fraction(value*2**64,cutoff))))
    return out


def compare_oracle(actual,expected):
    predicted={tuple(r['key']):r for r in actual['rows']};truth={tuple(r['key']):r for r in expected}
    if len(predicted)!=len(actual['rows']) or len(truth)!=len(expected):raise ValueError('Duplicate comparison key')
    out=[]
    for key in sorted(set(predicted)|set(truth),key=repr):
        expected_row=truth.get(key);row=predicted.get(key)
        value=None if expected_row is None or expected_row['verdict_expected'] is None else float(Fraction(**expected_row['verdict_expected']))
        point=None if row is None else row['point']
        valid=point is not None and math.isfinite(point) and value is not None
        status='EXTRA_MODEL_GROUP' if key not in truth else 'MISSING_MODEL_GROUP' if key not in predicted else 'MATCHED'
        ae=abs(point-value) if valid else None
        gate=(status=='MATCHED' and actual['usable_for_point_comparison'] and actual['error'] is None and
              ((value is None and row['point_status']=='NULL') or (valid and math.isclose(point,value,rel_tol=2e-12,abs_tol=1e-6))))
        out.append(dict(key=list(key),status=status,expected=value,prediction=point,zero_expected=value==0,
                        absolute_error=ae,relative_error=ae/abs(value) if ae is not None and value else None,
                        numeric_gate_pass=gate,engine_error=actual['error'],raw_prediction=row))
    return out


def population_statistics(actual,truth):
    predicted={tuple(x['key']):x for x in actual['rows']};exact={tuple(x['group']):x['value'] for x in truth}
    if len(predicted)!=len(actual['rows']) or len(exact)!=len(truth):raise ValueError('Duplicate population-comparison group')
    out=[]
    for key in sorted(set(predicted)|set(exact),key=repr):
        row=predicted.get(key);value=exact.get(key);point=None if row is None else row['point']
        status='EXTRA_MODEL_GROUP' if key not in exact else 'MISSING_MODEL_GROUP' if key not in predicted else 'MATCHED'
        valid=(actual['usable_for_point_comparison'] and actual['error'] is None and point is not None and math.isfinite(point) and value is not None)
        ae=abs(point-value) if valid else None
        interval=None if row is None else row.get('interval95')
        available=valid and interval is not None and row.get('ci_status')=='FINITE'
        out.append(dict(key=list(key),status=status,truth=value,prediction=point,zero_truth=value==0,
                        absolute_error=ae,relative_error=ae/abs(value) if ae is not None and value else None,
                        missing_penalty_relative_error=1. if status=='MISSING_MODEL_GROUP' else None,
                        native_ci95=interval,native_ci95_covers_truth=(interval[0]<=value<=interval[1]) if available else None,
                        native_ci_status='MISSING_GROUP' if row is None else row.get('ci_status','UNSUPPORTED_NO_COVARIANCE_MODEL'),
                        point_status='MISSING_GROUP' if row is None else row.get('point_status'),engine_error=actual['error']))
    return out


def population_comparison(call,actual,truth):
    if call['role'] in ('SUM_REVENUE','SUM_SUPPLYCOST'):
        return dict(status='UNAVAILABLE_NO_MATCHING_FULL_POPULATION_COMPONENT_TRUTH',groups=None)
    if call['role']!='RAW':raise ValueError('Unknown physical query population estimand')
    return dict(status='AVAILABLE_EXACT_EXPRESSION_TRUTH',groups=population_statistics(actual,[x for x in truth if x['query_no']==call['query_no']]))


def rewrite_proof(log,call):
    physical=[line.split('A query to db: ',1)[1] for line in log.splitlines() if 'A query to db: ' in line]
    physical=[sql for sql in physical if re.search(r'(?:public_verdict\.vs_lineorder_|public\.lineorder)',sql,re.I)]
    if len(physical)!=1:raise ValueError('Missing/ambiguous actual original physical rewrite')
    sql=physical[0]
    if re.search(r'public\.lineorder\b',sql,re.I) or SAMPLE_TABLE.lower() not in sql.lower():raise ValueError('Original rewrite did not use retained fact sample')
    expected=re.search(r'\bfrom\s+(.*?)\s+where\b',call['sql'],re.I).group(1)
    dims=sorted(set(x.strip().lower() for x in expected.split(','))-{'lineorder'})
    tables=set(re.findall(r'\bpublic\.([a-z_0-9]+)',sql,re.I))
    if tables!=set(dims) or set(re.findall(r'\bpublic_verdict\.(vs_[a-z_0-9]+)',sql,re.I))!={SAMPLE_TABLE.split('.')[1]}:
        raise ValueError('Original rewrite full dimension/sample table set mismatch')
    if call['mode']=='subsampling' and 'verdict_vpart' not in sql:raise ValueError('Missing native fact partition in actual CI rewrite')
    return dict(physical_sql=sql,full_dimensions=dims,fact_sample=SAMPLE_TABLE,
                native_ci_partition_present='verdict_vpart' in sql,
                scaled_probability_present='verdict_vprob' in sql)


def claim_namespace(home,binding):
    home=Path(home);home.parent.mkdir(parents=True,exist_ok=True);home.mkdir(exist_ok=False)
    atomic_json(home/'lifecycle.json',dict(status='RUNNING',binding_sha256=bhash(binding)))


def mark_tainted(home,error):
    atomic_json(Path(home)/'lifecycle.json',dict(status='TAINTED',error=str(error)))


def budget_total(own_files,own_database,wal_now,wal_before,tmp_now,tmp_before):
    wal=max(0,wal_now-wal_before);tmp=max(0,tmp_now-tmp_before)
    return dict(owned_files_bytes=own_files,owned_database_bytes=own_database,
                positive_wal_bytes=wal,positive_temp_bytes=tmp,total_bytes=own_files+own_database+wal+tmp,
                wal_now_bytes=wal_now,wal_before_bytes=wal_before,temp_now_bytes=tmp_now,temp_before_bytes=tmp_before)


def check_review(path,sha,plan):
    if not path or not sha or not Path(path).is_file() or digest(path)!=sha:raise ValueError('Exact root review approval required')
    review=json.loads(Path(path).read_text(encoding='utf-8'))
    if (review.get('status')!='APPROVED_SF2_EXECUTION' or review.get('scope')!='SF2_ONLY' or
        review.get('binding_sha256')!=plan['binding_sha256'] or review.get('limits')!=plan['limits']):
        raise ValueError('Root review approval scope/plan/resource mismatch')
    return review


def check_protected(before,after):
    if set(before)!= {'deepdb_job','deepdb_verdict'} or before!=after:raise ValueError('Protected database catalog identity changed')
    return dict(scope='CATALOG_IDENTITIES_ONLY_NOT_ROW_CONTENT',before=before,after=after)


def descriptor(path):
    path=Path(path).resolve()
    if ROOT not in path.parents or not path.is_file():raise ValueError('Required artifact outside project/missing: '+str(path))
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=digest(path))


def runtime_closure():
    """Derive runtime members from fixed archives, not an arbitrary saved map."""
    files={};counts={}
    selections=[('data/verdict/b',True,None),('.runtime/java',False,None),
                ('.runtime/postgresql-11.5',False,('pgsql/bin/','pgsql/lib/','pgsql/share/'))]
    for (archive,sha),(directory,strip,selected) in zip(ARCHIVES.items(),selections):
        path=ROOT/archive
        if digest(path)!=sha:raise ValueError('Fixed original source/runtime archive changed')
        files[archive]=descriptor(path);count=0
        with zipfile.ZipFile(str(path)) as source:
            prefix=source.namelist()[0] if strip else ''
            for item in source.infolist():
                if item.is_dir() or (selected and not item.filename.startswith(selected)):continue
                relative=item.filename[len(prefix):]
                if '..' in Path(relative).parts or ':' in relative or '\\' in relative:raise ValueError('Unsafe runtime archive member')
                target=ROOT/directory/relative;expected=hashlib.sha256(source.read(item)).hexdigest()
                rec=descriptor(target)
                if rec['sha256']!=expected:raise ValueError('Fixed runtime/source bytes changed: '+relative)
                files[rec['path']]=rec;count+=1
        counts[directory]=count
    if counts!={'data/verdict/b':400,'.runtime/java':446,'.runtime/postgresql-11.5':1436}:raise ValueError('Runtime closure member count changed')
    jar=ROOT/'data/verdict/p/jars/verdict-spark-lib-0.4.7.jar'
    if digest(jar)!=candidate().JAR_SHA256:raise ValueError('Original Verdict executable JAR changed')
    files[descriptor(jar)['path']]=descriptor(jar)
    paths=[Path(sys.executable),ROOT/'.venv/pyvenv.cfg']
    base=Path(sys.base_prefix).resolve()
    if ROOT not in base.parents:raise ValueError('Python runtime is not project-local')
    paths += [p for p in base.rglob('*') if p.is_file() and
              (p.suffix.lower() in ('.dll','.pyd') or (p.suffix=='.py' and 'site-packages' not in p.parts and '__pycache__' not in p.parts))]
    paths += [p for p in (ROOT/'.venv/Lib/site-packages/psycopg2').iterdir() if p.is_file()]
    paths += [p for p in (ROOT/'.venv/Lib/site-packages/psycopg2_binary-2.9.9.dist-info').iterdir() if p.is_file()]
    for path in paths:
        rec=descriptor(path);files[rec['path']]=rec
    return dict(files=files,archive_member_counts=counts,python_version=sys.version,
                platform=platform.platform(),machine=platform.machine(),python_hash_seed=os.environ.get('PYTHONHASHSEED'),
                platform_scope='Project Python/JDK/PG files; Windows transitive OS libraries remain platform dependencies')


def prepare_plan(reuse_oracle_from=None,reuse_registered_from=None):
    c=candidate();source=c.inspect_sf2();runtime=runtime_closure()
    files={rec['path']:rec for rec in runtime['files'].values()}
    for rec in source['artifacts'].values():
        rec=dict(path=Path(rec['path']).resolve().relative_to(ROOT).as_posix(),bytes=rec['bytes'],sha256=rec['sha256']);files[rec['path']]=rec
    for name in ['code/full_verdict_ssb.py','code/tests/test_full_verdict_ssb.py','code/full_verdict_ssb_run.py','code/full_verdict_ssb_bridge.java',
                 'code/tests/test_full_verdict_ssb_run.py','docs/FULL_VERDICT_SSB_PROTOCOL.md','docs/FULL_VERDICT_SSB_RUN.md',c.SQL_PATH,c.SCHEMA_PATH]:
        files[name]=descriptor(ROOT/name)
    body=dict(schema='verdict_ssb_sf2_run_plan_v1',scope='SF2_ONLY',limits=LIMITS,database=DB,
              population_rows=11997996,sample_rows=39587,source_audit=source,
              source_runtime_files=files,runtime=runtime,queries=c.call_plan(c.load_queries()),
              schema_contract=schema_contract((ROOT/c.SCHEMA_PATH).read_text(encoding='utf-8')),
              registration_information=['schema','retained fact sample','full dimensions','n','N'],
              selected_java=descriptor(JAVA),selected_javac=descriptor(JAVAC),
              resource_window='NO_FORMAL_RSPN_ACTIVE',
              formal_allowed=False,engine_calls_executed=0)
    body['pg_control_policy']='EXCLUSIVE_FILES_NO_PIPE_WITH_VERIFIED_THIS_ATTEMPT_OWNERSHIP_V3'
    body['oracle_reuse']=oracle_reuse_plan(reuse_oracle_from,body) if reuse_oracle_from else None
    if body['oracle_reuse']:
        files.update(body['oracle_reuse']['files'])
    body['float8_transport']='PostgreSQL11 session extra_float_digits=3; native float8 bytes unchanged'
    body['registered_reuse']=registered_reuse_plan(reuse_registered_from,body) if reuse_registered_from else None
    if body['registered_reuse']:files.update(body['registered_reuse']['files'])
    return dict(body,binding_sha256=bhash(body))


def connect(database=DB,autocommit=False):
    if database not in (DB,'postgres','deepdb_job','deepdb_verdict'):raise ValueError('Forbidden database target')
    import psycopg2
    connection=psycopg2.connect(host='127.0.0.1',port=55432,user='postgres',dbname=database,
        connect_timeout=10,application_name='verdict_ssb_owned_controller',
        options='-c statement_timeout=120000 -c work_mem=16384 -c temp_file_limit=131072 -c extra_float_digits=3')
    connection.autocommit=autocommit
    return connection


def process_rss(pid):
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ['peak','working','p1','p2','p3','p4','page','peakpage']]
    k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
    k.CloseHandle.argtypes=[wintypes.HANDLE];p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=k.OpenProcess(0x410,False,pid)
    if not handle:return 0
    count=Counters();count.cb=ctypes.sizeof(count)
    try:
        return max(int(count.working),int(count.peak)) if p.GetProcessMemoryInfo(handle,ctypes.byref(count),count.cb) else 0
    finally:k.CloseHandle(handle)


def available_ram():
    class Memory(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(x,ctypes.c_ulonglong) for x in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
    m=Memory();m.length=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('RAM probe failed')
    return int(m.available)


def tree_bytes(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file()) if Path(path).exists() else 0


class Budget:
    def __init__(self,home,stage):
        self.home=home;self.stage=stage;self.connection=None;self.samples=[]
        self.reused_oracle_bytes=0
        self.last_database_bytes=0
        self.wal_before=tree_bytes(CLUSTER/'pg_wal');self.tmp_before=self.temp_bytes();self.wal_lsn_before=None
    def temp_bytes(self):
        return sum(tree_bytes(p) for p in (CLUSTER/'base').glob('*/pgsql_tmp'))+tree_bytes(CLUSTER/'base/pgsql_tmp')
    def tick(self,force=False):
        if self.samples and not force and time.monotonic()-self.samples[-1]['monotonic']<.25:return self.samples[-1]
        database=self.last_database_bytes
        if self.connection is not None:
            with self.connection.cursor() as c:
                c.execute('SELECT pg_database_size(%s)',(DB,));database=c.fetchone()[0]
                self.last_database_bytes=database
        usage=budget_total(tree_bytes(self.home)+tree_bytes(self.stage)+self.reused_oracle_bytes,database,
                           tree_bytes(CLUSTER/'pg_wal'),self.wal_before,self.temp_bytes(),self.tmp_before)
        usage.update(monotonic=time.monotonic(),python_rss_bytes=process_rss(os.getpid()))
        if self.connection is not None and self.wal_lsn_before is not None:
            with self.connection.cursor() as c:
                c.execute('SELECT pg_current_wal_lsn()::text');usage['wal_lsn']=c.fetchone()[0]
                usage['wal_generated_bytes']=lsn_integer(usage['wal_lsn'])-lsn_integer(self.wal_lsn_before)
        self.samples.append(usage)
        if usage['total_bytes']>LIMITS['total_new_bytes']:raise ValueError('SF2 own DB/files/WAL/temp budget exceeded')
        if usage['python_rss_bytes']>LIMITS['python_rss_bytes']:raise ValueError('Controller Python RSS exceeded')
        return usage


def java_environment(environment):
    return {key:value for key,value in environment.items() if key.upper() not in ('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')}


def bounded_process(command,stem,watch,timeout):
    stem=Path(stem);started=time.monotonic();peak=0;reason=None
    out_path=Path(str(stem)+'.stdout.log');err_path=Path(str(stem)+'.stderr.log')
    with out_path.open('x',encoding='utf-8',newline='\n') as out,err_path.open('x',encoding='utf-8',newline='\n') as err:
        process=subprocess.Popen(list(map(str,command)),cwd=str(ROOT),stdout=out,stderr=err,env=java_environment(os.environ),creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            while process.poll() is None:
                peak=max(peak,process_rss(process.pid));watch.tick()
                if peak>LIMITS['java_rss_bytes']:raise ValueError('Java RSS exceeded 1GiB')
                if time.monotonic()-started>timeout:raise TimeoutError('Owned process deadline exceeded')
                time.sleep(.05)
        except BaseException as error:
            reason=repr(error);process.terminate();process.wait(timeout=15);raise
        finally:
            code=process.poll()
            atomic_json(Path(str(stem)+'.process.json'),dict(command=list(map(str,command)),exit_code=code,
                        seconds=time.monotonic()-started,peak_rss_bytes=peak,reason=reason))
        if process.wait()!=0:raise ValueError('Owned process failed: '+str(stem))
    watch.tick(force=True)
    return json.loads(Path(str(stem)+'.process.json').read_text())


def raw_chunks(path,width,terminal,chunk_rows=10000):
    with Path(path).open('r',encoding='utf-8',newline='') as source:
        while True:
            lines=[]
            for _ in range(chunk_rows):
                line=source.readline()
                if not line:break
                lines.append(line)
            if not lines:break
            buffer=io.StringIO();n=candidate().normalize_pipe_records(io.StringIO(''.join(lines)),buffer,width,terminal)
            yield n,lines,buffer.getvalue()


class CopyHashSink:
    def __init__(self,watch=None):self.hash=hashlib.sha256();self.bytes=0;self.rows=0;self.watch=watch
    def write(self,data):
        data=data.encode('utf-8') if isinstance(data,str) else data
        self.hash.update(data);self.bytes+=len(data);self.rows+=data.count(b'\n')
        if self.watch is not None:self.watch.tick()
        return len(data)
    def result(self):return dict(bytes=self.bytes,rows=self.rows,sha256=self.hash.hexdigest())


def canonical_input_hash(path,width,terminal):
    sink=CopyHashSink()
    for n,unused,text in raw_chunks(path,width,terminal):sink.write(text)
    return sink.result()


def require_import_identity(expected,actual):
    if expected!=actual:raise ValueError('Imported complete field values/order/duplicate multiplicity changed')


def check_native_metadata(size,name):
    expected_size=[['public_verdict','vs_lineorder_uf_0_0033',39587,11997996]]
    expected_name=[['public','lineorder','public_verdict','vs_lineorder_uf_0_0033','uniform',39587/11997996,'']]
    if size!=expected_size or name!=expected_name:raise ValueError('Native metadata must register only actual-fraction fact sample')


def input_tables(plan):
    c=candidate();binding=plan['source_audit'];gold=ROOT/c.SF2_GOLDEN
    return [('dwdate',gold/'dimensions/date.tbl',True,2556),('customer',gold/'dimensions/customer.tbl',True,60000),
            ('part',gold/'dimensions/part.tbl',True,400000),('supplier',gold/'dimensions/supplier.tbl',True,4000),
            ('lineorder',ROOT/c.SF2_BENCHMARK/'stream/lineorder_sampled.csv',False,39587)]


def sqlite_progress(deadline,watch):
    def check():
        if time.monotonic()>deadline:return 1
        try:watch.tick()
        except (ValueError,OSError):return 1
        return 0
    return check


def validate_oracle(plan,oracle):
    calls={c['call_id']:c for c in plan['queries'] if c['mode']=='nobound'}
    if (len(calls)!=19 or set(oracle['queries'])!=set(calls) or oracle.get('status')!='PASS_INDEPENDENT_SQLITE_INTEGER_SAMPLE_SUMS' or
        oracle.get('population_rows')!=11997996 or oracle.get('sample_rows')!=39587 or oracle.get('query_truth_used') is not False):
        raise ValueError('Independent oracle complete identity/accounting mismatch')
    for qid,call in calls.items():
        item=oracle['queries'][qid]
        if item['call']!=call or not math.isfinite(item['seconds']) or item['seconds']<0:raise ValueError('Oracle SQL/timing identity mismatch')
        rows=[tuple(group['key']+[group['sample_sum']]) for group in item['groups']]
        expected=oracle_records(rows,call['group_width'],39587,11997996,61482997997673935)
        if expected!=item['groups']:raise ValueError('Oracle integer scaling derivation changed')


def check_oracle_adoption_lineage(plan,old,execution,life,diagnostic):
    if any(plan[k]!=old[k] for k in ('source_audit','schema_contract','queries','population_rows','sample_rows')):
        raise ValueError('Completed oracle source/schema/query lineage differs')
    if (execution.get('database')!=ORACLE_DATABASE or execution.get('queries_executed')!=19 or
        execution.get('full_fact_recreated') is not False or life.get('status')!='TAINTED' or
        diagnostic.get('source_sha256')!='737c6c559615b1e2769335691cede77070d519df25638b08545dec895dcf112b' or
        diagnostic.get('recovery_exit_code')!=0 or diagnostic.get('active_external_database_clients')!=[]):
        raise ValueError('Completed oracle physical lineage/recovery evidence differs')


def oracle_reuse_plan(name,plan):
    if name!=ORACLE_REUSE_NAME:raise ValueError('Only the explicitly pinned completed v2 oracle can be reused')
    home=OUT/'runs'/name;files={};records={}
    for filename,sha in ORACLE_REUSE_SHA.items():
        path=home/filename
        if digest(path)!=sha:raise ValueError('Pinned failed-run oracle evidence changed: '+filename)
        rec=descriptor(path);files[rec['path']]=rec;records[filename]=json.loads(path.read_text(encoding='utf-8'))
    if descriptor(ROOT/ORACLE_DATABASE['path'])!=ORACLE_DATABASE:raise ValueError('Completed SQLite physical bytes changed')
    files[ORACLE_DATABASE['path']]=ORACLE_DATABASE
    for filename,sha in ORACLE_OLD_SOURCES.items():
        path=OUT/'v2_failed_source'/filename
        if digest(path)!=sha:raise ValueError('Frozen v2 failed-source snapshot changed: '+filename)
        rec=descriptor(path);files[rec['path']]=rec
    check_oracle_adoption_lineage(plan,records['plan.json'],records['oracle_execution.json'],records['lifecycle.json'],records['root_start_hang_diagnostic.json'])
    validate_oracle(plan,records['oracle.json'])
    return dict(status='PINNED_COMPLETED_ORACLE_FROM_TAINTED_OPERATIONAL_RUN',name=name,files=files,
        database=ORACLE_DATABASE,sqlite_connections_executed=0,queries_reexecuted=0,
        reuse_scope='Only completed exact sample SQL oracle; failed PG start is never adopted as PASS')


def adopt_oracle(plan,home):
    evidence=plan.get('oracle_reuse')
    if not evidence or evidence!=oracle_reuse_plan(evidence['name'],plan):raise ValueError('Reviewed oracle adoption changed')
    old=OUT/'runs'/evidence['name']
    for name in ('oracle.json','oracle_execution.json'):shutil.copyfile(str(old/name),str(Path(home)/name))
    atomic_json(Path(home)/'oracle_reuse.json',evidence)
    return ROOT/evidence['database']['path']


def registered_reuse_plan(name,plan):
    if name!=REGISTERED_REUSE_NAME or not plan.get('oracle_reuse'):raise ValueError('Explicit pinned v3 registration and v2 oracle adoption required')
    path=ROOT/REGISTERED_MANIFEST
    if digest(path)!=REGISTERED_MANIFEST_SHA:raise ValueError('Pinned completed PG registration manifest changed')
    manifest=json.loads(path.read_text(encoding='utf-8'));files=manifest.get('files',{})
    # The manifest bytes are fixed independently of its map and cannot be replaced
    # by an empty/resealed or a newly generated artifact subset.
    if len(files)!=57:raise ValueError('Incomplete registered-input adoption closure')
    for rel,rec in files.items():
        if descriptor(ROOT/rel)!=rec:raise ValueError('Completed PG/Java artifact changed: '+rel)
    home=OUT/'runs'/name
    old=json.loads((home/'plan.json').read_text(encoding='utf-8'))
    if digest(home/'plan.json')!='fa565820e884b9bee7a2ef742cef2bef10eee82c8225db3f47a3d55fda703f1d':raise ValueError('Original v3 plan changed')
    if any(plan[k]!=old[k] for k in ('source_audit','schema_contract','queries','population_rows','sample_rows','runtime')):
        raise ValueError('Completed PG/Java source/schema/query/runtime lineage differs')
    for rel,rec in old['source_runtime_files'].items():
        actual=OUT/'v3_failed_source'/REGISTERED_OLD_SOURCES[rel] if rel in REGISTERED_OLD_SOURCES else ROOT/rel
        if actual.stat().st_size!=rec['bytes'] or digest(actual)!=rec['sha256']:raise ValueError('Prior v3 source/runtime physical closure changed: '+rel)
    life=json.loads((home/'lifecycle.json').read_text(encoding='utf-8'))
    if life!={'status':'TAINTED','error':'Fact auxiliary fields differ'} or (home/'calls').exists():raise ValueError('Only the known pre-query v3 failure may be adopted')
    shutdown=json.loads((home/'failed_shutdown.json').read_text(encoding='utf-8'))
    validate_pg_control(shutdown['stop'],'stop',home,0);validate_pg_control(shutdown['status_after'],'status',home,3)
    diagnostic=json.loads((OUT/'diagnostic_vprob_v3/diagnostic.json').read_text(encoding='utf-8'))
    if (digest(OUT/'diagnostic_vprob_v3/diagnostic.json')!='d50c0bc2aef1eaf8bd96ac38ea6fac5885a09d4eea8d010face4c243c912a60f' or
        diagnostic.get('data_modified') is not False or diagnostic.get('science_calls_executed')!=0 or diagnostic.get('full_account_matches') is not True or
        diagnostic.get('expected_ieee754_hex')!='3f6b077c38a5b19d' or diagnostic.get('server_stopped_after_diagnostic') is not True):
        raise ValueError('Root independent float8 diagnosis differs')
    for role in ('compile','registration'):validate_process(json.loads((home/(role+'.process.json')).read_text(encoding='utf-8')),expected_command(role,home))
    imported=json.loads((home/'import.json').read_text(encoding='utf-8'))
    if imported['status']!='PASS_IMPORTED_EXISTING_SAMPLE_FULL_DIMENSIONS' or len(imported['loads'])!=5:raise ValueError('Completed v3 import missing')
    for item in imported['loads']:require_import_identity(item['canonical_source'],item['canonical_actual'])
    rec=descriptor(path);files=dict(files);files[rec['path']]=rec
    return dict(status='PINNED_COMPLETED_IMPORT_COMPILE_REGISTRATION_FROM_TAINTED_V3',name=name,files=files,
        classes=descriptor(home/'classes/full_verdict_ssb_bridge.class'),
        prior_steps_reexecuted=dict(sqlite_queries=0,imports=0,analyzes=0,javac=0,registrations=0),
        physical_pg_acceptance='Require complete locked COPY/source hashes, metadata/types/native bits/100parts and new before-after catalog/auxiliary snapshots; never replace DB')


def adopt_registered_files(plan,home):
    evidence=plan.get('registered_reuse')
    if not evidence or evidence!=registered_reuse_plan(evidence['name'],plan):raise ValueError('Reviewed PG/Java adoption changed')
    old=OUT/'runs'/evidence['name'];home=Path(home)
    names=['import.json','protected_before.json','registration.tsv']
    names += [role+suffix for role in ('compile','registration') for suffix in ('.stdout.log','.stderr.log','.process.json')]
    (home/'classes').mkdir()
    names.append('classes/full_verdict_ssb_bridge.class')
    for name in names:shutil.copyfile(str(old/name),str(home/name))
    atomic_json(home/'registered_reuse.json',evidence)


def expected_owned_schema(schema):
    result={}
    for table,spec in schema.items():
        result['public.'+table]=[[name,re.sub('^varchar','character varying',kind.lower()),True] for name,kind in spec['columns']]
    result[SAMPLE_TABLE]=result['public.lineorder']+[['verdict_vprob','double precision',True],['verdict_vpart','integer',True]]
    result['public_verdict.verdict_meta_size']=[[name,kind,False] for name,kind in [('schemaname','character varying(120)'),('tablename','character varying(120)'),('samplesize','bigint'),('originaltablesize','bigint')]]
    result['public_verdict.verdict_meta_name']=[[name,'double precision' if name=='samplingratio' else 'character varying(120)',False] for name in ('originalschemaname','originaltablename','sampleschemaaname','sampletablename','sampletype','samplingratio','columnnames')]
    return result


def validate_owned_catalog_record(catalog):
    db=catalog.get('database',{});relations=catalog.get('relations',[])
    if (set(db)!={'oid','name','owner','encoding','collation','ctype'} or db['name']!=DB or
        any(type(db[k]) is not int or db[k]<1 for k in ('oid','owner')) or type(db['encoding']) is not int or db['encoding']<0 or
        any(not isinstance(db[k],str) or not db[k] for k in ('collation','ctype'))):raise ValueError('Existing PG database catalog identity missing')
    tables={('public',t) for t in ('dwdate','customer','part','supplier','lineorder')}|{('public_verdict',t) for t in ('vs_lineorder_uf_0_0033','verdict_meta_size','verdict_meta_name')}
    indices={('public',t+'_pkey') for t in ('dwdate','customer','part','supplier')}
    if (len(relations)!=12 or any(len(x)!=5 or x[2] not in ('r','i') or any(type(x[k]) is not int or x[k]<1 for k in (3,4)) for x in relations) or
        len({x[3] for x in relations})!=12 or len({(x[0],x[1]) for x in relations})!=12 or
        {(x[0],x[1]) for x in relations if x[2]=='r'}!=tables or {(x[0],x[1]) for x in relations if x[2]=='i'}!=indices):
        raise ValueError('Unexpected own PG relations/indexes; no replacement permitted')


def validate_registered_snapshot(snapshot,imported,schema=None):
    if (snapshot.get('status')!='PASS_LOCKED_REGISTERED_INPUT_ADOPTION' or snapshot.get('loads')!=imported['loads'] or
        snapshot.get('aux_accounting')!=[39587,39587/11997996,39587/11997996,0,99] or
        snapshot.get('probability_hex')!=['3f6b077c38a5b19d']*2 or
        snapshot.get('types')!=[['verdict_vprob','double precision',True],['verdict_vpart','integer',True]] or
        snapshot.get('original_fact_rows')!=0 or snapshot.get('original_canonical_fields_match') is not True or
        type(snapshot.get('owned_database_bytes')) is not int or snapshot['owned_database_bytes']<=0):
        raise ValueError('Existing PG snapshot does not match sealed import/probability/type/accounting')
    for load in snapshot['loads']:require_import_identity(load['canonical_source'],load['canonical_actual'])
    parts=snapshot.get('partition_histogram',[])
    if [p[0] for p in parts]!=list(range(100)) or any(type(p[1]) is not int or p[1]<=0 for p in parts) or sum(p[1] for p in parts)!=39587:
        raise ValueError('Existing PG partition coverage/accounting changed')
    check_native_metadata(snapshot['metadata_size'],snapshot['metadata_name'])
    aux=snapshot.get('aux_rows',{})
    if aux.get('rows')!=39587 or type(aux.get('bytes')) is not int or aux['bytes']<=0 or re.fullmatch('[0-9a-f]{64}',aux.get('sha256','')) is None:
        raise ValueError('Existing PG complete auxiliary-row snapshot missing')
    validate_owned_catalog_record(snapshot.get('catalog',{}))
    if schema is None:schema=schema_contract((ROOT/candidate().SCHEMA_PATH).read_text(encoding='utf-8'))
    if snapshot.get('schema')!=expected_owned_schema(schema):raise ValueError('Existing PG complete column schema differs from original import/metadata')
    if snapshot.get('steps_executed')!=dict(imports=0,analyzes=0,javac=0,registrations=0,sqlite_queries=0):raise ValueError('Adoption must not repeat completed scientific setup')


def owned_catalog(cursor):
    cursor.execute('SELECT oid,datname,datdba,encoding,datcollate,datctype FROM pg_database WHERE datname=current_database()')
    row=list(cursor.fetchone())
    if row[1]!=DB:raise ValueError('Wrong own database during adoption')
    cursor.execute("SELECT n.nspname,c.relname,c.relkind,c.oid,c.relfilenode FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname,c.oid")
    relations=[list(x) for x in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname IN ('public','public_verdict'))")
    if cursor.fetchone()[0]!=0:raise ValueError('External user triggers in owned PG namespace')
    result=dict(database=dict(zip(('oid','name','owner','encoding','collation','ctype'),row)),relations=relations)
    validate_owned_catalog_record(result);return result


def auxiliary_snapshot(cursor,watch=None):
    sink=CopyHashSink(watch)
    cursor.copy_expert("COPY (SELECT ctid::text,encode(float8send(verdict_vprob),'hex'),verdict_vpart FROM "+SAMPLE_TABLE+" ORDER BY ctid) TO STDOUT WITH(FORMAT CSV,DELIMITER '|')",sink)
    return sink.result()


def audit_registered_pg(plan,home,cursor,watch):
    started=time.monotonic();imported=json.loads((Path(home)/'import.json').read_text(encoding='utf-8'));loads=[]
    cursor.execute('SHOW server_version');version=cursor.fetchone()[0]
    cursor.execute('SHOW data_directory');directory=cursor.fetchone()[0]
    cursor.execute('SHOW extra_float_digits');precision=cursor.fetchone()[0]
    if not version.startswith('11.5') or Path(directory).resolve()!=CLUSTER.resolve() or precision!='3':raise ValueError('Registered PG version/cluster/float8 session mismatch')
    protection=check_protected(json.loads((Path(home)/'protected_before.json').read_text(encoding='utf-8')),protected_identities())
    for table,path,terminal,expected in input_tables(plan):
        target=SAMPLE_TABLE if table=='lineorder' else 'public.'+table
        previous=next(x for x in imported['loads'] if x['table']==target)
        columns=','.join('"'+col+'"' for col,kind in plan['schema_contract'][table]['columns'])
        sink=CopyHashSink(watch)
        cursor.copy_expert('COPY (SELECT '+columns+' FROM '+target+" ORDER BY ctid) TO STDOUT WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N')",sink)
        require_import_identity(previous['canonical_source'],sink.result())
        actual=dict(previous,canonical_actual=sink.result())
        loads.append(actual)
    cursor.execute('SELECT COUNT(*),MIN(verdict_vprob),MAX(verdict_vprob),MIN(verdict_vpart),MAX(verdict_vpart),encode(float8send(MIN(verdict_vprob)),\'hex\'),encode(float8send(MAX(verdict_vprob)),\'hex\') FROM '+SAMPLE_TABLE)
    account=list(cursor.fetchone())
    cursor.execute('SELECT verdict_vpart,COUNT(*) FROM '+SAMPLE_TABLE+' GROUP BY verdict_vpart ORDER BY verdict_vpart');parts=[list(x) for x in cursor.fetchall()]
    cursor.execute("SELECT attname,format_type(atttypid,atttypmod),attnotnull FROM pg_attribute WHERE attrelid=%s::regclass AND attname IN ('verdict_vprob','verdict_vpart') ORDER BY attnum",(SAMPLE_TABLE,));types=[list(x) for x in cursor.fetchall()]
    cursor.execute('SELECT * FROM public_verdict.verdict_meta_size');meta_size=[list(x) for x in cursor.fetchall()]
    cursor.execute('SELECT * FROM public_verdict.verdict_meta_name');meta_name=[list(x) for x in cursor.fetchall()]
    cursor.execute('SELECT COUNT(*) FROM public.lineorder');empty=cursor.fetchone()[0]
    catalog=owned_catalog(cursor);aux=auxiliary_snapshot(cursor,watch)
    cursor.execute("SELECT n.nspname,c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid JOIN pg_attribute a ON a.attrelid=c.oid WHERE n.nspname IN ('public','public_verdict') AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY n.nspname,c.relname,a.attnum")
    actual_schema={}
    for ns,table,col,kind,notnull in cursor.fetchall():actual_schema.setdefault(ns+'.'+table,[]).append([col,kind,notnull])
    cursor.execute('SELECT pg_database_size(current_database())');size=cursor.fetchone()[0];watch.last_database_bytes=size
    snapshot=dict(status='PASS_LOCKED_REGISTERED_INPUT_ADOPTION',loads=loads,aux_accounting=account[:5],probability_hex=account[5:],types=types,
        partition_histogram=parts,metadata_size=meta_size,metadata_name=meta_name,original_fact_rows=empty,original_canonical_fields_match=True,
        catalog=catalog,schema=actual_schema,aux_rows=aux,owned_database_bytes=size,protected=protection,server=dict(version=version,data_directory=directory,extra_float_digits=precision),
        steps_executed=dict(imports=0,analyzes=0,javac=0,registrations=0,sqlite_queries=0),canonical_reverification_seconds=time.monotonic()-started,
        historical_limit='Prior v3 did not seal own OID or auxiliary row membership; this is their first complete locked snapshot; original columns match every v3 import hash.')
    validate_registered_snapshot(snapshot,imported,plan['schema_contract']);atomic_json(Path(home)/'registered_pg_snapshot.json',snapshot);watch.tick(force=True)
    return snapshot


def verify_registered_adoption(plan,home,imported):
    home=Path(home);evidence=plan['registered_reuse'];old=OUT/'runs'/evidence['name']
    if json.loads((home/'registered_reuse.json').read_text(encoding='utf-8'))!=evidence:raise ValueError('Registered reuse receipt changed')
    names=['import.json','protected_before.json','registration.tsv','classes/full_verdict_ssb_bridge.class']+[role+suffix for role in ('compile','registration') for suffix in ('.stdout.log','.stderr.log','.process.json')]
    for name in names:
        if digest(home/name)!=digest(old/name):raise ValueError('Adopted original setup artifact differs: '+name)
    snapshot=json.loads((home/'registered_pg_snapshot.json').read_text(encoding='utf-8'));validate_registered_snapshot(snapshot,imported,plan['schema_contract'])
    after=json.loads((home/'registered_pg_after.json').read_text(encoding='utf-8'))
    expected=dict(status='PASS_SAME_REGISTERED_DATABASE_AFTER_38_CALLS',catalog=snapshot['catalog'],aux_rows=snapshot['aux_rows'],original_fact_rows=0,
        share_lock_held_across_calls=38,registered_before_sha256=digest(home/'registered_pg_snapshot.json'))
    if after!=expected:raise ValueError('Complete PG adoption before/after identity/auxiliary snapshot changed')
    check_protected(snapshot['protected']['before'],snapshot['protected']['after'])
    server=snapshot['server']
    if not server['version'].startswith('11.5') or Path(server['data_directory']).resolve()!=CLUSTER.resolve() or server['extra_float_digits']!='3':raise ValueError('Adopted PG cluster/roundtrip-precision evidence changed')


def run_oracle(plan,home,stage,watch):
    import sqlite3
    db=stage/'oracle.sqlite';connection=sqlite3.connect(str(db));started=time.monotonic();loads=[]
    try:
        connection.execute('PRAGMA journal_mode=DELETE');connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA cache_size=-65536');connection.execute('PRAGMA temp_store=FILE')
        connection.execute('PRAGMA temp_store_directory='+"'"+str(stage).replace("'","''")+"'")
        for table,path,terminal,expected_rows in input_tables(plan):
            schema=plan['schema_contract'][table];connection.execute(create_table_sql(table,schema,'sqlite'));loaded=0;t=time.monotonic()
            placeholders=','.join('?' for _ in schema['columns'])
            for n,lines,unused in raw_chunks(path,len(schema['columns']),terminal):
                values=[]
                for line in lines:
                    raw=line.rstrip('\r\n');raw=raw[:-1] if terminal else raw
                    fields=raw.split('|')
                    values.append([int(x) if kind.lower() in ('integer','bigint') else x for x,(col,kind) in zip(fields,schema['columns'])])
                connection.executemany('INSERT INTO '+table+' VALUES('+placeholders+')',values);loaded+=n;watch.tick()
            connection.commit()
            if loaded!=expected_rows or connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]!=expected_rows:raise ValueError('Independent SQLite input count differs')
            loads.append(dict(table=table,rows=loaded,seconds=time.monotonic()-t))
        for fk,dim,pk in [('lo_custkey','customer','c_custkey'),('lo_suppkey','supplier','s_suppkey'),('lo_partkey','part','p_partkey'),('lo_orderdate','dwdate','d_datekey')]:
            count=connection.execute('SELECT COUNT(*) FROM lineorder LEFT JOIN '+dim+' ON '+fk+'='+pk+' WHERE '+pk+' IS NULL').fetchone()[0]
            if count:raise ValueError('Sample has orphan dimension keys')
        results={};cutoff=plan['source_audit']['scaling']['generator_probability']['numerator']
        for call in [x for x in plan['queries'] if x['mode']=='nobound']:
            t=time.monotonic();deadline=t+120
            connection.set_progress_handler(sqlite_progress(deadline,watch),10000)
            rows=connection.execute(call['sql']).fetchall()
            results[call['call_id']]=dict(call=call,groups=oracle_records(rows,call['group_width'],39587,11997996,cutoff),seconds=time.monotonic()-t)
            watch.tick(force=True)
        atomic_json(home/'oracle.json',dict(status='PASS_INDEPENDENT_SQLITE_INTEGER_SAMPLE_SUMS',queries=results,
                    population_rows=11997996,sample_rows=39587,query_truth_used=False))
        atomic_json(home/'oracle_execution.json',dict(sqlite_version=sqlite3.sqlite_version,loads=loads,seconds=time.monotonic()-started,
                    database=descriptor(db),full_fact_recreated=False,queries_executed=19))
    finally:connection.close()


def no_external_clients():
    connection=connect('postgres',True)
    try:
        with connection.cursor() as c:
            c.execute("SELECT datname,application_name,pid FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")
            foreign=[row for row in c.fetchall() if not row[1].startswith('verdict_ssb_')]
            if foreign:raise ValueError('External PostgreSQL clients present: '+repr(foreign))
            c.execute('SELECT spcname FROM pg_tablespace ORDER BY spcname')
            if [x[0] for x in c.fetchall()]!=['pg_default','pg_global']:raise ValueError('Unbudgeted PostgreSQL tablespaces present')
    finally:connection.close()


def protected_identities():
    result={}
    for name in ('deepdb_job','deepdb_verdict'):
        connection=connect(name,True)
        try:
            with connection.cursor() as c:
                c.execute('SELECT oid FROM pg_database WHERE datname=current_database()');oid=c.fetchone()[0]
                c.execute("SELECT n.nspname,c.relname,c.relkind,c.oid,c.relfilenode FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname,c.oid")
                result[name]=dict(oid=oid,relations=[list(x) for x in c.fetchall()])
        finally:connection.close()
    return result


def import_postgres(plan,home,watch):
    no_external_clients();before=protected_identities();atomic_json(home/'protected_before.json',before)
    admin=connect('postgres',True)
    try:
        with admin.cursor() as c:
            c.execute('SHOW server_version')
            version=c.fetchone()[0]
            if not version.startswith('11.5'):raise ValueError('Unexpected PostgreSQL version')
            c.execute('SHOW data_directory');directory=c.fetchone()[0]
            if Path(directory).resolve()!=CLUSTER.resolve():raise ValueError('Connection is not the project PostgreSQL cluster')
            c.execute('SELECT pg_postmaster_start_time()::text');server_start=c.fetchone()[0]
            c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(DB,))
            if c.fetchone() is not None:raise ValueError('Owned database already exists; no automatic replacement')
            c.execute('SELECT pg_current_wal_lsn()::text');watch.wal_lsn_before=c.fetchone()[0]
            c.execute('CREATE DATABASE '+DB)
    finally:admin.close()
    connection=connect();monitor=connect(DB,True);watch.connection=monitor;loads=[]
    try:
        with connection.cursor() as c:
            c.execute('CREATE SCHEMA public_verdict')
            for table in plan['schema_contract']:c.execute(create_table_sql(table,plan['schema_contract'][table],'postgres'))
            c.execute('CREATE TABLE '+SAMPLE_TABLE+' (LIKE public.lineorder INCLUDING DEFAULTS)')
            c.execute('ALTER TABLE '+SAMPLE_TABLE+' ADD COLUMN verdict_vprob double precision NOT NULL DEFAULT (39587::double precision/11997996::double precision), ADD COLUMN verdict_vpart integer NOT NULL DEFAULT mod(cast(round(random()*100) as integer),100)')
            c.execute('SELECT setseed(0.271828)')
            for table,path,terminal,expected in input_tables(plan):
                target=SAMPLE_TABLE if table=='lineorder' else 'public.'+table;schema=plan['schema_contract'][table]
                columns=','.join('"'+col+'"' for col,kind in schema['columns']);t=time.monotonic();loaded=0
                for n,unused,text in raw_chunks(path,len(schema['columns']),terminal):
                    c.copy_expert('COPY '+target+' ('+columns+") FROM STDIN WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N')",io.StringIO(text));loaded+=n;watch.tick()
                c.execute('SELECT COUNT(*) FROM '+target)
                if loaded!=expected or c.fetchone()[0]!=expected:raise ValueError('Actual imported row count mismatch')
                original=canonical_input_hash(path,len(schema['columns']),terminal)
                sink=CopyHashSink(watch)
                c.copy_expert('COPY (SELECT '+columns+' FROM '+target+" ORDER BY ctid) TO STDOUT WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N')",sink)
                require_import_identity(original,sink.result())
                loads.append(dict(table=target,rows=loaded,seconds=time.monotonic()-t,canonical_source=original,canonical_actual=sink.result()))
            c.execute('SELECT COUNT(*) FROM public.lineorder')
            if c.fetchone()[0]!=0:raise ValueError('Original fact skeleton is not empty')
            connection.commit()
        with connection.cursor() as c:
            for table in ['public.dwdate','public.customer','public.part','public.supplier',SAMPLE_TABLE]:c.execute('ANALYZE '+table)
            connection.commit()
        atomic_json(home/'import.json',dict(status='PASS_IMPORTED_EXISTING_SAMPLE_FULL_DIMENSIONS',loads=loads,
                    original_fact_rows=0,population_rows=11997996,sample_rows=39587,actual_probability=39587/11997996,
                    dimension_policy='FULL_UNSAMPLED_NO_VPART',query_truth_used_for_registration=False,
                    server=dict(version=version,data_directory=directory,postmaster_start_time=server_start)))
    finally:connection.close();watch.connection=None;monitor.close()


def java_command(classes):
    return [JAVA,'-Xmx384m','-XX:MaxMetaspaceSize=192m','-Duser.language=en','-Duser.country=US','-Duser.timezone=UTC',
            '-cp',str(classes)+os.pathsep+str(JAR),'full_verdict_ssb_bridge']


def expected_command(kind,home,call=None):
    home=Path(home);classes=home/'classes'
    if kind=='compile':return [JAVAC,'-J-Xmx256m','-encoding','UTF-8','-cp',JAR,'-d',classes,ROOT/'code/full_verdict_ssb_bridge.java']
    if kind=='registration':return java_command(classes)+['register','39587','11997996',home/'registration.tsv']
    if kind=='query' and call is not None:
        folder=home/'calls'/call['call_id']
        return java_command(classes)+['query',call['mode'],call['call_id'],folder/'input.sql',folder/'result.tsv']
    raise ValueError('Unknown original bridge command role')


def validate_process(process,expected,cap=None):
    if (set(process)!= {'command','exit_code','reason','seconds','peak_rss_bytes'} or process.get('command')!=list(map(str,expected)) or type(process.get('exit_code')) is not int or process['exit_code']!=0 or process.get('reason') is not None or
        type(process.get('seconds')) not in (int,float) or not math.isfinite(process['seconds']) or process['seconds']<0 or
        type(process.get('peak_rss_bytes')) is not int or not 0<=process['peak_rss_bytes']<=(LIMITS['java_rss_bytes'] if cap is None else cap)):
        raise ValueError('Actual process command/timing/RSS policy mismatch')


def verify_java_selection(plan):
    for selected,path in [('selected_java',JAVA),('selected_javac',JAVAC)]:
        rec=descriptor(path)
        if plan.get(selected)!=rec or plan['source_runtime_files'].get(rec['path'])!=rec:raise ValueError('Selected fixed JDK is not in reviewed runtime closure')


def execute_original(plan,home,stage,watch):
    classes=home/'classes'
    verify_java_selection(plan)
    if plan.get('registered_reuse'):
        if descriptor(classes/'full_verdict_ssb_bridge.class')['sha256']!=plan['registered_reuse']['classes']['sha256']:raise ValueError('Adopted original compiled class changed')
    else:
        classes.mkdir()
        bounded_process(expected_command('compile',home),home/'compile',watch,90)
        bounded_process(expected_command('registration',home),home/'registration',watch,120)
    fields=(home/'registration.tsv').read_text(encoding='utf-8').strip().split('\t')
    if fields[:4]!=['REGISTER',SAMPLE_TABLE,'39587','11997996'] or float(fields[4])!=39587/11997996:raise ValueError('Original metadata registration mismatch')
    lock=connect();monitor=connect(DB,True);watch.connection=monitor
    try:
        no_external_clients()
        with lock.cursor() as c:
            c.execute('SET lock_timeout=10000')
            c.execute('LOCK TABLE public.lineorder,public.dwdate,public.customer,public.part,public.supplier,'+SAMPLE_TABLE+',public_verdict.verdict_meta_size,public_verdict.verdict_meta_name IN SHARE MODE')
            registered_snapshot=audit_registered_pg(plan,home,c,watch) if plan.get('registered_reuse') else None
            c.execute("SELECT clock_timestamp()::text,txid_current_snapshot()::text,pg_backend_pid()")
            lock_begin=list(c.fetchone())
            c.execute('SELECT COUNT(*),MIN(verdict_vprob),MAX(verdict_vprob),MIN(verdict_vpart),MAX(verdict_vpart) FROM '+SAMPLE_TABLE);account=list(c.fetchone())
            if account[:3]!=[39587,39587/11997996,39587/11997996] or not 0<=account[3]<=account[4]<100:raise ValueError('Fact auxiliary fields differ')
            c.execute('SELECT verdict_vpart,COUNT(*) FROM '+SAMPLE_TABLE+' GROUP BY verdict_vpart ORDER BY verdict_vpart');parts=[list(x) for x in c.fetchall()]
            c.execute('SELECT * FROM public_verdict.verdict_meta_size');meta_size=[list(x) for x in c.fetchall()]
            c.execute('SELECT * FROM public_verdict.verdict_meta_name');meta_name=[list(x) for x in c.fetchall()]
            check_native_metadata(meta_size,meta_name)
        (home/'calls').mkdir()
        for call in plan['queries']:
            assert_no_model_processes()
            folder=home/'calls'/call['call_id'];folder.mkdir()
            (folder/'input.sql').write_text(call['sql'],encoding='utf-8')
            process=bounded_process(expected_command('query',home,call),folder/'java',watch,160)
            result=candidate().parse_engine((folder/'result.tsv').read_text(encoding='utf-8'),[call])[call['call_id']]
            logs=(folder/'java.stdout.log').read_text(encoding='utf-8')+'\n'+(folder/'java.stderr.log').read_text(encoding='utf-8')
            # A parser/rewrite error before physical SQL remains explicit unsupported.
            try:proof=rewrite_proof(logs,call)
            except ValueError as error:
                if result['status']!='ENGINE_ERROR':raise
                proof=dict(status='UNAVAILABLE_ENGINE_ERROR',diagnostic=str(error))
            receipt=dict(call=call,result=result,rewrite=proof,process=process)
            atomic_json(folder/'receipt.json',receipt);atomic_json(folder/'receipt.seal.json',dict(sha256=digest(folder/'receipt.json')))
        with lock.cursor() as c:
            c.execute('SELECT clock_timestamp()::text,txid_current_snapshot()::text');lock_end=list(c.fetchone())
            c.execute('SELECT COUNT(*) FROM public.lineorder');empty=c.fetchone()[0]
            if registered_snapshot:
                after_catalog=owned_catalog(c);after_aux=auxiliary_snapshot(c,watch)
                if after_catalog!=registered_snapshot['catalog'] or after_aux!=registered_snapshot['aux_rows']:raise ValueError('Adopted registered PG identity or partition/probability rows changed during calls')
                atomic_json(home/'registered_pg_after.json',dict(status='PASS_SAME_REGISTERED_DATABASE_AFTER_38_CALLS',catalog=after_catalog,aux_rows=after_aux,original_fact_rows=empty,
                    share_lock_held_across_calls=38,registered_before_sha256=digest(home/'registered_pg_snapshot.json')))
        if empty!=0:raise ValueError('Original fact skeleton modified')
        after=protected_identities();before=json.loads((home/'protected_before.json').read_text());protection=check_protected(before,after)
        atomic_json(home/'post_run.json',dict(status='PASS_LOCKED_INPUT_CATALOG_ACCOUNTING',lock_begin=lock_begin,lock_end=lock_end,
                    share_lock_held_across_calls=38,aux_accounting=account,partition_histogram=parts,
                    original_fact_rows=empty,metadata_size=meta_size,metadata_name=meta_name,protected=protection))
        lock.rollback()
    finally:watch.connection=None;monitor.close();lock.close()


def evaluate_run(plan,home):
    c=candidate();oracle=json.loads((home/'oracle.json').read_text());results={};comparisons=[]
    validate_oracle(plan,oracle)
    population=json.loads((ROOT/c.SF2_GOLDEN/'independent_truth.json').read_text(encoding='utf-8'));c.canonical_truth(population)
    for call in plan['queries']:
        saved=verify_call_evidence(home/'calls'/call['call_id'],call)
        result=saved['result'];results[call['call_id']]=result
        expected=oracle['queries'][call['call_id'].replace('.subsampling','.nobound')]['groups']
        comparisons.append(dict(call=call,groups=compare_oracle(result,expected),population_comparison=population_comparison(call,result,population)))
    adapters=[]
    for mode in ('nobound','subsampling'):
        for qno in (10,11,12):
            calls=[x for x in plan['queries'] if x['mode']==mode and x['query_no']==qno]
            adapter=c.profit_adapter(*(results[x['call_id']] for x in calls))
            expected=oracle['queries'][calls[0]['call_id'].replace('.subsampling','.nobound')]['groups']
            actual=dict(error=None if adapter['status']=='POINT_ADAPTER_RETURNED' else 'CHILD_ENGINE_ERROR',
                        usable_for_point_comparison=adapter['status']=='POINT_ADAPTER_RETURNED',
                        rows=[dict(r,point_status='FINITE' if r['point'] is not None else 'NULL') for r in adapter['groups']])
            adapters.append(dict(query_no=qno,mode=mode,adapter=adapter,groups=compare_oracle(actual,expected),
                                 population_statistics=population_statistics(actual,[x for x in population if x['query_no']==qno])))
    required=[x for x in comparisons if x['call']['mode']=='nobound' and x['call']['role']=='RAW' and x['call']['query_no']<10]
    checks=[r for x in required for r in x['groups']]+[r for x in adapters if x['mode']=='nobound' for r in x['groups']]
    point_gate=bool(checks) and all(x['numeric_gate_pass'] for x in checks)
    return dict(status='PASS_SF2_ORIGINAL_POINT_SAMPLE_SCALING_WITH_EXPLICIT_CI_GAPS' if point_gate else 'FAIL_SF2_ORIGINAL_POINT_GATE',
                point_gate_pass=point_gate,comparisons=comparisons,adapters=adapters,
                engine_error_calls=sum(r['status']=='ENGINE_ERROR' for r in results.values()),
                native_ci_rows=sum(len(r['rows']) for r in results.values() if r['call']['mode']=='subsampling'),
                nonfinite_or_unavailable_ci_rows=sum(row['ci_status']!='FINITE' for r in results.values() if r['call']['mode']=='subsampling' for row in r['rows']),
                original_calls=38,formal_allowed=False,confidence_probability=.95,
                timing_scope='Per original vc.execute and fetching, separately from startup/import/SQLite; sample-only, not 3B end-to-end')


def verify_call_evidence(folder,call):
    folder=Path(folder)
    if folder.name!=call['call_id'] or folder.parent.name!='calls':raise ValueError('Per-call namespace identity mismatch')
    receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
    if json.loads((folder/'receipt.seal.json').read_text(encoding='utf-8'))!={'sha256':digest(folder/'receipt.json')}:raise ValueError('Per-call receipt seal changed')
    if receipt['call']!=call or (folder/'input.sql').read_text(encoding='utf-8')!=call['sql']:raise ValueError('Per-call SQL/index/role identity mismatch')
    parsed=candidate().parse_engine((folder/'result.tsv').read_text(encoding='utf-8'),[call])[call['call_id']]
    if receipt['result']!=parsed:raise ValueError('Per-call raw decoding/result mismatch')
    logs=(folder/'java.stdout.log').read_text(encoding='utf-8')+'\n'+(folder/'java.stderr.log').read_text(encoding='utf-8')
    try:proof=rewrite_proof(logs,call)
    except ValueError as error:
        if parsed['status']!='ENGINE_ERROR':raise
        proof=dict(status='UNAVAILABLE_ENGINE_ERROR',diagnostic=str(error))
    process=json.loads((folder/'java.process.json').read_text(encoding='utf-8'))
    if receipt['rewrite']!=proof or receipt['process']!=process:raise ValueError('Per-call physical rewrite/process mismatch')
    validate_process(process,expected_command('query',folder.parent.parent,call))
    return receipt


def required_result_paths(plan):
    required=set('plan.json review.json source_input.json runtime.json oracle.json oracle_execution.json import.json protected_before.json post_run.json budget.json evaluation.json server.json resource_start.json classes/full_verdict_ssb_bridge.class'.split())
    for stem in ('compile','registration'):
        required.update(stem+suffix for suffix in ('.stdout.log','.stderr.log','.process.json'))
    required.add('registration.tsv')
    for call in plan['queries']:
        required.update('calls/'+call['call_id']+'/'+name for name in ('input.sql','result.tsv','java.stdout.log','java.stderr.log','java.process.json','receipt.json','receipt.seal.json'))
    if len(plan['queries'])!=38 or len({c['call_id'] for c in plan['queries']})!=38:raise ValueError('Incomplete/duplicate fixed query plan')
    if plan.get('oracle_reuse'):required.add('oracle_reuse.json')
    if plan.get('registered_reuse'):required.update(('registered_reuse.json','registered_pg_snapshot.json','registered_pg_after.json'))
    return required


def check_result_set(plan,files):
    if set(files)!=required_result_paths(plan):raise ValueError('Exact required result file set mismatch')


def verify_sources(plan):
    if not plan['source_runtime_files']:raise ValueError('Empty source/runtime/input closure')
    for name,rec in plan['source_runtime_files'].items():
        path=ROOT/name
        if descriptor(path)!=rec:raise ValueError('Source/runtime/input artifact changed: '+name)
    verify_java_selection(plan)


def check_model_processes(rows):
    for row in rows:
        command=row.get('CommandLine') or ''
        if (row.get('Name') or '').lower().startswith('python') and re.search(r'(full_ssb[^\s\"\']*model|full_training)',command,re.I):
            raise ValueError('Formal/model training active; SF2 resource window closed: '+str(row.get('ProcessId')))


def assert_no_model_processes():
    script="[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%.exe'\" | Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress"
    raw=subprocess.run(['powershell.exe','-NoProfile','-Command',script],check=True,capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    value=json.loads(raw.stdout.decode('utf-8-sig')) if raw.stdout.strip() else []
    rows=value if isinstance(value,list) else [value];check_model_processes(rows)
    return dict(status='NO_FORMAL_RSPN_ACTIVE',python_processes_checked=len(rows),process_ids=[r['ProcessId'] for r in rows])


def lsn_integer(text):
    if not isinstance(text,str) or re.fullmatch('[0-9A-F]+/[0-9A-F]+',text,re.I) is None:raise ValueError('Invalid WAL LSN')
    a,b=text.split('/');return (int(a,16)<<32)+int(b,16)


def pg_control_command(action,home):
    if action=='status':return [PG/'pg_ctl.exe','-D',CLUSTER,'status']
    if action=='start':return [PG/'pg_ctl.exe','-D',CLUSTER,'-l',Path(home)/'postgresql.log','-o',PG_START_OPTIONS,'-w','start']
    if action=='stop':return [PG/'pg_ctl.exe','-D',CLUSTER,'-w','stop']
    raise ValueError('Unknown project PostgreSQL control action')


def pg_control(action,home,label=None):
    # A PostgreSQL child can retain inherited stdout/stderr. Files have no EOF
    # reader thread: Windows subprocess.run timeout cleanup stays bounded.
    label=label or action
    if label not in ('status','start','stop','status_after','failed_stop','failed_status'):
        raise ValueError('Invalid pg_ctl evidence label')
    home=Path(home);stem=home/('pg_'+label)
    command=list(map(str,pg_control_command(action,home)));started=time.monotonic()
    result=dict(command=command,exit_code=None,capture='EXCLUSIVE_FILES_NO_PIPE',status='RUNNING')
    try:
        with stem.with_suffix('.stdout.log').open('xb') as out,stem.with_suffix('.stderr.log').open('xb') as err:
            try:
                process=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,close_fds=True,
                    timeout=90 if action!='status' else 15,creationflags=subprocess.CREATE_NO_WINDOW)
                result.update(exit_code=process.returncode,status='RETURNED')
            except subprocess.TimeoutExpired:
                result['status']='TIMEOUT';raise
            finally:
                out.flush();err.flush()
    finally:
        # Refuse overwrites even on failure; original child logs stay untouched.
        if result['status']!='RUNNING':
            result.update(seconds=time.monotonic()-started,
                stdout=stem.with_suffix('.stdout.log').read_bytes().decode('utf-8',errors='replace'),
                stderr=stem.with_suffix('.stderr.log').read_bytes().decode('utf-8',errors='replace'))
            atomic_json(stem.with_suffix('.process.json'),result)
    if result['exit_code'] not in ((0,3) if action=='status' else (0,)):raise ValueError('Project pg_ctl operation failed: '+repr(result))
    return result


def validate_pg_control(record,action,home,code):
    if (not isinstance(record,dict) or record.get('command')!=list(map(str,pg_control_command(action,home))) or
        type(record.get('exit_code')) is not int or record['exit_code']!=code or type(record.get('seconds')) not in (int,float) or
        not math.isfinite(record['seconds']) or record['seconds']<0 or not isinstance(record.get('stdout'),str) or not isinstance(record.get('stderr'),str) or
        record.get('capture')!='EXCLUSIVE_FILES_NO_PIPE' or record.get('status')!='RETURNED'):
        raise ValueError('Project pg_ctl command/result/timing evidence mismatch')


def postmaster_pid():
    value=(CLUSTER/'postmaster.pid').read_text(encoding='utf-8').splitlines()[0]
    if not value.isdigit() or int(value)<1:raise ValueError('Invalid project postmaster identity')
    return int(value)


def split_windows_command(command):
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.CommandLineToArgvW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype=ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes=[wintypes.HLOCAL];kernel.LocalFree.restype=wintypes.HLOCAL
    count=ctypes.c_int();args=shell.CommandLineToArgvW(command,ctypes.byref(count))
    if not args:raise OSError('Cannot parse postmaster command line')
    try:return [args[n] for n in range(count.value)]
    finally:kernel.LocalFree(args)


def postmaster_identity():
    lines=(CLUSTER/'postmaster.pid').read_text(encoding='utf-8').splitlines()
    if len(lines)<4:raise ValueError('Incomplete postmaster.pid')
    pid=int(lines[0])
    if pid<1:raise ValueError('Invalid project postmaster PID')
    script=("[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); "
        "$p=Get-CimInstance Win32_Process -Filter 'ProcessId="+str(pid)+"'; "
        "if($null -eq $p){throw 'postmaster process absent'}; "
        "[pscustomobject]@{pid=[int]$p.ProcessId;image=$p.ExecutablePath;command=$p.CommandLine;"
        "creation_epoch=([DateTimeOffset]$p.CreationDate.ToUniversalTime()).ToUnixTimeMilliseconds()/1000.0}|ConvertTo-Json -Compress")
    probe=subprocess.run(['powershell.exe','-NoProfile','-Command',script],check=True,capture_output=True,
        timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    rec=json.loads(probe.stdout.decode('utf-8-sig'))
    rec['command']=split_windows_command(rec['command'])
    rec.update(cluster=lines[1],start_epoch=int(lines[2]),port=int(lines[3]));return rec


def validate_owned_identity(identity,intent):
    if (type(identity.get('pid')) is not int or identity['pid']<1 or
        Path(identity.get('image','')).resolve()!= (PG/'postgres.exe').resolve() or
        Path(identity.get('cluster','')).resolve()!=CLUSTER.resolve() or identity.get('port')!=55432):
        raise ValueError('Postmaster PID/image/cluster/port does not prove ownership')
    command=identity.get('command',[])
    if command.count('-D')!=1 or command.index('-D')+1>=len(command) or Path(command[command.index('-D')+1]).resolve()!=CLUSTER.resolve():
        raise ValueError('Actual postmaster command does not select project cluster')
    for key in ('start_epoch','creation_epoch'):
        stamp=identity.get(key)
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not intent['started_epoch']-2<=stamp<=intent['deadline_epoch']+2:
            raise ValueError('Postmaster predates or falls outside this start attempt')
    if abs(identity['start_epoch']-identity['creation_epoch'])>2:raise ValueError('PID file/process creation time mismatch')


def start_owned_server(home,initial_status,owned):
    if initial_status.get('exit_code')!=3 or (CLUSTER/'postmaster.pid').exists():
        raise ValueError('Only an absent project postmaster may be started/owned')
    epoch=time.time();intent=dict(status='THIS_CONTROLLER_START_INTENT',initial_exit_code=3,
        started_epoch=epoch,deadline_epoch=epoch+90,command=list(map(str,pg_control_command('start',home))))
    atomic_json(Path(home)/'startup_intent.json',intent)
    start_error=None
    try:return pg_control('start',home)
    except BaseException as error:start_error=error;raise
    finally:
        try:
            identity=postmaster_identity();validate_owned_identity(identity,intent)
            # Set in-memory ownership before writing the receipt, so receipt I/O
            # failure can still reach identity-checked cleanup in the caller.
            owned['identity']=identity
            atomic_json(Path(home)/'startup_ownership.json',dict(status='OWNED_THIS_START_ATTEMPT',identity=identity,intent=intent))
        except BaseException as error:
            atomic_json(Path(home)/'startup_ownership.json',dict(status='UNRESOLVED_NOT_OWNED',error=repr(error),intent=intent))
            if start_error is None:raise


def pg_control_artifacts(home,server):
    labels=['status','start','stop','status_after'] if server['started_by_controller'] else ['status']
    expected={('pg_'+label+suffix) for label in labels for suffix in ('.stdout.log','.stderr.log','.process.json')}
    if server['started_by_controller']:expected.update(('startup_intent.json','startup_ownership.json'))
    return {name:descriptor(Path(home)/name) for name in sorted(expected)}


def validate_pg_files(home,server,files):
    if files!=pg_control_artifacts(home,server):raise ValueError('PostgreSQL file-log/ownership artifact closure changed')
    mappings=[('status','initial_status')]+([('start','start'),('stop','stop'),('status_after','post_stop_status')] if server['started_by_controller'] else [])
    for label,key in mappings:
        stem=Path(home)/('pg_'+label);record=json.loads(stem.with_suffix('.process.json').read_text(encoding='utf-8'))
        if record!=server[key] or any(record[k]!=stem.with_suffix('.'+k+'.log').read_bytes().decode('utf-8',errors='replace') for k in ('stdout','stderr')):
            raise ValueError('PostgreSQL command receipt differs from raw file logs')
    if server['started_by_controller']:
        if json.loads((Path(home)/'startup_ownership.json').read_text(encoding='utf-8'))!=server['startup_ownership'] or json.loads((Path(home)/'startup_intent.json').read_text(encoding='utf-8'))!=server['startup_ownership']['intent']:
            raise ValueError('PostgreSQL startup ownership receipt changed')


def validate_resources(start,budget,server,home):
    if start.get('limits')!=LIMITS or budget.get('limits')!=LIMITS:raise ValueError('Recorded resource policy changed')
    for key,threshold in [('available_ram_bytes',LIMITS['minimum_available_ram_bytes']),('free_disk_bytes',LIMITS['minimum_free_disk_bytes'])]:
        if type(start.get(key)) is not int or start[key]<threshold:raise ValueError('Startup resource gate was not met')
    scan=start.get('model_scan',{})
    if (scan.get('status')!='NO_FORMAL_RSPN_ACTIVE' or type(scan.get('python_processes_checked')) is not int or
        not isinstance(scan.get('process_ids'),list) or len(scan['process_ids'])!=scan['python_processes_checked'] or
        any(type(pid) is not int or pid<1 for pid in scan['process_ids']) or len(set(scan['process_ids']))!=len(scan['process_ids'])):
        raise ValueError('Startup model-process resource window evidence mismatch')
    samples=budget.get('samples')
    if not isinstance(samples,list) or not samples:raise ValueError('Empty resource sample history')
    previous=-1.
    ints=('owned_files_bytes','owned_database_bytes','positive_wal_bytes','positive_temp_bytes','total_bytes','python_rss_bytes','wal_now_bytes','wal_before_bytes','temp_now_bytes','temp_before_bytes')
    for sample in samples:
        if any(type(sample.get(k)) is not int or sample[k]<0 for k in ints):raise ValueError('Invalid resource component measurement')
        expected=budget_total(sample['owned_files_bytes'],sample['owned_database_bytes'],sample['wal_now_bytes'],sample['wal_before_bytes'],sample['temp_now_bytes'],sample['temp_before_bytes'])
        if any(sample[k]!=v for k,v in expected.items()) or sample['total_bytes']>LIMITS['total_new_bytes'] or sample['python_rss_bytes']>LIMITS['python_rss_bytes']:
            raise ValueError('Resource totals/positive growth/caps violated')
        timestamp=sample.get('monotonic')
        if type(timestamp) not in (float,int) or not math.isfinite(timestamp) or timestamp<0 or timestamp<previous:raise ValueError('Invalid resource sample order/timing')
        previous=timestamp
        if sample['wal_before_bytes']!=samples[0]['wal_before_bytes'] or sample['temp_before_bytes']!=samples[0]['temp_before_bytes']:raise ValueError('Resource growth baseline changed during run')
        if 'wal_generated_bytes' in sample:
            if type(sample['wal_generated_bytes']) is not int or sample['wal_generated_bytes']<0 or sample['wal_generated_bytes']!=lsn_integer(sample.get('wal_lsn'))-lsn_integer(budget.get('wal_lsn_before')):raise ValueError('WAL generated bytes accounting mismatch')
    if budget.get('peak_total_bytes')!=max(x['total_bytes'] for x in samples):raise ValueError('Resource peak measurement mismatch')
    if type(server.get('started_by_controller')) is not bool or type(server.get('startup_requested')) is not bool or server.get('protected_scope')!='CATALOG_IDENTITIES_ONLY_NOT_ROW_CONTENT':raise ValueError('Server ownership policy evidence missing')
    if server['started_by_controller']:
        if server['status']!='PROJECT_SERVER_STOPPED_BY_OWNER' or not server['startup_requested']:raise ValueError('Owned server not proven stopped')
        if type(server.get('started_postmaster_pid')) is not int or server['started_postmaster_pid']<1 or server.get('stopped_postmaster_pid')!=server['started_postmaster_pid']:raise ValueError('Owned server postmaster identity changed before stop')
        for key,action,code in [('initial_status','status',3),('start','start',0),('stop','stop',0),('post_stop_status','status',3)]:validate_pg_control(server.get(key),action,home,code)
        ownership=server.get('startup_ownership',{})
        if (ownership.get('status')!='OWNED_THIS_START_ATTEMPT' or ownership.get('identity',{}).get('pid')!=server['started_postmaster_pid'] or
            ownership.get('intent',{}).get('initial_exit_code')!=3 or ownership['intent'].get('command')!=list(map(str,pg_control_command('start',home)))):
            raise ValueError('Startup ownership intent/result missing')
        validate_owned_identity(ownership['identity'],ownership['intent'])
    else:
        if server['status']!='EXISTING_SERVER_NOT_STOPPED' or any(server.get(k) is not None for k in ('start','stop','post_stop_status','started_postmaster_pid','stopped_postmaster_pid')):raise ValueError('Unowned server must not be stopped')
        validate_pg_control(server.get('initial_status'),'status',home,0)


def validate_accounting(imported,post):
    sizes={'public.dwdate':2556,'public.customer':60000,'public.part':400000,'public.supplier':4000,SAMPLE_TABLE:39587}
    if (imported['status']!='PASS_IMPORTED_EXISTING_SAMPLE_FULL_DIMENSIONS' or imported['original_fact_rows']!=0 or
        imported['population_rows']!=11997996 or imported['sample_rows']!=39587 or imported['actual_probability']!=39587/11997996 or
        imported['dimension_policy']!='FULL_UNSAMPLED_NO_VPART' or imported['query_truth_used_for_registration'] is not False or
        len(imported['loads'])!=5 or {x['table']:x['rows'] for x in imported['loads']}!=sizes):raise ValueError('Historical import full dimension/fact accounting mismatch')
    for load in imported['loads']:require_import_identity(load['canonical_source'],load['canonical_actual'])
    if (post['status']!='PASS_LOCKED_INPUT_CATALOG_ACCOUNTING' or post['original_fact_rows']!=0 or post['share_lock_held_across_calls']!=38 or
        post['aux_accounting']!=[39587,39587/11997996,39587/11997996,0,99] or
        [p[0] for p in post['partition_histogram']]!=list(range(100)) or sum(p[1] for p in post['partition_histogram'])!=39587 or
        any(type(p[1]) is not int or p[1]<=0 for p in post['partition_histogram'])):raise ValueError('Historical locked sample/partition accounting mismatch')
    check_native_metadata(post['metadata_size'],post['metadata_name'])
    if post['protected']!=check_protected(post['protected']['before'],post['protected']['after']):raise ValueError('Historical protected catalog scope mismatch')


def verify_run(home):
    """Strictly read only. No SQLite/PG connect, compile, process or repair."""
    home=Path(home).resolve()
    if OUT.resolve() not in home.parents:raise ValueError('Run outside owned output namespace')
    result_path=home/'final.json';result=json.loads(result_path.read_text(encoding='utf-8'))
    seal=json.loads((home/'final.seal.json').read_text(encoding='utf-8'));life=json.loads((home/'lifecycle.json').read_text(encoding='utf-8'))
    if seal!={'sha256':digest(result_path)} or life!={'status':'PASS','final_sha256':digest(result_path)}:raise ValueError('Missing final PASS lifecycle/seal')
    plan=json.loads((home/'plan.json').read_text(encoding='utf-8'));current=prepare_plan((plan.get('oracle_reuse') or {}).get('name'),(plan.get('registered_reuse') or {}).get('name'))
    if plan!=current or result['binding_sha256']!=plan['binding_sha256']:raise ValueError('Reviewed execution plan/source changed')
    check_result_set(plan,result['files'])
    for name,rec in result['files'].items():
        if descriptor(home/name)!=rec:raise ValueError('Final result artifact changed: '+name)
    db=ROOT/result['sqlite_artifact']['path']
    if descriptor(db)!=result['sqlite_artifact']:raise ValueError('Independent SQLite physical artifact changed')
    check_review(home/'review.json',result['review_sha256'],plan)
    if json.loads((home/'source_input.json').read_text(encoding='utf-8'))!=plan['source_audit'] or json.loads((home/'runtime.json').read_text(encoding='utf-8'))!=plan['runtime']:
        raise ValueError('Source/runtime receipt differs from reviewed plan')
    if result['postgresql_log'] is not None:
        log=ROOT/result['postgresql_log']['path']
        if log.resolve()!=home/'postgresql.log' or descriptor(log)!=result['postgresql_log']:raise ValueError('Owned PostgreSQL operational log changed')
    resource_start=json.loads((home/'resource_start.json').read_text(encoding='utf-8'))
    budget=json.loads((home/'budget.json').read_text(encoding='utf-8'));server=json.loads((home/'server.json').read_text(encoding='utf-8'))
    validate_resources(resource_start,budget,server,home)
    reused_bytes=plan['oracle_reuse']['database']['bytes'] if plan.get('oracle_reuse') else 0
    if (budget.get('reused_oracle_bytes')!=reused_bytes or resource_start.get('reused_oracle_bytes')!=reused_bytes or
        any(x['owned_files_bytes']<reused_bytes for x in budget['samples'])):
        raise ValueError('Reused completed SQLite must remain inside the SF2 file budget')
    validate_pg_files(home,server,result['pg_control_files'])
    if plan.get('oracle_reuse'):
        if json.loads((home/'oracle_reuse.json').read_text(encoding='utf-8'))!=plan['oracle_reuse'] or result['sqlite_artifact']!=plan['oracle_reuse']['database']:
            raise ValueError('Completed oracle adoption receipt changed')
    if (result['postgresql_log'] is not None)!=server['started_by_controller']:raise ValueError('Owned PostgreSQL log/ownership closure mismatch')
    process_home=OUT/'runs'/plan['registered_reuse']['name'] if plan.get('registered_reuse') else home
    for kind in ('compile','registration'):
        validate_process(json.loads((home/(kind+'.process.json')).read_text(encoding='utf-8')),expected_command(kind,process_home))
    imported=json.loads((home/'import.json').read_text(encoding='utf-8'));post=json.loads((home/'post_run.json').read_text(encoding='utf-8'))
    validate_accounting(imported,post)
    if plan.get('registered_reuse'):
        verify_registered_adoption(plan,home,imported)
    for table,path,terminal,expected_rows in input_tables(plan):
        load=next(x for x in imported['loads'] if x['table']==(SAMPLE_TABLE if table=='lineorder' else 'public.'+table))
        require_import_identity(canonical_input_hash(path,len(plan['schema_contract'][table]['columns']),terminal),load['canonical_source'])
    verify_sources(plan)
    evaluation=evaluate_run(plan,home)
    if evaluation!=json.loads((home/'evaluation.json').read_text(encoding='utf-8')) or result['evaluation_status']!=evaluation['status']:raise ValueError('Raw/oracle/evaluation derivation mismatch')
    expected_steps=dict(sqlite_queries=0 if plan.get('oracle_reuse') else 19,imports=0 if plan.get('registered_reuse') else 5,
        javac=0 if plan.get('registered_reuse') else 1,registrations=0 if plan.get('registered_reuse') else 1,original_queries=38)
    if result.get('steps_reexecuted')!=expected_steps:raise ValueError('Actual/reused execution-stage counts differ')
    return dict(status='PASS_READ_ONLY_SF2_EVIDENCE_CLOSURE',point_gate_pass=evaluation['point_gate_pass'],
                evaluation_status=evaluation['status'],manifest_sha256=digest(result_path),database_connected=False,
                sqlite_connected=False,engine_calls_executed=False,formal_allowed=False)


def run_sf2(name,review_path,review_sha,start_project_postgres=False,reuse_oracle_from=None,reuse_registered_from=None):
    if not review_path or not review_sha:raise ValueError('Exact root review approval required before any operation')
    plan=prepare_plan(reuse_oracle_from,reuse_registered_from);check_review(review_path,review_sha,plan)
    if not name or not re.fullmatch('[a-zA-Z0-9_-]{1,64}',name):raise ValueError('Safe fresh run name required')
    ram=available_ram();free=shutil.disk_usage(ROOT).free
    if ram<LIMITS['minimum_available_ram_bytes'] or free<LIMITS['minimum_free_disk_bytes']:raise ValueError('SF2 startup RAM/free disk gate failed')
    resource_scan=assert_no_model_processes()
    home=OUT/'runs'/name;stage=DATA/name;claim_namespace(home,plan);started_server=False;watch=None
    server_start=None;server_stop=None;post_stop_status=None
    owned_postmaster_pid=None;owned={}
    try:
        stage.mkdir(parents=True,exist_ok=False);watch=Budget(home,stage)
        atomic_json(home/'plan.json',plan);shutil.copyfile(str(review_path),str(home/'review.json'))
        atomic_json(home/'source_input.json',plan['source_audit']);atomic_json(home/'runtime.json',plan['runtime'])
        atomic_json(home/'resource_start.json',dict(available_ram_bytes=ram,free_disk_bytes=free,model_scan=resource_scan,limits=LIMITS,
                    reused_oracle_bytes=plan['oracle_reuse']['database']['bytes'] if plan.get('oracle_reuse') else 0))
        if plan.get('oracle_reuse'):
            oracle_db=adopt_oracle(plan,home);watch.reused_oracle_bytes=plan['oracle_reuse']['database']['bytes']
        else:run_oracle(plan,home,stage,watch);oracle_db=stage/'oracle.sqlite'
        initial_status=pg_control('status',home)
        if initial_status['exit_code']==3:
            if not start_project_postgres:raise ValueError('Project PostgreSQL stopped; reviewed startup flag required')
            server_start=start_owned_server(home,initial_status,owned);started_server=True;owned_postmaster_pid=owned['identity']['pid']
        assert_no_model_processes()
        if plan.get('registered_reuse'):adopt_registered_files(plan,home)
        else:import_postgres(plan,home,watch)
        assert_no_model_processes();execute_original(plan,home,stage,watch)
        evaluation=evaluate_run(plan,home);atomic_json(home/'evaluation.json',evaluation)
        watch.tick(force=True)
        owned_server_started=started_server
        if started_server:
            no_external_clients()
            if postmaster_identity()!=owned['identity']:raise ValueError('Project postmaster ownership changed; refuse stop')
            server_stop=pg_control('stop',home);post_stop_status=pg_control('status',home,'status_after')
            if post_stop_status['exit_code']!=3:raise ValueError('Owned PostgreSQL still running after requested stop')
            started_server=False;owned.clear()
        atomic_json(home/'server.json',dict(status='PROJECT_SERVER_STOPPED_BY_OWNER' if owned_server_started else 'EXISTING_SERVER_NOT_STOPPED',
                    startup_requested=start_project_postgres,started_by_controller=owned_server_started,
                    initial_status=initial_status,start=server_start,stop=server_stop,post_stop_status=post_stop_status,
                    started_postmaster_pid=owned_postmaster_pid,stopped_postmaster_pid=owned_postmaster_pid if owned_server_started else None,
                    startup_ownership=json.loads((home/'startup_ownership.json').read_text(encoding='utf-8')) if owned_server_started else None,
                    protected_scope='CATALOG_IDENTITIES_ONLY_NOT_ROW_CONTENT'))
        watch.tick(force=True);atomic_json(home/'budget.json',dict(samples=watch.samples,peak_total_bytes=max(x['total_bytes'] for x in watch.samples),limits=LIMITS,
                    reused_oracle_bytes=watch.reused_oracle_bytes,
                    wal_lsn_before=watch.wal_lsn_before,
                    measurement_scope='Own DB/files + positive cluster physical WAL/temp growth; finite polling window; no whole-C-drive delta'))
        verify_sources(plan)
        # Server log is runtime mutable until shutdown; include it only as an
        # explicit additional separately described operational artifact.
        files={p:descriptor(home/p) for p in sorted(required_result_paths(plan))}
        final=dict(schema='verdict_ssb_sf2_final_v1',binding_sha256=plan['binding_sha256'],files=files,
                   sqlite_artifact=descriptor(oracle_db),evaluation_status=evaluation['status'],
                   pg_control_files=pg_control_artifacts(home,json.loads((home/'server.json').read_text(encoding='utf-8'))),
                   review_sha256=review_sha,
                   postgresql_log=descriptor(home/'postgresql.log') if (home/'postgresql.log').exists() else None,
                   point_gate_pass=evaluation['point_gate_pass'],formal_allowed=False)
        final['steps_reexecuted']=dict(sqlite_queries=0 if plan.get('oracle_reuse') else 19,
            imports=0 if plan.get('registered_reuse') else 5,javac=0 if plan.get('registered_reuse') else 1,
            registrations=0 if plan.get('registered_reuse') else 1,original_queries=38)
        atomic_json(home/'final.json',final);atomic_json(home/'final.seal.json',dict(sha256=digest(home/'final.json')))
        atomic_json(home/'lifecycle.json',dict(status='PASS',final_sha256=digest(home/'final.json')))
        return verify_run(home)
    except BaseException as error:
        if watch is not None:atomic_json(home/'failed_budget.json',dict(samples=watch.samples))
        mark_tainted(home,error);raise
    finally:
        if owned:
            # Never stop an externally started server. Refuse shutdown if a
            # foreign client appeared, preserving the failed namespace.
            try:
                no_external_clients()
                if postmaster_identity()!=owned['identity']:raise ValueError('Project postmaster ownership changed; refuse failed-run stop')
                atomic_json(home/'failed_shutdown.json',dict(identity=owned['identity'],stop=pg_control('stop',home,'failed_stop'),status_after=pg_control('status',home,'failed_status')))
            except BaseException as error:mark_tainted(home,'Owned shutdown unresolved: '+repr(error))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','run-sf2','verify'])
    parser.add_argument('--name');parser.add_argument('--review');parser.add_argument('--review-sha256')
    parser.add_argument('--start-project-postgres',action='store_true')
    parser.add_argument('--reuse-oracle-from',choices=[ORACLE_REUSE_NAME])
    parser.add_argument('--reuse-registered-from',choices=[REGISTERED_REUSE_NAME])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if args.action=='plan':
        encoded=json.dumps(prepare_plan(args.reuse_oracle_from,args.reuse_registered_from),sort_keys=True,indent=2,allow_nan=False)+'\n'
        if args.output:
            if OUT.resolve() not in args.output.resolve().parents:raise ValueError('Plan output outside owned namespace')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8',newline='\n') as stream:stream.write(encoded)
        else:print(encoded,end='')
    elif args.action=='run-sf2':print(json.dumps(run_sf2(args.name,args.review,args.review_sha256,args.start_project_postgres,args.reuse_oracle_from,args.reuse_registered_from),indent=2))
    else:
        if not args.name:raise ValueError('Run name required')
        print(json.dumps(verify_run(OUT/'runs'/args.name),indent=2))


if __name__=='__main__':main()
