"""Real ZIP fixtures exercise source validation, safe extraction, and cache seals."""
import importlib
import json
import struct
import zipfile

import pytest


def implementation():
    try:
        return importlib.import_module('full_aqp_data')
    except ModuleNotFoundError as exc:
        if exc.name != 'full_aqp_data':
            raise
        pytest.fail('AQP input downloader is not implemented yet')


COLUMNS = ['YEAR_DATE', 'UNIQUE_CARRIER', 'ORIGIN', 'ORIGIN_STATE_ABR',
           'DEST', 'DEST_STATE_ABR', 'DEP_DELAY', 'TAXI_OUT', 'TAXI_IN',
           'ARR_DELAY', 'AIR_TIME', 'DISTANCE']
CSV = (','.join(COLUMNS) + '\r\r\n'
       '1995,AA,DFW,TX,MCI,MO,86,13,3,84,80,460\r\r\n'
       '2016,WN,SFO,CA,LAS,NV,1,12,6,-6,70,414\r\r\n').encode()
DESCRIPTOR = json.dumps({'tables': {'fact': {'fields': [
    {'field': name, 'type': 'categorical' if i < 6 else 'quantitative'}
    for i, name in enumerate(COLUMNS)]}}}).encode()


def archive_fixture(tmp_path, omit=None, extra=None):
    archive = tmp_path / 'flights.zip'
    with zipfile.ZipFile(str(archive), 'w', compression=zipfile.ZIP_STORED) as bundle:
        for name, data in [('flights/sample.csv', CSV),
                           ('flights/sample.json', DESCRIPTOR),
                           ('flights/unused.txt', b'UNUSED_CONTENT_CRC_CHECK')]:
            if name != omit:
                bundle.writestr(name, data)
        if extra:
            bundle.writestr(extra, b'not allowed')
    return archive


@pytest.mark.parametrize('name', ['../escaped.csv', '/absolute.csv',
                                  'flights/../../escaped.csv',
                                  '..\\escaped.csv', 'C:/escaped.csv'])
def test_zip_path_traversal_is_rejected_before_writes(tmp_path, name):
    aqp = implementation()
    archive = archive_fixture(tmp_path, extra=name)
    destination = tmp_path / 'extracted'
    with pytest.raises(aqp.DataError, match='[Uu]nsafe'):
        aqp.prepare_archive(archive, destination)
    assert not destination.exists()


@pytest.mark.parametrize('member', ['flights/sample.csv', 'flights/unused.txt'])
def test_all_zip_members_must_pass_crc_before_extraction(tmp_path, member):
    aqp = implementation()
    archive = archive_fixture(tmp_path)
    with zipfile.ZipFile(str(archive)) as bundle:
        info = bundle.getinfo(member)
    content = bytearray(archive.read_bytes())
    header = struct.unpack_from('<4s5H3L2H', content, info.header_offset)
    offset = info.header_offset + 30 + header[-2] + header[-1]
    content[offset] ^= 1
    archive.write_bytes(content)
    destination = tmp_path / 'extracted'
    with pytest.raises(aqp.DataError, match='CRC'):
        aqp.prepare_archive(archive, destination)
    assert not destination.exists()


@pytest.mark.parametrize('member', ['flights/sample.csv', 'flights/sample.json'])
def test_missing_required_source_input_fails(tmp_path, member):
    aqp = implementation()
    archive = archive_fixture(tmp_path, omit=member)
    with pytest.raises(aqp.DataError, match='[Mm]issing'):
        aqp.prepare_archive(archive, tmp_path / 'extracted')


def test_tampered_extracted_data_is_not_a_valid_cache(tmp_path):
    aqp = implementation()
    archive = archive_fixture(tmp_path)
    destination = tmp_path / 'extracted'
    aqp.prepare_archive(archive, destination)
    (destination / 'sample.csv').write_bytes(CSV.replace(b'1995', b'1996'))
    with pytest.raises(aqp.DataError, match='[Cc]ache.*hash|[Tt]ampered'):
        aqp.prepare_archive(archive, destination)
    assert (destination / 'sample.csv').read_bytes() != CSV


def test_verified_cache_is_reused_and_rows_ignore_blank_lines(tmp_path):
    aqp = implementation()
    archive = archive_fixture(tmp_path)
    destination = tmp_path / 'extracted'
    first = aqp.prepare_archive(archive, destination)
    sample_time = (destination / 'sample.csv').stat().st_mtime_ns
    second = aqp.prepare_archive(archive, destination)
    assert first['all_zip_crcs_verified'] is True
    assert second['extraction_cached'] is True
    assert first['files'] == second['files']
    assert (destination / 'sample.csv').stat().st_mtime_ns == sample_time
    assert sorted(p.name for p in destination.iterdir()) == ['sample.csv', 'sample.json']
    summary = aqp.summarize_inputs(destination)
    assert summary['rows'] == 2
    assert summary['columns'] == COLUMNS
    assert summary['year_min'] == 1995 and summary['year_max'] == 2016
    assert summary['year_counts'] == {'1995': 1, '2016': 1}


def test_archive_must_match_pinned_git_blob(tmp_path):
    aqp = implementation()
    archive = archive_fixture(tmp_path)
    with pytest.raises(aqp.DataError, match='Git blob'):
        aqp.prepare_archive(archive, tmp_path / 'extracted', expected_git_blob='0' * 40)


def test_csv_schema_must_match_generator_descriptor(tmp_path):
    aqp = implementation()
    archive = archive_fixture(tmp_path)
    destination = tmp_path / 'extracted'
    aqp.prepare_archive(archive, destination)
    (destination / 'sample.csv').write_bytes(CSV.replace(b'YEAR_DATE', b'WRONG_KEY'))
    with pytest.raises(aqp.DataError, match='[Cc]olumn'):
        aqp.summarize_inputs(destination)
