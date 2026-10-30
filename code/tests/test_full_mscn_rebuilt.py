"""Independent SQL bitmap semantics and actual checkpoint continuation."""
import importlib
import random
import struct

import numpy as np
import pytest


def module():
    try:
        return importlib.import_module('full_mscn_rebuilt')
    except ModuleNotFoundError as exc:
        if exc.name != 'full_mscn_rebuilt':
            raise
        pytest.fail('Independent consistent-bitmap MSCN implementation is missing')


def sample():
    return {'table': 'title', 'alias': 't', 'columns': {
        'id': list(range(1, 9)), 'kind_id': [1, 1, 2, 2, 1, 2, 1, 2],
        'production_year': [None, 1991, 1992, 1993, 1994, 1995, None, 2000]}}


def test_null_sentinel_restoration_and_independent_sql_unknown_semantics():
    m = module()
    sentinel = 1992.7887619952553
    restored = m.restore_sql_values([1980., sentinel, 2000., float('nan')], sentinel)
    assert restored == [1980, None, 2000, None]
    fixed = {'table': 'title', 'alias': 't', 'columns': {'id': [1, 2, 3, 4], 'production_year': restored}}
    for predicates in [[], [('production_year', '>', 1992)], [('production_year', '<=', 2000)],
                       [('production_year', '=', 1992)]]:
        assert np.array_equal(m.predicate_bitmap(fixed, predicates), m.sqlite_bitmap(fixed, predicates))
    assert m.predicate_bitmap(fixed, []).tolist() == [True, True, True, True]
    assert m.predicate_bitmap(fixed, [('production_year', '>', 1992)]).tolist() == [False, False, True, False]


def test_all_comparison_boundaries_multiple_predicates_and_empty_result_match_sql():
    m = module()
    for operator in ['=', '<', '>', '<=', '>=']:
        for boundary in [1900, 1992, 1993, 2001]:
            predicates = [('production_year', operator, boundary)]
            assert np.array_equal(m.predicate_bitmap(sample(), predicates), m.sqlite_bitmap(sample(), predicates))
    for predicates in [[('production_year', '>', 1991), ('kind_id', '=', 1)],
                       [('production_year', '>', 2025)], []]:
        assert np.array_equal(m.predicate_bitmap(sample(), predicates), m.sqlite_bitmap(sample(), predicates))


def test_integer_closed_bound_conversion_is_explicitly_equivalent_to_sql():
    m = module()
    for original, expected in [(('production_year', '>=', '1992'), ('production_year', '>', 1991)),
                               (('production_year', '<=', '1992'), ('production_year', '<', 1993))]:
        converted = m.canonical_predicate(*original)
        assert converted == expected
        assert np.array_equal(m.sqlite_bitmap(sample(), [original]), m.sqlite_bitmap(sample(), [converted]))
    with pytest.raises(ValueError, match='integer'):
        m.canonical_predicate('production_year', '<=', '1992.5')
    with pytest.raises(ValueError, match='overflow|range'):
        m.canonical_predicate('production_year', '<=', str(2 ** 63 - 1))


def test_alias_resolution_table_order_and_most_significant_bit_first():
    m = module()
    title = sample()
    cast = {'table': 'cast_info', 'alias': 'ci', 'columns': {'id': list(range(8)), 'role_id': [1] + [2] * 7}}
    row = ['cast_info z,title x', 'x.id=z.id', 'z.role_id,=,1,x.kind_id,=,1', '7']
    payload = m.bitmap_record(row, {'title': title, 'cast_info': cast})
    assert struct.unpack('<I', payload[:4])[0] == 2
    assert payload[4:] == bytes([0b10000000, 0b11001010])
    reverse = ['title x,cast_info z', row[1], row[2], row[3]]
    assert m.bitmap_record(reverse, {'title': title, 'cast_info': cast})[4:] == bytes([0b11001010, 0b10000000])


def test_unknown_operator_alias_column_or_ambiguous_tables_are_rejected():
    m = module()
    for row in [['title t', '', 't.kind_id,!=,1', '7'],
                ['title t', '', 'x.kind_id,=,1', '7'],
                ['title t', '', 't.missing,=,1', '7'],
                ['title t,title x', '', '', '7']]:
        with pytest.raises(ValueError, match='operator|alias|column|table'):
            m.bitmap_record(row, {'title': sample()})


def test_table_sampling_is_uniform_without_replacement_and_does_not_consume_global_rng():
    m = module()
    random.seed(17)
    before = random.getstate()
    values = m.sample_positions(36244344, 'cast_info', 1, 1000)
    assert random.getstate() == before
    assert len(values) == len(set(values)) == 1000
    assert min(values) >= 0 and max(values) < 36244344
    assert values == m.sample_positions(36244344, 'cast_info', 1, 1000)
    assert values != m.sample_positions(36244344, 'cast_info', 2, 1000)


def test_materialized_cache_rejects_same_length_bitmap_tamper(tmp_path):
    import json
    m = module()
    bitmap = tmp_path / 'train.bitmaps'
    bitmap.write_bytes(b'12345678')
    record = m.base.file_record(bitmap, tmp_path)
    (tmp_path / 'manifest.json').write_text(json.dumps({'status': 'PASS', 'artifacts': [record]}))
    m.validate_rebuilt_manifest(tmp_path)
    bitmap.write_bytes(b'12345679')
    with pytest.raises(ValueError, match='changed|hash|SHA'):
        m.validate_rebuilt_manifest(tmp_path)


def test_checkpoint_next_update_restores_adam_all_rngs_and_preserves_epoch_one(tmp_path):
    torch = pytest.importorskip('torch')
    m = module()
    torch.manual_seed(1)
    np.random.seed(1)
    random.seed(1)
    def create_pair():
        net = torch.nn.Linear(2, 1)
        return net, torch.optim.Adam(net.parameters(), lr=.001)
    model, optimizer = create_pair()
    def step(net, optim):
        optim.zero_grad()
        loss = net(torch.tensor([[1., 2.]])).square().sum()
        loss.backward()
        optim.step()
        return float(loss.item())
    step(model, optimizer)
    before = {key: value.clone() for key, value in model.state_dict().items()}
    binding = {'mode': 'rebuilt_checkpoint_test', 'seed': 1}
    committed = m.base.save_training_checkpoint(tmp_path, 1, binding, model, optimizer, [{'epoch': 1}])
    result = m.verify_next_update_restoration(tmp_path, binding, model, optimizer, step, create_pair)
    assert result['status'] == 'PASS'
    assert result['model_equal'] and result['adam_equal'] and result['rng_equal']
    assert all(torch.equal(before[key], value) for key, value in model.state_dict().items())
    assert m.base.checkpoint_record(tmp_path, binding) == committed


def test_public_sql_conversion_preserves_table_order_resolves_aliases_and_closed_bounds():
    m = module()
    sql = 'SELECT COUNT(*) FROM title x,cast_info z WHERE x.id=z.movie_id AND z.person_id>=20 AND x.production_year<=2000;'
    row = m.sql_to_row(sql, 17, {'t.id=ci.movie_id'})
    assert row == ['title t,cast_info ci', 't.id=ci.movie_id',
                   'ci.person_id,>,19,t.production_year,<,2001', '17']


@pytest.mark.parametrize('condition', ['t.kind_id != 1', 't.kind_id=1 OR t.kind_id=2', "t.kind_id LIKE '1'", 'x.kind_id=1'])
def test_public_sql_does_not_silently_accept_unsupported_or_undeclared_conditions(condition):
    with pytest.raises(ValueError):
        module().sql_to_row('SELECT COUNT(*) FROM title t WHERE ' + condition + ';', 17, set())


def test_query_joint_seal_changes_with_samples_table_order_truth_or_bitmap():
    m = module()
    row = ['title t,cast_info ci', 't.id=ci.movie_id', 't.kind_id,=,1', '17']
    before = m.query_joint_sha(row, b'bitmap-a', 'samples-a', {'source_sha256': 'source-a', 'query_no': 0})
    changes = [m.query_joint_sha(row, b'bitmap-b', 'samples-a', {'source_sha256': 'source-a', 'query_no': 0}),
               m.query_joint_sha(row, b'bitmap-a', 'samples-b', {'source_sha256': 'source-a', 'query_no': 0}),
               m.query_joint_sha([row[0], row[1], row[2], '18'], b'bitmap-a', 'samples-a', {'source_sha256': 'source-a', 'query_no': 0}),
               m.query_joint_sha(['cast_info ci,title t', row[1], row[2], row[3]], b'bitmap-a', 'samples-a', {'source_sha256': 'source-a', 'query_no': 0})]
    assert all(value != before for value in changes)


def test_nonfinite_model_or_adam_is_rejected_before_epoch_commit():
    torch = pytest.importorskip('torch')
    m = module()
    model = torch.nn.Linear(2, 1)
    optimizer = torch.optim.Adam(model.parameters())
    m.assert_finite_model_adam(model, optimizer)
    with torch.no_grad():
        model.weight[0, 0] = float('inf')
    with pytest.raises(ValueError, match='finite'):
        m.assert_finite_model_adam(model, optimizer)
    with torch.no_grad():
        model.weight.fill_(1.)
    optimizer.state[model.weight]['exp_avg'] = torch.tensor([float('nan')])
    with pytest.raises(ValueError, match='finite'):
        m.assert_finite_model_adam(model, optimizer)

