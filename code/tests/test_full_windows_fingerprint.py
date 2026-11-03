"""Native Windows identity only; no database/scientific/process operations."""
import importlib.util
from pathlib import Path
import platform
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[2]


def helper():
    path=ROOT/'code/full_windows_fingerprint.py'
    assert path.exists(),'Shared native Windows fingerprint helper missing'
    spec=importlib.util.spec_from_file_location('windows_fingerprint_test',str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_native_fingerprint_refuses_version_registry_disagreement():
    m=helper()
    result=m.compose_identity((10,0,26200),(10,0,26200),'AMD64',0,1,(10,0,26100))
    assert result['platform']=='Windows-10-10.0.26200-SP0'
    assert result['platform_version_diagnostic']==[10,0,26100]
    with pytest.raises(ValueError):m.compose_identity((10,0,26100),(10,0,26200),'AMD64',0,1,(10,0,26100))


def test_context_rebuilds_real_platform_without_any_process_and_restores_hooks(monkeypatch):
    m=helper();old_ver=platform._syscmd_ver;old_uname=platform._uname_cache;old_cache=platform._platform_cache
    def forbidden(*args,**kwargs):raise AssertionError('A process launch escaped native fingerprint context')
    monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(subprocess,'check_output',forbidden)
    with m.verified_platform('Windows-10-10.0.26200-SP0','AMD64') as proof:
        assert platform.platform()=='Windows-10-10.0.26200-SP0' and platform.machine()=='AMD64'
        assert platform._syscmd_ver()==('Microsoft','Windows','10.0.26200')
        assert len(proof['helper_sha256'])==64 and proof['subprocess_executed'] is False
    assert platform._syscmd_ver is old_ver and platform._uname_cache is old_uname and platform._platform_cache is old_cache


def test_context_refuses_wrong_sealed_platform_or_architecture():
    m=helper()
    for expected,machine in [('Windows-10-10.0.1-SP0','AMD64'),('Windows-10-10.0.26200-SP0','ARM64')]:
        with pytest.raises(ValueError):
            with m.verified_platform(expected,machine):pass


def test_context_restores_original_state_after_consumer_error():
    m=helper();old=(platform._syscmd_ver,platform._uname_cache,platform._platform_cache)
    with pytest.raises(RuntimeError):
        with m.verified_platform('Windows-10-10.0.26200-SP0','AMD64'):raise RuntimeError('consumer failure')
    assert all(now is previous for now,previous in zip((platform._syscmd_ver,platform._uname_cache,platform._platform_cache),old))
