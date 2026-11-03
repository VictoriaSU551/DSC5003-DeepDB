"""Synthetic local-only model contracts; no preparation, fit or inference."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_ssb_local_model.py';assert p.exists(),'local model adapter missing'
    spec=importlib.util.spec_from_file_location('local_ssb_model_test',str(p));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_no_local_scientific_stage_can_start_without_reviewed_plan():
    m=module()
    with pytest.raises(ValueError,match='reviewed|scope'):m.execute_local_formal({},memory_approved=True)


def test_missing_local_formal_readonly_verifier_creates_nothing(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='missing'):m.verify_local_formal(root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_local_output_context_requires_fresh_worker_and_restores_on_failure(tmp_path,monkeypatch):
    m=module();core=SimpleNamespace(OUTPUT='original historical')
    directory=tmp_path/m.OUTPUT/'runtime'
    with pytest.raises(ValueError,match='fresh'):
        with m.local_output(core,directory,tmp_path):pass
    monkeypatch.setenv('DEEPDB_SSB_LOCAL_WORKER','1')
    with pytest.raises(RuntimeError):
        with m.local_output(core,directory,tmp_path):
            assert core.OUTPUT==directory;raise RuntimeError('synthetic interruption')
    assert core.OUTPUT=='original historical'


@pytest.mark.parametrize('damage',[None,'author_status','scope','author_gap','author_complete','paper_complete','source_status'])
def test_local_model_scope_never_aliases_author_success(damage):
    m=module();report=dict(status=m.PASS,scope=m.source.SCOPE,author_different_groups=1713,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,original_mismatch={'path':m.source.NATIVE_REPORT,'sha256':m.source.NATIVE_REPORT_SHA},
        inputs={'status':m.source.STATUS,'different_author_groups':1713,'scope':m.source.SCOPE})
    if damage=='author_status':report['status']='PASS_AUTHOR_TRUTHS'
    elif damage=='scope':report['scope']='SSB_AUTHOR'
    elif damage=='author_gap':report['author_different_groups']=1712
    elif damage=='author_complete':report['author_reproduction_complete']=True
    elif damage=='paper_complete':report['full_paper_reproduction_complete']=True
    elif damage=='source_status':report['inputs']['status']='PASS_AUTHOR_TRUTHS'
    if damage is None:m.validate_scope(report)
    else:
        with pytest.raises(ValueError):m.validate_scope(report)


def synthetic_stages(m,root,run_id='synthetic',source_sha='a'*64):
    """Adapt the existing labelled fake-file fixture; no author acceptance used."""
    import test_full_ssb_native_model as fixtures
    proxy=SimpleNamespace(**vars(m.base));proxy.OUTPUT_REL=m.OUTPUT
    complete={'sources':{'synthetic':'fixture'}}
    report,author=fixtures.synthetic_stages(proxy,root,run_id=run_id,complete=complete)
    local=copy.deepcopy(author)
    for row in local:
        if row['query_no']>=6:row['value']+=1
    n=m.source.SAMPLE_ROWS;p=float(m.source.CUTOFF/2**64);run=Path(report['directory'])
    report.update(scope=m.source.SCOPE,status=m.PASS,population_rows=m.source.N,actual_sample_rows=n,
        source_receipt_sha256=source_sha,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        original_mismatch={'path':m.source.NATIVE_REPORT,'sha256':m.source.NATIVE_REPORT_SHA})
    report['plan']={'dependencies':{'environment':{'complete':complete}}}
    report['inputs'].update(status=m.source.STATUS,scope=m.source.SCOPE,different_author_groups=1713,canonical_truth=local,
        sample_rows=n,receipt_sha256=source_sha,probability={'numerator':m.source.CUTOFF,'denominator':2**64})
    def refresh_outer(directory,kind,result,extra=None):
        home=m.base.stage_home(directory,kind);receipt=m.base.read(home/'receipt.json');receipt['result']=result;receipt['binding'].update(extra or {})
        m.base.atomic(home/'receipt.json',receipt);state=m.base.read(home/'lifecycle.json');state.update(binding=receipt['binding'],receipt_sha256=m.base.digest(home/'receipt.json'));m.base.atomic(home/'lifecycle.json',state)
    model=report['model'];directory=run/'model'
    for row in model['training_tables']:
        if row['table']=='lineorder':row['full_join_estimate']=n/p
        path=directory/(row['table']+'.json');record=m.base.read(path);record['training']=row;m.base.atomic(path,record)
    m.base.atomic(directory/'model.json',model);guard=m.base.read(directory/'model_guard.json')
    guard['model_files_sha256']={name:m.base.digest(directory/name) for name in guard['model_files_sha256']};m.base.atomic(directory/'model_guard.json',guard)
    refresh_outer(directory,'model',model)
    path=run/'sample_moments_native/moments.json';moment=m.base.read(path);moment['sample_rows']=n;m.base.atomic(path,moment)
    sealpath=path.parent/'seal.json';seal=m.base.read(sealpath);seal['binding']['sample_rows']=n;seal['sha256']=m.base.digest(path);m.base.atomic(sealpath,seal)
    checkpoint=run/'core_truth_checkpoint.json';m.base.atomic(checkpoint,m.truth_projection(report['inputs']))
    ebinding=report['evaluation_binding'];ebinding.update(confidence_sample_size=n,truth_checkpoint_sha256=m.base.digest(checkpoint),
        model_sha256=report['model_sha256'],model_input_artifact_guard_sha256=m.base.digest(directory/'model_guard.json'),sql_sha256=m.base.SQL_SHA)
    for q,identity in zip(report['queries'],report['evaluation']['identities']):
        if q['query_no']>=6:
            for group in q['groups']:group['truth']+=1;group['prediction']+=1
        path=Path(report['evaluation_directory'])/('query_%02d.json'%q['query_no']);m.base.atomic(path,q)
        m.base.atomic(path.with_suffix('.seal.json'),{'binding':ebinding,'sha256':m.base.digest(path)})
        identity.update(global_binding=ebinding,result_sha256=m.base.digest(path),core_seal_sha256=m.base.digest(path.with_suffix('.seal.json')))
    refresh_outer(run/'evaluation','evaluation',report['evaluation'],dict(model_outer_receipt_sha256=m.base.digest(m.base.stage_home(directory,'model')/'receipt.json'),
        model_sha256=report['model_sha256'],truth_sha256=m.base.digest(checkpoint)))
    return report


def test_local_stages_validate_all_local_truth_and_static_hdf_inventory(tmp_path,monkeypatch):
    m=module();r=synthetic_stages(m,tmp_path)
    monkeypatch.setattr(__import__('pickle'),'load',lambda *a,**k:pytest.fail('readonly must not unpickle'))
    records=m.stage_artifacts(r,tmp_path)
    assert sum('/query_' in p['path'] for p in records)==26 and any(p['path'].endswith('customer.hdflineorder.hdf') for p in records)


@pytest.mark.parametrize('damage',['query_subset','truth','author_truth','checkpoint_subset','unmatched_subset','moment_n','model_link','exactN'])
def test_local_stages_reject_resealed_subsets_or_author_truth(damage,tmp_path):
    m=module();r=synthetic_stages(m,tmp_path);run=Path(r['directory'])
    if damage=='query_subset':r['queries']=r['queries'][:12]
    elif damage in ('truth','author_truth'):r['queries'][6]['groups'][0]['truth']-=1
    elif damage=='checkpoint_subset':r['model']['files_sha256'].pop('supplier.pkl')
    elif damage=='unmatched_subset':
        p=run/'prepared';seal=m.base.read(p/'seal.json');seal['files_sha256'].pop('customer.hdflineorder.hdf');m.base.atomic(p/'seal.json',seal)
        outer=m.base.stage_home(p,'prepared');receipt=m.base.read(outer/'receipt.json');receipt['result']['core_input_artifacts']['prepared_files_sha256']=seal['files_sha256']
        receipt['result']['core_seal_sha256']=m.base.digest(p/'seal.json');m.base.atomic(outer/'receipt.json',receipt)
        state=m.base.read(outer/'lifecycle.json');state['receipt_sha256']=m.base.digest(outer/'receipt.json');m.base.atomic(outer/'lifecycle.json',state)
    elif damage=='moment_n':
        p=run/'sample_moments_native/moments.json';b=m.base.read(p);b['sample_rows']-=1;m.base.atomic(p,b)
    elif damage=='model_link':r['evaluation_binding']['model_sha256']='f'*64
    else:r['model']['training_tables'][0]['full_join_estimate']=m.source.N
    with pytest.raises((ValueError,KeyError,OSError)):m.stage_artifacts(r,tmp_path)


def synthetic_publication(m,root,monkeypatch,publish=True):
    codes={}
    for name in m.source.LOCAL_FILES:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes() if (ROOT/name).exists() else b'SYNTHETIC unexecuted local runner')
        codes[name]=m.digest(path)
    gate={}
    for key in ('verification','verification_seal','audit_receipt','audit_lifecycle','publication_receipt','publication_lifecycle'):
        f=root/m.source.OUTPUT/'synthetic_gate'/(key+'.json');m.atomic(f,{'synthetic_only':True});gate[key]=m.artifact(f,root)
    source_sha=gate['verification']['sha256']
    dependencies=dict(environment={'complete':{'sources':{'synthetic':'fixture'}}},local_sources=codes,auxiliary_sources={})
    plan=dict(status='ROOT_REVIEWED_LOCAL_SSB_MODEL_PLAN',scope=m.source.SCOPE,executable=True,model=m.MODEL,
        source_receipt_sha256=source_sha,dependencies=dependencies,root_decision_sha256=m.source.DECISION_SHA)
    p=m.value_hash(plan);r=synthetic_stages(m,root,p[:20],source_sha);run=Path(r['directory']);r['plan']=plan
    path=root/m.OUTPUT/'plans'/p[:20]/'plan.json';m.atomic(path,plan);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    r.update(plan_binding_sha256=p,plan_path=path.relative_to(root).as_posix(),plan_file_sha256=m.digest(path),adapter_source_sha256=m.digest(root/'code/full_ssb_local_model.py'),
        stage='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI')
    r['inputs'].update(gate)
    original=root/m.source.NATIVE_REPORT;original.parent.mkdir(parents=True,exist_ok=True);original.write_bytes((ROOT/m.source.NATIVE_REPORT).read_bytes());r['original_mismatch']=m.artifact(original,root)
    monkeypatch.setattr(m.source,'environment_artifacts',lambda *a,**k:[])
    m.base.formal_transaction(run/'formal_control',m.formal_binding(r),lambda:r,lambda report:m.stage_artifacts(report,root),kind='LOCAL_FORMAL')
    if publish:m.publish_local_model(r,root)
    return r


def test_local_publication_exact_inventory_and_default_missing_real_source_refusal(tmp_path_factory,monkeypatch):
    root=tmp_path_factory.mktemp('l');m=module();r=synthetic_publication(m,root,monkeypatch)
    before={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    records=m.verify_local_publication(r,root)
    assert len(records)>80 and len(records)==len({x['path'] for x in records})
    assert before=={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    with pytest.raises((ValueError,OSError)):m.verify_local_formal(root)


@pytest.mark.parametrize('damage',['omit','local_code','formal_running'])
def test_local_publication_rejects_resealed_subset_or_changed_source(tmp_path_factory,monkeypatch,damage):
    root=tmp_path_factory.mktemp('l');m=module();r=synthetic_publication(m,root,monkeypatch);run=Path(r['directory'])
    if damage=='local_code':(root/'code/full_ssb_local_model.py').write_bytes(b'changed local model source')
    elif damage=='formal_running':m.atomic(run/'formal_control/lifecycle.json',{'status':'RUNNING'})
    else:
        path=run/'verification_seal.json';seal=m.read(path);seal['artifacts']=seal['artifacts'][1:];m.atomic(path,seal)
    with pytest.raises((ValueError,OSError,KeyError)):m.verify_local_publication(r,root)


def test_local_publication_failure_taints_whole_formal(tmp_path_factory,monkeypatch):
    root=tmp_path_factory.mktemp('l');m=module();r=synthetic_publication(m,root,monkeypatch,publish=False)
    def fail(*a):raise OSError('synthetic disk failure')
    monkeypatch.setattr(m,'write_local_publication',fail)
    with pytest.raises(OSError):m.publish_local_model(r,root)
    assert m.read(Path(r['directory'])/'formal_control/lifecycle.json')['status']=='TAINTED'
