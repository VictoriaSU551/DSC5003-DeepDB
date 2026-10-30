from pathlib import Path

import pytest

from full_mscn_sources import destination_for, install_member


def test_source_routing_and_existing_bytes_are_preserved(tmp_path):
    target = destination_for('data/train.bitmaps', tmp_path)
    assert target == tmp_path / 'data/mscn/data/train.bitmaps'
    install_member(target, b'original')
    stamp = target.stat().st_mtime_ns
    install_member(target, b'original')
    assert target.stat().st_mtime_ns == stamp
    with pytest.raises(ValueError, match='existing'):
        install_member(target, b'different')
    assert target.read_bytes() == b'original'


@pytest.mark.parametrize('name', ['../private', '/absolute', 'data/../../outside', 'C:/outside', 'data\\outside'])
def test_unsafe_archive_paths_are_rejected(tmp_path, name):
    with pytest.raises(ValueError, match='member'):
        destination_for(name, tmp_path)
