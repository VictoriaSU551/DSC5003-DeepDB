import sqlite3

from full_postgres import star_count_query


def test_preaggregation_preserves_duplicate_join_multiplicities_and_filters():
    connection = sqlite3.connect(':memory:')
    connection.executescript('''
      CREATE TABLE title(id integer PRIMARY KEY, production_year integer);
      CREATE TABLE movie_info(id integer, movie_id integer, info_type_id integer);
      CREATE TABLE movie_companies(id integer, movie_id integer, company_type_id integer);
      INSERT INTO title VALUES(1,2010),(2,1990),(3,NULL);
      INSERT INTO movie_info VALUES(1,1,16),(2,1,16),(3,2,16),(4,NULL,16);
      INSERT INTO movie_companies VALUES(1,1,2),(2,1,2),(3,1,1),(4,2,2);
    ''')
    query = ('SELECT COUNT(*) FROM title t,movie_info mi,movie_companies mc '
             'WHERE t.id=mi.movie_id AND t.id=mc.movie_id AND mi.info_type_id=16 '
             'AND mc.company_type_id=2 AND t.production_year>2000;')
    assert connection.execute(query).fetchone()[0] == 4
    assert connection.execute(star_count_query(query)).fetchone()[0] == 4
