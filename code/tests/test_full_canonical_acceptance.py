import pytest

import full_canonical_acceptance as acceptance
from full_canonical_acceptance import require_seed_zero_baseline
from full_common import atomic_json, file_sha256


def test_seed_zero_gate_rejects_unmeasured_seed_zero_baseline():
    require_seed_zero_baseline({'groups': {'a': {'generation_hash_seed': '0'}}})
    with pytest.raises(ValueError, match='seed0'):
        require_seed_zero_baseline({'groups': {'a': {'generation_hash_seed': '1'}}})
    with pytest.raises(ValueError, match='seed0'):
        require_seed_zero_baseline({'groups': {}})


def test_cached_aggregate_still_rechecks_current_label_files(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance, 'ROOT', tmp_path)
    monkeypatch.setattr(acceptance, 'FULL', tmp_path / 'output/full')
    directory = acceptance.FULL / 'results'; directory.mkdir(parents=True)
    baseline = directory / 'model_evaluation_v3.json'; baseline.write_text('baseline')
    contexts = []
    for seed in range(4):
        paths = [baseline]
        if seed:
            replay = directory / ('model_replay_v3_seed%d.json' % seed)
            replay.write_text('replay'); paths.append(replay)
        context = dict(artifacts=[dict(path=p.relative_to(tmp_path).as_posix(), sha256=file_sha256(p)) for p in paths])
        contexts.append(context)
        atomic_json(acceptance.FULL / 'canonical_run' / ('seed%d_complete.json' % seed), context)
    aggregate = dict(contexts=contexts)
    acceptance.recheck_label_artifacts(aggregate, 'model')
    baseline.write_text('new self-consistent baseline')
    with pytest.raises(ValueError, match='artifact'):
        acceptance.recheck_label_artifacts(aggregate, 'model')
