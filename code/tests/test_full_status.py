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
