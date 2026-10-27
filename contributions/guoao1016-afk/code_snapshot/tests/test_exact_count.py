"""Check exact star-count semantics on duplicates, NULLs and orphan rows."""
import sqlite3
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from joblight_exact_count import factorized_count_sql

QUERY=('SELECT COUNT(*) FROM title t,movie_info mi,movie_companies mc,cast_info ci,movie_keyword mk '
       'WHERE t.id=mi.movie_id AND t.id=mc.movie_id AND t.id=ci.movie_id AND t.id=mk.movie_id '
       'AND ci.role_id=2 AND mi.info_type_id=16 AND t.production_year>2000;')

def toy_database():
    c=sqlite3.connect(':memory:')
    c.executescript('''
      CREATE TABLE title(id INTEGER PRIMARY KEY,production_year INTEGER);
      CREATE TABLE movie_info(movie_id INTEGER,info_type_id INTEGER);
      CREATE TABLE movie_companies(movie_id INTEGER);
      CREATE TABLE cast_info(movie_id INTEGER,role_id INTEGER);
      CREATE TABLE movie_keyword(movie_id INTEGER);
      INSERT INTO title VALUES(1,2003),(2,2011),(3,1990);
      INSERT INTO movie_info VALUES(1,16),(1,16),(2,16),(NULL,16),(99,16),(1,17);
      INSERT INTO movie_companies VALUES(1),(1),(1),(2),(NULL),(99);
      INSERT INTO cast_info VALUES(1,2),(1,2),(1,1),(2,2),(NULL,2),(99,2);
      INSERT INTO movie_keyword VALUES(1),(1),(2),(NULL),(99);
    ''')
    return c

def test_exact_count_preserves_duplicate_multiplicity_and_null_join_semantics():
    c=toy_database()
    original=c.execute(QUERY).fetchone()[0]
    # SQLite lacks PostgreSQL's ::numeric spelling; the small integer fixture
    # needs no wide numeric cast. The relational transformation is unchanged.
    rewritten=c.execute(factorized_count_sql(QUERY).replace('::numeric','')).fetchone()[0]
    assert original==rewritten==25  # movie 1:2*3*2*2; movie 2:1*1*1*1
    c.close()

def test_exact_count_preserves_filters_and_empty_results():
    c=toy_database()
    for query,expected in [(QUERY.replace('>2000','>2010'),1),(QUERY.replace('>2000','>2020'),0),
                           (QUERY.replace('role_id=2','role_id=1'),12)]:
        assert c.execute(query).fetchone()[0]==expected
        assert c.execute(factorized_count_sql(query).replace('::numeric','')).fetchone()[0]==expected
    c.close()

def test_reject_non_star_or_unhandled_predicates():
    for invalid in [QUERY.replace('t.id=mk.movie_id','ci.movie_id=mk.movie_id'),
                    QUERY.replace(' AND t.id=mk.movie_id',''),
                    QUERY.replace('ci.role_id=2','ci.role_id=mi.info_type_id'),
                    QUERY.replace('COUNT(*)','COUNT(DISTINCT t.id)')]:
        with pytest.raises(ValueError):factorized_count_sql(invalid)
