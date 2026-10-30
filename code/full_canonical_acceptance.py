"""Final four-process acceptance above the frozen canonical evaluator.

Checks actual seed0 generation, distinct reference-matched process hash values,
and worker artifacts bound to every current baseline/replay. Per-label status
must use this gate rather than assuming three replay files prove four seeds.
"""
from functools import lru_cache
import json
import os
import subprocess
import sys

from full_common import ROOT, FULL, atomic_json, file_sha256, load_json
from full_evaluation_v3 import checked_summary, require_sealed, seal, verify

WORDS = ['DeepDB canonical selection', 'movie_keyword', 'movie_companies']


def require_seed_zero_baseline(result):
    groups = result.get('groups', {})
    if not groups or any(group.get('generation_hash_seed') != '0' for group in groups.values()):
        raise ValueError('seed0 inference is absent from the generated baseline')


@lru_cache(maxsize=4)
def reference_fingerprints(seed):
    script = 'import json; words=' + repr(WORDS) + '; print(json.dumps({w:hash(w) for w in words}))'
    raw = subprocess.check_output([sys.executable, '-c', script],
                                  env=dict(os.environ, PYTHONHASHSEED=str(seed)),
                                  text=True, encoding='utf-8')
    return json.loads(raw)


@lru_cache(maxsize=2)
def validated_aggregate(expected_sha256, runner_sha256, evaluator_sha256):
    path = FULL / 'results/canonical_inference_verification.json'
    if file_sha256(path) != expected_sha256:
        raise ValueError('four-process verification changed during acceptance')
    aggregate = load_json(path)
    require_sealed(aggregate, dict(status='PASS_FOUR_INDEPENDENT_HASH_SEEDS', hash_seeds=[0, 1, 2, 3]))
    labels = aggregate.get('labels', [])
    if not labels or len(set(labels)) != len(labels) or len(aggregate.get('contexts', [])) != 4:
        raise ValueError('four-process labels/contexts are missing or duplicated')
    fingerprints = []
    for seed, context in zip([0, 1, 2, 3], aggregate['contexts']):
        require_sealed(context, dict(status='PASS', hash_seed=str(seed), labels=labels,
                                    worker_source_sha256=runner_sha256, evaluator_source_sha256=evaluator_sha256))
        actual_context = load_json(FULL / 'canonical_run' / ('seed%d_complete.json' % seed))
        if actual_context != context or context.get('hash_fingerprints') != reference_fingerprints(seed):
            raise ValueError('actual process hash fingerprint or context differs')
        fingerprints.append(tuple(sorted(context['hash_fingerprints'].items())))
        expected = ['output/full/results/' + label + '_evaluation_v3.json' for label in labels]
        if seed:
            expected += ['output/full/results/' + label + '_replay_v3_seed%d.json' % seed for label in labels]
        artifacts = context.get('artifacts', [])
        actual = [r['path'] for r in artifacts]
        if len(actual) != len(expected) or len(set(actual)) != len(actual) or set(actual) != set(expected):
            raise ValueError('process artifact set is incomplete, duplicated or unexpected')
        for item in artifacts:
            if file_sha256(ROOT / item['path']) != item['sha256']:
                raise ValueError('process artifact does not bind the current baseline/replay')
    if len(set(fingerprints)) != 4:
        raise ValueError('process hash fingerprints are not distinct')
    return aggregate


def recheck_label_artifacts(aggregate, label):
    """Never cache checks of mutable per-label files or worker contexts."""
    for seed, context in zip([0, 1, 2, 3], aggregate['contexts']):
        actual_context = load_json(FULL / 'canonical_run' / ('seed%d_complete.json' % seed))
        if actual_context != context:
            raise ValueError('process context changed after aggregate validation')
        required = ['output/full/results/' + label + '_evaluation_v3.json']
        if seed:
            required.append('output/full/results/' + label + '_replay_v3_seed%d.json' % seed)
        artifacts = {record['path']: record['sha256'] for record in context['artifacts']}
        for path in required:
            if path not in artifacts or file_sha256(ROOT / path) != artifacts[path]:
                raise ValueError('current label artifact changed after aggregate validation')


def verify_current(label, queries):
    aggregate_path = FULL / 'results/canonical_inference_verification.json'
    if not aggregate_path.exists():
        raise ValueError('four-process final acceptance is pending')
    aggregate = validated_aggregate(file_sha256(aggregate_path),
                                     file_sha256(ROOT / 'code/full_evaluation_v3_run.py'),
                                     file_sha256(ROOT / 'code/full_evaluation_v3.py'))
    if label not in aggregate['labels']:
        raise ValueError('label is not bound to the four-process acceptance')
    recheck_label_artifacts(aggregate, label)
    result = verify(label, queries)
    require_seed_zero_baseline(result)
    return result


def main():
    path = FULL / 'results/canonical_inference_verification.json'
    aggregate = load_json(path)
    if aggregate is None:
        raise ValueError('canonical four-process run is still pending')
    summaries = []
    for label in aggregate['labels']:
        result = checked_summary(label)
        verify_current(label, result['queries'])
        summaries.append(dict(label=label, queries=result['queries'], binding=result['binding']))
    result = seal(dict(status='PASS_CURRENT_CANONICAL_FOUR_SEED_ACCEPTANCE',
                       parent_verification_sha256=file_sha256(path),
                       acceptance_source_sha256=file_sha256(__file__), models=summaries,
                       full_paper_reproduction_complete=False))
    atomic_json(FULL / 'results/canonical_final_acceptance.json', result)
    print(result['status'], len(summaries))


if __name__ == '__main__':
    main()
