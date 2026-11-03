"""Bounded original-dbgen shards, native exact aggregation, sealed sampling.

SF500 is deliberately gated. The sf1 command verifies the entire six-million-row
reference against unmodified dbgen, an independent SQLite database, and resumed
native output consumption before any large-scale run can be considered.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'code/vendor/ssb_dbgen'
OUTPUT = ROOT / 'output/full/ssb'
DATA = ROOT / 'data/ssb'
BUILD = OUTPUT / 'build'
GCC = ROOT / '.runtime/w64devkit/bin/gcc.exe'
GPP = ROOT / '.runtime/w64devkit/bin/g++.exe'
QUERIES = ROOT / 'code/benchmarks/ssb/sql/aqp_queries.sql'
DIMENSIONS = ['customer', 'part', 'supplier', 'date']
SOURCES = ['build.c', 'driver.c', 'bm_utils.c', 'rnd.c', 'print.c', 'load_stub.c',
           'bcd2.c', 'speed_seed.c', 'text.c', 'permute.c']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def resume_sample(sample, state, binding):
    if state['binding'] != binding:
        raise ValueError('Checkpoint binding changed; refusing to truncate or resume')
    sample = Path(sample)
    offset = state['sample_bytes']
    if not sample.exists() or sample.stat().st_size < offset:
        raise ValueError('Committed sample prefix is missing or truncated')
    h = hashlib.sha256()
    with sample.open('rb') as stream:
        remaining = offset
        while remaining:
            block = stream.read(min(4 * 1024 * 1024, remaining))
            if not block:
                raise ValueError('Committed sample prefix is incomplete')
            h.update(block); remaining -= len(block)
    if h.hexdigest() != state['sample_sha256']:
        raise ValueError('Committed sample prefix checksum mismatch')
    with sample.open('r+b') as stream:
        stream.truncate(offset)
    return h


def merge_aggregates(destination, values):
    for query, groups in values.items():
        target = destination.setdefault(query, {})
        for key, value in groups.items():
            target[key] = target.get(key, 0) + int(value)


def clean_committed_raw(directory, state):
    directory = Path(directory).resolve()
    for item in state['committed_shards']:
        name = item['raw_filename']
        if Path(name).name != name:
            raise ValueError('Invalid committed raw filename')
        path = directory / name
        if path.exists():
            if digest(path) != item['raw_sha256']:
                raise ValueError('Committed raw file checksum mismatch')
            path.unlink()


def require_generation_gate(scale):
    if scale != 1:
        raise ValueError('SF500 and other non-SF1 execution remain gated; plan only')


def command(arguments, cwd, log):
    environment = dict(os.environ, PATH=str(GCC.parent) + os.pathsep + os.environ.get('PATH', ''))
    start = time.perf_counter()
    result = subprocess.run([str(x) for x in arguments], cwd=str(cwd), env=environment,
                            capture_output=True, text=True, errors='replace')
    atomic(log, {'arguments': [str(x) for x in arguments], 'cwd': str(cwd),
                 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                 'seconds': time.perf_counter() - start})
    if result.returncode:
        raise RuntimeError('Command failed; see ' + str(log))


def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    pins = json.loads((VENDOR / 'SOURCES.json').read_text())
    for name, expected in pins['files_sha256'].items():
        if digest(VENDOR / name) != expected:
            raise ValueError('Pinned upstream source changed: ' + name)
    binding = {'original_sources': pins['files_sha256'], 'consumer': digest(VENDOR / 'full_consumer.cpp'),
               'chunk_driver': digest(VENDOR / 'full_chunk_driver.c'),
               'compiler': digest(GCC), 'compile_flags_version': 3}
    executable, consumer = BUILD / 'dbgen.exe', BUILD / 'full_consumer.exe'
    chunk_driver = BUILD / 'dbgen_chunk.exe'
    receipt = BUILD / 'build.json'
    prior = None
    if receipt.exists():
        prior = json.loads(receipt.read_text())
        if (prior['binding'] == binding and executable.exists() and consumer.exists()
                and digest(executable) == prior['dbgen_sha256'] and digest(consumer) == prior['consumer_sha256']
                and chunk_driver.exists() and digest(chunk_driver) == prior.get('chunk_driver_sha256')):
            return prior
    flags = ['-O2', '-std=gnu89', '-fcommon', '-Wno-implicit-function-declaration',
             '-Wno-int-conversion', '-Wno-incompatible-pointer-types', '-DWIN32',
             '-DSSBM', '-DDB2', '-static-libgcc']
    original_keys = ['original_sources', 'compiler', 'compile_flags_version']
    if not (prior and executable.exists() and digest(executable) == prior['dbgen_sha256']
            and all(prior['binding'].get(k) == binding[k] for k in original_keys)):
        command([GCC] + flags + [VENDOR / x for x in SOURCES] + ['-o', executable, '-lm'],
                VENDOR, BUILD / 'compile_original.json')
    if not (prior and consumer.exists() and digest(consumer) == prior['consumer_sha256']
            and all(prior['binding'].get(k) == binding[k] for k in ['consumer', 'compiler'])):
        command([GPP, '-O2', '-std=c++17', '-static-libgcc', '-static-libstdc++',
                 VENDOR / 'full_consumer.cpp', '-o', consumer], VENDOR, BUILD / 'compile_consumer.json')
    command([GCC] + flags + ['-Dmain=ssb_original_main'] + [VENDOR / x for x in SOURCES]
            + [VENDOR / 'full_chunk_driver.c', '-o', chunk_driver, '-lm'], VENDOR, BUILD / 'compile_chunk_driver.json')
    result = {'status': 'PASS', 'binding': binding, 'dbgen_sha256': digest(executable),
              'consumer_sha256': digest(consumer), 'chunk_driver_sha256': digest(chunk_driver)}
    atomic(receipt, result)
    return result


def original_reference():
    directory = DATA / 'sf1_gold'
    directory.mkdir(parents=True, exist_ok=True)
    if not all((directory / (name + '.tbl')).exists() for name in DIMENSIONS + ['lineorder']):
        command([BUILD / 'dbgen.exe', '-s', '1', '-T', 'a', '-f', '-b', VENDOR / 'dists.dss'],
                directory, OUTPUT / 'sf1_original_generation.json')
    return directory


def sqlite_reference(directory):
    binding = {name: digest(directory / (name + '.tbl')) for name in DIMENSIONS + ['lineorder']}
    binding['queries'] = digest(QUERIES)
    receipt = OUTPUT / 'sf1_sqlite_reference.json'
    if receipt.exists():
        result = json.loads(receipt.read_text())
        if result['binding'] == binding and result['status'] == 'PASS':
            return result
        raise ValueError('Existing SF1 SQL reference binding changed')
    database = directory / 'independent_reference.sqlite'
    temporary = database.with_name(database.name + '.tmp')
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(str(temporary))
    connection.execute('PRAGMA journal_mode=OFF')
    connection.execute('PRAGMA synchronous=OFF')
    connection.execute('PRAGMA temp_store=MEMORY')
    schema = (ROOT / 'code/benchmarks/ssb/setup-sql/schema.sql').read_text()
    connection.executescript(schema.split('CREATE INDEX')[0])
    counts = {}
    for filename in DIMENSIONS + ['lineorder']:
        table = 'dwdate' if filename == 'date' else filename
        with (directory / (filename + '.tbl')).open(newline='') as stream:
            batch = []
            for row in csv.reader(stream, delimiter='|'):
                if row and row[-1] == '': row.pop()
                batch.append(row)
                if len(batch) == 10000:
                    connection.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' * len(row)) + ')', batch)
                    batch = []
            if batch:
                connection.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' * len(batch[0])) + ')', batch)
        counts[table] = connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
        connection.commit()
    queries = [x.strip() for x in QUERIES.read_text().splitlines() if x.strip()]
    truth = {}
    for query, sql in enumerate(queries):
        rows = connection.execute(sql).fetchall()
        truth[str(query)] = {'\t'.join(str(x) for x in row[:-1]): int(row[-1]) for row in rows if row[-1] is not None}
    connection.close()
    os.replace(str(temporary), str(database))
    result = {'status': 'PASS', 'binding': binding, 'table_rows': counts, 'queries': len(queries),
              'aggregates': truth, 'database': str(database.relative_to(ROOT)),
              'database_sha256': digest(database), 'method': 'Independent original SQL against full SF1 SQLite tables'}
    atomic(receipt, result)
    return result


def read_aggregates(path):
    result = {str(i): {} for i in range(13)}
    for line in Path(path).read_text().splitlines():
        fields = line.split('\t')
        result[fields[0]]['\t'.join(fields[1:-1])] = int(fields[-1])
    return result


class Consumer:
    def __init__(self, dimensions):
        self.error_log = (OUTPUT / 'consumer_stderr.log').open('a', encoding='utf-8')
        self.process = subprocess.Popen([str(BUILD / 'full_consumer.exe'), str(dimensions)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
                                        text=True, bufsize=1)
        if self.process.stdout.readline().strip() != 'READY':
            raise RuntimeError('Native dimension loading failed')

    def consume(self, raw, output, seed, probability):
        output = Path(output); output.mkdir(parents=True, exist_ok=True)
        self.process.stdin.write('\t'.join([str(raw), str(output), str(seed), str(probability)]) + '\n')
        self.process.stdin.flush()
        reply = self.process.stdout.readline().strip()
        if reply != 'OK':
            raise RuntimeError('Native consumer failed: ' + reply)
        return json.loads((output / 'stats.json').read_text())

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('QUIT\n'); self.process.stdin.flush()
            self.process.wait(timeout=10)
        self.error_log.close()


def generate_raw_shard(work, scale, shards, shard):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    command([BUILD / 'dbgen_chunk.exe', str(scale), str(shards), str(shard), VENDOR / 'dists.dss'], work,
            OUTPUT / ('generate_shard_%04d.json' % shard))
    return work / ('lineorder.tbl.%d' % shard)


def stream(scale=1, shards=8, seed=20261030, probability='0.003333', stop_after=None):
    require_generation_gate(scale)
    if shards < 1 or shards > 10000 or not (0 <= float(probability) <= 1):
        raise ValueError('Invalid shard count or sampling probability')
    compiled = build()
    dimensions = original_reference()
    directory = DATA / 'sf1_stream'
    directory.mkdir(parents=True, exist_ok=True)
    sample = directory / 'lineorder_sampled.csv'
    checkpoint = OUTPUT / 'sf1_stream_checkpoint.json'
    binding = {'scale': scale, 'shards': shards, 'sampling_seed': seed, 'sample_probability': probability,
               'build': compiled, 'runner_sha256': digest(Path(__file__).resolve()), 'queries': digest(QUERIES),
               'dimensions': {name: digest(dimensions / (name + '.tbl')) for name in DIMENSIONS},
               'reference_population_sha256': digest(dimensions / 'lineorder.tbl'),
               'generator_seed_policy': 'Unmodified fixed rnd.h streams; -S is shard number, not RNG seed'}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        h = resume_sample(sample, state, binding)
        for item in state['committed_shards']:
            for path, expected in item['retained_files_sha256'].items():
                if digest(ROOT / path) != expected:
                    raise ValueError('Committed shard receipt changed: ' + path)
        clean_committed_raw(directory / 'bounded_work', state)
    else:
        if sample.exists() and sample.stat().st_size:
            raise ValueError('Sample exists without checkpoint; refusing to overwrite')
        sample.touch(); h = hashlib.sha256()
        state = {'binding': binding, 'next_shard': 1, 'sample_bytes': 0,
                 'sample_sha256': h.hexdigest(), 'rows': 0, 'sample_rows': 0,
                 'reference_bytes': 0, 'aggregates': {str(i): {} for i in range(13)}, 'committed_shards': []}
        atomic(checkpoint, state)
    if state['next_shard'] > shards:
        return state
    consumer = Consumer(dimensions)
    try:
        new_shards = 0
        for shard in range(state['next_shard'], shards + 1):
            work = directory / 'bounded_work'
            work.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(str(directory)).free < 2 * 1024 ** 3:
                raise ValueError('Insufficient reserved free disk space')
            generate_raw_shard(work, scale, shards, shard)
            raw_files = list(work.glob('lineorder.tbl*'))
            if len(raw_files) != 1:
                raise ValueError('Expected one bounded fact shard')
            raw = raw_files[0]
            raw_sha = digest(raw)
            with (dimensions / 'lineorder.tbl').open('rb') as reference:
                reference.seek(state['reference_bytes'])
                remaining, reference_hash = raw.stat().st_size, hashlib.sha256()
                while remaining:
                    block = reference.read(min(4 * 1024 * 1024, remaining))
                    if not block: raise ValueError('Shard exceeds full SF1 reference')
                    reference_hash.update(block); remaining -= len(block)
            if reference_hash.hexdigest() != raw_sha:
                raise ValueError('Sharded generation differs from original full SF1 byte stream')
            chunk = OUTPUT / 'shards' / ('%04d' % shard)
            stats = consumer.consume(raw, chunk, seed, probability)
            values = read_aggregates(chunk / 'aggregates.tsv')
            with sample.open('ab') as target, (chunk / 'sample.csv').open('rb') as source:
                for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                    target.write(block); h.update(block)
                target.flush(); os.fsync(target.fileno())
            merge_aggregates(state['aggregates'], values)
            state['rows'] += stats['rows']; state['sample_rows'] += stats['sample_rows']
            state['reference_bytes'] += raw.stat().st_size
            state['sample_bytes'] = sample.stat().st_size; state['sample_sha256'] = h.hexdigest()
            item = {'shard': shard, 'raw_filename': raw.name, 'population_rows': stats['rows'], 'raw_bytes': raw.stat().st_size,
                    'raw_sha256': raw_sha, 'retained_files_sha256': {
                        p.relative_to(ROOT).as_posix(): digest(p) for p in [chunk / 'aggregates.tsv', chunk / 'stats.json', chunk / 'sample.csv']}}
            state['committed_shards'].append(item); state['next_shard'] = shard + 1
            atomic(checkpoint, state)
            raw.unlink()  # Exactly the verified bounded file under this run's workspace.
            new_shards += 1
            if stop_after is not None and new_shards >= stop_after:
                break
    finally:
        consumer.close()
    return state


def verify_sf1(shards=8):
    build(); dimensions = original_reference(); reference = sqlite_reference(dimensions)
    first = stream(shards=shards, stop_after=2)
    committed_before = json.dumps(first['committed_shards'], sort_keys=True)
    sample = DATA / 'sf1_stream/lineorder_sampled.csv'
    with sample.open('ab') as target:
        target.write(b'UNCOMMITTED_CRASH_TAIL\n')
    resumed = stream(shards=shards)
    preserved = json.dumps(resumed['committed_shards'][:len(first['committed_shards'])], sort_keys=True) == committed_before
    whole = OUTPUT / 'sf1_continuous_native'
    consumer = Consumer(dimensions)
    try:
        stats = consumer.consume(dimensions / 'lineorder.tbl', whole, 20261030, '0.003333')
    finally:
        consumer.close()
    continuous = read_aggregates(whole / 'aggregates.tsv')
    checks = {'all_13_integer_aggregates_match_independent_sql': resumed['aggregates'] == reference['aggregates'],
              'continuous_native_matches_independent_sql': continuous == reference['aggregates'],
              'interrupted_resumed_sample_matches_continuous': digest(sample) == digest(whole / 'sample.csv'),
              'committed_shards_preserved': preserved,
              'all_reference_bytes_covered': resumed['reference_bytes'] == (dimensions / 'lineorder.tbl').stat().st_size,
              'all_reference_rows_covered': resumed['rows'] == reference['table_rows']['lineorder'] == stats['rows'],
              'sample_rows_agree': resumed['sample_rows'] == stats['sample_rows']}
    result = {'status': 'PASS' if all(checks.values()) else 'FAIL', 'stage': 'SF1_STREAMING_VALIDATED_ONLY',
              'sf500_started': False, 'full_paper_reproduction_complete': False,
              'source': json.loads((VENDOR / 'SOURCES.json').read_text()), 'checks': checks,
              'sf1_fact_rows': resumed['rows'], 'sf1_sample_rows': resumed['sample_rows'],
              'reference_sql': reference, 'stream_checkpoint': str((OUTPUT / 'sf1_stream_checkpoint.json').relative_to(ROOT)),
              'sample_sha256': digest(sample), 'future_sf500_required_rows': 3000028242,
              'sf500_gate': 'CLOSED; exact row count, 13 author truth groups and resources must be audited separately'}
    atomic(ROOT / 'output/full/results/ssb_sources.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'sf1', 'plan'])
    parser.add_argument('--shards', type=int, default=8)
    args = parser.parse_args()
    if args.action == 'build': result = build()
    elif args.action == 'sf1': result = verify_sf1(args.shards)
    else:
        result = {'sf500_gate': 'CLOSED', 'future_rows_required': 3000028242,
                  'future_shards_suggestion': 4000, 'raw_shard_estimate_bytes': 100000000,
                  'sampling_probability': '0.003333', 'expected_sample_rows': 9999094.130586,
                  'missing': 'Generalize post-SF1 runner gate, compare author 13-query truth and exact population identity; no SF500 run authorized in this stage'}
    print(json.dumps({k: v for k, v in result.items() if k in ['status','stage','sf1_fact_rows','sf1_sample_rows','checks','sf500_gate']}, ensure_ascii=False))
    return 0 if result.get('status', 'PASS') == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
