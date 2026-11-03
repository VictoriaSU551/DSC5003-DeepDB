"""Stdlib-only independent trace audit; no DB/engine/scientific imports."""
import builtins
import importlib.util
from pathlib import Path
import pytest
import copy
import os
import tempfile
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_job_sampling_ibjs_audit.py';assert p.exists(),'IBJS independent auditor missing'
    s=importlib.util.spec_from_file_location('ibjs_audit_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_auditor_missing_run_imports_no_engines_controller_or_pg_and_writes_nothing(tmp_path,monkeypatch):
    original=builtins.__import__
    def guard(name,*a,**k):
        assert name not in {'psycopg2','full_job_sampling','full_job_sampling_ibjs','full_job_sampling_run','full_scalar_oracle_run'} and not name.startswith('ensemble_compilation')
        return original(name,*a,**k)
    monkeypatch.setattr(builtins,'__import__',guard);m=module()
    with pytest.raises((ValueError,OSError)):m.verify(tmp_path,root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_independent_parser_and_catalog_contract_are_exact():
    m=module();w=m.workload();assert len(w['queries'])==70
    assert m.SCOPE['live_driver_implemented'] is True and m.PURE_SCOPE['live_driver_implemented'] is False
    assert len(m.expected_files())==148 # plan/approval/collection/prediction/monitor/execution/verification/lifecycle +140 leaves


@pytest.fixture
def bundle(monkeypatch):
    import full_job_sampling_ibjs_run as run
    import full_job_sampling_ibjs as core
    import full_job_sampling_run as srsrun
    from test_full_job_sampling_ibjs_run import ToyMonitor
    m=module();parent=ROOT/'output/tmp';parent.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix='iba',dir=str(parent)) as home:
        root=Path(home);monkeypatch.setattr(m,'dependencies',lambda *a:{'fixture':True})
        p=m.make_plan('synthetic',{'fixture':True},root);directory=root/m.BASE/'runs'/p['binding'][:20];(directory/'queries').mkdir(parents=True)
        path=root/m.BASE/'plans/fixture.json';path.parent.mkdir();run.atomic(path,p)
        a=run.approval_template(p,path,root);a.update(status='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_IBJS_RUN',root_review_reference='PURE SYNTHETIC ONLY')
        run.atomic(directory/'plan.json',p);run.atomic(directory/'approval.json',a)
        metadata={t:dict(rows=n,distinct_ids=n,min_id=1,max_id=n) for t,n in m.POPULATION.items()};pred=[]
        for q in p['contract']['queries']:
            class Clock:
                i=0
                def __call__(self):self.i+=1;return 0. if self.i==1 else 31.
            leaf=run.run_query(q,metadata,p['contract'],None,ToyMonitor(),p['binding'],clock=Clock(),helpers=(core,srsrun))
            f=directory/'queries'/('query_%02d.json'%q['query_no']);run.atomic(f,leaf)
            run.atomic(f.with_suffix('.seal.json'),dict(binding=p['binding'],query_no=q['query_no'],artifact=m.artifact(f,root)));pred.append(m.prediction_row(leaf))
        snapshots={t:dict(schema=dict(table=t,oid=i+1,relkind='r',relfilenode=i+1,inherits=False,columns=[[c,23] for c in m.projection(p['contract'],t)],primary_key=['id'],valid_primary_key=True),
            projection=m.projection(p['contract'],t),binary_copy=dict(bytes=100,sha256='a'*64),seconds=0.) for i,t in enumerate(p['contract']['tables'])}
        indexes=[]
        for t in p['contract']['tables']:
            indexes.append([t,t+'_pkey',True,True,True,True,True,True,'btree','id',1])
            if t!='title':indexes.append([t,t+'_movie_id_idx',False,False,True,True,True,True,'btree','movie_id',1])
        identity=dict(database='deepdb_job',server_version_num='110005',address='127.0.0.1',port=55432,data_directory=str(root/'data/postgresql/cluster'),backend_pid=17,read_only='on',isolation='repeatable read',postmaster_start='fixture',image=str(root/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe'))
        setup=['SET LOCAL lock_timeout = 5000','LOCK TABLE '+', '.join('public."'+t+'"' for t in p['contract']['tables'])+' IN SHARE MODE NOWAIT',
            'SET LOCAL search_path = pg_catalog, public',"SET LOCAL work_mem = '16MB'","SET LOCAL temp_file_limit = '1GB'",'SET LOCAL statement_timeout = 600000',
            'SET LOCAL max_parallel_workers_per_gather = 0',"SET LOCAL application_name = 'deepdb_local_job70_ibjs'",m._srs_namespace()['IDENTITY_SQL']]
        ops=[dict(sql=s,parameters=None,seconds=0.,response=None) for s in setup]
        ops[8]['response']=[identity[k] for k in ('database','server_version_num','address','port','data_directory','backend_pid','read_only','isolation','postmaster_start')]
        ops.append(dict(sql=m.INDEX_SQL,parameters=[p['contract']['tables']],response=indexes,seconds=0.))
        ops.extend(dict(sql=m.population_sql(t),parameters=None,response=[metadata[t][k] for k in ('rows','distinct_ids','min_id','max_id')],seconds=0.) for t in p['contract']['tables'])
        ops.extend(dict(sql=s,parameters=None,response=None,seconds=0.) for s in ('SET LOCAL statement_timeout = 5000','SET LOCAL statement_timeout = 600000'))
        ops.append(copy.deepcopy(ops[9]));pid=os.getpid()
        r=dict(binding=p['binding'],scope=m.SCOPE,source_boundary=p['source_boundary'],client_pid=pid,database_identity=identity,before=snapshots,after=copy.deepcopy(snapshots),indexes_before=indexes,indexes_after=copy.deepcopy(indexes),metadata=metadata,common_operations=ops,
            timings=dict(before_projection_seconds=0.,live_population_metadata_seconds=0.,all_online_queries_and_leaf_checkpoint_seconds=2170.,after_projection_seconds=0.),seconds=2171.,
            server_started_or_stopped=False,new_model_calls=0,raw_csv_or_truth_read=False,scalar_predicate_counts_used=False,owned_connection_rolled_back_and_closed=True,cancelled_queries=[])
        resources=dict(available_memory_bytes=6*1024**3,process_rss_bytes=1024,free_disk_bytes=20*1024**3)
        monitor=dict(binding=p['binding'],client_pid=pid,startup_resources=resources,resources=[dict(resources,seconds=0.),dict(resources,seconds=2171.)],errors=[],cancelled_queries=[],stopped=True,started_before_physical_preflight=True,seconds=2171.)
        execution=dict(binding=p['binding'],client_pid=pid,admission_physical_validation_seconds=0.,collection_and_checkpoint_seconds=2171.,fresh_postflight_physical_validation_seconds=0.,offline_math_prepublication_validation_seconds=0.,measured_client_wall_seconds_before_final_records=2171.,
            final_record_and_seal_io_in_external_command_wall_only=True,root_external_command_wall_required_for_end_to_end_latency=True)
        for name,value in [('collection',r),('predictions',dict(binding=p['binding'],scope=m.SCOPE,queries=pred)),('monitor',monitor),('execution',execution),('lifecycle',dict(status='RUNNING',binding=p['binding'],client_pid=pid))]:run.atomic(directory/(name+'.json'),value)
        v=m.validate_bundle(directory,root,publishing=True);run.atomic(directory/'verification.json',v)
        run.atomic(directory/'lifecycle.json',dict(status='PASS',binding=p['binding'],client_pid=pid,verification_sha256=m.digest(directory/'verification.json')))
        def reseal():
            files={n:m.artifact(directory/n,root) for n in m.expected_files()};body=dict(schema='job70-ibjs-final-v1',binding=p['binding'],files=files);run.atomic(directory/'final_seal.json',dict(body,self_sha256=m.value_hash(body)))
        reseal();yield m,run,root,directory,reseal


def test_all70_null_receipts_offline_no_engine_db_write_or_launch(bundle,monkeypatch):
    m,run,root,d,seal=bundle;before={str(p):m.digest(p) for p in root.rglob('*') if p.is_file()};original=builtins.__import__
    def guard(name,*a,**k):
        assert name not in {'psycopg2','full_job_sampling_ibjs','full_job_sampling_run','full_scalar_oracle_run','full_job_sampling','full_job_sampling_ibjs_run'}
        return original(name,*a,**k)
    monkeypatch.setattr(builtins,'__import__',guard)
    import subprocess
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:pytest.fail('No audit launch'))
    monkeypatch.setattr(Path,'write_text',lambda *a,**k:pytest.fail('No audit write'))
    result=m.verify(d,root)
    assert result['status']=='PASS_READ_ONLY_LOCAL_JOB70_IBJS_WITH_GAPS'
    assert result['verification']['queries']==result['verification']['incomplete_queries']==70 and result['verification']['completed_queries']==0
    assert result['verification']['complete_finite_70_query_summary_allowed'] is False
    assert result['verification']['common_sql_roundtrips']==67
    assert {str(p):m.digest(p) for p in root.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('damage',['missing_leaf','projection','index','cidr','no_online_limit','old_prep','invent_zero','source_subset','trace_subset','monitor','pid'])
def test_resealed_whole_attempt_tamper_rejected(bundle,damage):
    m,run,root,d,seal=bundle
    if damage=='missing_leaf':(d/'queries/query_69.json').unlink()
    elif damage in {'projection','index','cidr','no_online_limit','old_prep'}:
        r=m.read(d/'collection.json')
        if damage=='projection':r['after']['title']['binary_copy']['sha256']='b'*64
        if damage=='index':r['indexes_after'][0][4]=False
        if damage=='cidr':r['database_identity']['address']='127.0.0.1/32'
        if damage=='no_online_limit':r['common_operations'].pop(16)
        if damage=='old_prep':r['common_operations'][5]['sql']='SET LOCAL statement_timeout = 120000'
        run.atomic(d/'collection.json',r)
    elif damage in {'invent_zero','trace_subset','pid'}:
        path=d/'queries/query_00.json';q=m.read(path)
        if damage=='invent_zero':q['raw_prediction']={'numerator':'0','denominator':'1'}
        if damage=='trace_subset':q.pop('algorithm')
        if damage=='pid':q['client_pid']+=1
        run.atomic(path,q);run.atomic(path.with_suffix('.seal.json'),dict(binding=q['binding'],query_no=0,artifact=m.artifact(path,root)))
    elif damage=='source_subset':
        p=m.read(d/'plan.json');p['dependencies']={};run.atomic(d/'plan.json',p)
    else:
        p=m.read(d/'monitor.json');p['stopped']=False;run.atomic(d/'monitor.json',p)
    if damage=='missing_leaf':
        with pytest.raises((OSError,ValueError)):m.verify(d,root)
    else:
        seal()
        with pytest.raises(ValueError):m.verify(d,root)
