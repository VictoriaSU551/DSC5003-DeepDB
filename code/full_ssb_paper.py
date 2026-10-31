"""Reviewable SF500 streaming entry. Only setup, SF2 gate and plan run by default.

SF1 artifacts and the unmodified pinned dbgen source remain read-only. The run
command requires the exact reviewed plan digest and an explicit --execute flag.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import pickle
import shutil
import subprocess
import time
import urllib.request
import uuid
import zipfile
from decimal import Decimal, localcontext

import full_ssb_generate as sf1

ROOT, VENDOR, BUILD = sf1.ROOT, sf1.VENDOR, sf1.BUILD
DATA = ROOT / 'data/ssb'
OUTPUT = ROOT / 'output/full/ssb/paper'
PINS = VENDOR / 'SOURCES.json'
TRUTH = ROOT / 'code/benchmarks/ssb/ground_truth_500GB.pkl'
QUERIES = sf1.QUERIES
REQUIRED_ROWS = 3000028242
SEED = 20261030
GIB = 1024 ** 3
digest, atomic = sf1.digest, sf1.atomic


def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def restore_sources(archive, destination, pins):
    """Validate everything first, then restore only missing upstream byte streams."""
    archive, destination = Path(archive), Path(destination)
    if digest(archive) != pins['archive_sha256']:
        raise ValueError('Fixed source archive checksum changed')
    validated = {}
    with zipfile.ZipFile(str(archive)) as stream:
        members = {}
        for item in stream.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename:
                raise ValueError('Unsafe archive member')
            if item.is_dir():
                continue
            if len(name.parts) != 2 or name.parts[1] not in pins['files_sha256']:
                raise ValueError('Unexpected archive member: ' + item.filename)
            if name.parts[1] in members:
                raise ValueError('Duplicate archive member')
            members[name.parts[1]] = item
        if set(members) != set(pins['files_sha256']):
            raise ValueError('Fixed source archive file set changed')
        for name, expected in pins['files_sha256'].items():
            content = stream.read(members[name])
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('Pinned file checksum changed: ' + name)
            target = destination / name
            if target.exists() and digest(target) != expected:
                raise ValueError('Existing upstream source changed: ' + name)
            validated[name] = content
    destination.mkdir(parents=True, exist_ok=True)
    restored = []
    for name, content in validated.items():
        target = destination / name
        if not target.exists():
            temporary = target.with_name(target.name + '.restore.tmp')
            with temporary.open('wb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.replace(str(temporary), str(target))
            restored.append(name)
    return {'status': 'PASS', 'archive_sha256': digest(archive), 'restored': restored,
            'verified_files': len(validated)}


def setup_sources():
    pins = json.loads(PINS.read_text())
    archive = ROOT / 'data/downloads' / ('ssb-dbgen-' + pins['commit'] + '.zip')
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = archive.with_suffix('.download.tmp')
        with urllib.request.urlopen(pins['url'], timeout=60) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target)
        if digest(temporary) != pins['archive_sha256']:
            raise ValueError('Downloaded source archive checksum changed')
        os.replace(str(temporary), str(archive))
    result = restore_sources(archive, VENDOR, pins)
    atomic(OUTPUT / 'source_setup.json', result)
    return result


def order_ranges(scale, shards):
    if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1 or scale > 500:
        raise ValueError('Invalid scale')
    total = scale * 1500000
    if not isinstance(shards, int) or shards < 1 or shards > min(10000, total):
        raise ValueError('Invalid shard count')
    per = total // shards
    return [(per * i + 1, per + (total % shards if i == shards - 1 else 0)) for i in range(shards)]


def compare_truth(actual, expected):
    missing, extra, values = [], [], []
    for q in sorted(set(actual) | set(expected), key=int):
        a, e = actual.get(q, {}), expected.get(q, {})
        missing += [{'query': q, 'group': k} for k in sorted(set(e) - set(a))]
        extra += [{'query': q, 'group': k} for k in sorted(set(a) - set(e))]
        for k in sorted(set(a) & set(e)):
            if type(a[k]) is not int or type(e[k]) is not int:
                raise ValueError('Truth must use exact integers')
            if a[k] != e[k]:
                values.append({'query': q, 'group': k, 'actual': a[k], 'expected': e[k]})
    return {'match': not (missing or extra or values), 'missing_groups': missing,
            'extra_groups': extra, 'different_values': values}


def author_truth():
    # This local pickle is part of the pinned DeepDB benchmark, not remote input.
    with TRUTH.open('rb') as source:
        raw = pickle.load(source)
    if set(raw) != set(range(13)):
        raise ValueError('Author truth must contain all 13 queries')
    result = {}
    for q, rows in raw.items():
        groups = {}
        for row in rows:
            key = '\t'.join(str(x) for x in row[:-1])
            if key in groups or type(row[-1]) is not int:
                raise ValueError('Invalid author truth group or noninteger total')
            groups[key] = row[-1]
        result[str(q)] = groups
    return result


def restore_checkpoint(sample, state, binding, directory):
    if state['binding'] != binding:
        raise ValueError('Checkpoint binding changed')
    records = state['committed_shards']
    if [x['shard'] for x in records] != list(range(1, len(records) + 1)) or state['next_shard'] != len(records) + 1:
        raise ValueError('Checkpoint shards must be contiguous')
    merged = {str(q): {} for q in range(13)}
    for item in records:
        for name, expected in item['retained_sha256'].items():
            path = Path(directory) / name
            if not path.is_file() or digest(path) != expected:
                raise ValueError('Committed shard artifact changed: ' + name)
        sf1.merge_aggregates(merged, sf1.read_aggregates(Path(directory) / item['aggregate_file']))
    if merged != state['aggregates'] or sum(x['rows'] for x in records) != state['rows']:
        raise ValueError('Committed aggregate or row accounting changed')
    if (sum(x['sample_rows'] for x in records) != state['sample_rows']
            or sum(x['sample_bytes'] for x in records) != state['sample_bytes']):
        raise ValueError('Committed sample accounting changed')
    return sf1.resume_sample(sample, state, binding)


def require_execution(plan, reviewed_sha, execute, free_bytes):
    if not execute:
        raise ValueError('SF500 requires explicit --execute from the reviewing root task')
    if reviewed_sha != object_sha(plan) or plan.get('status') != 'READY_FOR_ROOT_REVIEW':
        raise ValueError('The reviewed plan digest does not match')
    required = plan.get('resources', {}).get('required_free_bytes', 6 * GIB)
    if free_bytes < required:
        raise ValueError('Insufficient free disk for the reviewed plan')


def call(arguments, directory, log):
    environment = dict(os.environ, PATH=str(sf1.GCC.parent) + os.pathsep + os.environ.get('PATH', ''))
    started = time.perf_counter()
    result = subprocess.run([str(x) for x in arguments], cwd=str(directory), env=environment,
                            capture_output=True, text=True, errors='replace')
    receipt = {'arguments': [str(x) for x in arguments], 'returncode': result.returncode,
               'stdout': result.stdout, 'stderr': result.stderr, 'seconds': time.perf_counter() - started}
    atomic(log, receipt)
    if result.returncode:
        raise RuntimeError('Native command failed: ' + str(log))
    return receipt


def compiled_binding():
    setup_sources()
    result = sf1.build()  # Only sealed binaries; never original_reference()/SF1 evaluation.
    return {'build': result, 'dimension_build': build_dimension_driver(), 'runner_sha256': digest(Path(__file__)),
            'sf1_helpers_sha256': digest(Path(sf1.__file__)), 'pins_sha256': digest(PINS),
            'queries_sha256': digest(QUERIES), 'author_truth_sha256': digest(TRUTH),
            'dbgen_seed_policy': 'unmodified rnd.h fixed Seed[]; no generator seed override',
            'sampling_policy': 'independent stateless uint64 mix in pinned full_consumer.cpp'}


def build_dimension_driver():
    directory = OUTPUT / 'build'; directory.mkdir(parents=True, exist_ok=True)
    executable = directory / 'dbgen_dimensions.exe'
    source = VENDOR / 'full_dimension_driver.c'
    binding = {'upstream': json.loads(PINS.read_text())['files_sha256'], 'adapter': digest(source),
               'compiler': digest(sf1.GCC), 'flags_version': 1}
    receipt = directory / 'dimension_build.json'
    if receipt.exists():
        result = json.loads(receipt.read_text())
        if result['binding'] == binding and executable.exists() and digest(executable) == result['executable_sha256']:
            return result
    flags = ['-O2', '-std=gnu89', '-fcommon', '-Wno-implicit-function-declaration',
             '-Wno-int-conversion', '-Wno-incompatible-pointer-types', '-DWIN32',
             '-DSSBM', '-DDB2', '-static-libgcc', '-Dmain=ssb_original_main']
    call([sf1.GCC] + flags + [VENDOR / name for name in sf1.SOURCES]
         + [source, '-o', executable, '-lm'], VENDOR, directory / 'compile_dimensions.json')
    result = {'binding': binding, 'executable_sha256': digest(executable)}
    atomic(receipt, result)
    return result


def generate_dimension_group(scale, directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    compiled = build_dimension_driver()
    binding = {'scale': scale, 'dimension_build': compiled}
    receipt = directory / 'group_generation.json'
    if receipt.exists():
        prior = json.loads(receipt.read_text())
        if (prior['binding'] == binding and all((directory / (name + '.tbl')).exists()
                and digest(directory / (name + '.tbl')) == entry['sha256'] for name, entry in prior['files'].items())
                and set(prior['files']) == set(expected_dimensions(scale))):
            return prior
    run = call([OUTPUT / 'build/dbgen_dimensions.exe', scale, VENDOR / 'dists.dss'],
               directory, directory / 'generate_group.json')
    files = {}
    for name, expected in expected_dimensions(scale).items():
        path = directory / (name + '.tbl')
        rows = file_rows(path)
        if rows != expected:
            raise ValueError('Unexpected dimension row count: ' + name)
        files[name] = {'rows': rows, 'bytes': path.stat().st_size, 'sha256': digest(path)}
    result = {'binding': binding, 'files': files, 'seconds': run['seconds']}
    atomic(receipt, result)
    return result


def expected_dimensions(scale):
    return {'customer': 30000 * scale, 'supplier': 2000 * scale,
            'part': 200000 * int(math.floor(1 + math.log(scale, 2))), 'date': 2556}


def file_rows(path):
    with Path(path).open('rb') as stream:
        return sum(block.count(b'\n') for block in iter(lambda: stream.read(4 * 1024 * 1024), b''))


def pending_dimensions(directory, receipt, expected):
    if set(receipt['files']) - set(expected):
        raise ValueError('Unexpected committed dimension')
    for name, entry in receipt['files'].items():
        path = Path(directory) / (name + '.tbl')
        if entry['rows'] != expected[name] or not path.is_file() or digest(path) != entry['sha256']:
            raise ValueError('Committed dimension changed: ' + name)
    return [name for name in expected if name not in receipt['files']]


def cleanup_dimension_copies(work, files):
    for name, entry in files.items():
        path = Path(work) / (name + '.tbl')
        if path.exists():
            if digest(path) != entry['sha256']:
                raise ValueError('Unmatched completed dimension copy')
            path.unlink()


def dimensions(scale, directory, binding):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / 'dimensions.json'
    dimension_binding = {'scale': scale, 'dimension_build': binding['dimension_build'], 'pins_sha256': binding['pins_sha256']}
    if receipt.exists():
        result = json.loads(receipt.read_text())
        if result['binding'] != dimension_binding:
            raise ValueError('Dimension source binding changed')
    else:
        result = {'binding': dimension_binding, 'files': {}, 'seconds': 0.0, 'status': 'IN_PROGRESS'}
    expected = expected_dimensions(scale)
    pending = pending_dimensions(directory, result, expected)
    work = directory / 'building_group'
    if not pending:
        cleanup_dimension_copies(work, result['files'])
        if result.get('status') != 'PASS':
            result['status'] = 'PASS'; atomic(receipt, result)
        return result
    group = generate_dimension_group(scale, work)
    for name in pending:
        path = work / (name + '.tbl')
        entry = group['files'][name]
        os.replace(str(path), str(directory / path.name))
        result['files'][name] = entry
        atomic(receipt, result)
    result['seconds'] += group['seconds']
    cleanup_dimension_copies(work, result['files'])
    result['status'] = 'PASS'
    atomic(receipt, result)
    return result


class NativeConsumer:
    def __init__(self, dimension_directory, log_directory):
        Path(log_directory).mkdir(parents=True, exist_ok=True)
        self.log = (Path(log_directory) / 'consumer_stderr.log').open('a', encoding='utf-8')
        started = time.perf_counter()
        self.process = subprocess.Popen([str(BUILD / 'full_consumer.exe'), str(dimension_directory)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                        text=True, bufsize=1)
        if self.process.stdout.readline().strip() != 'READY':
            raise RuntimeError('Dimension loading failed')
        self.load_seconds = time.perf_counter() - started

    def consume(self, raw, directory, seed, probability):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        self.process.stdin.write('\t'.join(map(str, [raw, directory, seed, probability])) + '\n')
        self.process.stdin.flush()
        reply = self.process.stdout.readline().strip()
        if reply != 'OK':
            raise RuntimeError('Native consumer failed: ' + reply)
        result = json.loads((directory / 'stats.json').read_text())
        result['seconds'] = time.perf_counter() - started
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('QUIT\n'); self.process.stdin.flush()
            self.process.wait(timeout=20)
        self.log.close()


def cleanup_committed(state, work, directory):
    for item in state['committed_shards']:
        for path, expected in [(Path(work) / item['raw_name'], item['raw_sha256']),
                               (Path(directory) / item['sample_file'], item['sample_sha256'])]:
            if path.exists():
                if digest(path) != expected:
                    raise ValueError('Committed leftover checksum changed')
                path.unlink()


def stream(scale, shards, seed, probability, directory, data, binding, stop_after=None):
    ranges = order_ranges(scale, shards)
    directory, data = Path(directory), Path(data)
    directory.mkdir(parents=True, exist_ok=True); data.mkdir(parents=True, exist_ok=True)
    dimension_receipt = dimensions(scale, data / 'dimensions', binding)
    run_binding = {'scale': scale, 'shards': shards, 'sample_seed': seed, 'sample_probability': probability,
                   'inputs': binding, 'dimensions': dimension_receipt['files']}
    checkpoint, sample = directory / 'checkpoint.json', data / 'lineorder_sampled.csv'
    work = data / 'bounded_work'; work.mkdir(exist_ok=True)
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        hasher = restore_checkpoint(sample, state, run_binding, directory)
        cleanup_committed(state, work, directory)
    else:
        if sample.exists() and sample.stat().st_size:
            raise ValueError('Sample exists without a committed checkpoint')
        sample.touch(); hasher = hashlib.sha256()
        state = {'binding': run_binding, 'sample_bytes': 0, 'sample_sha256': hasher.hexdigest(),
                 'sample_rows': 0, 'next_shard': 1, 'committed_shards': [], 'rows': 0,
                 'aggregates': {str(q): {} for q in range(13)}}
        atomic(checkpoint, state)
    if state['next_shard'] > shards:
        return state
    consumer = NativeConsumer(data / 'dimensions', directory)
    completed = 0
    try:
        for shard in range(state['next_shard'], shards + 1):
            if shutil.disk_usage(str(data)).free < 2 * GIB:
                raise ValueError('Less than 2 GiB reserved free disk')
            started = time.perf_counter()
            generation = call([BUILD / 'dbgen_chunk.exe', scale, shards, shard, VENDOR / 'dists.dss'],
                              work, directory / 'logs' / ('generate_%04d.json' % shard))
            raw = work / ('lineorder.tbl.%d' % shard)
            if raw.stat().st_size > 256 * 1024 ** 2:
                raise ValueError('Raw chunk exceeded the 256 MiB hard bound')
            chunk = directory / 'shards' / ('%04d' % shard)
            stats = consumer.consume(raw, chunk, seed, probability)
            chunk_sample = chunk / 'sample.csv'
            aggregate = chunk / 'aggregates.tsv'
            with sample.open('ab') as target, chunk_sample.open('rb') as source:
                for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                    target.write(block); hasher.update(block)
                target.flush(); os.fsync(target.fileno())
            item = {'shard': shard, 'first_order': ranges[shard - 1][0], 'orders': ranges[shard - 1][1],
                    'rows': stats['rows'], 'sample_rows': stats['sample_rows'],
                    'raw_name': raw.name, 'raw_bytes': raw.stat().st_size, 'raw_sha256': digest(raw),
                    'sample_file': chunk_sample.relative_to(directory).as_posix(),
                    'sample_sha256': digest(chunk_sample), 'sample_bytes': chunk_sample.stat().st_size,
                    'aggregate_file': aggregate.relative_to(directory).as_posix(),
                    'retained_sha256': {p.relative_to(directory).as_posix(): digest(p) for p in [aggregate, chunk / 'stats.json']},
                    'generation_seconds': generation['seconds'], 'consume_seconds': stats['seconds'],
                    'total_seconds': time.perf_counter() - started}
            sf1.merge_aggregates(state['aggregates'], sf1.read_aggregates(aggregate))
            state['rows'] += stats['rows']; state['sample_rows'] += stats['sample_rows']
            state['sample_bytes'] = sample.stat().st_size; state['sample_sha256'] = hasher.hexdigest()
            state['committed_shards'].append(item); state['next_shard'] = shard + 1
            state['consumer_load_seconds'] = state.get('consumer_load_seconds', 0) + (consumer.load_seconds if completed == 0 else 0)
            atomic(checkpoint, state)
            raw.unlink(); chunk_sample.unlink()
            completed += 1
            if stop_after is not None and completed >= stop_after:
                break
    finally:
        consumer.close()
    return state


def stock_pipe_compare(scale, records, directory):
    """Unmodified stock -T a writes a Windows pipe; no full fact CSV lands."""
    if os.name != 'nt':
        raise RuntimeError('This byte gate currently requires Windows named pipes')
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    kernel.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = '\\\\.\\pipe\\ssb-' + uuid.uuid4().hex[:12]
    handle = kernel.CreateNamedPipeW(name, 1, 1, 1, 65536, 4 * 1024 * 1024, 600000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    process = subprocess.Popen([str(BUILD / 'dbgen.exe'), '-s', str(scale), '-T', 'a', '-f',
                                '-O', 'f', '-b', str(VENDOR / 'dists.dss')], cwd=str(directory),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write(('\n\n\n\n' + name + '\n').encode()); process.stdin.close()
    process.stdin = None
    result = {'command': 'unmodified dbgen -s %d -T a -f -O f; four original dimension paths, fact named pipe' % scale,
              'segments': [], 'bytes': 0, 'rows': 0}
    try:
        while True:
            connected = kernel.ConnectNamedPipe(handle, None)
            error = ctypes.get_last_error()
            if not connected and error == 535: break
            if not connected and error not in [536, 232]: raise ctypes.WinError(error)
            if process.poll() is not None or time.perf_counter() - started > 600:
                raise RuntimeError('Stock process failed or timed out before connecting fact pipe')
            time.sleep(0.01)
        buffer = ctypes.create_string_buffer(4 * 1024 * 1024)
        count = wintypes.DWORD()
        index, remaining, hasher = 0, records[0]['raw_bytes'], hashlib.sha256()
        while True:
            ok = kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None)
            if not ok:
                if ctypes.get_last_error() == 109: break
                if ctypes.get_last_error() == 232:
                    if time.perf_counter() - started > 600:
                        raise RuntimeError('Stock named-pipe read timed out')
                    time.sleep(0.002); continue
                raise ctypes.WinError(ctypes.get_last_error())
            if not count.value: break
            block = ctypes.string_at(buffer, count.value)
            result['bytes'] += len(block); result['rows'] += block.count(b'\n')
            offset = 0
            while offset < len(block):
                if index >= len(records):
                    raise ValueError('Stock stream exceeds adapted stream')
                take = min(remaining, len(block) - offset)
                hasher.update(block[offset:offset + take]); remaining -= take; offset += take
                if remaining == 0:
                    result['segments'].append({'shard': records[index]['shard'], 'sha256': hasher.hexdigest(),
                                               'match': hasher.hexdigest() == records[index]['raw_sha256']})
                    index += 1
                    if index < len(records):
                        remaining, hasher = records[index]['raw_bytes'], hashlib.sha256()
        stdout, stderr = process.communicate(timeout=30)
        result.update(returncode=process.returncode, stdout=stdout.decode(errors='replace'),
                      stderr=stderr.decode(errors='replace'), seconds=time.perf_counter() - started)
        result['all_bytes_match'] = process.returncode == 0 and index == len(records) and all(x['match'] for x in result['segments'])
    except Exception as error:
        result['error'] = repr(error)
        raise
    finally:
        kernel.CloseHandle(handle)
        if process.poll() is None:
            process.kill()
        if 'returncode' not in result:
            stdout, stderr = process.communicate()
            result.update(returncode=process.returncode, stdout=stdout.decode(errors='replace'),
                          stderr=stderr.decode(errors='replace'), seconds=time.perf_counter() - started)
        atomic(directory / 'stock_pipe.json', result)
    if not result.get('all_bytes_match'):
        raise ValueError('Unmodified stock -T a differs from adapted chunks')
    return result


def validate_sf2():
    binding = compiled_binding()
    directory, data = OUTPUT / 'sf2_gate_v2', DATA / 'sf2_gate_v2'
    receipt = directory / 'gate.json'
    if receipt.exists():
        result = json.loads(receipt.read_text())
        if result['binding'] != binding:
            raise ValueError('SF2 gate code/input changed; retain old result and review separately')
        if result['status'] == 'PASS':
            state = json.loads((directory / 'checkpoint.json').read_text())
            restore_checkpoint(data / 'lineorder_sampled.csv', state, state['binding'], directory)
            return result
    first = stream(2, 16, SEED, '0.003333', directory, data, binding, stop_after=2)
    records_before = json.dumps(first['committed_shards'], sort_keys=True)
    sample = data / 'lineorder_sampled.csv'
    with sample.open('ab') as target:
        target.write(b'UNCOMMITTED_SF2_CRASH_TAIL\n')
    resumed = stream(2, 16, SEED, '0.003333', directory, data, binding)
    stock = stock_pipe_compare(2, resumed['committed_shards'], data / 'stock_pipe')
    dimension_files = resumed['binding']['dimensions']
    dim_match = all(digest(data / 'stock_pipe' / (name + '.tbl')) == entry['sha256'] for name, entry in dimension_files.items())
    checks = {'all_stock_bytes_match': stock['all_bytes_match'], 'stock_rows_match': stock['rows'] == resumed['rows'],
              'all_dimensions_match_stock': dim_match,
              'committed_shards_preserved': json.dumps(resumed['committed_shards'][:len(first['committed_shards'])], sort_keys=True) == records_before,
              'all_16_shards_committed': len(resumed['committed_shards']) == 16}
    result = {'status': 'PASS' if all(checks.values()) else 'FAIL', 'stage': 'SF2_FULL_STOCK_BYTE_GATE_ONLY',
              'sf500_started': False, 'binding': binding, 'checks': checks, 'fact_rows': resumed['rows'],
              'sample_rows': resumed['sample_rows'], 'sample_sha256': digest(sample), 'stock_pipe': stock,
              'dimensions': dimension_files,
              'timing': {'dimension_seconds': json.loads((data / 'dimensions/dimensions.json').read_text())['seconds'],
                         'stock_seconds': stock['seconds'], 'consumer_load_seconds': resumed['consumer_load_seconds'],
                         'generation_seconds': sum(x['generation_seconds'] for x in resumed['committed_shards']),
                         'consume_seconds': sum(x['consume_seconds'] for x in resumed['committed_shards']),
                         'chunk_total_seconds': sum(x['total_seconds'] for x in resumed['committed_shards'])},
              'max_raw_bytes': max(x['raw_bytes'] for x in resumed['committed_shards'])}
    atomic(receipt, result)
    if result['status'] != 'PASS':
        raise ValueError('SF2 byte gate failed')
    return result


def plan():
    binding = compiled_binding()
    gate_path = OUTPUT / 'sf2_gate_v2/gate.json'
    gate = json.loads(gate_path.read_text())
    if gate['status'] != 'PASS' or gate['binding'] != binding:
        raise ValueError('A matching successful SF2 stock-byte gate is required')
    with localcontext() as context:
        context.prec = 42
        probability = str(Decimal(10000000) / Decimal(REQUIRED_ROWS))
    dimensions_bytes = sum(entry['bytes'] * (500 / 2 if name in ['customer', 'supplier'] else
                          expected_dimensions(500)['part'] / expected_dimensions(2)['part'] if name == 'part' else 1)
                           for name, entry in gate['dimensions'].items())
    byte_per_row = gate['stock_pipe']['bytes'] / gate['fact_rows']
    sample_bytes = math.ceil(byte_per_row * 10000000 * 1.2)
    raw_bound = 256 * 1024 ** 2
    # One global sample, dimensions, one bounded raw shard, retained small receipts,
    # plus conservative atomic/resume reserve. Original SF1 storage is not deleted.
    estimate = math.ceil(2 * dimensions_bytes + sample_bytes + raw_bound + 512 * 1024 ** 2)
    existing_ssb = sum(p.stat().st_size for directory in [DATA, ROOT / 'output/full/ssb']
                       for p in directory.rglob('*') if p.is_file())
    if estimate + existing_ssb > 10 * GIB:
        raise ValueError('Projected SSB storage exceeds the 10 GiB budget')
    timings = gate['timing']
    extrapolated = (timings['generation_seconds'] + timings['consume_seconds']) * 250
    result = {'status': 'READY_FOR_ROOT_REVIEW', 'sf500_started': False, 'binding': binding,
              'sf2_gate_sha256': digest(gate_path), 'scale': 500, 'shards': 4000,
              'generator_orders': 750000000, 'required_fact_rows': REQUIRED_ROWS,
              'sample_seed': SEED, 'sample_probability': probability, 'expected_sample_rows': 10000000,
              'expected_dimensions': expected_dimensions(500),
              'fact_part_key_ceiling_preserved': 200000 * (math.floor(math.log(500)) + 1),
              'resources': {'estimated_dimension_bytes': math.ceil(dimensions_bytes),
                            'dimension_recovery_staging_allowance_bytes': math.ceil(dimensions_bytes),
                            'estimated_sample_bytes_with_margin': sample_bytes,
                            'hard_raw_chunk_bytes': raw_bound, 'estimated_new_bytes_with_reserve': estimate,
                            'existing_ssb_bytes': existing_ssb, 'projected_total_ssb_bytes': existing_ssb + estimate,
                            'required_free_bytes': max(6 * GIB, estimate + 2 * GIB), 'total_ssb_budget_bytes': 10 * GIB,
                            'native_ram_budget_bytes': 1536 * 1024 ** 2,
                            'expected_raw_chunk_bytes_from_sf2': math.ceil(gate['stock_pipe']['bytes'] * 250 / 4000)},
              'timing_estimate': {'measured_sf2': timings, 'sf500_linear_generation_plus_consume_seconds': extrapolated,
                                  'planning_range_seconds': [extrapolated * 0.7, extrapolated * 2],
                                  'limit': 'Small-scale linear estimate, not measured SF500; dims/startup/hash/checkpoints/shared-machine contention add time'},
              'author_truth_groups': sum(len(x) for x in author_truth().values()),
              'completion_gate': 'exact 3000028242 rows AND all 13 integer author groups equal; otherwise retain MISMATCH and do not claim recovered paper population'}
    atomic(OUTPUT / 'sf500_plan.json', result)
    return result


class RunLock:
    """OS advisory lock automatically released on crash; file is not a PID seal."""
    def __init__(self, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a+b')
    def __enter__(self):
        if self.stream.seek(0, 2) == 0:
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self
    def __exit__(self, *args):
        self.stream.close()


def execute_plan(reviewed_sha, execute=False, stop_after=None):
    stored = json.loads((OUTPUT / 'sf500_plan.json').read_text())
    require_execution(stored, reviewed_sha, execute, shutil.disk_usage(str(ROOT)).free)
    binding = compiled_binding()
    if binding != stored['binding'] or digest(OUTPUT / 'sf2_gate_v2/gate.json') != stored['sf2_gate_sha256']:
        raise ValueError('Reviewed inputs changed; refusing generation')
    directory, data = OUTPUT / 'sf500', DATA / 'sf500_paper'
    with RunLock(directory / 'run.lock'):
        state = stream(500, stored['shards'], stored['sample_seed'], stored['sample_probability'],
                       directory, data, binding, stop_after=stop_after)
        complete = state['next_shard'] == stored['shards'] + 1
        result = {'status': 'CHECKPOINTED', 'sf500_started': True, 'complete': False,
                  'plan_sha256': reviewed_sha, 'rows': state['rows'], 'sample_rows': state['sample_rows'],
                  'committed_shards': len(state['committed_shards'])}
        if complete:
            comparison = compare_truth(state['aggregates'], author_truth())
            row_match = state['rows'] == REQUIRED_ROWS
            passed = row_match and comparison['match']
            result.update(status='PASS' if passed else 'MISMATCH', complete=passed,
                          row_count_matches_author=row_match, author_truth_comparison=comparison,
                          sample_sha256=state['sample_sha256'], full_paper_reproduction_complete=False)
        atomic(ROOT / 'output/full/results/ssb_paper.json', result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'sf2-gate', 'plan', 'run'])
    parser.add_argument('--plan-sha256')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--stop-after', type=int)
    args = parser.parse_args()
    if args.action == 'setup': result = setup_sources()
    elif args.action == 'sf2-gate': result = validate_sf2()
    elif args.action == 'plan':
        result = plan()
        print(json.dumps({'plan_sha256': object_sha(result), 'resources': result['resources'],
                          'timing_estimate': result['timing_estimate']}, ensure_ascii=False))
    else: result = execute_plan(args.plan_sha256, args.execute, args.stop_after)
    print(json.dumps({k: v for k, v in result.items() if k in ['status', 'stage', 'sf500_started', 'fact_rows', 'sample_rows', 'checks', 'restored', 'verified_files']}, ensure_ascii=False))
    return 0 if result.get('status') in ['PASS', 'READY_FOR_ROOT_REVIEW', 'CHECKPOINTED'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
