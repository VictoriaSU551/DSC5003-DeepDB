"""Pure candidate gates: no DB, JVM, native generation or actual data query."""
import base64
import importlib.util
import io
import copy
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module():
    path = ROOT / 'code/full_verdict_ssb.py'
    assert path.exists(), 'Independent Verdict SSB candidate is missing'
    spec = importlib.util.spec_from_file_location('full_verdict_ssb_candidate', str(path))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def token(value):
    return 'N' if value is None else 'V' + base64.b64encode(str(value).encode()).decode()


def output(call, rows, labels, error=None):
    qid = call['call_id']
    lines = ['META\t' + qid + '\t' + '\t'.join(map(token, labels))]
    lines += ['ROW\t' + qid + '\t' + '\t'.join(map(token, row)) for row in rows]
    if error is not None:
        lines += ['ERROR\t' + qid + '\t' + token(error)]
    return '\n'.join(lines + ['TIME\t' + qid + '\t123']) + '\n'


def call(width=2, mode='nobound'):
    return dict(call_id='Q2.1.raw.' + mode, group_width=width, mode=mode,
                role='RAW', query_no=3, sql='select original;')


def test_plan_keeps_all_original_sql_and_six_profit_children_in_each_mode():
    m = module()
    queries = m.load_queries(ROOT)
    calls = m.call_plan(queries)
    assert len(calls) == 38 and len({c['call_id'] for c in calls}) == 38
    assert {mode: sum(c['mode'] == mode for c in calls) for mode in ('nobound', 'subsampling')} == {'nobound': 19, 'subsampling': 19}
    for mode in ('nobound', 'subsampling'):
        raw = [c for c in calls if c['mode'] == mode and c['role'] == 'RAW']
        assert [c['sql'] for c in raw] == queries
        assert [c['group_width'] for c in raw] == [0, 0, 0, 2, 2, 2, 3, 3, 3, 3, 2, 3, 3]
    children = [c for c in calls if c['query_no'] == 10 and c['mode'] == 'nobound' and c['role'] != 'RAW']
    assert [c['sql'].split(' from ')[0] for c in children] == ['select d_year, c_nation, sum(lo_revenue)', 'select d_year, c_nation, sum(lo_supplycost)']
    assert all(c['sql'].split(' from ')[1] == queries[10].split(' from ')[1] for c in children)


def test_changed_query_file_rejected_even_if_still_thirteen_lines(tmp_path):
    m = module()
    p = tmp_path / 'code/benchmarks/ssb/sql/aqp_queries.sql'
    p.parent.mkdir(parents=True)
    p.write_bytes((ROOT / 'code/benchmarks/ssb/sql/aqp_queries.sql').read_bytes().replace(b'< 25', b'< 24'))
    with pytest.raises(ValueError, match='SQL.*hash'):
        m.load_queries(tmp_path)


def test_actual_fraction_and_generator_probability_remain_distinct():
    m = module()
    c = m.scaling_contract(39587, 11997996, 61482997997673935)
    assert Fraction(**c['verdict_probability']) == Fraction(39587, 11997996)
    assert Fraction(**c['verdict_weight']) == Fraction(11997996, 39587)
    assert Fraction(**c['deepdb_normalizer']) != 11997996
    assert m.scaled_sample_sum(7, 3, 10) == Fraction(70, 3)
    assert c['query_truth_used_for_registration'] is False


@pytest.mark.parametrize('n,N,cutoff', [(0, 10, 1), (11, 10, 1), (3, 0, 1), (3, 10, 0), (3, 10, 2**64+1), (True, 10, 1)])
def test_invalid_population_or_probability_rejected(n, N, cutoff):
    with pytest.raises(ValueError):
        module().scaling_contract(n, N, cutoff)


def test_multikey_rows_keep_null_nonfinite_ci_and_exact_raw_cells():
    m = module(); c = call(3, 'subsampling')
    text = output(c, [['UNITED ST1', 'UNITED ST2', '1997', 'NaN', 'Infinity'], ['X', 'Y', '1998', None, '2']], ['c_city', 's_city', 'd_year', 'sum', 'error'])
    parsed = m.parse_engine(text, [c])[c['call_id']]
    assert parsed['rows'][0]['key'] == ['UNITED ST1', 'UNITED ST2', '1997']
    assert parsed['rows'][0]['point_status'] == 'NONFINITE'
    assert parsed['rows'][0]['ci_status'] == 'NONFINITE'
    assert parsed['rows'][0]['raw_cells'][-2:] == ['NaN', 'Infinity']
    assert parsed['rows'][1]['point_status'] == 'NULL'
    assert parsed['rows'][1]['ci_status'] == 'NULL_POINT'


def test_zero_group_row_and_valid_interval():
    m = module(); c = call(0, 'subsampling')
    row = m.parse_engine(output(c, [['100', '5']], ['sum', 'error']), [c])[c['call_id']]['rows'][0]
    assert row['key'] == [] and row['interval95'] == [95.0, 105.0]


@pytest.mark.parametrize('mutation', ['duplicate_time', 'unknown_id', 'missing_time', 'wrong_arity', 'duplicate_group', 'row_after_time', 'invalid_base64', 'duplicate_meta'])
def test_malformed_engine_evidence_fails_closed(mutation):
    m = module(); c = call()
    text = output(c, [['1992', 'MFGR#121', '100']], ['d_year', 'brand', 'sum'])
    if mutation == 'duplicate_time': text += 'TIME\t' + c['call_id'] + '\t1\n'
    if mutation == 'unknown_id': text = text.replace(c['call_id'], 'UNKNOWN')
    if mutation == 'missing_time': text = text[:text.index('TIME\t')]
    if mutation == 'wrong_arity': text = output(c, [['1992', '100']], ['year', 'brand', 'sum'])
    if mutation == 'duplicate_group': text = output(c, [['1992', 'A', '1'], ['1992', 'A', '2']], ['year', 'brand', 'sum'])
    if mutation == 'row_after_time': text += 'ROW\t' + c['call_id'] + '\t' + '\t'.join(map(token, ['1993', 'B', '3'])) + '\n'
    if mutation == 'invalid_base64': text = text.replace(token('100'), 'V!!!')
    if mutation == 'duplicate_meta': text = text.splitlines()[0] + '\n' + text
    with pytest.raises(ValueError): m.parse_engine(text, [c])


def test_engine_error_preserves_partial_rows_without_treating_them_as_success():
    m = module(); c = call()
    result = m.parse_engine(output(c, [['1992', 'A', '100']], ['year', 'brand', 'sum'], 'timeout'), [c])[c['call_id']]
    assert result['status'] == 'ENGINE_ERROR' and result['error'] == 'timeout'
    assert result['rows'][0]['raw_cells'] == ['1992', 'A', '100']
    assert result['usable_for_point_comparison'] is False


def test_two_sum_adapter_preserves_missing_children_and_never_composes_ci():
    m = module()
    left = [{'key': ['1997', 'A'], 'point': 100.0}, {'key': ['1998', 'B'], 'point': 20.0}]
    right = [{'key': ['1997', 'A'], 'point': 30.0}, {'key': ['1999', 'C'], 'point': 5.0}]
    result = m.subtract_groups(left, right)
    assert {tuple(r['key']): r['status'] for r in result} == {('1997', 'A'): 'MATCHED', ('1998', 'B'): 'MISSING_RIGHT', ('1999', 'C'): 'MISSING_LEFT'}
    assert result[0]['point'] == 70.0
    assert all(r['interval95'] is None and r['ci_status'] == 'UNSUPPORTED_NO_COVARIANCE_MODEL' for r in result)
    with pytest.raises(ValueError, match='duplicate'): m.subtract_groups(left + left[:1], right)


def test_pipe_normalizer_preserves_duplicate_rows_empty_strings_quotes_and_spaces():
    m = module(); source = io.StringIO('1|  A"B  ||\r\n1|  A"B  ||\r\n'); target = io.StringIO()
    assert m.normalize_pipe_records(source, target, 3, terminal_pipe=True) == 2
    assert target.getvalue() == '1|"  A""B  "|""\n1|"  A""B  "|""\n'


def test_pipe_normalizer_rejects_missing_terminator_and_incomplete_row():
    m = module()
    for text in ('1|A\n', '1|A|B|C|\n', '1|A|B|'):
        with pytest.raises(ValueError): m.normalize_pipe_records(io.StringIO(text), io.StringIO(), 3, terminal_pipe=True)


def test_candidate_cli_cannot_start_database_or_engine():
    m = module()
    plan = m.candidate_plan(ROOT)
    assert plan['stage'] == 'CANDIDATE_PURE_ONLY'
    assert plan['engine_calls_executed'] == 0 and plan['formal_allowed'] is False
    assert plan['database'] == 'deepdb_verdict_ssb'
    assert plan['dimension_policy'] == 'FULL_UNSAMPLED_NO_VPART'
    assert plan['required_before_science'] == ['ROOT_GO', 'NATIVE_FINAL_ACCEPTED', 'MEASURED_PG_ALLOWANCE']
    assert set(plan['required_before_formal']) >= {'ROOT_SOURCE_MODEL_REPLAY_ACCEPTANCE', 'SF2_ORIGINAL_ENGINE_GATE', 'PROTECTED_DB_RESOURCE_REVIEW'}


def test_plan_import_and_decode_need_no_database_jvm_or_network(monkeypatch):
    import socket
    import sqlite3
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError('Candidate attempted an unauthorized external/scientific operation')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    m = module(); m.candidate_plan()
    c = call(0)
    assert m.parse_engine(output(c, [['5']], ['sum']), [c])[c['call_id']]['rows'][0]['point'] == 5.0


def lineage_fixture():
    # A hand-sized stream relation; no original generator or SQL engine involved.
    binding = dict(scale='2', total_orders=4, shards=2, sample_seed=7, actual_cutoff=5,
                   effective_probability_numerator=5, effective_probability_denominator=2**64,
                   native_build_binding={'frozen': 'A'}, dimensions={'all': 'same'})
    truth = [dict(query_no=i, group=[] if i < 3 else ['g'] * w, value=i + 1)
             for i, w in enumerate([0, 0, 0, 2, 2, 2, 3, 3, 3, 3, 2, 3, 3])]
    descriptor = dict(path='sample', bytes=30, rows=3, sha256='a' * 64)
    golden = dict(status='PASS', binding={'callback_binding': {'frozen': 'A'}}, rows=10,
                  all17_fields_equal=True, all_dimensions_equal=True,
                  all13_exact_integer_aggregates_equal=True, truth_groups=13)
    benchmark = dict(status='PASS', binding={'plan': {'binding': binding, 'ranges': [[1, 2], [3, 2]]}},
                     rows=10, sample_rows=3, all13_integer_aggregates_equal=True,
                     sample_descriptor=descriptor)
    checkpoint = dict(binding=copy.deepcopy(binding), complete=True, next_shard=2, rows=10,
                      sample_rows=3, sample_bytes=30, sample_sha256='a' * 64, aggregates=copy.deepcopy(truth),
                      committed_shards=[dict(shard=0, first_order=1, orders=2, rows=6, sample_rows=2, sample_bytes=20),
                                        dict(shard=1, first_order=3, orders=2, rows=4, sample_rows=1, sample_bytes=10)])
    return benchmark, golden, checkpoint, truth


def test_same_source_lineage_accepts_complete_contiguous_stream_and_exact_truth():
    m = module()
    b, g, cp, truth = lineage_fixture()
    result = m.validate_sample_lineage(b, g, cp, truth)
    assert result['population_rows'] == 10 and result['sample_rows'] == 3
    assert result['truth_group_count'] == 13
    assert result['sample_sql_computed'] is False and result['engine_calls_executed'] == 0


@pytest.mark.parametrize('change', ['callback', 'dimension', 'incomplete', 'duplicate_shard', 'missing_shard', 'sample_count', 'sample_hash', 'truth_value', 'truth_duplicate', 'truth_group_width', 'fraction'])
def test_wrong_sample_population_link_or_truth_is_rejected(change):
    m = module(); b, g, cp, truth = copy.deepcopy(lineage_fixture())
    if change == 'callback': g['binding']['callback_binding']['frozen'] = 'B'
    if change == 'dimension': cp['binding']['dimensions']['all'] = 'other'
    if change == 'incomplete': cp['complete'] = False
    if change == 'duplicate_shard': cp['committed_shards'][1]['shard'] = 0
    if change == 'missing_shard': cp['committed_shards'].pop()
    if change == 'sample_count': cp['committed_shards'][1]['sample_rows'] = 2
    if change == 'sample_hash': cp['sample_sha256'] = 'b' * 64
    if change == 'truth_value': truth[0]['value'] = 999
    if change == 'truth_duplicate': truth.append(copy.deepcopy(truth[0]))
    if change == 'truth_group_width': truth[3]['group'] = ['one']
    if change == 'fraction': cp['binding']['effective_probability_numerator'] = 6
    with pytest.raises(ValueError): m.validate_sample_lineage(b, g, cp, truth)


def test_source_inventory_rejects_empty_subset_extra_paths_without_reading_any_file(tmp_path):
    m = module()
    for files in ({}, {'stream/checkpoint.json': 'a' * 64}, {'foreign': 'b' * 64}):
        with pytest.raises(ValueError, match='required file set'):
            m.verify_benchmark_file_set(tmp_path, files)


def profit_results(m, error=None):
    plans = [c for c in m.call_plan(m.load_queries()) if c['query_no'] == 10 and c['mode'] == 'nobound']
    results = [m.parse_engine(output(c, [['1997', 'UNITED STATES', value]], ['year', 'nation', 'sum'], error if c['role'] == 'SUM_REVENUE' else None), [c])[c['call_id']]
               for c, value in zip(plans, ['7', '100', '30'])]
    return results


def test_profit_adapter_keeps_raw_compound_discrepancy_separate():
    m = module(); raw, left, right = profit_results(m)
    result = m.profit_adapter(raw, left, right)
    assert result['raw_compound']['rows'][0]['point'] == 7.0
    assert result['groups'][0]['point'] == 70.0
    assert result['groups'][0]['ci_status'] == 'UNSUPPORTED_NO_COVARIANCE_MODEL'


def test_profit_adapter_cannot_promote_partial_error_rows_to_point_success():
    m = module(); raw, left, right = profit_results(m, error='original join timeout')
    result = m.profit_adapter(raw, left, right)
    assert result['status'] == 'ENGINE_ERROR' and result['groups'] == []
    assert result['children'][0]['error'] == 'original join timeout'
    assert result['children'][0]['rows'][0]['point'] == 100.0


def test_profit_adapter_rejects_mismatched_query_or_child_role():
    m = module(); raw, left, right = profit_results(m)
    with pytest.raises(ValueError): m.profit_adapter(raw, right, left)
    left['call']['query_no'] = 11
    with pytest.raises(ValueError): m.profit_adapter(raw, left, right)


def test_cli_output_refuses_overwrite_or_writes_outside_candidate_namespace(tmp_path, monkeypatch):
    m = module()
    # The plan still reads fixed real SQL, but output containment is isolated.
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='inside output/full/verdict_ssb'):
        m.main(['plan', '--output', str(tmp_path / 'foreign_fixture.json')])
    existing = tmp_path / 'output/full/verdict_ssb/candidate.json'
    existing.parent.mkdir(parents=True)
    existing.write_text('preserve')
    with pytest.raises(FileExistsError): m.main(['plan', '--output', str(existing)])
    assert existing.read_text() == 'preserve'
