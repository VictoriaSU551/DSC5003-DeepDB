"""10M phase pure contracts; real scientific golden is a separate root command."""
import ast
import importlib.util
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_ssb_local_ci.py';assert path.exists(),'10M local adapter missing'
    s=importlib.util.spec_from_file_location('local_ci_test',str(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


@pytest.mark.parametrize('damage',[None,'missing','double','science'])
def test_cap_patch_is_exactly_one_known_comparison_and_no_other_scientific_edit(damage):
    m=module();raw=m.original_training_source()
    if damage=='missing':raw=raw.replace('100<=sample_cap<=1000000','100<=sample_cap<=999999')
    elif damage=='double':raw+='\n# 100<=sample_cap<=1000000\n'
    elif damage=='science':raw=raw.replace('rdc_threshold=.3','rdc_threshold=.15')
    if damage is None:
        changed,binding=m.adapt_training_source(raw)
        assert changed==raw.replace('100<=sample_cap<=1000000','100<=sample_cap<=10000000')
        assert binding['original_source_sha256']!=binding['adapted_source_sha256'] and binding['replacement_count']==1
        assert set(binding)>={'frozen_core_sha256','adapter_source_sha256','original_source_sha256','adapted_source_sha256','replacement_count'}
    else:
        with pytest.raises(ValueError):m.adapt_training_source(raw)


def test_runtime_training_adapter_restores_original_even_on_exception(monkeypatch):
    m=module();monkeypatch.setenv('DEEPDB_SSB_LOCAL_CI_WORKER','1')
    core=SimpleNamespace(train_single_models=lambda:None)
    original=core.train_single_models
    with pytest.raises(RuntimeError):
        with m.runtime_cap_adapter(core,namespace={}) as binding:
            assert core.train_single_models is not original
            tree=ast.parse(m.adapt_training_source(m.original_training_source())[0]);condition=next(n for n in tree.body[0].body if isinstance(n,ast.If))
            guard=compile(ast.Module(body=[condition],type_ignores=[]),'<pure-cap>','exec')
            exec(guard,{'sample_cap':10000000})
            with pytest.raises(ValueError):exec(guard,{'sample_cap':10000001})
            raise RuntimeError('synthetic interrupted guard')
    assert core.train_single_models is original


def test_runtime_adapter_requires_fresh_dedicated_ci_worker(monkeypatch):
    m=module();monkeypatch.delenv('DEEPDB_SSB_LOCAL_CI_WORKER',raising=False)
    with pytest.raises(ValueError,match='fresh'):
        with m.runtime_cap_adapter(SimpleNamespace(train_single_models=None)):pass


def test_ci_missing_publication_readonly_creates_nothing(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='missing'):m.verify_local_ci(tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_cap_actual_rows_and_phase_cannot_claim_author_or_exact10m_fact():
    m=module();assert m.EXPECTED_ROWS=={'lineorder':9996946,'dwdate':2556,'customer':10000000,'part':1800000,'supplier':1000000}
    assert m.SCOPE=='LOCAL_SSB_10M_CI' and m.PARAMETERS['samples_per_spn']==10000000
    assert m.OPERATIONAL_RESERVE_BYTES==2*2**30+64*2**20 and m.MINIMUM_LAUNCH_MEMORY_BYTES==7*2**30
    assert m.BUDGET_METADATA==dict(paper_figure11_training_budget_policy_applied=True,exact10000000_fact_training_rows_claimed=False)


def test_scientific_golden_and_formal_require_explicit_review_and_resource_release(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='review|memory'):m.run_golden('0'*64,memory_approved=False)
    with pytest.raises(ValueError,match='review|memory'):m.execute_formal({},memory_approved=False)


@pytest.mark.parametrize('damage',['missing','with_errors','cap','reverse','rows','gap'])
def test_ci_requires_complete_successful1m_formal_and_reverse_lineage(monkeypatch,tmp_path,damage):
    m=module()
    if damage=='missing':
        with pytest.raises((ValueError,OSError)):m.collect_lineage(tmp_path)
        assert list(tmp_path.iterdir())==[];return
    formal={'status':m.previous.API_PASS,'sample_rows':9996946,'population_rows':m.source.N,'scope':m.source.SCOPE,
        'author_different_groups':1713,'author_reproduction_complete':False,'full_paper_reproduction_complete':False,
        'report':{'plan':{'model':dict(m.previous.MODEL)}}}
    reverse={'status':'PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH','scope':m.source.SCOPE,'author_different_groups':1713,
        'author_reproduction_complete':False,'full_paper_reproduction_complete':False}
    if damage=='with_errors':formal['status']+='_WITH_ERRORS'
    elif damage=='cap':formal['report']['plan']['model']['samples_per_spn']=10000000
    elif damage=='reverse':reverse['status']='RUNNING'
    elif damage=='rows':formal['sample_rows']=10000000
    else:reverse['author_different_groups']=0
    with pytest.raises(ValueError):m.validate_lineage_headers(formal,reverse)


def synthetic_publication(m,root,monkeypatch,publish=True):
    import test_full_ssb_local_stage_validation as fixtures
    stages=fixtures.module();ci,r=fixtures.fixture(stages,root,source_sha=m.SOURCE_RECEIPT_SHA)
    r.update(kind='FORMAL',stage=m.STAGE,training_cap_per_table=10000000,actual_training_rows_per_table=m.EXPECTED_ROWS,
        lineage={'parent_formal':{'path':'old-formal','bytes':1,'sha256':'a'*64},'parent_reverse':{'path':'old-reverse','bytes':1,'sha256':'b'*64},'artifacts':[]},
        runtime_cap=m.adapt_training_source(m.original_training_source())[1],validation_binding=stages.binding(m.validation_config()),adapter_source_sha256=m.digest(m.__file__))
    r['lineage'].update({key:r[key] for key in ('prepared_directory','moments_directory','moments_helper_directory','truth_projection_path')})
    r['lineage']['inputs_sha256']=m.value_hash(r['inputs'])
    r['plan'].update(kind='FORMAL',scope=m.SCOPE,model=m.PARAMETERS,source_receipt_sha256=m.SOURCE_RECEIPT_SHA)
    r['source_receipt_sha256']=m.SOURCE_RECEIPT_SHA
    # Fake files test only publication controls; real dependency/prerequisite
    # APIs remain mandatory and reject this fixture from public success.
    p=m.value_hash(r['plan']);path=root/m.OUTPUT/'plans'/p[:20]/'plan.json';m.atomic(path,r['plan']);m.atomic(path.with_suffix('.seal.json'),{'sha256':m.digest(path)})
    r.update(plan_binding_sha256=p,plan_path=path.relative_to(root).as_posix(),plan_file_sha256=m.digest(path))
    monkeypatch.setattr(m,'dependency_artifacts',lambda *a,**k:[])
    m.base.formal_transaction(Path(r['directory'])/'formal_control',m.formal_binding(r),lambda:r,lambda x:stages.validate(x,m.validation_config(),root),kind='LOCAL_CI_FORMAL')
    if publish:m.publish(r,root)
    return r


def test_ci_publication_control_seals_full_stages_and_default_rejects_fake_parent(tmp_path_factory,monkeypatch):
    m=module();root=tmp_path_factory.mktemp('ci');r=synthetic_publication(m,root,monkeypatch)
    before={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    assert len(m.verify_publication(r,root))>60
    assert before=={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    with pytest.raises((ValueError,OSError)):m.verify_local_ci(root)


@pytest.mark.parametrize('damage',['subset','formal_running','writer'])
def test_ci_publication_subset_rejection_or_failure_taints_own_formal(tmp_path_factory,monkeypatch,damage):
    m=module();root=tmp_path_factory.mktemp('ci');r=synthetic_publication(m,root,monkeypatch,publish=damage!='writer');run=Path(r['directory'])
    if damage=='writer':
        def fail(*a,**k):raise OSError('synthetic write failure')
        monkeypatch.setattr(m,'write_publication',fail)
        with pytest.raises(OSError):m.publish(r,root)
        assert m.read(run/'formal_control/lifecycle.json')['status']=='TAINTED'
    else:
        path=run/('verification_seal.json' if damage=='subset' else 'formal_control/lifecycle.json');body=m.read(path)
        if damage=='subset':body['artifacts']=body['artifacts'][1:]
        else:body['status']='RUNNING'
        m.atomic(path,body)
        with pytest.raises(ValueError):m.verify_publication(r,root)


@pytest.mark.parametrize('damage',[None,'subset','matrix','structure','numpy','python'])
def test_golden_comparison_requires_all5_matrices_nodes_and_both_rng_streams(damage):
    m=module();names=['lineorder','dwdate','customer','part','supplier']
    expected={t:dict(table=t,sample_matrix_sha256='a'*64,structure_sha256='b'*64,numpy_rng_sha256='c'*64,python_rng_sha256='d'*64) for t in names}
    import copy
    actual=copy.deepcopy(expected)
    if damage=='subset':actual.pop('supplier')
    elif damage is not None:actual['lineorder'][{'matrix':'sample_matrix_sha256','structure':'structure_sha256','numpy':'numpy_rng_sha256','python':'python_rng_sha256'}[damage]]='f'*64
    if damage is None:assert len(m.compare_golden(expected,actual))==5
    else:
        with pytest.raises(ValueError):m.compare_golden(expected,actual)


def test_missing_golden_readonly_never_creates_or_fits(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='missing'):m.verify_golden(tmp_path)
    assert list(tmp_path.iterdir())==[]


@pytest.mark.skipif(os.name!='nt',reason='native Windows fingerprint')
def test_native_platform_boundary_forbids_os_subprocess_and_restores_cache(monkeypatch):
    import subprocess,platform
    m=module();old=(platform._syscmd_ver,platform._uname_cache,platform._platform_cache)
    def forbid(*a,**k):pytest.fail('read-only OS fingerprint must not fork')
    monkeypatch.setattr(subprocess,'Popen',forbid);monkeypatch.setattr(subprocess,'check_output',forbid)
    with m.native_platform() as proof:
        assert proof['helper_sha256']==m.WINDOWS_HELPER_SHA and proof['subprocess_executed'] is False
        assert platform.platform()==proof['platform'] and platform.machine()==proof['machine']
    assert old==(platform._syscmd_ver,platform._uname_cache,platform._platform_cache)


@pytest.mark.parametrize('damage',[None,'inputs','prepared_directory','moments_directory','moments_helper_directory','truth_projection_path'])
def test_formal_reuse_cannot_substitute_unrelated_prepared_moments_or_truth(damage):
    m=module();inputs={'receipt_sha256':m.SOURCE_RECEIPT_SHA,'canonical_truth':['local-only']};lineage={'inputs_sha256':m.value_hash(inputs)}
    lineage.update({key:'bound-original/'+key for key in ('prepared_directory','moments_directory','moments_helper_directory','truth_projection_path')})
    r=dict(lineage,lineage=lineage,inputs=inputs,source_receipt_sha256=m.SOURCE_RECEIPT_SHA)
    if damage is not None:r[damage]={'fake':'replacement'} if damage=='inputs' else 'a/different/file'
    if damage is None:m.validate_reuse(r)
    else:
        with pytest.raises(ValueError):m.validate_reuse(r)


@pytest.mark.parametrize('damage',[None,'foreign','changed'])
def test_optional_ci_inference_sources_must_equal_explicit_root_frozen_pins(damage):
    m=module();pins=dict(m.INFERENCE_PINS)
    if damage=='foreign':pins['code/full_ssb_local_replay.py']='a'*64
    elif damage=='changed':pins['code/full_ssb_scoped_replay.py']='b'*64
    if damage is None:assert m.validate_auxiliary_sources(pins)==pins and m.validate_auxiliary_sources({})=={}
    else:
        with pytest.raises(ValueError):m.validate_auxiliary_sources(pins)
