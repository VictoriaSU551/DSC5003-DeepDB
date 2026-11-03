"""Acquire and independently seal official AQP sources; never runs a baseline."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib import metadata
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/downloads/baselines'
RESULT = ROOT / 'output/full/results/baseline_sources.json'
SOURCES = {
    'dbpy': {'repo': 'qingzma/DBEstPy', 'commit': '2220a937b5eef358eb42a715da328915048b7250',
             'branch': 'v2.0', 'license_files': ['LICENSE'], 'license': 'BSD-2-Clause'},
    'dbclient': {'repo': 'qingzma/DBEstClient', 'commit': '684cc9f5b84e751c7eeb7836e9d21c90638563b4',
                 'branch': 'master (2019 original DBEst)', 'license_files': ['LICENSE'], 'license': 'BSD-2-Clause text; setup classifier incorrectly says MIT'},
    'verdict18': {'repo': 'verdict-project/verdict', 'commit': 'b59209f626d278687ea0a801295b41064c7fecbb',
                  'branch': 'sigmod18', 'license_files': ['LICENSE', '3RDPARTY_LICENSE'], 'license': 'Apache-2.0 plus retained third-party notices'},
    'xdb16': {'repo': 'InitialDLab/XDB', 'commit': '8e9dc8c35b0792c01fe477232a0837a9eb70d32c',
              'branch': 'sigmod16_stable', 'license_files': ['COPYRIGHT', 'postgresql.COPYRIGHT'],
              'license': 'COPYRIGHT custom permissive grant; PostgreSQL inherited notice; README noncommercial wording differs'},
    'qreg': {'repo': 'qingzma/qreg', 'commit': '50b5963f027beb747eac99080ae77ac11e7c6716',
             'branch': 'master (2020 dependency candidate, not original environment lock)',
             'license_files': ['LICENSE'], 'license': 'Apache-2.0'}
}
CURRENT_FILES = {
    'verdict21': ('verdict-project/verdict', '48533d410cbbc91dc2ce41506edde9e04004c6b8', ['README.md', 'LICENSE', 'pom.xml']),
    'dbclient_demo': ('qingzma/DBEstClient', '3c89bbc6f729b9d6bfaa969fb5c18134804acd50', ['README.md', 'LICENSE', 'setup.py'])
}
UPSTREAM_DEEPDB = '655ada13a043a4226a239b0c0a65bcdefef87a02'


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def acquire(url, path, fetch, cap=128 * 1024 ** 2):
    path = Path(path)
    if path.exists():
        return path.read_bytes()
    if not fetch:
        raise ValueError('Missing sealed input; run fetch: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.download.tmp')
    size = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'DeepDB-official-source-audit'})
    with urllib.request.urlopen(request, timeout=60) as source, temporary.open('wb') as target:
        while True:
            block = source.read(1024 * 1024)
            if not block: break
            size += len(block)
            if size > cap: raise ValueError('Source download exceeded its bounded cap')
            target.write(block)
        target.flush(); os.fsync(target.fileno())
    os.replace(str(temporary), str(path))
    return path.read_bytes()


def validate_archive(content, expected):
    result = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(x.file_size for x in archive.infolist()) > 256 * 1024 ** 2:
            raise ValueError('Uncompressed source cap exceeded')
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename:
                raise ValueError('Unsafe source archive path')
            if item.is_dir(): continue
            if len(name.parts) < 2: raise ValueError('Missing fixed archive prefix')
            path = '/'.join(name.parts[1:])
            if path in result or path not in expected: raise ValueError('Unexpected or duplicate source member')
            raw = archive.read(item)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if blob != expected[path]['sha'] or len(raw) != expected[path]['size']:
                raise ValueError('Git blob mismatch: ' + path)
            result[path] = raw
    if set(result) != set(expected): raise ValueError('Source archive file set changed')
    return result


def evidence_files(key, files):
    common = ['README.md', 'README.rst', 'LICENSE', '3RDPARTY_LICENSE', 'COPYRIGHT', 'postgresql.COPYRIGHT',
              'requirements.txt', 'setup.py', 'pom.xml', 'INSTALL']
    selected = set(name for name in common if name in files)
    if key in ['dbpy', 'dbclient', 'qreg']:
        selected.update(name for name in files if name.endswith('.py'))
    elif key == 'verdict18':
        selected.update(name for name in files if (name.endswith('.java') and any(s in name for s in
            ['CreateSample', 'SampleParam', 'VerdictConf', 'Dbms', 'SampleSize', 'ApproxAggregatedRelation']))
            or name.endswith('.g4') or name == 'conf/verdict.properties.template')
    elif key == 'xdb16':
        selected.update(name for name in files if name.startswith('queries/') or name in [
            'src/backend/executor/nodeOnline.c', 'src/backend/optimizer/plan/planonline.c',
            'src/backend/utils/adt/onlineagg_numeric.c', 'src/tools/msvc/README'])
    return sorted(selected)


def seal_source(pair, fetch):
    key, source = pair
    directory = BASE / key
    tree_url = 'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1'.format(**source)
    tree = json.loads(acquire(tree_url, directory / 'tree.json', fetch, 8 * 1024 ** 2))
    if tree.get('truncated'): raise ValueError('Truncated authoritative Git tree')
    expected = {i['path']: i for i in tree['tree'] if i['type'] == 'blob'}
    archive_url = 'https://codeload.github.com/{repo}/zip/{commit}'.format(**source)
    archive_path = directory / (source['commit'] + '.zip')
    archive = acquire(archive_url, archive_path, fetch)
    files = validate_archive(archive, expected)
    records = {}
    # Flatten evidence paths to avoid the Windows MAX_PATH trap. Source paths and
    # exact bytes are retained by this index and the complete pinned archive.
    for index, name in enumerate(evidence_files(key, files)):
        target = directory / 'evidence' / ('%04d' % index + PurePosixPath(name).suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = files[name]
        if target.exists() and target.read_bytes() != raw: raise ValueError('Existing evidence changed: ' + str(target))
        if not target.exists(): target.write_bytes(raw)
        records[name] = {'path': target.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'url': 'https://github.com/{repo}/blob/{commit}/{path}'.format(path=name, **source)}
    license_seals = {name: hashlib.sha256(files[name]).hexdigest() for name in source['license_files']}
    result = dict(source, archive_url=archive_url, archive_path=archive_path.relative_to(ROOT).as_posix(),
                  archive_sha256=hashlib.sha256(archive).hexdigest(), archive_bytes=len(archive),
                  full_uncompressed_bytes=sum(len(x) for x in files.values()), verified_git_blobs=len(files),
                  extensions=dict(Counter(PurePosixPath(name).suffix or '[none]' for name in files)),
                  license_sha256=license_seals, evidence=records, baseline_executed=False)
    previous = directory / 'seal.json'
    if previous.exists() and json.loads(previous.read_text()) != result:
        raise ValueError('Existing official source seal changed: ' + key)
    atomic(previous, result)
    return key, result


def seal_current(pair, fetch):
    key, (repo, commit, paths) = pair
    records = {}
    for name in paths:
        url = 'https://raw.githubusercontent.com/' + repo + '/' + commit + '/' + name
        target = BASE / key / name
        content = acquire(url, target, fetch, 1024 ** 2)
        records[name] = {'url': url, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
                         'path': target.relative_to(ROOT).as_posix()}
    result = {'repo': repo, 'commit': commit, 'selected_files_only': True, 'files': records}
    seal = BASE / key / 'seal.json'
    if seal.exists() and json.loads(seal.read_text()) != result: raise ValueError('Current-source evidence changed')
    atomic(seal, result)
    return key, result


def deepdb_resources():
    result = {}
    for name, expected_lines in [('dbest_flights_aqp_queries.sql', 12), ('dbest_ssb_aqp_queries.sql', 13)]:
        source = 'baselines/aqp/resources/' + name
        content = subprocess.run(['git', '-C', str(ROOT), 'show', UPSTREAM_DEEPDB + ':' + source],
                                 capture_output=True, check=True).stdout
        lines = [line for line in content.splitlines() if line.strip()]
        if len(lines) != expected_lines: raise ValueError('Original DBEst prefilter SQL changed')
        target = BASE / 'deepdb_resources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content: raise ValueError('Original SQL resource changed')
        if not target.exists(): target.write_bytes(content)
        result[name] = {'lines': len(lines), 'sha256': hashlib.sha256(content).hexdigest(),
                        'local_path': target.relative_to(ROOT).as_posix(),
                        'url': 'https://github.com/DataManagementLab/deepdb-public/blob/' + UPSTREAM_DEEPDB + '/' + source,
                        'role': 'Categorical prefilter/join materialization SQL, not baseline implementation or measured results'}
    return result


def environment_snapshot():
    packages = {}
    for name in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'matplotlib', 'xgboost', 'qregpy', 'sqlparse', 'pyhs2', 'pwlf']:
        try: packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError: packages[name] = None
    portable = ROOT / '.runtime/w64devkit/bin'
    return {'packages': packages, 'executables_on_path': {name: shutil.which(name) for name in ['java', 'javac', 'mvn', 'make', 'perl']},
            'portable_build_tools': {name: (portable / name).is_file() for name in ['gcc.exe', 'make.exe', 'sh.exe', 'perl.exe', 'bison.exe', 'flex.exe']},
            'free_disk_bytes_at_audit': shutil.disk_usage(str(ROOT)).free,
            'ssb_standard_schema_numeric_payload_lower_bound_bytes': 64 * 3000028242,
            'lower_bound_excludes': 'all tuple/page headers, variable fields, dimensions, indexes, sort/temp and staging'}


def release_metadata(fetch):
    urls = {'dbestclient_pypi': 'https://pypi.org/pypi/dbestclient/json',
            'verdictdb_maven': 'https://repo.maven.apache.org/maven2/org/verdictdb/verdictdb-core/maven-metadata.xml'}
    result = {}
    for name, url in urls.items():
        extension = '.json' if name.endswith('pypi') else '.xml'
        path = BASE / 'release_metadata' / (name + extension)
        content = acquire(url, path, fetch, 1024 * 1024)
        result[name] = {'url': url, 'local_path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(content).hexdigest()}
    return result


def inspect_old_wheel(fetch):
    catalog = json.loads((BASE / 'release_metadata/dbestclient_pypi.json').read_text())
    item = next(x for x in catalog['releases']['1.2'] if x['filename'].endswith('.whl'))
    path = BASE / 'release_metadata' / item['filename']
    content = acquire(item['url'], path, fetch, 1024 * 1024)
    if hashlib.sha256(content).hexdigest() != item['digests']['sha256']:
        raise ValueError('Official DBEst 1.2 wheel digest mismatch')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
    return {'version': '1.2', 'url': item['url'], 'bytes': len(content), 'sha256': item['digests']['sha256'],
            'files': names, 'contains_cli_prompt': 'dbestclient/cli/prompt.py' in names,
            'contains_queryengine': 'dbestclient/executor/queryengine.py' in names,
            'installed_or_imported': False}


def audit(fetch=False):
    BASE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = dict(pool.map(lambda pair: seal_source(pair, fetch), SOURCES.items()))
        current = dict(pool.map(lambda pair: seal_current(pair, fetch), CURRENT_FILES.items()))
    result = {'status': 'SOURCE_AUDIT_ONLY_NO_BASELINE_EXECUTED',
              'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'runner_sha256': file_hash(Path(__file__)),
              'sources': sources, 'current_official_comparison': current, 'self_test': self_test(),
              'deepdb_prefilter_resources': deepdb_resources(), 'environment': environment_snapshot(),
              'official_release_metadata_snapshot': release_metadata(fetch),
              'installed_dependencies': False, 'trained_models': False, 'baseline_results_created': False,
              'source_identity_limit': 'Official pinned sources; none established as the exact unpublished DeepDB baseline snapshot',
              'feasibility': {
                  'dbest': {'can_use_bounded_uniform_samples': 'conditional on explicit population/group multipliers and per-query prefilter columns; DBEstPy add_pair_client accepts CSV and num_of_points',
                            'paper_snapshot_identified': False, 'next': 'isolated original DBEstPy import/API and tiny query checks; do not substitute DBEst++'},
                  'verdictdb': {'directly_accept_plain_sample_with_population_truth': False,
                                'requires': 'sample/scramble metadata and backend table identity; paper stratified+uniform creation scans original mother table',
                                'next': 'separate backend/sample-import research; paper-scale setup cost unavailable from samples alone'},
                  'xdb': {'directly_accept_sample_as_original_population': False, 'sigmod16_requires_primary_index': True,
                          'requires': 'custom PostgreSQL 9.4.2, full mother tables, secondary indexes and warm-I/O protocol; separate database cluster',
                          'next': 'defer paper-scale execution under bounded-storage streaming design'},
                  'wavelets': {'official_implementation_located': False,
                               'requires': 'original multidimensional Haar relational operator implementation and domain/bin/coefficient protocol',
                               'next': 'author-source inquiry or explicitly labeled new implementation, neither performed here'}}}
    result['findings'] = {
        'dbest_client_2019_sample_probability': 'io/sampling.py:24-25 explicitly not implemented; CLI cannot treat a bounded sample as its full mother without a separate adapter',
        'dbest_py_multidimensional_risks': 'query_engine.py:63-64 built-in min/max on multidimensional arrays; density_estimation deletes self.training_data at 83 but multi-D querying reads it at 224ff/318ff; static findings, not executed baseline failures',
        'truth_boundary': 'Evaluation target aggregates must not be silently reused as training group/population metadata; any a-priori group-count input must be separately declared and bound',
        'verdict_version_boundary': 'sigmod18 pom 0.4.7 and CREATE SAMPLE differ from master 0.5.10-SNAPSHOT/CREATE SCRAMBLE; Maven release metadata must be checked independently',
        'wavelet_search_scope': 'DeepDB pinned tree, original paper, Garofalakis author publications/abstract, Microsoft Research official paper page; no implementation located within this scope'}
    result['citations'] = {
        'dbest_original_paper': 'https://wrap.warwick.ac.uk/id/eprint/115961/',
        'dbest_author_thesis_code_pointer': 'https://wrap.warwick.ac.uk/id/eprint/162529/1/WRAP_Theses_Ma_2021.pdf',
        'verdict_original_paper': 'https://arxiv.org/abs/1804.00770',
        'verdict_current_scramble_docs': 'https://docs.verdictdb.org/reference/scrambling/',
        'wander_join_original_paper': 'https://www.cse.ust.hk/~yike/sigmod16.pdf',
        'xdb_author_site': 'https://initialdlab.github.io/XDB/',
        'wavelets_author_journal_entry': 'https://minosng.github.io/Abstracts/vldbj01-abs.html',
        'wavelets_original_conference_paper': 'https://www.vldb.org/conf/2000/P111.pdf',
        'wavelets_journal_author_publication': 'https://www.microsoft.com/en-us/research/publication/approximate-query-processing-using-wavelets-3/',
        'postgres94_build_requirements': 'https://www.postgresql.org/docs/9.4/install-requirements.html'}
    result['official_old_wheel_audit'] = inspect_old_wheel(fetch)
    atomic(RESULT, result)
    return result


def self_test():
    """Actual archive integrity failures must be caught before extraction."""
    content = b'original\r\n'
    blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
    expected = {'a.py': {'sha': blob, 'size': len(content)}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('fixed/a.py', content)
    verified = validate_archive(stream.getvalue(), expected)
    assert verified['a.py'] == content
    for bad_path, bad_content in [('fixed/a.py', b'changed'), ('fixed/../escape.py', content)]:
        broken = io.BytesIO()
        with zipfile.ZipFile(broken, 'w') as archive:
            archive.writestr(bad_path, bad_content)
        try:
            validate_archive(broken.getvalue(), expected)
        except ValueError:
            pass
        else:
            raise AssertionError('Changed bytes or traversal passed the source seal')
    return {'status': 'PASS', 'checks': 3}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fetch', 'audit', 'self-test'])
    args = parser.parse_args()
    result = self_test() if args.action == 'self-test' else audit(args.action == 'fetch')
    print(json.dumps({'status': result['status'], 'sources': list(result.get('sources', {})),
                      'baseline_executed': False, 'self_test': result.get('self_test', result.get('checks'))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
