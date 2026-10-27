"""Repeat the base ensemble with independent training seeds and isolated outputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / 'code'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed', type=int, required=True, choices=[2, 3])
parser.add_argument('--samples', type=int, nargs='+', default=[10000, 100000, 1000000])
parser.add_argument('--timeout', type=int, default=900)
args = parser.parse_args()
env = dict(os.environ, PYTHONHASHSEED='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
           MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='4', LOKY_MAX_CPU_COUNT='4', PYTHONUTF8='1')
def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()
for n in args.samples:
    output = ROOT / 'output/seed_experiments' / ('seed_%d' % args.seed) / ('samples_%d' % n)
    record_path = output / 'run.json'
    if record_path.exists():
        previous = json.loads(record_path.read_text())
        if previous.get('status') == 'PASS':
            print('Already verified:', args.seed, n, flush=True)
            continue
        raise RuntimeError('Incomplete previous run requires inspection: ' + str(output))
    for name in ['models', 'results', 'logs']:
        (output / name).mkdir(parents=True, exist_ok=True)
    record = dict(seed=args.seed, samples=n, python_hash_seed=1, status='RUNNING', started_at=now(),
                  scope='Vary NumPy and Python training RNG only; reuse fixed full HDF; evaluation seed 1.',
                  files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [CODE/'maqp.py',CODE/'repeat_seeds.py',CODE/'verify_results.py',ROOT/'data/manifest.json']})
    start = time.perf_counter()
    def save():
        record_path.write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    save()
    common = ['--dataset','imdb-light','--csv_path',ROOT/'data/imdb','--hdf_path',ROOT/'output/hdf',
              '--max_rows_per_hdf_file','100000000']
    model = output/'models'/('ensemble_relationships_imdb-light_%d.pkl'%n)
    stages = [
       ('train',[CODE/'maqp.py']+common+['--seed',args.seed,'--generate_ensemble','--ensemble_strategy','relationship',
         '--samples_per_spn',n,n,n,n,n,'--ensemble_path',output/'models','--post_sampling_factor',10,10,5,1,1]),
       ('evaluate',[CODE/'maqp.py']+common+['--evaluate_cardinalities','--max_variants',1,
         '--ensemble_location',model,'--target_path',output/'results'/('job_light_%d.csv'%n),
         '--query_file_location',CODE/'benchmarks/job-light/sql/job_light_queries.sql',
         '--ground_truth_file_location',CODE/'benchmarks/job-light/sql/job_light_true_cardinalities.csv']),
       ('verify',[CODE/'verify_results.py','--samples',n,'--output-root',output])]
    try:
        for name, arguments in stages:
            command = [sys.executable,'-u']+list(map(str,arguments))
            print('START',args.seed,n,name,flush=True)
            stage_start = time.perf_counter()
            with (output/'logs'/(name+'.log')).open('w',encoding='utf-8') as log:
                proc = subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
                record['active_pid']=proc.pid
                save()
                try:
                    code = proc.wait(timeout=max(1,args.timeout-(time.perf_counter()-start)))
                except subprocess.TimeoutExpired:
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=log)
                    proc.wait(timeout=30)
                    raise RuntimeError('Run exceeded timeout')
            record[name]=dict(command=command,seconds=time.perf_counter()-stage_start,returncode=code)
            save()
            if code:
                raise RuntimeError('Stage failed: '+name)
        record['status']='PASS'
        record['model_sha256']=hashlib.sha256(model.read_bytes()).hexdigest()
        record['verification']=json.loads((output/'results'/('verification_%d.json'%n)).read_text())
    except BaseException as exc:
        record['status']='FAILED_OR_STOPPED'
        record['error']=str(exc)
        raise
    finally:
        record['seconds']=time.perf_counter()-start
        record['ended_at']=now()
        save()
    print('PASS',args.seed,n,round(record['seconds'],2),flush=True)
