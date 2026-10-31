"""Sampling controller mocks; never an actual database or projection scan."""
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_job_sampling_run.py';assert p.exists(),'sampling driver missing'
    s=importlib.util.spec_from_file_location('job_sampling_run_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_sampling_plan_requires_exact_root_approval_and_exclusive_window(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'dependencies',lambda *a:{'pure':'fixture'})
    p=m.build_plan(attempt='synthetic',root=tmp_path);f=tmp_path/'plan.json';m.atomic(f,p)
    a=m.approval_template(p,f,tmp_path)
    with pytest.raises(ValueError):m.validate_approval(a,p,f,tmp_path)
    a.update(status='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_SRS_RUN',root_review_reference='synthetic review only')
    m.validate_approval(a,p,f,tmp_path)
    a['exclusive_window']=False
    with pytest.raises(ValueError):m.validate_approval(a,p,f,tmp_path)


def test_unconditional_population_metadata_never_uses_scalar_or_predicate_counts():
    m=module()
    for t in m.core.EXPECTED_ROWS:
        sql=m.population_sql(t)
        assert 'COUNT(*)' in sql and 'COUNT(DISTINCT "id")' in sql and 'MIN("id")' in sql and 'MAX("id")' in sql
        assert 'WHERE' not in sql and 'JOIN' not in sql and 'FILTER' not in sql


def test_preexisting_or_tainted_attempt_cannot_rerun_or_adopt(tmp_path,monkeypatch):
    m=module();p={'binding':'b'*64};f=tmp_path/'plan.json';a=tmp_path/'approval.json';m.atomic(f,p);m.atomic(a,{})
    monkeypatch.setattr(m,'validate_plan',lambda *a:None);monkeypatch.setattr(m,'validate_approval',lambda *a:None)
    d=tmp_path/m.BASE/'runs'/('b'*20);d.mkdir(parents=True);m.atomic(d/'lifecycle.json',{'status':'TAINTED'})
    monkeypatch.setattr(m,'collect',lambda *a:pytest.fail('No science from prior failed attempts'))
    with pytest.raises(ValueError):m.execute(f,a,tmp_path)
    assert m.read(d/'lifecycle.json')=={'status':'TAINTED'}


def test_existing_shared_exclusive_lock_is_never_deleted_by_second_controller(tmp_path):
    m=module();lock=tmp_path/'controller.lock';lock.write_bytes(b'other owner')
    with pytest.raises((ValueError,FileExistsError)):
        with m.exclusive(lock):pytest.fail('Must not enter')
    assert lock.read_bytes()==b'other owner'


class FakeMonitor:
    active=None
    def check(self):pass


class FakeCursor:
    def __init__(self,m,query,contract,metadata):
        self.m=m;self.query=query;self.contract=contract;self.metadata=metadata;self.lookups={};self.executed=[]
    def execute(self,sql,parameters=None):
        self.executed.append((sql,parameters));self.response=None
        if sql.startswith('SELECT ') and 'WHERE "id" = ANY' in sql:
            t=sql.split('FROM public."')[1].split('"')[0];columns=self.m.core.projection(self.contract,t)
            ids=parameters[0];rows=[]
            for key in ids:
                # Odd IDs exist; even candidates demonstrate hole rejection.
                if self.metadata[t].get('toy_holes') and key%2==0:continue
                row=[key if c=='id' else (3 if c=='movie_id' else 1) for c in columns];rows.append(row)
            self.lookups.setdefault(t,[]).extend(rows);self.response=rows
        elif sql.startswith('WITH '):
            import full_job_sampling_audit as audit
            samples={t:dict(projection=self.m.core.projection(self.contract,t),rows=self.lookups[t]) for t in self.query['tables']}
            self.response=[audit.independent_sample_count(self.query,samples)]
    def fetchall(self):return [tuple(r) for r in self.response]
    def fetchone(self):return tuple(self.response)


def toy(m):
    q=m.core.parse_query('SELECT COUNT(*) FROM title t,cast_info c WHERE t.id=c.movie_id AND t.kind_id=1 AND c.role_id=1;',0)
    c=m.core.pinned_module('full_scalar_oracle').contract_from_queries([q])
    meta={t:dict(rows=3,distinct_ids=3,min_id=1,max_id=5,toy_holes=True) for t in q['tables']}
    return q,c,meta


def test_real_run_query_receipts_independently_recompute_from_unfiltered_id_lookups():
    m=module();q,c,pop=toy(m);cursor=FakeCursor(m,q,c,pop)
    r=m.run_query(q,pop,c,cursor,FakeMonitor(),'b'*64)
    import full_job_sampling_audit as audit
    assert r['status']=='COMPLETE' and r['raw_prediction']=={'numerator':'3','denominator':'1'}
    audit.validate_query(r,q,pop,c,'b'*64,r['client_pid'])
    assert r['id_attempts']['title']>3 and r['sql_roundtrips']==len(cursor.executed)


def test_resource_monitor_failure_is_permanent_and_cancels_only_owned_connection(tmp_path):
    m=module()
    class H:
        def resources(self,root):return {}
        def validate_resources(self,r):raise ValueError('resource stop')
    class C:
        cancelled=0
        def cancel(self):self.cancelled+=1
    c=C();mon=m.LiveMonitor(H(),c,tmp_path)
    assert mon.poll() is False and c.cancelled==1
    with pytest.raises(ValueError):mon.check()
    with pytest.raises(ValueError):m.QueryIO(object(),mon,m.core.Budget(),[]).one('x','SELECT 1')
    # The postflight guard has no live DB connection and must invent no target.
    post=m.LiveMonitor(H(),None,tmp_path)
    assert post.poll() is False and len(post.errors)==1 and c.cancelled==1


def test_query_sql_error_is_null_and_cleanup_preserves_transaction():
    m=module();q,c,pop=toy(m)
    class Bad(FakeCursor):
        def execute(self,sql,parameters=None):
            super().execute(sql,parameters)
            if sql.startswith('SELECT '):raise RuntimeError('synthetic SQL error')
    cursor=Bad(m,q,c,pop);r=m.run_query(q,pop,c,cursor,FakeMonitor(),'b'*64)
    assert r['status']=='QUERY_ERROR' and r['raw_prediction'] is None
    assert [x[0] for x in cursor.executed[-3:]]==['ROLLBACK TO SAVEPOINT sampling_query','SET LOCAL statement_timeout = 5000','RELEASE SAVEPOINT sampling_query']
    import full_job_sampling_audit as audit
    audit.validate_query(r,q,pop,c,'b'*64,r['client_pid'])


def test_statement_timeout_is_explicit_null_separate_from_thirty_second_wall():
    m=module();q,c,pop=toy(m)
    class Timeout(Exception):pgcode='57014'
    class Bad(FakeCursor):
        def execute(self,sql,parameters=None):
            super().execute(sql,parameters)
            if sql.startswith('SELECT '):raise Timeout('synthetic 5s statement timeout')
    row=m.run_query(q,pop,c,Bad(m,q,c,pop),FakeMonitor(),'b'*64)
    assert row['status']=='STATEMENT_TIMEOUT' and row['raw_prediction'] is None and row['sqlstate']=='57014'


def test_deadline_before_first_rng_attempt_is_null_and_auditable():
    m=module();q,c,pop=toy(m)
    class Clock:
        n=0
        def __call__(self):self.n+=1;return 0. if self.n<6 else 31.
    r=m.run_query(q,pop,c,FakeCursor(m,q,c,pop),FakeMonitor(),'b'*64,clock=Clock())
    assert r['status']=='QUERY_WALL_BUDGET' and r['raw_prediction'] is None
    import full_job_sampling_audit as audit
    audit.validate_query(r,q,pop,c,'b'*64,r['client_pid'])


@pytest.mark.parametrize('damage',[None,'early','wrong_status','fake_zero','sample','attempt','cleanup','error_type','sqlstate'])
def test_pre_savepoint_deadline_true_zero_sql_terminal_only(damage):
    m=module();q,c,pop=toy(m)
    class Clock:
        first=True
        def __call__(self):
            if self.first:self.first=False;return 0.
            return 31.
    cursor=FakeCursor(m,q,c,pop);r=m.run_query(q,pop,c,cursor,FakeMonitor(),'b'*64,clock=Clock())
    assert cursor.executed==[] and r['operations']==[] and r['table_samples']=={} and r['id_attempts']=={}
    assert r['status']=='QUERY_WALL_BUDGET' and r['raw_prediction'] is None and r['wall_seconds']==31.
    if damage=='early':r['wall_seconds']=29.
    if damage=='wrong_status':r['status']='QUERY_ERROR'
    if damage=='fake_zero':r['raw_prediction']={'numerator':'0','denominator':'1'}
    if damage=='sample':r['table_samples']={'title':{}}
    if damage=='attempt':r['id_attempts']={'title':0}
    if damage=='cleanup':r['cleanup_sql_roundtrips']=1
    if damage=='error_type':r['error_type']='RuntimeError'
    if damage=='sqlstate':r['sqlstate']='57014'
    import full_job_sampling_audit as audit
    if damage is None:audit.validate_query(r,q,pop,c,'b'*64,r['client_pid'])
    else:
        with pytest.raises(ValueError):audit.validate_query(r,q,pop,c,'b'*64,r['client_pid'])


def test_last_fraction_construction_cannot_publish_late_point(monkeypatch):
    m=module();q,c,pop=toy(m);now=[0.];original=m.core.rational
    def delayed(value):now[0]=31.;return original(value)
    monkeypatch.setattr(m.core,'rational',delayed)
    r=m.run_query(q,pop,c,FakeCursor(m,q,c,pop),FakeMonitor(),'b'*64,clock=lambda:now[0])
    assert r['status']=='QUERY_WALL_BUDGET' and r['sample_cardinality'] is None and r['raw_prediction'] is None


@pytest.mark.parametrize('force_cidr',[False,True])
def test_collect_readonly_locks_precede_select_and_twelve_full_projection_passes(tmp_path,monkeypatch,force_cidr):
    m=module();contract=m.core.workload();events=[];copies=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql,params=None):
            events.append(('sql',sql));self.sql=sql
            if sql.startswith('SET LOCAL statement_timeout = '):self.timeout=int(sql.split(' = ')[1])
        def fetchone(self):
            if self.sql.startswith('SELECT current_database()'):
                assert self.sql==m.core.IDENTITY_SQL # driver must use the shared pinned SQL
                address='127.0.0.1/32' if force_cidr or 'host(inet_server_addr())' not in self.sql else '127.0.0.1'
                return ('deepdb_job','110005',address,55432,str(tmp_path/'data/postgresql/cluster'),17,'on','repeatable read','start')
            t=self.sql.split('FROM public."')[1].split('"')[0];n=m.core.EXPECTED_ROWS[t];return(n,n,1,n)
        def copy_expert(self,sql,sink):copies.append(sql);sink.write(sql.encode())
    class Connection:
        rolled=closed=False
        def set_session(self,**kw):events.append(('session',kw))
        def cursor(self):return Cursor()
        def cancel(self):pytest.fail('No monitor failure in happy fixture')
        def rollback(self):self.rolled=True
        def close(self):self.closed=True
    connection=Connection()
    class Sink:
        def __init__(self,*a):self.b=b''
        def write(self,b):self.b+=b
        def record(self):return dict(bytes=len(self.b),sha256=__import__('hashlib').sha256(self.b).hexdigest())
    class Helper:
        HashSink=Sink
        def GuardedCursor(self,cursor,check):return cursor
        def resources(self,root):return dict(available_memory_bytes=6*m.core.GIB,process_rss_bytes=1024,free_disk_bytes=20*m.core.GIB)
        def validate_resources(self,*a,**k):pass
        def connect(self):return connection
        def backend_image(self,pid):return str((tmp_path/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve())
        def schema_record(self,cursor,c,t):return dict(columns=[[x,23] for x in m.core.projection(c,t)])
        def copy_statement(self,c,t):return 'COPY '+t
    monkeypatch.setattr(m.core,'pinned_module',lambda name:Helper())
    def initial_savepoint(q,metadata,contract,cursor,*args):
        cursor.execute('SAVEPOINT sampling_query')
        assert cursor.timeout==5000 # actual inherited limit at first query control SQL
        cursor.execute('RELEASE SAVEPOINT sampling_query')
        return dict(query_no=q['query_no'])
    monkeypatch.setattr(m,'run_query',initial_savepoint)
    (tmp_path/'queries').mkdir()
    if force_cidr:
        with pytest.raises(ValueError,match='Unexpected database/RR/read-only identity'):
            m.collect(dict(contract=contract,binding='b'*64,source_boundary='fixture'),tmp_path,tmp_path)
        assert copies==[] and list((tmp_path/'queries').iterdir())==[] and connection.rolled and connection.closed
        return
    r=m.collect(dict(contract=contract,binding='b'*64,source_boundary='fixture'),tmp_path,tmp_path)
    assert events[0]==('session',dict(isolation_level='REPEATABLE READ',readonly=True,autocommit=False))
    assert events[2][1].startswith('LOCK TABLE ') and 'IN SHARE MODE NOWAIT' in events[2][1]
    assert len(copies)==12 and len(r['metadata'])==6 and len(list((tmp_path/'queries').glob('*.json')))==140
    assert not any('FILTER' in e[1] for e in events if e[0]=='sql')
    assert [e[1] for e in events if e[0]=='sql' and e[1].startswith('SET LOCAL statement_timeout')] == ['SET LOCAL statement_timeout = 600000','SET LOCAL statement_timeout = 5000','SET LOCAL statement_timeout = 600000']
    assert m.core.POLICY['preparation_statement_timeout_ms']==600000
    assert m.core.CONFIG['statement_timeout_ms']==5000 and m.core.CONFIG['max_query_seconds']==30.
    assert r['resource_monitor_stopped'] and r['owned_connection_rolled_back_and_closed'] and connection.rolled and connection.closed


def test_identity_sql_and_reviewed_scalar_v4_pins_are_exact():
    import ast
    m=module()
    assert 'host(inet_server_addr())' in m.core.IDENTITY_SQL and 'inet_server_addr()::text' not in m.core.IDENTITY_SQL
    assert m.core.PINS['code/full_scalar_oracle_run.py']=='d5d31f3460d84942a2f22a0874f0c73bfcbbecb45a048a2ab78be76496ee9e26'
    assert m.core.PINS['docs/FULL_SCALAR_ORACLE_PROTOCOL.md']=='1f02d7b591197f8cf4bd318199acb0173741887f149c4f5c80c02647058797fa'
    nodes=ast.walk(ast.parse((ROOT/'code/full_job_sampling_run.py').read_text()))
    shared=[n for n in nodes if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='execute'
            and n.args and isinstance(n.args[0],ast.Attribute) and isinstance(n.args[0].value,ast.Name)
            and n.args[0].value.id=='core' and n.args[0].attr=='IDENTITY_SQL']
    assert len(shared)==1
