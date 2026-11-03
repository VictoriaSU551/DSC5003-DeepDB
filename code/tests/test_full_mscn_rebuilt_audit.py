import pytest

from full_mscn_rebuilt_audit import require_inventory
import full_mscn_rebuilt_audit as audit


@pytest.mark.parametrize('paths', [[], ['same', 'same'], ['only']])
def test_final_checkpoint_inventory_cannot_be_empty_or_duplicated(paths):
    with pytest.raises(ValueError, match='inventory'):
        require_inventory([dict(path=p) for p in paths], 2)


@pytest.mark.parametrize('mode', ['subset', 'duplicate', 'different_path'])
def test_exact_twenty_one_workload_grid_is_required(mode):
    pairs = audit.workload_files(True)
    if mode == 'subset': pairs = [pairs[0], pairs[6]]
    if mode == 'duplicate': pairs[-1] = pairs[0]
    if mode == 'different_path': pairs[0] = (pairs[0][0], pairs[1][1], pairs[0][2])
    with pytest.raises(ValueError, match='workload grid'):
        audit.require_workload_grid(pairs)


def test_actual_query_count_cannot_be_replaced_by_the_expected_total():
    groups = {name: {'queries': count} for name, count in audit.EXPECTED_COUNTS.items()}
    assert audit.require_query_totals(groups) == 753
    groups['job_light']['queries'] = 69
    with pytest.raises(ValueError, match='query totals'):
        audit.require_query_totals(groups)


def test_current_helper_source_must_equal_the_delivered_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    path = tmp_path / 'code/full_evaluation.py'
    path.parent.mkdir(); path.write_text('changed helper')
    record = dict(path='source_snapshot/code/full_evaluation.py', bytes=1, sha256='wrong')
    with pytest.raises(ValueError, match='helper source'):
        audit.check_helper_sources([record])
