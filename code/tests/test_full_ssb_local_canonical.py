"""Pure canonical evaluation-only contracts; no actual parent/scientific calls."""
import contextlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_ssb_local_canonical.py';assert p.exists(),'canonical provider missing'
    s=importlib.util.spec_from_file_location('canonical_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_distinct_scope_budget_and_historical_boundary():
    m=module();assert m.SCOPE=='LOCAL_SSB_SF500_CANONICAL_CI'
    assert m.PHASES==('FORWARD','REVERSE') and m.HASH_SEEDS=={'FORWARD':0,'REVERSE':173}
    assert m.RANDOM_SEED==74031 and (m.RTOL,m.ATOL)==(1e-9,1e-5)
    assert m.RESERVE_BYTES==512*2**20 and m.PARENT_RESULT_SHA=='da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82'


def test_actual_frozen_sql_identity_reader_has_all13_without_science():
    m=module();sqls,names=m.sql_identities();assert len(sqls)==13 and names[0]=='S1.1' and names[-1]=='S4.3'


def test_missing_publication_is_readonly_without_parent_call(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'collect_parent',lambda *a:pytest.fail('missing publication must not consume parent'))
    with pytest.raises((ValueError,OSError)):m.verify_canonical(tmp_path)
    assert not list(tmp_path.iterdir())


def test_fixed_parent_pin_fails_before_actual_parent_verifier(monkeypatch):
    m=module();monkeypatch.setattr(m,'native_platform',lambda:contextlib.nullcontext({}))
    monkeypatch.setattr(m,'digest',lambda *a:'changed')
    monkeypatch.setattr(m.previous,'verify_local_formal',lambda *a:pytest.fail('untrusted parent code imported/called'))
    with pytest.raises(ValueError,match='pin|source|changed'):m.collect_parent()


@pytest.mark.parametrize('damage',[None,'changed','alias','subset'])
def test_private_parent_refresh_rehashes_complete_physical_closure_without_recalling_formal(tmp_path,monkeypatch,damage):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    for name in ('model','raw','runtime'):(tmp_path/name).write_bytes(name.encode())
    records=[m.artifact(tmp_path/n,tmp_path) for n in ('model','raw','runtime')]
    parent={'artifacts':records,'published_result':records[0],'closure_sha256':m.value_hash(records)}
    if damage=='changed':(tmp_path/'raw').write_bytes(b'changed')
    elif damage=='alias':parent['published_result']=dict(records[0],path='raw')
    elif damage=='subset':parent['artifacts']=records[:-1]
    monkeypatch.setattr(m.previous,'verify_local_formal',lambda *a:pytest.fail('private same-stack refresh must not recursively call F'))
    if damage is None:assert m.refresh_parent(parent,tmp_path)==records
    else:
        with pytest.raises(ValueError):m.refresh_parent(parent,tmp_path)


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
@pytest.mark.parametrize('damage',[None,'loads','calls','order','hash','scope'])
def test_phase_identity_and_actual_evaluator_accounting(phase,damage):
    m=module();r=dict(scope=m.SCOPE,phase=phase,execution_order=list(range(13)) if phase=='FORWARD' else list(reversed(range(13))),
        actual_model_loads=1 if phase=='FORWARD' else 13,actual_evaluator_calls=26,evaluator_modes=[False,True]*13,
        environment=dict(PYTHONHASHSEED=str(m.HASH_SEEDS[phase]),random_seed=m.RANDOM_SEED,numpy_seed=m.RANDOM_SEED,thread_limits={n:'1' for n in m.THREADS}),
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False)
    if damage=='loads':r['actual_model_loads']=2
    elif damage=='calls':r['actual_evaluator_calls']=25
    elif damage=='order':r['execution_order']=[0]*13
    elif damage=='hash':r['environment']['PYTHONHASHSEED']='99'
    elif damage=='scope':r['scope']='LOCAL_SSB_SF500'
    if damage is None:m.validate_execution(r)
    else:
        with pytest.raises(ValueError):m.validate_execution(r)


def test_instrumentation_counts_actual_calls_and_restores_after_exception():
    m=module()
    class E:
        def evaluate_query(self,*a,**kw):return 'same'
    mod=SimpleNamespace(SPNEnsemble=E,read_ensemble=lambda *a,**k:E());old=(mod.read_ensemble,E.evaluate_query)
    with pytest.raises(RuntimeError):
        with m.observe_evaluation(mod) as count:
            e=mod.read_ensemble('fake');assert e.evaluate_query(None,confidence_intervals=False)=='same'
            assert count=={'loads':1,'modes':[False]};raise RuntimeError('synthetic')
    assert (mod.read_ensemble,E.evaluate_query)==old


@pytest.mark.parametrize('damage',[None,'missing','extra','sql','binding','body'])
def test_complete_phase_bundle_refuses_resealed_identity_or_subset(tmp_path,damage):
    m=module();directory=tmp_path/'q';binding={'adapter':'fixed'};sqls=['select '+str(i) for i in range(13)];names=['S'+str(i) for i in range(13)]
    for i,(sql,name) in enumerate(zip(sqls,names)):
        path=directory/('query_%02d.json'%i);m.atomic(path,dict(query_no=i,query_name=name,sql=sql))
        m.atomic(path.with_suffix('.seal.json'),{'binding':binding,'sha256':m.digest(path)})
    if damage=='missing':(directory/'query_12.seal.json').unlink()
    elif damage=='extra':m.atomic(directory/'query_99.json',{})
    elif damage in ('sql','body'):
        path=directory/'query_01.json';q=m.read(path);q['sql' if damage=='sql' else 'query_no']='changed';m.atomic(path,q)
        m.atomic(path.with_suffix('.seal.json'),{'binding':binding,'sha256':m.digest(path)})
    elif damage=='binding':binding={'adapter':'changed'}
    if damage is None:assert len(m.query_artifacts(directory,binding,sqls,names,tmp_path))==26
    else:
        with pytest.raises(ValueError):m.query_artifacts(directory,binding,sqls,names,tmp_path)


@pytest.mark.parametrize('damage',[None,'missing','point','truth','reference'])
def test_forward_preserves_old_point_and_exact_truth_reference_while_ci_can_change(damage):
    import copy
    m=module();old=dict(query_no=0,query_name='S1.1',sql='select1',truth_groups=1,model_groups=1,missing_model_groups=0,extra_model_groups=0,reference_ci_eligible_groups=1,groups=[dict(key=[],prediction=100.,model_interval=[90.,110.],truth=101,status='MATCHED',sample_moments={'sum':30},reference_ci={'eligible':True},released_ci_comparison={})])
    new=copy.deepcopy(old);new['groups'][0]['model_interval']=[95.,105.]
    if damage=='missing':new['groups']=[]
    elif damage=='point':new['groups'][0]['prediction']=200.
    elif damage=='truth':new['groups'][0]['truth']=99
    elif damage=='reference':new['groups'][0]['reference_ci']={}
    if damage is None:assert m.compare_forward_query(old,new)['point_values_compared']==1
    else:
        with pytest.raises(ValueError):m.compare_forward_query(old,new)


def test_reverse_coverage_uses_validated_forward_truth_scope_not_raw_executor_shape():
    m=module();raw=[dict(query_no=0,groups=[dict(key=[],prediction=1.,model_interval=[0.,2.])])]
    assert m.phase_coverage('REVERSE',raw,{'coverage':{'actual_truth_groups':2059}})=={'actual_truth_groups':2059}
    with pytest.raises(ValueError):m.phase_coverage('REVERSE',raw)


@pytest.mark.parametrize('field',['truth_groups','model_groups','missing_model_groups','extra_model_groups','reference_ci_eligible_groups'])
def test_forward_rejects_coverage_counter_changes_despite_identical_group_rows(field):
    import copy
    m=module();old=dict(query_no=0,query_name='S1.1',sql='select1',groups=[],truth_groups=0,model_groups=0,missing_model_groups=0,extra_model_groups=0,reference_ci_eligible_groups=0)
    new=copy.deepcopy(old);new[field]=999
    with pytest.raises(ValueError,match='coverage|count'):m.compare_forward_query(old,new)


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
@pytest.mark.parametrize('changed',[False,True])
def test_actual_worker_controller_one_fresh_parent_and_post_physical_change_taints_only_new_phase(tmp_path_factory,monkeypatch,phase,changed):
    import types
    m=module();root=tmp_path_factory.mktemp('w');monkeypatch.setattr(m,'ROOT',root)
    for n in m.THREADS:monkeypatch.setenv(n,'1')
    for n,v in {'DEEPDB_SSB_CANONICAL_WORKER':'1','DEEPDB_SSB_CANONICAL_PHASE':phase,'PYTHONHASHSEED':str(m.HASH_SEEDS[phase])}.items():monkeypatch.setenv(n,v)
    raw=root/'parent';raw.write_bytes(b'accepted');d=m.artifact(raw,root);parent=dict(artifacts=[d],published_result=d,closure_sha256=m.value_hash([d]))
    p={'parent':{'same':'proof'},'dependencies':{}};calls=[]
    monkeypatch.setattr(m,'native_platform',lambda:contextlib.nullcontext({}));monkeypatch.setattr(m,'dependency_snapshot',lambda:{})
    monkeypatch.setattr(m,'collect_parent',lambda:calls.append('F') or parent);monkeypatch.setattr(m,'parent_snapshot',lambda *a:p['parent'])
    original=m.refresh_parent;monkeypatch.setattr(m,'refresh_parent',lambda a:original(a,root))
    monkeypatch.setattr(m,'run_directory',lambda *a,**k:root/'run');monkeypatch.setattr(m,'_phase_query_records',lambda *a:[])
    path=root/m.OUTPUT/'plans'/m.value_hash(p)[:20]/'plan.json';m.atomic(path,p)
    runner=types.ModuleType('full_ssb_local_canonical_run');runner.read_plan=lambda *a:p
    runner.ops=SimpleNamespace(verify_owned_job_membership=lambda *a:None,operational_resources=lambda:dict(free_disk_bytes=20*2**30,available_memory_bytes=5*2**30,existing_ssb_bytes=0))
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical_run',runner)
    def science(*a):
        calls.append('synthetic_inference')
        if changed:raw.write_bytes(b'changed')
        return {'phase':phase}
    monkeypatch.setattr(m,'_scientific_phase',science)
    if changed:
        with pytest.raises(ValueError,match='physical artifact changed'):m.execute_worker(p,phase)
        assert m.read(root/'run'/phase.lower()/'science_control/lifecycle.json')['status']=='TAINTED'
        assert not (root/'run'/phase.lower()/'verification.json').exists()
    else:assert m.execute_worker(p,phase)=={'phase':phase}
    assert calls==['F','synthetic_inference']


@pytest.mark.parametrize('phase',['FORWARD','REVERSE'])
def test_scientific_plumbing_original_forward_one_load_reverse13_with_only_tiny_callbacks(tmp_path,monkeypatch,phase):
    import types
    import numpy as np
    m=module();sqls,names=m.sql_identities();monkeypatch.setattr(m,'run_directory',lambda *a,**k:tmp_path)
    for n in m.THREADS:monkeypatch.setenv(n,'1')
    monkeypatch.setenv('PYTHONHASHSEED',str(m.HASH_SEEDS[phase]))
    draws=[]
    class E:
        def evaluate_query(self,*a,**k):draws.append(int(np.random.randint(1000000)));return None,100.
        def _evaluate_group_by_spn_ensembles(self,q):return [],[],[]
    ensemble=types.ModuleType('ensemble_compilation.spn_ensemble');ensemble.SPNEnsemble=E;ensemble.read_ensemble=lambda *a,**k:E()
    package=types.ModuleType('ensemble_compilation');package.__path__=[];package.spn_ensemble=ensemble
    monkeypatch.setitem(sys.modules,'ensemble_compilation',package);monkeypatch.setitem(sys.modules,'ensemble_compilation.spn_ensemble',ensemble)
    original_observer=m.observe_evaluation
    @contextlib.contextmanager
    def late_import(*a,**k):
        np.random.seed(1) # Mirrors the released spn_ensemble import side effect.
        with original_observer(*a,**k) as count:yield count
    monkeypatch.setattr(m,'observe_evaluation',late_import)
    import full_ssb_replay as replay
    import full_ssb_native_replay as native
    monkeypatch.setattr(native,'deny_raw_data_access',lambda *a:contextlib.nullcontext())
    def q(i):return dict(query_no=i,query_name=names[i],sql=sqls[i],groups=[dict(key=[],prediction=100.,model_interval=[90.,110.])],nonfinite_original_intervals=[])
    def execute(i,*a):
        e=ensemble.read_ensemble('tiny');e.evaluate_query(None,confidence_intervals=False);e.evaluate_query(None,confidence_intervals=True)
        return dict(q(i),original_query_evaluator_calls=2,model_loads=1)
    monkeypatch.setattr(replay,'execute_query',execute)
    forward={'queries':[q(i) for i in range(13)],'coverage':{'fixture':True}}
    monkeypatch.setattr(m,'_verify_phase',lambda *a,**k:forward);monkeypatch.setattr(m,'phase_coverage',lambda *a:forward['coverage'])
    def evaluate(*a):
        e=ensemble.read_ensemble('tiny')
        for i in range(13):e.evaluate_query(None,confidence_intervals=False);e.evaluate_query(None,confidence_intervals=True)
        return dict(queries=forward['queries'],directory=str(tmp_path/'evaluation'),binding={},point_query_errors=0,ci_query_errors=0)
    guard=types.ModuleType('full_ssb_guard');guard.core=SimpleNamespace(population_truth_groups=lambda *a:{},evaluate_ssb=evaluate)
    monkeypatch.setitem(sys.modules,'full_ssb_guard',guard);monkeypatch.setattr(m,'read',lambda *a:{'queries':[]})
    parent={'report':dict(prepared_directory=str(tmp_path/'prepared'),directory=str(tmp_path/'old'),model={},model_path='tiny')}
    monkeypatch.setattr(m,'parent_snapshot',lambda *a:{})
    result=m._scientific_phase({'parent':{}},phase,parent)
    assert result['actual_model_loads']==(1 if phase=='FORWARD' else 13) and result['actual_evaluator_calls']==26
    assert len(result['queries'])==13 and result['evaluator_modes']==[False,True]*13
    assert draws[0]==int(np.random.RandomState(m.RANDOM_SEED).randint(1000000))


def synthetic_publication(m,root,monkeypatch,publish=True):
    """Actual new control/seal validators; parent and OS evidence are explicit test leaves."""
    import copy
    import full_ssb_local_canonical_run as runner
    from full_ssb_replay import coverage,compare_query
    sqls,names=m.sql_identities();monkeypatch.setattr(m,'sql_identities',lambda:(sqls,names))
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'PINS',{});monkeypatch.setattr(m,'FILES',())
    monkeypatch.setattr(m,'ADAPTER','adapter.py');monkeypatch.setattr(m,'WINDOWS_HELPER','fingerprint.py')
    for name in ('model.bin','raw.csv','adapter.py','fingerprint.py'):(root/name).write_bytes(name.encode())
    queries=[]
    for i,(sql,name) in enumerate(zip(sqls,names)):
        g=dict(key=[],prediction=100.,model_interval=[90.,110.],truth=101,status='MATCHED',zero_truth=False,sample_moments={'sum_integer':30},reference_ci={'eligible':True,'status':'REFERENCE_OK'},released_ci_comparison={})
        queries.append(dict(query_no=i,query_name=name,sql=sql,groups=[g],point_error=None,ci_error=None,truth_groups=1,model_groups=1,
            missing_model_groups=0,extra_model_groups=0,reference_ci_eligible_groups=1,nonfinite_original_intervals=[]))
    old=dict(inputs={'synthetic_parent_only':True},prepared_directory=str(root/'old/prepared'),directory=str(root/'old'),model_path=str(root/'model.bin'),
        model={},spn_count=5,training_tables=[],fact_normalizer=123,queries=queries)
    m.atomic(root/'parent.json',old);d=m.artifact(root/'parent.json',root)
    records=[d]+[m.artifact(root/n,root) for n in ('model.bin','raw.csv')]
    parent=dict(report=old,artifacts=records,published_result=d,verification=d,verification_seal=d,formal_receipt=d,formal_lifecycle=d,plan=d,
        model_path=old['model_path'],model_sha256=m.digest(root/'model.bin'),sample_rows=m.source.SAMPLE_ROWS,population_rows=m.source.N,original_mismatch={},closure_sha256=m.value_hash(records))
    deps=dict(environment={},canonical_sources={},frozen_sources={},group_order_adapter=m.artifact(root/'adapter.py',root))
    monkeypatch.setattr(m,'code_snapshot',lambda:{})
    monkeypatch.setattr(m,'dependency_snapshot',lambda:deps);monkeypatch.setattr(m.source,'environment_artifacts',lambda *a:[])
    monkeypatch.setattr(runner,'verify_child',lambda *a:[])
    c=runner.candidate_body(m.value_hash(deps['canonical_sources']),m.parent_snapshot(parent),deps)
    plan=dict(c,status='ROOT_REVIEWED_LOCAL_CANONICAL_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(c))
    key=m.value_hash(plan);path=root/m.OUTPUT/'plans'/key[:20]/'plan.json';m.atomic(path,plan);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    run=m.run_directory(plan,root)
    for phase in m.PHASES:
        binding=m.phase_binding(plan,phase);query_binding={'synthetic':'original_binding'} if phase=='FORWARD' else binding
        directory=run/phase.lower()/'evaluation'
        if phase=='FORWARD':directory=directory/m.hashlib.sha256(m.json.dumps(query_binding,sort_keys=True).encode()).hexdigest()[:16]
        actual=copy.deepcopy(queries)
        if phase=='REVERSE':
            actual=[dict(query_no=q['query_no'],query_name=q['query_name'],sql=q['sql'],groups=[dict(key=g['key'],prediction=g['prediction'],model_interval=g['model_interval']) for g in q['groups']],
                nonfinite_original_intervals=[],original_query_evaluator_calls=2,model_loads=1) for q in actual]
        for i,q in enumerate(actual):
            f=directory/('query_%02d.json'%i);m.atomic(f,q);m.atomic(f.with_suffix('.seal.json'),{'binding':query_binding,'sha256':m.digest(f)})
        r=dict(status='PASS_CANONICAL_'+phase+'_EVALUATION',scope=m.SCOPE,phase=phase,plan_binding_sha256=key,binding=binding,directory=str(run),
            evaluation_directory=str(directory),evaluation_binding=query_binding,queries=actual,comparisons={} if phase=='FORWARD' else {str(i):compare_query(queries[i],q) for i,q in enumerate(actual)},
            execution_order=list(range(13)) if phase=='FORWARD' else list(reversed(range(13))),actual_model_loads=1 if phase=='FORWARD' else 13,actual_evaluator_calls=26,evaluator_modes=[False,True]*13,
            environment=dict(PYTHONHASHSEED=str(m.HASH_SEEDS[phase]),random_seed=m.RANDOM_SEED,numpy_seed=m.RANDOM_SEED,thread_limits={n:'1' for n in m.THREADS}),
            parent=m.parent_snapshot(parent),group_order_adapter_sha256=m.ADAPTER_SHA,coverage=coverage({'queries':queries}),author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False)
        home=run/phase.lower();m.base.formal_transaction(home/'science_control',binding,lambda:r,lambda x:None,kind='CANONICAL_'+phase)
        m.atomic(home/'verification.json',r);m.atomic(home/'seal.json',dict(status='PASS_CANONICAL_PHASE',phase=phase,artifacts=m._phase_artifacts(plan,r,parent,root)))
    r=m.report_body(plan,path,parent,root)
    m.base.formal_transaction(run/'root_control',m.root_binding(plan),lambda:r,lambda x:m.validate_report(x,parent,root),kind='CANONICAL_ROOT')
    if publish:m.publish_report(r,parent,root)
    return parent,r


@pytest.mark.parametrize('field',['model_groups','missing_model_groups'])
def test_resealed_forward_query_and_coverage_cannot_relabel_parent_coverage(tmp_path_factory,monkeypatch,field):
    from full_ssb_replay import coverage
    m=module();root=tmp_path_factory.mktemp('c');parent,r=synthetic_publication(m,root,monkeypatch,publish=False)
    phase=m.read(Path(r['directory'])/'forward/verification.json');query=phase['queries'][0];query[field]=999
    path=Path(phase['evaluation_directory'])/'query_00.json';m.atomic(path,query)
    m.atomic(path.with_suffix('.seal.json'),dict(binding=phase['evaluation_binding'],sha256=m.digest(path)))
    phase['coverage']=coverage({'queries':phase['queries']})
    with pytest.raises(ValueError,match='coverage|count'):m._phase_query_records(r['plan'],phase,parent,root)


@pytest.mark.parametrize('damage',[None,'subset','root_running','reverse_tainted','missing_query','write_failure'])
def test_complete_synthetic_publication_public_one_f_and_physical_failure_refusal(tmp_path_factory,monkeypatch,damage):
    import inspect
    m=module();root=tmp_path_factory.mktemp('p');parent,r=synthetic_publication(m,root,monkeypatch,publish=damage!='write_failure');run=Path(r['directory'])
    if damage=='write_failure':
        original=m.atomic
        def fail(path,value):
            if Path(path)==root/m.RESULT:raise OSError('synthetic publication write')
            return original(path,value)
        monkeypatch.setattr(m,'atomic',fail)
        with pytest.raises(OSError):m.publish_report(r,parent,root)
        assert m.read(run/'root_control/lifecycle.json')['status']=='TAINTED';return
    if damage=='subset':
        path=run/'verification_seal.json';body=m.read(path);body['artifacts']=body['artifacts'][1:];m.atomic(path,body)
    elif damage in ('root_running','reverse_tainted'):
        path=run/('root_control/lifecycle.json' if damage=='root_running' else 'reverse/science_control/lifecycle.json');body=m.read(path);body['status']='RUNNING' if damage=='root_running' else 'TAINTED';m.atomic(path,body)
    elif damage=='missing_query':
        directory=Path(m.read(run/'reverse/verification.json')['evaluation_directory']);(directory/'query_12.seal.json').unlink()
    calls=[];monkeypatch.setattr(m,'collect_parent',lambda *a:calls.append('F') or parent)
    if damage is None:
        before={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
        result=m.verify_canonical(root);assert result['status']==m.API_PASS and result['parent_snapshot']['report']==parent['report']
        assert result['evaluation_variant']=='CANONICAL_DECODED_GROUP_PROTOTYPE_V1' and result['author_reproduction_complete'] is False
        assert calls==['F'];m.verify_canonical(root);assert calls==['F','F']
        assert before=={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
        assert list(inspect.signature(m.verify_canonical).parameters)==['root']
    else:
        with pytest.raises((ValueError,OSError)):m.verify_canonical(root)
        assert calls==['F']
