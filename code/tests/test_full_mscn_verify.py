import json

import pytest

from full_common import file_sha256
from full_mscn_verify import reuse_verification


def test_reuse_gate_checks_committed_epoch_and_sealed_artifact(tmp_path):
    artifact = tmp_path / 'model.pt'; artifact.write_bytes(b'verified trained model')
    report = dict(status='PASS', completed_epochs=100, replayed_job_queries=70,
                  artifacts=[dict(path='model.pt', bytes=artifact.stat().st_size, sha256=file_sha256(artifact))])
    (tmp_path / 'verification_epoch100.json').write_text(json.dumps(report))
    assert reuse_verification(tmp_path)['status'] == 'PASS'
    artifact.write_bytes(b'changed model')
    with pytest.raises(ValueError, match='artifact'):
        reuse_verification(tmp_path)
