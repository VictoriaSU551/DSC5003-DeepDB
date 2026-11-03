"""Recovery and independent SQL checks for the Flights streaming adapter."""
import importlib
import json

import numpy as np
import pandas as pd
import pytest


def implementation():
    try:
        return importlib.import_module('full_flights_generate')
    except ModuleNotFoundError as exc:
        if exc.name != 'full_flights_generate':
            raise
        pytest.fail('Flights streaming implementation is not present')


def frame():
    return pd.DataFrame([
        [1995, 'TW', 'ATL', 'LA', 'JFK', 'CA', 1600.1, 20.2, 5.1, 1300.2, 1500.1, 3000.1],
        [2005, 'UA', 'ATL', 'CA', 'HNL', 'HI', 1601.2, 25.3, 5.2, 1301.3, 1501.2, 3001.2],
        [2005, '9E', 'PHX', 'LA', 'HPN', 'CA', 1202.3, 26.4, 6.3, 1002.4, 300.3, 400.3],
        [2016, 'UA', 'ATL', 'LA', 'JFK', 'CA', 1603.4, 27.5, 7.4, 1303.5, 1503.4, 3003.4],
        [2005, 'TW', 'PHX', 'LA', 'HPN', 'NY', 1204.5, 28.6, 8.5, 1004.6, 304.5, 404.5],
        [2016, '9E', 'ATL', 'CA', 'HNL', 'HI', 1605.6, 29.7, 9.6, 1305.7, 1505.6, 3005.6],
    ], columns=['YEAR_DATE', 'UNIQUE_CARRIER', 'ORIGIN', 'ORIGIN_STATE_ABR',
                'DEST', 'DEST_STATE_ABR', 'DEP_DELAY', 'TAXI_OUT', 'TAXI_IN',
                'ARR_DELAY', 'AIR_TIME', 'DISTANCE'])


def binding(aqp):
    return {'config': aqp.parameters(rows=6, batch_size=3, sample_rate=0.5,
                                     retain_population=True),
            'input_seal': {'csv': 'source-A', 'descriptor': 'descriptor-A'}}


def run(aqp, tmp_path, name, seal):
    return aqp.StreamRun(tmp_path / 'output' / name, tmp_path / 'data' / name, seal)


def test_resume_truncates_uncommitted_sample_and_population_tails(tmp_path):
    aqp = implementation()
    seal = binding(aqp)
    continuous = run(aqp, tmp_path, 'continuous', seal)
    continuous.accept(frame().iloc[:3], 0)
    continuous.accept(frame().iloc[3:], 1)
    continuous.finish()
    partial = run(aqp, tmp_path, 'resumed', seal)
    partial.accept(frame().iloc[:3], 0)
    sample_offset = partial.state['files']['sample.csv']['offset']
    population_offset = partial.state['files']['population.csv']['offset']
    for name in ['sample.csv', 'population.csv']:
        with (partial.data_dir / name).open('ab') as stream:
            stream.write(b'UNCOMMITTED ROW AFTER INTERRUPTION\n')
    resumed = run(aqp, tmp_path, 'resumed', seal)
    assert resumed.next_batch == 1
    assert (resumed.data_dir / 'sample.csv').stat().st_size == sample_offset
    assert (resumed.data_dir / 'population.csv').stat().st_size == population_offset
    resumed.accept(frame().iloc[3:], 1)
    resumed.finish()
    assert resumed.state['aggregates'] == continuous.state['aggregates']
    assert resumed.state['sample_rows'] == continuous.state['sample_rows']
    for name in ['sample.csv', 'population.csv']:
        assert (resumed.data_dir / name).read_bytes() == (continuous.data_dir / name).read_bytes()


@pytest.mark.parametrize('kind', ['generation_seed', 'sampling_seed', 'input'])
def test_changed_inputs_or_seeds_are_rejected_before_truncation(tmp_path, kind):
    aqp = implementation()
    seal = binding(aqp)
    original = run(aqp, tmp_path, 'resume', seal)
    original.accept(frame().iloc[:3], 0)
    with (original.data_dir / 'sample.csv').open('ab') as stream:
        stream.write(b'UNCOMMITTED')
    before = (original.data_dir / 'sample.csv').read_bytes()
    changed = json.loads(json.dumps(seal))
    if kind == 'input':
        changed['input_seal']['csv'] = 'source-B'
    else:
        changed['config'][kind] += 1
    with pytest.raises(aqp.StreamError, match='[Bb]inding'):
        run(aqp, tmp_path, 'resume', changed)
    assert (original.data_dir / 'sample.csv').read_bytes() == before


def test_committed_prefix_corruption_is_rejected(tmp_path):
    aqp = implementation()
    seal = binding(aqp)
    original = run(aqp, tmp_path, 'resume', seal)
    original.accept(frame().iloc[:3], 0)
    path = original.data_dir / 'population.csv'
    data = bytearray(path.read_bytes())
    data[-4] ^= 1
    path.write_bytes(data)
    with pytest.raises(aqp.StreamError, match='[Hh]ash|[Pp]refix'):
        run(aqp, tmp_path, 'resume', seal)


def test_sampling_does_not_change_authors_global_numpy_state(tmp_path):
    aqp = implementation()
    writer = run(aqp, tmp_path, 'global_rng', binding(aqp))
    np.random.seed(51)
    before = np.random.get_state()
    writer.accept(frame().iloc[:3], 0)
    after = np.random.get_state()
    assert before[0] == after[0] and before[2:] == after[2:]
    assert np.array_equal(before[1], after[1])


def test_completed_batches_cannot_be_replayed(tmp_path):
    aqp = implementation()
    writer = run(aqp, tmp_path, 'no_replay', binding(aqp))
    writer.accept(frame().iloc[:3], 0)
    before = (writer.data_dir / 'sample.csv').read_bytes()
    with pytest.raises(aqp.StreamError, match='[Bb]atch'):
        writer.accept(frame().iloc[:3], 0)
    assert (writer.data_dir / 'sample.csv').read_bytes() == before


def test_all_twelve_aggregates_match_independent_sqlite_integer_sql(tmp_path):
    aqp = implementation()
    writer = run(aqp, tmp_path, 'sql', binding(aqp))
    writer.accept(frame().iloc[:3], 0)
    writer.accept(frame().iloc[3:], 1)
    writer.finish()
    truth = aqp.sqlite_reference(writer.data_dir / 'population.csv', tmp_path / 'reference.sqlite')
    assert len(truth['aggregates']) == 12
    assert all(query['groups'] for query in truth['aggregates'])
    assert writer.state['aggregates'] == truth['aggregates']


def test_short_output_and_corrupt_checkpoint_fail_closed(tmp_path):
    aqp = implementation()
    seal = binding(aqp)
    writer = run(aqp, tmp_path, 'short', seal)
    writer.accept(frame().iloc[:3], 0)
    (writer.data_dir / 'sample.csv').write_bytes(b'')
    with pytest.raises(aqp.StreamError, match='[Ss]hort|[Oo]ffset'):
        run(aqp, tmp_path, 'short', seal)
    other = run(aqp, tmp_path, 'checkpoint', seal)
    saved = json.loads(other.checkpoint.read_text(encoding='utf-8'))
    saved['rows_generated'] = 123
    other.checkpoint.write_text(json.dumps(saved), encoding='utf-8')
    with pytest.raises(aqp.StreamError, match='[Cc]heckpoint'):
        run(aqp, tmp_path, 'checkpoint', seal)
