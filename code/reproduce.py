"""Run the official JOB-light relationship baseline with explicit local paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / 'code'
OUTPUT = ROOT / 'output'


def run_stage(name, arguments):
    log = OUTPUT / 'logs' / (name + '.log')
    env = dict(os.environ, PYTHONHASHSEED='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='4', LOKY_MAX_CPU_COUNT='4', PYTHONUTF8='1')
    command = [sys.executable, '-u', str(CODE / 'maqp.py')] + [str(a) for a in arguments]
    print('Starting', name, flush=True)
    start = time.perf_counter()
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.run(command, cwd=OUTPUT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if process.returncode:
        raise RuntimeError('%s failed; see %s' % (name, log))
    elapsed = time.perf_counter() - start
    print('Finished %s in %.1f seconds' % (name, elapsed), flush=True)
    return dict(command=[part.replace(str(ROOT), '${PROJECT_ROOT}') for part in command],
                seconds=elapsed, log=log.relative_to(ROOT).as_posix())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['all', 'prepare', 'train', 'evaluate'], default='all', nargs='?')
    parser.add_argument('--samples', type=int, default=1000000)
    args = parser.parse_args()
    if args.samples < 100:
        parser.error('--samples must be at least 100')
    for directory in ['logs', 'models', 'results']:
        (OUTPUT / directory).mkdir(exist_ok=True, parents=True)
    hdf = OUTPUT / 'hdf'
    model = OUTPUT / 'models' / ('ensemble_relationships_imdb-light_%d.pkl' % args.samples)
    common = ['--dataset', 'imdb-light', '--csv_path', ROOT / 'data' / 'imdb',
              '--hdf_path', hdf, '--max_rows_per_hdf_file', '100000000']
    record_path = OUTPUT / 'results' / ('run_%d.json' % args.samples)
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    record.update(dataset='JOB-light', strategy='relationship', samples_per_spn=args.samples,
                  rdc_threshold=0.3, numpy_seed=1, python_hash_seed=1,
                  scope='Official base ensemble; not the optimized RDC ensemble or full paper reproduction.')

    def save():
        record_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    if args.stage == 'prepare' or (args.stage == 'all' and not model.exists() and not (hdf / 'meta_data.pkl').exists()):
        record['prepare'] = run_stage('prepare', common + ['--generate_hdf', '--csv_seperator', ','])
        save()
    if args.stage == 'train' or (args.stage == 'all' and not model.exists()):
        record['train'] = run_stage('train_%d' % args.samples, common + [
            '--generate_ensemble', '--ensemble_strategy', 'relationship',
            '--samples_per_spn', args.samples, args.samples, args.samples, args.samples, args.samples,
            '--ensemble_path', OUTPUT / 'models', '--post_sampling_factor', 10, 10, 5, 1, 1])
        save()
    if args.stage in ['all', 'evaluate']:
        record['evaluate'] = run_stage('evaluate_%d' % args.samples, common + [
            '--evaluate_cardinalities', '--max_variants', 1, '--ensemble_location', model,
            '--target_path', OUTPUT / 'results' / ('job_light_%d.csv' % args.samples),
            '--query_file_location', CODE / 'benchmarks/job-light/sql/job_light_queries.sql',
            '--ground_truth_file_location', CODE / 'benchmarks/job-light/sql/job_light_true_cardinalities.csv'])
        record['model_sha256'] = hashlib.sha256(model.read_bytes()).hexdigest()
        save()
        subprocess.run([sys.executable, str(CODE / 'verify_results.py'), '--samples', str(args.samples)], check=True)


if __name__ == '__main__':
    main()
