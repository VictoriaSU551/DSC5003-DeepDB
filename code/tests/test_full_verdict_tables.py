import copy

import pytest

from full_verdict_tables import summarize


def query():
    groups = [dict(key=['A'], truth=10., prediction=8., status='MATCHED', relative_error=.2),
              dict(key=['B'], truth=-20., prediction=None, status='MISSING_MODEL_GROUP', relative_error=None)]
    return dict(query_name='F5.2', raw_status='INCORRECT_RAW_UNSCALED_COMPOUND_SUM',
                groups=groups, missing=1, extra=0, raw={'engine_wall_ms':3.},
                native_ci_confidence=.95, native_ci={'engine_wall_ms':4.}, adapted=None)


def test_missing_group_penalty_is_distinct_from_matched_error_and_raw_bug_label():
    rows, summary = summarize(query(), 'raw')
    assert len(rows) == 2
    assert summary['mean_relative_error_with_missing_penalty'] == pytest.approx(.6)
    assert summary['matched_mean_relative_error'] == pytest.approx(.2)
    assert summary['source_status'] == 'INCORRECT_RAW_UNSCALED_COMPOUND_SUM'
    assert summary['missing_groups'] == 1
    assert summary['native_ci_confidence'] == .95


def test_adapted_sum_is_a_separate_two_call_result_without_fabricated_interval():
    q = query(); groups = copy.deepcopy(q['groups'])
    groups[0].update(prediction=10., relative_error=0.)
    q['adapted'] = dict(status='ADAPTED_TWO_ORIGINAL_TOP_LEVEL_SUMS', groups=groups,
                        missing=1, extra=0, physical_sql_calls=2, engine_wall_ms=7.,
                        ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL')
    rows, summary = summarize(q, 'adapted')
    assert summary['mean_relative_error_with_missing_penalty'] == .5
    assert summary['physical_sql_calls'] == 2
    assert summary['native_ci_confidence'] is None
    assert all(row['native_ci_status'] == 'UNSUPPORTED_NO_COVARIANCE_MODEL' for row in rows)
    assert all(row['native_interval'] is None for row in rows)


def test_invalid_matched_prediction_cannot_become_a_missing_group_or_a_valid_mean():
    q = query(); q['groups'][0].update(prediction=None, relative_error=None)
    rows, summary = summarize(q, 'raw')
    assert summary['invalid_predictions'] == 1
    assert summary['missing_groups'] == 1
    assert summary['mean_relative_error_with_missing_penalty'] is None
    assert rows[0]['status'] == 'MATCHED_WITHOUT_FINITE_PREDICTION'


@pytest.mark.parametrize('mode', ['duplicate', 'changed_error', 'changed_coverage'])
def test_changed_group_or_metric_identity_is_rejected(mode):
    q = query()
    if mode == 'duplicate': q['groups'].append(copy.deepcopy(q['groups'][0]))
    if mode == 'changed_error': q['groups'][0]['relative_error'] = .7
    if mode == 'changed_coverage': q['missing'] = 0
    with pytest.raises(ValueError):
        summarize(q, 'raw')
