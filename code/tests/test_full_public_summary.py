import json

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
