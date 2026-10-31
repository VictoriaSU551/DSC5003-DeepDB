"""Independent math, RNG/trace and offline source/seal acceptance."""
import importlib.util
from pathlib import Path
from fractions import Fraction
import builtins
import copy
import tempfile
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_job_sampling_audit.py';assert p.exists(),'strict offline auditor missing'
    s=importlib.util.spec_from_file_location('job_sampling_audit_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_auditor_import_and_missing_run_never_import_database_or_science(tmp_path,monkeypatch):
    original=builtins.__import__
    def guard(name,*a,**k):
        assert name not in ('psycopg2','full_scalar_oracle_run','full_job_sampling_run') and not name.startswith('ensemble_compilation')
        return original(name,*a,**k)
    monkeypatch.setattr(builtins,'__import__',guard);m=module()
    with pytest.raises((ValueError,OSError)):m.verify(tmp_path,root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_independent_sample_join_preserves_null_strict_year_and_duplicate_fk():
    m=module();q=m.core.parse_query('SELECT COUNT(*) FROM title t,cast_info c,movie_keyword k WHERE t.id=c.movie_id AND t.id=k.movie_id AND t.production_year>2005 AND c.role_id=1;',0)
    sample={'title':{'projection':['id','production_year'],'rows':[[1,2005],[2,2006],[3,None]]},
        'cast_info':{'projection':['id','movie_id','role_id'],'rows':[[1,2,1],[2,2,1],[3,3,1],[4,None,1]]},
        'movie_keyword':{'projection':['id','movie_id'],'rows':[[1,2],[2,2],[3,1]]}}
    assert m.independent_sample_count(q,sample)==4
    value=m.independent_estimate(4,{'title':10,'cast_info':40,'movie_keyword':30},{'title':3,'cast_info':4,'movie_keyword':3})
    assert value==Fraction(4000,3)


@pytest.fixture(scope='module')
def bundle():
    """Entire synthetic 70-query publication; no database/runtime verifier."""
    import full_job_sampling_run as run
    from test_full_job_sampling_run import FakeCursor,FakeMonitor
    m=module();parent=ROOT/'output/tmp';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sa',dir=str(parent)) as temp:
        root=Path(temp);p=m.core.make_plan('synthetic',{'fixture':True},root)
        d=root/m.core.BASE/'runs'/p['binding'][:20];(d/'queries').mkdir(parents=True)
        original=root/'plans/plan.json';original.parent.mkdir();run.atomic(original,p)
        a=run.approval_template(p,original,root);a.update(status='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_SRS_RUN',root_review_reference='SYNTHETIC ONLY')
        run.atomic(d/'plan.json',p);run.atomic(d/'approval.json',a)
        metadata={t:dict(rows=N,distinct_ids=N,min_id=1,max_id=N) for t,N in m.core.EXPECTED_ROWS.items()}
        rows=[]
        for q in p['contract']['queries']:
            r=run.run_query(q,metadata,p['contract'],FakeCursor(run,q,p['contract'],metadata),FakeMonitor(),p['binding']);rows.append(r)
            f=d/'queries'/('query_%02d.json'%q['query_no']);run.atomic(f,r)
            run.atomic(f.with_suffix('.seal.json'),dict(binding=p['binding'],query_no=q['query_no'],artifact=m.artifact(f,root)))
        pid=rows[0]['client_pid'];snapshot={}
        for t in m.core.EXPECTED_ROWS:
            columns=m.core.projection(p['contract'],t)
            snapshot[t]=dict(schema=dict(table=t,oid=1,relkind='r',relfilenode=1,inherits=False,columns=[[x,23] for x in columns],primary_key=['id'],valid_primary_key=True),
                             projection=columns,binary_copy=dict(bytes=100,sha256='a'*64),seconds=0.)
        setup=['SET LOCAL lock_timeout = 5000','LOCK TABLE '+', '.join('public."'+t+'"' for t in p['contract']['tables'])+' IN SHARE MODE NOWAIT',
               'SET LOCAL search_path = pg_catalog, public',"SET LOCAL work_mem = '16MB'","SET LOCAL temp_file_limit = '1GB'",'SET LOCAL statement_timeout = 600000',
               'SET LOCAL max_parallel_workers_per_gather = 0',"SET LOCAL application_name = 'deepdb_local_job70_srs'",m.core.IDENTITY_SQL]
        ops=[dict(sql=x,parameters=None,response=None,seconds=0.) for x in setup]
        for t in p['contract']['tables']:
            s=metadata[t];ops.append(dict(sql=m.core.population_sql(t),parameters=None,response=[s['rows'],s['distinct_ids'],s['min_id'],s['max_id']],seconds=0.))
        ops.append(dict(sql='SET LOCAL statement_timeout = 5000',parameters=None,response=None,seconds=0.))
        ops.append(dict(sql='SET LOCAL statement_timeout = 600000',parameters=None,response=None,seconds=0.))
        resources=dict(available_memory_bytes=6*m.core.GIB,process_rss_bytes=1024,free_disk_bytes=20*m.core.GIB)
        r=dict(binding=p['binding'],scope=dict(m.core.SCOPE),source_boundary=p['source_boundary'],client_pid=pid,
            database_identity=dict(database='deepdb_job',server_version_num='110005',address='127.0.0.1',port=55432,
                data_directory=str(root/'data/postgresql/cluster'),image=str(root/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe'),backend_pid=17,read_only='on',isolation='repeatable read',postmaster_start='fixture'),
            before=snapshot,after=copy.deepcopy(snapshot),metadata=metadata,common_operations=ops,
            startup_resources=resources,resources=[dict(resources,seconds=0.)],resource_monitor_stopped=True,
            owned_connection_rolled_back_and_closed=True,resource_monitor_errors=[],server_started_or_stopped=False,new_model_calls=0,
            raw_csv_or_truth_read=False,scalar_predicate_counts_used=False,cancelled_queries=[],seconds=20.,
            timings=dict(before_projection_seconds=0.,live_population_metadata_seconds=0.,after_projection_seconds=0.,all_online_queries_and_leaf_checkpoint_seconds=10.))
        ops[8]['response']=[r['database_identity'][k] for k in ('database','server_version_num','address','port','data_directory','backend_pid','read_only','isolation','postmaster_start')]
        run.atomic(d/'collection.json',r);run.atomic(d/'predictions.json',dict(binding=p['binding'],scope=dict(m.core.SCOPE),queries=[m.prediction_row(q) for q in rows]))
        run.atomic(d/'execution.json',dict(binding=p['binding'],client_pid=pid,admission_physical_validation_seconds=0.,collection_and_checkpoint_seconds=20.,
            fresh_postflight_physical_validation_seconds=0.,offline_math_prepublication_validation_seconds=0.,measured_client_wall_seconds_before_final_records=20.,
            postflight_resources=[dict(resources,seconds=0.)],postflight_resource_errors=[],postflight_resource_monitor_stopped=True,
            final_record_and_seal_io_in_external_command_wall_only=True,root_external_command_wall_required_for_end_to_end_latency=True))
        run.atomic(d/'lifecycle.json',dict(status='RUNNING',binding=p['binding'],client_pid=pid))
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(m.core,'dependencies',lambda *a:{'fixture':True})
            v=m.validate_bundle(d,root,prepublication=True);run.atomic(d/'verification.json',v)
            run.atomic(d/'lifecycle.json',dict(status='PASS',binding=p['binding'],client_pid=pid,verification_sha256=m.core.digest(d/'verification.json')))
            body=dict(schema='job70-srs-final-v1',binding=p['binding'],files={n:m.artifact(d/n,root) for n in m.FILES})
            run.atomic(d/'final_seal.json',dict(body,self_sha256=m.core.object_hash(body)))
            yield m,run,root,d


def test_full70_public_offline_audit_launch_db_and_writes_forbidden(bundle,monkeypatch):
    m,run,root,d=bundle;before={str(p):m.core.digest(p) for p in root.rglob('*') if p.is_file()}
    original=builtins.__import__
    def guard(name,*a,**kw):
        assert name not in ('psycopg2','full_scalar_oracle_run','full_job_sampling_run') and not name.startswith('ensemble_compilation')
        return original(name,*a,**kw)
    monkeypatch.setattr(builtins,'__import__',guard)
    monkeypatch.setattr(Path,'write_bytes',lambda *a,**kw:pytest.fail('No offline write'))
    monkeypatch.setattr(Path,'write_text',lambda *a,**kw:pytest.fail('No offline write'))
    import subprocess
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:pytest.fail('No offline process'))
    result=m.verify(d,root)
    assert result['status']=='PASS_READ_ONLY_LOCAL_JOB70_SRS' and result['verification']['queries']==70
    assert len(result['predictions']['queries'])==70 and result['verification']['raw_zero_queries']>0
    assert result['verification']['complete_finite_70_query_summary_allowed'] is False
    assert result['verification']['common_sql_roundtrips']==65
    assert result['verification']['common_sql_roundtrips_breakdown']==dict(recorded_setup_identity_metadata_reset=17,schema_checks=36,streaming_copy=12)
    assert {str(p):m.core.digest(p) for p in root.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('damage',['cidr_address','legacy_inet_text','old_preparation_timeout','old_reset_timeout','old64_missing_online_limit'])
def test_historical_identity_audit_rejects_cidr_and_legacy_inet_sql(bundle,damage):
    m,run,root,d=bundle;r=copy.deepcopy(m.read(d/'collection.json'))
    if damage=='cidr_address':r['database_identity']['address']='127.0.0.1/32'
    elif damage=='legacy_inet_text':r['common_operations'][8]['sql']=m.core.IDENTITY_SQL.replace('host(inet_server_addr())','inet_server_addr()::text')
    elif damage=='old64_missing_online_limit':del r['common_operations'][15]
    else:r['common_operations'][5 if damage=='old_preparation_timeout' else 16]['sql']='SET LOCAL statement_timeout = 120000'
    with pytest.raises(ValueError,match='identity|first SELECT|SQL set|roundtrip set'):m.validate_collection(m.read(d/'plan.json'),r,root)


@pytest.mark.parametrize('mutation,match',[
    ('rng','RNG/ID'),('response','exact base SQL'),('fraction','Fraction'),('zero','join count/zero'),
    ('projection','projection'),('pid','PID'),('sql','identity'),('missing_table','Incomplete sample|coverage|table prefix|RNG attempt'),
])
def test_self_resealed_query_tamper_rejected(bundle,mutation,match):
    m,run,root,d=bundle;f=d/'queries/query_00.json';s=f.with_suffix('.seal.json');seal=d/'final_seal.json'
    originals={p:p.read_bytes() for p in (f,s,seal)};q=m.read(f);t=next(iter(q['table_samples']));sample=q['table_samples'][t]
    if mutation=='rng':sample['batches'][0]['attempted_ids'][0]+=1
    if mutation=='response':q['operations'][sample['batches'][0]['operation_index']]['response'][0][0]+=1
    if mutation=='fraction':q['raw_prediction']['numerator']='1'
    if mutation=='zero':q['status']='COMPLETE' if q['status']=='COMPLETE_ZERO' else 'COMPLETE_ZERO'
    if mutation=='projection':sample['projection']=list(reversed(sample['projection']))
    if mutation=='pid':q['client_pid']+=1
    if mutation=='sql':q['sql']=q['sql'].replace('COUNT(*)','COUNT(1)')
    if mutation=='missing_table':del q['table_samples'][t]
    try:
        run.atomic(f,q);run.atomic(s,dict(binding=q['binding'],query_no=0,artifact=m.artifact(f,root)))
        body={k:v for k,v in m.read(seal).items() if k!='self_sha256'}
        for p in (f,s):body['files'][p.relative_to(d).as_posix()]=m.artifact(p,root)
        run.atomic(seal,dict(body,self_sha256=m.core.object_hash(body)))
        with pytest.raises(ValueError,match=match):m.verify(d,root)
    finally:
        for p,b in originals.items():p.write_bytes(b)


def test_self_resealed_subset_and_after_projection_mismatch_rejected(bundle):
    m,run,root,d=bundle;seal=d/'final_seal.json';saved=seal.read_bytes();body={k:v for k,v in m.read(seal).items() if k!='self_sha256'}
    del body['files']['queries/query_69.json']
    try:
        run.atomic(seal,dict(body,self_sha256=m.core.object_hash(body)))
        with pytest.raises(ValueError,match='required artifacts'):m.verify(d,root)
    finally:seal.write_bytes(saved)
    collection=m.read(d/'collection.json');collection['after']['title']['binary_copy']['sha256']='b'*64
    with pytest.raises(ValueError,match='projection changed'):m.validate_collection(m.read(d/'plan.json'),collection,root)


@pytest.mark.parametrize('failure_kind',['sql_error','pre_savepoint_deadline'])
def test_null_terminal_retained_and_full70_denominator_not_silently_dropped(bundle,failure_kind):
    m,run,root,d=bundle
    from test_full_job_sampling_run import FakeCursor,FakeMonitor
    names=['queries/query_00.json','queries/query_00.seal.json','predictions.json','verification.json','lifecycle.json','final_seal.json','collection.json','execution.json']
    saved={n:(d/n).read_bytes() for n in names};p=m.read(d/'plan.json');q=p['contract']['queries'][0];r=m.read(d/'collection.json')
    class Bad(FakeCursor):
        def execute(self,sql,parameters=None):
            super().execute(sql,parameters)
            if sql.startswith('SELECT '):raise RuntimeError('SYNTHETIC failure')
    class Clock:
        first=True
        def __call__(self):
            if self.first:self.first=False;return 0.
            return 31.
    try:
        if failure_kind=='pre_savepoint_deadline':
            cursor=FakeCursor(run,q,p['contract'],r['metadata'])
            row=run.run_query(q,r['metadata'],p['contract'],cursor,FakeMonitor(),p['binding'],clock=Clock())
            assert cursor.executed==[] and row['operations']==[] and row['table_samples']=={} and row['id_attempts']=={}
            assert row['wall_seconds']==31. and row['status']=='QUERY_WALL_BUDGET'
        else:row=run.run_query(q,r['metadata'],p['contract'],Bad(run,q,p['contract'],r['metadata']),FakeMonitor(),p['binding'])
        path=d/'queries/query_00.json';run.atomic(path,row)
        run.atomic(path.with_suffix('.seal.json'),dict(binding=p['binding'],query_no=0,artifact=m.artifact(path,root)))
        predictions=m.read(d/'predictions.json');predictions['queries'][0]=m.prediction_row(row);run.atomic(d/'predictions.json',predictions)
        r['timings']['all_online_queries_and_leaf_checkpoint_seconds']=max(10.,sum(x['wall_seconds'] for x in predictions['queries'])+1.)
        r['seconds']=sum(r['timings'].values())+1.;run.atomic(d/'collection.json',r)
        execution=m.read(d/'execution.json');execution['collection_and_checkpoint_seconds']=r['seconds'];execution['measured_client_wall_seconds_before_final_records']=r['seconds']+1.
        run.atomic(d/'execution.json',execution)
        run.atomic(d/'lifecycle.json',dict(status='RUNNING',binding=p['binding'],client_pid=r['client_pid']))
        v=m.validate_bundle(d,root,prepublication=True);run.atomic(d/'verification.json',v)
        run.atomic(d/'lifecycle.json',dict(status='PASS',binding=p['binding'],client_pid=r['client_pid'],verification_sha256=m.core.digest(d/'verification.json')))
        body=dict(schema='job70-srs-final-v1',binding=p['binding'],files={n:m.artifact(d/n,root) for n in m.FILES})
        run.atomic(d/'final_seal.json',dict(body,self_sha256=m.core.object_hash(body)))
        accepted=m.verify(d,root)
        assert accepted['status']=='PASS_READ_ONLY_LOCAL_JOB70_SRS_WITH_GAPS'
        assert accepted['verification']['queries']==70 and accepted['verification']['incomplete_queries']==1
        assert accepted['predictions']['queries'][0]['raw_prediction'] is None
        predictions['queries'].pop(0);run.atomic(d/'predictions.json',predictions)
        with pytest.raises(ValueError,match='omit/change'):m.validate_bundle(d,root)
    finally:
        for n,b in saved.items():(d/n).write_bytes(b)
