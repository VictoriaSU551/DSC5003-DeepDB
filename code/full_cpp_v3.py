"""Canonical v3 Python/native differential using existing sealed C++ assets.

Never generates or compiles C++. Historical v2 files stay read-only. Formal
inference requires the final 38-model, four-hash-seed canonical acceptance.
"""
import argparse
from contextlib import contextmanager
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/full/cpp-v3'
LABEL = 'paper_proxy_public_scale_rdc_n10000000_b0p5'
MODEL_SHA = '00c14f94cbedf038e45a7d22b54236b92026f1d39faed0839ce06a0c24710197'
PROTOCOL = 'canonical_v3_physical_cold_cache_sealed_native_v1'
LIMIT = 8 * 1024 ** 3
RTOL, ATOL = 1e-9, 1e-7
EXPECTED_MODELS = 38


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def record(path, root=ROOT):
    path, root = Path(path).resolve(), Path(root).resolve()
    return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=sha(path))


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(str(temporary), str(path))


def seal(value):
    value = {key: item for key, item in value.items() if key != 'receipt_sha256'}
    return dict(value, receipt_sha256=digest(value))


def require_seal(value):
    if not isinstance(value, dict) or value.get('receipt_sha256') != digest(
            {key: item for key, item in value.items() if key != 'receipt_sha256'}):
        raise ValueError('Receipt self-seal differs')


def require_exact_map(actual, expected, name):
    expected = list(expected)
    if (not isinstance(actual, dict) or not actual or not expected
            or len(set(expected)) != len(expected) or set(actual) != set(expected)):
        raise ValueError(name + ' map is empty, incomplete or unexpected')


def validate_assets(records, root):
    root = Path(root).resolve()
    if not isinstance(records, list) or not records:
        raise ValueError('Asset map is empty')
    seen = set()
    for item in records:
        relative = Path(item['path'])
        path = (root / relative).resolve()
        if relative.is_absolute() or root not in path.parents or item['path'] in seen:
            raise ValueError('Duplicate or escaping asset path')
        seen.add(item['path'])
        if not path.is_file() or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise ValueError('Asset SHA256/hash mismatch: ' + str(path))


def validate_references(queries, rows):
    if not queries:
        raise ValueError('Reference workload is empty')
    expected = {}
    for query in queries:
        expected.setdefault(query['group'], []).append(query)
    require_exact_map(rows, expected, 'reference group')
    values = {}
    for group, group_queries in expected.items():
        if not isinstance(rows[group], list) or len(rows[group]) != len(group_queries):
            raise ValueError('Reference group query count differs')
        for query, row in zip(group_queries, rows[group]):
            if (int(row['query_no']) != query['query_no'] or row['query'] != query['sql']
                    or int(row['cardinality_true']) != query['cardinality_true']
                    or hashlib.sha256(row['query'].encode()).hexdigest() != query['sql_sha256']):
                raise ValueError('Exact reference SQL/query/truth identity differs')
            key = (group, query['query_no'])
            value = float(row['cardinality_predict'])
            if key in values or not math.isfinite(value) or value < 0:
                raise ValueError('Duplicate or nonfinite reference prediction')
            values[key] = value
    return values


def validate_acceptance_structure(final, aggregate, acceptance_sha, aggregate_sha, expected_models=EXPECTED_MODELS):
    require_seal(final)
    if (final.get('status') != 'PASS_CURRENT_CANONICAL_FOUR_SEED_ACCEPTANCE'
            or final.get('parent_verification_sha256') != aggregate_sha
            or final.get('acceptance_source_sha256') != acceptance_sha):
        raise ValueError('Final canonical acceptance identity differs')
    labels, models = aggregate.get('labels', []), final.get('models', [])
    if len(labels) != expected_models or len(models) != expected_models:
        raise ValueError('Final canonical acceptance model set is incomplete')
    mapping = {item['label']: item for item in models}
    require_exact_map(mapping, labels, 'accepted models')
    if len(mapping) != len(models) or any(not item.get('binding') or item.get('queries', 0) <= 0 for item in models):
        raise ValueError('Final canonical acceptance contains duplicate or empty identities')
    return mapping


class NativeCounter:
    def __init__(self):
        self.calls = {}
        self.nanoseconds = 0
    def reset(self):
        self.calls = {}
        self.nanoseconds = 0
    @property
    def total(self):
        return sum(self.calls.values())


@contextmanager
def native_tracker(module, spns):
    expected = ['spn%d' % i for i in range(spns)]
    actual = {name: getattr(module, name) for name in dir(module) if re.fullmatch(r'spn\d+', name)}
    require_exact_map(actual, expected, 'native exports')
    if any(not callable(fn) for fn in actual.values()):
        raise ValueError('Native export is not callable')
    counter = NativeCounter()
    def wrap(name, function):
        def call(*args, **kwargs):
            started = time.perf_counter_ns()
            value = function(*args, **kwargs)
            elapsed = time.perf_counter_ns() - started
            counter.calls[name] = counter.calls.get(name, 0) + 1
            counter.nanoseconds += elapsed
            return value
        return call
    try:
        for name, fn in actual.items():
            setattr(module, name, wrap(name, fn))
        yield counter
    finally:
        for name, fn in actual.items():
            setattr(module, name, fn)


def check_triplet(python, native, reference, calls):
    values = [python, native, reference]
    if (not all(math.isfinite(value) and value >= 0 for value in values) or calls <= 0
            or not math.isclose(python, native, rel_tol=RTOL, abs_tol=ATOL)
            or not math.isclose(python, reference, rel_tol=RTOL, abs_tol=ATOL)
            or not math.isclose(native, reference, rel_tol=RTOL, abs_tol=ATOL)):
        raise ValueError('Three-way prediction/native call gate failed')
    return max(abs(python-native), abs(python-reference), abs(native-reference)) / max(abs(reference), ATOL)


def validate_call_counters(mode, calls, upstream_calls):
    physical=sum(calls.values())
    if (mode not in ('python','cpp') or upstream_calls<0
            or any(not re.fullmatch(r'spn\d+',key) or not isinstance(value,int) or value<=0 for key,value in calls.items())
            or (mode=='python' and (physical or upstream_calls))
            or (mode=='cpp' and (not calls or physical<=0 or upstream_calls>physical))):
        raise ValueError('Native physical call gate failed')
    return physical-upstream_calls


def require_round_grid(rows, workload, repetitions):
    if not workload or repetitions < 3 or len(rows) != len(workload) * repetitions:
        raise ValueError('Repeated query grid is incomplete')
    seen = set()
    for row in rows:
        rep, ordinal = row['repetition'], row['ordinal']
        if not isinstance(rep, int) or not isinstance(ordinal, int) or not 0 <= rep < repetitions or not 0 <= ordinal < len(workload):
            raise ValueError('Repeated query grid index differs')
        if (rep, ordinal) in seen:
            raise ValueError('Duplicate repeated query')
        seen.add((rep, ordinal))
        query = workload[ordinal]
        if any(row.get(key) != value for key, value in query.items()):
            raise ValueError('Repeated exact query identity differs')
        calls = row.get('native_call_map')
        if (not isinstance(calls, dict) or not calls
                or any(not re.fullmatch(r'spn\d+', key) or not isinstance(value, int) or value <= 0 for key, value in calls.items())
                or sum(calls.values()) != row.get('generated_spn_calls') or row.get('generated_spn_calls', 0) <= 0):
            raise ValueError('Every query requires a nonempty successful native call map')
        nanoseconds, milliseconds = row.get('cpp_physical_native_ns'), row.get('cpp_physical_native_ms')
        if (not isinstance(nanoseconds, int) or nanoseconds <= 0
                or not isinstance(milliseconds, (int, float)) or not math.isfinite(milliseconds)
                or not math.isclose(milliseconds, nanoseconds / 1e6, rel_tol=1e-12, abs_tol=0)):
            raise ValueError('Complete physical native wall evidence/units differ')


def tree_records(directory):
    directory = Path(directory)
    rows = [record(path, directory) for path in sorted(directory.rglob('*')) if path.is_file()]
    if not rows:
        raise ValueError('Protected legacy tree is empty')
    return rows


@contextmanager
def forbid_generation():
    import full_cpp_scale as old
    saved = []
    def forbidden(*args, **kwargs):
        raise AssertionError('This v3 runner must never generate or compile C++')
    for module, names in [(old, ['prepare_model','build_extension','boundary_differential']),
                          (old.full_cpp, ['copy_model','run_command','boundary_differential'])]:
        for name in names:
            saved.append((module, name, getattr(module, name)))
            setattr(module, name, forbidden)
    try:
        yield
    finally:
        for module, name, fn in saved:
            setattr(module, name, fn)


def accepted_reference(require_final):
    import full_evaluation_v3 as v3
    import full_canonical_acceptance as acceptance
    summary = v3.checked_summary(LABEL)
    if summary.get('queries') != 753 or summary.get('model_sha256') != MODEL_SHA:
        raise ValueError('Expected canonical 753-query model reference')
    final_path = ROOT / 'output/full/results/canonical_final_acceptance.json'
    accepted = None
    if require_final:
        if not final_path.is_file():
            raise ValueError('Final 38-model four-seed canonical acceptance is pending')
        final, parent_path = read_json(final_path), ROOT / 'output/full/results/canonical_inference_verification.json'
        aggregate = acceptance.validated_aggregate(sha(parent_path), sha(ROOT/'code/full_evaluation_v3_run.py'), sha(ROOT/'code/full_evaluation_v3.py'))
        models = validate_acceptance_structure(final, aggregate, sha(ROOT/'code/full_canonical_acceptance.py'), sha(parent_path))
        for label, item in models.items():
            current = read_json(ROOT/'output/full/results'/ (label+'_evaluation_v3.json'))
            if item['binding'] != current['binding'] or item['queries'] != current['queries']:
                raise ValueError('Final acceptance current model summary differs')
        acceptance.verify_current(LABEL, 753)
        accepted = dict(final=record(final_path), aggregate=record(parent_path),
                        contexts=[record(ROOT/'output/full/canonical_run'/('seed%d_complete.json'%seed)) for seed in range(4)],
                        target_replays=[record(ROOT/'output/full/results'/(LABEL+'_replay_v3_seed%d.json'%seed)) for seed in (1,2,3)])
    return summary, accepted


def inputs(repetitions=3, require_final=True):
    if repetitions < 3:
        raise ValueError('At least three timed repetitions are required')
    import full_cpp_scale as old
    import full_evaluation_v3 as v3
    from full_inventory import query_dimensions, sql_tokens
    with forbid_generation():
        summary, acceptance = accepted_reference(require_final)
        legacy = ROOT/'output/full/cpp-scale'
        old_tree = tree_records(legacy)
        outer = read_json(legacy/'sealed_paper_proxy_6spn.json')
        if outer.get('status') != 'SEALED_PASS' or outer.get('model_sha256') != MODEL_SHA:
            raise ValueError('Historical six-SPN outer seal differs')
        validate_assets(outer['assets'], legacy)
        historical_path = legacy/'model_00c14f94cbedf038_verification.json'
        historical = read_json(historical_path)
        build, generation = historical['build'], historical['build']['generation']
        directory = Path(generation['build_directory']).resolve()
        final = read_json(directory/'final_seal.json')
        if (final.get('status') != 'SEALED_MODEL_AWARE_CPP_AND_V2_REFERENCE_PASS'
                or final.get('model_sha256') != MODEL_SHA or generation.get('spns') != 6):
            raise ValueError('Historical inner seal or SPN count differs')
        validate_assets(final['assets'], directory)
        validate_assets(generation['assets'], directory)
        training, model, current = old.generation_binding(LABEL)
        if current != generation['binding'] or current != build['binding']['generation'] or current['model_sha256'] != MODEL_SHA:
            raise ValueError('Original generation/template/model binding differs')
        objects=build['binding']['object_sha256']
        require_exact_map(objects,['spn_%d.o'%i for i in range(6)]+['optimized_inference.o'],'compiled object')
        if any(sha(directory/name)!=value for name,value in objects.items()):
            raise ValueError('Historical object SHA differs')
        module, copy = Path(build['module_path']).resolve(), Path(build['model_copy']).resolve()
        if (sha(module)!=build['extension_sha256'] or sha(copy)!=build['model_copy_sha256']
                or not module.name.endswith(sysconfig.get_config_var('EXT_SUFFIX'))):
            raise ValueError('Native binary/model copy hash or Python ABI differs')
        compiler=build['binding']['compiler']
        if (sys.version!=compiler['python_version'] or importlib.metadata.version('pybind11')!=compiler['pybind11_version']
                or sha(Path(sys.base_prefix)/'libs/python38.lib')!=compiler['python_library_sha256']
                or compiler.get('fast_math') is not False or current['floating_data_type']!='double'):
            raise ValueError('Sealed native runtime/double configuration differs')
        workload, references, csv_records, groups = [], {}, [], list(v3.workload_files(True))
        require_exact_map(summary['groups'], [g for g,_,_ in groups], 'v3 group')
        for group, query_path, truth_path in groups:
            statements=[line.strip() for line in query_path.read_text().splitlines() if line.strip()]
            with truth_path.open(newline='',encoding='utf-8-sig') as stream:
                truths=list(csv.DictReader(stream))
            if len(statements)!=len(truths) or not statements:
                raise ValueError('Workload SQL/truth count differs')
            for index,(sql,truth) in enumerate(zip(statements,truths)):
                if int(truth['query_no'])!=index or sql_tokens(sql)!=sql_tokens(truth['query']):
                    raise ValueError('Workload SQL/truth identity differs')
                tables,predicates=query_dimensions(sql)
                if group!='job_light' and (tables,predicates)!=tuple(map(int,group.split('_')[:2])):
                    raise ValueError('Public workload dimension differs')
                workload.append(dict(group=group,query_no=index,sql=sql,sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                    tables=tables,predicates=predicates,cardinality_true=int(truth['cardinality_true'])))
            path=ROOT/'output/full/evaluation_v3'/LABEL/(group+'.csv')
            if sha(path)!=summary['groups'][group]['csv_sha256']:
                raise ValueError('Canonical reference CSV changed')
            with path.open(newline='',encoding='utf-8') as stream:
                references[group]=list(csv.DictReader(stream))
            csv_records.append(record(path))
        values=validate_references(workload,references)
        if len(workload)!=753 or sum(q['group']=='job_light' for q in workload)!=70:
            raise ValueError('Expected exact 70+683 workload')
        extras=['full_cpp_v3.py','full_cpp.py','full_cpp_scale.py','full_cpp_range_adapter.py',
                'full_factor_cache.py','full_stable_selection.py','full_canonical_acceptance.py','full_evaluation_v3_run.py']
        config=dict(protocol=PROTOCOL,label=LABEL,repetitions=repetitions,warmup_rounds=1,rtol=RTOL,atol=ATOL,
            worker_hash_seed='0',threads=1,memory_limit_bytes=LIMIT,native_regenerated_or_recompiled=False,
            canonical_configuration=summary['configuration'],canonical_acceptance=acceptance,
            reference_summary=record(ROOT/'output/full/results'/(LABEL+'_evaluation_v3.json')),
            reference_csvs=csv_records,new_and_reused_sources={name:sha(ROOT/'code'/name) for name in extras},
            range_adapter=old.range_adapter.adapter_binding(),legacy_tree=old_tree,
            legacy_build=record(historical_path),native_module=record(module),native_model_copy=record(copy),
            model=record(model),pairwise=record(ROOT/training['pairwise_rdc_path']),
            compiler_binding=compiler,extension_suffix=sysconfig.get_config_var('EXT_SUFFIX'))
        return config,workload,values,build


TIMERS = ['python_total_ms','cpp_total_ms','python_inference_ms','cpp_inference_ms','cpp_native_bridge_ms',
          'cpp_physical_native_ms']


def timing_summary(rows):
    import numpy as np
    if not rows:
        raise ValueError('Timing set is empty')
    result = {}
    for column in TIMERS:
        values = [row[column] for row in rows]
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError('Nonfinite/negative timing')
        result[column] = dict(mean=float(np.mean(values)),median=float(np.median(values)),p95=float(np.percentile(values,95)))
    return result


def figure8_groups(rows, repetitions):
    groups = []
    for tables in (4,5,6):
        for predicates in range(1,6):
            selected=[row for row in rows if row['group']!='job_light' and row['tables']==tables and row['predicates']==predicates]
            if not selected or len(selected)%repetitions:
                raise ValueError('Figure8 timing cell is empty or incomplete')
            groups.append(dict(tables=tables,predicates=predicates,unique_queries=len(selected)//repetitions,
                               timed_pairs=len(selected),timing_ms=timing_summary(selected)))
    return groups


def run_guarded(arguments, directory, memory_limit=LIMIT, label='worker'):
    import full_cpp_scale as old
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    stdout,stderr=directory/(label+'.stdout.log'),directory/(label+'.stderr.log')
    env=dict(os.environ,PYTHONHASHSEED='0',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
             PATH=str(old.COMPILER.parent)+os.pathsep+os.environ.get('PATH',''))
    started,peak,stopped=time.perf_counter(),0,False
    with stdout.open('wb') as output,stderr.open('wb') as errors:
        process=subprocess.Popen([str(x) for x in arguments],cwd=str(ROOT),env=env,
            stdout=output,stderr=errors,creationflags=0x08000000|0x20)
        monitor=old.WindowsOwnedMemory(process.pid)
        try:
            while process.poll() is None:
                peak=max(peak,monitor.sample())
                if peak>memory_limit:
                    stopped=True;monitor.terminate();process.wait(timeout=15);break
                time.sleep(.1)
            returncode=process.wait()
        except BaseException:
            monitor.terminate();process.wait(timeout=15);raise
        finally:
            names=dict(monitor.names);monitor.close()
    if any(Path(name).name.lower() in {'g++.exe','cc1plus.exe','ld.exe','as.exe'} for name in names.values()):
        raise ValueError('Unexpected compiler descendant during native reuse')
    result=dict(arguments=[str(x) for x in arguments],returncode=returncode,
        elapsed_seconds=time.perf_counter()-started,peak_tree_rss_bytes=peak,memory_limit_bytes=memory_limit,
        stopped_for_memory=stopped,monitor_interval_seconds=.1,owned_processes=names,compile_processes=0,
        scope='Owned validation process and observed descendants only',priority='Normal; process-local environment only',
        stdout_path=str(stdout),stderr_path=str(stderr))
    write_json(directory/(label+'.resource.json'),seal(result))
    return result


def worker(directory):
    directory=Path(directory).resolve()
    if OUT not in directory.parents:
        raise ValueError('Worker directory escapes v3 namespace')
    expected=read_json(directory/'input_binding.json')
    config,workload,references,build=inputs(expected['repetitions'],require_final=True)
    if expected!=config or os.environ.get('PYTHONHASHSEED')!='0' or any(os.environ.get(key)!='1' for key in
            ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']):
        raise ValueError('Worker actual source/runtime/input binding differs')
    import full_canonical_acceptance as acceptance
    hashes={word:hash(word) for word in acceptance.WORDS}
    baseline_context=read_json(ROOT/'output/full/canonical_run/seed0_complete.json')
    if hashes!=baseline_context['hash_fingerprints']:
        raise ValueError('Worker actual hash-seed fingerprint differs')
    import full_cpp_scale as old
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.cardinality_evaluation import GenCodeStats
    from evaluation.utils import parse_query
    from schemas.imdb.schema import gen_job_light_imdb_schema
    from full_factor_cache import model_aware_factor_cache
    from full_stable_selection import canonical_greedy_selection
    if 'optimized_inference' in sys.modules:
        raise ValueError('A native module was already loaded before the sealed asset')
    dll_directory=os.add_dll_directory(str(old.COMPILER.parent)) if hasattr(os,'add_dll_directory') else None
    spec=importlib.util.spec_from_file_location('optimized_inference',build['module_path'])
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    sys.modules['optimized_inference']=native
    rows,max_relative,warmup_calls=[],0.,0
    try:
        with forbid_generation(),canonical_greedy_selection(),model_aware_factor_cache(),old.range_adapter.mapped_numeric_inversion() as adaptation:
            python=read_ensemble(str(ROOT/config['model']['path']),build_reverse_dict=True)
            cpp=read_ensemble(build['model_copy'],build_reverse_dict=True)
            if len(python.spns)!=6 or len(cpp.spns)!=6:
                raise ValueError('Expected two six-SPN ensembles')
            for spn in python.spns:spn.use_generated_code=False
            cpp.use_generated_code()
            if [spn.id for spn in cpp.spns]!=list(range(6)):
                raise ValueError('Native physical SPN id map differs')
            schema=gen_job_light_imdb_schema(str(ROOT/'data/imdb/{}.csv'))
            pairwise=ROOT/config['pairwise']['path']
            with native_tracker(native,6) as tracker:
                for repetition in range(-1,config['repetitions']):
                    for ordinal,query in enumerate(workload):
                        modes=[('python',python),('cpp',cpp)]
                        if repetition%2:modes.reverse()
                        measured={}
                        for mode,ensemble in modes:
                            ensemble.cached_expecation_vals={}
                            tracker.reset();stats=GenCodeStats()
                            parsed=parse_query(query['sql'] if query['sql'].endswith(';') else query['sql']+';',schema)
                            with old.expectation_timer() as inference:
                                started=time.perf_counter()
                                _,_,prediction,_=ensemble.cardinality(parsed,rdc_spn_selection=True,
                                    pairwise_rdc_path=str(pairwise),max_variants=1,merge_indicator_exp=True,
                                    exploit_overlapping=True,return_factor_values=True,gen_code_stats=stats)
                                elapsed=time.perf_counter()-started
                            try:
                                omitted=validate_call_counters(mode,tracker.calls,stats.calls)
                            except ValueError:
                                write_json(directory/'native_counter_failure.json',seal(dict(status='FAIL_COUNTER_DIAGNOSTIC',
                                    query=query,repetition=repetition,mode=mode,physical_native_calls=tracker.total,
                                    upstream_stats_calls=stats.calls,native_call_map=dict(tracker.calls))))
                                raise
                            measured[mode]=dict(prediction=float(prediction),total_ms=elapsed*1000,
                                inference_ms=inference['seconds']*1000,expectation_calls=inference['calls'],
                                native_calls=tracker.total,upstream_stats_calls=stats.calls,
                                upstream_omitted_calls=omitted,native_call_map=dict(tracker.calls),bridge_ms=stats.total_time*1000,
                                physical_native_ns=tracker.nanoseconds)
                        py,cp=measured['python'],measured['cpp']
                        reference=references[(query['group'],query['query_no'])]
                        try:
                            relative=check_triplet(py['prediction'],cp['prediction'],reference,cp['native_calls'])
                        except ValueError:
                            write_json(directory/'prediction_failure.json',seal(dict(status='FAIL',query=query,
                                repetition=repetition,ordinal=ordinal,reference=reference,measured=measured)))
                            raise
                        if repetition<0:
                            warmup_calls+=cp['native_calls'];continue
                        max_relative=max(max_relative,relative)
                        rows.append(dict(query,repetition=repetition,ordinal=ordinal,
                            python_prediction=py['prediction'],cpp_prediction=cp['prediction'],v3_csv_prediction=reference,
                            python_total_ms=py['total_ms'],cpp_total_ms=cp['total_ms'],
                            python_inference_ms=py['inference_ms'],cpp_inference_ms=cp['inference_ms'],
                            cpp_native_bridge_ms=cp['bridge_ms'],python_expectation_calls=py['expectation_calls'],
                            cpp_physical_native_ns=cp['physical_native_ns'],cpp_physical_native_ms=cp['physical_native_ns']/1e6,
                            cpp_expectation_calls=cp['expectation_calls'],generated_spn_calls=cp['native_calls'],
                            upstream_stats_calls=cp['upstream_stats_calls'],upstream_omitted_calls=cp['upstream_omitted_calls'],
                            native_call_map=cp['native_call_map']))
                    print('CANONICAL_NATIVE_ROUND_PASS',repetition,len(workload),flush=True)
            adaptation=dict(adaptation)
    finally:
        if dll_directory is not None:dll_directory.close()
        sys.modules.pop('optimized_inference',None)
    require_round_grid(rows,workload,config['repetitions'])
    if inputs(config['repetitions'],True)[0]!=config:
        raise ValueError('Inputs/legacy bytes changed during native inference')
    cells=figure8_groups(rows,config['repetitions'])
    if sum(cell['unique_queries'] for cell in cells)!=413:
        raise ValueError('Figure8 query subset differs')
    jsonl=directory/'all_753_repeated.jsonl'
    with jsonl.open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
    csv_path=directory/'all_753_repeated.csv'
    with csv_path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader()
        for row in rows:writer.writerow(dict(row,native_call_map=json.dumps(row['native_call_map'],sort_keys=True)))
    write_json(directory/'figure8_grouped_timings.json',seal(dict(status='PASS',groups=cells,
        scope='Shared host; original total/inference/bridge definitions plus every successful pybind call wall; encoding/SQL parse excluded',
        figure8_primary_native_timer='cpp_physical_native_ms')))
    result=seal(dict(status='PASS',protocol=PROTOCOL,binding=digest(config),configuration=config,
        queries=753,paired_predictions=len(rows),repetitions=config['repetitions'],warmup_rounds=1,
        warmup_successful_native_calls=warmup_calls,minimum_native_calls_per_query=min(r['generated_spn_calls'] for r in rows),
        successful_native_calls=sum(r['generated_spn_calls'] for r in rows),
        upstream_stats_calls=sum(r['upstream_stats_calls'] for r in rows),
        upstream_omitted_successful_native_calls=sum(r['upstream_omitted_calls'] for r in rows),
        successful_native_wall_ns=sum(r['cpp_physical_native_ns'] for r in rows),
        max_three_way_relative_difference=max_relative,native_exports=6,actual_worker_hash_fingerprints=hashes,
        range_adapter=adaptation,timing_ms=timing_summary(rows),figure8_public_groups=cells,
        total_timer_scope='Cardinality/probabilistic compilation and factor evaluation; SQL parse excluded',
        inference_timer_scope='Same rspn.expectation boundary; evidence/scope, condition conversion, recursive/native evaluation and wrapping',
        native_bridge_timer_scope='Original GenCodeStats recorded subset: module lookup, successful native call, counter instrumentation and NumPy wrapping; conversion excluded; some author paths omit statistics',
        physical_native_timer_scope='Sum around every successful original pybind export call using perf_counter_ns: includes Python-to-C++ argument conversion, native evaluation and result conversion; excludes module lookup, evidence conversion, NumPy wrapping and counter updates',
        figure8_primary_native_timer='cpp_physical_native_ms',
        full_paper_reproduction_complete=False,native_regenerated_or_recompiled=False,
        legacy_tree_unchanged=True,original_model_unchanged=True,
        artifacts=[record(path,directory) for path in [jsonl,csv_path,directory/'figure8_grouped_timings.json']]))
    write_json(directory/'worker_result.json',result)
    return result


def verify(repetitions=3):
    config,workload,_,_=inputs(repetitions,True)
    directory=OUT/('model_'+MODEL_SHA[:16]+'_'+digest(config)[:16])
    receipt_path=directory/'verification.json'
    if receipt_path.exists():
        result=read_json(receipt_path);require_seal(result)
        if result.get('status')!='PASS' or result.get('configuration')!=config:
            raise ValueError('Existing v3 native result binding differs')
        validate_assets(result['output_artifacts'],directory)
        rows=[json.loads(line) for line in (directory/'all_753_repeated.jsonl').read_text().splitlines()]
        require_round_grid(rows,workload,repetitions)
        return dict(result,reused_verified_comparison=True)
    directory.mkdir(parents=True,exist_ok=True)
    write_json(directory/'input_binding.json',config)
    snapshot=directory/'source_snapshot'
    snapshot.mkdir(exist_ok=True)
    for name in ['full_cpp_v3.py','full_cpp_range_adapter.py','full_cpp_scale.py','full_factor_cache.py',
                 'full_stable_selection.py','full_evaluation_v3.py','full_canonical_acceptance.py']:
        (snapshot/name).write_bytes((ROOT/'code'/name).read_bytes())
    resource=run_guarded([sys.executable,'-B',str(Path(__file__).resolve()),'_worker','--directory',str(directory)],directory)
    if resource['returncode'] or resource['stopped_for_memory']:
        raise RuntimeError('Native v3 worker failed/capped; preserved logs in '+str(directory))
    result=read_json(directory/'worker_result.json');require_seal(result)
    if result.get('status')!='PASS' or result.get('configuration')!=config or result.get('paired_predictions')!=753*repetitions:
        raise ValueError('Worker result binding/count differs')
    validate_assets(result['artifacts'],directory)
    if inputs(repetitions,True)[0]!=config:
        raise ValueError('Final source/assets/acceptance changed')
    artifacts=tree_records(directory)
    final=seal(dict(result,resource=resource,output_artifacts=artifacts,
        scope='Canonical v3 70+683 public queries, six-SPN 10M model, sealed binary reuse; not full paper',
        legacy_v2_results_preserved=True))
    write_json(receipt_path,final)
    validate_assets(final['output_artifacts'],directory)
    write_json(OUT/'latest.json',seal(dict(status='PASS',path=receipt_path.relative_to(ROOT).as_posix(),sha256=sha(receipt_path))))
    return final


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preflight','verify','_worker'])
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--directory',type=Path)
    args=parser.parse_args()
    if args.action=='_worker':
        result=worker(args.directory)
    elif args.action=='preflight':
        config,workload,_,_=inputs(args.repetitions,False)
        result=seal(dict(status='PASS_READ_ONLY_PREFLIGHT_NOT_FORMAL_ACCEPTANCE',queries=len(workload),configuration=config,
                         formal_acceptance_required=True,native_inference_performed=False))
        write_json(OUT/('preflight_'+digest(config)[:16]+'.json'),result)
    else:
        result=verify(args.repetitions)
    print(json.dumps(dict(status=result['status'],queries=result.get('queries'),paired_predictions=result.get('paired_predictions'),
        successful_native_calls=result.get('successful_native_calls'),minimum_native_calls_per_query=result.get('minimum_native_calls_per_query'),
        maximum_relative_difference=result.get('max_three_way_relative_difference'),reused=result.get('reused_verified_comparison',False))))


if __name__=='__main__':
    main()
