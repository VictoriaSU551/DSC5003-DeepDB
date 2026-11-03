"""Verified Windows platform fingerprint without Python3.8's cmd/ver probe.

Read-only outer compatibility adapter. It does not modify frozen consumers.
Use `with verified_platform(sealed_platform, sealed_machine) as proof:`.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import platform
import sys


def compose_identity(native,registry,machine,service_pack_major,product_type,platform_version):
    native=tuple(native);registry=tuple(registry)
    if (len(native)!=3 or native!=registry or native[:2]!=(10,0) or
        any(type(x) is not int or x<0 for x in native) or product_type!=1 or
        type(service_pack_major) is not int or service_pack_major<0 or machine not in ('AMD64','ARM64','x86')):
        raise ValueError('Current native Windows/registry/architecture identity is unsupported or inconsistent')
    return dict(platform='Windows-10-{}.{}.{}-SP{}'.format(*native,service_pack_major),machine=machine,
        native_version=list(native),registry_version=list(registry),service_pack_major=service_pack_major,
        platform_version_diagnostic=list(platform_version),version_string='{}.{}.{}'.format(*native),
        diagnostic_note='sys.getwindowsversion.platform_version may differ; main native tuple must independently agree with registry')


def inspect_native():
    if sys.platform!='win32':raise ValueError('Native Windows fingerprint requires Windows')
    import winreg
    v=sys.getwindowsversion()
    with winreg.OpenKeyEx(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
        registry=tuple(int(winreg.QueryValueEx(key,n)[0]) for n in ('CurrentMajorVersionNumber','CurrentMinorVersionNumber','CurrentBuildNumber'))
    machine=os.environ.get('PROCESSOR_ARCHITEW6432') or os.environ.get('PROCESSOR_ARCHITECTURE','')
    proof=compose_identity(v[:3],registry,machine,v.service_pack_major,v.product_type,v.platform_version)
    proof.update(helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),subprocess_executed=False,
        method='Native sys.getwindowsversion main tuple + read-only 64bit registry + architecture environment',
        adapter_scope='Contextual _syscmd_ver native equivalent; original platform()/machine() algorithms and frozen consumers remain unchanged')
    return proof


@contextmanager
def verified_platform(expected_platform,expected_machine):
    proof=inspect_native()
    if proof['platform']!=expected_platform or proof['machine']!=expected_machine:
        raise ValueError('Independent current Windows fingerprint differs from sealed platform/machine')
    previous=(platform._syscmd_ver,platform._uname_cache,platform._platform_cache)
    def native_ver(*args,**kwargs):return ('Microsoft','Windows',proof['version_string'])
    try:
        platform._syscmd_ver=native_ver
        platform._uname_cache=None
        platform._platform_cache={}
        if platform.platform()!=expected_platform or platform.machine()!=expected_machine:
            raise ValueError('Original platform algorithm disagrees with independent native fingerprint')
        yield proof
    finally:
        platform._syscmd_ver,platform._uname_cache,platform._platform_cache=previous
