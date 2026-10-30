"""Acquire and seal IDEBench source inputs; never generate or train Flights 1B."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
import ntpath
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
COMMIT = '67339d9b81d0bcbb7b41ce6dc2e55918cf1c498f'
BASE_URL = 'https://raw.githubusercontent.com/IDEBench/IDEBench-public/' + COMMIT + '/'
ARCHIVE_BYTES = 78000681
ARCHIVE_BLOB = 'e8073ce07ea81db6df3e83c281c12beab2c416db'
SOURCE_PINS = {
    'datagen.py': (10368, '34d8a0945cc727529aabe203990014c6199284b3'),
    'LICENSE': (1055, '7100166aa29929163269787d01754bffb35bb369'),
    'README.md': (1029, '1a786236b73e8d44f602bc8be0ffc7c030840275'),
}
REQUIRED = ('flights/sample.csv', 'flights/sample.json')
MEMBER_PINS = {
    'flights/sample.csv': (327292943, '971900ce'),
    'flights/sample.json': (2835, '8946b66a'),
}
COLUMNS = ('YEAR_DATE', 'UNIQUE_CARRIER', 'ORIGIN', 'ORIGIN_STATE_ABR',
           'DEST', 'DEST_STATE_ABR', 'DEP_DELAY', 'TAXI_OUT', 'TAXI_IN',
           'ARR_DELAY', 'AIR_TIME', 'DISTANCE')
CHUNK = 1024 * 1024
LOGGER = logging.getLogger('full_aqp_data')


class DataError(ValueError):
    """An input, archive, or previously extracted cache failed verification."""


def fingerprints(path):
    path = Path(path)
    size = path.stat().st_size
    sha256 = hashlib.sha256()
    git_blob = hashlib.sha1(('blob %d\0' % size).encode('ascii'))
    with path.open('rb') as source:
        for block in iter(lambda: source.read(CHUNK), b''):
            sha256.update(block)
            git_blob.update(block)
    return {'bytes': size, 'sha256': sha256.hexdigest(),
            'git_blob_sha1': git_blob.hexdigest()}


def require_pins(path, size=None, git_blob=None):
    info = fingerprints(path)
    if size is not None and info['bytes'] != size:
        raise DataError('Unexpected source size: %s' % path)
    if git_blob is not None and info['git_blob_sha1'] != git_blob:
        raise DataError('Git blob differs from pinned upstream tree: %s' % path)
    return info


def ensure_download(url, path, size, git_blob, offline=False):
    """Reuse only a byte-identical pinned file; resume an unfinished download."""
    path = Path(path)
    if path.exists():
        info = require_pins(path, size, git_blob)
        LOGGER.info('Verified pinned cached source %s sha256=%s', path, info['sha256'])
        return info
    if offline:
        raise DataError('Missing pinned source in --verify-only mode: %s' % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.part')
    if partial.exists() and partial.stat().st_size > size:
        raise DataError('Download partial exceeds expected source size: %s' % partial)
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == size:
            break
        headers = {'User-Agent': 'DeepDB-reproduction-input-verifier',
                   'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = 'bytes=%d-' % offset
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                if response.status == 206:
                    prefix = 'bytes %d-' % offset
                    if not response.headers.get('Content-Range', '').startswith(prefix):
                        raise DataError('Unexpected download Content-Range')
                elif response.status == 200:
                    offset = 0  # Server ignored Range; safely restart the partial.
                else:
                    raise DataError('Unexpected HTTP status: %s' % response.status)
                LOGGER.info('Downloading %s at offset %d (attempt %d)', url, offset, attempt + 1)
                with partial.open('ab' if offset else 'wb') as target:
                    current = offset
                    progress = current // (16 * CHUNK)
                    for block in iter(lambda: response.read(CHUNK), b''):
                        current += len(block)
                        if current > size:
                            raise DataError('Download exceeds pinned source size: %s' % url)
                        target.write(block)
                        if current // (16 * CHUNK) != progress:
                            progress = current // (16 * CHUNK)
                            LOGGER.info('Download progress %s: %d/%d bytes', path.name, current, size)
                    target.flush()
                    os.fsync(target.fileno())
        except (urllib.error.URLError, OSError) as exc:
            LOGGER.warning('Download attempt %d failed: %s', attempt + 1, exc)
            if attempt == 2:
                raise
    if not partial.exists() or partial.stat().st_size != size:
        raise DataError('Incomplete download: %s' % path)
    info = require_pins(partial, size, git_blob)
    os.replace(str(partial), str(path))
    LOGGER.info('Downloaded and pinned %s sha256=%s', path, info['sha256'])
    return info


def safe_member_name(info):
    name = info.filename.replace('\\', '/')
    parts = PurePosixPath(name).parts
    if (not parts or name.startswith('/') or ntpath.splitdrive(name)[0]
            or '..' in parts or any(':' in p or p.endswith((' ', '.')) for p in parts)
            or stat.S_ISLNK(info.external_attr >> 16)):
        raise DataError('Unsafe ZIP member: %s' % info.filename)
    return name.rstrip('/')


def prepare_archive(archive, destination, expected_size=None,
                    expected_git_blob=None, expected_members=None):
    """Check every member CRC before extracting the two required regular files."""
    archive, destination = Path(archive), Path(destination)
    archive_info = require_pins(archive, expected_size, expected_git_blob)
    selected = {}
    verified = {}
    try:
        with zipfile.ZipFile(str(archive)) as bundle:
            members = bundle.infolist()
            seen = set()
            if sum(info.file_size for info in members) > 512 * 1024 * 1024:
                raise DataError('ZIP expansion exceeds source-input budget')
            for info in members:
                name = safe_member_name(info)
                if name.casefold() in seen:
                    raise DataError('Unsafe duplicate ZIP member: %s' % info.filename)
                seen.add(name.casefold())
                if name in REQUIRED:
                    if info.is_dir():
                        raise DataError('Missing required regular input: %s' % name)
                    selected[name] = info
            if set(selected) != set(REQUIRED):
                raise DataError('Missing required ZIP inputs: %s' % sorted(set(REQUIRED) - set(selected)))
            if expected_members:
                for name, (size, crc) in expected_members.items():
                    info = selected[name]
                    if info.file_size != size or '%08x' % info.CRC != crc:
                        raise DataError('Pinned ZIP member size/CRC metadata mismatch: %s' % name)
            for info in members:
                if info.is_dir():
                    continue
                digest = hashlib.sha256()
                with bundle.open(info) as source:
                    for block in iter(lambda: source.read(CHUNK), b''):
                        if info.filename in REQUIRED:
                            digest.update(block)
                if info.filename in REQUIRED:
                    verified[info.filename] = {'bytes': info.file_size,
                                               'sha256': digest.hexdigest(),
                                               'crc32': '%08x' % info.CRC,
                                               'archive_member': info.filename}
            # Validate all existing targets first. A changed file must not be
            # silently overwritten or mistaken for a successful cache hit.
            cached = True
            for name in REQUIRED:
                target = destination / PurePosixPath(name).name
                try:
                    target.resolve().relative_to(destination.resolve())
                except ValueError:
                    raise DataError('Unsafe extraction target: %s' % target)
                if target.exists():
                    if not target.is_file() or fingerprints(target)['sha256'] != verified[name]['sha256']:
                        raise DataError('Cache hash mismatch; extracted input was tampered: %s' % target)
                else:
                    cached = False
            destination.mkdir(parents=True, exist_ok=True)
            for name in REQUIRED:
                target = destination / PurePosixPath(name).name
                if target.exists():
                    continue
                partial = target.with_name(target.name + '.part')
                try:
                    with bundle.open(selected[name]) as source, partial.open('wb') as output:
                        shutil.copyfileobj(source, output, CHUNK)
                    if fingerprints(partial)['sha256'] != verified[name]['sha256']:
                        raise DataError('Extraction hash mismatch: %s' % name)
                    os.replace(str(partial), str(target))
                finally:
                    if partial.exists():
                        partial.unlink()
            return {'archive': archive_info, 'zip_entries': len(members),
                    'all_zip_crcs_verified': True, 'extraction_cached': cached,
                    'files': [dict(verified[name], filename=PurePosixPath(name).name)
                              for name in REQUIRED]}
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise DataError('ZIP integrity/CRC verification failed: %s' % exc)


def summarize_inputs(destination):
    destination = Path(destination)
    descriptor = json.loads((destination / 'sample.json').read_text(encoding='utf-8'))
    fields = descriptor.get('tables', {}).get('fact', {}).get('fields', [])
    if [item.get('field') for item in fields] != list(COLUMNS):
        raise DataError('Descriptor columns do not match the pinned Flights schema')
    years = {}
    rows = 0
    with (destination / 'sample.csv').open('r', encoding='utf-8', newline='') as source:
        reader = csv.reader(source)
        header = next(reader, [])
        if header != list(COLUMNS):
            raise DataError('CSV columns do not match the pinned Flights schema')
        for row in reader:
            if not row:  # The upstream CSV contains CR/CR/LF separators.
                continue
            if len(row) != len(COLUMNS):
                raise DataError('Wrong CSV column count at data row %d' % (rows + 1))
            try:
                year = int(row[0])
            except ValueError:
                raise DataError('Invalid YEAR_DATE at data row %d' % (rows + 1))
            years[year] = years.get(year, 0) + 1
            rows += 1
    if not rows:
        raise DataError('Empty Flights source sample')
    return {'rows': rows, 'columns': list(COLUMNS), 'year_min': min(years),
            'year_max': max(years),
            'year_counts': {str(year): years[year] for year in sorted(years)},
            'descriptor_fact_table': descriptor['tables']['fact'].get('name'),
            'quantitative_columns': [item['field'] for item in fields
                                     if item.get('type') == 'quantitative']}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.tmp')
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(str(partial), str(path))


def project_relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true',
                        help='Verify existing archive, vendor sources, extracted hashes and CSV; no network')
    args = parser.parse_args()
    receipt_path = ROOT / 'output/full/results/aqp_sources.json'
    log_path = ROOT / 'output/full/logs/aqp_download.log'
    archive = ROOT / ('data/downloads/idebench-flights-' + COMMIT[:12] + '.zip')
    destination = ROOT / 'data/flights'
    vendor = ROOT / 'code/vendor/idebench'
    for path in (receipt_path, log_path, archive, destination, vendor):
        project_relative(path)  # Refuse project paths redirected outside this checkout.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(log_path), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    LOGGER.info('Starting input-only verification; verify_only=%s', args.verify_only)
    try:
        source_records = []
        for name, (size, git_blob) in SOURCE_PINS.items():
            target = vendor / name
            record = ensure_download(BASE_URL + name, target, size, git_blob, args.verify_only)
            source_records.append(dict(record, path=project_relative(target), source_url=BASE_URL + name))
        vendor_record = {'upstream_repository': 'https://github.com/IDEBench/IDEBench-public',
                         'upstream_commit': COMMIT, 'files': source_records,
                         'upstream_files_unmodified': True, 'generator_executed': False,
                         'note': 'datagen.py is self-contained; sample.json is the input descriptor. '
                                 'NumPy/Pandas/SciPy dependencies were not installed or changed.'}
        atomic_json(vendor / 'SOURCES.json', vendor_record)
        archive_record = ensure_download(BASE_URL + 'data/flights.zip', archive,
                                         ARCHIVE_BYTES, ARCHIVE_BLOB, args.verify_only)
        prepared = prepare_archive(archive, destination, ARCHIVE_BYTES, ARCHIVE_BLOB, MEMBER_PINS)
        summary = summarize_inputs(destination)
        for info in prepared['files']:
            info['path'] = project_relative(destination / info['filename'])
        receipt = {'schema_version': 1, 'status': 'PASS',
                   'stage': 'AQP_SOURCE_INPUTS_VERIFIED_ONLY',
                   'verified_utc': datetime.now(timezone.utc).isoformat(),
                   'upstream_commit': COMMIT,
                   'archive': dict(archive_record, path=project_relative(archive),
                                   source_url=BASE_URL + 'data/flights.zip',
                                   zip_entries=prepared['zip_entries'], all_zip_crcs_verified=True),
                   'files': prepared['files'], 'source_sample': summary,
                   'vendor_sources': source_records,
                   'generator_defaults': {'random_seed': 41001, 'batch_size': 100000,
                                          'input_sample_limit': 5000000,
                                          'quantitative_minimum_shift': True,
                                          'paper_authors_generation_seed_confirmed': False},
                   'generation_1b_executed': False, 'training_executed': False,
                   'extraction_cached': prepared['extraction_cached'],
                   'not_completed': ['Flights 1B population generation and independent ground truth',
                                     'Flights 10M model training and Figure 9/11/13 evaluations',
                                     'SSB SF500 generation, 1M/10M training and independent ground truth',
                                     'VerdictDB, TABLESAMPLE, XDB/WanderJoin, DBEst and wavelet reruns'],
                   'note': 'This is the IDEBench generator input sample, not a generated 1B population '
                           'or a recovered DeepDB authors training sample.'}
        atomic_json(receipt_path, receipt)
        LOGGER.info('PASS input sources only: rows=%d years=%d..%d archive_sha256=%s cached=%s',
                    summary['rows'], summary['year_min'], summary['year_max'],
                    archive_record['sha256'], prepared['extraction_cached'])
        print(json.dumps({'status': receipt['status'], 'stage': receipt['stage'],
                          'rows': summary['rows'], 'years': [summary['year_min'], summary['year_max']],
                          'archive_sha256': archive_record['sha256'],
                          'extraction_cached': prepared['extraction_cached']}))
        return 0
    except Exception as exc:
        LOGGER.exception('FAIL AQP input verification')
        atomic_json(receipt_path, {'schema_version': 1, 'status': 'FAIL',
                                  'stage': 'AQP_SOURCE_INPUTS_VERIFIED_ONLY',
                                  'verified_utc': datetime.now(timezone.utc).isoformat(),
                                  'error': str(exc), 'generation_1b_executed': False,
                                  'training_executed': False})
        print('AQP input verification failed: %s' % exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
