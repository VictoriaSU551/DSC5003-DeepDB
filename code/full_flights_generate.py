"""Batch-resumable IDEBench adapter, with a bounded independent golden check.

Default commands generate only 200K rows. A full 1B run must be requested
explicitly; it keeps a Bernoulli sample and exact 12-query integer totals.
The pinned vendor source is never modified on disk.
"""
import argparse
import ast
import contextlib
import csv
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys

import numpy as np
import pandas as pd
import scipy


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'code/vendor/idebench/datagen.py'
SOURCE_SHA256 = 'e7527f37f062eafc501062aaac4b164d1413127ef45129bd7ed9db699cebd8e9'
CSV_SHA256 = '869aa27e19a89f99a06204292d9bfc584cfd0eea0debed9e3eb69f3e1820c936'
DESCRIPTOR_SHA256 = '8f686f9c854f52ab61a0def0ae9a94cab4c4b7fc39466c4b9ce934acba84efdf'
COLUMNS = ('YEAR_DATE', 'UNIQUE_CARRIER', 'ORIGIN', 'ORIGIN_STATE_ABR', 'DEST',
           'DEST_STATE_ABR', 'DEP_DELAY', 'TAXI_OUT', 'TAXI_IN', 'ARR_DELAY',
           'AIR_TIME', 'DISTANCE')
QUERY_NAMES = ('F1.1', 'F1.2', 'F2.1', 'F2.2', 'F2.3', 'F3.1',
               'F3.2', 'F3.3', 'F4.1', 'F4.2', 'F5.1', 'F5.2')
ORIGINAL_SQL = (
    "SELECT AVG(dep_delay) FROM flights WHERE origin='ATL';",
    "SELECT AVG(distance) FROM flights WHERE unique_carrier='TW';",
    "SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' GROUP BY unique_carrier;",
    "SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest_state_abr='CA' GROUP BY unique_carrier;",
    "SELECT year_date, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest='JFK' GROUP BY year_date;",
    "SELECT year_date, SUM(distance) FROM flights WHERE unique_carrier='9E' GROUP BY year_date;",
    "SELECT origin_state_abr, SUM(air_time) FROM flights WHERE dest='HPN' GROUP BY origin_state_abr;",
    "SELECT unique_carrier, AVG(dep_delay) FROM flights WHERE year_date=2005 AND origin='PHX' GROUP BY unique_carrier;",
    "SELECT dest_state_abr, COUNT(*) FROM flights WHERE distance>2500 GROUP BY dest_state_abr;",
    "SELECT unique_carrier, COUNT(*) FROM flights WHERE air_time>1000 AND dep_delay>1500 GROUP BY unique_carrier;",
    "SELECT year_date, SUM(arr_delay*dep_delay) FROM flights WHERE origin_state_abr = 'CA' AND dest_state_abr = 'HI' GROUP BY year_date;",
    "SELECT dest_state_abr, SUM(taxi_out)-SUM(taxi_in) FROM flights WHERE unique_carrier = 'UA' AND origin = 'ATL' GROUP BY dest_state_abr;",
)
# Independent SQLite queries over input decimals represented as integer tenths.
# Each row is group key (if any), exact numerator sum, exact matching row count.
EXACT_SQL = (
    "SELECT SUM(dep_delay),COUNT(*) FROM flights WHERE origin='ATL'",
    "SELECT SUM(distance),COUNT(*) FROM flights WHERE unique_carrier='TW'",
    "SELECT unique_carrier,0,COUNT(*) FROM flights WHERE origin_state_abr='LA' GROUP BY unique_carrier",
    "SELECT unique_carrier,0,COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest_state_abr='CA' GROUP BY unique_carrier",
    "SELECT year_date,0,COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest='JFK' GROUP BY year_date",
    "SELECT year_date,SUM(distance),COUNT(*) FROM flights WHERE unique_carrier='9E' GROUP BY year_date",
    "SELECT origin_state_abr,SUM(air_time),COUNT(*) FROM flights WHERE dest='HPN' GROUP BY origin_state_abr",
    "SELECT unique_carrier,SUM(dep_delay),COUNT(*) FROM flights WHERE year_date=2005 AND origin='PHX' GROUP BY unique_carrier",
    "SELECT dest_state_abr,0,COUNT(*) FROM flights WHERE distance>25000 GROUP BY dest_state_abr",
    "SELECT unique_carrier,0,COUNT(*) FROM flights WHERE air_time>10000 AND dep_delay>15000 GROUP BY unique_carrier",
    "SELECT year_date,SUM(arr_delay*dep_delay),COUNT(*) FROM flights WHERE origin_state_abr='CA' AND dest_state_abr='HI' GROUP BY year_date",
    "SELECT dest_state_abr,SUM(taxi_out)-SUM(taxi_in),COUNT(*) FROM flights WHERE unique_carrier='UA' AND origin='ATL' GROUP BY dest_state_abr",
)
PANDAS_TO_CSV = pd.DataFrame.to_csv
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
CHUNK = 1024 * 1024


class StreamError(ValueError):
    pass


class BatchLimitReached(Exception):
    pass


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('utf-8')).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write('\n')
        target.flush()
        os.fsync(target.fileno())
    os.replace(str(temporary), str(path))


def parameters(rows=200000, batch_size=100000, generation_seed=41001,
               sampling_seed=81001, sample_rate=0.01, input_limit=5000000,
               retain_population=False):
    batches = (rows + batch_size - 1) // batch_size if batch_size > 0 else 0
    if not 0 < rows <= 1000000000 or not 0 < batch_size <= 1000000 or input_limit <= 0:
        raise StreamError('Rows, batch size, or input limit is outside the supported range')
    if not math.isfinite(sample_rate) or not 0 <= sample_rate <= 1:
        raise StreamError('Invalid Bernoulli sample rate')
    if min(generation_seed, sampling_seed) < 0 or max(generation_seed, sampling_seed) + batches >= 2 ** 32:
        raise StreamError('A batch random seed exceeds NumPy RandomState limits')
    if retain_population and rows > 1000000:
        raise StreamError('Population retention is restricted to <=1M golden checks')
    return {'rows': int(rows), 'batch_size': int(batch_size),
            'generation_seed': int(generation_seed), 'sampling_seed': int(sampling_seed),
            'sample_rate': float(sample_rate), 'input_limit': int(input_limit),
            'retain_population': bool(retain_population)}


def empty_aggregates():
    return [{'query_no': i, 'query_name': name,
             'groups': [{'key': [], 'sum': 0, 'count': 0}] if i < 2 else []}
            for i, name in enumerate(QUERY_NAMES)]


def aggregate_frame(frame, previous):
    if list(frame.columns) != list(COLUMNS):
        raise StreamError('Generated frame columns differ from the pinned descriptor')
    cats = {name: frame[name].to_numpy() for name in COLUMNS[:6]}
    tenths = {}
    for name in COLUMNS[6:]:
        values = frame[name].to_numpy(dtype=np.float64) * 10
        if not np.all(np.isfinite(values)) or not np.all(np.abs(values - np.rint(values)) < 1e-6):
            raise StreamError('Generated numeric value is not a finite decimal tenth')
        tenths[name] = np.rint(values).astype(np.int64)
    dep, arr = tenths['DEP_DELAY'], tenths['ARR_DELAY']
    max_product = int(np.max(np.abs(dep))) * int(np.max(np.abs(arr))) if len(frame) else 0
    if max_product * max(len(frame), 1) > np.iinfo(np.int64).max:
        raise StreamError('Per-batch product sum exceeds exact int64 accumulation')
    origin, carrier = cats['ORIGIN'], cats['UNIQUE_CARRIER']
    os_state, ds_state = cats['ORIGIN_STATE_ABR'], cats['DEST_STATE_ABR']
    year, dest = cats['YEAR_DATE'], cats['DEST']
    specs = [
        (origin == 'ATL', None, dep),
        (carrier == 'TW', None, tenths['DISTANCE']),
        (os_state == 'LA', carrier, None),
        ((os_state == 'LA') & (ds_state == 'CA'), carrier, None),
        ((os_state == 'LA') & (dest == 'JFK'), year, None),
        (carrier == '9E', year, tenths['DISTANCE']),
        (dest == 'HPN', os_state, tenths['AIR_TIME']),
        ((year == 2005) & (origin == 'PHX'), carrier, dep),
        (tenths['DISTANCE'] > 25000, ds_state, None),
        ((tenths['AIR_TIME'] > 10000) & (dep > 15000), carrier, None),
        ((os_state == 'CA') & (ds_state == 'HI'), year, arr * dep),
        ((carrier == 'UA') & (origin == 'ATL'), ds_state,
         tenths['TAXI_OUT'] - tenths['TAXI_IN']),
    ]
    output = []
    for i, (mask, keys, values) in enumerate(specs):
        groups = {tuple(item['key']): [int(item['sum']), int(item['count'])]
                  for item in previous[i]['groups']}
        count = int(np.count_nonzero(mask))
        if count:
            if keys is None:
                unique, inverse = [None], np.zeros(count, dtype=np.int64)
            else:
                unique, inverse = np.unique(keys[mask], return_inverse=True)
            counts = np.bincount(inverse, minlength=len(unique))
            sums = np.zeros(len(unique), dtype=np.int64)
            if values is not None:
                selected = values[mask]
                if int(np.max(np.abs(selected))) * count > np.iinfo(np.int64).max:
                    raise StreamError('Per-batch aggregate sum exceeds int64')
                np.add.at(sums, inverse, selected)
            for key, subtotal, group_count in zip(unique, sums, counts):
                if isinstance(key, np.generic):
                    key = key.item()
                group_key = () if keys is None else (key,)
                old = groups.setdefault(group_key, [0, 0])
                old[0] += int(subtotal)
                old[1] += int(group_count)
        output.append({'query_no': i, 'query_name': QUERY_NAMES[i],
                       'groups': [{'key': list(key), 'sum': value[0], 'count': value[1]}
                                  for key, value in sorted(groups.items())]})
    return output


def aggregate_results(aggregates):
    output = []
    for item in aggregates:
        i = item['query_no']
        rows = []
        for group in item['groups']:
            total, count = group['sum'], group['count']
            if i in (2, 3, 4, 8, 9):
                numerator, denominator = count, 1
            elif i in (0, 1, 7):
                numerator, denominator = total, 10 * count
            else:
                numerator, denominator = total, 100 if i == 10 else 10
            rows.append(dict(group, numerator=numerator, denominator=denominator,
                             value=str(Decimal(numerator) / Decimal(denominator)) if denominator else None))
        output.append(dict(item, sql=ORIGINAL_SQL[i], groups=rows))
    return output


class StreamRun:
    """Commit only after file fsync; on recovery verify/truncate to sealed offsets."""

    def __init__(self, output_dir, data_dir, binding):
        self.output_dir, self.data_dir = Path(output_dir), Path(data_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint = self.output_dir / 'checkpoint.json'
        self.binding = binding
        self.config = binding['config']
        self.names = ['sample.csv'] + (['population.csv'] if self.config['retain_population'] else [])
        self.executed_batches = []
        self.truncated_bytes = {}
        if self.checkpoint.exists():
            state = json.loads(self.checkpoint.read_text(encoding='utf-8'))
            seal = state.pop('checkpoint_sha256', None)
            if seal != digest_json(state):
                raise StreamError('Checkpoint content seal differs')
            if state.get('binding') != digest_json(binding):
                raise StreamError('Binding differs: input, source, runtime, query, seed or configuration changed')
            if set(state.get('files', {})) != set(self.names):
                raise StreamError('Checkpoint output file inventory differs')
            self.state = state
        else:
            if any((self.data_dir / name).exists() for name in self.names):
                raise StreamError('Unsealed output exists without its checkpoint')
            self.state = {'version': 1, 'binding': digest_json(binding), 'binding_details': binding,
                          'status': 'RUNNING', 'next_batch': 0, 'rows_generated': 0,
                          'sample_rows': 0, 'aggregates': empty_aggregates(),
                          'files': {name: {'offset': 0, 'sha256': EMPTY_SHA256} for name in self.names}}
            self._checkpoint(self.state)
        self.hashes = {}
        # Verify every committed prefix before truncating any uncommitted tail.
        for name in self.names:
            path, record = self.data_dir / name, self.state['files'][name]
            offset = record['offset']
            if not isinstance(offset, int) or offset < 0:
                raise StreamError('Checkpoint output offset is invalid')
            if not path.exists() and offset:
                raise StreamError('Output is shorter than its committed offset')
            if path.exists() and path.stat().st_size < offset:
                raise StreamError('Output is shorter than its committed offset')
            digest = hashlib.sha256()
            if path.exists():
                with path.open('rb') as source:
                    remaining = offset
                    while remaining:
                        block = source.read(min(CHUNK, remaining))
                        if not block:
                            raise StreamError('Short output prefix')
                        digest.update(block)
                        remaining -= len(block)
            if digest.hexdigest() != record['sha256']:
                raise StreamError('Committed prefix hash differs: %s' % name)
            self.hashes[name] = digest
        for name in self.names:
            path = self.data_dir / name
            offset = self.state['files'][name]['offset']
            if path.exists() and path.stat().st_size > offset:
                self.truncated_bytes[name] = path.stat().st_size - offset
                with path.open('r+b') as target:
                    target.truncate(offset)
                    target.flush()
                    os.fsync(target.fileno())

    @property
    def next_batch(self):
        return self.state['next_batch']

    def _checkpoint(self, state):
        atomic_json(self.checkpoint, dict(state, checkpoint_sha256=digest_json(state)))

    def accept(self, frame, batch_number):
        if batch_number != self.next_batch:
            raise StreamError('Batch replay or gap: expected %d, got %d' % (self.next_batch, batch_number))
        expected = min(self.config['batch_size'], self.config['rows'] - self.state['rows_generated'])
        if len(frame) != expected or expected <= 0:
            raise StreamError('Batch row count differs from the configured population')
        aggregates = aggregate_frame(frame, self.state['aggregates'])
        # A local RandomState never consumes the vendor's global np.random state.
        sampler = np.random.RandomState(self.config['sampling_seed'] + batch_number)
        keep = sampler.random_sample(len(frame)) < self.config['sample_rate']
        payloads = {'sample.csv': frame.loc[keep]}
        if self.config['retain_population']:
            payloads['population.csv'] = frame
        files, hashes = {}, {}
        for name in self.names:
            old_offset = self.state['files'][name]['offset']
            text = PANDAS_TO_CSV(payloads[name], index=False, header=old_offset == 0)
            payload = text.encode('utf-8')
            path = self.data_dir / name
            actual_size = path.stat().st_size if path.exists() else 0
            if actual_size != old_offset:
                raise StreamError('Output size changed after checkpoint verification')
            with path.open('ab') as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            digest = self.hashes[name].copy()
            digest.update(payload)
            hashes[name] = digest
            files[name] = {'offset': old_offset + len(payload), 'sha256': digest.hexdigest()}
        next_batch = batch_number + 1
        rows_generated = self.state['rows_generated'] + len(frame)
        state = dict(self.state, next_batch=next_batch, rows_generated=rows_generated,
                     sample_rows=self.state['sample_rows'] + int(keep.sum()), files=files,
                     aggregates=aggregates,
                     status='COMPLETE' if rows_generated == self.config['rows'] else 'RUNNING')
        self._checkpoint(state)
        self.state, self.hashes = state, hashes
        self.executed_batches.append(batch_number)

    def finish(self):
        complete = self.state['rows_generated'] == self.config['rows']
        result = {'status': 'PASS' if complete else 'PARTIAL',
                  'stage': 'FLIGHTS_GENERATION_AND_12_QUERY_GROUND_TRUTH',
                  'paper_scale_reached': complete and self.config['rows'] == 1000000000,
                  'rows_generated': self.state['rows_generated'],
                  'sample_rows': self.state['sample_rows'], 'next_batch': self.next_batch,
                  'executed_batches_this_invocation': self.executed_batches,
                  'truncated_uncommitted_bytes': self.truncated_bytes,
                  'files': self.state['files'], 'binding': self.state['binding']}
        atomic_json(self.output_dir / 'ground_truth.json',
                    {'complete': complete, 'population_rows': self.state['rows_generated'],
                     'numeric_representation': 'Exact integer tenths; products in hundredths; AVG rational',
                     'queries': aggregate_results(self.state['aggregates'])})
        atomic_json(self.output_dir / 'generation_result.json', result)
        return result


class RunLock:
    """OS file lock is released after interruption; an old lock file is harmless."""

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        if not self.path.stat().st_size:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise StreamError('Another generator owns this run')
        return self

    def __exit__(self, *args):
        self.handle.close()


def build_binding(config):
    source_hash, csv_hash = file_sha256(VENDOR), file_sha256(ROOT / 'data/flights/sample.csv')
    descriptor_hash = file_sha256(ROOT / 'data/flights/sample.json')
    if (source_hash, csv_hash, descriptor_hash) != (SOURCE_SHA256, CSV_SHA256, DESCRIPTOR_SHA256):
        raise StreamError('Pinned source/CSV/descriptor input hash differs')
    query_path = ROOT / 'code/benchmarks/flights/sql/aqp_queries.sql'
    queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
    normalize = lambda text: ' '.join(text.lower().split())
    if list(map(normalize, queries)) != list(map(normalize, ORIGINAL_SQL)):
        raise StreamError('The 12 source queries changed; revalidate the aggregate adapter')
    return {'config': config,
            'input_seal': {'source_sha256': source_hash, 'sample_csv_sha256': csv_hash,
                           'descriptor_sha256': descriptor_hash, 'query_sha256': file_sha256(query_path)},
            'adapter_sha256': file_sha256(Path(__file__)),
            'runtime': {'python': platform.python_version(), 'numpy': np.__version__,
                        'pandas': pd.__version__, 'scipy': scipy.__version__,
                        'platform': platform.platform()}}


def original_arguments(config, output):
    return [str(VENDOR), '--sample-file', str(ROOT / 'data/flights/sample.csv'),
            '--sample-descriptor', str(ROOT / 'data/flights/sample.json'),
            '--size', str(config['rows']), '--batchsize', str(config['batch_size']),
            '--random-seed', str(config['generation_seed']), '--num-samples', str(config['input_limit']),
            '--output-file', str(output)]


def adapted_class(start_batch):
    """Only suppress auto-execution and start the existing loop at a sealed batch."""
    text = VENDOR.read_text(encoding='utf-8')
    tree = ast.parse(text, filename=str(VENDOR))
    final = tree.body[-1]
    if not (isinstance(final, ast.Expr) and isinstance(final.value, ast.Call)
            and isinstance(final.value.func, ast.Name) and final.value.func.id == 'DataGen'):
        raise StreamError('Unexpected vendor auto-execution shape')
    tree.body.pop()
    changed = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id == 'batch_i' and isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'range'
                and len(node.iter.args) == 1 and isinstance(node.iter.args[0], ast.Name)
                and node.iter.args[0].id == 'num_batches'):
            node.iter.args.insert(0, ast.Name(id='_resume_batch_start', ctx=ast.Load()))
            changed += 1
    if changed != 1:
        raise StreamError('Unexpected vendor batch loop shape')
    ast.fix_missing_locations(tree)
    namespace = {'__name__': '_sealed_idebench_adapter', '__file__': str(VENDOR),
                 '_resume_batch_start': start_batch}
    exec(compile(tree, str(VENDOR), 'exec'), namespace)
    record = {'original_source_sha256': SOURCE_SHA256,
              'original_source_file_unchanged': True,
              'adaptations': ['Remove only the terminal DataGen() auto-execution call',
                              'Replace range(num_batches) with range(_resume_batch_start,num_batches)',
                              'Wrap process_batch only to identify the batch and route its original to_csv'],
              'statistical_generation_body_changed': False,
              'adapted_ast_sha256': hashlib.sha256(ast.dump(tree).encode('utf-8')).hexdigest()}
    return namespace['DataGen'], record


def generate(config, output_dir, data_dir, max_batches=None):
    binding = build_binding(config)
    with RunLock(Path(output_dir) / '.run.lock'):
        writer = StreamRun(output_dir, data_dir, binding)
        if writer.state['status'] == 'COMPLETE':
            return writer.finish()
        original_class, adaptation = adapted_class(writer.next_batch)
        atomic_json(Path(output_dir) / 'source_adapter.json', adaptation)
        original_method = original_class.process_batch
        active_batch = [None]
        sentinel = '__SEALED_FLIGHTS_STREAM_OUTPUT__'

        def process_batch(self, batch_number):
            active_batch[0] = batch_number
            original_method(self, batch_number)
            if max_batches is not None and len(writer.executed_batches) >= max_batches:
                raise BatchLimitReached()

        def to_csv(frame, path_or_buf=None, *args, **kwargs):
            if (path_or_buf != sentinel or args or kwargs.get('index') is not False
                    or set(kwargs) - {'index', 'header', 'mode'}):
                raise StreamError('An unexpected vendor CSV write was refused')
            writer.accept(frame, active_batch[0])

        original_class.process_batch = process_batch
        old_argv, old_to_csv = sys.argv, pd.DataFrame.to_csv
        try:
            sys.argv = original_arguments(config, sentinel)
            pd.DataFrame.to_csv = to_csv
            with (Path(output_dir) / 'generator.log').open('a', encoding='utf-8') as log:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    try:
                        original_class()
                    except BatchLimitReached:
                        print('Stopped after a committed batch; next batch:', writer.next_batch)
        finally:
            sys.argv, pd.DataFrame.to_csv = old_argv, old_to_csv
        return writer.finish()


def sqlite_reference(csv_path, db_path):
    """Independent CSV->Decimal->SQLite exact SQL, without NumPy group reduction."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    rows = 0
    try:
        connection.execute('DROP TABLE IF EXISTS flights')
        ddl = ','.join('"%s" %s' % (name.lower(), 'INTEGER' if i == 0 or i >= 6 else 'TEXT')
                       for i, name in enumerate(COLUMNS))
        connection.execute('CREATE TABLE flights (' + ddl + ')')
        pending = []
        with Path(csv_path).open('r', encoding='utf-8', newline='') as source:
            reader = csv.reader(source)
            if next(reader, []) != list(COLUMNS):
                raise StreamError('Independent reference CSV columns differ')
            for row in reader:
                if not row:
                    continue
                if len(row) != 12:
                    raise StreamError('Independent reference CSV row width differs')
                values = [int(row[0])] + row[1:6]
                for value in row[6:]:
                    exact = Decimal(value) * 10
                    if not exact.is_finite() or exact != exact.to_integral_value():
                        raise StreamError('Independent reference value is not an exact tenth')
                    values.append(int(exact))
                pending.append(values)
                rows += 1
                if len(pending) == 10000:
                    connection.executemany('INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', pending)
                    pending = []
        if pending:
            connection.executemany('INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', pending)
        connection.commit()
        aggregates = []
        for i, query in enumerate(EXACT_SQL):
            groups = [{'key': list(row[:-2]), 'sum': int(row[-2] or 0), 'count': int(row[-1])}
                      for row in connection.execute(query).fetchall()]
            aggregates.append({'query_no': i, 'query_name': QUERY_NAMES[i],
                               'groups': sorted(groups, key=lambda item: item['key'])})
        return {'rows': rows, 'aggregates': aggregates, 'sqlite_version': sqlite3.sqlite_version,
                'storage': 'six numeric columns are exact integer tenths',
                'reference_sql': list(EXACT_SQL)}
    finally:
        connection.close()


def compare_csvs(reference, candidate, expected_rows):
    rows = 0
    with Path(reference).open('r', encoding='utf-8', newline='') as left, \
            Path(candidate).open('r', encoding='utf-8', newline='') as right:
        first, second = csv.reader(left), csv.reader(right)
        if next(first, []) != list(COLUMNS) or next(second, []) != list(COLUMNS):
            raise StreamError('Golden column headers differ')
        import itertools
        marker = object()
        for lrow, rrow in itertools.zip_longest(first, second, fillvalue=marker):
            if lrow != rrow:
                raise StreamError('Golden row/column content differs at row %d' % (rows + 1))
            rows += 1
    if rows != expected_rows:
        raise StreamError('Golden CSV row count differs')
    return {'rows': rows, 'columns_per_row': 12, 'all_row_values_identical': True,
            'reference_sha256': file_sha256(reference), 'candidate_sha256': file_sha256(candidate)}


def golden(config, output_dir, data_dir, provided_reference=None):
    if not 200000 <= config['rows'] <= 1000000 or not config['retain_population']:
        raise StreamError('Golden checks require 200K--1M rows and retained population')
    output_dir, data_dir = Path(output_dir), Path(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    binding = build_binding(config)
    receipt_path = output_dir / 'golden_validation.json'
    old = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else None
    reference = Path(provided_reference) if provided_reference else data_dir / 'original.csv'
    reference = reference.resolve()
    reference.relative_to((ROOT / 'data/flights/generated').resolve())
    command = [sys.executable, '-B'] + original_arguments(config, reference)
    if provided_reference:
        if not reference.is_file():
            raise StreamError('Provided original reference CSV is missing')
        origin = 'Explicitly provided CSV; original vendor subprocess command/log recorded separately'
    elif old and old.get('binding') == digest_json(binding) and old.get('reference_sha256') == file_sha256(reference):
        origin = 'Reused sealed original vendor CSV from the previous golden check'
    else:
        if reference.exists():
            raise StreamError('Unsealed original CSV exists; use --reference-csv to explicitly identify it')
        with (output_dir / 'original.log').open('wb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, cwd=str(ROOT))
        origin = 'Unmodified pinned vendor executed in a separate Python process'
    continuous = generate(config, output_dir / 'continuous', data_dir / 'continuous')
    resumed_output, resumed_data = output_dir / 'resumed', data_dir / 'resumed'
    checkpoint = resumed_output / 'checkpoint.json'
    first = None
    if not checkpoint.exists():
        first = generate(config, resumed_output, resumed_data, max_batches=1)
        # Simulate a hard interruption after data append but before the next commit.
        for name in ['sample.csv', 'population.csv']:
            with (resumed_data / name).open('ab') as target:
                target.write(b'UNCOMMITTED INTERRUPTED APPEND\n')
                target.flush()
                os.fsync(target.fileno())
    resumed = generate(config, resumed_output, resumed_data)
    csv_comparison = compare_csvs(reference, data_dir / 'continuous/population.csv', config['rows'])
    resumed_comparison = compare_csvs(reference, resumed_data / 'population.csv', config['rows'])
    if file_sha256(data_dir / 'continuous/sample.csv') != file_sha256(resumed_data / 'sample.csv'):
        raise StreamError('Resumed Bernoulli sample differs from continuous output')
    truth = sqlite_reference(reference, output_dir / 'reference.sqlite')
    if truth['rows'] != config['rows']:
        raise StreamError('SQLite reference row count differs')
    atomic_json(output_dir / 'sqlite_exact_state.json', truth)
    for folder in ['continuous', 'resumed']:
        state = json.loads((output_dir / folder / 'checkpoint.json').read_text(encoding='utf-8'))
        if state['aggregates'] != truth['aggregates']:
            raise StreamError('Independent SQLite 12-query aggregates differ for ' + folder)
    report = {'status': 'PASS', 'stage': 'SMALL_SCALE_GOLDEN_ONLY', 'paper_scale_reached': False,
              'population_rows': config['rows'], 'config': config, 'binding': digest_json(binding),
              'reference_provenance': origin, 'original_vendor_command': command,
              'original_source_sha256': SOURCE_SHA256, 'reference_sha256': file_sha256(reference),
              'row_and_column_comparison': csv_comparison, 'resumed_row_comparison': resumed_comparison,
              'all_12_sqlite_query_states_exactly_equal': True,
              'groups_per_query': [len(item['groups']) for item in truth['aggregates']],
              'sample_sha256': file_sha256(resumed_data / 'sample.csv'),
              'continuous': continuous, 'interrupted_first_invocation': first or (old or {}).get('interrupted_first_invocation'),
              'resumed': resumed, 'generation_1b_executed': False,
              'note': '200K--1M gold standard validates adapter equivalence and recovery; not a 1B reproduction.'}
    atomic_json(receipt_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['generate', 'golden'])
    parser.add_argument('--rows', type=int, default=200000)
    parser.add_argument('--batch-size', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=41001)
    parser.add_argument('--sampling-seed', type=int, default=81001)
    parser.add_argument('--sample-rate', type=float, default=0.01)
    parser.add_argument('--input-limit', type=int, default=5000000)
    parser.add_argument('--run-name', default='golden-200k')
    parser.add_argument('--max-batches', type=int)
    parser.add_argument('--retain-population', action='store_true')
    parser.add_argument('--reference-csv', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', args.run_name):
        parser.error('run-name must be a simple project-local directory name')
    if args.max_batches is not None and args.max_batches <= 0:
        parser.error('max-batches must be positive')
    config = parameters(args.rows, args.batch_size, args.seed, args.sampling_seed,
                        args.sample_rate, args.input_limit,
                        args.retain_population or args.command == 'golden')
    output_dir = ROOT / 'output/full/flights' / args.run_name
    data_dir = ROOT / 'data/flights/generated' / args.run_name
    for path in [output_dir, data_dir]:
        path.resolve().relative_to(ROOT)
    try:
        if args.command == 'golden':
            with RunLock(output_dir / '.golden.lock'):
                result = golden(config, output_dir, data_dir, args.reference_csv)
        else:
            result = generate(config, output_dir, data_dir, args.max_batches)
        print(json.dumps({key: result[key] for key in result if key in
                          ['status', 'stage', 'paper_scale_reached', 'population_rows',
                           'rows_generated', 'sample_rows', 'next_batch',
                           'all_12_sqlite_query_states_exactly_equal', 'groups_per_query',
                           'executed_batches_this_invocation', 'truncated_uncommitted_bytes']}))
        return 0
    except Exception as exc:
        atomic_json(output_dir / 'failure.json', {'status': 'FAIL', 'error': repr(exc),
                                                'generation_1b_executed_by_this_validation': False})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
