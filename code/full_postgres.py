"""Project-local PostgreSQL 11.5 and independent JOB-light truth/EXPLAIN audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

import pandas as pd
import psycopg2
from psycopg2 import sql

from full_common import ROOT, FULL, atomic_json, file_sha256, load_json
from schemas.imdb.schema import gen_job_light_imdb_schema
from evaluation.utils import parse_query

PORT = 55432
DB = 'deepdb_job'
ARCHIVE_URL = 'https://get.enterprisedb.com/postgresql/postgresql-11.5-1-windows-x64-binaries.zip'
ARCHIVE_MD5 = '7bdf6c42316a41d149797c478888fa6e'
RUNTIME = ROOT / '.runtime/postgresql-11.5'
CLUSTER = ROOT / 'data/postgresql/cluster'
NUMERIC = {
    'title': {'id', 'kind_id', 'production_year', 'imdb_id', 'episode_of_id', 'season_nr', 'episode_nr'},
    'movie_info_idx': {'id', 'movie_id', 'info_type_id'},
    'movie_info': {'id', 'movie_id', 'info_type_id'},
    'cast_info': {'id', 'person_id', 'movie_id', 'person_role_id', 'nr_order', 'role_id'},
    'movie_keyword': {'id', 'movie_id', 'keyword_id'},
    'movie_companies': {'id', 'movie_id', 'company_id', 'company_type_id'},
}


def table_ddl(name):
    table = gen_job_light_imdb_schema('{}.csv').table_dictionary[name]
    columns = []
    for attr in table.attributes:
        kind = 'integer' if attr in NUMERIC[name] else 'text'
        if attr == 'id':
            kind += ' PRIMARY KEY'
        columns.append('"%s" %s' % (attr, kind))
    return 'CREATE TABLE "%s" (%s)' % (name, ', '.join(columns))


def copy_sql(name):
    if name not in NUMERIC:
        raise ValueError('Unknown benchmark table')
    return "COPY \"%s\" FROM STDIN WITH (FORMAT CSV, DELIMITER ',', QUOTE '\"', ESCAPE E'\\\\', NULL '')" % name


def star_count_query(query):
    """Exact SQL reassociation: count child rows per movie before multiplying.

    This avoids enumerating billions of joined rows. It is an algebraic COUNT
    rewrite, not a cardinality estimate; duplicate multiplicities are retained.
    """
    schema = gen_job_light_imdb_schema('{}.csv')
    parsed = parse_query(query if query.rstrip().endswith(';') else query + ';', schema)
    if 'title' not in parsed.table_set:
        raise ValueError('Expected a title-centered JOB query')
    children = sorted(parsed.table_set - {'title'})
    factors, joins = [], []
    for index, name in enumerate(children):
        if name not in NUMERIC:
            raise ValueError('Unknown child table')
        conditions = parsed.table_where_condition_dict.get(name, [])
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        alias = 'counts%d' % index
        joins.append('JOIN (SELECT movie_id, COUNT(*) AS fanout FROM "%s"%s GROUP BY movie_id) %s '
                     'ON title.id=%s.movie_id' % (name, where, alias, alias))
        factors.append('CAST(%s.fanout AS numeric)' % alias)
    conditions = parsed.table_where_condition_dict.get('title', [])
    where = ' WHERE ' + ' AND '.join('title.' + condition for condition in conditions) if conditions else ''
    expression = ' * '.join(factors) if factors else '1'
    return 'SELECT COALESCE(SUM(%s),0) FROM title %s%s' % (expression, ' '.join(joins), where)


def connect(database=DB):
    return psycopg2.connect(host='127.0.0.1', port=PORT, user='postgres', dbname=database,
                            connect_timeout=5, application_name='deepdb_reproduction')


def install():
    if (RUNTIME / 'pgsql/bin/pg_ctl.exe').is_file():
        return
    archive = ROOT / 'data/downloads/postgresql-11.5-1-windows-x64-binaries.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        subprocess.run(['curl.exe', '-f', '-L', '--retry', '3', '-C', '-', '-o', str(archive), ARCHIVE_URL], check=True)
    md5 = hashlib.md5()
    with archive.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            md5.update(block)
    if md5.hexdigest() != ARCHIVE_MD5:
        raise ValueError('PostgreSQL archive differs from EDB published object metadata')
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('PostgreSQL ZIP CRC failed')
        members = [m for m in bundle.infolist() if m.filename.startswith(('pgsql/bin/', 'pgsql/lib/', 'pgsql/share/'))]
        for member in members:
            target = (RUNTIME / member.filename).resolve()
            if RUNTIME.resolve() not in target.parents:
                raise ValueError('Unsafe ZIP member')
            bundle.extract(member, str(RUNTIME))
    atomic_json(ROOT / 'data/postgresql/runtime_manifest.json', {
        'url': ARCHIVE_URL, 'version': '11.5', 'bytes': archive.stat().st_size,
        'sha256': file_sha256(archive), 'md5_from_edb_object_metadata': ARCHIVE_MD5})


def start():
    install()
    bin_dir = RUNTIME / 'pgsql/bin'
    CLUSTER.parent.mkdir(parents=True, exist_ok=True)
    (FULL / 'logs').mkdir(parents=True, exist_ok=True)
    if not (CLUSTER / 'PG_VERSION').exists():
        subprocess.run([str(bin_dir / 'initdb.exe'), '-D', str(CLUSTER), '-U', 'postgres',
                        '-A', 'trust', '--encoding=UTF8', '--locale=C'], check=True)
    status = subprocess.run([str(bin_dir / 'pg_ctl.exe'), '-D', str(CLUSTER), 'status'], capture_output=True)
    if status.returncode:
        options = ('-h 127.0.0.1 -p %d -c shared_buffers=256MB -c work_mem=64MB '
                   '-c maintenance_work_mem=256MB -c max_parallel_workers_per_gather=0') % PORT
        subprocess.run([str(bin_dir / 'pg_ctl.exe'), '-D', str(CLUSTER), '-l', str(FULL / 'logs/postgresql.log'),
                        '-o', options, '-w', 'start'], check=True)
    connection = connect('postgres')
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute('SHOW server_version')
        version = cursor.fetchone()[0]
        if not version.startswith('11.5'):
            raise ValueError('Unexpected PostgreSQL server at dedicated benchmark port: ' + version)
        cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', (DB,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DB)))
    connection.close()
    print('Project PostgreSQL ready:', version, 'port', PORT, flush=True)


def load_tables():
    start()
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    manifest = load_json(ROOT / 'data/manifest.json')
    expected_counts = load_json(ROOT / 'output/results/data_audit.json')['row_counts']
    receipts = ROOT / 'data/postgresql/imports.json'
    record = load_json(receipts, {})
    connection = connect()
    connection.autocommit = True
    with connection.cursor() as cursor:
        for table in schema.tables:
            name = table.table_name
            source = ROOT / 'data/imdb' / (name + '.csv')
            expected_hash = next(f['sha256'] for f in manifest['files'] if f['path'] == 'imdb/' + name + '.csv')
            cursor.execute('SELECT to_regclass(%s)', (name,))
            exists = cursor.fetchone()[0] is not None
            if exists and record.get(name, {}).get('sha256') == expected_hash:
                cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name)))
                count = cursor.fetchone()[0]
                if count == expected_counts[name]:
                    print('Reused verified table', name, count, flush=True)
                    continue
            if file_sha256(source) != expected_hash:
                raise ValueError('Raw data changed: ' + name)
            cursor.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(sql.Identifier(name)))
            cursor.execute(table_ddl(name))
            started = time.perf_counter()
            with source.open('r', encoding='utf-8', newline='') as stream:
                cursor.copy_expert(copy_sql(name), stream)
            cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name)))
            count = cursor.fetchone()[0]
            assert count == expected_counts[name], (name, count, expected_counts[name])
            if name != 'title':
                cursor.execute(sql.SQL('CREATE INDEX ON {} (movie_id)').format(sql.Identifier(name)))
            cursor.execute(sql.SQL('ANALYZE {}').format(sql.Identifier(name)))
            record[name] = {'sha256': expected_hash, 'rows': count, 'seconds': time.perf_counter() - started}
            atomic_json(receipts, record)
            print('Imported and analyzed', name, count, flush=True)
        # Validate the declared foreign-key domain without mutating the original data.
        for name in NUMERIC:
            if name == 'title':
                continue
            cursor.execute('SELECT count(*) FROM "%s" c LEFT JOIN title t ON c.movie_id=t.id WHERE t.id IS NULL' % name)
            print('Unmatched movie references', name, cursor.fetchone()[0], flush=True)
    connection.close()


def truth_and_baseline():
    start()
    benchmark = ROOT / 'code/benchmarks/job-light/sql'
    queries = [line.strip() for line in (benchmark / 'job_light_queries.sql').read_text().splitlines() if line.strip()]
    official = pd.read_csv(benchmark / 'job_light_true_cardinalities.csv')
    assert len(queries) == len(official) == 70
    target = FULL / 'results/postgres_job_light.csv'
    previous = pd.read_csv(target).to_dict('records') if target.exists() else []
    rows = []
    connection = connect()
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute('SET statement_timeout = 0')
        cursor.execute('SHOW server_version')
        version = cursor.fetchone()[0]
        for index, query in enumerate(queries):
            expected = int(official.loc[index, 'cardinality_true'])
            assert query == official.loc[index, 'query'].strip()
            if index < len(previous) and previous[index]['query'] == query and previous[index]['cardinality_true'] == expected:
                rows.append(previous[index])
                continue
            started = time.perf_counter()
            rewritten = star_count_query(query)
            cursor.execute(rewritten)
            actual = int(cursor.fetchone()[0])
            elapsed = time.perf_counter() - started
            if actual != expected:
                raise ValueError('Snapshot truth mismatch: query %d actual %d official %d' % (index, actual, expected))
            # EXPLAIN the rows consumed by COUNT, not the one-row aggregate result.
            cursor.execute('EXPLAIN (FORMAT JSON) ' + query)
            plan = cursor.fetchone()[0][0]['Plan']
            if plan['Node Type'] == 'Aggregate':
                estimated = float(plan['Plans'][0]['Plan Rows'])
            else:
                raise ValueError('Unexpected cardinality plan root')
            rows.append(dict(query_no=index, query=query, cardinality_true=actual,
                             cardinality_predict=estimated, truth_seconds=elapsed,
                             q_error=max(max(estimated, 1) / max(actual, 1), max(actual, 1) / max(estimated, 1)),
                             server_version=version, truth_method='exact_SQL_star_preaggregation'))
            temporary = target.with_suffix('.csv.tmp')
            target.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_csv(temporary, index=False)
            os.replace(str(temporary), str(target))
            print('Truth verified', index + 1, '/70:', actual, 'PG estimate:', estimated, flush=True)
    connection.close()
    q = pd.Series([r['q_error'] for r in rows])
    atomic_json(FULL / 'results/postgres_job_light_verification.json', {
        'status': 'PASS', 'queries': 70, 'all_official_truths_independently_matched': True,
        'server_version': version, 'seed_note': 'PostgreSQL ANALYZE sampling is not exactly seeded',
        'median': float(q.median()), 'p90': float(q.quantile(.9)), 'p95': float(q.quantile(.95)),
        'max': float(q.max()), 'mean': float(q.mean()), 'result_sha256': file_sha256(target)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['install', 'start', 'load', 'audit', 'stop'])
    stage = parser.parse_args().stage
    if stage == 'install': install()
    elif stage == 'start': start()
    elif stage == 'load': load_tables()
    elif stage == 'audit': truth_and_baseline()
    else:
        subprocess.run([str(RUNTIME / 'pgsql/bin/pg_ctl.exe'), '-D', str(CLUSTER), '-w', 'stop'], check=True)


if __name__ == '__main__':
    main()
