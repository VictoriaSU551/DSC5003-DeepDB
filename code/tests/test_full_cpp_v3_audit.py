"""The audit accepts stored evidence only and fails closed without it."""
import importlib
import pytest

def implementation():
    try:return importlib.import_module('full_cpp_v3_audit')
    except ModuleNotFoundError:pytest.fail('Read-only native v3 audit entry is missing')

def test_snapshot_map_must_be_exact_nonempty_and_cannot_hide_added_files(tmp_path):
    m=implementation();(tmp_path/'old.txt').write_text('old');seal=tmp_path/'final_current_seal.json'
    seal.write_text('{}')
    m.require_snapshot_map([{'path':'old.txt'}],tmp_path,seal)
    for assets in [[],[{'path':'missing.txt'}],[{'path':'old.txt'},{'path':'old.txt'}]]:
        with pytest.raises(ValueError):m.require_snapshot_map(assets,tmp_path,seal)
    (tmp_path/'extra.txt').write_text('extra')
    with pytest.raises(ValueError):m.require_snapshot_map([{'path':'old.txt'}],tmp_path,seal)

def test_triplet_audit_uses_fresh_csv_reference_and_complete_wall():
    m=implementation();row=dict(python_prediction=3.,cpp_prediction=3.,v3_csv_prediction=3.,
        generated_spn_calls=1,native_call_map={'spn0':1},cpp_physical_native_ns=1000,
        cpp_physical_native_ms=.001,upstream_stats_calls=0,upstream_omitted_calls=1)
    m.audit_row(row,3.)
    for changes,reference in [({},4.),({'native_call_map':{'spn99':1}},3.),
                              ({'upstream_omitted_calls':0},3.)]:
        with pytest.raises(ValueError):m.audit_row(dict(row,**changes),reference)

def test_missing_final_seal_fails_without_constructing_a_worker(tmp_path,monkeypatch):
    m=implementation()
    monkeypatch.setattr(m.runner,'OUT',tmp_path)
    def forbidden(*args,**kwargs):pytest.fail('Read-only audit attempted inference')
    monkeypatch.setattr(m.runner,'worker',forbidden)
    monkeypatch.setattr(m.runner,'run_guarded',forbidden)
    with pytest.raises(FileNotFoundError):m.audit()
