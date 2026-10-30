"""Local SF500 replay with the failed author population kept explicit."""
import argparse
import hashlib
import os
import math
from pathlib import Path
import random
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from full_ssb_replay import atomic, compare_query, coverage, digest, execute_query, read, value_hash
from full_ssb_native_replay import (required_query_files, validate_query_files,
    validate_query_identities, deny_raw_data_access)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/full/ssb/local_sf500_replay'
RTOL, ATOL = 1e-9, 1e-5
HASH_SEED, RANDOM_SEED = 173, 74031
THREAD_LIMITS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'NUMEXPR_NUM_THREADS')
QUERY_NAMES = ['S1.1', 'S1.2', 'S1.3', 'S2.1', 'S2.2', 'S2.3', 'S3.1',
               'S3.2', 'S3.3', 'S3.4', 'S4.1', 'S4.2', 'S4.3']
OLD_REPLAY_SHA = 'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab'
NATIVE_GUARD_SHA = '6c8de16e03a8ba20448121fd4659c092c668d4db0f7214b932a40bf20d30302d'
ORIGINAL_MISMATCH_SHA = '740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e'
WORKER_FLAG = 'DEEPDB_SSB_LOCAL_REPLAY_WORKER'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_execution(result):
    require(result['status'] == 'PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH'
            and result['stage'] == 'LOCAL_SSB_SF500_REVERSE_REPLAY'
            and result['full_paper_reproduction_complete'] is False
            and result['scope'] == 'LOCAL_SSB_SF500'
            and result['author_reproduction_complete'] is False
            and type(result['author_different_groups']) is int
            and result['author_different_groups'] == 1713
            and type(result['queries']) is int and result['queries'] == 13
            and type(result['original_query_evaluator_calls']) is int
            and result['original_query_evaluator_calls'] == 26
            and type(result['model_loads']) is int and result['model_loads'] == 13
            and result['execution_order'] == list(reversed(range(13)))
            and all(type(i) is int for i in result['execution_order']),
            'complete thirteen-load twenty-six-call reverse replay required')
    binding, environment = result['binding'], result['environment']
    require(binding['hash_seed'] == HASH_SEED and binding['random_seed'] == RANDOM_SEED
            and binding['relative_tolerance'] == RTOL and binding['absolute_tolerance'] == ATOL
            and environment['PYTHONHASHSEED'] == str(HASH_SEED)
            and environment['random_seed'] == environment['numpy_seed'] == RANDOM_SEED
            and environment['thread_limits'] == {name:'1' for name in THREAD_LIMITS},
            'fresh process seed/thread/tolerance policy differs')


def source_snapshot():
    """The local verifier never aliases or weakens the strict author verifier."""
    from full_ssb_local_model import verify_local_formal
    require(digest(ROOT/'code/full_ssb_replay.py') == OLD_REPLAY_SHA,
            'frozen replay helper changed')
    require(digest(ROOT/'code/full_ssb_native_replay.py') == NATIVE_GUARD_SHA,
            'frozen inference guard/identity helper changed')
    formal = verify_local_formal()
    require(formal['status'] == 'PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH'
            and formal['scope'] == 'LOCAL_SSB_SF500'
            and formal['author_reproduction_complete'] is False
            and formal['full_paper_reproduction_complete'] is False
            and type(formal['author_different_groups']) is int
            and formal['author_different_groups'] == 1713
            and type(formal['population_rows']) is int and formal['population_rows'] == 3000028242
            and type(formal['sample_rows']) is int and formal['sample_rows'] == 9996946,
            'complete accepted LOCAL model with author mismatch required')
    mismatch = formal['original_mismatch']
    target = ROOT/mismatch['path']
    require(target.resolve() == (ROOT/'output/full/results/ssb_native_v2.json').resolve()
            and mismatch['sha256'] == ORIGINAL_MISMATCH_SHA
            and target.stat().st_size == mismatch['bytes']
            and digest(target) == ORIGINAL_MISMATCH_SHA,
            'original author population mismatch cannot be hidden or substituted')
    sqls = (ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines()
    validate_query_identities(formal['queries'], sqls, QUERY_NAMES)
    fields = ('verification', 'verification_seal', 'published_result', 'plan',
              'formal_receipt', 'formal_lifecycle', 'artifacts', 'dependencies',
              'model_path', 'model_sha256', 'sample_rows', 'population_rows',
              'evaluation_binding', 'original_mismatch', 'scope',
              'author_reproduction_complete', 'full_paper_reproduction_complete',
              'author_different_groups')
    snapshot = {name:formal[name] for name in fields}
    snapshot['frozen_replay_helper_sha256'] = OLD_REPLAY_SHA
    snapshot['frozen_native_guard_sha256'] = NATIVE_GUARD_SHA
    return snapshot, formal['queries']


def binding_for(snapshot):
    return dict(source_snapshot_sha256=value_hash(snapshot), replay_source_sha256=digest(__file__),
                relative_tolerance=RTOL, absolute_tolerance=ATOL,
                hash_seed=HASH_SEED, random_seed=RANDOM_SEED)


def worker():
    import numpy as np
    require(os.environ.get('DEEPDB_SSB_LOCAL_REPLAY_WORKER') == '1'
            and os.environ.get('PYTHONHASHSEED') == str(HASH_SEED)
            and all(os.environ.get(name) == '1' for name in THREAD_LIMITS),
            'dedicated fresh reverse worker required')
    before, queries = source_snapshot()
    binding = binding_for(before)
    home = OUTPUT/'runs'/value_hash(binding)[:20]
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
        require(before == after, 'local model/source/raw/HDF/dependency snapshot changed')
        for name in required_query_files():
            files[name] = digest(home/name)
        result = dict(status='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH', stage='LOCAL_SSB_SF500_REVERSE_REPLAY',
            full_paper_reproduction_complete=False, author_reproduction_complete=False,
            author_different_groups=1713, scope='LOCAL_SSB_SF500',
            source_snapshot=before, binding=binding,
            directory=home.relative_to(ROOT).as_posix(), execution_order=list(reversed(range(13))),
            queries=13, original_query_evaluator_calls=calls, model_loads=loads,
            comparisons=comparisons, query_files_sha256=files, coverage=coverage(dict(queries=queries)),
            wall_seconds=time.perf_counter()-started,
            environment=dict(PYTHONHASHSEED=os.environ.get('PYTHONHASHSEED'), random_seed=RANDOM_SEED,
                numpy_seed=RANDOM_SEED, process_id=os.getpid(), hash_probe=hash('DeepDB LOCAL SSB replay'),
                thread_limits={name:os.environ.get(name) for name in THREAD_LIMITS}),
            limitations='Independent LOCAL behavior replay; author population still differs in 1713 groups; missing/extra/nonfinite/excluded groups remain explicit. '
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
    require(home.resolve() == (OUTPUT/'runs'/value_hash(result['binding'])[:20]).resolve(),
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
    require(type(process['returncode']) is int and process['returncode'] == 0
            and process['replay_source_sha256'] == digest(__file__)
            and process['binding'] == result['binding']
            and process['report_sha256'] == sha and process['directory'] == result['directory']
            and type(process['reported_worker_process_id']) is int
            and process['reported_worker_process_id'] > 0
            and process['reported_worker_process_id'] == result['environment']['process_id']
            and process['command'] == worker_command()
            and process['environment'] == worker_environment_record()
            and type(process['wall_seconds']) in (int, float)
            and math.isfinite(process['wall_seconds']) and process['wall_seconds'] >= 0,
            'successful fresh worker process receipt required')
    for name in ('stdout', 'stderr'):
        item = process[name]
        path = ROOT/item['path']
        require(path.resolve().parent == (OUTPUT/'logs').resolve() and path.stat().st_size == item['bytes']
                and digest(path) == item['sha256'], 'worker physical log differs')
    return result


def worker_command():
    return [str(ROOT/'.venv/Scripts/python.exe'), '-B', __file__, 'worker']


def worker_environment_record():
    return dict({name:'1' for name in THREAD_LIMITS}, PYTHONHASHSEED=str(HASH_SEED),
                DEEPDB_SSB_LOCAL_REPLAY_WORKER='1', PYTHONDONTWRITEBYTECODE='1')


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
        environment = dict(os.environ, **worker_environment_record())
        command = worker_command()
        started = time.perf_counter()
        with stdout.open('xb') as out, stderr.open('xb') as err:
            process = subprocess.run(command,
                cwd=str(ROOT), env=environment, stdout=out, stderr=err,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def record(path):
            return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=digest(path))
        published = read(OUTPUT/'verification.json') if process.returncode == 0 else None
        atomic(OUTPUT/'last_process.json', dict(returncode=process.returncode, stdout=record(stdout),
                stderr=record(stderr), replay_source_sha256=digest(__file__),
                command=command, environment=worker_environment_record(),
                wall_seconds=time.perf_counter()-started,
                binding=published['binding'] if published else None,
                report_sha256=digest(OUTPUT/'verification.json') if published else None,
                directory=published['directory'] if published else None,
                reported_worker_process_id=published['environment']['process_id'] if published else None))
        require(process.returncode == 0, 'local SSB reverse worker failed; logs and namespace retained')
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
