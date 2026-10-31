"""Run canonical inference and three independent hash-seed reverse replays.

Completed, hash-verified workers are reused. Each fresh worker records actual
Python hash fingerprints before inference; changing an environment string in
an already running interpreter cannot stand in for a new seeded process.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from full_common import ROOT, FULL, atomic_json, file_sha256, load_json
from full_evaluation_v3 import checked_summary, evaluate, require_sealed, seal, verify


def run_worker(seed, labels):
    if os.environ.get('PYTHONHASHSEED') != str(seed):
        raise ValueError('worker must start with the requested hash seed')
    context = dict(status='STARTED', hash_seed=str(seed), labels=labels,
                   hash_fingerprints={word: hash(word) for word in
                                      ['DeepDB canonical selection', 'movie_keyword', 'movie_companies']},
                   worker_source_sha256=file_sha256(__file__),
                   evaluator_source_sha256=file_sha256(ROOT / 'code/full_evaluation_v3.py'))
    directory = FULL / 'canonical_run'
    atomic_json(directory / ('seed%d_started.json' % seed), seal(context))
    artifacts = []
    for label in labels:
        if seed == 0:
            evaluate(label)
        else:
            summary = checked_summary(label)
            replay_path = FULL / 'results' / (label + '_replay_v3_seed%d.json' % seed)
            if replay_path.exists():
                verify(label, summary['queries'], seeds=(seed,))
            else:
                evaluate(label, replay=True)
                verify(label, summary['queries'], seeds=(seed,))
        paths = [FULL / 'results' / (label + '_evaluation_v3.json')]
        if seed != 0:
            paths.append(FULL / 'results' / (label + '_replay_v3_seed%d.json' % seed))
        artifacts.extend(dict(path=p.relative_to(ROOT).as_posix(), sha256=file_sha256(p)) for p in paths)
        import gc
        gc.collect()
    result = seal(dict(context, status='PASS', artifacts=artifacts))
    atomic_json(directory / ('seed%d_complete.json' % seed), result)
    print('CANONICAL_WORKER_COMPLETE', seed, len(labels), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2, 3])
    parser.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    labels = args.labels
    if args.all:
        labels = [load_json(p)['label'] for p in sorted((FULL / 'results').glob('*_evaluation_v2.json'))]
    if not labels:
        parser.error('provide labels or --all')
    if args.worker is not None:
        run_worker(args.worker, labels)
        return
    for seed in args.seeds:
        log = FULL / 'logs' / ('canonical_seed%d.log' % seed)
        log.parent.mkdir(parents=True, exist_ok=True)
        environment = dict(os.environ, PYTHONHASHSEED=str(seed), OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
        with log.open('a', encoding='utf-8') as stream:
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', str(seed), *labels],
                                     cwd=str(ROOT), env=environment, stdout=stream, stderr=subprocess.STDOUT)
        if process.returncode:
            raise SystemExit(process.returncode)
    if set(args.seeds) == {0, 1, 2, 3}:
        for label in labels:
            summary = checked_summary(label)
            verify(label, summary['queries'])
        contexts = [load_json(FULL / 'canonical_run' / ('seed%d_complete.json' % s)) for s in [0, 1, 2, 3]]
        for seed, context in zip([0, 1, 2, 3], contexts):
            require_sealed(context, dict(status='PASS', hash_seed=str(seed), labels=labels))
        fingerprints = [tuple(sorted(c['hash_fingerprints'].items())) for c in contexts]
        if len(set(fingerprints)) != 4:
            raise ValueError('seed processes did not have four distinct actual hash fingerprints')
        result = seal(dict(status='PASS_FOUR_INDEPENDENT_HASH_SEEDS', labels=labels,
                           hash_seeds=[0, 1, 2, 3], contexts=contexts))
        atomic_json(FULL / 'results/canonical_inference_verification.json', result)
        print('CANONICAL_ALL_MODELS_FOUR_SEEDS_PASS', len(labels), flush=True)


if __name__ == '__main__':
    main()
