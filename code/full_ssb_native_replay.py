"""Independent native SSB replay; execution waits for a sealed formal model."""
import argparse
import builtins
from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import random
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from full_ssb_replay import atomic, compare_query, coverage, digest, execute_query, read, value_hash

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/full/ssb/native_v2_replay'
RTOL, ATOL = 1e-9, 1e-5
HASH_SEED, RANDOM_SEED = 173, 74031
THREAD_LIMITS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'NUMEXPR_NUM_THREADS')
QUERY_NAMES = ['S1.1', 'S1.2', 'S1.3', 'S2.1', 'S2.2', 'S2.3', 'S3.1',
               'S3.2', 'S3.3', 'S3.4', 'S4.1', 'S4.2', 'S4.3']
OLD_REPLAY_SHA = 'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def required_query_files():
    return ['query_%02d%s' % (index, suffix) for index in range(13)
            for suffix in ('.json', '.seal.json')]


def validate_query_files(names):
    names = list(names)
    require(len(names) == 26 and len(set(names)) == 26
            and set(names) == set(required_query_files()),
            'exact twenty-six unique replay query artifacts required')


def validate_query_identities(queries, sqls, names):
    require(isinstance(queries, list) and len(queries) == len(sqls) == len(names) == 13,
            'all thirteen formal SQL identities required')
    require(len(set(sqls)) == len(set(names)) == 13, 'duplicate workload identity')
    for index, (query, sql, name) in enumerate(zip(queries, sqls, names)):
        require(type(query['query_no']) is int and query['query_no'] == index
                and query['query_name'] == name and query['sql'] == sql,
                'formal query index/name/exact SQL differs')
        require('point_error' in query and 'ci_error' in query
                and query['point_error'] is None and query['ci_error'] is None,
                'formal query errors must remain recorded; successful replay unavailable')


def validate_execution(result):
    require(result['status'] == 'PASS_NATIVE_V2_INDEPENDENT_REVERSE_REPLAY'
            and result['stage'] == 'SSB_NATIVE_V2_REVERSE_REPLAY'
            and result['full_paper_reproduction_complete'] is False
            and type(result['queries']) is int and result['queries'] == 13
            and type(result['original_query_evaluator_calls']) is int
            and result['original_query_evaluator_calls'] == 26
            and type(result['model_loads']) is int and result['model_loads'] == 13
            and result['execution_order'] == list(reversed(range(13))),
            'complete thirteen-load twenty-six-call reverse replay required')
    binding, environment = result['binding'], result['environment']
    require(binding['hash_seed'] == HASH_SEED and binding['random_seed'] == RANDOM_SEED
            and binding['relative_tolerance'] == RTOL and binding['absolute_tolerance'] == ATOL
            and environment['PYTHONHASHSEED'] == str(HASH_SEED)
            and environment['random_seed'] == environment['numpy_seed'] == RANDOM_SEED
            and environment['thread_limits'] == {name:'1' for name in THREAD_LIMITS},
            'fresh process seed/thread/tolerance policy differs')


def source_snapshot():
    """Only the new formal bridge may discover or accept native model evidence."""
    from full_ssb_native_model import verify_formal
    require(digest(ROOT/'code/full_ssb_replay.py') == OLD_REPLAY_SHA,
            'frozen replay helper changed')
    formal = verify_formal()
    require(formal['status'] == 'PASS_READ_ONLY_SSB_NATIVE_V2_FORMAL_MODEL',
            'successful complete formal model required before reverse replay')
    sqls = (ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines()
    validate_query_identities(formal['queries'], sqls, QUERY_NAMES)
    fields = ('verification', 'verification_seal', 'published_result', 'plan',
              'formal_receipt', 'formal_lifecycle', 'artifacts', 'dependencies',
              'model_path', 'model_sha256', 'sample_rows', 'population_rows',
              'evaluation_binding')
    snapshot = {name:formal[name] for name in fields}
    snapshot['frozen_replay_helper_sha256'] = OLD_REPLAY_SHA
    return snapshot, formal['queries']


@contextmanager
def deny_raw_data_access(roots):
    """Guard Python file readers and numerical data loaders during inference."""
    import numpy as np
    import pandas as pd
    import tables
    roots = [Path(root).resolve() for root in roots]
    original_open, original_io_open = builtins.open, io.open
    def guarded_open(original):
        def call(file, *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)):
                target = Path(os.fsdecode(file)).resolve()
                require(not any(target == root or root in target.parents for root in roots),
                        'raw/prepared input access forbidden during saved-model replay')
            return original(file, *args, **kwargs)
        return call
    def forbidden(*args, **kwargs):
        raise ValueError('numerical data loader forbidden during saved-model replay')
    loaders = [(np, 'load'), (np, 'fromfile'), (pd, 'read_csv'),
               (pd, 'read_hdf'), (tables, 'open_file')]
    saved = [(module, name, getattr(module, name)) for module, name in loaders]
    builtins.open, io.open = guarded_open(original_open), guarded_open(original_io_open)
    for module, name, _ in saved:
        setattr(module, name, forbidden)
    try:
        yield
    finally:
        builtins.open, io.open = original_open, original_io_open
        for module, name, original in saved:
            setattr(module, name, original)


def binding_for(snapshot):
    return dict(source_snapshot_sha256=value_hash(snapshot), replay_source_sha256=digest(__file__),
                relative_tolerance=RTOL, absolute_tolerance=ATOL,
                hash_seed=HASH_SEED, random_seed=RANDOM_SEED)


def worker():
    import numpy as np
    require(os.environ.get('DEEPDB_SSB_NATIVE_REPLAY_WORKER') == '1'
            and os.environ.get('PYTHONHASHSEED') == str(HASH_SEED)
            and all(os.environ.get(name) == '1' for name in THREAD_LIMITS),
            'dedicated fresh reverse worker required')
    before, queries = source_snapshot()
    binding = binding_for(before)
    home = OUTPUT/'runs'/value_hash(binding)
    home.parent.mkdir(parents=True, exist_ok=True)
    try:
        home.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise ValueError('prior replay namespace retained; automatic rerun refused') from error
    state = home/'lifecycle.json'
    atomic(state, dict(status='RUNNING', binding=binding))
    atomic(OUTPUT/'last_run.json', dict(status='RUNNING', directory=home.relative_to(ROOT).as_posix(), binding=binding))
    try:
        np.random.seed(RANDOM_SEED)
        random.seed(RANDOM_SEED)
        comparisons, files, calls, loads = {}, {}, 0, 0
        started = time.perf_counter()
        # Source checks are outside the inference guard. Protect prepared files
        # while permitting the saved model in its separate sibling directory.
        prepared = [ROOT/item['path'] for item in before['artifacts']
                    if '/prepared/' in item['path']]
        protected = [ROOT/'data'] + [path.parent for path in prepared]
        for index in reversed(range(13)):
            expected = queries[index]
            with deny_raw_data_access(protected):
                actual = execute_query(index, expected['sql'], expected['query_name'],
                                       before['model_path'], before['sample_rows'])
            require(actual['original_query_evaluator_calls'] == 2 and actual['model_loads'] == 1,
                    'each actual query must load once and execute both evaluator paths')
            calls += actual['original_query_evaluator_calls']
            loads += actual['model_loads']
            comparison = compare_query(expected, actual)
            path = home/('query_%02d.json' % index)
            atomic(path, dict(actual=actual, comparison=comparison))
            atomic(path.with_suffix('.seal.json'), dict(binding=binding, query_no=index,
                exact_sql_sha256=hashlib.sha256(expected['sql'].encode()).hexdigest(), sha256=digest(path)))
            comparisons[str(index)] = comparison
        after, _ = source_snapshot()
        require(before == after, 'native model/source/raw/HDF/dependency snapshot changed')
        for name in required_query_files():
            files[name] = digest(home/name)
        result = dict(status='PASS_NATIVE_V2_INDEPENDENT_REVERSE_REPLAY', stage='SSB_NATIVE_V2_REVERSE_REPLAY',
            full_paper_reproduction_complete=False, source_snapshot=before, binding=binding,
            directory=home.relative_to(ROOT).as_posix(), execution_order=list(reversed(range(13))),
            queries=13, original_query_evaluator_calls=calls, model_loads=loads,
            comparisons=comparisons, query_files_sha256=files, coverage=coverage(dict(queries=queries)),
            wall_seconds=time.perf_counter()-started,
            environment=dict(PYTHONHASHSEED=os.environ.get('PYTHONHASHSEED'), random_seed=RANDOM_SEED,
                numpy_seed=RANDOM_SEED, process_id=os.getpid(), hash_probe=hash('DeepDB native SSB replay'),
                thread_limits={name:os.environ.get(name) for name in THREAD_LIMITS}),
            scope='Independent behavior replay; missing/extra/nonfinite/excluded groups remain explicit. '
                  'Guarded Python raw/prepared data readers were forbidden during model execution; '
                  'this is not an operating-system file-access trace or full-paper completion.')
        validate_execution(result)
        atomic(home/'verification.json', result)
        seal = dict(report_sha256=digest(home/'verification.json'), binding=binding, query_files_sha256=files)
        atomic(home/'verification_seal.json', seal)
        atomic(state, dict(status='PASS', binding=binding, report_sha256=seal['report_sha256']))
        atomic(OUTPUT/'verification.json', result)
        atomic(OUTPUT/'verification_seal.json', seal)
        atomic(OUTPUT/'last_run.json', dict(status='PASS', directory=result['directory'],
                                          report_sha256=seal['report_sha256']))
        return result
    except BaseException as error:
        atomic(state, dict(status='TAINTED', binding=binding, error=repr(error)))
        atomic(OUTPUT/'last_run.json', dict(status='TAINTED', binding=binding,
                    directory=home.relative_to(ROOT).as_posix(), error=repr(error)))
        raise


def verify():
    """Strictly read-only: never predict, start a process, repair, or write."""
    result = read(OUTPUT/'verification.json')
    seal = read(OUTPUT/'verification_seal.json')
    validate_execution(result)
    snapshot, queries = source_snapshot()
    require(result['source_snapshot'] == snapshot and result['binding'] == binding_for(snapshot),
            'current complete source snapshot differs')
    home = ROOT/result['directory']
    require(home.resolve() == (OUTPUT/'runs'/value_hash(result['binding'])).resolve(),
            'replay namespace path differs')
    state, latest = read(home/'lifecycle.json'), read(OUTPUT/'last_run.json')
    sha = digest(OUTPUT/'verification.json')
    require(seal == dict(report_sha256=sha, binding=result['binding'], query_files_sha256=result['query_files_sha256'])
            and digest(home/'verification.json') == sha and read(home/'verification_seal.json') == seal
            and state == dict(status='PASS', binding=result['binding'], report_sha256=sha)
            and latest == dict(status='PASS', directory=result['directory'], report_sha256=sha),
            'complete replay lifecycle/alias/self seal differs')
    validate_query_files(result['query_files_sha256'])
    require({p.name for p in home.iterdir()} == set(required_query_files()) |
            {'verification.json', 'verification_seal.json', 'lifecycle.json'},
            'replay artifact set missing or extra')
    require(set(result['comparisons']) == {str(i) for i in range(13)}, 'all thirteen comparisons required')
    for index in range(13):
        path = home/('query_%02d.json' % index)
        qseal, query = read(path.with_suffix('.seal.json')), read(path)
        for candidate in (path, path.with_suffix('.seal.json')):
            require(digest(candidate) == result['query_files_sha256'][candidate.name], 'replay query hash differs')
        require(qseal == dict(binding=result['binding'], query_no=index, sha256=digest(path),
                exact_sql_sha256=hashlib.sha256(queries[index]['sql'].encode()).hexdigest()),
                'replay exact query identity/seal differs')
        actual = query['actual']
        require(actual['original_query_evaluator_calls'] == 2 and actual['model_loads'] == 1,
                'actual per-query execution accounting differs')
        comparison = compare_query(queries[index], actual)
        require(query['comparison'] == result['comparisons'][str(index)] == comparison,
                'replay numerical comparison differs')
    require(result['coverage'] == coverage(dict(queries=queries)), 'replay coverage/gaps differ')
    process = read(OUTPUT/'last_process.json')
    require(process['returncode'] == 0 and process['replay_source_sha256'] == digest(__file__),
            'successful fresh worker process receipt required')
    for name in ('stdout', 'stderr'):
        item = process[name]
        path = ROOT/item['path']
        require(path.resolve().parent == (OUTPUT/'logs').resolve() and path.stat().st_size == item['bytes']
                and digest(path) == item['sha256'], 'worker physical log differs')
    return result


def replay():
    """Explicit single controller; accepted evidence is only verified and reused."""
    if (OUTPUT/'verification.json').exists():
        return verify()
    source_snapshot()  # Fail before namespace creation or child launch.
    OUTPUT.mkdir(parents=True, exist_ok=True)
    lock = OUTPUT/'controller.lock'
    descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.fsync(descriptor)
        logs = OUTPUT/'logs'
        logs.mkdir(exist_ok=True)
        stem = str(time.time_ns())+'_'+digest(__file__)[:16]
        stdout, stderr = logs/(stem+'.stdout.log'), logs/(stem+'.stderr.log')
        environment = dict(os.environ, PYTHONHASHSEED=str(HASH_SEED),
                           DEEPDB_SSB_NATIVE_REPLAY_WORKER='1', PYTHONDONTWRITEBYTECODE='1')
        environment.update({name:'1' for name in THREAD_LIMITS})
        with stdout.open('xb') as out, stderr.open('xb') as err:
            process = subprocess.run([str(ROOT/'.venv/Scripts/python.exe'), '-B', __file__, 'worker'],
                cwd=str(ROOT), env=environment, stdout=out, stderr=err,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def record(path):
            return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=digest(path))
        atomic(OUTPUT/'last_process.json', dict(returncode=process.returncode, stdout=record(stdout),
                stderr=record(stderr), replay_source_sha256=digest(__file__)))
        require(process.returncode == 0, 'native SSB reverse worker failed; logs and namespace retained')
        return verify()
    finally:
        os.close(descriptor)
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['replay', 'worker', 'verify'])
    action = parser.parse_args().action
    report = {'replay':replay, 'worker':worker, 'verify':verify}[action]()
    print({name:report[name] for name in ('status', 'queries', 'coverage')})
