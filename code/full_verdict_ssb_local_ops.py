"""Explicit LOCAL DB and budget operations; no import-time operation.

Only DB-independent frozen utilities and same-cluster process ownership are
composed. No frozen global DB, LIMITS, sample count or operation is replaced.
"""
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
SCIENCE_SCAN_METHOD='WHOLE_CIM_RESCAN_ON_UNINSPECTABLE_COMMANDLINE_V1'
SCIENCE_SCAN_MAX_RETRIES=3
RESOURCE_SCAN_METHOD='WHOLE_RESOURCE_RESCAN_ON_IN_ROOT_FILENOTFOUND_V1'
RESOURCE_SCAN_MAX_RETRIES=3


def inspect_science_processes(rows):
    """Check every header and known command; return only temporarily unreadable IDs."""
    contract.require(isinstance(rows,list),'Complete Python process rows required')
    ids=[];uninspectable=[]
    for row in rows:
        contract.require(isinstance(row,dict) and set(row)=={'Name','ProcessId','CommandLine'} and
            isinstance(row['Name'],str) and row['Name'].lower().startswith('python') and
            type(row['ProcessId']) is int and row['ProcessId']>0 and (row['CommandLine'] is None or isinstance(row['CommandLine'],str)),
            'Malformed Python process header closes LOCAL science resource window')
        ids.append(row['ProcessId'])
    contract.require(len(ids)==len(set(ids)),'Duplicate process identities in resource scan')
    for row in rows:
        if row['CommandLine'] is None or row['CommandLine']=='':
            uninspectable.append(row['ProcessId']);continue
        # Match entrypoint basenames in quoted Windows paths and -m forms.
        # In particular *_ci_run.py/_worker and *_ci_replay.py lack "model".
        if re.search(r'(?:full_ssb[^\s\\/\"\']*(?:model|ci|replay|canonical|continuation)[^\s\\/\"\']*|full_training[^\s\\/\"\']*)(?:\.py)?(?:\s|[\"\']|$)',row['CommandLine'],re.I):
            raise ValueError('Conflicting science/model/CI/replay active; LOCAL resource window closed: '+str(row['ProcessId']))
    return uninspectable


def check_science_processes(rows):
    missing=inspect_science_processes(rows)
    contract.require(not missing,'Uninspectable Python process closes LOCAL science resource window; PIDs='+str(missing))


def validate_science_scan(value):
    contract.require(isinstance(value,dict) and set(value)=={'status','command','scan_method','max_additional_rescans','additional_rescans','attempts','processes','python_processes_checked','process_ids'} and
        value['status']=='NO_CONFLICTING_SCIENCE_ACTIVE' and value['command']==SCIENCE_SCAN_COMMAND and
        value['scan_method']==SCIENCE_SCAN_METHOD and type(value['max_additional_rescans']) is int and value['max_additional_rescans']==SCIENCE_SCAN_MAX_RETRIES and
        type(value['additional_rescans']) is int and 0<=value['additional_rescans']<=SCIENCE_SCAN_MAX_RETRIES and
        isinstance(value['attempts'],list) and len(value['attempts'])==value['additional_rescans']+1,'Exact bounded LOCAL science scanner evidence required')
    for index,attempt in enumerate(value['attempts']):
        contract.require(isinstance(attempt,dict) and set(attempt)=={'attempt','processes','python_processes_checked','process_ids','uninspectable_process_ids'} and
            type(attempt['attempt']) is int and attempt['attempt']==index,'Complete ordered CIM attempts required')
        rows=attempt['processes'];missing=inspect_science_processes(rows)
        contract.require(type(attempt['python_processes_checked']) is int and attempt['python_processes_checked']==len(rows) and
            isinstance(attempt['process_ids'],list) and all(type(p) is int for p in attempt['process_ids']) and attempt['process_ids']==[r['ProcessId'] for r in rows] and
            isinstance(attempt['uninspectable_process_ids'],list) and all(type(p) is int for p in attempt['uninspectable_process_ids']) and attempt['uninspectable_process_ids']==missing and
            (bool(missing) if index<value['additional_rescans'] else not missing),'CIM retry reason or complete per-attempt process accounting differs')
    rows=value['processes'];check_science_processes(rows)
    contract.require(rows==value['attempts'][-1]['processes'] and type(value['python_processes_checked']) is int and value['python_processes_checked']==len(rows) and
        isinstance(value['process_ids'],list) and all(type(p) is int for p in value['process_ids']) and value['process_ids']==[r['ProcessId'] for r in rows],'Complete final science process accounting differs')


def assert_no_science_processes():
    attempts=[];snapshots=[]
    for retry in range(SCIENCE_SCAN_MAX_RETRIES+1):
        rows=[]
        snapshot=dict(attempt=retry,status='SNAPSHOT_UNAVAILABLE',raw_rows_available=False,processes=None,raw_row_count=None,process_ids=[])
        snapshots.append(snapshot)
        try:
            raw=subprocess.run(SCIENCE_SCAN_COMMAND,check=True,capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            value=json.loads(raw.stdout.decode('utf-8-sig')) if raw.stdout.strip() else []
            rows=value if isinstance(value,list) else [value]
            snapshot.update(status='SNAPSHOT_ACQUIRED',raw_rows_available=True,processes=rows,raw_row_count=len(rows),
                process_ids=[r['ProcessId'] for r in rows if isinstance(r,dict) and type(r.get('ProcessId')) is int and r['ProcessId']>0])
            missing=inspect_science_processes(rows)
            snapshot.update(status='UNINSPECTABLE_COMMANDLINE' if missing else 'COMPLETE_NO_CONFLICT',uninspectable_process_ids=missing)
            attempts.append(dict(attempt=retry,processes=rows,python_processes_checked=len(rows),process_ids=[r['ProcessId'] for r in rows],uninspectable_process_ids=missing))
            if missing:
                if retry<SCIENCE_SCAN_MAX_RETRIES:continue
                error=ValueError('Uninspectable Python process closes LOCAL science resource window after bounded rescans; PIDs='+str(missing))
                raise error
            result=dict(status='NO_CONFLICTING_SCIENCE_ACTIVE',command=list(SCIENCE_SCAN_COMMAND),scan_method=SCIENCE_SCAN_METHOD,
                max_additional_rescans=SCIENCE_SCAN_MAX_RETRIES,additional_rescans=retry,attempts=attempts,
                processes=rows,python_processes_checked=len(rows),process_ids=[r['ProcessId'] for r in rows])
            validate_science_scan(result);return result
        except Exception as error:
            if snapshot['status']=='SNAPSHOT_ACQUIRED':snapshot['status']='SNAPSHOT_REJECTED'
            snapshot['error_type']=type(error).__name__
            error.scan_diagnostics=dict(status='UNINSPECTABLE_COMMANDLINE' if snapshot['status']=='UNINSPECTABLE_COMMANDLINE' else 'SNAPSHOT_REJECTED',
                attempt=retry,max_additional_rescans=SCIENCE_SCAN_MAX_RETRIES,process_ids=snapshot['process_ids'],
                scan_method=SCIENCE_SCAN_METHOD,command=list(SCIENCE_SCAN_COMMAND),additional_rescans=retry,attempts=snapshots)
            raise


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
    validate_resource_scan(sample.get('resource_scan'),('home','staging','wal','temp'))


def resource_scan_receipt(retries):
    return dict(method=RESOURCE_SCAN_METHOD,max_additional_rescans=RESOURCE_SCAN_MAX_RETRIES,retries=dict(retries))


def validate_resource_scan(record,kinds):
    contract.require(isinstance(record,dict) and set(record)=={'method','max_additional_rescans','retries'} and
        record['method']==RESOURCE_SCAN_METHOD and type(record['max_additional_rescans']) is int and record['max_additional_rescans']==RESOURCE_SCAN_MAX_RETRIES and
        isinstance(record['retries'],dict) and set(record['retries'])==set(kinds) and
        all(type(n) is int and 0<=n<=RESOURCE_SCAN_MAX_RETRIES for n in record['retries'].values()),
        'Exact bounded whole-resource scan receipt required')


def resource_tree_bytes(core,kind,home,stage,trace=None):
    """Retry only a complete owned-resource scan after an in-root disappearance."""
    contract.require(kind in ('home','staging','wal','temp'),'Unknown resource scan scope')
    root={'home':Path(home),'staging':Path(stage),'wal':core.CLUSTER/'pg_wal','temp':core.CLUSTER/'base'}[kind].resolve()
    contract.require(contract.ROOT.resolve() in root.parents,'Resource scan outside project root')
    trace={} if trace is None else trace
    for retry in range(RESOURCE_SCAN_MAX_RETRIES+1):
        trace['retries']=retry
        try:
            if not root.is_dir():raise FileNotFoundError(2,'Required resource root missing',str(root))
            if kind=='temp':
                # Re-enumerate and recount every temp directory on each attempt.
                total=core.tree_bytes(root/'pgsql_tmp')+sum(core.tree_bytes(p) for p in root.glob('*/pgsql_tmp'))
            else:total=core.tree_bytes(root)
            contract.require(type(total) is int and total>=0,'Invalid complete resource byte count')
            return total,retry
        except FileNotFoundError as error:
            name=error.filename
            if not isinstance(name,(str,os.PathLike)) or not name or not Path(name).is_absolute():raise
            missing=Path(name).resolve()
            if root not in missing.parents:raise
            if kind=='temp':
                parts=missing.relative_to(root).parts
                if not (parts[0]=='pgsql_tmp' or len(parts)>1 and parts[1]=='pgsql_tmp'):raise
            if retry==RESOURCE_SCAN_MAX_RETRIES:raise


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


def validate_serial_scan(explain,target):
    schema,relation=target.split('.')
    contract.require(isinstance(explain,list) and len(explain)==1 and isinstance(explain[0],dict) and isinstance(explain[0].get('Plan'),dict),
        'One explicit physical COPY plan required')
    node=explain[0]['Plan']
    contract.require(node.get('Node Type')=='Seq Scan' and node.get('Parallel Aware') is False and
        node.get('Schema')==schema and node.get('Relation Name')==node.get('Alias')==relation and
        not any(key in node for key in ('Plans','Filter','One-Time Filter','Index Cond','Recheck Cond')),
        'Physical COPY requires only one serial unfiltered target Seq Scan')


def validate_physical_scan(proof,target,rows,keep_ctid=False):
    contract.require(isinstance(proof,dict) and proof.get('status')=='PASS_SERIAL_SEQSCAN_MONOTONIC_CTID' and
        proof.get('table')==target and type(proof.get('rows')) is int and proof['rows']==rows>0 and proof.get('keep_ctid') is keep_ctid and
        proof.get('settings')==['off','0'] and isinstance(proof.get('previous_settings'),list) and len(proof['previous_settings'])==2 and
        all(isinstance(x,str) for x in proof['previous_settings']) and proof.get('restored_settings')==proof['previous_settings'],
        'Complete physical COPY settings/order receipt required')
    first,last=proof.get('first_ctid'),proof.get('last_ctid')
    contract.require(all(isinstance(pair,list) and len(pair)==2 and all(type(x) is int for x in pair) and
        0<=pair[0]<2**32-1 and 0<pair[1]<2**16 for pair in (first,last)) and
        (first==last if rows==1 else first<last),'Invalid physical COPY CTID range')
    validate_serial_scan(proof.get('explain'),target)


class PhysicalCopySink:
    """Strip only the fixed CTID field; normalized source forbids CR/LF fields."""
    def __init__(self,sink,keep_ctid=False):
        self.sink=sink;self.keep_ctid=keep_ctid;self.pending=b'';self.first=None;self.last=None;self.rows=0
    def write(self,data):
        contract.require(isinstance(data,(str,bytes)) and len(data)<=8*1024**2,'Physical COPY fragment exceeds bounded memory')
        data=data.encode('utf-8') if isinstance(data,str) else data
        contract.require(len(data)<=8*1024**2,'Physical COPY UTF8 fragment exceeds bounded memory')
        lines=(self.pending+data).split(b'\n');self.pending=lines.pop()
        contract.require(len(self.pending)<=65536,'Incomplete physical COPY record exceeds bound')
        for line in lines:
            contract.require(len(line)<=65536 and b'\r' not in line and b'\x00' not in line,'Invalid normalized physical COPY record')
            prefix,separator,payload=line.partition(b'|');match=re.fullmatch(rb'\((0|[1-9][0-9]*),(0|[1-9][0-9]*)\)',prefix)
            contract.require(match is not None and separator and payload,'Malformed physical COPY CTID prefix/payload')
            pair=(int(match[1]),int(match[2]))
            contract.require(0<=pair[0]<2**32-1 and 0<pair[1]<2**16 and (self.last is None or self.last<pair),
                'Physical COPY CTIDs must be strictly increasing')
            self.first=self.first or pair;self.last=pair;self.rows+=1
            self.sink.write((line if self.keep_ctid else payload)+b'\n')
        return len(data)
    def finish(self):
        contract.require(not self.pending and self.rows>0 and self.rows==self.sink.rows,'Empty/incomplete physical COPY stream')


def copy_physical(c,target,columns,core,budget,keep_ctid=False):
    """One linear heap scan, verified order, exact original CSV payload bytes."""
    contract.require(re.fullmatch(r'[a-z_][a-z_0-9]*\.[a-z_][a-z_0-9]*',target) is not None,'Explicit physical COPY target required')
    settings_sql="SELECT current_setting('synchronize_seqscans'),current_setting('max_parallel_workers_per_gather')"
    restore_sql="SELECT set_config('synchronize_seqscans',%s,true),set_config('max_parallel_workers_per_gather',%s,true)"
    c.execute(settings_sql);previous=tuple(c.fetchone())
    contract.require(len(previous)==2 and all(isinstance(x,str) for x in previous),'Physical COPY original settings missing')
    query='SELECT ctid::text,'+columns+' FROM ONLY '+target
    try:
        c.execute('SET LOCAL synchronize_seqscans=off');c.execute('SET LOCAL max_parallel_workers_per_gather=0')
        c.execute(settings_sql);effective=tuple(c.fetchone());contract.require(effective==('off','0'),'Physical COPY effective settings differ')
        c.execute('EXPLAIN (VERBOSE,FORMAT JSON) '+query);explain=c.fetchone()[0];validate_serial_scan(explain,target)
        sink=core.CopyHashSink(budget);stream=PhysicalCopySink(sink,keep_ctid)
        c.copy_expert('COPY ('+query+") TO STDOUT WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N',ENCODING 'UTF8')",stream);stream.finish()
    except BaseException:
        # A failed SQL may have aborted the transaction; never mask its first error.
        try:c.execute(restore_sql,previous);contract.require(tuple(c.fetchone())==previous,'Physical COPY settings not restored')
        except BaseException:pass
        raise
    c.execute(restore_sql,previous);restored=tuple(c.fetchone());contract.require(restored==previous,'Physical COPY settings not restored')
    sink.physical_scan=dict(status='PASS_SERIAL_SEQSCAN_MONOTONIC_CTID',table=target,rows=stream.rows,keep_ctid=keep_ctid,
        first_ctid=list(stream.first),last_ctid=list(stream.last),explain=explain,settings=list(effective),previous_settings=list(previous),restored_settings=list(restored))
    validate_physical_scan(sink.physical_scan,target,sink.rows,keep_ctid);return sink


class NormalizedCopyReader:
    """One COPY consumes frozen normalized chunks, without materializing a table."""
    def __init__(self,chunks,source,budget=None):
        self.chunks=iter(chunks);self.source=source;self.budget=budget;self.buffer=b'';self.position=0
        self.normalized_rows=0;self.eof=False;self.closed=False
    def read(self,size):
        contract.require(not self.closed and type(size) is int and 0<size<=65536,'Bounded open COPY reader required')
        if self.budget is not None:self.budget.tick()
        parts=[];remaining=size
        while remaining and not self.eof:
            if self.position==len(self.buffer):
                try:n,unused,text=next(self.chunks)
                except StopIteration:self.eof=True;self.buffer=b'';self.position=0;break
                contract.require(type(n) is int and n>0 and isinstance(text,str) and len(text)<=8*1024**2 and text.endswith('\n') and text.count('\n')==n,
                    'Invalid frozen normalized COPY chunk accounting')
                self.buffer=text.encode('utf-8');self.position=0
                contract.require(len(self.buffer)<=8*1024**2,'Normalized COPY chunk exceeds memory bound')
                self.normalized_rows+=n
            take=min(remaining,len(self.buffer)-self.position)
            parts.append(self.buffer[self.position:self.position+take]);self.position+=take;remaining-=take
        data=b''.join(parts)
        if data:self.source.write(data)
        return data
    def finish(self,expected):
        contract.require(self.eof and self.position==len(self.buffer) and type(expected) is int and
            self.source.rows==self.normalized_rows==expected>0,'COPY source must reach complete exact-row EOF')
    def close(self):
        if self.closed:return
        self.closed=True;self.buffer=b'';self.position=0
        close=getattr(self.chunks,'close',None)
        if close is not None:close()


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
        validate_physical_scan(row.get('physical_scan'),row['table'],count)
        if committed:
            contract.require(row.get('status')=='PASS_COMMITTED_TABLE_IMPORT' and row.get('canonical_source')==canonical and
                row.get('import_protocol')=='FRESH_CREATE_SINGLE_COPY_SAME_TRANSACTION_V1' and row.get('created_and_copied_same_transaction') is True and
                type(row.get('copy_from_calls')) is int and row['copy_from_calls']==1 and row.get('source_eof') is True and
                type(row.get('source_normalized_rows')) is int and row['source_normalized_rows']==count and
                type(row.get('seconds')) in (int,float) and math.isfinite(row['seconds']) and row['seconds']>=0,'Committed LOCAL source/value import proof differs')
    return {row['table']:row for row in loads}


class LocalBudget:
    def __init__(self,spec,home,stage):
        self.spec=spec;self.home=Path(home);self.stage=Path(stage);self.core=contract.load_frozen()
        self.connection=None;self.samples=[];self.last_database_bytes=0
        self.resource_scan_failure=None
        self.wal_before,wal_retries=self._resource_count('wal');self.temp_before,temp_retries=self._resource_count('temp')
        self.resource_scan_baseline=resource_scan_receipt(dict(wal=wal_retries,temp=temp_retries))
        self.wal_lsn_before=None;self.last_wal_lsn=None;self.last_lsn_observed=None
    def _resource_count(self,kind):
        trace={}
        try:return resource_tree_bytes(self.core,kind,self.home,self.stage,trace)
        except BaseException as error:
            self.resource_scan_failure=dict(scope=kind,scan=resource_scan_receipt({kind:trace.get('retries',0)}),error=repr(error));raise
    def temp_bytes(self):
        return self._resource_count('temp')[0]
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
        home_bytes,home_retries=self._resource_count('home');stage_bytes,stage_retries=self._resource_count('staging')
        wal_bytes,wal_retries=self._resource_count('wal');temp_bytes,temp_retries=self._resource_count('temp')
        sample=self.core.budget_total(home_bytes+stage_bytes,self.last_database_bytes,wal_bytes,self.wal_before,temp_bytes,self.temp_before)
        sample.update(monotonic=time.monotonic(),python_rss_bytes=self.core.process_rss(os.getpid()),
            resource_scan=resource_scan_receipt(dict(home=home_retries,staging=stage_retries,wal=wal_retries,temp=temp_retries)))
        if self.wal_lsn_before is not None and lsn is not None:sample.update(wal_lsn=lsn,wal_generated_bytes=self.core.lsn_integer(lsn)-self.core.lsn_integer(self.wal_lsn_before),
            wal_lsn_observed_monotonic=self.last_lsn_observed,monitor_connection_live=self.connection is not None)
        self.samples.append(sample);validate_budget_sample(self.spec,sample);return sample
    def report(self):
        return dict(spec_limits=self.spec['limits'],samples=self.samples,peak_total_bytes=max((x['total_bytes'] for x in self.samples),default=0),wal_lsn_before=self.wal_lsn_before,
            resource_scan_baseline=self.resource_scan_baseline,resource_scan_failure=self.resource_scan_failure,
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
                c.execute(self.core.create_table_sql('lineorder',plan['schema_contract']['lineorder'],'postgres'))
                connection.commit()
                for table,path,terminal,expected in expected_inputs(plan):
                    assert_no_science_processes()
                    started=time.monotonic();target=self.spec['sample_relation'] if table=='lineorder' else 'public.'+table
                    columns=','.join('"'+name+'"' for name,kind in plan['schema_contract'][table]['columns'])
                    source=self.core.CopyHashSink();reader=None;actual=None;copy_calls=0;copy_completed=False;failed=False;stage='CREATE_TARGET'
                    try:
                        # PG11.5 skips FSM only when this target is new in this transaction.
                        if table=='lineorder':
                            c.execute('CREATE TABLE '+target+' (LIKE public.lineorder INCLUDING DEFAULTS)')
                            c.execute('ALTER TABLE '+target+' ADD COLUMN verdict_vprob double precision NOT NULL DEFAULT ({}::double precision/{}::double precision), ADD COLUMN verdict_vpart integer NOT NULL DEFAULT mod(cast(round(random()*100) as integer),100)'.format(self.spec['sample_rows'],self.spec['population_rows']))
                            c.execute('SELECT setseed(%s)',(self.spec['partition_seed'],))
                        else:c.execute(self.core.create_table_sql(table,plan['schema_contract'][table],'postgres'))
                        reader=NormalizedCopyReader(self.core.raw_chunks(path,len(plan['schema_contract'][table]['columns']),terminal),source,budget)
                        stage='COPY_FROM';copy_calls+=1
                        c.copy_expert('COPY '+target+' ('+columns+") FROM STDIN WITH(FORMAT CSV,DELIMITER '|',NULL E'\\\\N',ENCODING 'UTF8')",reader,size=65536)
                        copy_completed=True;stage='SOURCE_EOF';reader.finish(expected);count=reader.normalized_rows
                        stage='SOURCE_CLOSE';reader.close()
                        stage='READBACK';actual=copy_physical(c,target,columns,self.core,budget)
                        stage='COMPARE';contract.require(source.result()==actual.result(),'LOCAL complete imported field/order/duplicate accounting differs')
                        stage='COMMIT';connection.commit()
                        loads.append(dict(status='PASS_COMMITTED_TABLE_IMPORT',table=target,rows=count,canonical_source=source.result(),canonical_actual=actual.result(),
                            physical_scan=actual.physical_scan,seconds=time.monotonic()-started,import_protocol='FRESH_CREATE_SINGLE_COPY_SAME_TRANSACTION_V1',
                            created_and_copied_same_transaction=True,copy_from_calls=copy_calls,source_eof=reader.eof,source_normalized_rows=reader.normalized_rows))
                        stage='RECEIPT';self.core.atomic_json(home/('import_'+table+'.json'),loads[-1])
                    except BaseException as error:
                        failed=True
                        failure=dict(status='FAILED_LOCAL_TABLE_IMPORT',table=target,stage=stage,expected_rows=expected,copy_from_calls=copy_calls,copy_from_completed=copy_completed,
                            source=source.result(),source_eof=reader is not None and reader.eof,source_normalized_rows=0 if reader is None else reader.normalized_rows,
                            actual=None if actual is None else actual.result(),physical_scan=None if actual is None else actual.physical_scan,error=repr(error))
                        try:self.core.atomic_json(home/('import_'+table+'_failure.json'),failure)
                        except BaseException:pass # Preserve the first import error if diagnostics cannot be written.
                        raise
                    finally:
                        if reader is not None:
                            try:reader.close()
                            except BaseException:
                                if not failed:raise
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
        sink=copy_physical(c,self.spec['sample_relation'],"encode(float8send(verdict_vprob),'hex'),verdict_vpart",self.core,budget,True)
        return dict(sink.result(),physical_scan=sink.physical_scan)
    def locked_snapshot(self,plan,home,c,budget):
        before=contract.read(home/'protected_before.json');protected=self.protected()
        contract.require(set(before)==set(self.spec['protected_databases']) and before==protected,'Protected prior3 catalog identities changed')
        imported=contract.read(home/'import.json');loads=[]
        for table,path,terminal,expected in expected_inputs(plan):
            target=self.spec['sample_relation'] if table=='lineorder' else 'public.'+table
            columns=','.join('"'+name+'"' for name,kind in plan['schema_contract'][table]['columns']);sink=copy_physical(c,target,columns,self.core,budget)
            previous=next(x for x in imported['loads'] if x['table']==target);contract.require(previous['canonical_source']==sink.result() and sink.rows==expected,'Locked LOCAL original fields changed')
            loads.append(dict(table=target,canonical_actual=sink.result(),physical_scan=sink.physical_scan,rows=expected))
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
