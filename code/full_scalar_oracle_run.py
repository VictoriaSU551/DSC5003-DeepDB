"""Explicit plan/ROOT-approval gated read-only scalar collection. No server lifecycle API."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time

import full_scalar_oracle as core
from full_scalar_oracle import require, object_hash

ROOT = core.ROOT
BASE = 'output/full/scalar_oracle'
KERNEL32 = Path('C:/Windows/System32/kernel32.dll')
SOURCES = ('code/full_scalar_oracle.py','code/full_scalar_oracle_run.py',
           'code/full_scalar_oracle_audit.py','docs/FULL_SCALAR_ORACLE_PROTOCOL.md')
INPUTS = {'data/manifest.json':'ae6a5cef66340bae23325722f0f0d29ee616850851b99b6989ab1d5b6a6f3e13',
          'data/postgresql/imports.json':'b5a2167bd4419aa38f6a0d48dfab7d1b75aada932949cd748e9226e9c8b79f1d',
          'code/full_postgres.py':'5eb6db79110be8e257bb3a8e300eb2b804dc5dc5907432a121cf9206fbe99292'}
FILES = ('plan.json','approval.json','counts.json','predictions.json','verification.json','lifecycle.json')
GIB = 1024**3
POLICY = dict(startup_available_memory_bytes=5*GIB, running_available_memory_bytes=GIB,
              max_client_rss_bytes=512*1024**2, min_free_disk_bytes=8*GIB,
              work_mem_mb=16, temp_file_limit_mb=1024, statement_timeout_ms=120000,
              lock_timeout_ms=5000, max_parallel_workers_per_gather=0,
              max_snapshot_bytes_per_table=2*GIB, memory_poll_seconds=1,max_total_seconds=1800)


def read(path):
    def unique(items):
        d={}
        for k,v in items:
            require(k not in d,'Duplicate JSON field');d[k]=v
        return d
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def atomic(path, value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024**2),b''):h.update(b)
    return h.hexdigest()


def artifact(path,root=ROOT,allow_empty=False):
    path=Path(path).resolve();root=Path(root).resolve()
    require(root in path.parents or path==KERNEL32.resolve(),'External artifact is not the fixed native Windows import')
    require(path.is_file() and (allow_empty or path.stat().st_size>0),'Missing or empty physical artifact: '+str(path))
    try:name=path.relative_to(root).as_posix()
    except ValueError:name=str(path)
    return dict(path=name,bytes=path.stat().st_size,sha256=digest(path))


def inventory(paths,root,allow_empty=False):
    output={};physical=set()
    for path in sorted(set(Path(x).resolve() for x in paths),key=str):
        key=os.path.normcase(str(path));require(key not in physical,'Duplicate physical dependency');physical.add(key)
        d=artifact(path,root,allow_empty=allow_empty);output[d['path']]=d
    require(bool(output),'Empty physical dependency inventory')
    return output


def runtime_paths(root):
    root=Path(root).resolve();base=Path(sys.base_prefix).resolve()
    require(base.is_relative_to(root) if hasattr(base,'is_relative_to') else str(base).lower().startswith(str(root).lower()+os.sep),
            'Project-local base Python required')
    venv=root/'.venv';pg=root/'.runtime/postgresql-11.5/pgsql';package=venv/'Lib/site-packages/psycopg2'
    require(pg.is_dir() and package.is_dir(),'Pinned PostgreSQL runtime and psycopg2 installation required')
    paths=[Path(sys.executable),Path(getattr(sys,'_base_executable',sys.executable)),venv/'pyvenv.cfg']
    for required in paths+[pg/'bin/postgres.exe',package/'__init__.py']:
        require(required.is_file() and required.stat().st_size>0,'Essential runtime executable/configuration is missing or empty')
    paths += [p for p in base.rglob('*') if p.is_file() and p.suffix.lower() in {'.py','.pyd','.dll','.exe','.zip'}]
    paths += [p for p in pg.rglob('*') if p.is_file()]
    paths += [p for p in package.rglob('*') if p.is_file() and p.suffix.lower()!='.pyc']
    paths += [p for parent in (venv/'Lib/site-packages').glob('psycopg2*') if parent.is_dir()
              for p in parent.rglob('*') if p.is_file() and p.suffix.lower()!='.pyc']
    require(os.name=='nt','Windows runtime contract required')
    paths += [KERNEL32]
    return paths


def dependency_snapshot(root=ROOT):
    root=Path(root).resolve()
    import full_scalar_oracle_audit as audit
    require(Path(core.__file__).resolve()==root/'code/full_scalar_oracle.py'
            and Path(__file__).resolve()==root/'code/full_scalar_oracle_run.py'
            and Path(audit.__file__).resolve()==root/'code/full_scalar_oracle_audit.py',
            'Actually loaded scalar-oracle modules must match the current physical source')
    for name,sha in INPUTS.items():require(digest(root/name)==sha,'Historic source/import lineage changed: '+name)
    raw=read(root/'data/manifest.json');imports=read(root/'data/postgresql/imports.json')
    require(set(imports)==set(core.EXPECTED_ROWS),'Historic six-table imports required')
    manifest={d['path']:d for d in raw['files']}
    for table,n in core.EXPECTED_ROWS.items():
        require(imports[table]['rows']==n and imports[table]['sha256']==manifest['imdb/'+table+'.csv']['sha256'],
                'Historic import and raw-manifest lineage disagree')
    sources=inventory([root/name for name in SOURCES]+[root/core.QUERY_FILE]+[root/name for name in INPUTS],root)
    runtime=inventory(runtime_paths(root),root,allow_empty=True)
    return dict(sources=sources,runtime=runtime,python_version=sys.version,
                raw_csv_current_bytes_rehashed=False, database_current_all_column_identity_proven=False)


def build_plan(root=ROOT,attempt='initial'):
    require(type(attempt) is str and re.fullmatch('[a-z0-9_]{1,32}',attempt) is not None,'Explicit safe attempt identity required')
    root=Path(root).resolve();contract=core.workload(root/core.QUERY_FILE)
    body=dict(schema='scalar-oracle-plan-v1',attempt=attempt,scope=dict(core.SCOPE),contract=contract,
              dependencies=dependency_snapshot(root),policy=POLICY,
              connection=dict(host='127.0.0.1',port=55432,database='deepdb_job',server_version_num=110005,
                              data_directory=str((root/'data/postgresql/cluster').resolve())),
              source_boundary='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY')
    return dict(body,binding=object_hash(body))


def validate_plan(plan,root=ROOT):
    require(object_hash(plan)==object_hash(build_plan(root,attempt=plan.get('attempt'))),'Plan is incomplete, stale, or differs from current physical dependencies')


def approval_template(plan,path,root=ROOT):
    return dict(status='PENDING_ROOT_REVIEW_NOT_AUTHORIZED',binding=plan['binding'],
                plan_file=artifact(path,root),exclusive_window=True,root_review_reference='')


def validate_approval(approval,plan,path,root=ROOT):
    require(set(approval)=={'status','binding','plan_file','exclusive_window','root_review_reference'}
            and approval['status']=='APPROVED_BY_ROOT_FOR_SINGLE_SCALAR_ORACLE_RUN'
            and approval['binding']==plan['binding'] and approval['plan_file']==artifact(path,root)
            and approval['exclusive_window'] is True and type(approval['root_review_reference']) is str
            and bool(approval['root_review_reference'].strip()),'Exact source-bound ROOT approval and exclusive window required')


def projection(contract,table):
    columns={'id'} if table=='title' else {'id','movie_id'}
    for p in contract['predicates']:
        if p['table']==table:columns.update(t['column'] for t in p['conditions'])
    return sorted(columns)


def copy_statement(contract,table):
    return 'COPY (SELECT '+', '.join('"'+c+'"' for c in projection(contract,table))+' FROM public."'+table+'" ORDER BY "id") TO STDOUT WITH (FORMAT BINARY)'


def requests(contract):
    output=[]
    for table,s in sorted(core.count_statements(contract).items()):
        output.append(dict(s,kind='scalar_aggregate',table=table))
    for table in sorted(set(contract['tables'])-{'title'}):
        output.append(dict(kind='foreign_key_check',table=table,parameters=[],
          sql='SELECT COUNT(*) FILTER (WHERE c.movie_id IS NULL), COUNT(*) FILTER (WHERE c.movie_id IS NOT NULL AND t.id IS NULL) FROM public."'+table+'" c LEFT JOIN public."title" t ON c.movie_id=t.id'))
    return output


class HashSink:
    def __init__(self,cap,check=None):self.h=hashlib.sha256();self.n=0;self.cap=cap;self.check=check
    def write(self,value):
        if self.check is not None:self.check()
        require(isinstance(value,bytes),'Binary COPY bytes required');require(self.n+len(value)<=self.cap,'Snapshot byte cap exceeded')
        self.h.update(value);self.n+=len(value)
        if self.check is not None:self.check()
        return len(value)
    def record(self):return dict(bytes=self.n,sha256=self.h.hexdigest())


class GuardedCursor:
    """A monitor failure is permanent even if idle connection.cancel did nothing."""
    def __init__(self,cursor,check):self.cursor=cursor;self.check=check
    def _call(self,name,*args,**kwargs):
        self.check();result=getattr(self.cursor,name)(*args,**kwargs);self.check();return result
    def execute(self,*a,**k):return self._call('execute',*a,**k)
    def fetchone(self,*a,**k):return self._call('fetchone',*a,**k)
    def fetchall(self,*a,**k):return self._call('fetchall',*a,**k)
    def copy_expert(self,*a,**k):return self._call('copy_expert',*a,**k)


def native_kernel():
    # Use the identical absolute asset recorded by runtime_paths. SystemRoot or
    # DLL-name search must not select a different file from the sealed one.
    return ctypes.WinDLL(str(KERNEL32.resolve()),use_last_error=True)


def validate_schema(contract,table,s):
    columns={x[0]:x[1] for x in s['columns']}
    require(s['table']==table and type(s['oid']) is int and s['oid']>0 and s['relkind']=='r'
            and not s['inherits'] and s['primary_key']==['id'] and s['valid_primary_key'] is True,
            'Ordinary noninherited relation with valid unique id primary key required')
    require(len(columns)==len(s['columns']) and all(columns.get(n) in {20,21,23,1700} for n in projection(contract,table)),
            'Required query columns must have actual built-in integer/numeric types')


def schema_record(cursor,contract,table):
    cursor.execute("SELECT c.oid::bigint,c.relkind,c.relfilenode::bigint,EXISTS(SELECT 1 FROM pg_catalog.pg_inherits h WHERE h.inhrelid=c.oid) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=%s",(table,))
    r=cursor.fetchone();require(r is not None,'Missing benchmark relation')
    cursor.execute('SELECT attname,atttypid::bigint FROM pg_catalog.pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT attisdropped ORDER BY attnum',(r[0],));cols=[list(x) for x in cursor.fetchall()]
    cursor.execute('SELECT a.attname,i.indisvalid,i.indisready FROM pg_catalog.pg_index i JOIN pg_catalog.pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indrelid=%s AND i.indisprimary ORDER BY a.attnum',(r[0],));keys=cursor.fetchall()
    s=dict(table=table,oid=r[0],relkind=r[1],relfilenode=r[2],inherits=r[3],columns=cols,
           primary_key=[x[0] for x in keys],valid_primary_key=bool(keys) and all(x[1] and x[2] for x in keys))
    validate_schema(contract,table,s);return s


def resources(root=ROOT):
    require(os.name=='nt','Native Windows memory measurement required')
    class Memory(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    class Process(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak_ws','working_set','peak_pool','pool','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
    kernel=native_kernel();m=Memory();m.length=ctypes.sizeof(m);p=Process();p.cb=ctypes.sizeof(p)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.K32GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    require(kernel.GlobalMemoryStatusEx(ctypes.byref(m)) and kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(p),p.cb),'Native resource measurement failed')
    return dict(available_memory_bytes=int(m.available),process_rss_bytes=int(p.working_set),free_disk_bytes=shutil.disk_usage(str(root)).free)


def validate_resources(record,startup=False):
    require(set(record)=={'available_memory_bytes','process_rss_bytes','free_disk_bytes'},'Resource receipt fields changed')
    for v in record.values():core.integer(v,'resource')
    require(record['available_memory_bytes']>=POLICY['startup_available_memory_bytes' if startup else 'running_available_memory_bytes']
            and record['process_rss_bytes']<=POLICY['max_client_rss_bytes'] and record['free_disk_bytes']>=POLICY['min_free_disk_bytes'],
            'Resource budget exceeded')


def backend_image(pid):
    kernel=native_kernel()
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid);require(bool(handle),'Cannot inspect database backend image')
    try:
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
        require(kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)),'Database backend image query failed')
        return str(Path(buffer.value).resolve())
    finally:kernel.CloseHandle(handle)


def connect():
    import psycopg2
    require(Path(psycopg2.__file__).resolve().parent==(ROOT/'.venv/Lib/site-packages/psycopg2').resolve(),'psycopg2 loaded from another installation')
    absent_passfile=ROOT/BASE/'NO_PASSWORD_FILE_ALLOWED'
    require(not absent_passfile.exists(),'External or implicit password file is not part of this local connection contract')
    previous={k:v for k,v in os.environ.items() if k.upper().startswith('PG')}
    try:
        for k in previous:os.environ.pop(k,None)
        return psycopg2.connect(host='127.0.0.1',port=55432,user='postgres',dbname='deepdb_job',sslmode='disable',
                               passfile=str(absent_passfile),connect_timeout=5,application_name='deepdb_scalar_oracle_local')
    finally:
        for k in list(os.environ):
            if k.upper().startswith('PG'):os.environ.pop(k,None)
        os.environ.update(previous)


def collect(plan,root=ROOT):
    root=Path(root).resolve();contract=plan['contract'];samples=[];operations=[]
    startup=resources(root);validate_resources(startup,startup=True);samples.append(startup)
    connection=connect();started=time.perf_counter();stop=threading.Event();errors=[];produced=None;thread_started=False
    def check():
        require(not errors and not stop.is_set(),'Collection permanently stopped by resource monitor: '+repr(errors))
        require(time.perf_counter()-started<=POLICY['max_total_seconds'],'Maximum scalar collection window exceeded')
    def monitor():
        while not stop.wait(POLICY['memory_poll_seconds']):
            try:
                require(time.perf_counter()-started<=POLICY['max_total_seconds'],'Maximum scalar collection window exceeded')
                s=resources(root);validate_resources(s);samples.append(s)
            except BaseException as e:
                errors.append(repr(e))
                try:connection.cancel()
                except BaseException as cancel_error:errors.append('Connection cancellation failed: '+repr(cancel_error))
                return
    thread=threading.Thread(target=monitor,daemon=True)
    try:
        thread.start();thread_started=True;check()
        # psycopg2 must configure its own implicit BEGIN; sending a second BEGIN
        # on a default non-autocommit connection can leave the first transaction
        # read-write. No data statement precedes these transaction attributes.
        connection.set_session(isolation_level='REPEATABLE READ',readonly=True,autocommit=False)
        with connection.cursor() as raw_cursor:
            cursor=GuardedCursor(raw_cursor,check)
            cursor.execute('SET LOCAL lock_timeout = '+str(POLICY['lock_timeout_ms']))
            cursor.execute('LOCK TABLE '+', '.join('public."'+t+'"' for t in contract['tables'])+' IN SHARE MODE NOWAIT')
            for text in ("SET LOCAL search_path = pg_catalog, public", "SET LOCAL work_mem = '16MB'", "SET LOCAL temp_file_limit = '1GB'", 'SET LOCAL statement_timeout = 120000', 'SET LOCAL max_parallel_workers_per_gather = 0'):
                cursor.execute(text)
            cursor.execute("SELECT current_database(),current_setting('server_version_num'),host(inet_server_addr()),inet_server_port(),current_setting('data_directory'),pg_backend_pid(),current_setting('transaction_read_only'),current_setting('transaction_isolation'),pg_postmaster_start_time()::text")
            r=cursor.fetchone();require(r[:4]==('deepdb_job','110005','127.0.0.1',55432)
                and Path(r[4]).resolve()==(root/'data/postgresql/cluster').resolve() and r[6:8]==('on','repeatable read'), 'Unexpected database server/transaction identity')
            image=backend_image(r[5]);require(Path(image)==(root/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve(),'Database backend runtime differs from sealed executable')
            identity=dict(database=r[0],server_version_num=r[1],address=r[2],port=r[3],data_directory=r[4],backend_pid=r[5],read_only=r[6],isolation=r[7],postmaster_start=r[8],image=image)
            before={};after={};counts={};assumptions={}
            for t in contract['tables']:
                s=schema_record(cursor,contract,t);sink=HashSink(POLICY['max_snapshot_bytes_per_table'],check);cursor.copy_expert(copy_statement(contract,t),sink)
                before[t]=dict(schema=s,projection=projection(contract,t),binary_copy=sink.record())
            for request in requests(contract):
                check();tick=time.perf_counter();cursor.execute(request['sql'],request['parameters']);row=cursor.fetchone()
                require(row is not None and all(type(v) is int and v>=0 for v in row),'Exact nonnegative SQL counts required')
                if request['kind']=='scalar_aggregate':
                    require(len(row)==3+len(request['predicate_ids']),'Truncated scalar aggregate')
                    assumptions[request['table']]=dict(rows=row[0],distinct_ids=row[1],null_ids=row[2],null_movie_ids=0,orphan_movie_ids=0)
                    for k,v in zip(request['predicate_ids'],row[3:]):require(k not in counts,'Duplicate scalar');counts[k]=v
                else:
                    require(len(row)==2,'Truncated foreign key check');assumptions[request['table']].update(null_movie_ids=row[0],orphan_movie_ids=row[1])
                sample=resources(root);validate_resources(sample);samples.append(sample)
                operations.append(dict(request=request,returned_counts=list(row),seconds=time.perf_counter()-tick))
            core.validate_counts(contract,counts,core.EXPECTED_ROWS,assumptions)
            for t in contract['tables']:
                s=schema_record(cursor,contract,t);sink=HashSink(POLICY['max_snapshot_bytes_per_table'],check);cursor.copy_expert(copy_statement(contract,t),sink)
                after[t]=dict(schema=s,projection=projection(contract,t),binary_copy=sink.record())
            require(before==after,'Database query-column snapshot changed')
            check()
        produced=dict(scope=core.SCOPE,population=core.EXPECTED_ROWS,scalar_counts=counts,assumptions=assumptions,
                    operations=operations,database_identity=identity,before=before,after=after,resources=samples,
                    seconds=time.perf_counter()-started,client_pid=os.getpid(),new_model_calls=0,server_started_or_stopped=False,
                    source_boundary=plan['source_boundary'],resource_monitor_errors=errors,resource_monitor_stopped=False)
        return produced
    finally:
        stop.set()
        try:
            if thread_started:thread.join(timeout=3)
        finally:
            try:connection.rollback()
            finally:connection.close()
        require((not thread_started or not thread.is_alive()) and not errors,
                'Resource monitor did not stop cleanly or failed at finalization: '+repr(errors))
        if produced is not None:produced['resource_monitor_stopped']=True


def execute(plan_path,approval_path,root=ROOT):
    root=Path(root).resolve();plan_path=Path(plan_path).resolve();plan=read(plan_path);approval=read(approval_path)
    validate_plan(plan,root);validate_approval(approval,plan,plan_path,root)
    directory=root/BASE/'runs'/plan['binding'][:20];directory.parent.mkdir(parents=True,exist_ok=True)
    try:directory.mkdir(exist_ok=False)
    except FileExistsError:raise ValueError('Existing namespace cannot be resumed, replaced or adopted')
    try:
        atomic(directory/'lifecycle.json',dict(status='RUNNING',binding=plan['binding'],client_pid=os.getpid()))
        atomic(directory/'plan.json',plan);atomic(directory/'approval.json',approval)
        receipt=collect(plan,root)
        validate_plan(plan,root)
        values=core.predictions(plan['contract'],receipt['scalar_counts'],receipt['population'],receipt['assumptions'])
        from full_scalar_oracle_audit import validate_receipt,verify_predictions
        validate_receipt(plan['contract'],receipt,root);verify_predictions(plan['contract'],receipt,values)
        atomic(directory/'counts.json',receipt);atomic(directory/'predictions.json',dict(scope=core.SCOPE,binding=plan['binding'],queries=values))
        verification=dict(status='PASS_LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY_COUNTS',binding=plan['binding'],scope=core.SCOPE,
                          scalar_predicates=50,queries=70,counts=artifact(directory/'counts.json',root),predictions=artifact(directory/'predictions.json',root),
                          source_boundary=plan['source_boundary'])
        atomic(directory/'verification.json',verification)
        atomic(directory/'lifecycle.json',dict(status='PASS',binding=plan['binding'],verification_sha256=digest(directory/'verification.json')))
        seal=dict(schema='scalar-oracle-final-v1',binding=plan['binding'],files={n:artifact(directory/n,root) for n in FILES})
        atomic(directory/'final_seal.json',dict(seal,self_sha256=object_hash(seal)))
        return verification
    except BaseException as error:
        atomic(directory/'lifecycle.json',dict(status='TAINTED',binding=plan['binding'],error=repr(error)));raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['plan','run']);parser.add_argument('--plan',required=True);parser.add_argument('--approval');parser.add_argument('--attempt',default='initial')
    args=parser.parse_args()
    if args.action=='plan':
        target=Path(args.plan).resolve();require((ROOT/BASE/'plans').resolve() in target.parents and not target.exists(),'New plan must be inside the independent plans directory')
        plan=build_plan(attempt=args.attempt);target.parent.mkdir(parents=True,exist_ok=True);atomic(target,plan)
        print(json.dumps(dict(status='PLAN_ONLY_NOT_EXECUTED',binding=plan['binding'],approval_template=approval_template(plan,target))))
    else:
        require(args.approval is not None,'ROOT approval file required');print(json.dumps(execute(args.plan,args.approval)))


if __name__=='__main__':main()
