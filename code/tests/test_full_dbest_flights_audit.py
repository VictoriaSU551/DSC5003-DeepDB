"""The independent final auditor must reject vacuous or incomplete seals."""
import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize('mutation',['empty','missing','extra','alias'])
def test_manifest_requires_exact_nonempty_set(mutation):
    module=importlib.import_module('full_dbest_flights_audit')
    good={'a/file.json':'a'*64,'b/file.pkl':'b'*64}
    bad=dict(good)
    if mutation=='empty':bad={}
    elif mutation=='missing':bad.pop('a/file.json')
    elif mutation=='extra':bad['unexpected.json']='c'*64
    else:bad['a\\file.json']='a'*64
    with pytest.raises(ValueError):
        module.validate_manifest(bad,set(good),module.manifest_digest(good))


def test_duplicate_json_keys_are_rejected_before_mapping_collapses_them():
    module=importlib.import_module('full_dbest_flights_audit')
    with pytest.raises(ValueError,match='Duplicate'):
        module.strict_json('{"files_sha256":{"x":"a","x":"b"}}')


def test_physical_tamper_rejected_even_if_manifest_is_structurally_valid(tmp_path):
    module=importlib.import_module('full_dbest_flights_audit')
    source=tmp_path/'model.pkl';source.write_bytes(b'original')
    manifest={'model.pkl':hashlib.sha256(b'original').hexdigest()}
    module.verify_files(tmp_path,manifest)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):
        module.verify_files(tmp_path,manifest)


def test_changed_frozen_wrapper_rejected_before_partial_cache_access(tmp_path):
    module=importlib.import_module('full_dbest_flights_audit')
    source=tmp_path/'code/full_dbest_flights.py';source.parent.mkdir()
    source.write_text('# changed wrapper; partial cache must not be used\n')
    with pytest.raises(ValueError,match='wrapper'):
        module.assert_frozen_wrapper(tmp_path)


@pytest.mark.parametrize('key,value',[('population_rows',200000),('unique_fit_rows',19999),
                                    ('native_method_calls_total_verified',75)])
def test_semantics_cannot_downgrade_population_or_fit_or_native_calls(key,value):
    module=importlib.import_module('full_dbest_flights_audit')
    report=module.strict_json((module.ROOT/'output/full/dbest_flights/verification.json').read_text())
    bad=copy.deepcopy(report);bad[key]=value
    with pytest.raises(ValueError):module.validate_report(bad)


def test_finalized_real_one_billion_artifacts_pass_without_refit_or_integration():
    module=importlib.import_module('full_dbest_flights_audit')
    report=module.audit(write=False)
    assert report['status']=='PASS_WITH_GAPS'
    assert report['source_manifest_items']==256
    assert report['population_rows']==1000000000
    assert report['unique_fit_rows']==20000 and report['verified_native_calls']==76
    assert report['unsupported_query_count']==8
    assert report['original_files_unchanged']


def test_new_self_seal_cannot_authorize_an_empty_scientific_map(tmp_path,monkeypatch):
    module=importlib.import_module('full_dbest_flights_audit')
    # Even recomputing the new report's outer checksum cannot turn an empty map
    # into the independently pinned complete required artifact set.
    report=module.audit(write=False)
    report['files_sha256']={}
    path=tmp_path/'verification.json';module.atomic_json(path,report)
    module.atomic_json(tmp_path/'verification_seal.json',{
        'report_sha256':module.sha256(path),'audit_source_sha256':module.sha256(module.__file__),
        'source_manifest_sha256':module.SOURCE_MANIFEST_SHA256,
        'complete_inventory_sha256':module.COMPLETE_INVENTORY_SHA256,
        'required_source_artifacts':sorted(module.required_artifacts())})
    monkeypatch.setattr(module,'OUT',tmp_path)
    with pytest.raises(ValueError,match='physical/content mismatch'):module.verify()
