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
    assert status.model_stages()[1]['paper_figure11_training_budget_reproduced'] is False
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


def test_10m_ci_remains_pending_until_its_own_model_and_replay(tmp_path,monkeypatch):
    monkeypatch.setattr(status,'FULL',tmp_path)
    result=status.ci10m_stage()
    assert result['status']=='PENDING'
    assert result['model_training_cap_per_table']==10000000
    assert result['paper_figure11_training_budget_policy_applied'] is False
    write(tmp_path,'results/ssb_local_sf500_ci10m.json',dict(status='PASS_LOCAL_SSB_SF500_10M_CI_WITH_AUTHOR_MISMATCH'))
    assert status.ci10m_stage()['status']=='FORMAL_COMPLETE_REPLAY_PENDING'


def test_recorded_historical_reverse_failure_is_not_reported_as_unstarted(tmp_path,monkeypatch):
    monkeypatch.setattr(status,'FULL',tmp_path)
    write(tmp_path,'results/ssb_local_sf500_model_aqp_ci.json',dict(status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI'))
    write(tmp_path,'ssb/local_sf500_replay/last_run.json',dict(status='TAINTED',error='interval mismatch'))
    model,ci=status.model_stages()
    assert model['status']==ci['status']=='FORMAL_COMPLETE_REPLAY_FAILURE_RECORDED'
    assert model['reason']=='interval mismatch' and ci['author_reproduction_complete'] is False


def canonical_fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(status,'FULL',tmp_path)
    name='results/ssb_local_sf500_canonical_aqp_ci.json'
    write(tmp_path,name,dict(status='PASS_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH'))
    coverage=dict(missing_model_groups_total=0,extra_model_groups_total=0,nonfinite_point_groups=0,
        nonfinite_original_ci_groups=0,missing_or_nonfinite_model_interval_groups=0,
        reference_ci_eligible_truth_groups=2000,reference_ci_excluded_truth_groups=59)
    accepted=dict(status='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH',
        scope='LOCAL_SSB_SF500_CANONICAL_CI',evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',
        group_order_adapter_sha256='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c',
        author_reproduction_complete=False,full_paper_reproduction_complete=False,author_different_groups=1713,
        historical_reverse_accepted=False,population_rows=3000028242,sample_rows=9996946,
        published_result=dict(path='output/full/'+name,bytes=(tmp_path/name).stat().st_size,sha256=status.file_sha256(tmp_path/name)),
        report=dict(coverage=coverage))
    calls=[]
    def verify():calls.append('fresh');return accepted
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical',SimpleNamespace(verify_canonical=verify))
    return accepted,calls


def test_canonical_pending_does_not_import_or_verify_science(tmp_path,monkeypatch):
    monkeypatch.setattr(status,'FULL',tmp_path)
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical',SimpleNamespace(verify_canonical=lambda:pytest.fail('no published result')))
    assert all(x['status']=='PENDING' for x in status.canonical_stages())


def test_canonical_projection_verifies_once_and_preserves_separate_historical_scope(tmp_path,monkeypatch):
    accepted,calls=canonical_fixture(tmp_path,monkeypatch)
    model,ci=status.canonical_stages()
    assert calls==['fresh']
    assert model['status']=='PASS_LOCAL_CANONICAL_1M_AQP_WITH_AUTHOR_MISMATCH'
    assert ci['status']=='PASS_LOCAL_CANONICAL_1M_CI_WITH_EXCLUSIONS'
    assert ci['excluded_truth_groups']==59 and ci['paper_figure11_training_budget_policy_applied'] is False
    assert model['historical_reverse_accepted'] is False and model['author_different_groups']==1713
    assert model['evaluation_variant']==accepted['evaluation_variant']


@pytest.mark.parametrize('field,value',[('evaluation_variant','OLD_SET_ORDER'),('group_order_adapter_sha256','0'*64),
    ('author_reproduction_complete',True),('full_paper_reproduction_complete',True),('historical_reverse_accepted',True),
    ('author_different_groups',0),('sample_rows',10000000),('population_rows',3000000000)])
def test_canonical_projection_rejects_scope_relabelling(tmp_path,monkeypatch,field,value):
    accepted,calls=canonical_fixture(tmp_path,monkeypatch);accepted[field]=value
    assert all(x['status']=='EVIDENCE_INVALID' for x in status.canonical_stages())
    assert calls==['fresh']


@pytest.mark.parametrize('variant',['CANONICAL_DECODED_GROUP_PROTOTYPE_V1','OLD_SET_ORDER'])
def test_10m_projection_requires_new_group_replay_and_variant(tmp_path,monkeypatch,variant):
    monkeypatch.setattr(status,'FULL',tmp_path)
    name='results/ssb_local_sf500_ci10m.json'
    write(tmp_path,name,dict(status='PASS_LOCAL_SSB_SF500_10M_CI_WITH_AUTHOR_MISMATCH'))
    write(tmp_path,'ssb/local_sf500_ci10m_group_replay/verification.json',{})
    coverage=dict(missing_model_groups_total=0,extra_model_groups_total=0,nonfinite_point_groups=0,
        nonfinite_original_ci_groups=0,missing_or_nonfinite_model_interval_groups=0,
        reference_ci_eligible_truth_groups=2000,reference_ci_excluded_truth_groups=59)
    accepted=dict(status='PASS_LOCAL_SSB_10M_CI_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',scope='LOCAL_SSB_10M_CI',
        author_reproduction_complete=False,full_paper_reproduction_complete=False,author_different_groups=1713,
        training_cap_per_table=10000000,evaluation_variant=variant,group_order_adapter_sha256=status.GROUP_ADAPTER_SHA,
        paper_figure11_training_budget_policy_applied=True,exact10000000_fact_training_rows_claimed=False,
        actual_training_rows_per_table=dict(lineorder=9996946,dwdate=2556,customer=10000000,part=1800000,supplier=1000000),
        source_snapshot=dict(published_result=dict(sha256=status.file_sha256(tmp_path/name)),sample_rows=9996946),coverage=coverage)
    calls=[]
    def verify():calls.append('new-group-replay');return accepted
    monkeypatch.setitem(sys.modules,'full_ssb_local_ci_group_replay',SimpleNamespace(verify=verify))
    monkeypatch.setitem(sys.modules,'full_ssb_local_ci_replay',SimpleNamespace(verify=lambda:pytest.fail('historical replay')))
    result=status.ci10m_stage()
    assert calls==['new-group-replay']
    assert result['status']==('PASS_LOCAL_10M_CAP_CI_WITH_EXCLUSIONS' if variant==status.CANONICAL_VARIANT else 'EVIDENCE_INVALID')
