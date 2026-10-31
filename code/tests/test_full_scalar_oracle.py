"""The estimator may see only independent single-table cardinalities."""
from fractions import Fraction
from pathlib import Path
import importlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def core():
    try:
        return importlib.import_module('full_scalar_oracle')
    except ModuleNotFoundError:
        pytest.fail('Missing scalar-oracle implementation')


def test_fixed_workload_registers_all_sqls_and_no_multi_table_count(core):
    contract = core.workload()
    assert len(contract['queries']) == 70
    assert len(contract['predicates']) == 50
    assert set(contract['tables']) == {'title', 'cast_info', 'movie_info', 'movie_info_idx', 'movie_keyword', 'movie_companies'}
    assert [q['query_no'] for q in contract['queries']] == list(range(70))
    for table, statement in core.count_statements(contract).items():
        assert statement['sql'].count('FROM') == 1
        assert 'JOIN' not in statement['sql']
        assert 'public."' + table + '"' in statement['sql']
    assert sum(len(s['predicate_ids']) for s in core.count_statements(contract).values()) == 50


def test_correlated_toy_is_an_explicit_uniform_key_approximation(core):
    query = core.parse_query('SELECT COUNT(*) FROM title t,movie_info a,movie_keyword b WHERE t.id=a.movie_id AND t.id=b.movie_id AND t.production_year>2000;', 0)
    # Independent exact integer single-table oracle. Two qualifying titles;
    # three a rows and two b rows, with a duplicated join key retained.
    titles = [(1, 2001), (2, 2002), (3, 1999), (4, None)]
    a = [1, 1, 2]; b = [1, 3]
    counts = {p['id']: {'title': 2, 'movie_info': 3, 'movie_keyword': 2}[p['table']] for p in query['predicates']}
    estimate = core.uniform_estimate(query, counts, 4)
    exact_join = sum(1 for key, year in titles for x in a for y in b if year is not None and year > 2000 and key == x == y)
    assert exact_join == 2
    assert estimate == Fraction(3, 4)
    assert estimate != exact_join  # The method does not pretend to recover correlations.


def test_zero_is_not_replaced_by_metric_floor(core):
    query = core.parse_query('SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id;', 0)
    counts = {p['id']: (0 if p['table'] == 'movie_info' else 4) for p in query['predicates']}
    assert core.uniform_estimate(query, counts, 4) == 0
    assert core.rational_record(Fraction(0)) == {'numerator': '0', 'denominator': '1'}


def test_integer_oracle_above_float_precision_is_exact(core):
    query = core.parse_query('SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id;', 0)
    n = 2**54 + 1
    counts = {p['id']: (n if p['table'] == 'title' else n + 2) for p in query['predicates']}
    assert core.uniform_estimate(query, counts, n) == n + 2


@pytest.mark.parametrize('sql', [
    'SELECT COUNT(*) FROM title t,movie_info a WHERE t.production_year=2000;',
    'SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id AND t.id=a.movie_id;',
    'SELECT COUNT(*) FROM title t,movie_info t WHERE t.id=t.movie_id;',
    'SELECT COUNT(*) FROM title t,title u WHERE t.id=u.id;',
    'SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id OR t.kind_id=1;',
    'SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id; DROP TABLE title;',
    'SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id AND a.info IS NULL;',
    'SELECT SUM(t.id) FROM title t,movie_info a WHERE t.id=a.movie_id;',
])
def test_unsupported_or_ambiguous_sql_never_reaches_database(core, sql):
    with pytest.raises(ValueError):
        core.parse_query(sql, 0)


@pytest.mark.parametrize('bad', [-1, True, 1.5, '2', None])
def test_non_integer_or_negative_oracle_cannot_be_estimated(core, bad):
    q = core.parse_query('SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id;', 0)
    with pytest.raises(ValueError):
        core.uniform_estimate(q, {p['id']: bad for p in q['predicates']}, 4)


def test_changed_workload_is_rejected_before_parsing(core, tmp_path):
    p = tmp_path / 'changed.sql'; p.write_text('SELECT 1;')
    with pytest.raises(ValueError, match='workload'):
        core.workload(p)


def test_count_statements_parameterize_literals_and_share_conjunctions(core):
    q = core.parse_query('SELECT COUNT(*) FROM title t,movie_info a WHERE t.id=a.movie_id AND t.production_year>2000 AND t.production_year<2010;', 0)
    contract = core.contract_from_queries([q])
    sql = core.count_statements(contract)['title']
    assert sql['parameters'] == [2000, 2010]
    assert '2000' not in sql['sql'] and '2010' not in sql['sql']
    assert '"production_year" > %s AND "production_year" < %s' in sql['sql']


def test_complete_counts_and_assumptions_gate_rejects_gaps(core):
    c = core.workload()
    counts = {p['id']: 0 if p['conditions'] else core.EXPECTED_ROWS[p['table']] for p in c['predicates']}
    population = dict(core.EXPECTED_ROWS)
    assumptions = {t: {'rows': n, 'distinct_ids': n, 'null_ids': 0, 'null_movie_ids': 0, 'orphan_movie_ids': 0} for t,n in population.items()}
    core.validate_counts(c, counts, population, assumptions)
    for field in ['distinct_ids', 'null_ids', 'null_movie_ids', 'orphan_movie_ids']:
        bad = {k: dict(v) for k,v in assumptions.items()}
        bad['movie_info'][field] = population['movie_info'] - 1 if field == 'distinct_ids' else 1
        with pytest.raises(ValueError):
            core.validate_counts(c, counts, population, bad)
    with pytest.raises(ValueError):
        core.validate_counts(c, dict(list(counts.items())[1:]), population, assumptions)
