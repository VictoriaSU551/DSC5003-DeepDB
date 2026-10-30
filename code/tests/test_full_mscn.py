"""Input pairing and committed epoch recovery must fail closed."""
import importlib
import importlib.util
import json
import random
import runpy
from pathlib import Path
import struct

import pytest


ROOT = Path(__file__).resolve().parents[2]


def module():
    assert importlib.util.find_spec('full_mscn') is not None, 'MSCN wrapper is not implemented'
    return importlib.import_module('full_mscn')


def pair(tmp_path, rows, table_counts):
    csv_path = tmp_path / 'queries.csv'
    bitmap = tmp_path / 'queries.bitmaps'
    csv_path.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    with bitmap.open('wb') as stream:
        for count in table_counts:
            stream.write(struct.pack('<I', count))
            stream.write(bytes([128]) * (125 * count))
    return csv_path, bitmap


def test_bitmap_query_count_and_table_order_pairing(tmp_path):
    # Omitting the row-wise bitmap count check would accept a shifted input.
    csv_path, bitmap = pair(tmp_path, ['title t##t.kind_id,=,1#7',
                                      'title t,cast_info ci#t.id=ci.movie_id##11'], [1, 2])
    report = module().inspect_pair(csv_path, bitmap)
    assert report['queries'] == 2
    assert report['bitmap_bytes'] == 383
    assert report['table_count_histogram'] == {'1': 1, '2': 1}
    bitmap.write_bytes(struct.pack('<I', 2) + bytes(250) + struct.pack('<I', 1) + bytes(125))
    with pytest.raises(ValueError, match='bitmap table count.*row 1'):
        module().inspect_pair(csv_path, bitmap)


@pytest.mark.parametrize('tail', ['truncated', 'trailing'])
def test_partial_or_extra_bitmap_bytes_are_rejected(tmp_path, tail):
    csv_path, bitmap = pair(tmp_path, ['title t###7'], [1])
    payload = bitmap.read_bytes()
    bitmap.write_bytes(payload[:-1] if tail == 'truncated' else payload + b'\x00')
    with pytest.raises(ValueError, match='truncated|trailing'):
        module().inspect_pair(csv_path, bitmap)


def test_job_truth_permutation_rejected_even_if_same_length(tmp_path):
    job = tmp_path / 'job.csv'
    job.write_text('title t##t.kind_id,=,1#7\ntitle t##t.kind_id,=,2#11\n', encoding='utf-8')
    truth = tmp_path / 'truth.csv'
    truth.write_text('query_no,query,cardinality_true\n'
                     '0,SELECT COUNT(*) FROM title t WHERE t.kind_id=2;,11\n'
                     '1,SELECT COUNT(*) FROM title t WHERE t.kind_id=1;,7\n', encoding='utf-8')
    with pytest.raises(ValueError, match='JOB query mismatch.*row 1'):
        module().inspect_job_truth(job, truth)


def test_real_table1_inputs_match_and_source_change_is_rejected(tmp_path):
    m = module()
    result = m.audit_inputs(ROOT)
    assert result['train']['queries'] == 100000
    assert result['job_light']['queries'] == 70
    assert result['job_truth_alignment'] == 'PASS'
    # A source artifact changed after sealing cannot be silently accepted.
    copied = tmp_path / 'source.py'
    copied.write_text('original', encoding='utf-8')
    record = m.file_record(copied, tmp_path)
    copied.write_text('modified', encoding='utf-8')
    with pytest.raises(ValueError, match='sealed artifact changed'):
        m.verify_records([record], tmp_path)


def test_missing_checkpoint_starts_at_epoch_zero_without_creating_artifact(tmp_path):
    assert module().checkpoint_record(tmp_path, {'seed': 1}) is None
    assert list(tmp_path.iterdir()) == []


def test_checkpoint_resumes_only_uncompleted_epochs_and_rejects_mutation(tmp_path):
    m = module()
    artifact = tmp_path / 'epoch_000003.pt'
    artifact.write_bytes(b'committed epoch three')
    binding = {'seed': 1, 'training_input_sha256': 'abc'}
    m.commit_checkpoint_record(tmp_path, artifact, 3, binding)
    record = m.checkpoint_record(tmp_path, binding)
    assert record['completed_epochs'] == 3
    assert m.pending_epochs(record, 5) == [4, 5]
    assert m.pending_epochs(record, 3) == []
    artifact.write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='sealed artifact changed'):
        m.checkpoint_record(tmp_path, binding)


def test_checkpoint_refuses_changed_protocol_instead_of_restarting(tmp_path):
    m = module()
    artifact = tmp_path / 'epoch_000001.pt'
    artifact.write_bytes(b'epoch one')
    m.commit_checkpoint_record(tmp_path, artifact, 1, {'seed': 1})
    with pytest.raises(ValueError, match='checkpoint binding mismatch'):
        m.checkpoint_record(tmp_path, {'seed': 2})


def test_uncommitted_epoch_does_not_supersede_last_committed_checkpoint(tmp_path):
    m = module()
    first = tmp_path / 'epoch_000001.pt'
    first.write_bytes(b'epoch one')
    m.commit_checkpoint_record(tmp_path, first, 1, {'seed': 1})
    (tmp_path / 'epoch_000002.pt').write_bytes(b'interrupted write')
    record = m.checkpoint_record(tmp_path, {'seed': 1})
    assert record['completed_epochs'] == 1
    assert record['artifact']['path'] == 'epoch_000001.pt'


def small_real_training_input(tmp_path, count=22):
    data = tmp_path / 'data'
    data.mkdir()
    source = ROOT / 'data/mscn/data'
    rows = (source / 'train.csv').read_text().splitlines()[:count]
    (data / 'train.csv').write_text('\n'.join(rows) + '\n')
    size = sum(4 + 125 * len(row.split('#')[0].split(',')) for row in rows)
    (data / 'train.bitmaps').write_bytes((source / 'train.bitmaps').read_bytes()[:size])
    (data / 'column_min_max_vals.csv').write_bytes((source / 'column_min_max_vals.csv').read_bytes())
    return tmp_path


@pytest.mark.filterwarnings('ignore:.*U.*mode is deprecated:DeprecationWarning')
def test_lazy_dataset_matches_upstream_encoded_tensors_including_padding(tmp_path, monkeypatch):
    # A different split/vocabulary, bit order, normalization or padding breaks equality.
    torch = pytest.importorskip('torch')
    m = module()
    assert hasattr(m, 'prepare_datasets'), 'Lazy paired MSCN Dataset is not implemented'
    data_root = small_real_training_input(tmp_path)
    official, upstream = m.official_modules()
    monkeypatch.chdir(data_root)
    expected = upstream.get_train_datasets(20, 1000)
    actual = m.prepare_datasets(data_root, 20)
    assert len(actual['train']) == 18
    assert len(actual['validation']) == 2
    for name, upstream_dataset in [('train', expected[-2]), ('validation', expected[-1])]:
        for i in range(len(upstream_dataset)):
            assert all(torch.equal(a, b) for a, b in zip(actual[name][i], upstream_dataset[i]))
    assert actual['min_val'] == expected[2]
    assert actual['max_val'] == expected[3]


def test_torch_checkpoint_restores_model_adam_and_all_rngs(tmp_path):
    # Dropping optimizer moments or RNG state changes the first resumed update.
    torch = pytest.importorskip('torch')
    import numpy as np
    m = module()
    assert hasattr(m, 'save_training_checkpoint'), 'Torch checkpoint persistence is not implemented'
    torch.manual_seed(7)
    random.seed(7)
    np.random.seed(7)
    model = torch.nn.Linear(2, 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    x = torch.tensor([[1., 2.]])

    def step():
        optimizer.zero_grad()
        model(x).square().sum().backward()
        optimizer.step()

    step()
    m.save_training_checkpoint(tmp_path, 1, {'seed': 7}, model, optimizer, [{'epoch': 1}])
    expected_rng = (torch.rand(3), np.random.random(3), random.random())
    step()
    expected_weights = {k: v.clone() for k, v in model.state_dict().items()}
    step()
    history = m.restore_training_checkpoint(tmp_path, {'seed': 7}, model, optimizer)
    assert history == [{'epoch': 1}]
    assert torch.equal(torch.rand(3), expected_rng[0])
    assert np.array_equal(np.random.random(3), expected_rng[1])
    assert random.random() == expected_rng[2]
    step()
    assert all(torch.equal(v, expected_weights[k]) for k, v in model.state_dict().items())


def test_audit_cli_writes_sources_and_never_creates_training_checkpoint(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['full_mscn.py', 'audit'])
    runpy.run_path(str(ROOT / 'code/full_mscn.py'), run_name='__main__')
    output = capsys.readouterr().out.strip()
    assert output, 'MSCN audit CLI is not implemented'
    assert json.loads(output)['status'] == 'INPUTS_VERIFIED_TRAINING_NOT_IMPLIED'
    saved = json.loads((ROOT / 'output/full/results/mscn_sources.json').read_text(encoding='utf-8'))
    assert saved['train']['queries'] == 100000
    assert saved['job_light']['queries'] == 70
    assert 'completed_epochs' not in saved
