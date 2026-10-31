from fractions import Fraction

import pytest

from full_aqp_tables import sample_estimate, group_error_summary


def test_sample_estimate_uses_actual_rows_and_keeps_avg_count_and_sum_distinct():
    moments = dict(count=1, filter_count=1, sum_integer=30, scale=10)
    assert sample_estimate(moments, 'SUM', 1000, 3) == Fraction(1000)
    assert sample_estimate(moments, 'COUNT', 1000, 3) == Fraction(1000, 3)
    assert sample_estimate(moments, 'AVG', 1000, 3) == Fraction(3)


def test_group_mean_retains_missing_groups_with_explicit_penalty():
    rows = [dict(truth=1000., sample_prediction=1000., sample_group_present=True),
            dict(truth=1., sample_prediction=None, sample_group_present=False)]
    result = group_error_summary(rows)
    assert result['mean_relative_error_with_missing_penalty'] == .5
    assert result['matched_mean_relative_error'] == 0.
    assert result['missing_groups'] == 1


@pytest.mark.parametrize('mode', ['empty', 'duplicate', 'binding', 'tamper', 'escape'])
def test_cached_flights_bundle_cannot_hide_changed_or_missing_outputs(tmp_path, monkeypatch, mode):
    import full_aqp_tables as tables
    monkeypatch.setattr(tables, 'ROOT', tmp_path)
    directory = tmp_path/'figures'; directory.mkdir()
    for name in ['query_summary.csv', 'all_groups.csv', 'flights_relative_error.png', 'flights_ci_half_width.png']:
        (directory/name).write_bytes(b'original')
    binding = {'source':'exact'}
    receipt = dict(status='PASS_LOCAL_SAME_SAMPLE_COMPARISON', full_paper_complete=False,
        binding=tables.binding_hash(binding), binding_details=binding,
        artifacts=[tables.artifact(p) for p in directory.iterdir()])
    tables.require_existing_figures(receipt, directory, binding)
    if mode == 'empty': receipt['artifacts'] = []
    if mode == 'duplicate': receipt['artifacts'][-1] = receipt['artifacts'][0]
    if mode == 'binding': receipt['binding_details'] = {'source':'older'}
    if mode == 'tamper': (directory/'all_groups.csv').write_bytes(b'changed')
    if mode == 'escape':
        external = tmp_path/'all_groups.csv'; external.write_bytes(b'original')
        receipt['artifacts'] = [tables.artifact(external) if item['path'].endswith('all_groups.csv') else item
                                for item in receipt['artifacts']]
    with pytest.raises(ValueError):
        tables.require_existing_figures(receipt, directory, binding)
