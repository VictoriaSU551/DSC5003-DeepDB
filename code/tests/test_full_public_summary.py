import json
from pathlib import Path

import pytest

import full_public_summary as export


def bundle(tmp_path, monkeypatch, artifacts=None):
    monkeypatch.setattr(export, 'ROOT', tmp_path)
    source = tmp_path / 'output/full/figures/example'
    source.mkdir(parents=True)
    (source / 'table1.csv').write_text('method,median\nlocal,1.5\n')
    records = [export.record(source / 'table1.csv')] if artifacts is None else artifacts
    manifest = source / 'manifest.json'
    manifest.write_text(json.dumps({'full_paper_complete': False, 'artifacts': records}))
    pointer = tmp_path / 'pointer.json'
    pointer.write_text(json.dumps({'path': source.relative_to(tmp_path).as_posix(),
                                  'manifest_sha256': export.file_sha256(manifest)}))
    return pointer, source


def test_only_explicit_derived_files_are_exported(tmp_path, monkeypatch):
    pointer, source = bundle(tmp_path, monkeypatch)
    (source / 'model.pkl').write_bytes(b'private model')
    selected, evidence = export.checked_bundle(pointer, ['table1.csv'])
    assert [p.name for p in selected] == ['table1.csv']
    assert evidence['manifest']['path'].startswith('output/full/')
    assert ':' not in evidence['manifest']['path']


@pytest.mark.parametrize('mode', ['empty', 'duplicate', 'tampered', 'escape', 'unsealed'])
def test_invalid_bundle_fails_closed(tmp_path, monkeypatch, mode):
    pointer, source = bundle(tmp_path, monkeypatch)
    manifest = source / 'manifest.json'
    data = json.loads(manifest.read_text())
    if mode == 'empty': data['artifacts'] = []
    if mode == 'duplicate': data['artifacts'] *= 2
    if mode == 'escape': data['artifacts'][0]['path'] = '../outside.csv'
    if mode == 'unsealed': data['artifacts'][0]['path'] = 'other.csv'
    if mode != 'tampered':
        manifest.write_text(json.dumps(data))
        p = json.loads(pointer.read_text()); p['manifest_sha256'] = export.file_sha256(manifest)
        pointer.write_text(json.dumps(p))
    else:
        (source / 'table1.csv').write_text('changed')
    with pytest.raises((ValueError, OSError)):
        export.checked_bundle(pointer, ['table1.csv'])


def test_model_and_raw_extension_cannot_be_selected(tmp_path, monkeypatch):
    pointer, _ = bundle(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='derived CSV or PNG'):
        export.checked_bundle(pointer, ['model.pkl'])


def test_different_strings_cannot_alias_one_physical_artifact(tmp_path, monkeypatch):
    pointer, source = bundle(tmp_path, monkeypatch)
    manifest = source / 'manifest.json'
    data = json.loads(manifest.read_text())
    alias = dict(data['artifacts'][0])
    alias['path'] = alias['path'].replace('/table1.csv', '/./table1.csv')
    data['artifacts'].append(alias); manifest.write_text(json.dumps(data))
    p = json.loads(pointer.read_text()); p['manifest_sha256'] = export.file_sha256(manifest)
    pointer.write_text(json.dumps(p))
    with pytest.raises(ValueError, match='physical artifact'):
        export.checked_bundle(pointer, ['table1.csv'])


def test_nested_sweep_statuses_survive_without_publishing_diagnostic_paths():
    stages = {'sweep': {'1000': {'status':'PASS', 'queries':753}},
              'failed': {'status':'EVIDENCE_INVALID', 'reason':'C:/Users/private/file'}}
    rows = export.coverage_rows(stages)
    assert rows['sweep/1000'] == {'status':'PASS', 'queries':753}
    assert rows['failed'] == {'status':'EVIDENCE_INVALID'}


@pytest.mark.parametrize('field,value',[('scope','AUTHOR_SSB_SF500'),
    ('author_reproduction_complete',True),('author_different_groups',0)])
def test_local_bundle_cannot_drop_or_promote_author_mismatch(tmp_path,monkeypatch,field,value):
    old,source=bundle(tmp_path,monkeypatch)
    pointer=tmp_path/'ssb_local_sf500_tables_latest.json'
    pointer.write_bytes(old.read_bytes())
    manifest=source/'manifest.json';m=json.loads(manifest.read_text());p=json.loads(pointer.read_text())
    local=dict(scope='LOCAL_SSB_SF500',author_reproduction_complete=False,author_different_groups=1713,
        full_paper_complete=False,status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES')
    m.update(local);p.update(local);m[field]=value
    manifest.write_text(json.dumps(m));p['manifest_sha256']=export.file_sha256(manifest)
    pointer.write_text(json.dumps(p))
    with pytest.raises(ValueError):export.checked_bundle(pointer,['table1.csv'])


def test_local_bundle_is_optional_and_has_only_derived_outputs():
    assert 'ssb_local_sf500' in export.OPTIONAL_BUNDLES
    pointer,names=export.BUNDLES['ssb_local_sf500']
    assert pointer=='ssb_local_sf500_tables_latest.json' and len(names)==5
    assert all(Path(name).suffix in ('.csv','.png') for name in names)


@pytest.mark.parametrize('mutation',[None,'tainted','missing_status','pointer_complete'])
def test_local_export_requires_successful_derived_manifest_and_incomplete_pointer(tmp_path,monkeypatch,mutation):
    old,source=bundle(tmp_path,monkeypatch)
    pointer=tmp_path/'ssb_local_sf500_tables_latest.json'
    manifest=source/'manifest.json';m=json.loads(manifest.read_text());p=json.loads(old.read_text())
    local=dict(scope='LOCAL_SSB_SF500',author_reproduction_complete=False,
        author_different_groups=1713,full_paper_complete=False)
    m.update(local);p.update(local);m['status']='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES'
    if mutation=='tainted':m['status']='TAINTED'
    if mutation=='missing_status':m.pop('status')
    if mutation=='pointer_complete':p['full_paper_complete']=True
    manifest.write_text(json.dumps(m));p['manifest_sha256']=export.file_sha256(manifest)
    pointer.write_text(json.dumps(p))
    if mutation is None:
        paths,_=export.checked_bundle(pointer,['table1.csv'])
        assert paths==[source/'table1.csv']
    else:
        with pytest.raises(ValueError):export.checked_bundle(pointer,['table1.csv'])


@pytest.mark.parametrize('scope',['LOCAL_SSB_10M_CI','LOCAL_SSB_SF500','AUTHOR_SSB_SF500'])
def test_separate_ci_bundle_rejects_1m_or_author_scope(tmp_path,monkeypatch,scope):
    old,source=bundle(tmp_path,monkeypatch)
    pointer=tmp_path/'ssb_local_ci10m_tables_latest.json'
    manifest=source/'manifest.json';m=json.loads(manifest.read_text());p=json.loads(old.read_text())
    local=dict(scope=scope,author_reproduction_complete=False,author_different_groups=1713,
        full_paper_complete=False,status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES')
    m.update(local);p.update(local)
    m['binding_details']=dict(presentation=dict(evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'),
        readonly_acceptance=dict(evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',
            group_order_adapter_sha256='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'))
    manifest.write_text(json.dumps(m));p['manifest_sha256']=export.file_sha256(manifest)
    pointer.write_text(json.dumps(p))
    if scope=='LOCAL_SSB_10M_CI':
        assert export.checked_bundle(pointer,['table1.csv'])[0]==[source/'table1.csv']
    else:
        with pytest.raises(ValueError):export.checked_bundle(pointer,['table1.csv'])


@pytest.mark.parametrize('mutation',[None,'scope','variant','adapter','caption'])
def test_canonical_bundle_preserves_reviewed_evaluation_variant(tmp_path,monkeypatch,mutation):
    old,source=bundle(tmp_path,monkeypatch)
    pointer=tmp_path/'ssb_local_canonical_tables_latest.json'
    manifest=source/'manifest.json';m=json.loads(manifest.read_text());p=json.loads(old.read_text())
    local=dict(scope='LOCAL_SSB_SF500_CANONICAL_CI',author_reproduction_complete=False,author_different_groups=1713,
        full_paper_complete=False,status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES')
    m.update(local);p.update(local)
    variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
    m['binding_details']=dict(presentation=dict(evaluation_variant=variant),readonly_acceptance=dict(evaluation_variant=variant,
        group_order_adapter_sha256='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'))
    if mutation=='scope':m['scope']='LOCAL_SSB_SF500'
    if mutation=='variant':m['binding_details']['readonly_acceptance']['evaluation_variant']='OLD_SET_ORDER'
    if mutation=='adapter':m['binding_details']['readonly_acceptance']['group_order_adapter_sha256']='0'*64
    if mutation=='caption':m['binding_details']['presentation']['evaluation_variant']='OLD_SET_ORDER'
    manifest.write_text(json.dumps(m));p['manifest_sha256']=export.file_sha256(manifest)
    pointer.write_text(json.dumps(p))
    if mutation is None:
        assert export.checked_bundle(pointer,['table1.csv'])[0]==[source/'table1.csv']
        assert 'ssb_local_canonical' in export.OPTIONAL_BUNDLES
        assert export.BUNDLES['ssb_local_canonical'][0]==pointer.name
    else:
        with pytest.raises(ValueError):export.checked_bundle(pointer,['table1.csv'])


@pytest.mark.parametrize('damage',[None,'scope','protocol','adoption','reexecution','calls','readonly'])
def test_continuation_bundle_preserves_distinct_adoption_contract(tmp_path,monkeypatch,damage):
    old,source=bundle(tmp_path,monkeypatch)
    pointer=tmp_path/'ssb_local_continuation_tables_latest.json'
    manifest=source/'manifest.json';m=json.loads(manifest.read_text());p=json.loads(old.read_text())
    scope='LOCAL_SSB_SF500_CANONICAL_CONTINUATION'
    local=dict(scope=scope,author_reproduction_complete=False,author_different_groups=1713,
        full_paper_complete=False,status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES')
    m.update(local);p.update(local)
    variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
    protocol='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
    acceptance=dict(status='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH',
        scope=scope,evaluation_variant=variant,execution_protocol=protocol,
        group_order_adapter_sha256='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c',
        historical_reverse_accepted=False,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False,
        continuation_validation=dict(execution_protocol=protocol,adopted_forward=True,forward_reexecuted=False,
            phase_model_loads=dict(FORWARD=1,REVERSE=13),phase_evaluator_calls=dict(FORWARD=26,REVERSE=26)))
    m['binding_details']=dict(presentation=dict(evaluation_variant=variant),readonly_acceptance=acceptance)
    if damage=='scope':m['scope']='LOCAL_SSB_SF500_CANONICAL_CI'
    if damage=='protocol':acceptance['execution_protocol']='OLD_ROOT'
    if damage=='adoption':acceptance['continuation_validation']['adopted_forward']=False
    if damage=='reexecution':acceptance['continuation_validation']['forward_reexecuted']=True
    if damage=='calls':acceptance['continuation_validation']['phase_evaluator_calls']['REVERSE']=0
    if damage=='readonly':acceptance['inference_executed']=True
    manifest.write_text(json.dumps(m));p['manifest_sha256']=export.file_sha256(manifest);pointer.write_text(json.dumps(p))
    if damage is None:
        assert export.checked_bundle(pointer,['table1.csv'])[0]==[source/'table1.csv']
        assert 'ssb_local_continuation' in export.OPTIONAL_BUNDLES
        assert export.BUNDLES['ssb_local_continuation'][0]==pointer.name
    else:
        with pytest.raises(ValueError):export.checked_bundle(pointer,['table1.csv'])
