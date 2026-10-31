"""Exact star counts from a sealed, read-only PostgreSQL column snapshot.

The SQL driver repeatedly scans/group-bys the same large child tables. This
separate engine exports only the nine predicate columns and movie keys, then
computes the same sum of products with exact integer arithmetic. It must match
every previously computed SQL count before it verifies any remaining query.
Prepared model HDFs and published truths are never used as input rows.
"""
import argparse
from collections import OrderedDict
import csv
import json
import math
import operator
import os
from pathlib import Path
import re
import time

import numpy as np

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import workload_files
from full_postgres import connect
from full_workload_truth import logical_query, previous_job_counts

NULL = np.iinfo(np.int64).min
COLUMNS = {'title': ['id', 'kind_id', 'production_year'],
           'movie_companies': ['movie_id', 'company_id', 'company_type_id'],
           'movie_info': ['movie_id', 'info_type_id'],
           'movie_info_idx': ['movie_id', 'info_type_id'],
           'movie_keyword': ['movie_id', 'keyword_id'],
           'cast_info': ['movie_id', 'person_id', 'role_id']}
OPERATORS = {'=': operator.eq, '<': operator.lt, '>': operator.gt,
             '<=': operator.le, '>=': operator.ge}


def filter_rows(columns, predicates):
    size = len(next(iter(columns.values())))
    mask = np.ones(size, dtype=bool)
    for tokens in predicates:
        if (len(tokens) != 3 or tokens[0] not in columns or tokens[1] not in OPERATORS
                or not re.fullmatch(r'-?\d+', tokens[2])):
            raise ValueError('unsupported numeric predicate: ' + repr(tokens))
        values = columns[tokens[0]]
        mask &= (values != NULL) & OPERATORS[tokens[1]](values, int(tokens[2]))
    return mask


def exact_sum_products(factors):
    if not factors: raise ValueError('at least one factor is required')
    size = len(factors[0])
    if any(len(f) != size for f in factors): raise ValueError('factor lengths differ')
    total = 0
    for offset in range(0, size, 100000):
        parts = [np.asarray(f[offset:offset+100000]) for f in factors]
        upper = math.prod(int(p.max()) for p in parts) * len(parts[0])
        # Use exact object integers when even the conservative sum bound can
        # overflow. This also protects genuinely huge join multiplicities.
        dtype = np.uint64 if upper <= np.iinfo(np.uint64).max else object
        values = np.ones(len(parts[0]), dtype=dtype)
        for part in parts: values *= part.astype(dtype, copy=False)
        total += int(values.sum())
    return total


def count_star(tables, logical, fanout_cache=None):
    selected = filter_rows(tables['title'], logical['predicates'].get('title', []))
    ids = np.asarray(tables['title']['id'][selected])
    if not len(ids): return 0
    max_id = int(tables['title']['id'].max())
    if max_id > 100000000 or min(ids) < 0: raise ValueError('unexpected parent key domain')
    factors = []
    for table in sorted(set(logical['tables']) - {'title'}):
        predicates = logical['predicates'].get(table, [])
        key = (table, tuple(tuple(p) for p in predicates))
        counts = fanout_cache.get(key) if fanout_cache is not None else None
        if counts is None:
            columns = tables[table]
            mask = filter_rows(columns, predicates)
            keys = columns['movie_id']
            mask &= (keys >= 0) & (keys <= max_id)
            counts = np.bincount(np.asarray(keys[mask]), minlength=max_id + 1).astype(np.uint64)
            if fanout_cache is not None:
                fanout_cache[key] = counts
                while len(fanout_cache) > 8: fanout_cache.popitem(last=False)
        elif fanout_cache is not None:
            fanout_cache.move_to_end(key)
        factors.append(counts[ids])
    return exact_sum_products(factors) if factors else len(ids)


def inputs():
    return dict(imports_sha256=file_sha256(ROOT / 'data/postgresql/imports.json'),
                raw_manifest=file_sha256(ROOT / 'data/manifest.json'),
                helpers={name: file_sha256(ROOT / 'code' / name) for name in
                         ['full_truth_arrays.py', 'full_workload_truth.py', 'full_postgres.py',
                          'full_common.py', 'full_inventory.py', 'evaluation/utils.py', 'schemas/imdb/schema.py']})


def dump_columns():
    binding = inputs(); key = binding_hash(binding)
    directory = ROOT / 'data/postgresql/column_snapshot' / key
    directory.mkdir(parents=True, exist_ok=True)
    reports = {}
    imports = load_json(ROOT / 'data/postgresql/imports.json')
    connection = connect(); connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET application_name='deepdb_exact_column_snapshot'")
            cursor.execute('SHOW server_version')
            if not cursor.fetchone()[0].startswith('11.5'): raise ValueError('wrong PostgreSQL version')
        for table, columns in COLUMNS.items():
            receipt_path, path = directory / (table + '.json'), directory / (table + '.npy')
            report = load_json(receipt_path)
            if report is not None:
                if report['binding'] != key or file_sha256(path) != report['sha256']:
                    raise ValueError('column snapshot seal changed: ' + table)
                reports[table] = report
                continue
            temporary = path.with_name(path.name + '.tmp')
            rows = imports[table]['rows']
            values = np.lib.format.open_memmap(str(temporary), mode='w+', dtype=np.int64, shape=(rows, len(columns)))
            started, offset = time.perf_counter(), 0
            with connection.cursor(name='deepdb_columns_' + table) as cursor:
                cursor.itersize = 50000
                cursor.execute('SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM "' + table + '"')
                while True:
                    batch = cursor.fetchmany(50000)
                    if not batch: break
                    block = np.asarray([[NULL if v is None else v for v in row] for row in batch], dtype=np.int64)
                    values[offset:offset+len(block)] = block; offset += len(block)
            if offset != rows: raise ValueError('complete PostgreSQL table row count differs: ' + table)
            values.flush(); del values
            os.replace(str(temporary), str(path))
            report = dict(status='PASS_READ_ONLY_SQL_SNAPSHOT', binding=key, columns=columns,
                          rows=rows, path=path.relative_to(ROOT).as_posix(), sha256=file_sha256(path),
                          seconds=time.perf_counter()-started)
            atomic_json(receipt_path, report); reports[table] = report
            print('SEALED_SQL_COLUMNS', table, rows, report['seconds'], flush=True)
    finally:
        connection.rollback(); connection.close()
    snapshot = dict(binding=key, binding_details=binding, tables=reports)
    atomic_json(directory / 'snapshot.json', snapshot)
    return snapshot


def load_tables(snapshot):
    tables = {}
    for table, record in snapshot['tables'].items():
        matrix = np.load(str(ROOT / record['path']), mmap_mode='r')
        tables[table] = {column: matrix[:, i] for i, column in enumerate(record['columns'])}
    return tables


def previous_exact_counts():
    result = previous_job_counts()
    for path in (FULL / 'truth_cache/counts').glob('*.json'):
        row = load_json(path)
        seal = row.pop('receipt_sha256', None)
        if seal != binding_hash(row): raise ValueError('prior exact count receipt changed')
        logical = row['binding_details']['logical_query']
        result[binding_hash(logical)] = row['count']
    return result


def run(gate_only=False):
    snapshot = dump_columns(); tables = load_tables(snapshot)
    cache, prior, checked = OrderedDict(), previous_exact_counts(), 0
    # Gate all trusted SQL results, including the original70. The original SQL
    # engine may still be running; this finite prefix is fixed at gate start.
    logicals = {}
    for group, query_path, truth_path in workload_files():
        for row in csv.DictReader(truth_path.open(newline='', encoding='utf-8')):
            query = logical_query(row['query']); logicals[binding_hash(query)] = query
    for key, actual in prior.items():
        if key not in logicals: raise ValueError('prior count has no current workload binding')
        predicted = count_star(tables, logicals[key], cache)
        if predicted != actual: raise ValueError('independent SQL/array exact count mismatch')
        checked += 1
    directory = FULL / 'truth_arrays' / snapshot['binding']
    directory.mkdir(parents=True, exist_ok=True)
    gate = dict(status='PASS', compared_prior_sql_counts=checked, snapshot=snapshot)
    atomic_json(directory / 'sql_gate.json', gate)
    print('ALL_PRIOR_SQL_COUNTS_MATCH', checked, flush=True)
    if gate_only: return gate
    rows = []
    for group, query_path, truth_path in workload_files()[1:]:
        with truth_path.open(newline='', encoding='utf-8') as stream:
            expected = list(csv.DictReader(stream))
        for index, row in enumerate(expected):
            logical = logical_query(row['query']); key = binding_hash(logical)
            path = directory / 'counts' / (key + '.json')
            record = load_json(path)
            if record:
                contents = dict(record); seal = contents.pop('receipt_sha256', None)
                if seal != binding_hash(contents) or record['snapshot_binding'] != snapshot['binding']:
                    raise ValueError('exact array count checkpoint changed')
                count = record['count']
            else:
                started = time.perf_counter()
                count = prior[key] if key in prior else count_star(tables, logical, cache)
                record = dict(snapshot_binding=snapshot['binding'], logical_query=logical,
                    count=count, method='reused_sealed_prior_SQL' if key in prior else 'exact_SQL_column_sum_of_products',
                    seconds=time.perf_counter()-started)
                record['receipt_sha256'] = binding_hash(record); atomic_json(path, record)
            truth = int(row['cardinality_true'])
            rows.append(dict(group=group, query_no=index, query=row['query'], published_truth=truth,
                             independently_computed=count, matches=count == truth, method=record['method']))
            print('EXACT_ARRAY_TRUTH', group, index, count, 'MATCH' if count == truth else 'MISMATCH', flush=True)
    destination = directory / 'all683.csv'
    with destination.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = dict(status='PASS' if all(r['matches'] for r in rows) else 'MISMATCH', queries=len(rows),
        all_official_truths_independently_matched=all(r['matches'] for r in rows),
        independently_SQL_checked_gate=checked, snapshot=snapshot,
        result_path=destination.relative_to(ROOT).as_posix(), result_sha256=file_sha256(destination),
        input_scope='Full PostgreSQL tables, raw numeric columns; model-prepared inputs are not used',
        integer_arithmetic='UInt64 only under proven product and sum bound; Python arbitrary precision otherwise')
    atomic_json(directory / 'verification.json', result)
    atomic_json(FULL / 'results/grouped_independent_truth_arrays.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate-only', action='store_true')
    args = parser.parse_args()
    run(args.gate_only)
