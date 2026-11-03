import math

import pytest

from full_paper_tables import checked_errors, selected_summary


def row(prediction, truth=10):
    error = math.inf if prediction == 0 else max(prediction / truth, truth / prediction)
    return {'cardinality_true': str(truth), 'cardinality_predict': str(prediction), 'q_error': str(error)}


def test_overall_quantile_uses_queries_rather_than_medians_of_groups():
    groups = {'3_1_SPN': [row(1000)], '4_1_SPN': [row(10)] * 99,
              'job_light': [row(100000)] * 70}
    result = selected_summary(groups, lambda group: group != 'job_light')
    assert result['queries'] == 100
    assert result['median'] == 1
    assert result['mean'] == 1.99


def test_zero_estimate_stays_infinite_and_bad_recorded_error_is_rejected():
    assert math.isinf(checked_errors([row(0)])[0])
    wrong = row(1)
    wrong['q_error'] = '1'
    with pytest.raises(ValueError, match='recorded q-error'):
        checked_errors([wrong])


def test_absent_selection_is_missing_instead_of_zero():
    assert selected_summary({'job_light': [row(10)]}, lambda group: group.startswith('6_')) is None


def test_direct_script_relative_path_can_be_sealed(tmp_path, monkeypatch):
    import full_paper_tables as tables
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tables, 'ROOT', tmp_path)
    (tmp_path / 'driver.py').write_bytes(b'sealed source')
    assert tables.source_record('driver.py')['path'] == 'driver.py'
