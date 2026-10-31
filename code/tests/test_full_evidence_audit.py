import pytest

import full_evidence_audit as audit
from full_common import binding_hash, file_sha256


def test_original_binding_rejects_changed_pairwise_input(tmp_path, monkeypatch):
    pairwise = tmp_path / 'rdc.pkl'; pairwise.write_bytes(b'original RDC')
    query = tmp_path / 'queries.sql'; query.write_text('SELECT COUNT(*) FROM title;')
    truth = tmp_path / 'truth.csv'; truth.write_text('cardinality_true\n1\n')
    training = dict(model_sha256='model', pairwise_rdc_path='rdc.pkl')
    monkeypatch.setattr(audit, 'helper_seal', lambda: {'helper': 'unchanged'})
    record = dict(binding=binding_hash(audit.original_binding(training, query, truth, tmp_path)))
    audit.require_original_binding(record, training, query, truth, tmp_path)
    pairwise.write_bytes(b'changed RDC')
    with pytest.raises(ValueError, match='binding'):
        audit.require_original_binding(record, training, query, truth, tmp_path)


def test_alias_requires_same_pairwise_content_and_selection_mode(tmp_path):
    first = tmp_path / 'a.pkl'; first.write_bytes(b'first')
    second = tmp_path / 'b.pkl'; second.write_bytes(b'second')
    base = dict(profile='joblight', models=[dict(binding='component', artifacts=[dict(sha256='model')])])
    current = dict(base, pairwise_rdc_path='a.pkl')
    source = dict(base, pairwise_rdc_path='b.pkl')
    with pytest.raises(ValueError, match='pairwise'):
        audit.require_alias_identity(current, source, tmp_path)
    second.write_bytes(first.read_bytes())
    audit.require_alias_identity(current, source, tmp_path)
    with pytest.raises(ValueError, match='pairwise'):
        audit.require_alias_identity(current, dict(base, pairwise_rdc_path=None), tmp_path)


def test_group_cache_rejects_wrong_identity_and_receipt_tampering():
    identity = dict(binding='same-run', group='5_2_SPN', queries=23,
                    query_sha256='sql', truth_sha256='truth', prediction_sha256='prediction')
    receipt = dict(identity, status='PASS', order='reverse; fresh ensemble; cold cache for every query',
                   max_relative_prediction_difference=0.)
    receipt['receipt_sha256'] = binding_hash(receipt)
    audit.require_group_receipt(receipt, identity)
    changed = dict(receipt, group='6_2_SPN')
    changed['receipt_sha256'] = binding_hash({k: v for k, v in changed.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='group'):
        audit.require_group_receipt(changed, identity)
    with pytest.raises(ValueError, match='seal'):
        audit.require_group_receipt(dict(receipt, max_relative_prediction_difference=1.), identity)


@pytest.mark.parametrize('artifacts', [[], ['a', 'a'], ['a', 'c']])
def test_audit_requires_exact_unique_group_artifact_set(artifacts):
    with pytest.raises(ValueError, match='group'):
        audit.require_group_set(artifacts, ['a', 'b'])
