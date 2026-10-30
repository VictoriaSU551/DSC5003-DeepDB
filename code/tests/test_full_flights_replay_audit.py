"""Fail-closed posthoc parser binding without revising frozen model inference."""
import copy
import importlib
from pathlib import Path
import pytest


def implementation():
    try:return importlib.import_module('full_flights_replay_audit')
    except ModuleNotFoundError:pytest.fail('Independent posthoc parser audit is missing')


def package(tmp_path):
    path=tmp_path/'sqlparse';path.mkdir()
    (path/'__init__.py').write_text('version=1\n')
    (path/'lexer.py').write_text('value=100\n')
    return path


@pytest.mark.parametrize('mutation',['same_size','added','deleted'])
def test_current_parser_source_inventory_rejects_same_size_tamper_added_or_missing_python(tmp_path,mutation):
    m=implementation();root=package(tmp_path);expected=m.package_snapshot(root,'0.3.1','0.3.1')
    if mutation=='same_size':(root/'lexer.py').write_text('value=200\n')
    if mutation=='added':(root/'extra.py').write_text('x=1\n')
    if mutation=='deleted':(root/'lexer.py').unlink()
    with pytest.raises(ValueError):m.require_package(expected,m.package_snapshot(root,'0.3.1','0.3.1'))


def test_empty_duplicate_or_case_alias_parser_sources_are_rejected(tmp_path):
    m=implementation();root=package(tmp_path);binding=m.package_snapshot(root,'0.3.1','0.3.1')
    for records in [[],binding['python_sources']+[binding['python_sources'][0]],
                    binding['python_sources']+[dict(binding['python_sources'][0],path=binding['python_sources'][0]['path'].upper())]]:
        with pytest.raises(ValueError):m.validate_source_set(records,root)
    (root/'__init__.py').unlink();(root/'lexer.py').unlink()
    with pytest.raises(ValueError):m.package_snapshot(root,'0.3.1','0.3.1')


@pytest.mark.parametrize('distribution,module',[('',''),('0.3.1','0.4.0'),(None,'0.3.1')])
def test_distribution_and_loaded_module_versions_must_be_nonempty_equal(tmp_path,distribution,module):
    m=implementation();root=package(tmp_path)
    with pytest.raises(ValueError):m.package_snapshot(root,distribution,module)


def test_outer_source_tamper_is_rejected_without_changing_frozen_sources(tmp_path):
    m=implementation();source=tmp_path/'audit.py';source.write_text('gate=1\n')
    asset=m.legacy.record(source,tmp_path)
    m.validate_source_set([asset],tmp_path)
    source.write_text('gate=2\n')
    with pytest.raises(ValueError):m.validate_source_set([asset],tmp_path)


def test_verify_missing_receipt_is_readonly_and_never_builds_or_calls_old_audit(tmp_path,monkeypatch):
    m=implementation();missing=tmp_path/'absent';monkeypatch.setattr(m,'OUT',missing)
    def forbidden():pytest.fail('Missing evidence must not be rebuilt or delegated')
    monkeypatch.setattr(m,'checked_legacy_audit',forbidden)
    with pytest.raises(FileNotFoundError):m.verify()
    assert not missing.exists()


def test_peer_records_support_current_matching_only_not_historical_flights_claim(tmp_path):
    m=implementation();root=package(tmp_path);current=m.package_snapshot(root,'0.3.1','0.3.1')
    canonical={'versions':{'sqlparse':'0.3.1'}}
    ssb={'versions':{'sqlparse':'0.3.1'},'sqlparse_sources':{r['path']:r['sha256'] for r in current['python_sources']}}
    result=m.compare_peer_dependencies(current,canonical,ssb)
    assert result['canonical']=='VERSION_ONLY_SOURCE_SET_NOT_RECORDED'
    assert result['ssb']=='CURRENT_VERSION_AND_COMPLETE_PYTHON_SOURCES_MATCH'
    assert result['proves_historical_flights_parser'] is False
    changed=copy.deepcopy(ssb);changed['sqlparse_sources'].pop(next(iter(changed['sqlparse_sources'])))
    with pytest.raises(ValueError):m.compare_peer_dependencies(current,canonical,changed)


def test_verify_valid_fixture_preserves_legacy_fields_and_writes_nothing(tmp_path,monkeypatch):
    m=implementation();out=tmp_path/'audit';out.mkdir();source=tmp_path/'outer.py';source.write_text('audit=1\n')
    current={'scope':'CURRENT_POSTHOC_NOT_HISTORICAL_PARSER_PROOF','sqlparse':m.package_snapshot(package(tmp_path),'0.3.1','0.3.1')}
    old=dict(status='PASS_READ_ONLY_FLIGHTS_REVERSE_AUDIT',verification={'path':'formal.json','sha256':'old'},
             maximum_relative_difference=0.,successful_prior_calls=24,queries=12,groups=331,actual_new_predictions=0)
    receipt=m.legacy.seal(dict(status=m.RECEIPT_STATUS,current_binding=current,legacy_audit_result=old))
    m.legacy.write_json(out/'verification.json',receipt)
    final=m.legacy.seal(dict(status=m.FINAL_STATUS,sources=[m.legacy.record(source,tmp_path)],
        artifacts=[m.legacy.record(out/'verification.json',out)]))
    m.legacy.write_json(out/'final_seal.json',final)
    monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'OUT',out)
    monkeypatch.setattr(m,'current_binding',lambda:current)
    monkeypatch.setattr(m,'checked_legacy_audit',lambda:old)
    before={p:p.read_bytes() for p in out.rglob('*') if p.is_file()}
    result=m.verify()
    assert result['verification']==old['verification'] and result['successful_prior_calls']==24
    assert result['parser_binding_status']=='PASS_CURRENT_POSTHOC_PARSER_BINDING'
    assert result['parser_bound_during_original_inference'] is False
    assert before=={p:p.read_bytes() for p in out.rglob('*') if p.is_file()}
    (out/'unexpected.json').write_text('{}')
    with pytest.raises(ValueError):m.verify()
