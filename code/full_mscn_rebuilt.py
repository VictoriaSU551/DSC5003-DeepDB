"""Independent MSCN samples/bitmaps; original inputs and training stay read-only."""
import argparse
import copy
import csv
import hashlib
import json
import math
import inspect
import os
from pathlib import Path
import pickle
import random
import re
import shutil
import sqlite3
import struct
import sys
import time

import full_mscn as base

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/mscn/rebuilt'
OUT = ROOT / 'output/full/mscn/rebuilt_seed1/results'
TABLES = {'title': 't', 'cast_info': 'ci', 'movie_companies': 'mc',
          'movie_info': 'mi', 'movie_info_idx': 'mi_idx', 'movie_keyword': 'mk'}
PROTOCOL = {'name': 'independent_consistent_mscn_samples_v1', 'sample_seed': 1,
            'sample_rows_per_table': 1000, 'sampling': 'Python3.8 Random.sample(range(n),k), table-derived SHA256 seed',
            'null_policy': 'Restore sealed numeric sentinel to SQL NULL; unknown fails a predicate',
            'bit_order': 'NumPy packbits default MSB first', 'header': 'little-endian uint32 table count'}


def sample_positions(length, table, seed=1, count=1000):
    if not isinstance(length, int) or not 0 < count <= length:
        raise ValueError('Cannot take the requested uniform table sample')
    key = '{}:{}:{}'.format(PROTOCOL['name'], seed, table).encode('utf-8')
    local_seed = int.from_bytes(hashlib.sha256(key).digest(), 'big')
    return random.Random(local_seed).sample(range(length), count)


def restore_sql_values(values, sentinel):
    result = []
    for value in values:
        if value is None or math.isnan(float(value)) or (sentinel is not None and value == sentinel):
            result.append(None)
        elif not math.isfinite(float(value)):
            raise ValueError('Nonfinite sample value')
        elif float(value).is_integer():
            result.append(int(value))
        else:
            result.append(float(value))
    return result


def _number(value):
    if re.fullmatch(r'[+-]?\d+', str(value)):
        return int(value)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Predicate literal is not finite')
    return int(number) if number.is_integer() else number


def canonical_predicate(column, operator, value):
    if operator not in ('=', '<', '>', '<=', '>='):
        raise ValueError('Unsupported predicate operator ' + operator)
    number = _number(value)
    if operator in ('<=', '>='):
        if not isinstance(number, int):
            raise ValueError('Closed-bound conversion requires an integer literal/domain')
        number += 1 if operator == '<=' else -1
        if not -(2 ** 63) <= number <= 2 ** 63 - 1:
            raise ValueError('Closed integer boundary overflow outside SQLite range')
        operator = '<' if operator == '<=' else '>'
    return column, operator, number


def predicate_bitmap(sample, predicates):
    import numpy as np
    count = len(next(iter(sample['columns'].values())))
    result = np.ones(count, dtype=bool)
    functions = {'=': np.equal, '<': np.less, '>': np.greater, '<=': np.less_equal, '>=': np.greater_equal}
    for column, operator, value in predicates:
        if column not in sample['columns']:
            raise ValueError('Unknown sample column ' + column)
        if operator not in functions:
            raise ValueError('Unsupported predicate operator ' + operator)
        values = np.asarray(sample['columns'][column], dtype=np.float64)
        result &= np.isfinite(values) & functions[operator](values, _number(value))
    return result


def _quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


class SQLiteOracle:
    """Real SQL NULLs and SELECT semantics, independent of NumPy comparisons."""
    def __init__(self, samples):
        self.connection = sqlite3.connect(':memory:')
        self.samples = samples
        for table, sample in samples.items():
            names = list(sample['columns'])
            count = len(sample['columns'][names[0]])
            if any(len(sample['columns'][name]) != count for name in names):
                raise ValueError('Sample column lengths differ')
            columns = ','.join(_quoted(name) + ' NUMERIC' for name in names)
            self.connection.execute('CREATE TABLE ' + _quoted(table) + ' (__sample_index INTEGER PRIMARY KEY,' + columns + ')')
            rows = ((i,) + tuple(sample['columns'][name][i] for name in names) for i in range(count))
            self.connection.executemany('INSERT INTO ' + _quoted(table) + ' VALUES (' + ','.join(['?'] * (len(names) + 1)) + ')', rows)
            for index, name in enumerate(names):
                self.connection.execute('CREATE INDEX ' + _quoted(table + '_ix_' + str(index)) + ' ON ' + _quoted(table) + '(' + _quoted(name) + ')')

    def bitmap(self, table, predicates):
        import numpy as np
        conditions, parameters = [], []
        for column, operator, value in predicates:
            if column not in self.samples[table]['columns']:
                raise ValueError('Unknown SQL sample column ' + column)
            if operator not in ('=', '<', '>', '<=', '>='):
                raise ValueError('Unsupported SQL predicate operator ' + operator)
            conditions.append(_quoted(column) + operator + '?')
            parameters.append(_number(value))
        query = 'SELECT __sample_index FROM ' + _quoted(table)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY __sample_index'
        count = len(next(iter(self.samples[table]['columns'].values())))
        result = np.zeros(count, dtype=bool)
        for (position,) in self.connection.execute(query, parameters):
            result[position] = True
        return result

    def close(self):
        self.connection.close()


def sqlite_bitmap(sample, predicates):
    oracle = SQLiteOracle({sample['table']: sample})
    try:
        return oracle.bitmap(sample['table'], predicates)
    finally:
        oracle.close()


def row_tables_predicates(row, samples):
    ordered, aliases = [], {}
    for declaration in row[0].split(','):
        match = re.fullmatch(r'\s*([A-Za-z_]\w*)\s+(?:AS\s+)?([A-Za-z_]\w*)\s*', declaration, re.I)
        if not match:
            raise ValueError('Invalid table declaration or alias')
        table, alias = match.groups()
        if table not in samples or alias in aliases or table in aliases.values():
            raise ValueError('Unknown or ambiguous table/alias')
        aliases[alias] = table
        ordered.append((table, alias))
    predicates = {alias: [] for table, alias in ordered}
    parts = row[2].split(',') if row[2] else []
    if len(parts) % 3:
        raise ValueError('Invalid predicate triples')
    for offset in range(0, len(parts), 3):
        field, operator, value = parts[offset:offset + 3]
        match = re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)', field)
        if not match or match.group(1) not in aliases:
            raise ValueError('Unknown predicate alias')
        alias, column = match.groups()
        if column not in samples[aliases[alias]]['columns']:
            raise ValueError('Unknown predicate column')
        canonical_predicate(column, operator, value)
        predicates[alias].append((column, operator, _number(value)))
    for join in row[1].split(',') if row[1] else []:
        match = re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)=([A-Za-z_]\w*)\.([A-Za-z_]\w*)', join)
        if not match:
            raise ValueError('Unsupported join operator/form')
        for alias, column in [match.groups()[:2], match.groups()[2:]]:
            if alias not in aliases or column not in samples[aliases[alias]]['columns']:
                raise ValueError('Unknown join alias/column')
    return ordered, predicates


def bitmap_record(row, samples):
    import numpy as np
    ordered, predicates = row_tables_predicates(row, samples)
    blocks = [np.packbits(predicate_bitmap(samples[table], predicates[alias])).tobytes() for table, alias in ordered]
    return struct.pack('<I', len(blocks)) + b''.join(blocks)


def sql_to_row(sql, cardinality, join_vocabulary, convert_closed=True):
    match = re.fullmatch(r'\s*SELECT\s+COUNT\s*\(\s*\*\s*\)\s+FROM\s+(.+?)(?:\s+WHERE\s+(.+?))?\s*;?\s*', sql, re.I)
    if not match or int(cardinality) < 1:
        raise ValueError('Unsupported SQL SELECT or nonpositive truth')
    from_clause, where = match.groups()
    aliases, declarations = {}, []
    for declaration in from_clause.split(','):
        table_match = re.fullmatch(r'\s*([A-Za-z_]\w*)\s+(?:AS\s+)?([A-Za-z_]\w*)\s*', declaration, re.I)
        if not table_match:
            raise ValueError('Unsupported SQL table/alias')
        table, alias = table_match.groups()
        if table not in TABLES or alias in aliases or table in aliases.values():
            raise ValueError('Unknown or duplicate SQL table/alias')
        aliases[alias] = table
        declarations.append(table + ' ' + TABLES[table])
    def field(alias, column):
        if alias not in aliases:
            raise ValueError('Undeclared SQL alias ' + alias)
        return TABLES[aliases[alias]] + '.' + column
    joins, predicates = [], []
    for condition in re.split(r'\s+AND\s+', where, flags=re.I) if where else []:
        join = re.fullmatch(r'\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*', condition)
        if join:
            left, right = field(*join.groups()[:2]), field(*join.groups()[2:])
            alternatives = [left + '=' + right, right + '=' + left]
            selected = next((value for value in alternatives if value in join_vocabulary), None)
            if selected is None:
                raise ValueError('SQL join is outside the frozen training dictionary')
            joins.append(selected)
            continue
        predicate = re.fullmatch(r'\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(<=|>=|=|<|>)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*', condition)
        if not predicate:
            raise ValueError('Unsupported SQL predicate operator/form')
        alias, column, operator, literal = predicate.groups()
        full_column = field(alias, column)
        converted = canonical_predicate(full_column, operator, literal)
        predicates.extend([converted[0], converted[1] if convert_closed else operator,
                           str(converted[2] if convert_closed else _number(literal))])
    return [','.join(declarations), ','.join(joins), ','.join(predicates), str(int(cardinality))]


def query_joint_sha(row, bitmap, sample_manifest_sha256, source):
    return base.digest({'canonical_row': row, 'bitmap_sha256': hashlib.sha256(bitmap).hexdigest(),
                        'sample_manifest_sha256': sample_manifest_sha256, 'source': source})


def training_vocabulary(rows):
    columns, operators = set(), set()
    for row in rows:
        parts = row[2].split(',') if row[2] else []
        for offset in range(0, len(parts), 3):
            columns.add(parts[offset])
            operators.add(parts[offset + 1])
    return {'tables': sorted({table for row in rows for table in row[0].split(',')}),
            'columns': sorted(columns), 'operators': sorted(operators),
            'joins': sorted({join for row in rows for join in row[1].split(',')})}


def collect_workloads():
    from full_evaluation import workload_files
    from full_inventory import sql_tokens
    train_path = ROOT / 'data/mscn/data/train.csv'
    job_path = ROOT / 'data/mscn/workloads/job-light.csv'
    train, job = base.read_queries(train_path), base.read_queries(job_path)
    if len(train) != 100000 or len(job) != 70:
        raise ValueError('Rebuilt protocol requires official full 100K and JOB70')
    vocabulary = training_vocabulary(train)
    if vocabulary['operators'] != ['<', '=', '>']:
        raise ValueError('Unexpected frozen training operator dictionary')
    datasets = {'train': train, 'job-light': job, 'public-grouped': []}
    traces = {name: [] for name in datasets}
    sources = [base.file_record(path) for path in [train_path, job_path, ROOT / 'data/mscn/data/column_min_max_vals.csv']]
    for name, path in [('train', train_path), ('job-light', job_path)]:
        source_hash = base.sha256(path)
        for index, row in enumerate(datasets[name]):
            traces[name].append({'group': 'job_light' if name == 'job-light' else 'train', 'query_no': index,
                                 'source_path': str(path.relative_to(ROOT)), 'source_sha256': source_hash,
                                 'source_sql_sha256': hashlib.sha256(base.query_sql(row).encode()).hexdigest(),
                                 'original_row': row})
    for group, sql_path, truth_path in workload_files(True):
        statements = [line.strip() for line in sql_path.read_text().splitlines() if line.strip()]
        with truth_path.open(newline='', encoding='utf-8') as stream:
            truths = list(csv.DictReader(stream))
        if len(statements) != len(truths):
            raise ValueError('Public SQL/truth counts differ')
        sql_hash, truth_hash = base.sha256(sql_path), base.sha256(truth_path)
        sources.extend([base.file_record(sql_path), base.file_record(truth_path)])
        for index, (sql, truth) in enumerate(zip(statements, truths)):
            if int(truth['query_no']) != index or sql_tokens(sql) != sql_tokens(truth['query']):
                raise ValueError('Public SQL/truth query permutation or mismatch')
            if group == 'job_light':
                if (base.normalize_numeric_sql(sql) != base.normalize_numeric_sql(base.query_sql(job[index]))
                        or int(truth['cardinality_true']) != int(job[index][3])):
                    raise ValueError('Official JOB70 differs from published query/truth')
                traces['job-light'][index].update(published_sql_sha256=sql_hash, published_truth_sha256=truth_hash)
                continue
            row = sql_to_row(sql, int(truth['cardinality_true']), set(vocabulary['joins']))
            original = sql_to_row(sql, int(truth['cardinality_true']), set(vocabulary['joins']), False)
            datasets['public-grouped'].append(row)
            traces['public-grouped'].append({'group': group, 'query_no': index,
                'source_path': str(sql_path.relative_to(ROOT)), 'source_sha256': sql_hash,
                'source_sql': sql, 'source_sql_sha256': hashlib.sha256(sql.encode()).hexdigest(),
                'truth_path': str(truth_path.relative_to(ROOT)), 'truth_sha256': truth_hash, 'original_row': original})
    if len(datasets['public-grouped']) != 683:
        raise ValueError('Expected all 683 public generalization queries')
    for name, rows in datasets.items():
        current = training_vocabulary(rows)
        for field in ('tables', 'columns', 'operators', 'joins'):
            unknown = set(current[field]) - set(vocabulary[field])
            if unknown:
                raise ValueError('Unknown {} encoding symbols in {}: {}'.format(field, name, sorted(unknown)))
    return datasets, traces, vocabulary, sources


def read_hdf_sample(table, hdf_path, metadata, data_root, source_hash, meta_hash):
    import pandas as pd
    target = data_root / 'samples' / (table + '.json')
    sampling_seal = base.digest({'source': inspect.getsource(sample_positions) + inspect.getsource(restore_sql_values)
                                + inspect.getsource(read_hdf_sample), 'protocol': PROTOCOL})
    binding = {'hdf_sha256': source_hash, 'metadata_sha256': meta_hash, 'sampling_sha256': sampling_seal,
               'table': table, 'seed': 1, 'count': 1000}
    if target.exists():
        sample = json.loads(target.read_text(encoding='utf-8'))
        if sample.get('binding') != binding or sample.get('payload_sha256') != base.digest(sample['payload']):
            raise ValueError('Cached uniform sample binding/hash changed: ' + table)
        return sample['payload']
    with pd.HDFStore(str(hdf_path), mode='r') as store:
        storer = store.get_storer('df')
        length = int(storer.nrows)
        if length != int(metadata['length']):
            raise ValueError('HDF is not the complete sealed table: ' + table)
        positions = sample_positions(length, table)
        selected, indices, dtypes = {}, {}, None
        for start in range(0, length, 250000):
            wanted = [p for p in positions if start <= p < start + 250000]
            if not wanted:
                continue
            block = store.select('df', start=start, stop=min(start + 250000, length))
            if dtypes is None:
                dtypes = {name: str(dtype) for name, dtype in block.dtypes.items()}
            for position in wanted:
                series = block.iloc[position - start]
                selected[position] = {name: value.item() if hasattr(value, 'item') else value for name, value in series.items()}
                value = block.index[position - start]
                indices[position] = value.item() if hasattr(value, 'item') else value
            del block
    if len(selected) != 1000:
        raise ValueError('Incomplete uniform HDF sample')
    full_columns = metadata['relevant_attributes_full']
    sentinels = dict(zip(full_columns, metadata['null_values_column']))
    raw = {name[len(table) + 1:]: [selected[position][name] for position in positions] for name in full_columns}
    sql_columns = {name: restore_sql_values(values, sentinels[table + '.' + name]) for name, values in raw.items()}
    keys = sql_columns['id']
    if any(value is None for value in keys) or len(set(keys)) != 1000:
        raise ValueError('Uniform sample primary keys are missing or duplicated')
    payload = {'table': table, 'alias': TABLES[table], 'population_rows': length,
               'positions': positions, 'hdf_index': [indices[position] for position in positions],
               'primary_keys': keys, 'raw_columns': raw, 'columns': sql_columns,
               'null_sentinels': {name[len(table) + 1:]: float(value) for name, value in sentinels.items()},
               'column_dtypes': dtypes,
               'null_counts': {name: sum(value is None for value in values) for name, values in sql_columns.items()}}
    base.atomic_json(target, {'binding': binding, 'payload': payload, 'payload_sha256': base.digest(payload)})
    print('SAMPLED', table, 'rows', 1000, 'source_rows', length, flush=True)
    return payload


def preparation_source_seal():
    functions = [sample_positions, restore_sql_values, _number, canonical_predicate, predicate_bitmap,
                 _quoted, SQLiteOracle, row_tables_predicates, bitmap_record, sql_to_row, query_joint_sha,
                 training_vocabulary, collect_workloads, read_hdf_sample, write_materialized_workload, prepare_rebuilt]
    return base.digest({'protocol': PROTOCOL, 'sources': [inspect.getsource(fn) for fn in functions]})


def write_materialized_workload(name, rows, traces, samples, sample_sha, encoding_sha, data_root, oracle, cache):
    import numpy as np
    stem = data_root / ('data/train' if name == 'train' else 'workloads/' + name)
    receipt = data_root / 'stages' / (name + '.json')
    source_records = [{k: v for k, v in trace.items() if k != 'original_row'} for trace in traces]
    binding = {'samples_sha256': sample_sha, 'encoding_sha256': encoding_sha,
               'query_sources_sha256': base.digest(source_records), 'preparation_source_sha256': preparation_source_seal()}
    if receipt.exists():
        prior = json.loads(receipt.read_text())
        if prior.get('status') != 'PASS' or prior.get('binding') != binding:
            raise ValueError('Existing bitmap stage differs from its input binding')
        base.verify_records(prior['artifacts'], data_root)
        print('REUSED_BITMAPS', name, len(rows), flush=True)
        return prior
    stem.parent.mkdir(parents=True, exist_ok=True)
    csv_path, bitmap_path = stem.with_suffix('.csv'), stem.with_suffix('.bitmaps')
    joint_path = stem.with_suffix('.joint.jsonl')
    csv_temp, bitmap_temp, joint_temp = [path.with_name(path.name + '.tmp') for path in [csv_path, bitmap_path, joint_path]]
    if name in ('train', 'job-light'):
        source = ROOT / ('data/mscn/data/train.csv' if name == 'train' else 'data/mscn/workloads/job-light.csv')
        shutil.copyfile(str(source), str(csv_temp))
    else:
        with csv_temp.open('w', newline='', encoding='utf-8') as stream:
            csv.writer(stream, delimiter='#', lineterminator='\n').writerows(rows)
    table_checks, sql_checks, closed_checks = 0, 0, 0
    with bitmap_temp.open('wb') as binary, joint_temp.open('w', encoding='utf-8', newline='\n') as joint:
        for index, (row, trace) in enumerate(zip(rows, traces)):
            ordered, predicates = row_tables_predicates(row, samples)
            _, original_predicates = row_tables_predicates(trace['original_row'], samples)
            blocks = []
            for table, alias in ordered:
                current = predicates[alias]
                key = (table, tuple(sorted(current)))
                if key not in cache:
                    values = predicate_bitmap(samples[table], current)
                    reference = oracle.bitmap(table, current)
                    if not np.array_equal(values, reference):
                        raise ValueError('SQLite/bitmap golden mismatch at {} row {} {}'.format(name, index, alias))
                    cache[key] = np.packbits(values).tobytes()
                    sql_checks += 1
                blocks.append(cache[key])
                original = original_predicates[alias]
                if original != current:
                    if not np.array_equal(oracle.bitmap(table, original), np.unpackbits(np.frombuffer(cache[key], dtype=np.uint8)).astype(bool)):
                        raise ValueError('Closed-bound SQL equivalence failed')
                    closed_checks += 1
                table_checks += 1
            packed = struct.pack('<I', len(blocks)) + b''.join(blocks)
            binary.write(packed)
            source = {k: value for k, value in trace.items() if k != 'original_row'}
            record = dict(source, row_no=index, table_order=[alias for table, alias in ordered],
                          cardinality_true=int(row[3]), bitmap_sha256=hashlib.sha256(packed).hexdigest(),
                          joint_sha256=query_joint_sha(row, packed, sample_sha, source))
            joint.write(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n')
        for stream in [binary, joint]:
            stream.flush()
            os.fsync(stream.fileno())
    for temporary, final in zip([csv_temp, bitmap_temp, joint_temp], [csv_path, bitmap_path, joint_path]):
        os.replace(str(temporary), str(final))
    structural = base.inspect_pair(csv_path, bitmap_path)
    result = {'status': 'PASS', 'binding': binding, 'queries': len(rows), 'per_table_checks': table_checks,
              'new_unique_sql_checks': sql_checks, 'closed_bound_sql_equivalence_checks': closed_checks,
              'structural': structural, 'artifacts': [base.file_record(path, data_root) for path in [csv_path, bitmap_path, joint_path]]}
    base.atomic_json(receipt, result)
    print('VERIFIED_BITMAPS', name, 'queries', len(rows), 'tables', table_checks, 'unique_SQL', sql_checks, flush=True)
    return result


def prepare_rebuilt(data_root=DATA):
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    if tuple(sys.version_info[:3]) != (3, 8, 20):
        raise ValueError('Prepare using the existing Python3.8.20 .venv runtime')
    # Audit only: none of the original bitmap payloads are used for rebuilding.
    base.audit_inputs(ROOT)
    protected = protected_cpp_artifacts()
    profile = ROOT / 'output/full/checkpoints/prepared_public-scale.json'
    profile_record = json.loads(profile.read_text())
    if profile_record.get('status') != 'PASS' or profile_record.get('profile') != 'public-scale':
        raise ValueError('Complete public-scale HDF seal is missing')
    recorded = {item['path']: item['sha256'] for item in profile_record['artifacts']}
    hdf_root = ROOT / 'output/full/prepared/public-scale/hdf'
    meta_path = hdf_root / 'meta_data.pkl'
    source_paths = [meta_path] + [hdf_root / (table + '.hdf') for table in TABLES]
    source_records = []
    for path in source_paths:
        relative = path.relative_to(ROOT).as_posix()
        actual_hash = base.sha256(path)
        if recorded.get(relative) != actual_hash:
            raise ValueError('Complete HDF/source seal changed: ' + relative)
        source_records.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': actual_hash})
    datasets, traces, vocabulary, query_sources = collect_workloads()
    binding = {'protocol': PROTOCOL, 'source_seal': preparation_source_seal(),
               'complete_hdf': source_records, 'queries': query_sources,
               'profile_receipt_sha256': base.sha256(profile),
               'original_wrapper_sha256': base.sha256(ROOT / 'code/full_mscn.py'),
               'official_commit': base.COMMIT, 'official_archive_sha256': base.ARCHIVE_SHA256,
               'declared_integer_schema_sha256': base.sha256(ROOT / 'code/benchmarks/job-light/setup-sql/tables_only.sql')}
    manifest_path = data_root / 'manifest.json'
    if manifest_path.exists():
        old = validate_rebuilt_manifest(data_root)
        if old['binding'] != binding:
            raise ValueError('Committed rebuilt data protocol changed; refusing replacement')
        return dict(old, reused_verified_materialization=True)
    with meta_path.open('rb') as stream:
        metadata = pickle.load(stream)
    samples = {}
    for table in TABLES:
        hdf_path = hdf_root / (table + '.hdf')
        samples[table] = read_hdf_sample(table, hdf_path, metadata[table], data_root,
                                       recorded[hdf_path.relative_to(ROOT).as_posix()], recorded[meta_path.relative_to(ROOT).as_posix()])
    for column in vocabulary['columns']:
        alias, attribute = column.split('.')
        table = next(table for table, code in TABLES.items() if code == alias)
        if any(value is not None and not isinstance(value, int) for value in samples[table]['columns'][attribute]):
            raise ValueError('Predicate SQL integer domain was not preserved: ' + column)
    sample_files = [data_root / 'samples' / (table + '.json') for table in TABLES]
    sample_manifest = {'status': 'PASS', 'protocol': PROTOCOL, 'complete_hdf': source_records,
                       'artifacts': [base.file_record(path, data_root) for path in sample_files]}
    base.atomic_json(data_root / 'samples_manifest.json', sample_manifest)
    sample_sha = base.sha256(data_root / 'samples_manifest.json')
    vocabulary['onehot_policy'] = 'Frozen upstream get_set_encoding sorted vocabulary; train only'
    vocabulary['minmax_source_sha256'] = base.sha256(ROOT / 'data/mscn/data/column_min_max_vals.csv')
    base.atomic_json(data_root / 'encoding.json', vocabulary)
    encoding_sha = base.sha256(data_root / 'encoding.json')
    (data_root / 'data').mkdir(exist_ok=True)
    shutil.copyfile(str(ROOT / 'data/mscn/data/column_min_max_vals.csv'), str(data_root / 'data/column_min_max_vals.csv'))
    oracle = SQLiteOracle(samples)
    cache, stages = {}, {}
    try:
        for name, rows in datasets.items():
            stages[name] = write_materialized_workload(name, rows, traces[name], samples, sample_sha, encoding_sha,
                                                       data_root, oracle, cache)
    finally:
        oracle.close()
    artifacts = [base.file_record(path, data_root) for path in sample_files + [data_root / 'samples_manifest.json',
                 data_root / 'encoding.json', data_root / 'data/column_min_max_vals.csv']]
    for name, stage in stages.items():
        artifacts.extend(stage['artifacts'])
        artifacts.append(base.file_record(data_root / 'stages' / (name + '.json'), data_root))
    result = {'status': 'PASS', 'binding': binding, 'source_wrapper_sha256_at_creation': base.sha256(__file__),
              'protected_root_artifacts': protected,
              'samples_manifest_sha256': sample_sha, 'encoding_sha256': encoding_sha, 'stages': stages,
              'queries': {'train': 100000, 'job_light': 70, 'public_grouped': 683},
              'scope': 'New consistent local samples and all bitmaps; not official bitmap or paper 200-query reproduction',
              'artifacts': artifacts}
    base.atomic_json(manifest_path, result)
    base.verify_records(protected, ROOT)
    return result


def validate_rebuilt_manifest(data_root=DATA):
    data_root = Path(data_root)
    manifest = json.loads((data_root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'PASS':
        raise ValueError('Materialized bitmap manifest is not PASS')
    base.verify_records(manifest['artifacts'], data_root)
    return manifest


def _states_equal(left, right):
    import numpy as np
    import torch
    if torch.is_tensor(left):
        return torch.is_tensor(right) and torch.equal(left, right)
    if isinstance(left, np.ndarray):
        return isinstance(right, np.ndarray) and np.array_equal(left, right)
    if isinstance(left, dict):
        return isinstance(right, dict) and left.keys() == right.keys() and all(_states_equal(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple)):
        return isinstance(right, type(left)) and len(left) == len(right) and all(_states_equal(a, b) for a, b in zip(left, right))
    return left == right


def verify_next_update_restoration(directory, binding, model, optimizer, step_function, create_pair):
    import numpy as np
    import torch
    committed = base.checkpoint_record(directory, binding)
    if committed is None:
        raise ValueError('No committed checkpoint for continuation gate')
    def draws():
        return torch.rand(5), np.random.random(5), random.random()
    try:
        expected_rng = draws()
        expected_loss = step_function(model, optimizer)
        expected_model = copy.deepcopy(model.state_dict())
        expected_adam = copy.deepcopy(optimizer.state_dict())
        restored_model, restored_optimizer = create_pair()
        base.restore_training_checkpoint(directory, binding, restored_model, restored_optimizer)
        actual_rng = draws()
        actual_loss = step_function(restored_model, restored_optimizer)
        result = {'model_equal': _states_equal(expected_model, restored_model.state_dict()),
                  'adam_equal': _states_equal(expected_adam, restored_optimizer.state_dict()),
                  'rng_equal': _states_equal(expected_rng, actual_rng),
                  'loss_equal': expected_loss == actual_loss,
                  'checkpoint_sha256': committed['artifact']['sha256'],
                  'binding_sha256': base.digest(binding)}
        result['status'] = 'PASS' if all(result[key] for key in ['model_equal', 'adam_equal', 'rng_equal', 'loss_equal']) else 'FAIL'
        return result
    finally:
        # The gate's extra update is never a formal training epoch or checkpoint.
        base.restore_training_checkpoint(directory, binding, model, optimizer)


CONFIG = {'queries': 100000, 'batch': 1024, 'hidden': 256, 'seed': 1, 'threads': 4}


def protected_cpp_artifacts():
    cpp = ROOT / 'output/full/cpp-scale'
    paths = [ROOT / 'code/full_mscn.py', cpp / 'sealed_public_scale_5spn.json', cpp / 'sealed_paper_proxy_6spn.json']
    for name in ['public_scale_verification.json', 'model_00c14f94cbedf038_verification.json']:
        receipt = json.loads((cpp / name).read_text())
        binding = receipt['build']['generation']['binding']
        model = ROOT / binding['model_path']
        if base.sha256(model) != binding['model_sha256']:
            raise ValueError('Protected CPP original model SHA changed')
        paths.extend([cpp / name, model])
    return [base.file_record(path) for path in paths]


def assert_finite_model_adam(model, optimizer):
    import torch
    def finite(value):
        if torch.is_tensor(value):
            return bool(torch.isfinite(value).all())
        if isinstance(value, dict):
            return all(finite(item) for item in value.values())
        if isinstance(value, (tuple, list)):
            return all(finite(item) for item in value)
        if isinstance(value, float):
            return math.isfinite(value)
        return True
    if not finite(model.state_dict()) or not finite(optimizer.state_dict()):
        raise ValueError('Non-finite model or Adam state; refusing epoch commit')


def rebuilt_training_binding(data_root=DATA):
    manifest = validate_rebuilt_manifest(data_root)
    if (manifest.get('queries') != {'train': 100000, 'job_light': 70, 'public_grouped': 683}
            or manifest['binding']['source_seal'] != preparation_source_seal()):
        raise ValueError('Rebuilt source protocol or full query count changed')
    base.verify_records(manifest['binding']['queries'], ROOT)
    base.verify_records(manifest['protected_root_artifacts'], ROOT)
    runtime = base.runtime_versions()
    if runtime != {'python': '3.8.20', 'numpy': '1.24.4', 'torch': '1.13.1+cpu'}:
        raise ValueError('Use the pinned .venv-mscn runtime: ' + repr(runtime))
    paths = ['code/full_mscn_rebuilt.py', 'code/full_mscn.py', 'code/vendor/mscn/train.py',
             'code/vendor/mscn/mscn/model.py', 'code/vendor/mscn/mscn/util.py', 'code/vendor/mscn/mscn/data.py']
    return {'schema_version': 1, 'protocol': PROTOCOL, 'configuration': CONFIG, 'runtime': runtime,
            'rebuilt_manifest_sha256': base.sha256(Path(data_root) / 'manifest.json'),
            'samples_manifest_sha256': manifest['samples_manifest_sha256'],
            'encoding_sha256': manifest['encoding_sha256'],
            'source_artifacts': [base.file_record(ROOT / path) for path in paths],
            'upstream_commit': base.COMMIT, 'optimizer': {'name': 'Adam', 'lr': .001},
            'split': 'first_90000_train_next_10000_validation', 'shuffle': False,
            'device': 'cpu', 'data_root': str(Path(data_root).relative_to(ROOT))}


def prepared_rebuilt(data_root=DATA):
    prepared = base.prepare_datasets(data_root, CONFIG['queries'])
    encoding = json.loads((Path(data_root) / 'encoding.json').read_text())
    for field, key in [('tables', 'table2vec'), ('columns', 'column2vec'),
                       ('operators', 'op2vec'), ('joins', 'join2vec')]:
        if sorted(prepared[key]) != encoding[field]:
            raise ValueError('Frozen training dictionary encoding mismatch: ' + field)
        for index, symbol in enumerate(encoding[field]):
            vector = prepared[key][symbol]
            if vector[index] != 1 or float(vector.sum()) != 1:
                raise ValueError('Frozen one-hot order changed')
    return prepared


def one_batch_step(model, optimizer, batch, prepared, official):
    import torch
    samples, predicates, joins, targets, sample_masks, predicate_masks, join_masks = batch
    optimizer.zero_grad()
    output = model(samples, predicates, joins, sample_masks, predicate_masks, join_masks)
    loss = official.qerror_loss(output, targets.float(), prepared['min_val'], prepared['max_val'])
    if not torch.isfinite(loss):
        raise ValueError('Non-finite training loss; epoch not committed')
    loss.backward()
    optimizer.step()
    return float(loss.item())


def epoch_one_gate(directory, binding, model, optimizer, prepared, loader, official):
    assert_finite_model_adam(model, optimizer)
    record = base.checkpoint_record(directory / 'checkpoints', binding)
    if record['completed_epochs'] != 1:
        raise ValueError('The initial full-data gate requires the committed first epoch')
    def step(net, optim):
        net.train()
        loss = one_batch_step(net, optim, next(iter(loader)), prepared, official)
        assert_finite_model_adam(net, optim)
        return loss
    def factory():
        return base.model_and_optimizer(prepared, CONFIG)
    gate = verify_next_update_restoration(directory / 'checkpoints', binding, model, optimizer, step, factory)
    gate.update(configured_queries=100000, training_queries=len(prepared['train']),
                validation_queries=len(prepared['validation']), model_parameters_finite=True, adam_finite=True,
                checkpoint_epochs=1, next_update='Full first batch of epoch2, same original SetConv/qerror/Adam',
                gate_update_committed_as_training=False)
    base.atomic_json(directory / 'epoch1_gate.json', gate)
    if gate['status'] != 'PASS':
        raise ValueError('Full-data epoch1 continuation gate failed')
    return gate


def verified_epoch_one_gate(directory, binding):
    path = directory / 'epoch1_gate.json'
    if not path.exists():
        return None
    gate = json.loads(path.read_text())
    first = directory / 'checkpoints/epoch_000001.pt'
    if (gate.get('status') != 'PASS' or gate.get('binding_sha256') != base.digest(binding)
            or not first.is_file() or gate.get('checkpoint_sha256') != base.sha256(first)):
        raise ValueError('Epoch1 gate/checkpoint binding changed')
    return gate


def train_rebuilt(target_epochs=100, directory=OUT, data_root=DATA):
    from torch.utils.data import DataLoader
    if not 1 <= target_epochs <= 100:
        raise ValueError('Target epochs must be in [1,100]')
    directory, data_root = Path(directory), Path(data_root)
    binding = rebuilt_training_binding(data_root)
    with base.run_lock(directory):
        record = base.checkpoint_record(directory / 'checkpoints', binding)
        remaining = base.pending_epochs(record, target_epochs)
        gate = verified_epoch_one_gate(directory, binding)
        if not remaining and gate is not None:
            return {'status': 'TARGET_ALREADY_COMMITTED', 'completed_epochs': record['completed_epochs'], 'epoch1_gate': gate}
        if record and record['completed_epochs'] > 1 and gate is None:
            raise ValueError('Missing first-epoch gate after subsequent committed training')
        base.setup_runtime(CONFIG)
        prepared = prepared_rebuilt(data_root)
        model, optimizer = base.model_and_optimizer(prepared, CONFIG)
        loader = DataLoader(prepared['train'], batch_size=CONFIG['batch'], shuffle=False, num_workers=0)
        official, _ = base.official_modules()
        history = base.restore_training_checkpoint(directory / 'checkpoints', binding, model, optimizer)
        if record:
            assert_finite_model_adam(model, optimizer)
        base.atomic_json(directory / 'binding.json', binding)
        base.atomic_json(directory / 'config.json', CONFIG)
        if record and record['completed_epochs'] == 1 and gate is None:
            gate = epoch_one_gate(directory, binding, model, optimizer, prepared, loader, official)
        for epoch in remaining:
            if epoch > 1 and gate is None:
                raise ValueError('Continuation is prohibited before the first-epoch gate')
            model.train()
            loss_total, started = 0., time.perf_counter()
            for batch in loader:
                loss_total += one_batch_step(model, optimizer, batch, prepared, official)
            assert_finite_model_adam(model, optimizer)
            item = {'epoch': epoch, 'training_queries': len(prepared['train']), 'batches': len(loader),
                    'loss_mean_of_batches': loss_total / len(loader),
                    'training_seconds': time.perf_counter() - started, 'finite_model_and_adam': True}
            history.append(item)
            record = base.save_training_checkpoint(directory / 'checkpoints', epoch, binding, model, optimizer, history)
            base.atomic_json(directory / 'history.json', history)
            if epoch == 1:
                gate = epoch_one_gate(directory, binding, model, optimizer, prepared, loader, official)
            state = {'status': 'REBUILT_TRAINING_COMPLETE_EVALUATION_REQUIRED' if epoch == 100 else 'PARTIAL_TRAINING',
                     'completed_epochs': epoch, 'target_epochs': target_epochs, 'checkpoint': record,
                     'binding_sha256': base.digest(binding), 'epoch1_gate_status': gate['status'],
                     'training_seconds': sum(row['training_seconds'] for row in history)}
            base.atomic_json(directory / 'training_state.json', state)
            print(json.dumps(item), flush=True)
        if not remaining:
            state = {'status': 'EPOCH1_GATE_PASS', 'completed_epochs': record['completed_epochs'], 'epoch1_gate': gate}
        return state


def verified_joint_traces(data_root, name, dataset):
    import numpy as np
    manifest = validate_rebuilt_manifest(data_root)
    prefix = Path(data_root) / 'workloads' / name
    with prefix.with_suffix('.joint.jsonl').open(encoding='utf-8') as stream:
        traces = [json.loads(line) for line in stream]
    if len(traces) != len(dataset.rows):
        raise ValueError('Evaluation bitmap/source trace count mismatch')
    derived = {'row_no', 'table_order', 'cardinality_true', 'bitmap_sha256', 'joint_sha256'}
    for index, (row, trace) in enumerate(zip(dataset.rows, traces)):
        tables = row[0].split(',')
        packed = struct.pack('<I', len(tables)) + dataset.bitmap[dataset.offsets[index]:dataset.offsets[index] + 125 * len(tables)].tobytes()
        source = {key: value for key, value in trace.items() if key not in derived}
        if (trace['row_no'] != index or trace['cardinality_true'] != int(row[3])
                or trace['table_order'] != [table.split()[-1] for table in tables]
                or trace['bitmap_sha256'] != hashlib.sha256(packed).hexdigest()
                or trace['joint_sha256'] != query_joint_sha(row, packed, manifest['samples_manifest_sha256'], source)):
            raise ValueError('Evaluation joint query/bitmap/sample seal mismatch')
    return traces


def evaluate_rebuilt(directory=OUT, data_root=DATA):
    import torch
    directory, data_root = Path(directory), Path(data_root)
    binding = rebuilt_training_binding(data_root)
    with base.run_lock(directory):
        record = base.checkpoint_record(directory / 'checkpoints', binding)
        if record is None or record['completed_epochs'] != 100 or verified_epoch_one_gate(directory, binding) is None:
            raise ValueError('Final evaluation requires 100 committed epochs and the full first-epoch gate')
        receipt_path = directory / 'evaluation.json'
        if receipt_path.exists():
            previous = json.loads(receipt_path.read_text())
            if (previous.get('status') == 'REBUILT_PUBLIC_WORKLOAD_EVALUATION_COMPLETE'
                    and previous.get('binding_sha256') == base.digest(binding)
                    and previous.get('checkpoint', {}).get('artifact', {}).get('sha256') == record['artifact']['sha256']):
                base.verify_records(previous['artifacts'], directory)
                return dict(previous, reused_verified_evaluation=True)
        base.setup_runtime(CONFIG)
        prepared = prepared_rebuilt(data_root)
        model, optimizer = base.model_and_optimizer(prepared, CONFIG)
        history = base.restore_training_checkpoint(directory / 'checkpoints', binding, model, optimizer)
        assert_finite_model_adam(model, optimizer)
        groups, all_rows = {}, []
        for name in ['job-light', 'public-grouped']:
            dataset = base.workload_dataset(data_root, name, prepared)
            traces = verified_joint_traces(data_root, name, dataset)
            estimates, ms, _ = base.predict_dataset(model, dataset, CONFIG['batch'], prepared)
            for index, (row, trace) in enumerate(zip(dataset.rows, traces)):
                predicted, actual = int(estimates[index]), int(row[3])
                if predicted < 1 or actual < 1:
                    raise ValueError('Nonpositive final estimate/truth')
                item = {'query_no': trace['query_no'], 'group': trace['group'],
                        'query': trace.get('source_sql', base.query_sql(row)), 'cardinality_true': actual,
                        'cardinality_predict': predicted, 'q_error': max(predicted / actual, actual / predicted),
                        'forward_amortized_ms': ms[index], 'bitmap_joint_sha256': trace['joint_sha256'],
                        'source_sql_sha256': trace['source_sql_sha256'],
                        'samples_manifest_sha256': binding['samples_manifest_sha256']}
                groups.setdefault(trace['group'], []).append(item)
                all_rows.append(item)
        metrics, artifacts = {}, []
        for group, rows in groups.items():
            destination = directory / (group + '.csv')
            temporary = destination.with_suffix('.csv.tmp')
            with temporary.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(destination))
            metrics[group] = {'queries': len(rows), 'qerror': base.qerror_metrics(
                [row['cardinality_predict'] for row in rows], [row['cardinality_true'] for row in rows])}
            artifacts.append(base.file_record(destination, directory))
        figure8 = [{'tables': tables, 'predicates': predicates, **metrics['{}_{}_SPN'.format(tables, predicates)]}
                   for tables in (4, 5, 6) for predicates in range(1, 6)]
        model_path = directory / 'model_state.pt'
        temporary = model_path.with_suffix('.pt.tmp')
        with temporary.open('wb') as stream:
            torch.save(model.state_dict(), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(model_path))
        artifacts.append(base.file_record(model_path, directory))
        result = {'status': 'REBUILT_PUBLIC_WORKLOAD_EVALUATION_COMPLETE', 'full_paper_reproduction_complete': False,
                  'scope': 'New consistent local 1000-row samples; 100K input split90K/10K; 100epochs; JOB70+683 public queries, not author original200',
                  'queries': len(all_rows), 'job_light_queries': len(groups['job_light']), 'public_grouped_queries': len(all_rows) - len(groups['job_light']),
                  'completed_epochs': 100, 'checkpoint': record, 'binding_sha256': base.digest(binding),
                  'samples_manifest_sha256': binding['samples_manifest_sha256'],
                  'groups': metrics, 'figure8_public_groups': figure8,
                  'training_seconds': sum(row['training_seconds'] for row in history),
                  'latency_protocol': 'Same frozen predict_dataset; one warm-up, batch-forward/no_grad CPU only, encoding excluded',
                  'model_parameter_bytes': sum(value.numel() * value.element_size() for value in model.state_dict().values()),
                  'model_state_disk_bytes': model_path.stat().st_size, 'checkpoint_disk_bytes': record['artifact']['bytes'],
                  'official_model_or_data_modified': False, 'artifacts': artifacts}
        if result['queries'] != 753 or len(figure8) != 15:
            raise ValueError('Final public workload is incomplete')
        base.atomic_json(directory / 'evaluation.json', result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'train', 'evaluate', 'all'])
    parser.add_argument('--epochs', type=int, default=100, help='Cumulative target; never repeats committed epochs')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare_rebuilt()
    elif args.action == 'train':
        result = train_rebuilt(args.epochs)
    elif args.action == 'evaluate':
        result = evaluate_rebuilt()
    else:
        import subprocess
        if not (DATA / 'manifest.json').exists():
            subprocess.run([str(ROOT / '.venv/Scripts/python.exe'), '-B', str(Path(__file__).resolve()), 'prepare'], check=True)
        result = train_rebuilt(100)
        result = evaluate_rebuilt()
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
