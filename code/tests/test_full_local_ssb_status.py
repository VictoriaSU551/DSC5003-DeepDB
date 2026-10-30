"""A local experiment may be accepted without ever promoting the author gate."""
import json
import sys
from types import SimpleNamespace
import pytest
import full_local_ssb_status as status


def write(root,name,body):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(body))


def test_local_formal_file_without_replay_stays_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    assert status.model_stages()[0]['status'] == 'PENDING'
    write(tmp_path, 'results/ssb_local_sf500_model_aqp_ci.json', dict(status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI'))
    model, ci = status.model_stages()
    assert model['status'] == ci['status'] == 'FORMAL_COMPLETE_REPLAY_PENDING'


@pytest.mark.parametrize('bad', ['wrong_status', 'wrong_report'])
def test_wrong_replay_identity_fails(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    path = tmp_path/'results/ssb_local_sf500_model_aqp_ci.json'
    write(tmp_path, 'results/ssb_local_sf500_model_aqp_ci.json', dict(status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI'))
    write(tmp_path, 'ssb/local_sf500_replay/verification.json', {})
    accepted = dict(scope='LOCAL_SSB_SF500',author_reproduction_complete=False,
        full_paper_reproduction_complete=False,author_different_groups=1713,status='wrong' if bad == 'wrong_status' else 'PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',
        source_snapshot=dict(published_result=dict(sha256='0'*64)))
    monkeypatch.setitem(sys.modules, 'full_ssb_local_replay', SimpleNamespace(verify=lambda: accepted))
    model, ci = status.model_stages()
    assert model['status'] == ci['status'] == 'EVIDENCE_INVALID'


def test_replay_group_and_ci_gaps_survive_status_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    write(tmp_path, 'results/ssb_local_sf500_model_aqp_ci.json', dict(status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI'))
    path = tmp_path/'results/ssb_local_sf500_model_aqp_ci.json'
    write(tmp_path, 'ssb/local_sf500_replay/verification.json', {})
    coverage = dict(missing_model_groups_total=1, extra_model_groups_total=0,
        nonfinite_point_groups=0, nonfinite_original_ci_groups=0,
        missing_or_nonfinite_model_interval_groups=0,
        reference_ci_eligible_truth_groups=2000, reference_ci_excluded_truth_groups=59)
    accepted = dict(scope='LOCAL_SSB_SF500',author_reproduction_complete=False,
        full_paper_reproduction_complete=False,author_different_groups=1713,status='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',
        source_snapshot=dict(published_result=dict(sha256=status.file_sha256(path)),
                             population_rows=3000028242, sample_rows=9999000), coverage=coverage)
    monkeypatch.setitem(sys.modules, 'full_ssb_local_replay', SimpleNamespace(verify=lambda: accepted))
    model, ci = status.model_stages()
    assert model['status'] == 'PASS_REPLAY_WITH_GROUP_GAPS'
    assert ci['status'] == 'PASS_REPLAY_WITH_CI_GAPS'
    assert ci['excluded_truth_groups'] == 59
    assert model['author_different_groups']==1713 and model['author_reproduction_complete'] is False


@pytest.mark.parametrize('field,value',[('scope','AUTHOR_SSB_SF500'),('author_reproduction_complete',True),
    ('full_paper_reproduction_complete',True),('author_different_groups',0)])
def test_resealed_scope_alias_cannot_promote_local_science(tmp_path,monkeypatch,field,value):
    monkeypatch.setattr(status,'FULL',tmp_path)
    write(tmp_path,'results/ssb_local_sf500_model_aqp_ci.json',dict(status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI'))
    write(tmp_path,'ssb/local_sf500_replay/verification.json',{})
    accepted=dict(status='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',scope='LOCAL_SSB_SF500',
        author_reproduction_complete=False,full_paper_reproduction_complete=False,author_different_groups=1713,
        source_snapshot=dict(published_result=dict(sha256=status.file_sha256(tmp_path/'results/ssb_local_sf500_model_aqp_ci.json'))))
    accepted[field]=value
    monkeypatch.setitem(sys.modules,'full_ssb_local_replay',SimpleNamespace(verify=lambda:accepted))
    assert status.model_stages()[0]['status']=='EVIDENCE_INVALID'
