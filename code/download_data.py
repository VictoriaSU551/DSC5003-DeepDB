"""Download and verify the original JOB snapshot; extract only JOB-light tables."""
import argparse
import hashlib
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://event.cwi.nl/da/job/imdb.tgz'
ARCHIVE_BYTES = 1263193115
ARCHIVE_SHA256 = '25f9d893c54f903366e0c263f88db0d429dbc2b159d4987ebc1e203242a7e988'
TABLES = ('title', 'movie_info_idx', 'movie_info', 'cast_info', 'movie_keyword', 'movie_companies')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep-archive', action='store_true')
    args = parser.parse_args()
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    manifest_path = data / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if all((data / f['path']).is_file() and sha256(data / f['path']) == f['sha256']
               for f in manifest['files']):
            print('Existing six tables match all recorded SHA256 hashes.', flush=True)
            return
    archive = data / 'imdb.tgz'
    if not archive.exists() or archive.stat().st_size != ARCHIVE_BYTES:
        subprocess.run(['curl', '--fail', '-L', '--retry', '3', '-C', '-', '-o', str(archive), URL], check=True)
    if archive.stat().st_size != ARCHIVE_BYTES:
        raise ValueError('Unexpected snapshot archive size; check upstream before using a changed dataset')
    archive_hash = sha256(archive)
    if archive_hash != ARCHIVE_SHA256:
        raise ValueError('Archive SHA256 differs from the verified JOB snapshot')
    with gzip.open(archive, 'rb') as compressed:
        while compressed.read(8 * 1024 * 1024):
            pass
    destination = data / 'imdb'
    destination.mkdir(exist_ok=True)
    found = set()
    # The full gzip stream was checked above; never trust arbitrary archive paths.
    with tarfile.open(archive, 'r|gz') as bundle:
        for member in bundle:
            name = Path(member.name).name
            if name not in {t + '.csv' for t in TABLES}:
                continue
            if not member.isfile() or name in found:
                raise ValueError('Invalid or duplicate table member: ' + member.name)
            target = destination / name
            with bundle.extractfile(member) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
            found.add(name)
            print('Extracted', name, member.size, flush=True)
    if found != {t + '.csv' for t in TABLES}:
        raise ValueError('Incomplete JOB-light dataset')
    files = [dict(path='imdb/' + t + '.csv', bytes=(destination / (t + '.csv')).stat().st_size,
                  sha256=sha256(destination / (t + '.csv'))) for t in TABLES]
    manifest = dict(source_url=URL, original_readme_url='http://homepages.cwi.nl/~boncz/job/imdb.tgz',
                    archive_sha256=archive_hash, archive_bytes=archive.stat().st_size,
                    tables=list(TABLES), files=files,
                    note='Original JOB IMDb snapshot; only the six JOB-light tables retained. No row sampling.')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if not args.keep_archive:
        archive.unlink()
    print('Verified extraction and wrote data/manifest.json.', flush=True)


if __name__ == '__main__':
    main()
