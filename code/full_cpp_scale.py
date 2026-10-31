"""Externalize generated RSPN constants without changing inference formulas."""
import argparse
from contextlib import contextmanager
import csv
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import sysconfig
import time

import full_cpp
import full_cpp_range_adapter as range_adapter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/full/cpp-scale'
COMPILER = full_cpp.COMPILER
TRAINING = ROOT / 'output/full/results/public_scale_rdc_n10000000_b0p5_training.json'
DEFAULT_LABEL = 'public_scale_rdc_n10000000_b0p5'
MEMORY_LIMIT = 8 * 1024 ** 3
NUMBER = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
ARRAY = re.compile(
    r'vector\s*<\s*(?P<vector_type>double|float)\s*>\s+'
    r'(?P<vector_name>(?:uniqueVals|probSum)\d+)\s*\{(?P<vector_values>[^{}]*)\}\s*;'
    r'|(?P<array_type>double|float)\s+(?P<array_name>probsNode\d+)\s*'
    r'\[\s*\]\s*=\s*\{(?P<array_values>[^{}]*)\}\s*;')


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    full_cpp.write_json(path, value)


def asset(path, root):
    path = Path(path)
    return {'path': path.resolve().relative_to(Path(root).resolve()).as_posix(),
            'bytes': path.stat().st_size, 'sha256': file_hash(path)}


def validate_assets(records, root):
    root = Path(root).resolve()
    for record in records:
        path = (root / record['path']).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ValueError('Asset path escapes its sealed build directory')
        if (not path.is_file() or path.stat().st_size != record['bytes']
                or file_hash(path) != record['sha256']):
            raise ValueError('Asset SHA256/hash mismatch: ' + str(path))


def externalize_arrays(source, binary_path):
    """Parse only generator numeric literals; preserve IEEE values and order."""
    binary_path = Path(binary_path)
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = binary_path.with_name(binary_path.name + '.tmp')
    arrays = []
    offset = 0
    try:
        with temporary.open('wb') as target:
            def replace(match):
                nonlocal offset
                dtype = match.group('vector_type') or match.group('array_type')
                name = match.group('vector_name') or match.group('array_name')
                literal = match.group('vector_values') if match.group('vector_type') else match.group('array_values')
                tokens = [token.strip() for token in literal.split(',') if token.strip()]
                digest = hashlib.sha256()
                start = offset
                pack = struct.Struct('<d' if dtype == 'double' else '<f').pack
                buffer = bytearray()
                for token in tokens:
                    if not NUMBER.fullmatch(token):
                        raise ValueError('Unsupported generated array literal: ' + token[:100])
                    number = float(token)
                    if not math.isfinite(number):
                        raise ValueError('Nonfinite generated array literal')
                    buffer.extend(pack(number))
                    if len(buffer) >= 65536:
                        target.write(buffer)
                        digest.update(buffer)
                        offset += len(buffer)
                        buffer = bytearray()
                if buffer:
                    target.write(buffer)
                    digest.update(buffer)
                    offset += len(buffer)
                arrays.append({'name': name, 'dtype': dtype, 'offset': start,
                               'count': len(tokens), 'bytes': offset - start,
                               'sha256': digest.hexdigest(),
                               'literal_sha256': hashlib.sha256(literal.encode('utf-8')).hexdigest()})
                return 'static const vector<%s> %s = scale_array<%s>(%dULL,%dULL);' % (
                    dtype, name, dtype, start, len(tokens))
            rewritten = ARRAY.sub(replace, source)
            # A const vector has const iterators; the binary search is unchanged.
            rewritten = re.sub(r'vector\s*<\s*(double|float)\s*>::iterator',
                               r'vector<\1>::const_iterator', rewritten)
            target.flush()
            os.fsync(target.fileno())
        if not arrays:
            raise ValueError('No generated model array literals were found')
        os.replace(str(temporary), str(binary_path))
        return rewritten, {'arrays': arrays, 'array_count': len(arrays),
                           'binary_bytes': offset, 'binary_sha256': file_hash(binary_path),
                           'byte_order': 'little', 'values_compressed_or_reduced': False}
    finally:
        if temporary.exists():
            temporary.unlink()


COMMON_HEADER = r'''#pragma once
#include <cstdint>
#include <algorithm>
#include <vector>
#include <fstream>
#include <stdexcept>
#include <cstring>
#include <sstream>
#include <iomanip>
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
using namespace std;
struct ScaleHash {
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE handle = NULL;
    vector<unsigned char> object;
    ~ScaleHash(){if(handle) BCryptDestroyHash(handle); if(algorithm) BCryptCloseAlgorithmProvider(algorithm,0);}
};
static string scale_sha256(const vector<unsigned char>& bytes){
    ScaleHash hash;
    if(BCryptOpenAlgorithmProvider(&hash.algorithm,BCRYPT_SHA256_ALGORITHM,NULL,0)!=0)
        throw runtime_error("BCrypt SHA256 provider failed");
    DWORD length=0,returned=0;
    if(BCryptGetProperty(hash.algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&length),sizeof(length),&returned,0)!=0)
        throw runtime_error("BCrypt hash object property failed");
    hash.object.resize(length);
    if(BCryptCreateHash(hash.algorithm,&hash.handle,hash.object.data(),length,NULL,0,0)!=0)
        throw runtime_error("BCrypt hash creation failed");
    for(size_t start=0;start<bytes.size();start+=1048576){
        ULONG count=static_cast<ULONG>(min<size_t>(1048576,bytes.size()-start));
        if(BCryptHashData(hash.handle,const_cast<PUCHAR>(bytes.data()+start),count,0)!=0)
            throw runtime_error("BCrypt SHA256 update failed");
    }
    unsigned char result[32];
    if(BCryptFinishHash(hash.handle,result,32,0)!=0) throw runtime_error("BCrypt SHA256 finish failed");
    ostringstream output;
    for(unsigned char value:result) output<<hex<<setw(2)<<setfill('0')<<static_cast<unsigned int>(value);
    return output.str();
}
static vector<unsigned char> scale_read_blob(const char* path,const char* hash,size_t expected){
    static_assert(sizeof(double)==8 && sizeof(float)==4,"IEEE array widths differ");
    uint32_t endian=1;
    if(*reinterpret_cast<unsigned char*>(&endian)!=1) throw runtime_error("Array byte order is not little endian");
    ifstream source(path,ios::binary|ios::ate);
    if(!source || source.tellg()!=static_cast<streamoff>(expected)) throw runtime_error("Array binary size/open failed");
    vector<unsigned char> bytes(expected);
    source.seekg(0);
    if(expected && !source.read(reinterpret_cast<char*>(bytes.data()),expected)) throw runtime_error("Short array binary read");
    if(scale_sha256(bytes)!=hash) throw runtime_error("Array binary SHA256 mismatch");
    return bytes;
}
'''


def blob_loader(record, path):
    quoted = json.dumps(str(Path(path).resolve()))
    return '''
static const vector<unsigned char>& scale_blob(){
    static const vector<unsigned char> value=scale_read_blob(%s,"%s",%dULL);
    return value;
}
template<class T> static vector<T> scale_array(size_t offset,size_t count){
    const auto& bytes=scale_blob();
    if(offset>bytes.size() || count>(bytes.size()-offset)/sizeof(T)) throw runtime_error("Array slice exceeds binary");
    vector<T> value(count);
    if(count) memcpy(value.data(),bytes.data()+offset,count*sizeof(T));
    return value;
}
''' % (quoted, record['binary_sha256'], record['binary_bytes'])


class WindowsOwnedMemory:
    """Use stable process handles for this subprocess tree, never name matching."""

    def __init__(self, root_pid):
        if os.name != 'nt':
            raise RuntimeError('This resource guard requires the validated Windows host')
        self.root_pid = root_pid
        self.handles = {}
        self.names = {}
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.psapi = ctypes.WinDLL('psapi', use_last_error=True)
        pointer = ctypes.c_size_t
        class Entry(ctypes.Structure):
            _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                        ('pid', wintypes.DWORD), ('heap', pointer), ('module', wintypes.DWORD),
                        ('threads', wintypes.DWORD), ('parent', wintypes.DWORD),
                        ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                        ('name', wintypes.WCHAR * 260)]
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (name, pointer) for name in ['peak_rss', 'rss', 'peak_paged', 'paged',
                                             'peak_nonpaged', 'nonpaged', 'pagefile',
                                             'peak_pagefile', 'private']]
        self.Entry, self.Counters = Entry, Counters
        self.kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        self.kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]

    def sample(self):
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError('Cannot inspect owned compiler processes')
        entries = {}
        entry = self.Entry()
        entry.dwSize = ctypes.sizeof(entry)
        try:
            more = self.kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                entries[entry.pid] = (entry.parent, entry.name)
                more = self.kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            self.kernel.CloseHandle(snapshot)
        owned = {self.root_pid} | set(self.handles)
        changed = True
        while changed:
            before = len(owned)
            owned.update(pid for pid, (parent, name) in entries.items() if parent in owned)
            changed = len(owned) != before
        rss = 0
        for pid in owned:
            if pid not in self.handles and pid in entries:
                handle = self.kernel.OpenProcess(0x1000 | 0x0010 | 0x0001, False, pid)
                if handle:
                    self.handles[pid] = handle
                    self.names[pid] = entries[pid][1]
            if pid in self.handles:
                counters = self.Counters()
                counters.cb = ctypes.sizeof(counters)
                if self.psapi.GetProcessMemoryInfo(self.handles[pid], ctypes.byref(counters), counters.cb):
                    rss += int(counters.rss)
        return rss

    def terminate(self):
        # Stable handles still name the originally observed processes if PIDs recycle.
        for handle in self.handles.values():
            self.kernel.TerminateProcess(handle, 137)

    def close(self):
        for handle in self.handles.values():
            self.kernel.CloseHandle(handle)


def run_limited(arguments, directory, label, memory_limit=MEMORY_LIMIT):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = directory / (label + '.stdout.log'), directory / (label + '.stderr.log')
    environment = dict(os.environ, PATH=str(COMPILER.parent) + os.pathsep + os.environ.get('PATH', ''))
    started, peak, stopped = time.perf_counter(), 0, False
    with stdout_path.open('wb') as output, stderr_path.open('wb') as errors:
        process = subprocess.Popen([str(x) for x in arguments], cwd=str(directory), env=environment,
                                   stdout=output, stderr=errors,
                                   creationflags=0x08000000 | 0x00004000)
        monitor = WindowsOwnedMemory(process.pid)
        try:
            while process.poll() is None:
                peak = max(peak, monitor.sample())
                if peak > memory_limit:
                    stopped = True
                    monitor.terminate()
                    process.wait(timeout=15)
                    break
                time.sleep(0.1)
            returncode = process.wait()
        except BaseException:
            monitor.terminate()
            process.wait(timeout=15)
            raise
        finally:
            names = dict(monitor.names)
            monitor.close()
    record = {'arguments': [str(x) for x in arguments], 'returncode': returncode,
              'elapsed_seconds': time.perf_counter() - started,
              'peak_tree_rss_bytes': peak, 'memory_limit_bytes': memory_limit,
              'stopped_for_memory': stopped, 'compile_processes': 1,
              'monitor_interval_seconds': 0.1, 'owned_processes': names,
              'scope': 'Owned subprocess and observed descendants only',
              'priority': 'Below normal; process-local PATH only',
              'stdout_path': str(stdout_path), 'stderr_path': str(stderr_path)}
    write_json(directory / (label + '.json'), record)
    return record


def boundary_differential(directory):
    import numpy as np
    from spn.structure.StatisticalTypes import MetaType
    from rspn.code_generation.generate_code import generate_code
    from rspn.structure.leaves import IdentityNumericLeaf, identity_likelihood_range
    from rspn.algorithms.ranges import NumericRange

    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    cases = [(-float('inf'), 3., True, False), (-float('inf'), 1., True, False),
             (-float('inf'), 5., True, False), (1., 5., False, False),
             (3., 3., True, True), (3., 3., False, True), (3., 3., True, False),
             (10., 20., False, False), (-10., 0., True, False),
             (-float('inf'), float('inf'), True, True), (-99., -99., True, True),
             (-99., 3., True, True)]
    leaf = IdentityNumericLeaf([-99., 1., 3., 5.], [.1, .2, .3, .4], -99., [0])
    original, _ = generate_code(0, leaf, [MetaType.REAL], 'double')
    literal = directory / 'boundary_literal.cpp'
    literal.write_text(original, encoding='utf-8')
    binary = directory / 'boundary.bin'
    rewritten, external = externalize_arrays(original, binary)
    header = directory / 'sealed_arrays.hpp'
    header.write_text(COMMON_HEADER, encoding='utf-8')
    lines = ['#include "sealed_arrays.hpp"', '#include <iostream>',
             blob_loader(external, binary), rewritten,
             'int main(){try{cout<<setprecision(17);']
    predictions = []
    serialized = []
    for left, right, left_inc, right_inc in cases:
        numeric = NumericRange([[left, right]], [[left_inc, right_inc]], null_value=-99.)
        evidence = np.empty((1, 1), dtype=object)
        evidence[0, 0] = numeric
        predictions.append(float(identity_likelihood_range(leaf, evidence)[0, 0]))
        args = ['vector<bool>{true}', 'vector<bool>{false}', 'false',
                str(math.isinf(left)).lower(), str(0. if math.isinf(left) else left),
                str(math.isinf(right)).lower(), str(0. if math.isinf(right) else right),
                str(left_inc).lower(), str(right_inc).lower(), '-99.0']
        lines.append('cout<<spn0(' + ','.join(args) + ')<<"\\n";')
        serialized.append({'left': str(left), 'right': str(right),
                           'left_included': left_inc, 'right_included': right_inc})
    lines.append('return 0;}catch(const exception& error){cerr<<error.what();return 17;}}')
    source, executable = directory / 'boundary_external.cpp', directory / 'boundary.exe'
    source.write_text('\n'.join(lines), encoding='utf-8')
    compiled = run_limited([COMPILER, '-std=c++11', '-O2', '-D_GLIBCXX_ASSERTIONS',
                            '-static-libgcc', '-static-libstdc++', source, '-lbcrypt', '-o', executable],
                           directory, 'compile_boundary')
    if compiled['returncode']:
        raise RuntimeError('External boundary compilation failed: ' +
                           Path(compiled['stderr_path']).read_text(errors='replace')[-2500:])
    executed = run_limited([executable], directory, 'execute_boundary')
    values = [float(value) for value in Path(executed['stdout_path']).read_text().splitlines() if value.strip()]
    check = full_cpp.check_prediction_pairs(predictions, values, [1] * len(values), rtol=1e-12, atol=1e-12)
    raw = binary.read_bytes()
    tampered = bytearray(raw)
    tampered[0] ^= 1
    try:
        binary.write_bytes(tampered)
        rejected = run_limited([executable], directory, 'execute_binary_tamper')
        tamper_pass = rejected['returncode'] == 17 and 'SHA256' in Path(rejected['stderr_path']).read_text()
    finally:
        binary.write_bytes(raw)
    result = {'status': 'PASS' if check['status'] == 'PASS' and tamper_pass else 'FAIL',
              'check': check, 'external_array_count': external['array_count'],
              'binary_tamper_runtime_rejected': tamper_pass,
              'compile_peak_tree_rss_bytes': compiled['peak_tree_rss_bytes'],
              'assets': [asset(path, directory) for path in [literal, source, header, binary, executable]],
              'numeric_template_sha256': file_hash(full_cpp.TEMPLATE),
              'cases': [dict(case, python=python, cpp=cpp)
                        for case, python, cpp in zip(serialized, predictions, values)]}
    write_json(directory / 'boundary_verification.json', result)
    return result


def load_workload():
    from full_evaluation import workload_files
    from full_inventory import sql_tokens, query_dimensions

    queries, records = [], []
    grouped_count = job_count = 0
    for group, sql_path, truth_path in workload_files(True):
        statements = [line.strip() for line in sql_path.read_text().splitlines() if line.strip()]
        with truth_path.open(newline='', encoding='utf-8-sig') as source:
            truths = list(csv.DictReader(source))
        if len(statements) != len(truths):
            raise ValueError('Workload SQL/truth counts differ: ' + group)
        for index, (sql, row) in enumerate(zip(statements, truths)):
            if sql_tokens(sql) != sql_tokens(row['query']) or int(row['query_no']) != index:
                raise ValueError('Workload SQL/truth alignment differs: ' + group)
            tables, predicates = query_dimensions(sql)
            if group != 'job_light' and (tables, predicates) != tuple(map(int, group.split('_')[:2])):
                raise ValueError('Grouped workload dimensions differ')
            queries.append({'group': group, 'query_no': index, 'sql': sql if sql.endswith(';') else sql + ';',
                            'tables': tables, 'predicates': predicates,
                            'cardinality_true': int(row['cardinality_true'])})
        if group == 'job_light':
            job_count += len(statements)
        else:
            grouped_count += len(statements)
        records += [{'path': str(path.relative_to(ROOT)), 'sha256': file_hash(path)}
                    for path in [sql_path, truth_path]]
    if (job_count, grouped_count) != (70, 683):
        raise ValueError('Expected 70+683=753 public queries')
    return {'queries': queries, 'job_light_queries': job_count,
            'grouped_queries': grouped_count, 'source_seals': records}


def binding_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def training_receipt_path(training_label):
    if not re.fullmatch(r'[A-Za-z0-9_]+', training_label):
        raise ValueError('Invalid training label')
    return ROOT / 'output/full/results' / (training_label + '_training.json')


def model_build_directory(binding):
    return OUT / ('model_' + binding['model_sha256'][:16] + '_' + binding_hash(binding)[:12])


def load_v2_references(training_label, workload, model_sha256):
    from full_inventory import sql_tokens
    summary_path = ROOT / 'output/full/results' / (training_label + '_evaluation_v2.json')
    if not summary_path.is_file():
        raise ValueError('V2 reference summary missing for training label ' + training_label)
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    if (summary.get('status') != 'PASS' or summary.get('model_sha256') != model_sha256
            or summary.get('protocol') != 'model_identity_factor_hash_and_cold_query_cache_v2'
            or summary.get('queries') != len(workload['queries'])):
        raise ValueError('V2 reference model/protocol/query count mismatch')
    source_label = summary.get('reused_from_label', training_label)
    training_receipt_path(source_label)
    rows, csv_seals = {}, {}
    for group in sorted({q['group'] for q in workload['queries']}):
        path = ROOT / 'output/full/evaluation_v2' / source_label / (group + '.csv')
        record = summary['groups'][group]
        if file_hash(path) != record['csv_sha256']:
            raise ValueError('V2 reference CSV SHA256/hash mismatch: ' + group)
        helpers = record['helpers']
        if not {'full_factor_cache.py', 'full_evaluation_v2.py'}.issubset(helpers):
            raise ValueError('V2 reference helper seal missing')
        for name, digest in helpers.items():
            if Path(name).name != name or file_hash(ROOT / 'code' / name) != digest:
                raise ValueError('V2 reference helper SHA256/hash mismatch: ' + name)
        with path.open(newline='', encoding='utf-8') as stream:
            rows[group] = list(csv.DictReader(stream))
        expected = [q for q in workload['queries'] if q['group'] == group]
        if len(expected) != len(rows[group]):
            raise ValueError('V2 reference CSV query count mismatch')
        for query, row in zip(expected, rows[group]):
            if (int(row['query_no']) != query['query_no'] or sql_tokens(row['query']) != sql_tokens(query['sql'])
                    or int(row['cardinality_true']) != query['cardinality_true']):
                raise ValueError('V2 reference CSV SQL/truth alignment mismatch')
        csv_seals[str(path.relative_to(ROOT))] = record['csv_sha256']
    return {'rows': rows, 'binding': {'protocol': summary['protocol'], 'source_label': source_label,
                                     'summary_sha256': file_hash(summary_path), 'csv_sha256': csv_seals}}


def generation_binding(training_label=DEFAULT_LABEL):
    import inspect
    receipt_path = training_receipt_path(training_label)
    training = json.loads(receipt_path.read_text(encoding='utf-8'))
    if (training.get('status') != 'PASS' or training.get('requested_samples') != 10000000
            or training.get('budget') != .5 or training.get('profile') != 'public-scale'
            or training.get('label') != training_label):
        raise ValueError('Expected sealed public-scale 10M B=.5 training receipt')
    model = (ROOT / training['model_path']).resolve()
    model.relative_to(ROOT)
    if file_hash(model) != training['model_sha256']:
        raise ValueError('Original 10M model differs from its training receipt')
    template_dir = ROOT / 'code/rspn/code_generation/templates'
    binding = {'training_label': training_label,
               'model_path': str(model.relative_to(ROOT)), 'model_sha256': training['model_sha256'],
               'training_receipt_sha256': file_hash(receipt_path),
               'generator_sha256': file_hash(ROOT / 'code/rspn/code_generation/generate_code.py'),
               'templates': {p.name: file_hash(p) for p in sorted(template_dir.glob('*.cpp'))},
               'externalizer_sha256': hashlib.sha256((inspect.getsource(externalize_arrays) +
                                                     inspect.getsource(blob_loader)).encode()).hexdigest(),
               'loader_header_sha256': hashlib.sha256(COMMON_HEADER.encode('utf-8')).hexdigest(),
               'floating_data_type': 'double', 'model_values_compressed': False,
               'condition_parameter_signature': 'Unchanged author generator signature (float endpoints)',
               'split': 'One author-generated SPN function per translation unit'}
    return training, model, binding


def prepare_model(training_label=DEFAULT_LABEL):
    """Generate author literals first, then externalize one SPN at a time."""
    from ensemble_compilation.spn_ensemble import read_ensemble
    from rspn.code_generation.generate_code import generate_code, replace_template, TemplatePath

    training, original, binding = generation_binding(training_label)
    build_dir = model_build_directory(binding)
    build_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = build_dir / 'generation.json'
    if receipt_path.exists():
        prior = json.loads(receipt_path.read_text(encoding='utf-8'))
        if prior.get('status') != 'PASS' or prior.get('binding') != binding:
            raise ValueError('Existing generation receipt differs from its sealed binding')
        validate_assets(prior['assets'], build_dir)
        return dict(prior, reused_verified_generation=True)
    copy = build_dir / 'ensemble_with_ids.pkl'
    seal = full_cpp.copy_model(original, copy)
    ensemble = read_ensemble(str(copy), build_reverse_dict=True)
    header = build_dir / 'sealed_arrays.hpp'
    header.write_text(COMMON_HEADER, encoding='utf-8')
    declarations, registrations, units = [], [], []
    paths = [header]
    literal_dir = build_dir / 'author_literals'
    literal_dir.mkdir(exist_ok=True)
    for i, spn in enumerate(ensemble.spns):
        spn.id = i
        started = time.perf_counter()
        method, registration = generate_code(i, spn.mspn, spn.meta_types, 'double')
        literal = literal_dir / ('spn_%d.cpp' % i)
        literal.write_text(method, encoding='utf-8')
        binary = build_dir / ('spn_%d.bin' % i)
        rewritten, arrays = externalize_arrays(method, binary)
        if any(item['dtype'] != 'double' for item in arrays['arrays']):
            raise ValueError('Production model array unexpectedly lost double precision')
        signature = method.split('{', 1)[0].strip()
        if not signature.startswith('double spn%d(' % i):
            raise ValueError('Unexpected author generated function signature')
        declarations.append(signature + ';')
        registrations.append(registration)
        source = build_dir / ('spn_%d.cpp' % i)
        source.write_text('#include "sealed_arrays.hpp"\n' + blob_loader(arrays, binary) + rewritten,
                          encoding='utf-8')
        metadata = build_dir / ('spn_%d_arrays.json' % i)
        write_json(metadata, arrays)
        unit = {'spn': i, 'source': source.name, 'binary': binary.name,
                'literal_source': str(literal.relative_to(build_dir)),
                'literal_bytes': literal.stat().st_size, 'external_source_bytes': source.stat().st_size,
                'binary_bytes': binary.stat().st_size, 'arrays': arrays['array_count'],
                'values': sum(item['count'] for item in arrays['arrays']),
                'generation_seconds': time.perf_counter() - started}
        units.append(unit)
        paths.extend([literal, binary, source, metadata])
        write_json(build_dir / ('spn_%d_generated.json' % i), unit)
        print('Externalized SPN', i, 'literal_bytes', unit['literal_bytes'],
              'source_bytes', unit['external_source_bytes'], 'bin_bytes', unit['binary_bytes'], flush=True)
        del method, rewritten
    ensemble.save(str(copy))
    entry = build_dir / 'optimized_inference.cpp'
    entry.write_text('#include <cstdint>\n#include <algorithm>\n' + replace_template(
        TemplatePath.MASTER, {'methods': '\n'.join(declarations),
                              'registration': '\n'.join(registrations)}, 0), encoding='utf-8')
    paths += [copy, entry]
    if file_hash(original) != seal['source_sha256']:
        raise ValueError('Original model changed during code generation')
    result = {'status': 'PASS', 'binding': binding, 'seal': seal,
              'build_directory': str(build_dir), 'model_copy': str(copy),
              'model_copy_sha256': file_hash(copy), 'spns': len(units), 'units': units,
              'author_literal_bytes': sum(item['literal_bytes'] for item in units),
              'external_source_bytes': sum(item['external_source_bytes'] for item in units) + entry.stat().st_size,
              'binary_bytes': sum(item['binary_bytes'] for item in units),
              'values_externalized': sum(item['values'] for item in units),
              'original_model_unchanged': True, 'assets': [asset(path, build_dir) for path in paths]}
    write_json(receipt_path, result)
    return result


def build_extension(training_label=DEFAULT_LABEL):
    import pybind11
    generation = prepare_model(training_label)
    directory = Path(generation['build_directory'])
    common = directory / 'sealed_arrays.hpp'
    python_library = Path(sys.base_prefix) / 'libs/python38.lib'
    module = directory / ('optimized_inference' + sysconfig.get_config_var('EXT_SUFFIX'))
    flags = ['-O2', '-std=c++11', '-ftemplate-depth=2048', '-D_GLIBCXX_ASSERTIONS']
    compiler_seal = {'compiler_sha256': file_hash(COMPILER), 'flags': flags,
                     'python_version': sys.version, 'pybind11_version': pybind11.__version__,
                     'python_library_sha256': file_hash(python_library),
                     'shared_header_sha256': file_hash(common), 'compile_processes': 1,
                     'rss_limit_bytes': MEMORY_LIMIT, 'fast_math': False}
    objects, compile_records = [], []
    sources = [directory / item['source'] for item in generation['units']] + [directory / 'optimized_inference.cpp']
    for source in sources:
        object_path = source.with_suffix('.o')
        label = 'compile_' + source.stem
        seal_path = directory / (label + '.seal.json')
        unit_binding = dict(compiler_seal, source_sha256=file_hash(source))
        prior = json.loads(seal_path.read_text()) if seal_path.exists() else {}
        if (prior.get('status') == 'PASS' and prior.get('binding') == unit_binding
                and object_path.exists() and file_hash(object_path) == prior.get('object_sha256')):
            compiled = dict(prior['command'], reused_verified_object=True)
        else:
            arguments = [COMPILER] + flags + ['-c', source, '-o', object_path]
            if source.name == 'optimized_inference.cpp':
                arguments += ['-I' + pybind11.get_include(), '-I' + sysconfig.get_path('include')]
            compiled = run_limited(arguments, directory, label)
            if compiled['returncode'] != 0:
                write_json(directory / 'build_failure.json', {'status': 'FAIL', 'failed_unit': source.name,
                                                             'command': compiled, 'generation': generation})
                raise RuntimeError('Serial compilation failed or exceeded RSS limit: ' + source.name)
            write_json(seal_path, {'status': 'PASS', 'binding': unit_binding,
                                   'object_sha256': file_hash(object_path), 'command': compiled})
        objects.append(object_path)
        compile_records.append(compiled)
        print('Compiled', source.name, 'peak_tree_RSS_MiB', round(compiled['peak_tree_rss_bytes'] / 1024 ** 2, 1),
              'cached', compiled.get('reused_verified_object', False), flush=True)
    binding = {'generation': generation['binding'], 'compiler': compiler_seal,
               'object_sha256': {path.name: file_hash(path) for path in objects}}
    build_path = directory / 'build.json'
    prior = json.loads(build_path.read_text()) if build_path.exists() else {}
    if (prior.get('status') == 'PASS' and prior.get('binding') == binding
            and module.exists() and file_hash(module) == prior.get('extension_sha256')):
        validate_assets(generation['assets'], directory)
        return dict(prior, reused_verified_build=True)
    linked = run_limited([COMPILER, '-shared', '-static-libgcc', '-static-libstdc++'] + objects +
                         [python_library, '-lbcrypt', '-o', module], directory, 'link_extension')
    if linked['returncode']:
        raise RuntimeError('Link failed or exceeded RSS limit; see link_extension.json')
    original = ROOT / generation['binding']['model_path']
    if file_hash(original) != generation['binding']['model_sha256']:
        raise ValueError('Original 10M model changed during serial compilation')
    result = {'status': 'PASS', 'binding': binding, 'generation': generation,
              'module_path': str(module), 'extension_sha256': file_hash(module),
              'model_copy': generation['model_copy'], 'model_copy_sha256': generation['model_copy_sha256'],
              'compile_records': compile_records, 'link_record': linked,
              'compile_peak_tree_rss_bytes': max([r['peak_tree_rss_bytes'] for r in compile_records] +
                                                [linked['peak_tree_rss_bytes']]),
              'compile_seconds': sum(r['elapsed_seconds'] for r in compile_records) + linked['elapsed_seconds'],
              'original_model_unchanged': True}
    write_json(build_path, result)
    return result


@contextmanager
def expectation_timer():
    """Time the same unmodified expectation entry point in both execution modes."""
    import rspn.rspn as rspn_module
    original = rspn_module.expectation
    measured = {'seconds': 0., 'calls': 0}
    def timed(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            measured['seconds'] += time.perf_counter() - start
            measured['calls'] += 1
    rspn_module.expectation = timed
    try:
        yield measured
    finally:
        rspn_module.expectation = original


def verify_extension(build, repetitions=3):
    from full_factor_cache import model_aware_factor_cache
    with model_aware_factor_cache(), range_adapter.mapped_numeric_inversion() as adaptation:
        return _verify_extension(build, repetitions, adaptation)


def _verify_extension(build, repetitions, adaptation):
    import numpy as np
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.cardinality_evaluation import GenCodeStats
    from evaluation.utils import parse_query
    from schemas.imdb.schema import gen_job_light_imdb_schema

    if repetitions < 2:
        raise ValueError('At least two timed repetitions are required')
    training_label = build['generation']['binding']['training_label']
    training, original, binding = generation_binding(training_label)
    generation = build['generation']
    if binding != generation['binding']:
        raise ValueError('Current model/source/template binding differs from the build')
    directory = Path(generation['build_directory'])
    validate_assets(generation['assets'], directory)
    module_path, copy = Path(build['module_path']), Path(build['model_copy'])
    if file_hash(module_path) != build['extension_sha256'] or file_hash(copy) != build['model_copy_sha256']:
        raise ValueError('Compiled extension or copied model SHA256 differs')
    workload = load_workload()
    pairwise = ROOT / training['pairwise_rdc_path']
    adaptation_binding = range_adapter.adapter_binding()
    references = load_v2_references(training_label, workload, binding['model_sha256'])
    reference_seals = references['binding']['csv_sha256']
    validation_binding = {'model_sha256': binding['model_sha256'],
                          'extension_sha256': build['extension_sha256'],
                          'generation_binding': binding, 'runner_sha256': file_hash(__file__),
                          'pairwise_rdc_sha256': file_hash(pairwise),
                          'workload_seals': workload['source_seals'], 'repetitions': repetitions,
                          'warmup_rounds': 1, 'rtol': 1e-9, 'atol': 1e-7,
                          'range_adapter': adaptation_binding,
                          'python_v2_reference': references['binding'],
                          'factor_cache_adapter_sha256': file_hash(ROOT / 'code/full_factor_cache.py'),
                          'original_factor_hash_source_sha256': file_hash(ROOT / 'code/ensemble_compilation/probabilistic_query.py'),
                          'max_variants': 1, 'merge_indicator_exp': True, 'exploit_overlapping': True}
    receipt = directory / 'verification.json'
    if receipt.exists():
        prior = json.loads(receipt.read_text(encoding='utf-8'))
        if prior.get('status') == 'PASS' and prior.get('binding') == validation_binding:
            validate_assets(prior['result_assets'], directory)
            return dict(prior, reused_verified_comparison=True)
    specification = importlib.util.spec_from_file_location('optimized_inference', str(module_path))
    native = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(native)
    sys.modules['optimized_inference'] = native
    python_ensemble = read_ensemble(str(copy), build_reverse_dict=True)
    cpp_ensemble = read_ensemble(str(copy), build_reverse_dict=True)
    for spn in python_ensemble.spns:
        spn.use_generated_code = False
    cpp_ensemble.use_generated_code()
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    rows, python_values, cpp_values, calls = [], [], [], []
    original_hash = file_hash(original)
    for repetition in range(-1, repetitions):
        for ordinal, item in enumerate(workload['queries']):
            measured = {}
            modes = [('python', python_ensemble), ('cpp', cpp_ensemble)]
            if repetition % 2:
                modes.reverse()
            for mode, ensemble in modes:
                ensemble.cached_expecation_vals = {}
                stats = GenCodeStats()
                parsed = parse_query(item['sql'], schema)
                with expectation_timer() as inference:
                    started = time.perf_counter()
                    _, _, prediction, _ = ensemble.cardinality(
                        parsed, rdc_spn_selection=True, pairwise_rdc_path=str(pairwise),
                        max_variants=1, merge_indicator_exp=True, exploit_overlapping=True,
                        return_factor_values=True, gen_code_stats=stats)
                    elapsed = time.perf_counter() - started
                measured[mode] = {'prediction': float(prediction), 'total_ms': elapsed * 1000,
                                  'expectation_ms': inference['seconds'] * 1000,
                                  'expectation_calls': inference['calls'], 'native_calls': stats.calls,
                                  'native_bridge_ms': stats.total_time * 1000}
            if repetition < 0:
                continue
            py, cpp = measured['python'], measured['cpp']
            python_values.append(py['prediction'])
            cpp_values.append(cpp['prediction'])
            calls.append(cpp['native_calls'])
            rows.append(dict(item, repetition=repetition, ordinal=ordinal,
                             python_prediction=py['prediction'], cpp_prediction=cpp['prediction'],
                             python_total_ms=py['total_ms'], cpp_total_ms=cpp['total_ms'],
                             python_inference_ms=py['expectation_ms'], cpp_inference_ms=cpp['expectation_ms'],
                             cpp_native_bridge_ms=cpp['native_bridge_ms'],
                             python_expectation_calls=py['expectation_calls'],
                             cpp_expectation_calls=cpp['expectation_calls'], generated_spn_calls=cpp['native_calls']))
        print('Completed paired round', repetition, 'queries', len(workload['queries']), flush=True)
    comparison = full_cpp.check_prediction_pairs(python_values, cpp_values, calls, rtol=1e-9, atol=1e-7)
    destination = directory / 'all_753_repeated.csv'
    with destination.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    dimensions = []
    columns = ['python_total_ms', 'cpp_total_ms', 'python_inference_ms', 'cpp_inference_ms', 'cpp_native_bridge_ms']
    def summarize(selected):
        return {column: {'mean': float(np.mean([r[column] for r in selected])),
                         'median': float(np.median([r[column] for r in selected])),
                         'p95': float(np.percentile([r[column] for r in selected], 95))}
                for column in columns}
    for tables in (4, 5, 6):
        for predicates in range(1, 6):
            selected = [row for row in rows if row['group'] != 'job_light' and
                        row['tables'] == tables and row['predicates'] == predicates]
            if not selected:
                raise ValueError('Figure8 public grouped workload cell is empty')
            dimensions.append({'tables': tables, 'predicates': predicates,
                               'unique_queries': len(selected) // repetitions,
                               'timed_pairs': len(selected), 'timing_ms': summarize(selected)})
    grouped_path = directory / 'figure8_grouped_timings.json'
    write_json(grouped_path, {'groups': dimensions, 'timing_scope': 'Public workload, local shared-machine repetitions'})
    local_match_failures = []
    expected_rows = references['rows']
    for row in rows:
        expected = float(expected_rows[row['group']][row['query_no']]['cardinality_predict'])
        if not math.isclose(row['python_prediction'], expected, rel_tol=1e-9, abs_tol=1e-7):
            local_match_failures.append([row['group'], row['query_no'], row['repetition']])
    after = file_hash(original)
    preserved = original_hash == after == binding['model_sha256']
    converter_preserved = file_hash(adaptation_binding['original_converter_path']) == adaptation_binding['original_converter_sha256']
    reference_preserved = all(file_hash(ROOT / path) == digest for path, digest in reference_seals.items())
    result = {'status': 'PASS' if comparison['status'] == 'PASS' and preserved and converter_preserved and reference_preserved and not local_match_failures else 'FAIL',
              'scope': 'Figure8 public-scale 10M double external-array verification on 70+683 public queries; not full-paper reproduction',
              'training_label': training_label,
              'overall_status_scope': 'Model-aware cold-cache Python/C++ differential, independent Python v2 CSV agreement and immutable inputs',
              'cold_cache_python_cpp_gate': comparison['status'],
              'python_v2_reference_gate': 'PASS' if not local_match_failures else 'FAIL',
              'historical_python_reference_gate': 'NOT_COMPARED_PRESERVED_LEGACY_ARTIFACTS',
              'python_v2_reference_csv_unchanged': reference_preserved,
              'full_paper_reproduction_complete': False, 'binding': validation_binding,
              'queries': 753, 'job_light_queries': 70, 'grouped_queries': 683,
              'timed_repetitions': repetitions, 'paired_predictions': len(rows), 'warmup_rounds': 1,
              'comparison': comparison, 'existing_python_predictions_match': not local_match_failures,
              'python_v2_predictions_match': not local_match_failures,
              'existing_python_prediction_mismatches': local_match_failures,
              'range_adapter': dict(adaptation_binding, **adaptation),
              'original_converter_unchanged': converter_preserved,
              'figure8_public_group_cells': dimensions, 'timing_ms': summarize(rows),
              'cache_policy': 'Model-aware factor hash and fresh expectation cache before every query in both modes',
              'total_timer_scope': 'Cardinality/probabilistic query compilation and factor evaluation; SQL parse excluded',
              'inference_timer_scope': 'Same rspn.expectation entry point; includes evidence/relevant-scope work, condition conversion, recursive/native evaluation and result wrapping',
              'native_bridge_timer_scope': 'Upstream GenCodeStats: module lookup, native call and NumPy wrapping; condition conversion excluded',
              'timing_environment': 'Shared host; one warm-up round and alternating mode order; not a paper hardware speed claim',
              'build': build, 'original_model_sha256_before': original_hash,
              'original_model_sha256_after': after, 'original_model_unchanged': preserved,
              'result_assets': [asset(path, directory) for path in [destination, grouped_path]]}
    write_json(receipt, result)
    write_json(OUT / ('model_' + binding['model_sha256'][:16] + '_verification.json'), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['boundary', 'prepare', 'build', 'verify', 'all'])
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--training-label', default=DEFAULT_LABEL)
    args = parser.parse_args()
    if os.environ.get('PYTHONHASHSEED') != '1':
        environment = dict(os.environ, PYTHONHASHSEED='1', OMP_NUM_THREADS='1',
                           OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        return subprocess.call([sys.executable, '-B', str(Path(__file__).resolve())] + sys.argv[1:], env=environment)
    if args.action == 'boundary':
        result = boundary_differential(OUT / 'boundary_current')
    else:
        gate_path = OUT / 'boundary_tdd/boundary_verification.json'
        if gate_path.exists():
            gate = json.loads(gate_path.read_text())
            validate_assets(gate['assets'], gate_path.parent)
            if gate.get('status') != 'PASS' or gate['numeric_template_sha256'] != file_hash(full_cpp.TEMPLATE):
                raise ValueError('Small actual compiled boundary gate failed or changed')
        else:
            gate = boundary_differential(OUT / 'boundary_current')
            if gate['status'] != 'PASS':
                raise ValueError('Small actual compiled boundary gate failed')
        if args.action == 'prepare':
            result = prepare_model(args.training_label)
        else:
            build = build_extension(args.training_label)
            result = build if args.action == 'build' else verify_extension(build, args.repetitions)
    print(json.dumps({'status': result['status'], 'queries': result.get('queries'),
                      'comparison': result.get('comparison'), 'timing_ms': result.get('timing_ms'),
                      'historical_python_reference_gate': result.get('historical_python_reference_gate'),
                      'python_v2_reference_gate': result.get('python_v2_reference_gate'),
                      'compile_peak_tree_rss_bytes': result.get('compile_peak_tree_rss_bytes', result.get('build', {}).get('compile_peak_tree_rss_bytes')),
                      'original_model_unchanged': result.get('original_model_unchanged')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
