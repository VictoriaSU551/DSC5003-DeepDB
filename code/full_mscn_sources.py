"""Acquire the pinned original MSCN source/data archive without overwriting files.

This fills the fresh-clone bootstrap step. The original audit/training modules
remain unchanged, and existing byte-identical sources/data keep their mtimes.
"""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import urllib.request
import zipfile

import full_mscn as original


def destination_for(name, root):
    relative = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or relative.is_absolute()
            or any(part in ['', '.', '..'] for part in name.split('/'))):
        raise ValueError('unsafe MSCN archive member')
    base = 'data/mscn' if name.startswith(('data/', 'workloads/')) else 'code/vendor/mscn'
    return Path(root) / base / relative


def install_member(destination, content):
    destination = Path(destination)
    if destination.exists():
        if original.sha256(destination) != hashlib.sha256(content).hexdigest():
            raise ValueError('existing source/data differs; preserved without overwrite: ' + str(destination))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.download.tmp')
    temporary.write_bytes(content)
    os.replace(str(temporary), str(destination))


def acquire(offline=False):
    root = original.ROOT
    archive = root / original.ARCHIVE
    if not archive.exists():
        if offline:
            raise ValueError('pinned source archive is missing in offline mode')
        archive.parent.mkdir(parents=True, exist_ok=True)
        partial = archive.with_name(archive.name + '.download.tmp')
        url = 'https://codeload.github.com/andreaskipf/learnedcardinalities/zip/' + original.COMMIT
        with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as stream:
            shutil.copyfileobj(response, stream, 1024 * 1024)
        if original.sha256(partial) != original.ARCHIVE_SHA256:
            raise ValueError('download differs from pinned official archive; not extracted')
        os.replace(str(partial), str(archive))
    if original.sha256(archive) != original.ARCHIVE_SHA256:
        raise ValueError('existing official archive differs; preserved without extraction')
    prefix = 'learnedcardinalities-' + original.COMMIT + '/'
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if member.is_dir():
                continue
            if not member.filename.startswith(prefix):
                raise ValueError('unexpected archive member prefix')
            destination = destination_for(member.filename[len(prefix):], root)
            install_member(destination, source.read(member))
    result = original.audit_inputs(root)
    original.atomic_json(root / 'output/full/results/mscn_bootstrap_source_audit.json', result)
    print('MSCN_PINNED_SOURCES_READY', result['train']['queries'], result['job_light']['queries'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    acquire(args.offline)


if __name__ == '__main__':
    main()
