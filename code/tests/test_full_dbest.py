"""Numerical/input contracts for the original DBEst bounded wrapper."""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sqlite3

import pytest

ROOT=Path(__file__).resolve().parents[2]
ENGINE_READY=(ROOT/'.venv-dbest/Scripts/python.exe').exists() and (ROOT/'output/full/dbest/environment.json').exists()
GOLD_READY=(ROOT/'data/flights/generated/golden-200k/original.csv').exists()


def implementation():
    assert importlib.util.find_spec('full_dbest') is not None, 'Original DBEst wrapper is missing'
    return importlib.import_module('full_dbest')


def test_exact_reference_preserves_strict_boundary_and_tenths():
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE flights(DISTANCE INTEGER,DEST_STATE_ABR TEXT)')
    connection.executemany('INSERT INTO flights VALUES (?,?)', [(29,'CA'),(30,'CA'),(31,'CA'),(40,'TX')])
    module = implementation()
    strict = module.exact_range(connection, 'DISTANCE', 3, 4, lower_closed=False, upper_closed=True,
                                conditions={'DEST_STATE_ABR':'CA'})
    closed = module.exact_range(connection, 'DISTANCE', 3, 4, lower_closed=True, upper_closed=True,
                                conditions={'DEST_STATE_ABR':'CA'})
    assert strict == {'count': 1, 'sum_tenths': 31, 'avg_numerator': 31, 'avg_denominator': 10}
    assert closed['count'] == 2 and closed['sum_tenths'] == 61


def test_exact_reference_rejects_unknown_identifier():
    with pytest.raises(ValueError, match='column'):
        implementation().exact_range(sqlite3.connect(':memory:'), 'DISTANCE); DROP TABLE flights', 0, 1)


@pytest.mark.parametrize('rows', [0,20001,-1])
def test_fit_size_is_bounded_before_fitting(rows):
    with pytest.raises(ValueError, match='20K'):
        implementation().require_fit_size(rows)


def test_all_original_queries_have_explicit_support_status():
    support = implementation().query_support()
    assert len(support) == 12
    assert [x['name'] for x in support] == ['F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2']
    assert support[8]['status'] == 'SUPPORTED'
    assert support[9]['status'] == 'UNSUPPORTED' and support[9]['reason']
    assert all(x['status'] in ['SUPPORTED','UNSUPPORTED'] for x in support)


def test_source_seal_refuses_changed_bytes(tmp_path):
    source = tmp_path / 'engine.py'
    source.write_bytes(b'original')
    expected = hashlib.sha256(b'original').hexdigest()
    implementation().check_file(source, expected)
    source.write_bytes(b'changed!')
    with pytest.raises(ValueError, match='checksum'):
        implementation().check_file(source, expected)


def test_gaussian_reference_uses_population_N_not_fit_n():
    reference = implementation().gaussian_moments
    first = reference([0.,0.], 0., 1., 1., float('-inf'), float('inf'), 10)
    larger = reference([0.,0.], 0., 1., 1., float('-inf'), float('inf'), 100)
    assert first['count'] == pytest.approx(10)
    assert larger['count'] == pytest.approx(100)
    assert first['sum'] == pytest.approx(10)
    assert larger['avg'] == pytest.approx(1)


def test_gaussian_reference_has_correct_truncated_first_moment():
    result = implementation().gaussian_moments([0.], 1., 0., 1., 0., float('inf'), 10)
    assert result['count'] == pytest.approx(5)
    assert result['sum'] == pytest.approx(3.989422804014327)
    assert result['avg'] == pytest.approx(0.7978845608028654)


@pytest.mark.skipif(not ENGINE_READY,reason='Requires full_dbest.py setup in its independent environment')
def test_actual_official_engine_probe_has_population_scaling_and_call_evidence():
    report = implementation().run_probe()
    assert report['status'] == 'PASS'
    assert report['training_rows'] == 8
    assert report['population_counts'] == [80,800]
    assert report['native_method_calls'] >= 6
    assert report['native_kde_evaluations'] > 0
    assert report['max_sum_relative_error'] < 1e-7
    assert report['max_avg_absolute_error'] < 1e-7
    assert report['max_count_absolute_error'] <= 1
    assert report['source_bytes_unchanged'] is True
    assert report['default_population_if_N_omitted']==8
    assert report['sample_as_population']['values']['sum']==pytest.approx(32)
    assert report['explicit_population_sum_multiplier']==pytest.approx(10)
    assert report['multidimensional']['exception_type']=='ValueError'


@pytest.mark.skipif(not (ENGINE_READY and GOLD_READY),reason='Requires the independent engine and sealed Flights200K inputs')
def test_frozen_200k_gate_queries_are_real_and_numerically_verified():
    report=implementation().run_small()
    assert report['status']=='PASS'
    assert report['population_rows']==200000 and report['unique_fit_rows']==20000
    assert report['native_method_calls']>=74
    assert report['all_12_sqlite_states_match_sealed_truth']
    assert report['input_bytes_unchanged'] and report['source_bytes_unchanged']
    assert {x['name'] for x in report['queries']}=={'F1.1','F1.2','F3.1','F4.1'}
    assert all(x['all_native_integrals_verified'] for x in report['queries'])


@pytest.mark.skipif(not (ENGINE_READY and GOLD_READY),reason='Requires the independent engine and sealed Flights200K inputs')
def test_wide_domain_integration_regression_preserves_failed_native_evidence():
    report=implementation().run_small()
    failure=implementation().OUTPUT/'numerical_failure_F1.2_all.json'
    import json
    before=json.loads(failure.read_text())
    after=next(x for x in report['queries'] if x['name']=='F1.2')['predictions'][0]['native']
    assert before['integral_verified'] is False
    assert before['oracle_absolute_errors']['avg']>30
    assert after['integral_verified'] is True
    assert after['oracle_absolute_errors']['avg']<1e-5
    assert after['numerical_adapter']['kde_and_regression_unchanged']


@pytest.mark.skipif(not GOLD_READY,reason='Requires frozen SQLite truth to exercise real state/SQL alignment')
def test_truncated_truth_cannot_be_misreported_as_all_twelve_queries(tmp_path,monkeypatch):
    import json
    module=implementation()
    state=json.loads((module.GOLD_OUTPUT/'sqlite_exact_state.json').read_text())
    state['aggregates'].pop()
    (tmp_path/'sqlite_exact_state.json').write_text(json.dumps(state))
    monkeypatch.setattr(module,'GOLD_OUTPUT',tmp_path)
    with pytest.raises(ValueError,match='12'):
        module.read_gold_truth()
