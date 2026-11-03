"""Scope-bound replay orchestration; numerical evaluation stays in frozen helpers."""
import hashlib
import math
import os
from pathlib import Path
import random
import subprocess
import time
from full_ssb_replay import atomic, compare_query, coverage, digest, read, value_hash
from full_ssb_native_replay import required_query_files, validate_query_files, deny_raw_data_access
RTOL, ATOL = 1e-9, 1e-5
HASH_SEED, RANDOM_SEED = 173, 74031
THREAD_LIMITS = ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')
HELPER_FILE = Path(__file__).resolve()

def require(condition, message):
    if not condition:
        raise ValueError(message)

class ScopedReplay:
    def __init__(self, root, output, entry, metadata, status, stage, worker_flag, source_factory, executor):
        self.ROOT, self.OUTPUT, self.ENTRY = Path(root), Path(output), Path(entry)
        self.metadata, self.status, self.stage = metadata, status, stage
        self.worker_flag, self.source_snapshot, self.execute_query = worker_flag, source_factory, executor

    def helper_sha(self):
        return digest(HELPER_FILE)

    def validate_execution(self, result):
        require(result['status'] == self.status and result['stage'] == self.stage,
                'replay status/stage differs')
        require(all(type(result[k]) is type(v) and value_hash(result[k]) == value_hash(v)
                    for k,v in self.metadata.items()), 'scope or training budget differs')
        require(type(result['queries']) is int and result['queries'] == 13
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
                and environment['thread_limits'] == {n:'1' for n in THREAD_LIMITS},
                'fresh process seed/thread/tolerance policy differs')

    def binding_for(self, snapshot):
        return dict(source_snapshot_sha256=value_hash(snapshot),
            replay_source_sha256=digest(self.ENTRY), helper_source_sha256=self.helper_sha(),
            configuration_sha256=value_hash(dict(metadata=self.metadata,status=self.status,
                stage=self.stage,worker_flag=self.worker_flag)),
            relative_tolerance=RTOL,absolute_tolerance=ATOL,hash_seed=HASH_SEED,random_seed=RANDOM_SEED)

    def worker_environment_record(self):
        return dict({name:'1' for name in THREAD_LIMITS}, **{self.worker_flag:'1',
            'PYTHONHASHSEED':str(HASH_SEED),'PYTHONDONTWRITEBYTECODE':'1'})

    def worker(self):
        import numpy as np
        require(os.environ.get(self.worker_flag) == '1'
                and os.environ.get('PYTHONHASHSEED') == str(HASH_SEED)
                and all(os.environ.get(name) == '1' for name in THREAD_LIMITS),
                'dedicated fresh reverse worker required')
        before, queries = self.source_snapshot()
        binding = self.binding_for(before)
        home = self.OUTPUT/'runs'/value_hash(binding)[:20]
        home.parent.mkdir(parents=True, exist_ok=True)
        try:
            home.mkdir(exist_ok=False)
        except FileExistsError as error:
            raise ValueError('prior replay namespace retained; automatic rerun refused') from error
        state = home/'lifecycle.json'
        atomic(state, dict(status='RUNNING', binding=binding))
        atomic(self.OUTPUT/'last_run.json', dict(status='RUNNING', directory=home.relative_to(self.ROOT).as_posix(), binding=binding))
        try:
            np.random.seed(RANDOM_SEED)
            random.seed(RANDOM_SEED)
            comparisons, files, calls, loads = {}, {}, 0, 0
            started = time.perf_counter()
            # Source checks are outside the inference guard. Protect prepared files
            # while permitting the saved model in its separate sibling directory.
            prepared = [self.ROOT/item['path'] for item in before['artifacts']
                        if '/prepared/' in item['path']]
            protected = [self.ROOT/'data'] + [path.parent for path in prepared]
            for index in reversed(range(13)):
                expected = queries[index]
                with deny_raw_data_access(protected):
                    actual = self.execute_query(index, expected['sql'], expected['query_name'],
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
            after, _ = self.source_snapshot()
            require(before == after, 'local model/source/raw/HDF/dependency snapshot changed')
            for name in required_query_files():
                files[name] = digest(home/name)
            result = dict(status=self.status, stage=self.stage,
                full_paper_reproduction_complete=False, author_reproduction_complete=False,
                author_different_groups=1713, scope='LOCAL_SSB_SF500',
                source_snapshot=before, binding=binding,
                directory=home.relative_to(self.ROOT).as_posix(), execution_order=list(reversed(range(13))),
                queries=13, original_query_evaluator_calls=calls, model_loads=loads,
                comparisons=comparisons, query_files_sha256=files, coverage=coverage(dict(queries=queries)),
                wall_seconds=time.perf_counter()-started,
                environment=dict(PYTHONHASHSEED=os.environ.get('PYTHONHASHSEED'), random_seed=RANDOM_SEED,
                    numpy_seed=RANDOM_SEED, process_id=os.getpid(), hash_probe=hash('DeepDB LOCAL SSB replay'),
                    thread_limits={name:os.environ.get(name) for name in THREAD_LIMITS}),
                limitations='Independent LOCAL behavior replay; author population still differs in 1713 groups; missing/extra/nonfinite/excluded groups remain explicit. '
                      'Guarded Python raw/prepared data readers were forbidden during model execution; '
                      'this is not an operating-system file-access trace or full-paper completion.')
            result.update(self.metadata)
            self.validate_execution(result)
            atomic(home/'verification.json', result)
            seal = dict(report_sha256=digest(home/'verification.json'), binding=binding, query_files_sha256=files)
            atomic(home/'verification_seal.json', seal)
            atomic(state, dict(status='PASS', binding=binding, report_sha256=seal['report_sha256']))
            atomic(self.OUTPUT/'verification.json', result)
            atomic(self.OUTPUT/'verification_seal.json', seal)
            atomic(self.OUTPUT/'last_run.json', dict(status='PASS', directory=result['directory'],
                                              report_sha256=seal['report_sha256']))
            return result
        except BaseException as error:
            atomic(state, dict(status='TAINTED', binding=binding, error=repr(error)))
            atomic(self.OUTPUT/'last_run.json', dict(status='TAINTED', binding=binding,
                        directory=home.relative_to(self.ROOT).as_posix(), error=repr(error)))
            raise

    def verify(self):
        """Read-only orchestration; provider must independently guarantee its own no-process boundary."""
        result = read(self.OUTPUT/'verification.json')
        seal = read(self.OUTPUT/'verification_seal.json')
        self.validate_execution(result)
        snapshot, queries = self.source_snapshot()
        require(result['source_snapshot'] == snapshot and result['binding'] == self.binding_for(snapshot),
                'current complete source snapshot differs')
        home = self.ROOT/result['directory']
        require(home.resolve() == (self.OUTPUT/'runs'/value_hash(result['binding'])[:20]).resolve(),
                'replay namespace path differs')
        state, latest = read(home/'lifecycle.json'), read(self.OUTPUT/'last_run.json')
        sha = digest(self.OUTPUT/'verification.json')
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
        process = read(self.OUTPUT/'last_process.json')
        require(type(process['returncode']) is int and process['returncode'] == 0
                and process['replay_source_sha256'] == digest(str(self.ENTRY))
                and process['helper_source_sha256'] == self.helper_sha()
                and process['binding'] == result['binding']
                and process['report_sha256'] == sha and process['directory'] == result['directory']
                and type(process['reported_worker_process_id']) is int
                and process['reported_worker_process_id'] > 0
                and process['reported_worker_process_id'] == result['environment']['process_id']
                and process['command'] == self.worker_command()
                and process['environment'] == self.worker_environment_record()
                and type(process['wall_seconds']) in (int, float)
                and math.isfinite(process['wall_seconds']) and process['wall_seconds'] >= 0,
                'successful fresh worker process receipt required')
        require((self.ROOT/process['stdout']['path']).resolve() !=
                (self.ROOT/process['stderr']['path']).resolve(),
                'two distinct physical worker logs required')
        for name in ('stdout', 'stderr'):
            item = process[name]
            path = self.ROOT/item['path']
            require(path.resolve().parent == (self.OUTPUT/'logs').resolve() and path.stat().st_size == item['bytes']
                    and digest(path) == item['sha256'], 'worker physical log differs')
        return result

    def worker_command(self):
        return [str(self.ROOT/'.venv/Scripts/python.exe'), '-B', str(self.ENTRY), 'worker']

    def replay(self):
        """Explicit single controller; accepted evidence is only verified and reused."""
        if (self.OUTPUT/'verification.json').exists():
            return self.verify()
        self.source_snapshot()  # Fail before namespace creation or child launch.
        self.OUTPUT.mkdir(parents=True, exist_ok=True)
        lock = self.OUTPUT/'controller.lock'
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(descriptor, str(os.getpid()).encode())
            os.fsync(descriptor)
            logs = self.OUTPUT/'logs'
            logs.mkdir(exist_ok=True)
            stem = str(time.time_ns())+'_'+digest(str(self.ENTRY))[:16]
            stdout, stderr = logs/(stem+'.stdout.log'), logs/(stem+'.stderr.log')
            environment = dict(os.environ, **self.worker_environment_record())
            command = self.worker_command()
            started = time.perf_counter()
            with stdout.open('xb') as out, stderr.open('xb') as err:
                process = subprocess.run(command,
                    cwd=str(self.ROOT), env=environment, stdout=out, stderr=err,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def record(path):
                return dict(path=path.relative_to(self.ROOT).as_posix(), bytes=path.stat().st_size, sha256=digest(path))
            published = read(self.OUTPUT/'verification.json') if process.returncode == 0 else None
            atomic(self.OUTPUT/'last_process.json', dict(returncode=process.returncode, stdout=record(stdout),
                    stderr=record(stderr), replay_source_sha256=digest(str(self.ENTRY)),
                    helper_source_sha256=self.helper_sha(),
                    command=command, environment=self.worker_environment_record(),
                    wall_seconds=time.perf_counter()-started,
                    binding=published['binding'] if published else None,
                    report_sha256=digest(self.OUTPUT/'verification.json') if published else None,
                    directory=published['directory'] if published else None,
                    reported_worker_process_id=published['environment']['process_id'] if published else None))
            require(process.returncode == 0, 'local SSB reverse worker failed; logs and namespace retained')
            return self.verify()
        finally:
            os.close(descriptor)
            lock.unlink()
