"""Pure consumer/receipt regressions; no scientific provider execution."""
import copy
import hashlib
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def acceptance():
    assert importlib.util.find_spec('full_ssb_local_ci_acceptance') is not None, \
        'the read-only invocation adapter must exist'
    return importlib.import_module('full_ssb_local_ci_acceptance')


def test_ci_tables_select_readonly_invocation_adapter(monkeypatch):
    import full_ssb_local_ci_tables as tables

    accepted = {'status': 'accepted by fixed invocation spelling'}
    monkeypatch.setitem(sys.modules, 'full_ssb_local_ci_acceptance',
                        SimpleNamespace(verify=lambda: accepted))

    def imported_provider_verify():
        raise ValueError('successful fresh worker process receipt required')

    monkeypatch.setitem(sys.modules, 'full_ssb_local_ci_group_replay',
                        SimpleNamespace(verify=imported_provider_verify))
    assert tables.configuration()['verify']() is accepted


def test_ci_tables_bind_adapter_source_in_derived_artifacts():
    from full_ssb_local_ci_tables import configuration

    assert 'code/full_ssb_local_ci_acceptance.py' in configuration()['helpers']


def receipt_fixture(tmp_path, monkeypatch):
    """Use the original receipt verifier; replace only its scientific source F."""
    import full_ssb_local_ci_group_replay as provider
    from full_ssb_scoped_replay import ScopedReplay
    from full_ssb_replay import atomic, compare_query, coverage, digest, value_hash

    acceptance = importlib.import_module('full_ssb_local_ci_acceptance')
    source_root = Path(__file__).resolve().parents[2]
    root = tmp_path
    code = root/'code'; code.mkdir()
    for name in ('full_ssb_local_ci_group_replay.py', 'full_ssb_scoped_replay.py'):
        (code/name).write_bytes((source_root/'code'/name).read_bytes())
    monkeypatch.setattr(acceptance, 'ROOT', root)
    monkeypatch.chdir(root)
    monkeypatch.setitem(sys.modules, 'full_ssb_scoped_replay',
        SimpleNamespace(__file__=str(code/'full_ssb_scoped_replay.py')))
    entry = root/'code/full_ssb_local_ci_group_replay.py'
    output = tmp_path/'o'
    events, instances = [], []
    queries = [dict(query_no=i, query_name='fixture%d'%i, sql='SELECT %d;'%i,
        groups=[dict(key=[], prediction=1.5, truth=1.5, model_interval=[1., 2.],
            status='MATCHED', zero_truth=False,
            reference_ci=dict(eligible=True, status='ELIGIBLE'))],
        truth_groups=1, model_groups=1, missing_model_groups=0, extra_model_groups=0,
        nonfinite_original_intervals=[]) for i in range(13)]
    snapshot = dict(test_only=True, artifacts=[])

    def source():
        events.append('source-F')
        return snapshot, queries

    def forbidden(*args, **kwargs):
        pytest.fail('read-only acceptance must never execute a model or worker')

    class ObservedReplay(ScopedReplay):
        def verify(self):
            events.append('complete-verify')
            return super().verify()

    def engine():
        value = ObservedReplay(root, output, entry, copy.deepcopy(provider.METADATA),
            'PASS_LOCAL_SSB_10M_CI_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',
            'LOCAL_SSB_10M_CI_REVERSE_REPLAY', 'DEEPDB_SSB_LOCAL_CI_REPLAY_WORKER',
            source, forbidden)
        instances.append(value)
        return value

    initial = engine()
    binding = initial.binding_for(snapshot)
    home = output/'runs'/value_hash(binding)[:20]
    home.mkdir(parents=True)
    comparisons = {}
    for expected in queries:
        index = expected['query_no']
        actual = dict(query_no=index, query_name=expected['query_name'], sql=expected['sql'],
            groups=[dict(key=[], prediction=1.5, model_interval=[1., 2.])],
            nonfinite_original_intervals=[], original_query_evaluator_calls=2, model_loads=1)
        comparison = compare_query(expected, actual)
        path = home/('query_%02d.json'%index)
        atomic(path, dict(actual=actual, comparison=comparison))
        atomic(path.with_suffix('.seal.json'), dict(binding=binding, query_no=index,
            exact_sql_sha256=hashlib.sha256(expected['sql'].encode()).hexdigest(), sha256=digest(path)))
        comparisons[str(index)] = comparison
    files = {p.name:digest(p) for p in home.iterdir()}
    result = dict(provider.METADATA, status=initial.status, stage=initial.stage,
        queries=13, original_query_evaluator_calls=26, model_loads=13,
        execution_order=list(reversed(range(13))), source_snapshot=snapshot, binding=binding,
        directory=home.relative_to(root).as_posix(), query_files_sha256=files,
        comparisons=comparisons, coverage=coverage(dict(queries=queries)),
        environment=dict(PYTHONHASHSEED='173', random_seed=74031, numpy_seed=74031,
            process_id=12345, thread_limits={n:'1' for n in provider.THREAD_LIMITS}))
    atomic(home/'verification.json', result)
    report_sha = digest(home/'verification.json')
    seal = dict(report_sha256=report_sha, binding=binding, query_files_sha256=files)
    atomic(home/'verification_seal.json', seal)
    atomic(home/'lifecycle.json', dict(status='PASS', binding=binding, report_sha256=report_sha))
    atomic(output/'verification.json', result)
    atomic(output/'verification_seal.json', seal)
    atomic(output/'last_run.json', dict(status='PASS', directory=result['directory'], report_sha256=report_sha))
    logs = output/'logs'; logs.mkdir()
    stdout, stderr = logs/'out', logs/'err'
    stdout.write_bytes(b'pure fixture'); stderr.write_bytes(b'')

    def descriptor(path):
        return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=digest(path))

    process = dict(returncode=0, stdout=descriptor(stdout), stderr=descriptor(stderr),
        replay_source_sha256=digest(entry), helper_source_sha256=initial.helper_sha(),
        command=[str(root/'.venv/Scripts/python.exe'), '-B',
            str(Path('code/full_ssb_local_ci_group_replay.py')), 'worker'],
        environment=initial.worker_environment_record(), wall_seconds=1.0, binding=binding,
        report_sha256=report_sha, directory=result['directory'], reported_worker_process_id=12345)
    atomic(output/'last_process.json', process)
    instances.clear()
    monkeypatch.setitem(sys.modules, 'full_ssb_local_ci_group_replay',
        SimpleNamespace(__file__=str(entry), engine=engine))
    return SimpleNamespace(root=root, output=output, engine=engine, result=result,
        process=process, events=events, instances=instances, source=source, forbidden=forbidden)


def test_imported_entry_alias_fails_original_guard_then_adapter_passes_once(tmp_path, monkeypatch, acceptance):
    fixture = receipt_fixture(tmp_path, monkeypatch)
    imported = fixture.engine()
    assert imported.ENTRY.is_absolute()
    with pytest.raises(ValueError, match='successful fresh worker process receipt required'):
        imported.verify()
    fixture.events.clear(); fixture.instances.clear()
    assert acceptance.verify() == fixture.result
    assert fixture.events == ['complete-verify', 'source-F']
    adapted, = fixture.instances
    assert adapted.ENTRY == Path('code/full_ssb_local_ci_group_replay.py')
    assert imported.ENTRY.is_absolute()
    assert adapted.source_snapshot is fixture.source
    assert adapted.execute_query is fixture.forbidden
    assert adapted.metadata == imported.metadata
    assert adapted.worker_environment_record() == imported.worker_environment_record()


@pytest.mark.parametrize('index, replacement', [
    (0, 'another-python.exe'), (1, '-I'), (2, 'code/another_replay.py'),
    (2, 'ABSOLUTE_ENTRY_ALIAS'),
    (3, 'replay')])
def test_adapter_does_not_accept_other_recorded_command_spellings(tmp_path, monkeypatch, acceptance, index, replacement):
    from full_ssb_replay import atomic
    fixture = receipt_fixture(tmp_path, monkeypatch)
    if replacement == 'ABSOLUTE_ENTRY_ALIAS':
        replacement = str(fixture.root/'code/full_ssb_local_ci_group_replay.py')
    fixture.process['command'][index] = replacement
    atomic(fixture.output/'last_process.json', fixture.process)
    with pytest.raises(ValueError, match='successful fresh worker process receipt required'):
        acceptance.verify()
    assert fixture.events == ['complete-verify', 'source-F']


@pytest.mark.parametrize('field, value', [
    ('returncode', True), ('replay_source_sha256', '0'*64),
    ('helper_source_sha256', '0'*64), ('binding', {}), ('report_sha256', '0'*64),
    ('directory', 'another/run'), ('reported_worker_process_id', True),
    ('reported_worker_process_id', 12346), ('environment', {}),
    ('wall_seconds', -1), ('wall_seconds', '1')])
def test_original_noncommand_receipt_checks_remain_required(tmp_path, monkeypatch, acceptance, field, value):
    from full_ssb_replay import atomic
    fixture = receipt_fixture(tmp_path, monkeypatch)
    fixture.process[field] = value
    atomic(fixture.output/'last_process.json', fixture.process)
    with pytest.raises(ValueError, match='successful fresh worker process receipt required'):
        acceptance.verify()
    assert fixture.events == ['complete-verify', 'source-F']


@pytest.mark.parametrize('mutation', ['same_log', 'log_bytes', 'log_sha', 'query_file'])
def test_original_physical_log_and_query_checks_remain_required(tmp_path, monkeypatch, acceptance, mutation):
    from full_ssb_replay import atomic
    fixture = receipt_fixture(tmp_path, monkeypatch)
    if mutation == 'same_log':
        fixture.process['stderr'] = fixture.process['stdout']
    elif mutation == 'log_bytes':
        fixture.process['stdout']['bytes'] += 1
    elif mutation == 'log_sha':
        fixture.process['stderr']['sha256'] = '0'*64
    else:
        home = fixture.root/fixture.result['directory']
        (home/'query_12.json').write_bytes(b'{}')
    atomic(fixture.output/'last_process.json', fixture.process)
    with pytest.raises(ValueError):
        acceptance.verify()


def test_wrong_cwd_fails_before_engine_or_source(tmp_path, monkeypatch, acceptance):
    fixture = receipt_fixture(tmp_path, monkeypatch)
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with pytest.raises(ValueError, match='working directory'):
        acceptance.verify()
    assert fixture.instances == [] and fixture.events == []


@pytest.mark.parametrize('name', ['full_ssb_local_ci_group_replay', 'full_ssb_scoped_replay'])
def test_substituted_module_identity_fails_before_source(tmp_path, monkeypatch, acceptance, name):
    fixture = receipt_fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, name, SimpleNamespace(__file__=str(tmp_path/'elsewhere.py')))
    with pytest.raises(ValueError, match='physical identity'):
        acceptance.verify()
    assert fixture.events == []


def test_engine_with_another_entry_fails_before_complete_verification(tmp_path, monkeypatch, acceptance):
    fixture = receipt_fixture(tmp_path, monkeypatch)
    original_engine = fixture.engine

    def engine():
        value = original_engine()
        value.ENTRY = tmp_path/'another.py'
        return value

    monkeypatch.setitem(sys.modules, 'full_ssb_local_ci_group_replay',
        SimpleNamespace(__file__=str(fixture.root/'code/full_ssb_local_ci_group_replay.py'), engine=engine))
    with pytest.raises(ValueError, match='entry physical identity'):
        acceptance.verify()
    assert fixture.events == []


@pytest.mark.parametrize('changed', ['full_ssb_local_ci_group_replay.py', 'full_ssb_scoped_replay.py'])
def test_actual_changed_source_bytes_fail_before_engine(tmp_path, monkeypatch, acceptance, changed):
    code = tmp_path/'code'; code.mkdir()
    for name in ('full_ssb_local_ci_group_replay.py', 'full_ssb_scoped_replay.py'):
        path = code/name
        path.write_bytes((acceptance.ROOT/'code'/name).read_bytes())
        if name == changed:
            path.write_bytes(path.read_bytes()+b'\n# changed fixture\n')
        module = SimpleNamespace(__file__=str(path), engine=lambda:pytest.fail('source must fail before engine'))
        monkeypatch.setitem(sys.modules, path.stem, module)
    monkeypatch.setattr(acceptance, 'ROOT', tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match='source changed'):
        acceptance.verify()


def test_complete_provider_failure_propagates_without_fallback(tmp_path, monkeypatch, acceptance):
    fixture = receipt_fixture(tmp_path, monkeypatch)
    failure = ValueError('scientific source F rejected the evidence')

    def rejected_source():
        fixture.events.append('source-F-rejected')
        raise failure

    original_engine = fixture.engine

    def engine():
        value = original_engine()
        value.source_snapshot = rejected_source
        return value

    monkeypatch.setitem(sys.modules, 'full_ssb_local_ci_group_replay',
        SimpleNamespace(__file__=str(fixture.root/'code/full_ssb_local_ci_group_replay.py'), engine=engine))
    with pytest.raises(ValueError) as observed:
        acceptance.verify()
    assert observed.value is failure
    assert fixture.events == ['complete-verify', 'source-F-rejected']


def test_acceptance_does_not_write_load_models_connect_or_launch(tmp_path, monkeypatch, acceptance):
    from full_ssb_local_readonly_audit import inventory, no_operations
    fixture = receipt_fixture(tmp_path, monkeypatch)
    files = [p for p in tmp_path.rglob('*') if p.is_file()]
    before = inventory(files)
    attempts = []
    with no_operations(attempts):
        assert acceptance.verify() == fixture.result
    assert attempts == []
    assert inventory(files) == before
    assert fixture.events == ['complete-verify', 'source-F']
