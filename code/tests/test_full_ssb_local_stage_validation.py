"""Configurable validation capsule; only fake files, no load/fit/inference."""
import copy
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_ssb_local_stage_validation.py';assert path.exists(),'configurable validation module missing'
    s=importlib.util.spec_from_file_location('local_stage_test',str(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def ci_module():
    import full_ssb_local_ci as ci
    return ci


def fixture(m,root,source_sha='a'*64):
    import test_full_ssb_local_model as fixtures
    ci=ci_module();old=fixtures.module();r=fixtures.synthetic_stages(old,root,source_sha=source_sha)
    before=Path(r['directory']);run=root/ci.OUTPUT/'runs/synthetic';run.mkdir(parents=True)
    # A labelled fake predecessor owns prepared/moments/truth. New model and
    # queries are relocated into the new namespace, independently of reuse.
    import shutil
    for name in ('model','evaluation'):
        shutil.move(str(before/name),str(run/name))
        guard=old.base.stage_home(before/name,name)
        shutil.move(str(guard),str(old.base.stage_home(run/name,name)))
    r.update(directory=str(run),prepared_directory=str(before/'prepared'),moments_directory=str(before/'sample_moments_native'),
        moments_helper_directory=str(root/old.OUTPUT/'runtime/native'),truth_projection_path=str(before/'core_truth_checkpoint.json'),
        scope=ci.SCOPE,status=ci.PASS,author_population_row_count_and_13_truths_match=False,author_full_row_byte_identity_proven=False,
        model_path=str(run/'model/ensemble_single.pkl'),evaluation_directory=str(run/'evaluation/cache'))
    r['evaluation_directory']=str(next((run/'evaluation').glob('*')))
    # Actual frame rows, complete frozen core model guard and outer receipts.
    model=r['model'];model['model_path']=r['model_path'];model['binding']['samples_per_spn']=10000000
    for row in model['training_tables']:row['actual_training_rows']=ci.EXPECTED_ROWS[row['table']]
    directory=run/'model'
    for table in old.base.TABLES:
        p=directory/(table+'.json');b=old.read(p);b['training']=next(v for v in model['training_tables'] if v['table']==table);b['binding']=model['binding'];old.atomic(p,b)
    old.atomic(directory/'model.json',model)
    mg=old.read(directory/'model_guard.json');mg['binding']['model_stage']=model['binding'];old.atomic(directory/'input_guard.json',{'binding':mg['binding']})
    mg['model_files_sha256']={n:old.digest(directory/n) for n in mg['model_files_sha256']};old.atomic(directory/'model_guard.json',mg)
    home=old.base.stage_home(directory,'model');rec=old.read(home/'receipt.json');rec['result']=model;old.atomic(home/'receipt.json',rec)
    life=old.read(home/'lifecycle.json');life['receipt_sha256']=old.digest(home/'receipt.json');old.atomic(home/'lifecycle.json',life)
    eb=r['evaluation_binding'];eb['model_input_artifact_guard_sha256']=old.digest(directory/'model_guard.json')
    r['evaluation']['directory']=r['evaluation_directory']
    for q,identity in zip(r['queries'],r['evaluation']['identities']):
        p=Path(r['evaluation_directory'])/('query_%02d.json'%q['query_no']);old.atomic(p.with_suffix('.seal.json'),{'binding':eb,'sha256':old.digest(p)})
        identity.update(global_binding=eb,core_seal_sha256=old.digest(p.with_suffix('.seal.json')))
    h=old.base.stage_home(run/'evaluation','evaluation');b=old.read(h/'receipt.json');b['result']=r['evaluation'];b['binding']['model_outer_receipt_sha256']=old.digest(home/'receipt.json');old.atomic(h/'receipt.json',b)
    l=old.read(h/'lifecycle.json');l.update(binding=b['binding'],receipt_sha256=old.digest(h/'receipt.json'));old.atomic(h/'lifecycle.json',l)
    return ci,r


def test_configurable_capsule_binds_exact_validation_source_and_its_configuration():
    m=module();ci=ci_module();binding=m.binding(ci.validation_config())
    assert binding['frozen_validation_module_sha256']==ci.PRIOR_PINS['code/full_ssb_local_model.py']
    assert binding['source_sha256']!=binding['configured_source_sha256'] and binding['configuration']==ci.validation_config()


def test_reused_prepared_moments_with_new10m_model_and_complete26queries(tmp_path_factory):
    m=module();root=tmp_path_factory.mktemp('cv');ci,r=fixture(m,root)
    items=m.validate(r,ci.validation_config(),root)
    assert sum('/query_' in x['path'] for x in items)==26 and any('/local_sf500_models/' in x['path'] and '/prepared/' in x['path'] for x in items)


@pytest.mark.parametrize('damage',['wrong_cap','wrong_rows','author_scope','truth_rewrite','query_subset','prepared_alias'])
def test_configurable_validation_rejects_wrong_phase_or_incomplete_reuse(tmp_path_factory,damage):
    m=module();root=tmp_path_factory.mktemp('cv');ci,r=fixture(m,root)
    if damage=='wrong_cap':r['model']['binding']['samples_per_spn']=1000000
    elif damage=='wrong_rows':r['training_tables'][0]['actual_training_rows']=10000000
    elif damage=='author_scope':r['scope']='SSB_AUTHOR'
    elif damage=='truth_rewrite':r['queries'][6]['groups'][0]['truth']-=1
    elif damage=='query_subset':r['queries']=r['queries'][:12]
    else:r['prepared_directory']=str(Path(r['directory'])/'prepared')
    with pytest.raises((ValueError,OSError,KeyError)):m.validate(r,ci.validation_config(),root)
