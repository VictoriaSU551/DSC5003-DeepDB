"""Run sealed Flights stages in separate processes with a Windows memory gate.

Operational monitor only: no imports or modifications of the scientific driver.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/full/flights'
GIB = 1024 ** 3
KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
PSAPI = ctypes.WinDLL('psapi', use_last_error=True)


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
               ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
               ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
               ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
               ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]


class MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in ['total_physical', 'available_physical',
        'total_pagefile', 'available_pagefile', 'total_virtual', 'available_virtual', 'extended_virtual']]


class ProcessMemory(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ['PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage']]


KERNEL.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
KERNEL.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
KERNEL.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
KERNEL.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
KERNEL.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
KERNEL.OpenProcess.restype = wintypes.HANDLE
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
KERNEL.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
PSAPI.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]


def process_tree(root_pid):
    handle = KERNEL.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = ProcessEntry(); entry.dwSize = ctypes.sizeof(entry)
    parents = {}
    try:
        success = KERNEL.Process32FirstW(handle, ctypes.byref(entry))
        while success:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            success = KERNEL.Process32NextW(handle, ctypes.byref(entry))
    finally:
        KERNEL.CloseHandle(handle)
    owned = {root_pid}
    while True:
        expanded = owned | {pid for pid, parent in parents.items() if parent in owned}
        if expanded == owned: return sorted(pid for pid in owned if pid in parents)
        owned = expanded


def rss(pid):
    handle = KERNEL.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle: return 0  # Child may exit between snapshot and query.
    counters = ProcessMemory(); counters.cb = ctypes.sizeof(counters)
    try:
        if not PSAPI.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize)
    finally:
        KERNEL.CloseHandle(handle)


def available():
    status = MemoryStatus(); status.dwLength = ctypes.sizeof(status)
    if not KERNEL.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(status.available_physical)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()


def terminate_owned(pids):
    for pid in reversed(pids):
        handle = KERNEL.OpenProcess(1, False, pid)
        if handle:
            try: KERNEL.TerminateProcess(handle, 75)
            finally: KERNEL.CloseHandle(handle)


def main(stages):
    assert os.getpid() in process_tree(os.getpid())
    assert rss(os.getpid()) > 0 and available() > 0
    env = dict(os.environ)
    for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS',
                 'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS']:
        env[name] = '1'
    driver = ROOT / 'code/full_flights_model.py'
    bound_driver = sha256(driver)
    reports = []
    for stage in stages:
        assert sha256(driver) == bound_driver, 'Frozen scientific driver changed'
        command = [str(ROOT / '.venv/Scripts/python.exe'), str(driver), stage, '--source', 'flights-1b',
                   '--paper', '--formal-memory-approved', '--max-rows', '10000000', '--seed', '1']
        stdout_path = OUTPUT / ('model_formal_' + stage + '.stdout.log')
        stderr_path = OUTPUT / ('model_formal_' + stage + '.stderr.log')
        monitor_path = OUTPUT / ('model_formal_' + stage + '_memory.csv')
        report_path = OUTPUT / ('model_formal_' + stage + '_execution.json')
        if report_path.exists() and json.loads(report_path.read_text())['status'] == 'PASS_STAGE_EXIT0':
            raise RuntimeError('Stage already completed; choose only unfinished stages, preserving prior logs')
        started = time.monotonic(); peak = 0; largest = 0; minimum = available(); breach = None
        with stdout_path.open('w', encoding='utf-8') as out, stderr_path.open('w', encoding='utf-8') as err, monitor_path.open('w', encoding='utf-8') as monitor:
            monitor.write('elapsed_seconds,available_physical_bytes,owned_tree_rss_bytes,largest_process_rss_bytes,pids\n')
            process = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=out, stderr=err,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            print(json.dumps(dict(stage=stage, pid=process.pid, started_utc=datetime.now(timezone.utc).isoformat())), flush=True)
            while process.poll() is None:
                pids = process_tree(process.pid); sizes = [rss(pid) for pid in pids]
                total = sum(sizes); big = max(sizes, default=0); free = available()
                peak = max(peak, total); largest = max(largest, big); minimum = min(minimum, free)
                monitor.write('{:.3f},{},{},{},{}\n'.format(time.monotonic()-started, free, total, big, '|'.join(map(str,pids)))); monitor.flush()
                if free < GIB or total > 6 * GIB:
                    breach = 'AVAILABLE_BELOW_1_GIB' if free < GIB else 'OWNED_RSS_ABOVE_6_GIB'
                    terminate_owned(pids); break
                time.sleep(2)
            code = process.wait()
        result = dict(status='STOPPED_MEMORY_GATE' if breach else 'PASS_STAGE_EXIT0' if code == 0 else 'STAGE_FAILED',
                      stage=stage, command=command, driver_sha256=bound_driver, exit_code=code,
                      elapsed_seconds=time.monotonic()-started, peak_owned_tree_rss_bytes=peak,
                      peak_largest_process_rss_bytes=largest, minimum_available_physical_bytes=minimum,
                      memory_gate_reason=breach, threads={n:env[n] for n in env if n.endswith('NUM_THREADS')},
                      stdout=str(stdout_path.relative_to(ROOT)), stderr=str(stderr_path.relative_to(ROOT)),
                      memory_csv=str(monitor_path.relative_to(ROOT)),
                      logs_sha256={p.name:sha256(p) for p in [stdout_path,stderr_path,monitor_path]},
                      completed_utc=datetime.now(timezone.utc).isoformat())
        atomic_json(report_path,result); reports.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if code != 0 or breach: return 75 if breach else code
    atomic_json(OUTPUT / 'model_formal_execution_summary.json', dict(status='PASS_REQUESTED_STAGES', stages=reports))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stages', nargs='*', choices=['prepare','train','evaluate'])
    args = parser.parse_args()
    raise SystemExit(main(args.stages or ['prepare','train','evaluate']))
