"""Explicit LOCAL DB and budget operations; no import-time operation.

Only DB-independent frozen utilities and same-cluster process ownership are
composed. No frozen global DB, LIMITS, sample count or operation is replaced.
"""
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import full_verdict_ssb_local as contract

SCIENCE_SCAN_COMMAND=['powershell.exe','-NoProfile','-Command',
    '[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); Get-CimInstance Win32_Process -Filter "Name LIKE \'python%.exe\'" | Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress']


def check_science_processes(rows):
    contract.require(isinstance(rows,list),'Complete Python process rows required')
    ids=[]
    for row in rows:
        contract.require(isinstance(row,dict) and set(row)=={'Name','ProcessId','CommandLine'} and
            isinstance(row['Name'],str) and row['Name'].lower().startswith('python') and
            type(row['ProcessId']) is int and row['ProcessId']>0 and isinstance(row['CommandLine'],str) and bool(row['CommandLine']),
            'Uninspectable Python process closes LOCAL science resource window')
        ids.append(row['ProcessId'])
        # Match entrypoint basenames in quoted Windows paths and -m forms.
        # In particular *_ci_run.py/_worker and *_ci_replay.py lack "model".
        if re.search(r'(?:full_ssb[^\s\\/\"\']*(?:model|ci|replay)[^\s\\/\"\']*|full_training[^\s\\/\"\']*)(?:\.py)?(?:\s|[\"\']|$)',row['CommandLine'],re.I):
            raise ValueError('Conflicting science/model/CI/replay active; LOCAL resource window closed: '+str(row['ProcessId']))
    contract.require(len(ids)==len(set(ids)),'Duplicate process identities in resource scan')


def validate_science_scan(value):
    contract.require(value.get('status')=='NO_CONFLICTING_SCIENCE_ACTIVE' and value.get('command')==SCIENCE_SCAN_COMMAND,'Explicit LOCAL science scanner evidence required')
    rows=value.get('processes');check_science_processes(rows)
    contract.require(value.get('python_processes_checked')==len(rows) and value.get('process_ids')==[r['ProcessId'] for r in rows],'Complete science process accounting differs')


def assert_no_science_processes():
    raw=subprocess.run(SCIENCE_SCAN_COMMAND,check=True,capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    value=json.loads(raw.stdout.decode('utf-8-sig')) if raw.stdout.strip() else []
    rows=value if isinstance(value,list) else [value];check_science_processes(rows)
    result=dict(status='NO_CONFLICTING_SCIENCE_ACTIVE',command=SCIENCE_SCAN_COMMAND,processes=rows,python_processes_checked=len(rows),process_ids=[r['ProcessId'] for r in rows])
    validate_science_scan(result);return result


def probability_hex(spec):return struct.pack('!d',spec['sample_rows']/spec['population_rows']).hex()


def validate_metadata(spec,size,names):
    ns,table=spec['sample_relation'].split('.')
    contract.require(size==[[ns,table,spec['sample_rows'],spec['population_rows']]] and
        names==[['public','lineorder',ns,table,'uniform',spec['sample_rows']/spec['population_rows'],'']],
        'Native metadata must register only the LOCAL actual-fraction fact sample')


def validate_aux(spec,account,parts,bits):
    n,N=spec['sample_rows'],spec['population_rows']
    contract.require(account==[n,n/N,n/N,0,99] and bits==[probability_hex(spec)]*2,'LOCAL exact count/probability/native bits/partition bounds differ')
    contract.require([p[0] for p in parts]==list(range(100)) and all(type(p[1]) is int and p[1]>0 for p in parts) and sum(p[1] for p in parts)==n,'LOCAL100 complete unique nonempty partitions required')


def validate_budget_sample(spec,sample):
    limits=spec['limits'];keys=('owned_files_bytes','owned_database_bytes','positive_wal_bytes','positive_temp_bytes')
    contract.require(all(type(sample.get(k)) is int and sample[k]>=0 for k in keys+('total_bytes','python_rss_bytes')),'LOCAL resource counts must be nonnegative integers')
    contract.require(sample['total_bytes']==sum(sample[k] for k in keys) and sample['total_bytes']<=limits['total_new_bytes'] and
        all(sample[k]<=limits[k] for k in keys) and sample['python_rss_bytes']<=limits['python_rss_bytes'],'LOCAL component/total/RSS budget exceeded')


def expected_schema(plan):
    schema=plan['schema_contract'];s=plan['spec'];result={}
    for t,v in schema.items():result['public.'+t]=[[col,kind.lower().replace('varchar','character varying'),True] for col,kind in v['columns']]
    result[s['sample_relation']]=result['public.lineorder']+[['verdict_vprob','double precision',True],['verdict_vpart','integer',True]]
    result['public_verdict.verdict_meta_size']=[[n,k,False] for n,k in [('schemaname','character varying(120)'),('tablename','character varying(120)'),('samplesize','bigint'),('originaltablesize','bigint')]]
    result['public_verdict.verdict_meta_name']=[[n,'double precision' if n=='samplingratio' else 'character varying(120)',False] for n in ('originalschemaname','originaltablename','sampleschemaaname','sampletablename','sampletype','samplingratio','columnnames')]
    return result


def expected_inputs(plan):
    source=plan['lineage']['source'];s=plan['spec'];items=[]
    for key,t in [('date','dwdate'),('customer','customer'),('part','part'),('supplier','supplier')]:
        d=source['dimensions'][key];contract.require(d['rows']==s['dimension_rows'][t],'LOCAL full dimension cardinality differs')
        items.append((t,contract.ROOT/d['path'],True,d['rows']))
    d=source['raw_sample'];contract.require(d['rows']==s['sample_rows'] and d['fields']==17,'LOCAL retained sample shape differs')
    items.append(('lineorder',contract.ROOT/d['path'],False,s['sample_rows']));return items


def validate_loads(spec,loads,committed=False):
    expected={'public.'+table:rows for table,rows in spec['dimension_rows'].items()}
    expected[spec['sample_relation']]=spec['sample_rows']
    contract.require(isinstance(loads,list) and len(loads)==5 and {r.get('table') for r in loads}==set(expected),'Exactly five unique LOCAL full-field targets required')
    for row in loads:
        count=expected[row['table']]
        contract.require(type(row.get('rows')) is int and row['rows']==count,'LOCAL full-field target row count differs')
        canonical=row.get('canonical_actual',{})
        contract.require(set(canonical)=={'bytes','rows','sha256'} and type(canonical['bytes']) is int and canonical['bytes']>0 and
            type(canonical['rows']) is int and canonical['rows']==count and isinstance(canonical['sha256'],str) and re.fullmatch('[0-9a-f]{64}',canonical['sha256']),
            'Complete LOCAL canonical field statistics required')
        if committed:
            contract.require(row.get('status')=='PASS_COMMITTED_TABLE_IMPORT' and row.get('canonical_source')==canonical and
                type(row.get('seconds')) in (int,float) and math.isfinite(row['seconds']) and row['seconds']>=0,'Committed LOCAL source/value import proof differs')
    return {row['table']:row for row in loads}


class LocalBudget:
    def __init__(self,spec,home,stage):
        self.spec=spec;self.home=Path(home);self.stage=Path(stage);self.core=contract.load_frozen()
        self.connection=None;self.samples=[];self.last_database_bytes=0
        self.wal_before=self.core.tree_bytes(self.core.CLUSTER/'pg_wal');self.temp_before=self.temp_bytes();self.wal_lsn_before=None;self.last_wal_lsn=None;self.last_lsn_observed=None
    def temp_bytes(self):
        root=self.core.CLUSTER/'base'
        return self.core.tree_bytes(root/'pgsql_tmp')+sum(self.core.tree_bytes(p) for p in root.glob('*/pgsql_tmp'))
    def attach(self,db):
        self.connection=db.connect('postgres',True)
        with self.connection.cursor() as c:c.execute('SELECT pg_current_wal_lsn()::text');self.wal_lsn_before=c.fetchone()[0]
        self.tick(force=True)
    def close(self):
        if self.connection is not None:self.connection.close();self.connection=None
    def tick(self,force=False):
        if self.samples and not force and time.monotonic()-self.samples[-1]['monotonic']<.25:return self.samples[-1]
        lsn=self.last_wal_lsn
        if self.connection is not None:
            with self.connection.cursor() as c:
                c.execute('SELECT pg_database_size(oid) FROM pg_database WHERE datname=%s',(self.spec['database'],));r=c.fetchone()
                self.last_database_bytes=0 if r is None else int(r[0])
                c.execute('SELECT pg_current_wal_lsn()::text');lsn=c.fetchone()[0]
                self.last_wal_lsn=lsn;self.last_lsn_observed=time.monotonic()
        sample=self.core.budget_total(self.core.tree_bytes(self.home)+self.core.tree_bytes(self.stage),self.last_database_bytes,
            self.core.tree_bytes(self.core.CLUSTER/'pg_wal'),self.wal_before,self.temp_bytes(),self.temp_before)
        sample.update(monotonic=time.monotonic(),python_rss_bytes=self.core.process_rss(os.getpid()))
        if self.wal_lsn_before is not None and lsn is not None:sample.update(wal_lsn=lsn,wal_generated_bytes=self.core.lsn_integer(lsn)-self.core.lsn_integer(self.wal_lsn_before),
            wal_lsn_observed_monotonic=self.last_lsn_observed,monitor_connection_live=self.connection is not None)
        self.samples.append(sample);validate_budget_sample(self.spec,sample);return sample
    def report(self):
        return dict(spec_limits=self.spec['limits'],samples=self.samples,peak_total_bytes=max(x['total_bytes'] for x in self.samples),wal_lsn_before=self.wal_lsn_before,
            scope='LOCAL own DB/files + positive physical cluster WAL/temp; no whole-drive delta; finite polling window',
            wal_lsn_scope='First live PG monitor before import through last live monitor before owned shutdown; stopped samples retain the last observed LSN with its timestamp')


class LocalDatabase:
    def __init__(self,spec=None):
        self.spec=spec or contract.local_spec();contract.require(self.spec==contract.local_spec(),'Only the explicit reviewed LOCAL spec is supported')
        self.core=contract.load_frozen()
        contract.require(self.core.LIMITS['java_rss_bytes']==self.spec['limits']['java_rss_bytes'],'Frozen generic process cap must exactly match explicit LOCAL cap')
    def connect(self,database=None,autocommit=False):
        database=database or self.spec['database']
        contract.require(database in [self.spec['database'],'postgres']+self.spec['protected_databases'],'Forbidden LOCAL connection target')
        import psycopg2
        limits=self.spec['limits']
        connection=psycopg2.connect(host='127.0.0.1',port=55432,user='postgres',dbname=database,connect_timeout=10,
            application_name='verdict_local_ssb_controller',options='-c statement_timeout={} -c work_mem={} -c temp_file_limit={} -c extra_float_digits=3'.format(limits['statement_timeout_ms'],limits['work_mem_kib'],limits['temp_file_limit_kib']))
        connection.autocommit=autocommit;return connection
    def no_external_clients(self):
        connection=self.connect('postgres',True)
        try:
            with connection.cursor() as c:
                c.execute("SELECT datname,application_name,pid FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")
                contract.require(not [r for r in c.fetchall() if not r[1].startswith('verdict_local_ssb_')],'External PostgreSQL clients present')
                c.execute('SELECT spcname FROM pg_tablespace ORDER BY spcname');contract.require([x[0] for x in c.fetchall()]==['pg_default','pg_global'],'External tablespace is not allowed')
        finally:connection.close()
    def protected(self):
        result={}
        for database in self.spec['protected_databases']:
            connection=self.connect(database,True)
            try:
                with connection.cursor() as c:
                    c.execute('SELECT oid FROM pg_database WHERE datname=current_database()');oid=c.fetchone()[0]
                    c.execute("SELECT n.nspname,c.relname,c.relkind,c.oid,c.relfilenode FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname,c.oid")
                    result[database]=dict(oid=oid,relations=[list(x) for x in c.fetchall()])
            finally:connection.close()
        return result
    def import_data(self,plan,home,budget):
        self.no_external_clients();before=self.protected();self.core.atomic_json(home/'protected_before.json',before)
        admin=self.connect('postgres',True)
        try:
            with admin.cursor() as c:
                c.execute('SHOW server_version');version=c.fetchone()[0]
                c.execute('SHOW data_directory');directory=c.fetchone()[0]
                contract.require(version.startswith('11.5') and Path(directory).resolve()==self.core.CLUSTER.resolve(),'Wrong project PG version/cluster')
                c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(self.spec['database'],));contract.require(c.fetchone() is None,'LOCAL database exists; no automatic replacement')
                c.execute('CREATE DATABASE '+self.spec['database'])
        finally:admin.close()
        connection=self.connect();loads=[]
        try:
            with connection.cursor() as c:
                c.execute('CREATE SCHEMA public_verdict')
                for table,schema in plan['schema_contract'].items():c.execute(self.core.create_table_sql(table,schema,'postgres'))
                c.execute('CREATE TABLE '+self.spec['sample_relation']+' (LIKE public.lineorder INCLUDING DEFAULTS)')
                c.execute('ALTER TABLE '+self.spec['sample_relation']+' ADD COLUMN verdict_vprob double precision NOT NULL DEFAULT ({}::double precision/{}::double precision), ADD COLUMN verdict_vpart integer NOT NULL DEFAULT mod(cast(round(random()*100) as integer),100)'.format(self.spec['sample_rows'],self.spec['population_rows']))
                c.execute('SELECT setseed(%s)',(self.spec['partition_seed'],))
                connection.commit()
                for table,path,terminal,expected in expected_inputs(plan):
                    assert_no_science_processes()
                    started=time.monotonic();target=self.spec['sample_relation'] if table=='lineorder' else 'public.'+table
                    columns=','.join('"'+name+'"' for name,kind in plan['schema_contract'][table]['columns'])
                    source=self.core.CopyHashSink();count=0
                    for n,unused,text in self.core.raw_chunks(path,len(plan['schema_contract'][table]['columns']),terminal):
                        source.write(text);c.copy_expert('COPY '+target+' ('+columns+") FROM STDIN WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N')",io.StringIO(text));count+=n;budget.tick()
                    actual=self.core.CopyHashSink(budget)
                    c.copy_expert('COPY (SELECT '+columns+' FROM '+target+" ORDER BY ctid) TO STDOUT WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N')",actual)
                    contract.require(count==expected and source.result()==actual.result(),'LOCAL complete imported field/order/duplicate accounting differs')
                    connection.commit()
                    loads.append(dict(status='PASS_COMMITTED_TABLE_IMPORT',table=target,rows=count,canonical_source=source.result(),canonical_actual=actual.result(),seconds=time.monotonic()-started))
                    self.core.atomic_json(home/('import_'+table+'.json'),loads[-1])
                c.execute('SELECT COUNT(*) FROM public.lineorder');contract.require(c.fetchone()[0]==0,'Original LOCAL fact skeleton must remain empty')
                connection.commit()
            with connection.cursor() as c:
                for table in [r['table'] for r in loads]:c.execute('ANALYZE '+table)
                connection.commit()
            receipt=dict(status='PASS_LOCAL_FULL_DIMENSIONS_RETAINED_FACT_IMPORT',loads=loads,population_rows=self.spec['population_rows'],sample_rows=self.spec['sample_rows'],original_fact_rows=0,
                dimension_policy=self.spec['dimension_policy'],original_queries_executed=0,server=dict(version=version,data_directory=directory))
            self.core.atomic_json(home/'import.json',receipt);return receipt
        finally:connection.close()
    def catalog(self,c):
        c.execute('SELECT oid,datname,datdba,encoding,datcollate,datctype FROM pg_database WHERE datname=current_database()');row=list(c.fetchone())
        contract.require(row[1]==self.spec['database'],'Wrong LOCAL own DB')
        c.execute("SELECT n.nspname,c.relname,c.relkind,c.oid,c.relfilenode FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname,c.oid")
        relations=[list(x) for x in c.fetchall()]
        validate_catalog(self.spec,dict(database=row,relations=relations))
        c.execute("SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname IN ('public','public_verdict'))")
        contract.require(c.fetchone()[0]==0,'External triggers in LOCAL namespace')
        return dict(database=row,relations=relations)
    def aux_hash(self,c,budget):
        sink=self.core.CopyHashSink(budget)
        c.copy_expert("COPY (SELECT ctid::text,encode(float8send(verdict_vprob),'hex'),verdict_vpart FROM "+self.spec['sample_relation']+" ORDER BY ctid) TO STDOUT WITH(FORMAT CSV,DELIMITER '|')",sink)
        return sink.result()
    def locked_snapshot(self,plan,home,c,budget):
        before=contract.read(home/'protected_before.json');protected=self.protected()
        contract.require(set(before)==set(self.spec['protected_databases']) and before==protected,'Protected prior3 catalog identities changed')
        imported=contract.read(home/'import.json');loads=[]
        for table,path,terminal,expected in expected_inputs(plan):
            target=self.spec['sample_relation'] if table=='lineorder' else 'public.'+table
            columns=','.join('"'+name+'"' for name,kind in plan['schema_contract'][table]['columns']);sink=self.core.CopyHashSink(budget)
            c.copy_expert('COPY (SELECT '+columns+' FROM '+target+" ORDER BY ctid) TO STDOUT WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N')",sink)
            previous=next(x for x in imported['loads'] if x['table']==target);contract.require(previous['canonical_source']==sink.result() and sink.rows==expected,'Locked LOCAL original fields changed')
            loads.append(dict(table=target,canonical_actual=sink.result(),rows=expected))
        c.execute('SELECT COUNT(*),MIN(verdict_vprob),MAX(verdict_vprob),MIN(verdict_vpart),MAX(verdict_vpart),encode(float8send(MIN(verdict_vprob)),\'hex\'),encode(float8send(MAX(verdict_vprob)),\'hex\') FROM '+self.spec['sample_relation']);account=list(c.fetchone())
        c.execute('SELECT verdict_vpart,COUNT(*) FROM '+self.spec['sample_relation']+' GROUP BY verdict_vpart ORDER BY verdict_vpart');parts=[list(x) for x in c.fetchall()]
        validate_aux(self.spec,account[:5],parts,account[5:])
        c.execute('SELECT * FROM public_verdict.verdict_meta_size');size=[list(x) for x in c.fetchall()]
        c.execute('SELECT * FROM public_verdict.verdict_meta_name');names=[list(x) for x in c.fetchall()];validate_metadata(self.spec,size,names)
        c.execute("SELECT n.nspname,c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid JOIN pg_attribute a ON a.attrelid=c.oid WHERE n.nspname IN ('public','public_verdict') AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY n.nspname,c.relname,a.attnum")
        schema={}
        for ns,table,col,kind,nn in c.fetchall():schema.setdefault(ns+'.'+table,[]).append([col,kind,nn])
        contract.require(schema==expected_schema(plan),'LOCAL full schema or dimension sampling changed')
        c.execute('SELECT COUNT(*) FROM public.lineorder');empty=c.fetchone()[0]
        contract.require(empty==0,'LOCAL skeleton changed')
        return dict(status='PASS_LOCAL_LOCKED_FULL_INPUT_SNAPSHOT',loads=loads,aux_accounting=account[:5],probability_hex=account[5:],partition_histogram=parts,
            metadata_size=size,metadata_name=names,schema=schema,catalog=self.catalog(c),aux_rows=self.aux_hash(c,budget),original_fact_rows=empty,
            protected_before=before,protected_after=protected)


def validate_catalog(spec,value):
    rows=value.get('relations',[]);db=value.get('database',[])
    expected={('public',t,'r') for t in ('dwdate','customer','part','supplier','lineorder')}
    expected|={('public_verdict',t,'r') for t in (spec['sample_relation'].split('.')[1],'verdict_meta_size','verdict_meta_name')}
    expected|={('public',t+'_pkey','i') for t in ('dwdate','customer','part','supplier')}
    contract.require(len(db)==6 and db[1]==spec['database'] and type(db[0]) is int and db[0]>0 and len(rows)==12 and
        all(len(x)==5 and type(x[3]) is int and x[3]>0 and type(x[4]) is int and x[4]>0 for x in rows) and len({x[3] for x in rows})==12 and
        {tuple(x[:3]) for x in rows}==expected,'Exact LOCAL own DB/table/index identities required')
