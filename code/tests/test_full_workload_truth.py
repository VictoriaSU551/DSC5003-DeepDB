import json

import pytest

from full_workload_truth import logical_query, store_count, load_count


def test_truth_cache_ignores_alias_order_but_preserves_predicate_semantics():
    a = ('SELECT COUNT(*) FROM title t,cast_info ci WHERE t.id=ci.movie_id '
         'AND ci.person_id>100 AND t.production_year<2000;')
    b = ('select count(*) from cast_info c,title z where z.production_year < 2000 '
         'AND z.id=c.movie_id AND c.person_id > 100;')
    assert logical_query(a) == logical_query(b)
    assert logical_query(a) != logical_query(a.replace('person_id>100', 'person_id>=100'))


def test_count_cache_requires_sealed_input_and_integer_result(tmp_path):
    target = tmp_path / 'count.json'
    binding = {'data': 'snapshot', 'query': 'fixed'}
    store_count(target, binding, 2 ** 60 + 1, 'independent exact SQL')
    assert load_count(target, binding)['count'] == 2 ** 60 + 1
    with pytest.raises(ValueError, match='binding'):
        load_count(target, {'data': 'changed', 'query': 'fixed'})
    record = json.loads(target.read_text())
    record['count'] += 1
    target.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='seal'):
        load_count(target, binding)
