"""Real CI control stack, mocked physical leaves; no parent/science execution."""
import ast
import contextlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import types
from collections import Counter
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    s=importlib.util.spec_from_file_location('ci_calls_test',str(ROOT/'code/full_ssb_local_ci.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def full_parent_calls_per_collect():
    tree=ast.parse((ROOT/'code/full_ssb_local_ci.py').read_text(encoding='utf-8'))
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('collect_lineage','_verified_parent_canonical')]
    def number(target):
        expected=ast.dump(ast.parse(target,mode='eval').body)
        return sum(isinstance(n,ast.Call) and ast.dump(n.func)==expected for f in functions for n in ast.walk(f))
    # Canonical public verification directly performs one complete original F.
    # This pinned leaf is modelled, never executed by these tests.
    return number('previous.verify_local_formal')+number('canonical.verify_canonical')


def controls(monkeypatch):
    m=module();counts=Counter();monkeypatch.setattr(m,'native_platform',lambda:contextlib.nullcontext({}))
    full={'inputs':{'physical_artifacts':[]},'artifacts':[],'prior_dependencies':{},'parent_formal':{},'parent_reverse':{},'parent_canonical':{}}
    def collect(root=m.ROOT):counts['parent_collections']+=1;counts['complete1m_formal']+=full_parent_calls_per_collect();return full
    monkeypatch.setattr(m,'collect_lineage',collect);monkeypatch.setattr(m,'golden_inputs',lambda:{'fixture':'mock'})
    monkeypatch.setattr(m,'dependency_snapshot',lambda *a,**k:{'auxiliary_sources':{}});monkeypatch.setattr(m,'verify_publication',lambda *a,**k:[])
    monkeypatch.setattr(m,'artifact',lambda p,root=m.ROOT:dict(path=str(Path(p).relative_to(root)),bytes=0,sha256='mock'))
    reports={}
    for kind in ('FORMAL','GOLDEN'):
        key=('f' if kind=='FORMAL' else 'a')*64
        reports[kind]=dict(kind=kind,scope=m.SCOPE,stage=m.STAGE,status=m.PASS,directory=str(m.ROOT/m.OUTPUT/'runs'/key[:20]),plan_path=kind+'.json',plan_file_sha256='mock',plan_binding_sha256=key,
            plan={'kind':kind,'dependencies':{'auxiliary_sources':{}},'lineage':m.lineage_snapshot(full),'golden':{'fixture':'mock'}},lineage=m.lineage_snapshot(full),inputs=full['inputs'],inherited_artifacts=[],golden_artifacts=[],
            training_cap_per_table=10000000,actual_training_rows_per_table=m.EXPECTED_ROWS,point_query_errors=0,ci_query_errors=0,model_path='mock',model_sha256='mock',queries=[],evaluation_binding={},original_mismatch={},**m.EVALUATION_METADATA)
    monkeypatch.setattr(m,'read',lambda p:reports['GOLDEN' if Path(p)==m.ROOT/m.GOLDEN_RESULT else 'FORMAL'])
    runner=types.ModuleType('full_ssb_local_ci_run');runner.read_plan=lambda p,*a:reports[Path(p).stem]['plan'];runner.verify_supervisor=lambda *a:[]
    monkeypatch.setitem(sys.modules,'full_ssb_local_ci_run',runner);monkeypatch.setattr(Path,'is_file',lambda p:True)
    prior=m.verify_golden();reports['FORMAL']['plan']['golden']=m.golden_snapshot(prior);counts.clear()
    return m,counts


def test_public_ci_real_control_stack_six_full_parent_verifications_become_one(monkeypatch):
    m,counts=controls(monkeypatch);m.verify_local_ci()
    assert counts=={'parent_collections':1,'complete1m_formal':1}
    counts.clear();m.verify_local_ci();assert counts=={'parent_collections':1,'complete1m_formal':1}


def test_public_golden_real_control_stack_has_one_fresh_parent_and_no_external_cache_argument(monkeypatch):
    m,counts=controls(monkeypatch);m.verify_golden();assert counts=={'parent_collections':1,'complete1m_formal':1}
    assert list(inspect.signature(m.verify_golden).parameters)==['root']
    assert list(inspect.signature(m.verify_local_ci).parameters)==['root']
    assert list(inspect.signature(m.verify_scientific_publication).parameters)==['kind','root']


def parent_body(m):
    return dict(status=m.previous.PASS,stage='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI',scope=m.source.SCOPE,population_rows=m.source.N,actual_sample_rows=m.source.SAMPLE_ROWS,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,author_population_row_count_and_13_truths_match=False,author_full_row_byte_identity_proven=False,
        point_query_errors=0,ci_query_errors=0,plan={'model':dict(m.previous.MODEL),'dependencies':{}},model_path='parent.pkl',model_sha256='a'*64,evaluation_binding={},
        original_mismatch={'path':m.source.NATIVE_REPORT,'sha256':m.source.NATIVE_REPORT_SHA},inputs={'receipt_sha256':m.SOURCE_RECEIPT_SHA})


def canonical_parent(m,snap,r):
    formal=dict(snap,status=m.previous.API_PASS,report=r,proof_method='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL')
    return dict(status='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH',scope='LOCAL_SSB_SF500_CANONICAL_CI',
        population_rows=m.source.N,sample_rows=m.source.SAMPLE_ROWS,author_different_groups=1713,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,parent_snapshot=formal,parent_formal=snap['published_result'],
        model_path=r['model_path'],model_sha256=r['model_sha256'],historical_reverse_accepted=False,
        published_result={'path':'output/full/results/ssb_local_sf500_canonical_aqp_ci.json','bytes':1,'sha256':'c'*64},**m.EVALUATION_METADATA)


@pytest.mark.parametrize('damage',[None,'alias','bytes','sha','author','budget','model','canonical_scope','canonical_status','variant','adapter','proof','parent_report'])
def test_delegated_formal_body_requires_exact_current_published_descriptor_and_fields(tmp_path,damage):
    m=module();r=parent_body(m);path=tmp_path/m.previous.RESULT;m.atomic(path,r)
    snap=dict(published_result=m.artifact(path,tmp_path),scope=m.source.SCOPE,population_rows=m.source.N,sample_rows=m.source.SAMPLE_ROWS,author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,dependencies={},model_path=r['model_path'],model_sha256=r['model_sha256'],evaluation_binding={},original_mismatch=r['original_mismatch'])
    reverse=canonical_parent(m,snap,r)
    # A tiny physical fixture replaces only the fixed historical report hash.
    m.PARENT_RESULT_SHA=snap['published_result']['sha256']
    if damage=='alias':snap['published_result']['path']='another.json'
    elif damage=='bytes':snap['published_result']['bytes']+=1
    elif damage=='sha':snap['published_result']['sha256']='f'*64
    elif damage in ('author','budget','model'):
        if damage=='author':r['author_reproduction_complete']=True
        elif damage=='budget':r['plan']['model']['samples_per_spn']=10000000
        else:r['model_sha256']='b'*64
        m.atomic(path,r);snap['published_result']=m.artifact(path,tmp_path)
        reverse['parent_snapshot']['published_result']=snap['published_result'];reverse['parent_formal']=snap['published_result'];m.PARENT_RESULT_SHA=snap['published_result']['sha256']
    elif damage=='canonical_scope':reverse['scope']=m.source.SCOPE
    elif damage=='canonical_status':reverse['status']='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH'
    elif damage=='variant':reverse['evaluation_variant']='ORIGINAL'
    elif damage=='adapter':reverse['group_order_adapter_sha256']='f'*64
    elif damage=='proof':reverse['parent_snapshot']['proof_method']='stored JSON'
    elif damage=='parent_report':reverse['parent_snapshot']['report']=dict(r,stage='changed')
    if damage is None:assert m._read_delegated_parent(reverse,tmp_path)==(reverse['parent_snapshot'],r)
    else:
        with pytest.raises(ValueError):m._read_delegated_parent(reverse,tmp_path)


def test_pin_failure_happens_before_frozen_canonical_public_call(monkeypatch):
    m=module();called=[];fake=types.ModuleType('full_ssb_local_canonical');fake.verify_canonical=lambda:called.append('unexpected')
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical',fake);monkeypatch.setattr(m,'digest',lambda *a:'wrong')
    with pytest.raises(ValueError,match='frozen|pin|changed'):m._verified_parent_canonical(m.ROOT)
    assert called==[]


def test_verified_canonical_delegate_calls_only_its_public_verifier_once(monkeypatch):
    m=module();calls=[];proof=object()
    fake=types.ModuleType('full_ssb_local_canonical');fake.__file__=str(m.ROOT/'code/full_ssb_local_canonical.py')
    fake.verify_canonical=lambda:calls.append('canonical public') or proof
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical',fake)
    failed=types.ModuleType('full_ssb_local_replay');failed.verify=lambda:pytest.fail('failed9c is never a delegate')
    monkeypatch.setitem(sys.modules,'full_ssb_local_replay',failed)
    monkeypatch.setattr(m.previous,'verify_local_formal',lambda *a:pytest.fail('the original F is exclusively inside the canonical boundary'))
    assert m._verified_parent_canonical(m.ROOT) is proof and calls==['canonical public']


@pytest.mark.parametrize('changed',sorted(module().PRIOR_PINS.keys() | {'code/full_ssb_local_canonical.py','code/full_ssb_local_canonical_run.py','code/full_ssb_group_order.py','code/full_ssb_local_replay.py','code/full_ssb_replay.py','code/full_ssb_native_replay.py'}))
def test_every_fixed_parent_source_pin_is_checked_before_canonical_call(monkeypatch,changed):
    m=module();called=[];pins=dict(m.PRIOR_PINS,**m.PARENT_CANONICAL_PINS)
    fake=types.ModuleType('full_ssb_local_canonical');fake.__file__=str(m.ROOT/'code/full_ssb_local_canonical.py');fake.verify_canonical=lambda:called.append('unexpected')
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical',fake)
    monkeypatch.setattr(m,'digest',lambda p:'wrong' if Path(p)==m.ROOT/changed else pins[Path(p).relative_to(m.ROOT).as_posix()])
    with pytest.raises(ValueError,match='pin changed'):m._verified_parent_canonical(m.ROOT)
    assert called==[]


def test_canonical_lineage_inherits_full_original_proof_and_new_artifacts_once(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'native_platform',lambda:contextlib.nullcontext({}));monkeypatch.setattr(m,'PRIOR_PINS',{});monkeypatch.setattr(m,'PARENT_CANONICAL_PINS',{})
    r=parent_body(m);r.update(directory=str(tmp_path/'old'),prepared_directory=str(tmp_path/'prepared'))
    path=tmp_path/m.previous.RESULT;m.atomic(path,r);published=m.artifact(path,tmp_path);m.PARENT_RESULT_SHA=published['sha256']
    snap=dict(published_result=published,verification=published,verification_seal=published,scope=m.source.SCOPE,population_rows=m.source.N,
        sample_rows=m.source.SAMPLE_ROWS,author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        dependencies={},model_path=r['model_path'],model_sha256=r['model_sha256'],evaluation_binding={},original_mismatch=r['original_mismatch'],artifacts=[published])
    canonical=canonical_parent(m,snap,r);canonical['artifacts']=[]
    for name in ('published_result','verification','verification_seal','forward','reverse'):
        f=tmp_path/('new_'+name+'.json');m.atomic(f,{'only':'synthetic canonical leaf'});d=m.artifact(f,tmp_path)
        canonical[name]=d;canonical['artifacts'].append(d)
    canonical['published_result']['path']=m.PARENT_CANONICAL_RESULT
    f=tmp_path/m.PARENT_CANONICAL_RESULT;m.atomic(f,{'only':'synthetic canonical leaf'});canonical['published_result']=m.artifact(f,tmp_path);canonical['artifacts'][0]=canonical['published_result']
    m.atomic(Path(r['directory'])/'supervisor_control/monitor.json',{'peak_owned_rss_bytes':123})
    calls=[];monkeypatch.setattr(m,'_verified_parent_canonical',lambda *a:calls.append('canonical public') or canonical)
    monkeypatch.setattr(m.previous,'verify_local_formal',lambda *a:pytest.fail('canonical is the sole delegated complete parent boundary'))
    monkeypatch.setattr(m,'prepared_shapes',lambda *a:{'metadata':'fixture only'})
    full=m.collect_lineage(tmp_path)
    assert calls==['canonical public'] and full['parent_formal']==published and full['parent_reverse']==canonical['reverse']
    assert full['parent_canonical']==canonical['published_result'] and all(d in full['artifacts'] for d in canonical['artifacts']+[published])
    assert full['historical_reverse_accepted'] is False and full['evaluation_variant']==m.EVALUATION_METADATA['evaluation_variant']


@pytest.mark.parametrize('key',list(module().EVALUATION_METADATA))
def test_public_ci_rejects_resealed_wrong_evaluation_variant(monkeypatch,key):
    m,counts=controls(monkeypatch);r=m.read(m.ROOT/m.RESULT);r[key]='wrong'
    with pytest.raises(ValueError,match='canonical|variant|adapter'):m.verify_local_ci()


def test_public_ci_returns_exact_group_variant_and_preserves_parent_canonical(monkeypatch):
    m,counts=controls(monkeypatch);r=m.verify_local_ci()
    assert all(r[k]==v for k,v in m.EVALUATION_METADATA.items()) and 'parent_canonical' in r['lineage']


@pytest.mark.parametrize('existing_pass',[False,True])
@pytest.mark.parametrize('tamper',[False,True])
def test_supervisor_same_stack_postflight_only_and_existing_pass_fresh_verify(tmp_path,monkeypatch,existing_pass,tamper):
    """Run the actual supervisor closure; mock only OS/physical scientific leaves."""
    import full_ssb_local_ci_run as runner
    counts=Counter();m=module();monkeypatch.setattr(runner,'model',m);monkeypatch.setattr(runner,'ROOT',tmp_path)
    p={'kind':'FORMAL','source_receipt_sha256':m.SOURCE_RECEIPT_SHA,'lineage':{'parent':'bound'},'golden':{'golden':'bound'},
        'dependencies':{'auxiliary_sources':{},'ci_sources':{'code/full_ssb_local_ci.py':'a'*64}}}
    monkeypatch.setattr(runner,'read_plan',lambda *a:p);monkeypatch.setattr(runner,'supervisor_binding',lambda *a:{'bootstrap_executable':{'fake':'base'}})
    monkeypatch.setattr(m,'dependency_snapshot',lambda *a:p['dependencies'])
    def pre(*a):counts['root_preflight']+=1;return {},{'verified':'golden'}
    monkeypatch.setattr(m,'_verify_prerequisites',pre);monkeypatch.setattr(m,'lineage_snapshot',lambda *a:p['lineage'])
    monkeypatch.setattr(m,'golden_snapshot',lambda *a:p['golden'])
    monkeypatch.setattr(m,'collect_lineage',lambda *a:counts.update(old_direct_collection=1) or {})
    monkeypatch.setattr(runner.base,'check_resources',lambda *a,**k:None)
    monkeypatch.setattr(runner.base,'controller_lock',lambda *a:contextlib.nullcontext())
    monkeypatch.setattr(runner.ops,'operational_resources',lambda:dict(available_memory_bytes=8*2**30,free_disk_bytes=30*2**30,existing_ssb_bytes=0))
    monkeypatch.setattr(runner.ops,'base_python_executable',lambda:tmp_path/'base.exe')
    monkeypatch.setattr(runner,'artifact',lambda *a,**k:{'fake':'base'})
    monkeypatch.setattr(runner.ops,'run_owned_child',lambda *a,**k:{'artifacts':[],'returncode':0})
    report=tmp_path/m.RESULT;seal=tmp_path/'seal.json';m.atomic(report,{'actual':'published'});m.atomic(seal,{'seal':'actual'})
    def post(*a):
        counts['root_postflight']+=1
        return {'published_result':m.artifact(report,tmp_path),'verification_seal':m.artifact(seal,tmp_path)}
    monkeypatch.setattr(m,'verify_scientific_publication',post)
    def validate(*a):
        counts['monitor_validation']+=1
        if tamper:m.atomic(report,{'actual':'changed after postflight'})
    monkeypatch.setattr(runner,'verify_supervisor_result',validate);monkeypatch.setattr(runner,'taint_local_tail',lambda *a:counts.update(tainted=1))
    def transaction(home,binding,producer,validator,**kwargs):
        result={'published_result_sha256':m.digest(report),'verification_seal_sha256':m.digest(seal)} if existing_pass else producer()
        validator(result);return result
    monkeypatch.setattr(runner.base,'formal_transaction',transaction)
    if tamper:
        with pytest.raises(ValueError,match='postflight|publication'):runner.run_supervised(tmp_path/'plan.json','b'*64,True,tmp_path)
        assert counts['tainted']==1
    else:runner.run_supervised(tmp_path/'plan.json','b'*64,True,tmp_path)
    assert counts['root_postflight']==1 and counts['monitor_validation']==1
    assert counts['root_preflight']==(0 if existing_pass else 1) and counts['old_direct_collection']==0


@pytest.mark.parametrize('parent_changed',[False,True])
def test_actual_formal_worker_controller_checks_parent_fresh_before_and_after_fit(tmp_path,monkeypatch,parent_changed):
    """The real FORMAL controller runs; all scientific functions are tiny stubs."""
    m=module();calls=[];monkeypatch.setattr(m,'native_platform',lambda:contextlib.nullcontext({}));monkeypatch.setattr(m,'ROOT',tmp_path)
    full={'inputs':{'physical_artifacts':[],'receipt_sha256':m.SOURCE_RECEIPT_SHA,'original_mismatch':{},'fact_normalizer':123},
        'artifacts':[],'prior_dependencies':{},'parent_formal':{},'parent_reverse':{},'prepared_directory':str(tmp_path/'prepared'),
        'moments_directory':str(tmp_path/'moments'),'moments_helper_directory':str(tmp_path/'helper'),'truth_projection_path':str(tmp_path/'truth.json')}
    g=dict(status='complete_mock_golden',published_result={},verification={},verification_seal={},artifacts=[])
    p=dict(kind='FORMAL',lineage=m.lineage_snapshot(full),golden=m.golden_snapshot(g),dependencies={'auxiliary_sources':{},'stage_validation':{},'runtime_cap':{}})
    def collect(*a):
        calls.append('fresh_parent')
        return dict(full,marker='changed') if parent_changed and calls.count('fresh_parent')==2 else full
    monkeypatch.setattr(m,'collect_lineage',collect);monkeypatch.setattr(m,'_verify_golden_with_parent',lambda *a:g)
    monkeypatch.setattr(m,'require_worker',lambda p:('a'*64,tmp_path/'plan.json'))
    monkeypatch.setattr(m,'read',lambda *a:{'queries':[]});monkeypatch.setattr(m,'digest',lambda *a:'b'*64)
    monkeypatch.setattr(m,'dependency_snapshot',lambda *a:p['dependencies']);monkeypatch.setattr(m.base,'make_schema',lambda *a:'mock_schema')
    monkeypatch.setattr(m.base,'check_resources',lambda *a,**k:{})
    monkeypatch.setattr(m.base,'controller_lock',lambda *a:contextlib.nullcontext());monkeypatch.setattr(m,'publish',lambda *a:calls.append('published'))
    monkeypatch.setattr(m,'runtime_cap_adapter',lambda *a:contextlib.nullcontext({}))
    @contextlib.contextmanager
    def canonical_context():
        calls.append('canonical_enter')
        try:yield
        finally:calls.append('canonical_exit')
    monkeypatch.setattr(m,'canonical_evaluation',canonical_context)
    def fit(*a):
        calls.append('fit')
        return dict(model_path='mock.pkl',spn_count=5,training_tables=[dict(table=t,actual_training_rows=n) for t,n in m.EXPECTED_ROWS.items()])
    evaluated=dict(point_query_errors=0,ci_query_errors=0,queries=[],directory='mock_eval',binding={})
    def evaluate(*a):
        assert calls[-1]=='canonical_enter';calls.append('evaluate');return evaluated
    guard=types.ModuleType('full_ssb_guard');guard.core=types.SimpleNamespace(population_truth_groups=lambda *a:[]);guard.guarded_train=fit;guard.guarded_evaluate=evaluate
    monkeypatch.setitem(sys.modules,'full_ssb_guard',guard)
    stages=types.ModuleType('full_ssb_local_stage_validation');stages.validate=lambda *a:calls.append('own_stages_checked');monkeypatch.setitem(sys.modules,'full_ssb_local_stage_validation',stages)
    runner=types.ModuleType('full_ssb_local_ci_run');runner.ops=types.SimpleNamespace(operational_resources=lambda:dict(free_disk_bytes=30*2**30,available_memory_bytes=8*2**30,existing_ssb_bytes=0));monkeypatch.setitem(sys.modules,'full_ssb_local_ci_run',runner)
    def transaction(home,binding,producer,validator,**k):r=producer();validator(r);return r
    monkeypatch.setattr(m.base,'formal_transaction',transaction)
    if parent_changed:
        with pytest.raises(ValueError,match='changed during'):m.execute_reviewed(p)
        assert calls==['fresh_parent','fit','canonical_enter','evaluate','canonical_exit','fresh_parent']
    else:
        r=m.execute_reviewed(p);assert calls==['fresh_parent','fit','canonical_enter','evaluate','canonical_exit','fresh_parent','own_stages_checked','published']
        assert all(r[k]==v for k,v in m.EVALUATION_METADATA.items())
