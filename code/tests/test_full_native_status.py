import json
import sys
from types import SimpleNamespace

import pytest

import full_native_status as status


def write(root, name, body):
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def test_progress_is_never_an_author_acceptance(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    write(tmp_path, 'ssb/native_v2/formal500/stream/checkpoint.json',
          dict(rows=8000000, sample_rows=26000, next_shard=10))
    stage = status.generation_stage()
    assert stage['status'] == 'PARTIAL_CHECKPOINT'
    assert stage['generated_rows'] == 8000000
    assert stage['committed_shards'] == 10


def test_final_pass_label_alone_cannot_certify_numeric_or_metadata_closure(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    write(tmp_path, 'results/ssb_native_v2.json', dict(status='PASS_AUTHOR_TRUTHS'))
    def reject(**kwargs):
        raise ValueError('missing physical stream lifecycle')
    monkeypatch.setitem(sys.modules, 'full_ssb_native_model', SimpleNamespace(verify_generation=reject))
    assert status.generation_stage()['status'] == 'EVIDENCE_INVALID'


def test_mismatch_does_not_import_bridge_or_promote_historical_run(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    monkeypatch.setitem(sys.modules, 'full_ssb_native_model', None)
    write(tmp_path, 'results/ssb_native_v2.json', dict(status='MISMATCH'))
    assert status.generation_stage()['status'] == 'FAILED_AUTHOR_POPULATION_GATE'


def test_generation_acceptance_retains_row_identity_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    write(tmp_path, 'results/ssb_native_v2.json', dict(status='PASS_AUTHOR_TRUTHS'))
    calls = []
    def accept(**kwargs):
        calls.append(kwargs)
        return dict(population_rows=3000028242, sample_rows=9999000, truth_groups=2059)
    monkeypatch.setitem(sys.modules, 'full_ssb_native_model', SimpleNamespace(verify_generation=accept))
    stage = status.generation_stage()
    assert stage['status'] == 'PASS_AUTHOR_ROWS_AND_13_TRUTHS_WITH_PHYSICAL_CLOSURE'
    assert stage['author_full_row_byte_identity_proven'] is False
    assert len(calls) == 1 and len(calls[0]['expected_receipt_sha256']) == 64


def test_native_formal_file_without_replay_stays_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    assert status.model_stages()[0]['status'] == 'PENDING'
    write(tmp_path, 'results/ssb_native_v2_model_aqp_ci.json', dict(status='PASS'))
    model, ci = status.model_stages()
    assert model['status'] == ci['status'] == 'FORMAL_COMPLETE_REPLAY_PENDING'


@pytest.mark.parametrize('bad', ['wrong_status', 'wrong_report'])
def test_wrong_replay_identity_fails(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    path = tmp_path/'results/ssb_native_v2_model_aqp_ci.json'
    write(tmp_path, 'results/ssb_native_v2_model_aqp_ci.json', dict(status='PASS'))
    write(tmp_path, 'ssb/native_v2_replay/verification.json', {})
    accepted = dict(status='wrong' if bad == 'wrong_status' else 'PASS_NATIVE_V2_INDEPENDENT_REVERSE_REPLAY',
        source_snapshot=dict(published_result=dict(sha256='0'*64)))
    monkeypatch.setitem(sys.modules, 'full_ssb_native_replay', SimpleNamespace(verify=lambda: accepted))
    model, ci = status.model_stages()
    assert model['status'] == ci['status'] == 'EVIDENCE_INVALID'


def test_replay_group_and_ci_gaps_survive_status_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    write(tmp_path, 'results/ssb_native_v2_model_aqp_ci.json', dict(status='PASS'))
    path = tmp_path/'results/ssb_native_v2_model_aqp_ci.json'
    write(tmp_path, 'ssb/native_v2_replay/verification.json', {})
    coverage = dict(missing_model_groups_total=1, extra_model_groups_total=0,
        nonfinite_point_groups=0, nonfinite_original_ci_groups=0,
        missing_or_nonfinite_model_interval_groups=0,
        reference_ci_eligible_truth_groups=2000, reference_ci_excluded_truth_groups=59)
    accepted = dict(status='PASS_NATIVE_V2_INDEPENDENT_REVERSE_REPLAY',
        source_snapshot=dict(published_result=dict(sha256=status.file_sha256(path)),
                             population_rows=3000028242, sample_rows=9999000), coverage=coverage)
    monkeypatch.setitem(sys.modules, 'full_ssb_native_replay', SimpleNamespace(verify=lambda: accepted))
    model, ci = status.model_stages()
    assert model['status'] == 'PASS_REPLAY_WITH_GROUP_GAPS'
    assert ci['status'] == 'PASS_REPLAY_WITH_CI_GAPS'
    assert ci['excluded_truth_groups'] == 59
