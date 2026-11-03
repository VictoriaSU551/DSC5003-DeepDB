"""Input-bound namespace for future training/recovery, preserving legacy runs.

Planning seals the actual raw/prepared files. Execution requires that exact
plan and checks the same inputs again after training. Legacy components and
unqualified RDC selection receipts are never imported into this namespace.
"""
import argparse
from contextlib import contextmanager
import importlib.metadata
import json
import platform

import full_training as training
from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_prepared_seal import input_binding


@contextmanager
def guarded_namespace(identifier, profile):
    old = {name: getattr(training, name) for name in
           ['FULL', 'HDF', 'SELECTION', 'PAIRWISE', 'PROFILE', 'algorithm_seal']}
    directory = FULL / 'guarded_training' / profile / identifier
    try:
        training.FULL = directory
        training.HDF = FULL / 'prepared' / ('hdf' if profile == 'joblight' else 'public-scale/hdf')
        training.SELECTION = directory / 'checkpoints/rdc_selection.json'
        training.PAIRWISE = directory / 'models/pairwise_rdc.pkl'
        training.PROFILE = profile
        training.algorithm_seal = lambda: identifier
        yield directory
    finally:
        for name, value in old.items():
            setattr(training, name, value)


def runtime_seal():
    versions = dict(python=platform.python_version())
    for name in ['numpy', 'scipy', 'pandas', 'spflow', 'scikit-learn', 'networkx']:
        versions[name] = importlib.metadata.version(name)
    return dict(versions=versions, guard_sha256=file_sha256(__file__))


def make_plan(profile, strategy, samples, budget):
    return dict(protocol='actual_prepared_inputs_bound_training_v1', profile=profile,
                strategy=strategy, samples=samples, budget=budget,
                prepared_input_binding=input_binding(profile), **runtime_seal())


def execute(plan):
    runtime = runtime_seal()
    if any(plan.get(key) != value for key, value in runtime.items()):
        raise ValueError('runtime versions or training guard changed after plan')
    identifier = binding_hash(plan)
    profile = plan['profile']
    state_path = FULL / 'guarded_training' / profile / identifier / 'state.json'
    previous = load_json(state_path, {})
    if previous.get('status') in ['TAINTED', 'RUNNING']:
        raise ValueError('TAINTED or interrupted namespace cannot recover components automatically')
    if input_binding(profile) != plan['prepared_input_binding']:
        raise ValueError('prepared inputs changed after plan')
    with guarded_namespace(identifier, profile) as directory:
        atomic_json(state_path, dict(status='RUNNING', plan_sha256=identifier))
        try:
            atomic_json(directory / 'plan.json', plan)
            training.train(plan['strategy'], plan['samples'], plan['budget'])
            legacy_label = '%s_n%d_b%s' % (plan['strategy'], plan['samples'], str(plan['budget']).replace('.', 'p'))
            if profile != 'joblight':
                legacy_label = profile.replace('-', '_') + '_' + legacy_label
            training_path = directory / 'results' / (legacy_label + '_training.json')
            result = load_json(training_path)
            if input_binding(profile) != plan['prepared_input_binding']:
                raise ValueError('prepared inputs changed during training; result is not released')
            label = 'guarded_' + identifier[:12] + '_' + legacy_label
            selection = directory / 'results' / ('rdc_selection_budget_%s.json' % str(plan['budget']).replace('.', 'p'))
            result.update(label=label, prepared_input_plan_sha256=identifier,
                          prepared_input_plan_path=(directory / 'plan.json').relative_to(ROOT).as_posix(),
                          selection_receipt=dict(path=selection.relative_to(ROOT).as_posix(), sha256=file_sha256(selection))
                          if selection.exists() else None,
                          guard_scope='New input-bound components only; no legacy checkpoint recovery')
            atomic_json(state_path, dict(status='PASS', plan_sha256=identifier, released_label=label))
        except BaseException as error:
            atomic_json(state_path, dict(status='TAINTED', plan_sha256=identifier,
                                         reason=type(error).__name__ + ': ' + str(error)))
            raise
    atomic_json(FULL / 'results' / (label + '_training.json'), result)
    print('GUARDED_TRAINING_COMPLETE', label, flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['joblight', 'public-scale'], default='joblight')
    parser.add_argument('--strategy', choices=['rdc', 'single', 'relationship'], default='rdc')
    parser.add_argument('--samples', type=int, default=10000000)
    parser.add_argument('--budget', type=float, default=.5)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.samples < 100 or args.budget < 0:
        parser.error('samples must be at least 100 and budget must be nonnegative')
    plan = make_plan(args.profile, args.strategy, args.samples, args.budget)
    identifier = binding_hash(plan)
    if not args.execute:
        atomic_json(FULL / 'guarded_training' / args.profile / identifier / 'plan.json', plan)
        print(json.dumps(dict(plan_sha256=identifier, plan=plan), indent=2))
        return
    if args.plan_sha256 != identifier:
        parser.error('--plan-sha256 must match the current complete input plan')
    execute(plan)


if __name__ == '__main__':
    main()
