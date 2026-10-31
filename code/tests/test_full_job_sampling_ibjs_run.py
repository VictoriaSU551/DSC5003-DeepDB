"""New SQL bridge mocks only; never starts/connects to PostgreSQL."""
import importlib.util
from pathlib import Path
import pytest
from fractions import Fraction
import copy
import full_job_sampling_ibjs as core
import full_job_sampling_run as srsrun
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_job_sampling_ibjs_run.py';assert p.exists(),'IBJS SQL driver missing'
    s=importlib.util.spec_from_file_location('ibjs_run_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_plan_approval_and_namespace_are_independent_and_exact(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.audit,'dependencies',lambda *a:{'fixture':True})
    p=m.build_plan('synthetic',tmp_path);path=tmp_path/'plan.json';m.atomic(path,p)
    assert p['scope']['live_driver_implemented'] is True and p['pure_scope']['live_driver_implemented'] is False
    a=m.approval_template(p,path,tmp_path)
    with pytest.raises(ValueError):m.audit.approval(a,p,path,tmp_path)
    a.update(status='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_IBJS_RUN',root_review_reference='SYNTHETIC ONLY')
    m.audit.approval(a,p,path,tmp_path)
    a['exclusive_window']=False
    with pytest.raises(ValueError):m.audit.approval(a,p,path,tmp_path)


def test_probe_sql_is_one_new_base_and_positions_null_casts_and_predicates_are_bound():
    m=module();q=m.audit.parse_query('SELECT COUNT(*) FROM title t,cast_info c WHERE t.id=c.movie_id AND c.role_id=1;',0)
    for kind,values in [('count',[(0,None),(1,3)]),('kth',[(0,None,0),(1,3,2)])]:
        sql,p=m.probe_statement(kind,'cast_info',values,q,['id','movie_id','role_id'])
        assert sql.count('public."cast_info"')==1 and 'public."title"' not in sql
        assert '::bigint' in sql and 'ORDER BY v.i' in sql and p[-1]==1 and None in p
        assert not any(s in sql for s in ('CREATE ','INSERT ','UPDATE ','DELETE '))
        if kind=='kth':assert 'LATERAL' in sql and 'OFFSET v.o LIMIT 1' in sql and 'ORDER BY a."id"' in sql


def test_index_receipt_requires_exact_six_pk_five_valid_movie_id_indexes():
    m=module();rows=[]
    for t in m.audit.POPULATION:
        rows.append([t,t+'_pkey',True,True,True,True,True,True,'btree','id',1])
        if t!='title':rows.append([t,t+'_movie_id_idx',False,False,True,True,True,True,'btree','movie_id',1])
    m.audit.validate_indexes(rows)
    for bad in ('missing','invalid','partial','expression','wrong_key','extra'):
        copy=[list(x) for x in rows]
        if bad=='missing':copy.pop()
        elif bad=='extra':copy.append(list(copy[0]))
        else:copy[0][{'invalid':4,'partial':6,'expression':7,'wrong_key':9}[bad]]=False if bad!='wrong_key' else 'movie_id'
        with pytest.raises(ValueError):m.audit.validate_indexes(copy)


def test_output_cap_stops_instead_of_dropping_a_trace(tmp_path):
    m=module();sink=m.OutputBudget(tmp_path,cap=64,per_query=32)
    with pytest.raises(ValueError):m.atomic(tmp_path/'query.json',{'payload':'x'*80},sink=sink,query=True)
    assert not (tmp_path/'query.json').exists()


class ToyMonitor:
    active=None
    def check(self):pass


class ToyCursor:
    def __init__(self,q,contract,population):self.q=q;self.contract=contract;self.population=population;self.result=[];self.sql=[]
    def execute(self,sql,params=None):
        self.sql.append((sql,params));self.result=[]
        if sql.startswith('SET ') or 'SAVEPOINT' in sql:return
        t=next(t for t in self.population if 'public."'+t+'"' in sql);cols=sorted(self.population[t][0])
        if sql.startswith('SELECT '):
            self.result=[[r[c] for c in cols] for r in self.population[t] if r['id'] in params[0]];return
        kth='LATERAL' in sql;arity=3 if kth else 2
        pred=next(p['conditions'] for p in self.q['predicates'] if p['table']==t)
        n=(len(params)-len(pred))//arity
        for i in range(n):
            request=params[i*arity:(i+1)*arity];key=request[1];field='id' if t=='title' else 'movie_id'
            matching=sorted([r for r in self.population[t] if key is not None and r[field]==key and core.accepts(self.q,t,r)],key=lambda r:r['id'])
            if kth:
                if request[2]<len(matching):self.result.append([i]+[matching[request[2]][c] for c in cols])
            else:self.result.append([i,len(matching)])
    def fetchall(self):return self.result


def toy():
    q=core.parse_query('SELECT COUNT(*) FROM title t,cast_info c,movie_keyword k WHERE t.id=c.movie_id AND t.id=k.movie_id AND c.role_id=1;',0)
    contract={'predicates':q['predicates']}
    rows={'title':[dict(id=1),dict(id=3)],'cast_info':[dict(id=1,movie_id=1,role_id=1),dict(id=3,movie_id=1,role_id=1),dict(id=4,movie_id=None,role_id=1)],
          'movie_keyword':[dict(id=2,movie_id=1),dict(id=4,movie_id=3)]}
    metadata={t:dict(rows=len(r),distinct_ids=len(r),min_id=min(x['id'] for x in r),max_id=max(x['id'] for x in r)) for t,r in rows.items()}
    return q,contract,rows,metadata


def test_thin_enumeration_matches_frozen_kernel_and_records_all_rank_draws():
    m=module();q,contract,population,meta=toy();srs=core.frozen_srs();bases={}
    for t,rows in population.items():
        cols=sorted(rows[0]);raw=dict(table=t,complete=True,rows=[[r[c] for c in cols] for r in rows],projection=cols,population=meta[t],selected_ids=[r['id'] for r in rows])
        bases[t]=core.base_state(q,t,raw)
    class Probe:
        def count_many(self,bags,t,q):return [sum((r['id'] if t=='title' else r['movie_id'])==(next(iter(b.values()))['movie_id'] if t=='title' else b['title']['id']) and core.accepts(q,t,r) for r in population[t]) for b in bags]
        def kth_many(self,requests,t,q):
            return [sorted([r for r in population[t] if (r['id'] if t=='title' else r['movie_id'])==(next(iter(b.values()))['movie_id'] if t=='title' else b['title']['id']) and core.accepts(q,t,r)],key=lambda x:x['id'])[k] for b,k in requests]
    expected=core.estimate_query(q,bases,Probe(),{},n=1000);trace={}
    actual=m.enumerate_states(core,q,bases,Probe(),trace)
    assert {k:v.fingerprint() for k,v in actual['states'].items()}=={k:v.fingerprint() for k,v in expected['states'].items()}
    assert actual['prediction']==Fraction(2) and actual['budget_spent']==expected['budget_spent']
    assert all(len(a['rng_draws'])==len(a['ranks']) for a in trace['attempts'])


def test_live_query_toy_holes_duplicates_null_and_independent_replay():
    m=module();q,contract,population,meta=toy();cursor=ToyCursor(q,contract,population)
    leaf=m.run_query(q,meta,contract,cursor,ToyMonitor(),'binding',helpers=(core,srsrun))
    assert leaf['status']=='COMPLETE' and leaf['raw_prediction']=={'numerator':'2','denominator':'1'}
    assert leaf['charged_logical_lookups']>0 and leaf['sql_roundtrips']==len(cursor.sql)
    assert m.audit.validate_query(leaf,q,meta,contract,'binding',leaf['client_pid'])['raw_prediction']==leaf['raw_prediction']
    for mutate in ('rank','cost','output','ids','sql','scope','truth'):
        bad=copy.deepcopy(leaf)
        if mutate=='rank':next(a for a in bad['algorithm']['attempts'] if a['ranks'])['ranks'][0]+=1
        if mutate=='cost':bad['charged_logical_lookups']+=1
        if mutate=='output':next(a for a in bad['algorithm']['attempts'] if a.get('output_rows'))['output_rows'][0]['title']['id']+=1
        if mutate=='ids':bad['table_samples']['title']['raw_sample']['batches'][0]['attempted_ids'][0]+=1
        if mutate=='sql':bad['operations'][1]['sql']='SELECT 1'
        if mutate=='scope':bad['scope']['author_reproduction_complete']=True
        if mutate=='truth':bad['truth']=2
        with pytest.raises(ValueError):m.audit.validate_query(bad,q,meta,contract,'binding',leaf['client_pid'])


def test_real_zero_sql_expired_terminal_is_null_and_auditable():
    m=module();q,contract,population,meta=toy()
    class Clock:
        n=0
        def __call__(self):self.n+=1;return 0. if self.n==1 else 31.
    cursor=ToyCursor(q,contract,population);leaf=m.run_query(q,meta,contract,cursor,ToyMonitor(),'b',clock=Clock(),helpers=(core,srsrun))
    assert leaf['operations']==[] and leaf['table_samples']=={} and leaf['raw_prediction'] is None and leaf['status']=='QUERY_WALL_BUDGET'
    m.audit.validate_query(leaf,q,meta,contract,'b',leaf['client_pid'])


@pytest.mark.parametrize('damage',[None,'cidr','missing_index','projection_change'])
def test_collector_real_rr_locks_catalog_twelve_copy_online_limit_and_owned_close(tmp_path,monkeypatch,damage):
    m=module();contract=m.audit.workload();events=[];copies=[];cursor=None
    import full_scalar_oracle_run as scalar
    class Cursor:
        timeout=None
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql,params=None):
            events.append(('sql',sql));self.sql=sql
            if sql.startswith('SET LOCAL statement_timeout = '):self.timeout=int(sql.split(' = ')[1])
        def fetchone(self):
            if self.sql.startswith('SELECT current_database()'):
                return ('deepdb_job','110005','127.0.0.1/32' if damage=='cidr' else '127.0.0.1',55432,str(tmp_path/'data/postgresql/cluster'),17,'on','repeatable read','start')
            t=self.sql.split('FROM public."')[1].split('"')[0];n=m.audit.POPULATION[t];return(n,n,1,n)
        def fetchall(self):
            rows=[]
            for t in contract['tables']:
                rows.append([t,t+'_pkey',True,True,True,True,True,True,'btree','id',1])
                if t!='title':rows.append([t,t+'_movie_id_idx',False,False,True,True,True,True,'btree','movie_id',1])
            return rows[:-1] if damage=='missing_index' else rows
        def copy_expert(self,sql,sink):copies.append(sql);sink.write(sql.encode()+ (b'changed' if damage=='projection_change' and len(copies)>6 else b''))
    class Connection:
        rolled=closed=False
        def set_session(self,**kw):events.append(('session',kw))
        def cursor(self):
            nonlocal cursor
            cursor=Cursor();return cursor
        def rollback(self):self.rolled=True
        def close(self):self.closed=True
        def cancel(self):pytest.fail('No resource cancellation expected')
    conn=Connection()
    class Helper:
        HashSink=scalar.HashSink;GuardedCursor=scalar.GuardedCursor
        resources=staticmethod(lambda r:dict(available_memory_bytes=6*1024**3,process_rss_bytes=1024,free_disk_bytes=20*1024**3))
        validate_resources=staticmethod(scalar.validate_resources)
        connect=staticmethod(lambda:conn)
        backend_image=staticmethod(lambda pid:str((tmp_path/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve()))
        copy_statement=staticmethod(scalar.copy_statement)
        @staticmethod
        def schema_record(c,contract,t):return dict(table=t,columns=[[c,23] for c in m.audit.projection(contract,t)])
    monkeypatch.setattr(m,'_helpers',lambda:(core,srsrun,Helper()))
    def query(q,*args,**kwargs):
        assert cursor.timeout==5000;return dict(query_no=q['query_no'])
    monkeypatch.setattr(m,'run_query',query);(tmp_path/'queries').mkdir();monitor=srsrun.LiveMonitor(Helper(),None,tmp_path)
    monitor.poll()
    try:
        if damage:
            with pytest.raises(ValueError):m.collect(dict(contract=contract,binding='b',source_boundary='fixture'),tmp_path,monitor,tmp_path)
        else:
            receipt=m.collect(dict(contract=contract,binding='b',source_boundary='fixture'),tmp_path,monitor,tmp_path)
            assert len(copies)==12 and len(receipt['common_operations'])==19
            assert len(list((tmp_path/'queries').glob('*.json')))==140
            assert events[0]==('session',dict(isolation_level='REPEATABLE READ',readonly=True,autocommit=False))
            assert events[2][1].startswith('LOCK TABLE ') and 'IN SHARE MODE NOWAIT' in events[2][1]
            assert [x[1] for x in events if x[0]=='sql' and x[1].startswith('SET LOCAL statement_timeout')] == ['SET LOCAL statement_timeout = 600000','SET LOCAL statement_timeout = 5000','SET LOCAL statement_timeout = 600000']
        assert conn.rolled and conn.closed and monitor.connection is None
    finally:monitor.finish()


def test_execute_never_adopts_prior_namespace_and_never_deletes_foreign_lock(tmp_path,monkeypatch):
    m=module();p={'binding':'a'*64};path=tmp_path/'p.json';m.atomic(path,p)
    d=tmp_path/m.BASE/'runs'/('a'*20);d.mkdir(parents=True);m.atomic(d/'lifecycle.json',{'status':'TAINTED'})
    monkeypatch.setattr(m,'_helpers',lambda:pytest.fail('Prior namespace must reject before imports/connections'))
    with pytest.raises(ValueError,match='Prior attempts'):m.execute(path,path,tmp_path)
    assert m.read(d/'lifecycle.json')=={'status':'TAINTED'}
    lock=tmp_path/'lock';lock.write_bytes(b'foreign')
    with pytest.raises(FileExistsError):
        with srsrun.exclusive(lock):pytest.fail('Foreign lock entered')
    assert lock.read_bytes()==b'foreign'


def test_original_monitor_permanent_stop_cancels_only_owned_connection(tmp_path):
    class Connection:
        calls=0
        def cancel(self):self.calls+=1
    conn=Connection()
    class Helper:
        def resources(self,root):return {}
        def validate_resources(self,r):raise ValueError('synthetic low memory')
    monitor=srsrun.LiveMonitor(Helper(),conn,tmp_path)
    assert monitor.poll() is False and conn.calls==1
    with pytest.raises(ValueError):monitor.check()
    monitor.connection=None
    assert monitor.poll() is False and conn.calls==1


def weighted_toy():
    q,contract,rows,metadata=toy()
    rows['cast_info']=[dict(id=i,movie_id=1 if i%2 else 3,role_id=1) for i in range(1,1101)]
    rows['movie_keyword']=[dict(id=1,movie_id=1),dict(id=2,movie_id=3),dict(id=3,movie_id=3),dict(id=4,movie_id=3)]
    metadata={t:dict(rows=len(r),distinct_ids=len(r),min_id=min(x['id'] for x in r),max_id=max(x['id'] for x in r)) for t,r in rows.items()}
    return q,contract,rows,metadata


def test_weighted_global_wor_nonuniform_fanout_and_overwrites_replay():
    m=module();q,c,rows,metadata=weighted_toy();leaf=m.run_query(q,metadata,c,ToyCursor(q,c,rows),ToyMonitor(),'w',helpers=(core,srsrun))
    assert leaf['status']=='COMPLETE'
    expansion=next(a for a in leaf['algorithm']['attempts'] if sum(a['fanouts'])>1000)
    assert len(expansion['ranks'])==len(set(expansion['ranks']))==1000
    assert any(a['replaces_existing'] for a in leaf['algorithm']['attempts'])
    assert m.audit.validate_query(leaf,q,metadata,c,'w',leaf['client_pid'])['raw_prediction']==leaf['raw_prediction']


@pytest.mark.parametrize('failure',['sql','rank_deadline'])
def test_partial_dispatch_or_rank_failure_stays_null_and_replays_costs(failure):
    m=module();q,c,rows,metadata=weighted_toy()
    class Clock:
        armed=False;i=0
        def __call__(self):
            if self.armed:self.i+=1
            return 31. if self.i>=10 else 0.
    clock=Clock()
    class Cursor(ToyCursor):
        def execute(self,sql,params=None):
            if '(SELECT COUNT(*)' in sql:
                if failure=='sql':
                    class Timeout(Exception):pgcode='57014'
                    raise Timeout('synthetic statement timeout')
                clock.armed=True
            return super().execute(sql,params)
    leaf=m.run_query(q,metadata,c,Cursor(q,c,rows),ToyMonitor(),'f',clock=clock,helpers=(core,srsrun))
    assert leaf['raw_prediction'] is None and leaf['charged_logical_lookups']>0 and leaf['cleanup_sql_roundtrips']==3
    if failure=='rank_deadline':assert any(a['rng_draws'] and not a['ranks'] for a in leaf['algorithm']['attempts'])
    m.audit.validate_query(leaf,q,metadata,c,'f',leaf['client_pid'])


def test_whole_controller_mock_70_complete_zero_final_seal_and_no_adoption(monkeypatch):
    import tempfile
    import full_scalar_oracle_run as scalar
    m=module();parent=ROOT/'output/tmp';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ibc',dir=str(parent)) as home:
        root=Path(home);monkeypatch.setattr(m.audit,'dependencies',lambda *a:{'fixture':'NO_REAL_DB_NO_SCIENCE'})
        p=m.build_plan('controller_fixture',root);contract=p['contract'];events=[];connections=[]
        class Cursor:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def execute(self,sql,params=None):self.sql=sql;self.params=params;events.append(sql)
            def fetchone(self):
                if self.sql.startswith('SELECT current_database()'):return ('deepdb_job','110005','127.0.0.1',55432,str(root/'data/postgresql/cluster'),17,'on','repeatable read','fixture')
                t=self.sql.split('FROM public."')[1].split('"')[0];n=m.audit.POPULATION[t];return(n,n,1,n)
            def fetchall(self):
                if self.sql==m.audit.INDEX_SQL:
                    return [[t,t+'_pkey',True,True,True,True,True,True,'btree','id',1] for t in contract['tables']]+[[t,t+'_movie_id_idx',False,False,True,True,True,True,'btree','movie_id',1] for t in contract['tables'] if t!='title']
                if self.sql.startswith('SELECT '):
                    t=self.sql.split('FROM public."')[1].split('"')[0];cols=m.audit.projection(contract,t)
                    return [[identity if c=='id' else None if c=='movie_id' else 1 for c in cols] for identity in self.params[0]]
                n=self.sql.count('(%s::integer,%s::bigint)');assert n>0 and 'COUNT(*)' in self.sql
                return [[i,0] for i in range(n)]
            def copy_expert(self,sql,sink):sink.write(sql.encode())
        class Connection:
            closed=rolled=False
            def set_session(self,**kw):assert kw==dict(isolation_level='REPEATABLE READ',readonly=True,autocommit=False)
            def cursor(self):return Cursor()
            def rollback(self):self.rolled=True
            def close(self):self.closed=True
            def cancel(self):pytest.fail('Unexpected fixture cancellation')
        class Helper:
            HashSink=scalar.HashSink;GuardedCursor=scalar.GuardedCursor;copy_statement=staticmethod(scalar.copy_statement)
            resources=staticmethod(lambda r:dict(available_memory_bytes=6*1024**3,process_rss_bytes=1024,free_disk_bytes=20*1024**3))
            validate_resources=staticmethod(scalar.validate_resources)
            backend_image=staticmethod(lambda pid:str((root/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve()))
            @staticmethod
            def connect():c=Connection();connections.append(c);return c
            @staticmethod
            def schema_record(cursor,c,t):return dict(table=t,oid=1,relfilenode=1,relkind='r',inherits=False,columns=[[x,23] for x in m.audit.projection(c,t)],primary_key=['id'],valid_primary_key=True)
        monkeypatch.setattr(m,'_helpers',lambda:(core,srsrun,Helper()))
        path=root/m.BASE/'plans/p.json';path.parent.mkdir(parents=True);m.atomic(path,p)
        a=m.approval_template(p,path,root);a.update(status='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_IBJS_RUN',root_review_reference='SYNTHETIC ONLY')
        approval=path.with_name('a.json');m.atomic(approval,a)
        value=m.execute(path,approval,root);d=root/m.BASE/'runs'/p['binding'][:20]
        result=m.audit.verify(d,root)
        assert value==result['verification'] and value['completed_queries']==value['raw_zero_queries']==70
        assert value['complete_finite_70_query_summary_allowed'] is False and len(result['artifacts'])==148
        assert len(connections)==1 and connections[0].rolled and connections[0].closed
        before={str(f):m.digest(f) for f in d.rglob('*') if f.is_file()}
        with pytest.raises(ValueError,match='Prior attempts'):m.execute(path,approval,root)
        assert before=={str(f):m.digest(f) for f in d.rglob('*') if f.is_file()}


def test_offline_same_entity_cannot_change_query_column_across_different_states():
    m=module();q,c,rows,metadata=toy()
    q=core.parse_query(q['sql'].rstrip(';')+' AND t.production_year>0;',0);c={'predicates':q['predicates']}
    for row in rows['title']:row['production_year']=10
    class Cursor(ToyCursor):
        def fetchall(self):
            result=super().fetchall()
            if 'LATERAL' in self.sql[-1][0] and 'public."title"' in self.sql[-1][0]:
                for row in result:row[-1]=11 # still passes >0, but contradicts the same sampled IDs
            return result
    leaf=m.run_query(q,metadata,c,Cursor(q,c,rows),ToyMonitor(),'e',helpers=(core,srsrun))
    assert leaf['status']=='COMPLETE'
    with pytest.raises(ValueError,match='entity'):m.audit.validate_query(leaf,q,metadata,c,'e',leaf['client_pid'])


def test_taint_persists_even_if_original_lifecycle_atomic_was_interrupted(tmp_path):
    m=module();path=tmp_path/'lifecycle.json'
    def interrupted():raise ValueError('synthetic interruption')
    with pytest.raises(ValueError):m.atomic(path,{'status':'RUNNING'},check=interrupted)
    assert path.with_name('lifecycle.json.tmp').exists()
    m.taint(tmp_path,'b',ValueError('synthetic interruption'))
    assert m.read(path)['status']=='TAINTED' and path.with_name('lifecycle.json.tmp').exists()
