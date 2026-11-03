import full_training as training
import full_training_guard as guard
from full_training_guard import guarded_namespace
from full_common import atomic_json, binding_hash, load_json
import pytest


def test_new_input_identity_isolates_components_selection_and_receipts():
    old = (training.FULL, training.HDF, training.SELECTION, training.PAIRWISE,
           training.PROFILE, training.algorithm_seal)
    with guarded_namespace('f' * 64, 'public-scale') as directory:
        assert training.algorithm_seal() == 'f' * 64
        assert training.FULL == directory
        assert 'public-scale' in str(directory)
        assert training.SELECTION.parent == directory / 'checkpoints'
        assert training.PAIRWISE.parent == directory / 'models'
        assert training.HDF == old[0] / 'prepared/public-scale/hdf'
    assert old == (training.FULL, training.HDF, training.SELECTION, training.PAIRWISE,
                   training.PROFILE, training.algorithm_seal)


def test_input_change_persistently_taints_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'FULL', tmp_path / 'output/full')
    monkeypatch.setattr(guard, 'ROOT', tmp_path)
    plan = dict(profile='joblight', strategy='relationship', samples=100, budget=0.,
                prepared_input_binding={'input': 1}, **guard.runtime_seal())
    observed = iter([{'input': 1}, {'input': 2}])
    monkeypatch.setattr(guard, 'input_binding', lambda profile: next(observed))
    def fake_train(*args):
        atomic_json(training.FULL / 'results/relationship_n100_b0p0_training.json', dict(status='PASS'))
    monkeypatch.setattr(training, 'train', fake_train)
    with pytest.raises(ValueError, match='changed'):
        guard.execute(plan)
    state = guard.FULL / 'guarded_training/joblight' / binding_hash(plan) / 'state.json'
    assert load_json(state)['status'] == 'TAINTED'
    monkeypatch.setattr(guard, 'input_binding', lambda profile: {'input': 1})
    with pytest.raises(ValueError, match='TAINTED'):
        guard.execute(plan)


def test_execute_directly_rejects_stale_runtime_and_guard():
    with pytest.raises(ValueError, match='runtime'):
        guard.execute(dict(profile='joblight', versions={'python': 'WRONG_RUNTIME'}, guard_sha256='WRONG_GUARD'))
