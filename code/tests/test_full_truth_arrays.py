import sqlite3

import numpy as np

from full_truth_arrays import NULL, exact_sum_products, count_star, filter_rows


def test_sql_null_duplicate_multiplicity_and_filtered_inner_join_match_sqlite():
    tables = {'title': {'id': np.array([1, 2, 3]), 'production_year': np.array([2000, NULL, 2010])},
              'movie_info': {'movie_id': np.array([1, 1, 2, 3, NULL]), 'info_type_id': np.array([1, 1, 1, 2, 1])},
              'cast_info': {'movie_id': np.array([1, 1, 1, 2, 3]), 'role_id': np.array([1, 1, 2, 1, 1])}}
    query = {'tables': list(tables), 'predicates': {'title': [['production_year', '>=', '2000']],
             'movie_info': [['info_type_id', '=', '1']], 'cast_info': [['role_id', '<', '2']]}}
    db = sqlite3.connect(':memory:')
    for table, columns in tables.items():
        db.execute('CREATE TABLE ' + table + ' (' + ','.join(columns) + ')')
        rows = [[None if int(x) == NULL else int(x) for x in row] for row in zip(*columns.values())]
        db.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in columns) + ')', rows)
    expected = db.execute('SELECT COUNT(*) FROM title t JOIN movie_info m ON t.id=m.movie_id '
                          'JOIN cast_info c ON t.id=c.movie_id WHERE t.production_year>=2000 '
                          'AND m.info_type_id=1 AND c.role_id<2').fetchone()[0]
    assert expected == count_star(tables, query) == 4
    assert filter_rows(tables['title'], [['production_year', '<', '0']]).tolist() == [False, False, False]


def test_exact_product_and_sum_do_not_overflow_uint64():
    assert exact_sum_products([np.array([2**32, 2**32], dtype=np.uint64)] * 2) == 2**65
    assert exact_sum_products([np.array([2**53+1], dtype=np.uint64), np.array([3], dtype=np.uint64)]) == (2**53+1)*3
