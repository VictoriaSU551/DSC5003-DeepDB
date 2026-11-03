import json
from pathlib import Path

from full_common import atomic_json, binding_hash, checkpoint_valid, file_sha256
from full_postgres import table_ddl, copy_sql


def test_checkpoint_rejects_changed_inputs_and_artifacts(tmp_path):
    artifact = tmp_path / 'model.pkl'
    artifact.write_bytes(b'original fitted model')
    binding = {'seed': 1, 'samples': 10000000, 'data': 'sha'}
    record = {'status': 'PASS', 'binding': binding_hash(binding),
              'artifacts': [{'path': 'model.pkl', 'sha256': file_sha256(artifact)}]}
    assert checkpoint_valid(record, binding, tmp_path)
    assert not checkpoint_valid(record, dict(binding, samples=100000), tmp_path)
    artifact.write_bytes(b'incomplete or changed model')
    assert not checkpoint_valid(record, binding, tmp_path)


def test_checkpoint_cannot_escape_project(tmp_path):
    record = {'status': 'PASS', 'binding': binding_hash({}),
              'artifacts': [{'path': '../outside', 'sha256': 'anything'}]}
    assert not checkpoint_valid(record, {}, tmp_path)


def test_atomic_json_preserves_existing_receipt(tmp_path):
    target = tmp_path / 'receipt.json'
    atomic_json(target, {'status': 'PASS', 'queries': 70})
    assert json.loads(target.read_text())['queries'] == 70
    assert not list(tmp_path.glob('*.tmp'))


def test_postgres_schema_keeps_real_numeric_keys_and_text():
    ddl = table_ddl('title')
    assert '"id" integer PRIMARY KEY' in ddl
    assert '"production_year" integer' in ddl
    assert '"title" text' in ddl
    assert 'ESCAPE' in copy_sql('title')
