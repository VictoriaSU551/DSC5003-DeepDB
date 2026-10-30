import copy

import pytest

from full_ssb_tables import summarize


def query():
    group = dict(key=[], status='MATCHED', truth=1000., prediction=900.,
                 relative_error=.1, model_covers_truth=None, model_relative_half_width=None,
                 sample_moments=dict(count=0, filter_count=0, sum_integer=0, scale=1),
                 reference_ci=dict(eligible=False, status='LESS_THAN_10_SAMPLES'))
    return dict(query_name='S1.1', query_no=0, sql='select sum(lo_revenue) from lineorder',
                point_error=None, ci_error=None, point_seconds=1., ci_seconds=2.,
                missing_model_groups=0, extra_model_groups=0, nonfinite_original_intervals=[], groups=[group])


def test_missing_reference_group_has_error_penalty_and_ci_is_not_zero_filled():
    rows, summary = summarize(query(), 1000, 10)
    assert rows[0]['sample_prediction'] == 0.
    assert not rows[0]['sample_group_present']
    assert summary['sample_mean_relative_error_with_missing_penalty'] == 1.
    assert summary['reference_ci_eligible'] == 0
    assert summary['model_ci_coverage_all_eligible'] is None
    assert summary['model_mean_relative_error_with_missing_penalty'] == pytest.approx(.1)


def test_missing_model_group_is_retained_and_extra_group_is_separate():
    q = query(); q['groups'][0].update(prediction=None, status='MISSING_MODEL_GROUP', relative_error=None)
    q['missing_model_groups'] = 1
    extra = copy.deepcopy(q['groups'][0]); extra.update(key=['extra'], truth=None, status='EXTRA_MODEL_GROUP')
    q['groups'].append(extra); q['extra_model_groups'] = 1
    rows, summary = summarize(q, 1000, 10)
    assert len(rows) == 2
    assert summary['model_mean_relative_error_with_missing_penalty'] == 1.
    assert summary['truth_groups'] == summary['missing_model_groups'] == summary['extra_model_groups'] == 1


def test_reference_uses_actual_ten_million_sample_size_not_one_million_training_cap():
    q = query(); q['groups'][0]['sample_moments'].update(count=2, filter_count=2, sum_integer=100)
    rows, summary = summarize(q, 1000, 20)
    assert rows[0]['sample_prediction'] == 5000
    q['groups'][0]['relative_error'] = .9
    with pytest.raises(ValueError, match='relative error'):
        summarize(q, 1000, 20)


def test_nonfinite_matched_prediction_is_not_a_missing_group_or_finite_error_penalty():
    q = query(); q['groups'][0]['prediction'] = None; q['groups'][0]['relative_error'] = None
    rows, summary = summarize(q, 1000, 10)
    assert rows[0]['status'] == 'MATCHED_WITHOUT_FINITE_PREDICTION'
    assert summary['invalid_model_points'] == 1
    assert summary['missing_model_groups'] == 0
    assert summary['model_mean_relative_error_with_missing_penalty'] is None
    assert rows[0]['model_relative_error_with_missing_penalty'] is None


@pytest.mark.parametrize('mode', ['empty', 'duplicate', 'binding', 'tamper'])
def test_cached_figures_require_complete_current_five_artifact_inventory(tmp_path, monkeypatch, mode):
    import full_ssb_tables as tables
    monkeypatch.setattr(tables, 'ROOT', tmp_path)
    directory = tmp_path/'figures'; directory.mkdir()
    for name in tables.OUTPUT_NAMES:
        (directory/name).write_bytes(b'original')
    binding = {'source':'exact'}
    receipt = dict(status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES', full_paper_complete=False,
        binding=tables.binding_hash(binding), binding_details=binding,
        artifacts=[dict(path=p.relative_to(tmp_path).as_posix(), bytes=p.stat().st_size,
                        sha256=tables.file_sha256(p)) for p in directory.iterdir()])
    tables.require_existing_figures(receipt, directory, binding)
    if mode == 'empty': receipt['artifacts'] = []
    if mode == 'duplicate': receipt['artifacts'][-1] = receipt['artifacts'][0]
    if mode == 'binding': receipt['binding'] = 'wrong'
    if mode == 'tamper': (directory/'all_groups.csv').write_bytes(b'different')
    with pytest.raises(ValueError):
        tables.require_existing_figures(receipt, directory, binding)
