"""Small shared primitives for sealed, recoverable full-paper experiments."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / 'output/full'


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def binding_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def checkpoint_valid(record, binding, root=ROOT):
    if record.get('status') != 'PASS' or record.get('binding') != binding_hash(binding):
        return False
    root = Path(root).resolve()
    if not record.get('artifacts'):
        return False
    for item in record['artifacts']:
        candidate = (root / item['path']).resolve()
        if root not in candidate.parents or not candidate.is_file():
            return False
        if file_sha256(candidate) != item['sha256']:
            return False
    return True


def algorithm_seal():
    selected = []
    for folder in ['aqp_spn', 'rspn', 'ensemble_creation', 'ensemble_compilation', 'data_preparation', 'schemas']:
        selected.extend((ROOT / 'code' / folder).rglob('*.py'))
    return binding_hash({p.relative_to(ROOT).as_posix(): file_sha256(p) for p in sorted(selected)})


def load_json(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).is_file() else default
