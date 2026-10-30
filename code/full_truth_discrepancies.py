"""Resolve public COUNT discrepancies with a second exact PostgreSQL execution.

Never edits published truth CSVs or prediction artifacts. Writes an additional
local truth table only after all discrepant rows agree between the independent
numeric-column engine and the exact SQL reassociation.
"""
import csv
import json
import re
import time

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import workload_files
from full_inventory import sql_tokens
from full_postgres import connect, star_count_query
from full_truth_arrays_run import database_identity


def classify(published, array_count, sql_count):
    if sql_count != array_count: return 'ARRAY_ENGINE_FAILURE'
    return 'PUBLISHED_MATCH' if published == sql_count else 'CONFIRMED_PUBLIC_INPUT_DIFFERENCE'


def run():
    summary_path = FULL / 'results/grouped_independent_truth_arrays.json'
    summary = load_json(summary_path)
    if summary is None or summary['queries'] != 683: raise ValueError('full independent array count stage missing')
    source = ROOT / summary['result_path']
    if file_sha256(source) != summary['result_sha256']: raise ValueError('array result CSV changed')
    with source.open(newline='', encoding='utf-8') as stream: rows = list(csv.DictReader(stream))
    by_group = {}
    for row in rows: by_group.setdefault(row['group'], []).append(row)
    workload_seals = {}
    for group, query, truth in workload_files()[1:]:
        sqls = [line.strip() for line in query.read_text().splitlines() if line.strip()]
        if len(sqls) != len(by_group[group]) or any(sql_tokens(q) != sql_tokens(r['query']) for q, r in zip(sqls, by_group[group])):
            raise ValueError('local array results do not align with public SQL files')
        workload_seals.update({p.relative_to(ROOT).as_posix(): file_sha256(p) for p in (query, truth)})
    directory = FULL / 'truth_discrepancies'; directory.mkdir(parents=True, exist_ok=True)
    binding = dict(array_verification_sha256=file_sha256(summary_path), source_sha256=file_sha256(source),
                   snapshot=summary['snapshot']['binding'], workload_seals=workload_seals,
                   driver_sha256=file_sha256(__file__), sql_helper_sha256=file_sha256(ROOT / 'code/full_postgres.py'))
    binding_id, records = binding_hash(binding), []
    connection = connect(); connection.set_session(readonly=False, isolation_level='READ COMMITTED')
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET application_name='deepdb_discrepancy_SQL_audit'")
            cursor.execute('LOCK TABLE cast_info,movie_companies,movie_info,movie_info_idx,movie_keyword,title IN SHARE MODE')
            before = database_identity(connection)
            for row in rows:
                published, array_count = int(row['published_truth']), int(row['independently_computed'])
                if published == array_count: continue
                path = directory / ('%s_%04d.json' % (row['group'], int(row['query_no'])))
                record = load_json(path)
                if record is not None:
                    contents = dict(record); seal = contents.pop('receipt_sha256', None)
                    if seal != binding_hash(contents) or record['binding'] != binding_id or record['query'] != row['query']:
                        raise ValueError('discrepancy SQL checkpoint changed')
                    records.append(record); continue
                started = time.perf_counter()
                first_log = FULL / 'logs/truth_mismatch_first_sql.log'
                match = re.search(r'INDEPENDENT_PG_FIRST (\d+) (\d+)', first_log.read_text()) if first_log.exists() else None
                if row['group'] == '4_1_SPN' and int(row['query_no']) == 0 and match:
                    sql_count = int(match.group(1))
                    if int(match.group(2)) != published: raise ValueError('prior exact SQL audit log truth differs')
                    method = 'reused_prior_exact_SQL_execution_log'
                else:
                    cursor.execute(star_count_query(row['query']))
                    sql_count = int(cursor.fetchone()[0]); method = 'PostgreSQL_exact_groupby_count_product_sum'
                status = classify(published, array_count, sql_count)
                record = dict(binding=binding_id, group=row['group'], query_no=int(row['query_no']), query=row['query'],
                    published=published, independent_array=array_count, independent_SQL=sql_count,
                    status=status, seconds=time.perf_counter()-started, method=method,
                    reused_log_sha256=file_sha256(first_log) if method.startswith('reused') else None)
                record['receipt_sha256'] = binding_hash(record); atomic_json(path, record)
                records.append(record)
                print('DISCREPANCY_SQL', row['group'], row['query_no'], status, sql_count, flush=True)
                if status == 'ARRAY_ENGINE_FAILURE': raise ValueError('SQL disproves the exact array engine')
            after = database_identity(connection)
            if before != after: raise ValueError('database identity changed during SQL discrepancy audit')
    finally:
        connection.rollback(); connection.close()
    local = directory / 'all683_local_truth.csv'
    with local.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, ['group', 'query_no', 'query', 'cardinality_true', 'cardinality_published'])
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(group=row['group'], query_no=row['query_no'], query=row['query'],
                cardinality_true=row['independently_computed'], cardinality_published=row['published_truth']))
    result = dict(status='PASS_LOCAL_COUNTS_WITH_PUBLISHED_INPUT_DIFFERENCES', queries=683,
        source_binding=binding_id, binding_details=binding, published_matches=683-len(records),
        independent_SQL_confirmed_differences=len(records), differences=records,
        local_truth_path=local.relative_to(ROOT).as_posix(), local_truth_sha256=file_sha256(local),
        original_published_inputs_unchanged=all(file_sha256(ROOT / p) == sha for p, sha in workload_seals.items()),
        note='The discrepancy cause is not identified. Local exact counts and original published counts stay separate; predictions and trained models are preserved.')
    atomic_json(FULL / 'results/grouped_truth_discrepancies.json', result)
    print('DISCREPANCIES_RESOLVED', len(records), flush=True)
    return result


if __name__ == '__main__': run()
