"""Sealed MSCN Table 1 inputs and recoverable CPU training, without SPFlow changes."""
import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import struct
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '50073283eacdea300d1dcd815c720f64e3d2d400'
ARCHIVE_SHA256 = '8cd760049c496e5cf30aba7bd8e89051738e9931745bceb9198e5554acbdfe4e'
ARCHIVE = 'data/downloads/mscn-' + COMMIT + '.zip'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temp), str(path))


def file_record(path, root=ROOT):
    path, root = Path(path).resolve(), Path(root).resolve()
    return {'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha256(path)}


def verify_records(records, root=ROOT):
    root = Path(root).resolve()
    for record in records:
        path = (root / record['path']).resolve()
        if root not in path.parents or not path.is_file() or path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
            raise ValueError('sealed artifact changed: ' + record['path'])


def read_queries(path):
    rows = []
    with Path(path).open(newline='', encoding='utf-8') as stream:
        for i, row in enumerate(csv.reader(stream, delimiter='#'), 1):
            if len(row) != 4 or not re.fullmatch(r'[1-9][0-9]*', row[3]):
                raise ValueError('invalid MSCN query/cardinality at row {}'.format(i))
            tables = row[0].split(',')
            predicates = row[2].split(',') if row[2] else []
            if not all(tables) or len(predicates) % 3:
                raise ValueError('invalid tables/predicates at row {}'.format(i))
            rows.append(row)
    if not rows:
        raise ValueError('empty MSCN queries')
    return rows


def bitmap_offsets(rows, bitmap, num_samples=1000):
    offsets = []
    bitmap_bytes = (num_samples + 7) >> 3
    with Path(bitmap).open('rb') as stream:
        for i, row in enumerate(rows, 1):
            header = stream.read(4)
            if len(header) != 4:
                raise ValueError('truncated bitmap header at row {}'.format(i))
            count = struct.unpack('<I', header)[0]
            if count != len(row[0].split(',')):
                raise ValueError('bitmap table count mismatch at row {}'.format(i))
            offsets.append(stream.tell())
            if len(stream.read(count * bitmap_bytes)) != count * bitmap_bytes:
                raise ValueError('truncated bitmap at row {}'.format(i))
        if stream.read(1):
            raise ValueError('trailing bitmap bytes after last query')
    return offsets


def inspect_pair(csv_path, bitmap, num_samples=1000):
    rows = read_queries(csv_path)
    bitmap_offsets(rows, bitmap, num_samples)
    return {'queries': len(rows), 'bitmap_bytes': Path(bitmap).stat().st_size,
            'materialized_samples': num_samples,
            'table_count_histogram': dict(sorted(Counter(str(len(r[0].split(','))) for r in rows).items()))}


def query_sql(row):
    conditions = row[1].split(',') if row[1] else []
    parts = row[2].split(',') if row[2] else []
    conditions += [''.join(parts[i:i + 3]) for i in range(0, len(parts), 3)]
    return 'SELECT COUNT(*) FROM ' + row[0] + (' WHERE ' + ' AND '.join(conditions) if conditions else '') + ';'


def normalize_numeric_sql(query):
    # This workload has numeric literals only; never fold arbitrary string literals.
    if "'" in query or '"' in query:
        raise ValueError('unexpected quoted literal in numeric MSCN workload')
    return re.sub(r'\s+', '', query).lower().rstrip(';')


def inspect_job_truth(csv_path, truth_path):
    rows = read_queries(csv_path)
    with Path(truth_path).open(newline='', encoding='utf-8') as stream:
        truths = list(csv.DictReader(stream))
    if len(rows) != len(truths):
        raise ValueError('JOB truth row count mismatch')
    for i, (row, truth) in enumerate(zip(rows, truths)):
        if int(truth['query_no']) != i or normalize_numeric_sql(query_sql(row)) != normalize_numeric_sql(truth['query']):
            raise ValueError('JOB query mismatch at row {}'.format(i + 1))
        if int(row[3]) != int(truth['cardinality_true']):
            raise ValueError('JOB cardinality mismatch at row {}'.format(i + 1))
    return 'PASS'


def audit_inputs(root=ROOT):
    root = Path(root).resolve()
    archive = root / ARCHIVE
    if sha256(archive) != ARCHIVE_SHA256:
        raise ValueError('fixed official archive digest mismatch')
    records = [file_record(archive, root)]
    with zipfile.ZipFile(archive) as z:
        prefix = 'learnedcardinalities-' + COMMIT + '/'
        for info in z.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith(prefix):
                raise ValueError('unexpected archive member')
            rel = info.filename[len(prefix):]
            destination = 'data/mscn/' + rel if rel.startswith(('data/', 'workloads/')) else 'code/vendor/mscn/' + rel
            path = root / destination
            expected = hashlib.sha256(z.read(info)).hexdigest()
            record = file_record(path, root)
            if record['sha256'] != expected:
                raise ValueError('official source changed: ' + destination)
            records.append(record)
    train = inspect_pair(root / 'data/mscn/data/train.csv', root / 'data/mscn/data/train.bitmaps')
    job = inspect_pair(root / 'data/mscn/workloads/job-light.csv', root / 'data/mscn/workloads/job-light.bitmaps')
    if train['queries'] != 100000 or job['queries'] != 70:
        raise ValueError('Table 1 requires official 100K train and 70 JOB-light queries')
    truth = root / 'code/benchmarks/job-light/sql/job_light_true_cardinalities.csv'
    aligned = inspect_job_truth(root / 'data/mscn/workloads/job-light.csv', truth)
    records.append(file_record(truth, root))
    return {'status': 'INPUTS_VERIFIED_TRAINING_NOT_IMPLIED', 'upstream_commit': COMMIT,
            'upstream_url': 'https://github.com/andreaskipf/learnedcardinalities/tree/' + COMMIT,
            'archive_url': 'https://codeload.github.com/andreaskipf/learnedcardinalities/zip/' + COMMIT,
            'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'train': train, 'job_light': job,
            'job_truth_alignment': aligned, 'artifacts': records,
            'generalization_683_status': 'BLOCKED_MISSING_MATCHED_BITMAPS_AND_SAMPLE_ROWS'}


def checkpoint_record(directory, binding):
    directory = Path(directory)
    receipt = directory / 'latest.json'
    if not receipt.exists():
        return None
    record = json.loads(receipt.read_text(encoding='utf-8'))
    if record.get('binding_sha256') != digest(binding):
        raise ValueError('checkpoint binding mismatch; refusing restart or reuse')
    if record.get('status') != 'COMMITTED' or not isinstance(record.get('completed_epochs'), int) or record['completed_epochs'] < 1:
        raise ValueError('invalid checkpoint receipt')
    verify_records([record['artifact']], directory)
    return record


def commit_checkpoint_record(directory, artifact, completed_epochs, binding):
    record = {'status': 'COMMITTED', 'completed_epochs': completed_epochs,
              'binding_sha256': digest(binding), 'artifact': file_record(artifact, directory)}
    atomic_json(Path(directory) / 'latest.json', record)
    return record


def pending_epochs(record, target):
    completed = record['completed_epochs'] if record else 0
    if target < completed:
        raise ValueError('requested target precedes committed epoch')
    return list(range(completed + 1, target + 1))


def official_modules():
    vendor = ROOT / 'code/vendor/mscn'
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import mscn.data
    spec = importlib.util.spec_from_file_location('_full_mscn_official_train', vendor / 'train.py')
    official = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official)
    return official, mscn.data


class BitmapDataset:
    """Map-style dataset: exact upstream padded tensors, with lazy bitmap expansion."""

    def __init__(self, rows, offsets, bitmap, encoding, labels, indices, max_joins, max_predicates):
        import numpy as np
        self.rows, self.offsets = rows, offsets
        self.bitmap = np.memmap(bitmap, mode='r', dtype=np.uint8)
        self.encoding, self.labels = encoding, labels
        self.indices = indices
        self.max_joins, self.max_predicates = max_joins, max_predicates

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, item):
        import numpy as np
        import torch
        i = self.indices[item]
        row, offset = self.rows[i], self.offsets[i]
        tables = row[0].split(',')
        table2vec, pred_enc, join_enc = self.encoding
        packed = self.bitmap[offset:offset + 125 * len(tables)].reshape(len(tables), 125)
        bits = np.unpackbits(packed, axis=1)
        sample = np.vstack([np.hstack([table2vec[table], bits[j]]) for j, table in enumerate(tables)])

        def padded(values, count):
            values = np.vstack(values)
            mask = np.ones_like(values).mean(1, keepdims=True)
            pad = count - len(values)
            if pad < 0:
                raise ValueError('query exceeds dataset padding')
            return (torch.as_tensor(np.pad(values, ((0, pad), (0, 0))), dtype=torch.float32),
                    torch.as_tensor(np.pad(mask, ((0, pad), (0, 0))), dtype=torch.float32))

        samples, sample_mask = padded(sample, self.max_joins + 1)
        predicates, predicate_mask = padded(pred_enc[i], self.max_predicates)
        joins, join_mask = padded(join_enc[i], self.max_joins)
        return (samples, predicates, joins, torch.tensor(self.labels[i], dtype=torch.float32),
                sample_mask, predicate_mask, join_mask)


def prepare_datasets(data_root, num_queries=100000):
    """Read compact query/encoding metadata, retaining packed bitmap bytes on disk."""
    _, upstream = official_modules()
    u = sys.modules['mscn.util']
    data_root = Path(data_root)
    rows = read_queries(data_root / 'data/train.csv')
    if not 2 <= num_queries <= len(rows):
        raise ValueError('num_queries outside training input range')
    offsets = bitmap_offsets(rows, data_root / 'data/train.bitmaps')
    tables = [r[0].split(',') for r in rows]
    joins = [r[1].split(',') for r in rows]
    predicates = [list(u.chunks(r[2].split(','), 3)) for r in rows]
    table2vec, _ = u.get_set_encoding(u.get_all_table_names(tables))
    column2vec, _ = u.get_set_encoding(u.get_all_column_names(predicates))
    op2vec, _ = u.get_set_encoding(u.get_all_operators(predicates))
    join2vec, _ = u.get_set_encoding(u.get_all_joins(joins))
    with (data_root / 'data/column_min_max_vals.csv').open(newline='', encoding='utf-8') as stream:
        reader = csv.reader(stream)
        next(reader)
        ranges = {r[0]: [float(r[1]), float(r[2])] for r in reader}
    pred_enc, join_enc = u.encode_data(predicates, joins, ranges, column2vec, op2vec, join2vec)
    labels, min_val, max_val = u.normalize_labels([r[3] for r in rows])
    train_count = int(num_queries * 0.9)
    max_joins = max(len(r) for r in joins[:num_queries])
    max_predicates = max(len(r) for r in predicates[:num_queries])
    encoding = (table2vec, pred_enc, join_enc)
    args = (rows, offsets, data_root / 'data/train.bitmaps', encoding, labels)
    return {'train': BitmapDataset(*args, range(train_count), max_joins, max_predicates),
            'validation': BitmapDataset(*args, range(train_count, num_queries), max_joins, max_predicates),
            'min_val': min_val, 'max_val': max_val,
            'table2vec': table2vec, 'column2vec': column2vec, 'op2vec': op2vec, 'join2vec': join2vec,
            'column_ranges': ranges,
            'model_features': [len(table2vec) + 1000, len(column2vec) + len(op2vec) + 1, len(join2vec)]}


def save_training_checkpoint(directory, epoch, binding, model, optimizer, history):
    import numpy as np
    import torch
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / 'epoch_{:06d}.pt'.format(epoch)
    temp = artifact.with_suffix('.pt.tmp')
    payload = {'completed_epochs': epoch, 'binding_sha256': digest(binding),
               'model': model.state_dict(), 'optimizer': optimizer.state_dict(), 'history': history,
               'rng_python': random.getstate(), 'rng_numpy': np.random.get_state(),
               'rng_torch': torch.get_rng_state()}
    with temp.open('wb') as stream:
        torch.save(payload, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temp), str(artifact))
    return commit_checkpoint_record(directory, artifact, epoch, binding)


def restore_training_checkpoint(directory, binding, model, optimizer):
    import numpy as np
    import torch
    record = checkpoint_record(directory, binding)
    if record is None:
        return []
    payload = torch.load(Path(directory) / record['artifact']['path'], map_location='cpu')
    if payload['binding_sha256'] != digest(binding) or payload['completed_epochs'] != record['completed_epochs']:
        raise ValueError('checkpoint payload/receipt mismatch')
    if len(payload['history']) != record['completed_epochs']:
        raise ValueError('checkpoint epoch/history mismatch')
    model.load_state_dict(payload['model'])
    optimizer.load_state_dict(payload['optimizer'])
    random.setstate(payload['rng_python'])
    np.random.set_state(payload['rng_numpy'])
    torch.set_rng_state(payload['rng_torch'])
    return payload['history']


def runtime_versions():
    from importlib.metadata import version
    return {'python': '.'.join(map(str, sys.version_info[:3])),
            'numpy': version('numpy'), 'torch': version('torch')}


def training_binding(config, root=ROOT):
    root = Path(root).resolve()
    sources = audit_inputs(root)
    records = sources['artifacts'] + [file_record(root / p, root) for p in
                                    ['code/full_mscn.py', 'docs/FULL_MSCN_PROTOCOL.md']]
    runtime = runtime_versions()
    if runtime != {'python': '3.8.20', 'numpy': '1.24.4', 'torch': '1.13.1+cpu'}:
        raise ValueError('Use the pinned .venv-mscn runtime: ' + repr(runtime))
    return {'schema_version': 1, 'configuration': config, 'runtime': runtime,
            'artifacts': records, 'upstream_commit': COMMIT,
            'loader': 'lazy_bitmap_upstream_equivalent_v1', 'optimizer': {'name': 'Adam', 'lr': 0.001},
            'materialized_samples': 1000, 'split': 'first_90pct_train_next_10pct_validation',
            'shuffle': False, 'device': 'cpu'}


@contextmanager
def run_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'run.lock').open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def setup_runtime(config):
    import numpy as np
    import torch
    random.seed(config['seed'])
    np.random.seed(config['seed'])
    torch.manual_seed(config['seed'])
    torch.set_num_threads(config['threads'])
    torch.use_deterministic_algorithms(True)


def model_and_optimizer(prepared, config):
    import torch
    official, _ = official_modules()
    model = official.SetConv(*prepared['model_features'], config['hidden'])
    return model, torch.optim.Adam(model.parameters(), lr=0.001)


def train_run(directory, config, target_epochs, root=ROOT):
    import torch
    from torch.utils.data import DataLoader
    if not 1 <= target_epochs <= 100:
        raise ValueError('target epochs must be in [1, 100]')
    directory = Path(directory)
    binding = training_binding(config, root)
    with run_lock(directory):
        record = checkpoint_record(directory / 'checkpoints', binding)
        remaining = pending_epochs(record, target_epochs)
        if not remaining:
            return {'status': 'TARGET_ALREADY_COMMITTED', 'completed_epochs': record['completed_epochs'],
                    'checkpoint': record}
        setup_runtime(config)
        prepared = prepare_datasets(Path(root) / 'data/mscn', config['queries'])
        model, optimizer = model_and_optimizer(prepared, config)
        loader = DataLoader(prepared['train'], batch_size=config['batch'], shuffle=False, num_workers=0)
        official, _ = official_modules()
        history = restore_training_checkpoint(directory / 'checkpoints', binding, model, optimizer)
        atomic_json(directory / 'binding.json', binding)
        atomic_json(directory / 'config.json', config)
        for epoch in remaining:
            model.train()
            loss_total = 0.0
            started = time.perf_counter()
            for samples, predicates, joins, targets, sample_masks, predicate_masks, join_masks in loader:
                optimizer.zero_grad()
                outputs = model(samples, predicates, joins, sample_masks, predicate_masks, join_masks)
                loss = official.qerror_loss(outputs, targets.float(), prepared['min_val'], prepared['max_val'])
                if not torch.isfinite(loss):
                    raise ValueError('non-finite training loss; epoch not committed')
                loss_total += loss.item()
                loss.backward()
                optimizer.step()
            item = {'epoch': epoch, 'training_queries': len(prepared['train']),
                    'batches': len(loader), 'loss_mean_of_batches': loss_total / len(loader),
                    'training_seconds': time.perf_counter() - started}
            history.append(item)
            record = save_training_checkpoint(directory / 'checkpoints', epoch, binding, model, optimizer, history)
            atomic_json(directory / 'history.json', history)
            print(json.dumps(item), flush=True)
        status = 'TRAINING_COMPLETE_EVALUATION_REQUIRED' if record['completed_epochs'] == 100 else 'PARTIAL_TRAINING'
        result = {'status': status, 'completed_epochs': record['completed_epochs'], 'target_epochs': target_epochs,
                  'binding_sha256': digest(binding), 'checkpoint': record,
                  'training_seconds': sum(r['training_seconds'] for r in history)}
        atomic_json(directory / 'training_state.json', result)
        return result


def workload_dataset(data_root, name, prepared):
    _, upstream = official_modules()
    u = sys.modules['mscn.util']
    prefix = Path(data_root) / 'workloads' / name
    rows = read_queries(prefix.with_suffix('.csv'))
    bitmap = prefix.with_suffix('.bitmaps')
    offsets = bitmap_offsets(rows, bitmap)
    joins = [r[1].split(',') for r in rows]
    predicates = [list(u.chunks(r[2].split(','), 3)) for r in rows]
    pred_enc, join_enc = u.encode_data(predicates, joins, prepared['column_ranges'],
                                      prepared['column2vec'], prepared['op2vec'], prepared['join2vec'])
    labels, _, _ = u.normalize_labels([r[3] for r in rows], prepared['min_val'], prepared['max_val'])
    encoding = (prepared['table2vec'], pred_enc, join_enc)
    return BitmapDataset(rows, offsets, bitmap, encoding, labels, range(len(rows)),
                         max(len(j) for j in joins), max(len(p) for p in predicates))


def predict_dataset(model, dataset, batch_size, prepared):
    import numpy as np
    import torch
    from torch.utils.data import DataLoader
    u = sys.modules['mscn.util']
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    model.eval()
    predictions, amortized_ms = [], []
    forward_seconds = 0.0
    with torch.no_grad():
        # Warm-up is excluded from the reported forward time.
        sample, pred, joins, _, sm, pm, jm = next(iter(loader))
        model(sample, pred, joins, sm, pm, jm)
        for sample, pred, joins, _, sm, pm, jm in loader:
            started = time.perf_counter()
            values = model(sample, pred, joins, sm, pm, jm)
            elapsed = time.perf_counter() - started
            forward_seconds += elapsed
            predictions.extend(values.cpu().numpy().reshape(-1).tolist())
            amortized_ms.extend([elapsed * 1000 / len(sample)] * len(sample))
    unnormalized = u.unnormalize_labels(np.asarray(predictions, dtype=np.float32), prepared['min_val'], prepared['max_val'])
    return unnormalized, amortized_ms, forward_seconds


def qerror_metrics(estimates, truths):
    import numpy as np
    estimates, truths = np.asarray(estimates, dtype=np.float64), np.asarray(truths, dtype=np.float64)
    if np.any(estimates < 1) or np.any(truths < 1):
        raise ValueError('q-error requires positive estimates and truths')
    errors = np.maximum(estimates / truths, truths / estimates)
    return {'median': float(np.median(errors)), 'p90': float(np.percentile(errors, 90)),
            'p95': float(np.percentile(errors, 95)), 'p99': float(np.percentile(errors, 99)),
            'max': float(errors.max()), 'mean': float(errors.mean())}


def evaluate_run(directory, config, root=ROOT):
    import torch
    directory = Path(directory)
    binding = training_binding(config, root)
    with run_lock(directory):
        record = checkpoint_record(directory / 'checkpoints', binding)
        if record is None:
            raise ValueError('no committed training checkpoint; evaluation never starts training')
        setup_runtime(config)
        prepared = prepare_datasets(Path(root) / 'data/mscn', config['queries'])
        model, optimizer = model_and_optimizer(prepared, config)
        history = restore_training_checkpoint(directory / 'checkpoints', binding, model, optimizer)
        dataset = workload_dataset(Path(root) / 'data/mscn', 'job-light', prepared)
        estimates, ms, forward_seconds = predict_dataset(model, dataset, config['batch'], prepared)
        truths = [int(r[3]) for r in dataset.rows]
        output = directory / 'predictions_job_light.csv'
        temp = output.with_suffix('.csv.tmp')
        with temp.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['query_no', 'query', 'cardinality_true', 'cardinality_predict', 'q_error', 'forward_amortized_ms'])
            for i, row in enumerate(dataset.rows):
                estimate, truth = int(estimates[i]), truths[i]
                writer.writerow([i, query_sql(row), truth, estimate, max(estimate / truth, truth / estimate), ms[i]])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp), str(output))
        validation_estimates, _, _ = predict_dataset(model, prepared['validation'], config['batch'], prepared)
        validation_truths = [int(prepared['validation'].rows[i][3]) for i in prepared['validation'].indices]
        model_path = directory / 'model_state.pt'
        model_temp = model_path.with_suffix('.pt.tmp')
        with model_temp.open('wb') as stream:
            torch.save(model.state_dict(), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(model_temp), str(model_path))
        standard = config['queries'] == 100000 and config['batch'] == 1024 and config['hidden'] == 256
        status = 'TABLE1_LOCAL_RERUN_COMPLETE' if record['completed_epochs'] == 100 and standard else 'PARTIAL_TRAINING'
        result = {'status': status, 'completed_epochs': record['completed_epochs'], 'queries': len(dataset),
                  'training_queries': len(prepared['train']), 'validation_queries': len(prepared['validation']),
                  'binding_sha256': digest(binding), 'checkpoint': record,
                  'job_light_qerror': qerror_metrics(estimates, truths),
                  'validation_qerror': qerror_metrics(validation_estimates, validation_truths),
                  'training_seconds': sum(r['training_seconds'] for r in history),
                  'forward_seconds': forward_seconds, 'forward_amortized_ms': forward_seconds * 1000 / len(dataset),
                  'latency_protocol': 'one warm-up; batch-forward only; CPU; no_grad; excludes input encoding',
                  'model_parameter_bytes': sum(v.numel() * v.element_size() for v in model.state_dict().values()),
                  'model_state_disk_bytes': model_path.stat().st_size,
                  'checkpoint_disk_bytes': record['artifact']['bytes'],
                  'artifacts': [file_record(output, directory), file_record(model_path, directory)]}
        atomic_json(directory / 'evaluation.json', result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['audit', 'train', 'evaluate'])
    parser.add_argument('--run', default='table1_job_light_seed1')
    parser.add_argument('--queries', type=int, default=100000)
    parser.add_argument('--epochs', type=int, default=100, help='target total, not additional epochs')
    parser.add_argument('--batch', type=int, default=1024)
    parser.add_argument('--hidden', type=int, default=256)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run):
        parser.error('run must be a simple directory name')
    if not 2 <= args.queries <= 100000 or min(args.batch, args.hidden, args.threads) < 1:
        parser.error('invalid training configuration')
    config = {'queries': args.queries, 'batch': args.batch, 'hidden': args.hidden,
              'seed': args.seed, 'threads': args.threads}
    directory = ROOT / 'output/full/mscn' / args.run
    if args.action == 'audit':
        result = audit_inputs()
        result['wrapper_artifacts'] = [file_record(ROOT / p) for p in ['code/full_mscn.py', 'docs/FULL_MSCN_PROTOCOL.md']]
        atomic_json(ROOT / 'output/full/results/mscn_sources.json', result)
    elif args.action == 'train':
        result = train_run(directory, config, args.epochs)
    else:
        result = evaluate_run(directory, config)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
