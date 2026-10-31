"""Permanent official-MSCN checkpoint audit, with immutable completed-run reuse.

A fresh 100-epoch run replays the original loader and measures batch-one timing.
An existing verified run is hash-checked without inference or output replacement.
"""
from pathlib import Path
import argparse
import json

from full_common import file_sha256

ROOT = Path(__file__).resolve().parents[1]


def reuse_verification(directory):
    directory = Path(directory).resolve()
    report_path = directory / 'verification_epoch100.json'
    if not report_path.exists():
        return None
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if (report.get('status') != 'PASS' or report.get('completed_epochs') != 100
            or report.get('replayed_job_queries') != 70 or not report.get('artifacts')):
        raise ValueError('Existing verification does not describe a completed 100-epoch audit')
    records = [(r, directory, 'artifact') for r in report['artifacts']]
    if report.get('verification_driver'):
        records.append((report['verification_driver'], ROOT, 'verification driver'))
    for record, base, label in records:
        candidate = (base / record['path']).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError(f'{label} path escapes its sealed directory') from exc
        if (not candidate.is_file() or candidate.stat().st_size != record['bytes']
                or file_sha256(candidate) != record['sha256']):
            raise ValueError(f'{label} does not match its verification seal: {record["path"]}')
    return report


def execute_audit():
    from pathlib import Path
    import csv
    from datetime import datetime, timezone
    import json
    import math
    import statistics
    import sys
    import time
    import warnings

    import numpy as np
    import torch

    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / 'code'))
    import full_mscn as m

    RUN = ROOT / 'output/full/mscn/table1_job_light_seed1'
    config = json.loads((RUN / 'config.json').read_text())
    binding = m.training_binding(config)
    record = m.checkpoint_record(RUN / 'checkpoints', binding)
    assert record['completed_epochs'] == 100, 'Final audit requires 100 committed epochs'
    evaluation = json.loads((RUN / 'evaluation.json').read_text())
    assert evaluation['status'] == 'TABLE1_LOCAL_RERUN_COMPLETE'
    assert evaluation['completed_epochs'] == 100
    assert evaluation['queries'] == 70 and evaluation['validation_queries'] == 10000
    assert evaluation['checkpoint'] == record
    assert evaluation['binding_sha256'] == m.digest(binding)
    m.verify_records(evaluation['artifacts'], RUN)
    payload = torch.load(RUN / 'checkpoints' / record['artifact']['path'], map_location='cpu')
    assert payload['binding_sha256'] == m.digest(binding)
    assert payload['completed_epochs'] == 100
    history = payload['history']
    assert [r['epoch'] for r in history] == list(range(1, 101))
    assert all(r['training_queries'] == 90000 and r['batches'] == 88 and
               math.isfinite(r['loss_mean_of_batches']) for r in history)
    adam_steps = [float(s['step']) for s in payload['optimizer']['state'].values()]
    assert len(adam_steps) == 16 and all(step == 8800 for step in adam_steps)
    gate = json.loads((RUN / 'epoch1_restore_gate.json').read_text())
    assert gate['status'] == 'EPOCH1_TRAIN_RESTORE_EVALUATE_GATE_PASS'
    m.verify_records([gate['checkpoint']['artifact']], RUN / 'checkpoints')
    m.verify_records(gate['epoch1_archive'], RUN)
    state = torch.load(RUN / 'model_state.pt', map_location='cpu')
    assert state.keys() == payload['model'].keys()
    assert all(torch.equal(v, state[k]) for k, v in payload['model'].items())

    # Build vocabularies and normalization from the original training CSV without
    # loading or expanding its 100K bitmaps. All test tensors use the original loader.
    official, upstream = m.official_modules()
    u = sys.modules['mscn.util']
    data_root = ROOT / 'data/mscn'
    with (data_root / 'data/train.csv').open(newline='') as stream:
        train = list(csv.reader(stream, delimiter='#'))
    tables = [r[0].split(',') for r in train]
    joins = [r[1].split(',') for r in train]
    predicates = [list(u.chunks(r[2].split(','), 3)) for r in train]
    table2vec, _ = u.get_set_encoding(u.get_all_table_names(tables))
    column2vec, _ = u.get_set_encoding(u.get_all_column_names(predicates))
    op2vec, _ = u.get_set_encoding(u.get_all_operators(predicates))
    join2vec, _ = u.get_set_encoding(u.get_all_joins(joins))
    log_labels = np.asarray([np.log(float(r[3])) for r in train])
    minimum, maximum = log_labels.min(), log_labels.max()
    with (data_root / 'data/column_min_max_vals.csv').open(newline='') as stream:
        reader = csv.reader(stream)
        next(reader)
        ranges = {r[0]: [float(r[1]), float(r[2])] for r in reader}
    del train, tables, joins, predicates, log_labels
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=DeprecationWarning)
        joins, predicates, tables, samples, labels = upstream.load_data(
            str(data_root / 'workloads/job-light'), 1000)
    sample_enc = u.encode_samples(tables, samples, table2vec)
    predicate_enc, join_enc = u.encode_data(predicates, joins, ranges, column2vec, op2vec, join2vec)
    label_norm, _, _ = u.normalize_labels(labels, minimum, maximum)
    max_joins = max(map(len, join_enc))
    max_predicates = max(map(len, predicate_enc))
    dataset = upstream.make_dataset(sample_enc, predicate_enc, join_enc, label_norm, max_joins, max_predicates)
    torch.set_num_threads(config['threads'])
    model = official.SetConv(len(table2vec) + 1000, len(column2vec) + len(op2vec) + 1,
                             len(join2vec), config['hidden'])
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        raw_predictions, _ = official.predict(model, torch.utils.data.DataLoader(dataset, batch_size=1024), False)
        # NumPy1.24 no longer coerces a list of non-scalar Torch tensors; the explicit
        # stack changes the container only, preserving the official prediction values.
        normalized = torch.stack(raw_predictions).numpy().reshape(-1)
        replay = u.unnormalize_labels(normalized, minimum, maximum)
    with (RUN / 'predictions_job_light.csv').open(newline='', encoding='utf-8') as stream:
        predictions = list(csv.DictReader(stream))
    assert len(predictions) == 70 and len(dataset) == 70
    assert [int(r['query_no']) for r in predictions] == list(range(70))
    truths = np.asarray([int(value) for value in labels], dtype=np.int64)
    assert np.array_equal(truths, [int(r['cardinality_true']) for r in predictions])
    assert np.array_equal(replay, [int(r['cardinality_predict']) for r in predictions])
    qerrors = [max(int(p) / int(t), int(t) / int(p)) for p, t in zip(replay, truths)]
    metrics = {'median': float(np.median(qerrors)), 'p90': float(np.percentile(qerrors, 90)),
               'p95': float(np.percentile(qerrors, 95)), 'p99': float(np.percentile(qerrors, 99)),
               'mean': float(np.mean(qerrors)), 'max': float(np.max(qerrors))}
    for key, value in metrics.items():
        assert math.isclose(value, evaluation['job_light_qerror'][key], rel_tol=1e-12, abs_tol=1e-12)

    # Parsed numeric query fields and sample bytes are resident; time encoding,
    # tensor creation and forward separately from prebuilt-tensor forward.
    def forward(batch):
        s, p, j, _, sm, pm, jm = batch
        return model(s, p, j, sm, pm, jm)


    def online_query(i):
        s = u.encode_samples([tables[i]], [samples[i]], table2vec)
        p, j = u.encode_data([predicates[i]], [joins[i]], ranges, column2vec, op2vec, join2vec)
        encoded = upstream.make_dataset(s, p, j, [0.0], max_joins, max_predicates)
        return forward(tuple(t.unsqueeze(0) for t in encoded[0]))


    repeats = 10
    forward_times, pipeline_times = [], []
    normalized_delta = 0.0
    per_query = []
    with torch.no_grad():
        for i in range(3):
            online_query(i)
        for i in range(70):
            batch = tuple(t.unsqueeze(0) for t in dataset[i])
            forward_measurements, pipeline_measurements = [], []
            for _ in range(repeats):
                start = time.perf_counter_ns()
                value = forward(batch)
                forward_measurements.append((time.perf_counter_ns() - start) / 1e6)
                start = time.perf_counter_ns()
                online_value = online_query(i)
                pipeline_measurements.append((time.perf_counter_ns() - start) / 1e6)
            torch.testing.assert_close(value, online_value, rtol=1e-5, atol=1e-6)
            normalized_delta = max(normalized_delta, abs(float(value[0, 0]) - float(normalized[i])))
            forward_times.extend(forward_measurements)
            pipeline_times.extend(pipeline_measurements)
            per_query.append([i, statistics.mean(forward_measurements), statistics.mean(pipeline_measurements)])
    assert normalized_delta < 1e-5
    latency_path = RUN / 'latency_single_query.csv'
    with latency_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['query_no', 'forward_mean_ms', 'encoding_and_forward_mean_ms'])
        writer.writerows(per_query)


    def latency_summary(values):
        return {'mean_ms': float(np.mean(values)), 'median_ms': float(np.median(values)),
                'p95_ms': float(np.percentile(values, 95))}


    result = {'status': 'PASS', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'completed_epochs': 100, 'training_queries': 90000, 'validation_queries': 10000,
              'replayed_job_queries': 70, 'prediction_equality': 'EXACT_ROUNDED_PREDICTIONS_ALL_70',
              'replay_loader': 'unmodified official load_data/encode/make_dataset/predict',
              'model_tensors_exact': len(state), 'adam_steps_all_parameters': 8800,
              'epoch1_checkpoint_unchanged': True, 'binding_sha256': m.digest(binding),
              'qerror': metrics, 'threads': config['threads'], 'latency_repeats_per_query': repeats,
              'latency_warmup_queries': 3, 'latency_forward_batch1': latency_summary(forward_times),
              'latency_encoding_and_forward_batch1': latency_summary(pipeline_times),
              'latency_exclusions': ['CSV/bitmap disk reading', 'SQL parsing', 'truth/q-error/unnormalization'],
              'max_normalized_output_difference_batch1_vs_batch70': normalized_delta,
              'artifacts': [m.file_record(p, RUN) for p in
                            [RUN / 'evaluation.json', RUN / 'predictions_job_light.csv', latency_path,
                             RUN / 'model_state.pt', RUN / 'checkpoints' / record['artifact']['path']]],
              'verification_driver': m.file_record(Path(__file__), ROOT)}
    m.atomic_json(RUN / 'verification_epoch100.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    run = ROOT / 'output/full/mscn/table1_job_light_seed1'
    existing = reuse_verification(run)
    if existing is not None:
        print(json.dumps(dict(status='REUSED_VERIFIED_100_EPOCH_AUDIT',
                              completed_epochs=existing['completed_epochs'],
                              replayed_job_queries=existing['replayed_job_queries']), indent=2))
        return
    execute_audit()


if __name__ == '__main__':
    main()
