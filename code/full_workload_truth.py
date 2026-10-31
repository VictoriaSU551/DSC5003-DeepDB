"""Independently verify all public grouped COUNT truths without join expansion.

Each exact count is committed separately by logical query and input seals, so
aliases/order and previously verified JOB queries do not cause repeated work.
The dedicated PostgreSQL connection is read-only and uses the complete tables.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import time

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import workload_files
from full_inventory import sql_tokens
from full_postgres import connect, star_count_query
from evaluation.utils import parse_query
from schemas.imdb.schema import gen_job_light_imdb_schema


def logical_query(query):
    if not re.match(r'^\s*select\s+count\s*\(\s*\*\s*\)\s+from\b', query, flags=re.I):
        raise ValueError('only COUNT(*) star workloads are supported')
    schema = gen_job_light_imdb_schema('{}.csv')
    parsed = parse_query(query if query.rstrip().endswith(';') else query + ';', schema)
    if 'title' not in parsed.table_set:
        raise ValueError('not a title-centered query')
    return dict(tables=sorted(parsed.table_set), relationships=sorted(parsed.relationship_set),
                predicates={table: sorted(tuple(sql_tokens(condition)) for condition in conditions)
                            for table, conditions in sorted(parsed.table_where_condition_dict.items())})


def store_count(path, binding, count, source, seconds=0.):
    if type(count) is not int or count < 0:
        raise ValueError('count must be an exact nonnegative Python integer')
    result = dict(status='EXACT_COUNT_COMPUTED', binding=binding_hash(binding),
                  binding_details=binding, count=count, source=source, seconds=seconds)
    result['receipt_sha256'] = binding_hash(result)
    atomic_json(path, result)
    return result


def load_count(path, binding):
    result = load_json(path)
    if result is None:
        return None
    seal = result.pop('receipt_sha256', None)
    if seal != binding_hash(result):
        raise ValueError('count receipt seal differs')
    if result['binding'] != binding_hash(binding):
        raise ValueError('count input binding differs')
    if type(result['count']) is not int or result['count'] < 0:
        raise ValueError('count is not an exact integer')
    return result


def previous_job_counts():
    verified = load_json(FULL / 'results/postgres_job_light_verification.json', {})
    path = FULL / 'results/postgres_job_light.csv'
    if (verified.get('status') != 'PASS' or not verified.get('all_official_truths_independently_matched')
            or verified.get('queries') != 70 or file_sha256(path) != verified.get('result_sha256')):
        raise ValueError('earlier 70-query exact truth receipt is not sealed')
    with path.open(newline='', encoding='utf-8') as stream:
        return {binding_hash(logical_query(row['query'])): int(row['cardinality_true'])
                for row in csv.DictReader(stream)}


def run(timeout_seconds=180):
    imports_path = ROOT / 'data/postgresql/imports.json'
    imports = load_json(imports_path)
    if imports is None:
        raise ValueError('full PostgreSQL table imports have not been completed')
    seal = dict(imports_sha256=file_sha256(imports_path), raw_manifest=file_sha256(ROOT / 'data/manifest.json'),
                helpers={name: file_sha256(ROOT / 'code' / name) for name in
                         ['full_workload_truth.py', 'full_postgres.py', 'full_common.py', 'full_inventory.py',
                          'evaluation/utils.py', 'schemas/imdb/schema.py']})
    prior = previous_job_counts()
    connection = connect()
    connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
    result_rows, computed, reused = [], 0, 0
    try:
        with connection.cursor() as cursor:
            cursor.execute('SHOW server_version')
            version = cursor.fetchone()[0]
            if not version.startswith('11.5'):
                raise ValueError('wrong dedicated PostgreSQL version')
            cursor.execute("SET application_name='deepdb_grouped_truth'")
            cursor.execute('SET statement_timeout=%s', (timeout_seconds * 1000,))
            actual_rows = {}
            for table, source in imports.items():
                if not re.fullmatch(r'[a-z_]+', table):
                    raise ValueError('unexpected table name in import seal')
                cursor.execute('SELECT COUNT(*) FROM "' + table + '"')
                actual_rows[table] = cursor.fetchone()[0]
                if actual_rows[table] != source['rows']:
                    raise ValueError('full table row count changed: ' + table)
            atomic_json(FULL / 'truth_cache/database_snapshot.json',
                        dict(server_version=version, rows=actual_rows, input_seal=seal, transaction='read-only repeatable-read'))
            for group, query_path, truth_path in workload_files()[1:]:
                queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
                with truth_path.open(newline='', encoding='utf-8') as stream:
                    expected = list(csv.DictReader(stream))
                if len(queries) != len(expected):
                    raise ValueError('query/truth row count differs')
                for index, (query, published) in enumerate(zip(queries, expected)):
                    if sql_tokens(query) != sql_tokens(published['query']):
                        raise ValueError('query/truth SQL does not align')
                    logical = logical_query(query)
                    binding = dict(snapshot=seal, logical_query=logical)
                    cache = FULL / 'truth_cache/counts' / (binding_hash(binding) + '.json')
                    receipt = load_count(cache, binding)
                    if receipt is not None:
                        reused += 1
                    elif binding_hash(logical) in prior:
                        receipt = store_count(cache, binding, prior[binding_hash(logical)],
                                              'previously verified JOB70 independent SQL')
                        reused += 1
                    else:
                        exact_sql = star_count_query(query)
                        started = time.perf_counter()
                        cursor.execute(exact_sql)
                        actual = int(cursor.fetchone()[0])
                        elapsed = time.perf_counter() - started
                        receipt = store_count(cache, binding, actual, exact_sql, elapsed)
                        computed += 1
                    actual, truth = receipt['count'], int(published['cardinality_true'])
                    result_rows.append(dict(group=group, query_no=index, query=query,
                                            cardinality_published=truth, cardinality_independent=actual,
                                            match=actual == truth, exact_count_seconds=receipt['seconds'],
                                            cache_receipt=cache.relative_to(ROOT).as_posix()))
                    print('EXACT_TRUTH', group, index, actual, 'MATCH' if actual == truth else 'MISMATCH', flush=True)
                atomic_json(FULL / 'truth_cache/progress.json', dict(group=group, completed_queries=len(result_rows),
                            computed_this_invocation=computed, reused_this_invocation=reused,
                            mismatches=sum(not row['match'] for row in result_rows)))
    finally:
        connection.close()
    destination = FULL / 'results/grouped_independent_truth.csv'
    temp = destination.with_suffix('.csv.tmp')
    with temp.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result_rows[0]))
        writer.writeheader(); writer.writerows(result_rows)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(str(temp), str(destination))
    mismatches = [row for row in result_rows if not row['match']]
    result = dict(status='PASS' if len(result_rows) == 683 and not mismatches else 'MISMATCH', queries=len(result_rows),
                  all_published_truths_independently_matched=not mismatches, mismatches=mismatches,
                  computed_this_invocation=computed, reused_this_invocation=reused, input_seal=seal,
                  result_sha256=file_sha256(destination),
                  method='exact star COUNT reassociation, preserving duplicate FK multiplicities and SQL filters')
    atomic_json(FULL / 'results/grouped_independent_truth_verification.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout-seconds', type=int, default=180)
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        parser.error('timeout must be positive')
    result = run(args.timeout_seconds)
    print(json.dumps({k: v for k, v in result.items() if k in ['status', 'queries', 'computed_this_invocation', 'reused_this_invocation']}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
