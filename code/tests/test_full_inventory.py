"""Audit failures must stop input acceptance before any experiment is run."""
import csv
import importlib
import importlib.util
from pathlib import Path
import runpy

import pytest


def inventory_module():
    assert importlib.util.find_spec('full_inventory') is not None, 'Input audit is not implemented'
    return importlib.import_module('full_inventory')


def write_pair(tmp_path, queries, rows, fields=('query_no', 'query', 'cardinality_true')):
    sql = tmp_path / 'queries.sql'
    truth = tmp_path / 'truth.csv'
    sql.write_text('\n'.join(queries) + '\n', encoding='utf-8')
    with truth.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)
    return sql, truth


def test_unterminated_single_line_query_is_counted_and_matched(tmp_path):
    # Splitting on semicolons would merge or drop the second query.
    queries = ['SELECT COUNT(*) FROM title t WHERE t.kind_id = 1;',
               'SELECT COUNT(*) FROM title t WHERE t.kind_id = 2']
    sql, truth = write_pair(tmp_path, queries,
                            [(0, queries[0], 7), (1, queries[1] + ';', 11)])
    report = inventory_module().inspect_query_pair(sql, truth)
    assert report['queries'] == 2
    assert report['missing_terminal_semicolon_lines'] == [2]
    assert report['query_alignment'] == 'PASS'


def test_truth_query_permutation_is_rejected_despite_equal_row_counts(tmp_path):
    queries = ['SELECT COUNT(*) FROM title t WHERE t.kind_id = 1;',
               'SELECT COUNT(*) FROM title t WHERE t.kind_id = 2;']
    sql, truth = write_pair(tmp_path, queries,
                            [(0, queries[1], 11), (1, queries[0], 7)])
    with pytest.raises(ValueError, match='SQL mismatch.*line 1'):
        inventory_module().inspect_query_pair(sql, truth)


def test_alignment_does_not_fold_string_literal_case(tmp_path):
    sql, truth = write_pair(tmp_path, ["SELECT COUNT(*) FROM t WHERE name = 'ATL';"],
                            [(0, "select count(*) from t where name='atl';", 3)])
    with pytest.raises(ValueError, match='SQL mismatch'):
        inventory_module().inspect_query_pair(sql, truth)


def test_truth_aliases_and_zero_cardinality_are_preserved(tmp_path):
    sql, truth = write_pair(tmp_path, ['SELECT COUNT(*) FROM t WHERE x = 9'],
                            [(0, 'select count(*) from t where x=9;', 0)],
                            fields=('query_no', 'sql', 'true_cardinality'))
    report = inventory_module().inspect_query_pair(sql, truth)
    assert report['queries'] == 1
    assert report['zero_truth_queries'] == 1
    assert report['truth_columns']['query'] == 'sql'


@pytest.mark.parametrize('rows, message', [
    ([(1, 'SELECT COUNT(*) FROM t;', 3)], 'query_no mismatch'),
    ([(0, 'SELECT COUNT(*) FROM t;', -1)], 'Invalid cardinality'),
    ([], 'row count mismatch'),
])
def test_invalid_truth_cannot_receive_pass(tmp_path, rows, message):
    sql, truth = write_pair(tmp_path, ['SELECT COUNT(*) FROM t;'], rows)
    with pytest.raises(ValueError, match=message):
        inventory_module().inspect_query_pair(sql, truth)


def test_git_path_classification_keeps_literal_quotes_and_no_extension():
    # A quoted filename is literal here, not Git's escaped display representation.
    paths = ['baselines/aqp/results/dbest/result_[\'flights\'].csv',
             'baselines/aqp/results/xdbresults/run0',
             'baselines/aqp/resources/query.sql',
             'baselines/new_method/estimate.py']
    report = inventory_module().classify_baseline_paths(paths)
    assert report['extension_counts'] == {'.csv': 1, '.py': 1, '.sql': 1, '[none]': 1}
    assert report['implementation_source_paths'] == ['baselines/new_method/estimate.py']
    assert report['sql_resource_paths'] == ['baselines/aqp/resources/query.sql']


def test_group_dimensions_are_checked_against_sql_content(tmp_path):
    query = 'SELECT COUNT(*) FROM title t, cast_info ci WHERE t.id=ci.movie_id AND ci.role_id=1;'
    sql, truth = write_pair(tmp_path, [query], [(0, query, 42)])
    module = inventory_module()
    assert module.inspect_query_pair(sql, truth, expected_dimensions=(2, 1))['queries'] == 1
    with pytest.raises(ValueError, match='Query dimensions mismatch'):
        module.inspect_query_pair(sql, truth, expected_dimensions=(3, 1))


def test_relative_script_invocation_audits_real_inputs_without_writing(monkeypatch):
    # CPython 3.8 preserves a relative __file__ for a relative script invocation.
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root)
    namespace = runpy.run_path('code/full_inventory.py', run_name='inventory_test')
    report = namespace['build_inventory']()
    assert report['summary']['generalization_queries_3_to_6_tables'] == 683
    assert report['summary']['figure_6_8_queries_4_to_6_tables'] == 413
    assert report['paper_200_queries']['selection_rule_or_query_ids'] is None
    assert report['upstream_baselines']['extension_counts'] == {
        '.csv': 567, '.pkl': 602, '.png': 1, '.sql': 2, '[none]': 600}
    assert 'code/full_inventory.py' in report['audit_file_seals']
