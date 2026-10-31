"""Build and verify generated inference without changing the original model."""
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import time


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / 'output/full/cpp'
COMPILER = ROOT / '.runtime/w64devkit/bin/g++.exe'
ORIGINAL = ROOT / 'output/models/ensemble_relationships_imdb-light_1000000.pkl'
TEMPLATE = ROOT / 'code/rspn/code_generation/templates/identity_leave.cpp'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                         encoding='utf-8')
    os.replace(str(temporary), str(path))


def copy_model(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Source model and generated model must be different paths')
    before = file_hash(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(source), str(destination))
    if file_hash(source) != before or file_hash(destination) != before:
        raise ValueError('Model copy failed its SHA256 check')
    return {'source': str(source), 'source_sha256': before, 'copy': str(destination),
            'copy_sha256_before_id_assignment': before}


def check_prediction_pairs(python_values, cpp_values, calls, rtol=1e-5, atol=1e-6):
    if not python_values or not (len(python_values) == len(cpp_values) == len(calls)):
        return {'status': 'FAIL', 'reason': 'Prediction lengths are empty or different'}
    failures = []
    relative_errors = []
    for index, (python, cpp, count) in enumerate(zip(python_values, cpp_values, calls)):
        finite = math.isfinite(python) and math.isfinite(cpp)
        if not finite or count <= 0 or not math.isclose(python, cpp, rel_tol=rtol, abs_tol=atol):
            failures.append(index)
        if finite:
            relative_errors.append(abs(python - cpp) / max(abs(python), atol))
    return {'status': 'PASS' if not failures else 'FAIL', 'queries': len(calls),
            'failed_query_numbers': failures, 'generated_calls': int(sum(calls)),
            'minimum_calls_per_query': int(min(calls)), 'rtol': rtol, 'atol': atol,
            'maximum_relative_difference': max(relative_errors) if relative_errors else None}


def run_command(arguments, directory, label):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    environment = dict(os.environ, PATH=str(COMPILER.parent) + os.pathsep + os.environ.get('PATH', ''))
    result = subprocess.run([str(x) for x in arguments], cwd=str(directory),
                            capture_output=True, text=True, errors='replace', env=environment)
    record = {'arguments': [str(x) for x in arguments], 'cwd': str(directory),
              'returncode': result.returncode, 'elapsed_seconds': time.perf_counter() - started,
              'stdout': result.stdout, 'stderr': result.stderr}
    write_json(directory / (label + '.json'), record)
    return record


def boundary_differential(directory, cases=None):
    """Compare an actual compiled generated numeric leaf to Python likelihood."""
    import numpy as np
    from spn.structure.StatisticalTypes import MetaType
    from rspn.code_generation.generate_code import generate_code
    from rspn.structure.leaves import IdentityNumericLeaf, identity_likelihood_range
    from rspn.algorithms.ranges import NumericRange

    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if cases is None:
        cases = [(-float('inf'), 3.0, True, False), (-float('inf'), 1.0, True, False),
                 (-float('inf'), 5.0, True, False), (1.0, 5.0, False, False),
                 (3.0, 3.0, True, True), (3.0, 3.0, False, True),
                 (3.0, 3.0, True, False), (10.0, 20.0, False, False),
                 (-10.0, 0.0, True, False), (-float('inf'), float('inf'), True, True),
                 (-99.0, -99.0, True, True), (-99.0, 3.0, True, True)]
    leaf = IdentityNumericLeaf([-99.0, 1.0, 3.0, 5.0], [0.1, 0.2, 0.3, 0.4], -99.0, [0])
    method, _ = generate_code(0, leaf, [MetaType.REAL], 'float')
    lines = ['#include <vector>', '#include <algorithm>', '#include <iostream>',
             '#include <iomanip>', 'using namespace std;', method,
             'int main(){cout << setprecision(17);']
    python_values = []
    serialized_cases = []
    for left, right, left_included, right_included in cases:
        numeric = NumericRange([[left, right]], [[left_included, right_included]], null_value=-99.0)
        evidence = np.empty((1, 1), dtype=object)
        evidence[0, 0] = numeric
        python_values.append(float(identity_likelihood_range(leaf, evidence)[0, 0]))
        arguments = ['vector<bool>{true}', 'vector<bool>{false}', 'false',
                     str(math.isinf(left)).lower(), str(0.0 if math.isinf(left) else left),
                     str(math.isinf(right)).lower(), str(0.0 if math.isinf(right) else right),
                     str(left_included).lower(), str(right_included).lower(), '-99.0']
        lines.append('cout << spn0(' + ','.join(arguments) + ') << "\\n";')
        serialized_cases.append({'left': str(left), 'right': str(right),
                                 'left_included': left_included, 'right_included': right_included})
    lines.append('return 0;}')
    source, executable = directory / 'numeric_boundary.cpp', directory / 'numeric_boundary.exe'
    source.write_text('\n'.join(lines), encoding='utf-8')
    compiled = run_command([COMPILER, '-std=c++11', '-O1', '-D_GLIBCXX_ASSERTIONS',
                            '-static-libgcc', '-static-libstdc++', source, '-o', executable],
                           directory, 'compile')
    if compiled['returncode'] != 0:
        raise RuntimeError('Boundary C++ compilation failed: ' + compiled['stderr'][-2000:])
    executed = run_command([executable], directory, 'execute')
    cpp_values = [float(x) for x in executed['stdout'].splitlines() if x.strip()]
    if executed['returncode'] != 0:
        check = {'status': 'FAIL', 'reason': 'Boundary executable failed or asserted',
                 'returncode': executed['returncode']}
    else:
        check = check_prediction_pairs(python_values, cpp_values, [1] * len(cpp_values), rtol=1e-6)
    result = {'status': check['status'], 'check': check, 'template_sha256': file_hash(TEMPLATE),
              'source_sha256': file_hash(source), 'cases': []}
    for index, (case, python) in enumerate(zip(serialized_cases, python_values)):
        result['cases'].append(dict(case, python=python,
                                    cpp=cpp_values[index] if index < len(cpp_values) else None))
    write_json(directory / 'boundary_verification.json', result)
    return result


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(str(previous))


def build_extension(floating_type='double'):
    """Use the original generator on a copied model, then compile one process."""
    import pybind11
    from ensemble_compilation.spn_ensemble import read_ensemble
    from rspn.code_generation.generate_code import generate_ensemble_code

    build = CPP / floating_type
    build.mkdir(parents=True, exist_ok=True)
    copy = build / 'ensemble_with_ids.pkl'
    module = build / ('optimized_inference' + sysconfig.get_config_var('EXT_SUFFIX'))
    source = build / 'optimized_inference.cpp'
    receipt = build / 'build.json'
    binding = {'original_model_sha256': file_hash(ORIGINAL),
               'numeric_template_sha256': file_hash(TEMPLATE),
               'generator_sha256': file_hash(ROOT / 'code/rspn/code_generation/generate_code.py'),
               'compiler_sha256': file_hash(COMPILER),
               'runner_sha256': file_hash(Path(__file__).resolve()),
               'floating_type': floating_type, 'pybind11_version': pybind11.__version__,
               'python_version': sys.version, 'optimization': '-O2', 'compile_processes': 1}
    if receipt.exists():
        prior = json.loads(receipt.read_text(encoding='utf-8'))
        if (prior.get('status') == 'PASS' and prior.get('binding') == binding and
                all(path.exists() and file_hash(path) == prior.get(key)
                    for path, key in [(copy, 'copy_sha256_after_id_assignment'),
                                      (source, 'generated_source_sha256'), (module, 'extension_sha256')])):
            return dict(prior, reused_verified_build=True)
    seal = copy_model(ORIGINAL, copy)
    ensemble = read_ensemble(str(copy), build_reverse_dict=True)
    with working_directory(build):
        generate_ensemble_code(ensemble, floating_data_type=floating_type, ensemble_path=str(copy))
    # Make the algorithm header explicit; no original Python generator is edited.
    source.write_text('#include <cstdint>\n#include <algorithm>\n' + source.read_text(encoding='utf-8'), encoding='utf-8')
    python_library = Path(sys.base_prefix) / 'libs/python38.lib'
    arguments = [COMPILER, '-O2', '-shared', '-std=c++11', '-ftemplate-depth=2048',
                 '-static-libgcc', '-static-libstdc++', '-I' + pybind11.get_include(),
                 '-I' + sysconfig.get_path('include'), source, python_library, '-o', module]
    compiled = run_command(arguments, build, 'compile_extension')
    result = {'status': 'PASS' if compiled['returncode'] == 0 else 'FAIL',
              'binding': binding, 'seal': seal, 'copy_sha256_after_id_assignment': file_hash(copy),
              'generated_source_sha256': file_hash(source), 'generated_source_bytes': source.stat().st_size,
              'module_path': str(module), 'model_copy': str(copy), 'spns': len(ensemble.spns),
              'compile_returncode': compiled['returncode'], 'compile_seconds': compiled['elapsed_seconds'],
              'original_model_unchanged': file_hash(ORIGINAL) == seal['source_sha256']}
    if compiled['returncode'] == 0:
        result['extension_sha256'] = file_hash(module)
    write_json(receipt, result)
    if not result['original_model_unchanged']:
        raise RuntimeError('Original model SHA256 changed during code generation')
    if result['status'] != 'PASS':
        raise RuntimeError('Extension compilation failed; see ' + str(build / 'compile_extension.json'))
    return result


def verify_extension(build, repetitions=5):
    """Fresh factor cache per query, one warm-up round, then repeated paired runs."""
    import numpy as np
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.cardinality_evaluation import GenCodeStats
    from evaluation.utils import parse_query
    from schemas.imdb.schema import gen_job_light_imdb_schema

    if repetitions < 2:
        raise ValueError('At least two timed repetitions are required')
    original_hash = file_hash(ORIGINAL)
    if original_hash != build['binding']['original_model_sha256']:
        raise ValueError('Source model no longer matches the compilation binding')
    module_path = Path(build['module_path'])
    model_copy = Path(build['model_copy'])
    if file_hash(module_path) != build['extension_sha256'] or file_hash(model_copy) != build['copy_sha256_after_id_assignment']:
        raise ValueError('Compiled module or copied model changed after compilation')
    specification = importlib.util.spec_from_file_location('optimized_inference', str(module_path))
    native = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(native)
    sys.modules['optimized_inference'] = native
    python_ensemble = read_ensemble(str(model_copy), build_reverse_dict=True)
    cpp_ensemble = read_ensemble(str(model_copy), build_reverse_dict=True)
    for spn in python_ensemble.spns:
        spn.use_generated_code = False
    cpp_ensemble.use_generated_code()
    benchmark = ROOT / 'code/benchmarks/job-light/sql'
    sql = (benchmark / 'job_light_queries.sql').read_text().splitlines()
    with (benchmark / 'job_light_true_cardinalities.csv').open(newline='') as stream:
        truths = list(csv.DictReader(stream))
    if len(sql) != len(truths) or len(sql) != 70:
        raise ValueError('Expected exactly 70 aligned JOB-light queries')
    for index, (query, truth) in enumerate(zip(sql, truths)):
        if query.strip() != truth['query'].strip() or truth['query_no'] != str(index):
            raise ValueError('JOB-light SQL/truth mismatch')
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    rows = []
    python_predictions, cpp_predictions, cpp_calls = [], [], []
    for repetition in range(-1, repetitions):
        for index, query_sql in enumerate(sql):
            measured = {}
            # Alternate ordering to reduce systematic scheduling/order advantage.
            order = [('python', python_ensemble), ('cpp', cpp_ensemble)]
            if repetition % 2:
                order.reverse()
            for mode, ensemble in order:
                ensemble.cached_expecation_vals = {}
                stats = GenCodeStats()
                query = parse_query(query_sql.strip(), schema)
                started = time.perf_counter()
                _, _, prediction, _ = ensemble.cardinality(
                    query, max_variants=1, merge_indicator_exp=True, exploit_overlapping=True,
                    return_factor_values=True, gen_code_stats=stats)
                measured[mode] = {'prediction': float(prediction),
                                  'total_ms': (time.perf_counter() - started) * 1000,
                                  'generated_calls': stats.calls,
                                  'inference_ms': stats.total_time * 1000}
            if repetition < 0:
                continue
            py, cpp = measured['python'], measured['cpp']
            python_predictions.append(py['prediction'])
            cpp_predictions.append(cpp['prediction'])
            cpp_calls.append(cpp['generated_calls'])
            rows.append({'repetition': repetition, 'query_no': index, 'query': query_sql,
                         'cardinality_true': int(truths[index]['cardinality_true']),
                         'python_prediction': py['prediction'], 'cpp_prediction': cpp['prediction'],
                         'python_total_ms': py['total_ms'], 'cpp_total_ms': cpp['total_ms'],
                         'cpp_inference_ms': cpp['inference_ms'],
                         'generated_spn_calls': cpp['generated_calls']})
    comparison = check_prediction_pairs(python_predictions, cpp_predictions, cpp_calls)
    result_path = Path(build['module_path']).parent / 'job_light_repeated.csv'
    with result_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    timing = {}
    for column in ['python_total_ms', 'cpp_total_ms', 'cpp_inference_ms']:
        values = [row[column] for row in rows]
        timing[column] = {'mean': float(np.mean(values)), 'median': float(np.median(values)),
                          'p95': float(np.percentile(values, 95))}
    boundary = boundary_differential(CPP / 'boundary_after_fix')
    preserved = file_hash(ORIGINAL) == original_hash
    status = 'PASS' if comparison['status'] == boundary['status'] == 'PASS' and preserved else 'FAIL'
    report = {'status': status, 'verified_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Generated inference verification on existing 1M relationship model; not Figure 8 or full-paper reproduction',
              'full_paper_reproduction_complete': False, 'queries': 70, 'timed_repetitions': repetitions,
              'warmup_rounds': 1, 'cache_policy': 'Reset factor expectation cache before every query in both modes',
              'query_sql_parse_in_timed_region': False,
              'inference_timer_scope': 'Upstream GenCodeStats includes module lookup/call and NumPy result wrapping; condition conversion excluded',
              'timing_environment': 'Shared machine while other independent reproduction work may run; no paper speed claim',
              'comparison': comparison, 'boundary': boundary,
              'timing_ms': timing, 'build': build,
              'original_model_sha256_before': original_hash,
              'original_model_sha256_after': file_hash(ORIGINAL), 'original_model_unchanged': preserved,
              'rows_csv': str(result_path.relative_to(ROOT)), 'rows_csv_sha256': file_hash(result_path),
              'query_sha256': file_hash(benchmark / 'job_light_queries.sql'),
              'truth_sha256': file_hash(benchmark / 'job_light_true_cardinalities.csv')}
    write_json(ROOT / 'output/full/results/cpp_verification.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['boundary', 'build', 'verify', 'all'])
    parser.add_argument('--label', default='boundary_current')
    parser.add_argument('--floating-type', choices=['float', 'double'], default='double')
    parser.add_argument('--repetitions', type=int, default=5)
    args = parser.parse_args()
    if os.environ.get('PYTHONHASHSEED') != '1':
        environment = dict(os.environ, PYTHONHASHSEED='1', OMP_NUM_THREADS='1',
                           OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        return subprocess.call([sys.executable, str(Path(__file__).resolve())] + sys.argv[1:], env=environment)
    if '/' in args.label or '\\' in args.label or args.label in ('.', '..'):
        parser.error('label must be a directory name')
    if args.action == 'boundary':
        report = boundary_differential(CPP / args.label)
    else:
        build = build_extension(args.floating_type)
        report = build if args.action == 'build' else verify_extension(build, args.repetitions)
    print(json.dumps({'status': report['status'], 'queries': report.get('queries'),
                      'comparison': report.get('comparison'), 'timing_ms': report.get('timing_ms'),
                      'original_model_unchanged': report.get('original_model_unchanged')}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
