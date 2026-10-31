import json

import full_status as status


def test_formal_file_cannot_be_called_accepted_before_independent_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    assert status.ssb_model_stages()[0]['status'] == 'PENDING'
    report = tmp_path/'results/ssb_model_aqp_ci.json'; report.parent.mkdir()
    report.write_text(json.dumps({'status':'PASS'}))
    model, ci = status.ssb_model_stages()
    assert model['status'] == ci['status'] == 'FORMAL_COMPLETE_REPLAY_PENDING'


def test_exception_report_stays_an_error_without_trying_to_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(status, 'FULL', tmp_path)
    report = tmp_path/'results/ssb_model_aqp_ci.json'; report.parent.mkdir()
    report.write_text(json.dumps({'status':'MODEL_QUERY_ERRORS_RECORDED'}))
    assert status.ssb_model_stages()[0]['status'] == 'FORMAL_QUERY_ERRORS_RECORDED'


def test_completed_ssb_traversal_with_different_author_truth_is_a_failed_gate():
    checkpoint = dict(rows=3000028334, sample_rows=9993609, committed_shards=list(range(4000)))
    final = dict(status='MISMATCH', author_truth_comparison={'different_values':[{'query':'0'}]})
    result = status.ssb_generation_stage(checkpoint, final)
    assert result['status'] == 'FAILED_AUTHOR_POPULATION_GATE'
    assert result['generated_rows'] == 3000028334
    assert result['requested_rows'] == 3000028242
    assert result['author_aggregate_value_differences'] == 1
