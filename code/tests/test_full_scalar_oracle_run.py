"""Only synthetic databases and temporary receipts; no PostgreSQL imports."""
import importlib
import json
import os
from pathlib import Path
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import full_scalar_oracle as core


@pytest.fixture
def run():
    return importlib.import_module('full_scalar_oracle_run')


def test_absent_approval_never_connects(run, tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'connect', lambda: pytest.fail('No database permission'))
    with pytest.raises((ValueError, FileNotFoundError)):
        run.execute(tmp_path/'missing-plan.json', tmp_path/'missing-approval.json', root=tmp_path)
    assert not (tmp_path/'output/full/scalar_oracle/runs').exists()


def test_projection_uses_only_actual_integer_columns_and_original_join_keys(run):
    c=core.workload()
    assert run.projection(c,'title') == ['id','kind_id','production_year']
    assert 'movie_id' in run.projection(c,'movie_info')
    assert 'info' not in run.projection(c,'movie_info')
    assert run.copy_statement(c,'title') == 'COPY (SELECT "id", "kind_id", "production_year" FROM public."title" ORDER BY "id") TO STDOUT WITH (FORMAT BINARY)'


@pytest.mark.parametrize('bad', [None, True, -1, float('nan'), float('inf')])
def test_invalid_resource_measurement_cannot_be_published(run,bad):
    sample={'available_memory_bytes':6*1024**3,'process_rss_bytes':1024**2,'free_disk_bytes':20*1024**3}
    sample['available_memory_bytes']=bad
    with pytest.raises(ValueError):run.validate_resources(sample,startup=True)


def test_same_plan_requires_exact_approval_scope_and_file_bytes(run,tmp_path):
    p=tmp_path/'plan.json';p.write_text('{}')
    plan={'binding':'b'*64}
    good=run.approval_template(plan,p,tmp_path)
    with pytest.raises(ValueError):run.validate_approval(good,plan,p,tmp_path)
    good['status']='APPROVED_BY_ROOT_FOR_SINGLE_SCALAR_ORACLE_RUN'
    good['root_review_reference']='ROOT explicit review, synthetic fixture'
    run.validate_approval(good,plan,p,tmp_path)
    for field,value in [('binding','a'*64),('exclusive_window',False),('root_review_reference','')]:
        bad=dict(good);bad[field]=value
        with pytest.raises(ValueError):run.validate_approval(bad,plan,p,tmp_path)
    p.write_text('{"changed":true}')
    with pytest.raises(ValueError):run.validate_approval(good,plan,p,tmp_path)


def test_hash_sink_is_streaming_and_caps_total_bytes(run):
    sink=run.HashSink(10)
    assert sink.write(b'abc')==3 and sink.write(b'de')==2
    assert sink.record()=={'bytes':5,'sha256':'36bbe50ed96841d10443bcb670d6554f0a34b761be67ec9c4a8ad2c0c44ca42c'}
    with pytest.raises(ValueError):sink.write(b'012345')


def test_query_and_operation_payloads_are_exactly_bound(run):
    c=core.workload()
    requests=run.requests(c)
    assert len([x for x in requests if x['kind']=='scalar_aggregate'])==6
    assert len([x for x in requests if x['kind']=='foreign_key_check'])==5
    assert all('CREATE' not in x['sql'] and 'INSERT' not in x['sql'] and 'UPDATE' not in x['sql'] for x in requests)
    assert sum(len(x.get('predicate_ids',[])) for x in requests)==50


def test_schema_rejects_views_missing_pk_noninteger_columns_and_extra_inheritance(run):
    c=core.workload();columns=run.projection(c,'title')
    schema={'table':'title','oid':12,'relkind':'r','relfilenode':12,'inherits':False,
            'primary_key':['id'],'valid_primary_key':True,'columns':[[n,23] for n in columns]}
    run.validate_schema(c,'title',schema)
    for field,value in [('relkind','v'),('valid_primary_key',False),('inherits',True),('primary_key',['kind_id'])]:
        bad=dict(schema);bad[field]=value
        with pytest.raises(ValueError):run.validate_schema(c,'title',bad)
    bad=dict(schema,columns=[['id',23],['kind_id',23],['production_year',25]])
    with pytest.raises(ValueError):run.validate_schema(c,'title',bad)


def test_tainted_namespace_cannot_be_recovered_after_input_restoration(run,tmp_path,monkeypatch):
    plan={'binding':'b'*64,'contract':core.workload(),'scope':core.SCOPE}
    p=tmp_path/'plan.json';a=tmp_path/'approval.json';p.write_text(json.dumps(plan));a.write_text('{}')
    monkeypatch.setattr(run,'validate_plan',lambda *_:None)
    monkeypatch.setattr(run,'validate_approval',lambda *_:None)
    monkeypatch.setattr(run,'collect',lambda *_:(_ for _ in ()).throw(RuntimeError('synthetic cancelled count')))
    with pytest.raises(RuntimeError):run.execute(p,a,root=tmp_path)
    directory=tmp_path/'output/full/scalar_oracle/runs'/('b'*20)
    assert json.loads((directory/'lifecycle.json').read_text())['status']=='TAINTED'
    monkeypatch.setattr(run,'collect',lambda *_:pytest.fail('A failed namespace must never execute again'))
    with pytest.raises(ValueError):run.execute(p,a,root=tmp_path)


def test_preexisting_unowned_namespace_is_not_overwritten(run,tmp_path,monkeypatch):
    plan={'binding':'b'*64};p=tmp_path/'plan.json';a=tmp_path/'approval.json';p.write_text(json.dumps(plan));a.write_text('{}')
    monkeypatch.setattr(run,'validate_plan',lambda *_:None);monkeypatch.setattr(run,'validate_approval',lambda *_:None)
    d=tmp_path/'output/full/scalar_oracle/runs'/('b'*20);d.mkdir(parents=True);(d/'unowned').write_text('keep')
    with pytest.raises(ValueError):run.execute(p,a,root=tmp_path)
    assert (d/'unowned').read_text()=='keep' and not (d/'lifecycle.json').exists()


def test_wrong_loaded_core_is_rejected_before_runtime_inventory(run,tmp_path,monkeypatch):
    monkeypatch.setattr(core,'__file__',str(tmp_path/'elsewhere.py'))
    monkeypatch.setattr(run,'runtime_paths',lambda *_:pytest.fail('Wrong imported source must fail first'))
    with pytest.raises(ValueError,match='loaded'):
        run.dependency_snapshot()


def test_actual_collection_control_flow_sets_readonly_before_any_sql_and_releases_client(run,tmp_path,monkeypatch):
    contract=core.workload();tables=contract['tables'];queries=run.requests(contract);seen=[]
    counts={p['id']:0 if p['conditions'] else core.EXPECTED_ROWS[p['table']] for p in contract['predicates']}
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,statement,parameters=None):
            assert connection.session==dict(isolation_level='REPEATABLE READ',readonly=True,autocommit=False)
            seen.append(statement);self.result=[]
            if statement.startswith('SELECT current_database'):
                # Actual PostgreSQL 11 inet::text includes /32; host(inet)
                # returns the host-only value used by the strict identity gate.
                address='127.0.0.1' if 'host(inet_server_addr())' in statement else '127.0.0.1/32'
                self.result=[('deepdb_job','110005',address,55432,str(tmp_path/'data/postgresql/cluster'),456,'on','repeatable read','synthetic')]
            elif statement.startswith('SELECT c.oid'):
                table=parameters[0];i=tables.index(table)+1;self.result=[(i,'r',i,False)]
            elif statement.startswith('SELECT attname'):
                self.result=[(n,23) for n in sorted(core.COLUMNS[tables[parameters[0]-1]])]
            elif statement.startswith('SELECT a.attname'):self.result=[('id',True,True)]
            else:
                for req in queries:
                    if req['sql']==statement:
                        assert parameters==req['parameters']
                        if req['kind']=='scalar_aggregate':
                            n=core.EXPECTED_ROWS[req['table']];self.result=[tuple([n,n,0]+[counts[k] for k in req['predicate_ids']])]
                        else:self.result=[(0,0)]
                        break
                else:assert statement.startswith(('SET LOCAL','LOCK TABLE'))
        def fetchone(self):return self.result[0]
        def fetchall(self):return self.result
        def copy_expert(self,statement,sink):
            assert statement in [run.copy_statement(contract,t) for t in tables]
            seen.append(statement);sink.write(statement.encode('ascii'))
    class Connection:
        session=None;closed=False;rolled_back=False
        def set_session(self,**kwargs):self.session=kwargs
        def cursor(self):return Cursor()
        def rollback(self):self.rolled_back=True
        def close(self):self.closed=True
        def cancel(self):pytest.fail('No synthetic resource violation')
    connection=Connection()
    monkeypatch.setattr(run,'connect',lambda:connection)
    monkeypatch.setattr(run,'resources',lambda root:dict(available_memory_bytes=6*1024**3,process_rss_bytes=1024**2,free_disk_bytes=20*1024**3))
    monkeypatch.setattr(run,'backend_image',lambda pid:str(tmp_path/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe'))
    plan=dict(contract=contract,source_boundary='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY')
    r=run.collect(plan,tmp_path)
    assert len(r['scalar_counts'])==50 and len(r['operations'])==11
    assert r['database_identity']['address']=='127.0.0.1'
    assert 'host(inet_server_addr())' in next(s for s in seen if s.startswith('SELECT current_database'))
    assert sum(s.startswith('COPY ') for s in seen)==12
    assert not any(s.startswith(('CREATE','INSERT','UPDATE','DROP','BEGIN')) for s in seen)
    assert seen.index(next(s for s in seen if s.startswith('LOCK TABLE'))) < seen.index(next(s for s in seen if s.startswith('SELECT')))
    assert connection.closed and connection.rolled_back and r['resource_monitor_stopped'] is True


@pytest.mark.parametrize('raises',[False,True])
def test_database_connect_cannot_consume_external_pg_service_options_or_passfiles(run,monkeypatch,raises):
    monkeypatch.setenv('PGSERVICE','synthetic_external_service');monkeypatch.setenv('PGOPTIONS','synthetic_options');monkeypatch.setenv('PGPASSFILE','synthetic_external_file')
    expected={k:v for k,v in os.environ.items() if k.upper().startswith('PG')}
    def connector(**kwargs):
        assert not any(k.upper().startswith('PG') for k in os.environ)
        assert kwargs['sslmode']=='disable'
        assert kwargs['host']=='127.0.0.1' and kwargs['port']==55432 and kwargs['dbname']=='deepdb_job'
        if raises:raise RuntimeError('synthetic connect failure')
        return 'synthetic-connection'
    monkeypatch.setitem(sys.modules,'psycopg2',types.SimpleNamespace(__file__=str(run.ROOT/'.venv/Lib/site-packages/psycopg2/__init__.py'),connect=connector))
    if raises:
        with pytest.raises(RuntimeError):run.connect()
    else:assert run.connect()=='synthetic-connection'
    assert {k:v for k,v in os.environ.items() if k.upper().startswith('PG')}==expected


def test_empty_runtime_members_stay_in_complete_closure_but_results_cannot_be_empty(run,tmp_path):
    p=tmp_path/'empty_init.py';p.write_bytes(b'')
    with pytest.raises(ValueError):run.artifact(p,tmp_path)
    items=run.inventory([p],tmp_path,allow_empty=True)
    assert items=={'empty_init.py':{'path':'empty_init.py','bytes':0,'sha256':'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}}


@pytest.mark.parametrize('phase',['idle_before_sql','inside_first_copy','after_first_copy','inside_after_snapshot','cancel_failed'])
def test_idle_cancellation_permanently_blocks_all_later_sql_and_copy_blocks(run,tmp_path,monkeypatch,phase):
    c=core.workload();tables=c['tables'];reqs=run.requests(c);copies=[];statements=[];cancelled=[];threads=[];monitoring=[False]
    scalar={p['id']:0 if p['conditions'] else core.EXPECTED_ROWS[p['table']] for p in c['predicates']}
    class Event:
        def __init__(self):self.stopped=False
        def wait(self,timeout):return self.stopped
        def is_set(self):return self.stopped
        def set(self):self.stopped=True
    class Thread:
        def __init__(self,target,**kwargs):self.target=target;threads.append(self)
        def inject(self):
            monitoring[0]=True
            try:self.target()
            finally:monitoring[0]=False
        def start(self):
            if phase in ('idle_before_sql','cancel_failed'):self.inject()
        def join(self,**kwargs):pass
        def is_alive(self):return False
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql,parameters=None):
            statements.append(sql);self.result=[]
            if sql.startswith('SELECT current_database'):
                self.result=[('deepdb_job','110005','127.0.0.1',55432,str(tmp_path/'data/postgresql/cluster'),456,'on','repeatable read','synthetic')]
            elif sql.startswith('SELECT c.oid'):
                i=tables.index(parameters[0])+1;self.result=[(i,'r',i,False)]
            elif sql.startswith('SELECT attname'):self.result=[(n,23) for n in sorted(core.COLUMNS[tables[parameters[0]-1]])]
            elif sql.startswith('SELECT a.attname'):self.result=[('id',True,True)]
            else:
                for req in reqs:
                    if req['sql']==sql:
                        if req['kind']=='scalar_aggregate':
                            n=core.EXPECTED_ROWS[req['table']];self.result=[tuple([n,n,0]+[scalar[k] for k in req['predicate_ids']])]
                        else:self.result=[(0,0)]
                        break
        def fetchone(self):return self.result[0]
        def fetchall(self):return self.result
        def copy_expert(self,sql,sink):
            copies.append(sink);sink.write(b'first-block')
            if (phase in ('inside_first_copy','after_first_copy') and len(copies)==1) or (phase=='inside_after_snapshot' and len(copies)==7):
                threads[0].inject()
            if phase!='after_first_copy':sink.write(b'following-block')
    class Connection:
        closed=False;rolled_back=False
        def set_session(self,**kw):pass
        def cursor(self):return Cursor()
        def cancel(self):
            cancelled.append(True)
            if phase=='cancel_failed':raise RuntimeError('synthetic cancellation failure')
        def rollback(self):self.rolled_back=True
        def close(self):self.closed=True
    connection=Connection()
    monkeypatch.setattr(run.threading,'Event',Event);monkeypatch.setattr(run.threading,'Thread',Thread)
    monkeypatch.setattr(run,'connect',lambda:connection)
    monkeypatch.setattr(run,'resources',lambda root:dict(available_memory_bytes=0 if monitoring[0] else 6*1024**3,process_rss_bytes=1024**2,free_disk_bytes=20*1024**3))
    monkeypatch.setattr(run,'backend_image',lambda pid:str(tmp_path/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe'))
    with pytest.raises(ValueError):run.collect(dict(contract=c,source_boundary='fixture'),tmp_path)
    assert cancelled and connection.closed and connection.rolled_back
    if phase in ('idle_before_sql','cancel_failed'):
        assert copies==[] and statements==[]
    else:
        assert len(copies)==(7 if phase=='inside_after_snapshot' else 1)
        assert copies[-1].record()['bytes']==len(b'first-block')


def test_external_dependency_and_native_loader_are_the_same_fixed_system_file(run,tmp_path,monkeypatch):
    outside=tmp_path/'outside.dll';outside.write_bytes(b'not the native loader DLL');root=tmp_path/'project';root.mkdir()
    with pytest.raises(ValueError):run.artifact(outside,root)
    calls=[]
    monkeypatch.setenv('SystemRoot',str(tmp_path/'injected'))
    monkeypatch.setattr(run.ctypes,'WinDLL',lambda path,**kw:calls.append((str(Path(path).resolve()),kw)) or 'native-loader-fixture')
    assert run.native_kernel()=='native-loader-fixture'
    assert calls==[(str(Path('C:/Windows/System32/kernel32.dll').resolve()),{'use_last_error':True})]


@pytest.mark.parametrize('failure',['still_alive','join_raises'])
def test_monitor_finalization_failure_closes_connection_and_taints_namespace(run,tmp_path,monkeypatch,failure):
    class Thread:
        def __init__(self,**kw):pass
        def start(self):pass
        def join(self,**kw):
            if failure=='join_raises':raise RuntimeError('synthetic monitor join failure')
        def is_alive(self):return True
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,*a):pass
        def fetchone(self):
            return ('deepdb_job','110005','127.0.0.1',55432,str(tmp_path/'data/postgresql/cluster'),456,'on','repeatable read','synthetic')
    class Connection:
        closed=False;rolled_back=False
        def set_session(self,**kw):pass
        def cursor(self):return Cursor()
        def rollback(self):self.rolled_back=True
        def close(self):self.closed=True
    connection=Connection();plan=dict(binding='f'*64,contract=dict(tables=[]),source_boundary='fixture')
    p=tmp_path/'plan.json';a=tmp_path/'approval.json';p.write_text(json.dumps(plan));a.write_text('{}')
    monkeypatch.setattr(run.threading,'Thread',Thread)
    monkeypatch.setattr(run,'validate_plan',lambda *_:None);monkeypatch.setattr(run,'validate_approval',lambda *_:None)
    monkeypatch.setattr(run,'connect',lambda:connection);monkeypatch.setattr(run,'requests',lambda _:[])
    monkeypatch.setattr(core,'validate_counts',lambda *a:None)
    monkeypatch.setattr(run,'resources',lambda _:dict(available_memory_bytes=6*1024**3,process_rss_bytes=1024**2,free_disk_bytes=20*1024**3))
    monkeypatch.setattr(run,'backend_image',lambda _:str(tmp_path/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe'))
    with pytest.raises((ValueError,RuntimeError)):run.execute(p,a,root=tmp_path)
    d=tmp_path/'output/full/scalar_oracle/runs'/('f'*20)
    assert connection.closed and connection.rolled_back
    assert run.read(d/'lifecycle.json')['status']=='TAINTED'
    assert not (d/'final_seal.json').exists() and not (d/'counts.json').exists()
