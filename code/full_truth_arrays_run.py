"""Freeze the dedicated SQL dataset and guard the sealed exact-count runner.

Adds database identity and query-key recovery gates without changing the
already running/exported numeric snapshot or its scientific calculation code.
"""
import argparse
import os
from pathlib import Path
import time

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_postgres import connect
import full_truth_arrays as engine

ENGINE_SHA256 = '5d108ace300762929822e1aac89117ff94cb35a8b4c740397599ee7f39494f4e'


def fs_path(path):
    absolute = str(Path(path).resolve())
    if os.name == 'nt' and len(absolute) >= 240 and not absolute.startswith('\\\\?\\'):
        absolute = '\\\\?\\' + absolute
    return Path(absolute)


def validate_database_identity(stats, reset_timestamp, import_timestamp, imports):
    if reset_timestamp is not None and reset_timestamp > import_timestamp:
        raise ValueError('database statistics reset after sealed table import')
    actual = {name: (inserted, updated, deleted) for name, inserted, updated, deleted in stats}
    if set(actual) != set(imports): raise ValueError('dedicated table inventory changed')
    for table, record in imports.items():
        if actual[table] != (record['rows'], 0, 0):
            raise ValueError('dedicated imported data modified or statistics incomplete: ' + table)
    return True


def validate_count_identity(record, path):
    if isinstance(record, dict) and 'snapshot_binding' in record and 'logical_query' in record:
        if Path(path).stem != binding_hash(record['logical_query']):
            raise ValueError('count receipt query key differs from destination filename')


def database_identity(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_stat_clear_snapshot()')
        cursor.execute('SELECT relname,n_tup_ins,n_tup_upd,n_tup_del FROM pg_stat_user_tables ORDER BY relname')
        stats = cursor.fetchall()
        cursor.execute('SELECT stats_reset FROM pg_stat_database WHERE datname=current_database()')
        reset = cursor.fetchone()[0]
        cursor.execute("SELECT oid,relname,relfilenode FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' ORDER BY relname")
        relation_files = cursor.fetchall()
    path = ROOT / 'data/postgresql/imports.json'
    validate_database_identity(stats, reset.timestamp() if reset else None, path.stat().st_mtime, load_json(path))
    return dict(statistics=stats, stats_reset=reset.isoformat() if reset else None,
                relation_files=relation_files, imported_receipt_sha256=file_sha256(path))


def run(replace_slow_driver=False):
    if file_sha256(ROOT / 'code/full_truth_arrays.py') != ENGINE_SHA256:
        raise ValueError('frozen numeric snapshot engine changed')
    binding = engine.inputs()
    directory = FULL / 'truth_arrays' / binding_hash(binding)
    gate = load_json(directory / 'sql_gate.json')
    if gate is None or gate['status'] != 'PASS' or gate['compared_prior_sql_counts'] < 70:
        raise ValueError('completed independent SQL prefix gate is required')
    # Every table in this first snapshot was exported in one read-only
    # REPEATABLE READ transaction; a SHARE lock now prevents data writes while
    # verifying the remaining queries or resuming this immutable imported DB.
    connection = connect()
    connection.set_session(readonly=False, isolation_level='READ COMMITTED')
    original_loader, original_atomic = engine.load_json, engine.atomic_json
    envelope = dict(status='RUNNING', engine_sha256=ENGINE_SHA256,
        wrapper_sha256=file_sha256(__file__), snapshot_binding=binding_hash(binding),
        initial_sql_gate_sha256=file_sha256(directory / 'sql_gate.json'),
        workload_seals={p.relative_to(ROOT).as_posix(): file_sha256(p)
            for _, query, truth in engine.workload_files() for p in (query, truth)})
    started = time.perf_counter()
    previous = load_json(directory / 'frozen_run.json')
    if previous is not None:
        atomic_json(directory / ('attempt_' + binding_hash(previous)[:12] + '.json'), previous)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET application_name='deepdb_exact_truth_freeze'")
            cursor.execute('LOCK TABLE ' + ','.join('"' + name + '"' for name in sorted(engine.COLUMNS)) + ' IN SHARE MODE')
        envelope['database_before'] = database_identity(connection)
        if replace_slow_driver:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND application_name='deepdb_grouped_truth'")
                pids = [row[0] for row in cursor.fetchall()]
                if len(pids) > 1: raise ValueError('multiple slow-driver connections; refuse ambiguous cancellation')
                for pid in pids:
                    cursor.execute('SELECT pg_cancel_backend(%s)', (pid,))
                    if not cursor.fetchone()[0]: raise ValueError('owned slow exact-count query could not be canceled')
            envelope['superseded_owned_sql_backend_pids'] = pids
        def checked_loader(path, default=None):
            result = original_loader(fs_path(path), default)
            validate_count_identity(result, path)
            return result
        engine.load_json = checked_loader
        engine.atomic_json = lambda path, value: original_atomic(fs_path(path), value)
        result = engine.run()
        envelope['database_after'] = database_identity(connection)
        if envelope['database_before'] != envelope['database_after']:
            raise ValueError('dedicated database identity changed under freeze lock')
        if any(file_sha256(ROOT / path) != checksum for path, checksum in envelope['workload_seals'].items()):
            raise ValueError('workload changed during exact count verification')
        envelope.update(status='PASS' if result['status'] == 'PASS' else result['status'],
            results_sha256=file_sha256(directory / 'verification.json'), queries=result['queries'])
        return envelope
    except BaseException as error:
        envelope.update(status='FAILED', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        engine.load_json = original_loader
        engine.atomic_json = original_atomic
        connection.rollback(); connection.close()
        envelope['seconds'] = time.perf_counter()-started
        envelope['envelope_sha256'] = binding_hash(envelope)
        atomic_json(directory / 'frozen_run.json', envelope)
        print('FROZEN_EXACT_TRUTH_RUN', envelope['status'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-slow-driver', action='store_true')
    run(parser.parse_args().replace_slow_driver)
