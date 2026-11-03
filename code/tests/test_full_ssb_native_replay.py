"""Contract failures must reject a purported replay without executing a model."""
import copy
import builtins
import io
from pathlib import Path

import pytest

import full_ssb_native_replay as replay


def fixture_queries():
    sqls = ['SELECT SUM(x) FROM t WHERE k=%d;' % i for i in range(13)]
    names = ['S%d' % i for i in range(13)]
    queries = [dict(query_no=i, query_name=names[i], sql=sqls[i], point_error=None,
                    ci_error=None) for i in range(13)]
    for q in queries:
        q.update(groups=[dict(key=[], prediction=1.5, truth=1.5,
            model_interval=[1.,2.], status='MATCHED', zero_truth=False,
            reference_ci=dict(eligible=True,status='ELIGIBLE'))],
            truth_groups=1,model_groups=1,missing_model_groups=0,extra_model_groups=0,
            nonfinite_original_intervals=[])
    return queries, sqls, names


def fixture_execution():
    return dict(status='PASS_NATIVE_V2_INDEPENDENT_REVERSE_REPLAY', queries=13,
        stage='SSB_NATIVE_V2_REVERSE_REPLAY', full_paper_reproduction_complete=False,
        original_query_evaluator_calls=26, model_loads=13,
        execution_order=list(reversed(range(13))),
        environment=dict(PYTHONHASHSEED='173', random_seed=74031, numpy_seed=74031,
            thread_limits={name:'1' for name in replay.THREAD_LIMITS}),
        binding=dict(hash_seed=173, random_seed=74031,
                     relative_tolerance=1e-9, absolute_tolerance=1e-5))


def test_full_execution_contract_accepts_only_the_recorded_fresh_process_policy():
    replay.validate_execution(fixture_execution())
    queries, sqls, names = fixture_queries()
    replay.validate_query_identities(queries, sqls, names)
    assert len(replay.required_query_files()) == 26


@pytest.mark.parametrize('mutation', ['subset', 'duplicate', 'index', 'sql', 'name', 'error'])
def test_formal_subset_duplicate_sql_or_failed_query_is_rejected_before_execution(mutation):
    queries, sqls, names = fixture_queries()
    if mutation == 'subset': queries.pop()
    if mutation == 'duplicate': queries[-1] = copy.deepcopy(queries[0])
    if mutation == 'index': queries[4]['query_no'] = 11
    if mutation == 'sql': queries[4]['sql'] += ' '
    if mutation == 'name': queries[4]['query_name'] = 'another workload'
    if mutation == 'error': queries[4]['ci_error'] = 'unavailable'
    with pytest.raises(ValueError):
        replay.validate_query_identities(queries, sqls, names)


@pytest.mark.parametrize('mutation', ['calls', 'loads', 'count', 'order', 'hash', 'numpy', 'threads', 'tolerance', 'full_paper'])
def test_resealed_counter_or_process_policy_change_is_rejected(mutation):
    result = fixture_execution()
    if mutation == 'calls': result['original_query_evaluator_calls'] = 24
    if mutation == 'loads': result['model_loads'] = 1
    if mutation == 'count': result['queries'] = 12
    if mutation == 'order': result['execution_order'] = list(range(13))
    if mutation == 'hash': result['environment']['PYTHONHASHSEED'] = '0'
    if mutation == 'numpy': result['environment']['numpy_seed'] += 1
    if mutation == 'threads': result['environment']['thread_limits']['MKL_NUM_THREADS'] = '2'
    if mutation == 'tolerance': result['binding']['relative_tolerance'] = 1e-2
    if mutation == 'full_paper': result['full_paper_reproduction_complete'] = True
    with pytest.raises(ValueError):
        replay.validate_execution(result)


def test_query_file_inventory_rejects_empty_subset_duplicate_and_escape():
    required = replay.required_query_files()
    replay.validate_query_files(required)
    for wrong in [[], required[:-1], required + [required[0]],
                  required[:-1] + ['../query_12.seal.json']]:
        with pytest.raises(ValueError):
            replay.validate_query_files(wrong)


def test_inference_guard_blocks_raw_readers_and_restores_them_after_error(tmp_path):
    import numpy as np
    import pandas as pd
    import tables
    raw = tmp_path/'raw'; raw.mkdir(); (raw/'facts.csv').write_text('source')
    model = tmp_path/'model.pkl'; model.write_bytes(b'allowed-model')
    originals = (builtins.open, io.open, np.load, pd.read_csv, tables.open_file)
    with pytest.raises(RuntimeError, match='stop'):
        with replay.deny_raw_data_access([raw]):
            assert model.read_bytes() == b'allowed-model'
            for read in [lambda:(raw/'facts.csv').read_bytes(),
                         lambda:builtins.open(raw/'facts.csv','rb'),
                         lambda:np.load(model), lambda:pd.read_csv(model),
                         lambda:tables.open_file(model)]:
                with pytest.raises(ValueError, match='forbidden'):
                    read()
            raise RuntimeError('stop')
    assert (builtins.open, io.open, np.load, pd.read_csv, tables.open_file) == originals
    assert (raw/'facts.csv').read_text() == 'source'


def sealed_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, 'ROOT', tmp_path)
    # Keep hashed namespaces within Windows MAX_PATH in this deep workspace.
    monkeypatch.setattr(replay, 'OUTPUT', tmp_path/'o')
    queries, sqls, names = fixture_queries()
    snapshot = dict(test_only=True,artifacts=[])
    monkeypatch.setattr(replay, 'source_snapshot', lambda:(snapshot, queries))
    binding = replay.binding_for(snapshot)
    home = replay.OUTPUT/'runs'/replay.value_hash(binding); home.mkdir(parents=True)
    comparisons, files = {}, {}
    for q in queries:
        index=q['query_no']
        actual=dict(query_no=index,query_name=q['query_name'],sql=q['sql'],
            groups=[dict(key=[],prediction=1.5,model_interval=[1.,2.])],
            nonfinite_original_intervals=[],original_query_evaluator_calls=2,model_loads=1)
        comparison=replay.compare_query(q,actual)
        path=home/('query_%02d.json'%index)
        replay.atomic(path,dict(actual=actual,comparison=comparison))
        replay.atomic(path.with_suffix('.seal.json'),dict(binding=binding,query_no=index,
            exact_sql_sha256=replay.hashlib.sha256(q['sql'].encode()).hexdigest(),sha256=replay.digest(path)))
        comparisons[str(index)]=comparison
    files={name:replay.digest(home/name) for name in replay.required_query_files()}
    result=fixture_execution()
    result.update(source_snapshot=snapshot,binding=binding,directory=home.relative_to(tmp_path).as_posix(),
        query_files_sha256=files,comparisons=comparisons,coverage=replay.coverage(dict(queries=queries)))
    seal=dict(report_sha256='',binding=binding,query_files_sha256=files)
    def publish():
        replay.atomic(home/'verification.json',result)
        seal['report_sha256']=replay.digest(home/'verification.json')
        replay.atomic(home/'verification_seal.json',seal)
        replay.atomic(home/'lifecycle.json',dict(status='PASS',binding=binding,report_sha256=seal['report_sha256']))
        replay.atomic(replay.OUTPUT/'verification.json',result)
        replay.atomic(replay.OUTPUT/'verification_seal.json',seal)
        replay.atomic(replay.OUTPUT/'last_run.json',dict(status='PASS',directory=result['directory'],report_sha256=seal['report_sha256']))
    publish()
    logs=replay.OUTPUT/'logs';logs.mkdir();stdout=logs/'worker.stdout';stderr=logs/'worker.stderr'
    stdout.write_text('real process output fixture');stderr.write_bytes(b'')
    def record(p):return dict(path=p.relative_to(tmp_path).as_posix(),bytes=p.stat().st_size,sha256=replay.digest(p))
    replay.atomic(replay.OUTPUT/'last_process.json',dict(returncode=0,stdout=record(stdout),stderr=record(stderr),replay_source_sha256=replay.digest(replay.__file__)))
    return result, home, publish


def test_acceptance_is_read_only_and_never_predicts_or_repairs(tmp_path, monkeypatch):
    result, home, _ = sealed_fixture(tmp_path,monkeypatch)
    files=[p for p in tmp_path.rglob('*') if p.is_file()]
    before={str(p):(replay.digest(p),p.stat().st_mtime_ns) for p in files}
    def forbidden(*args,**kwargs):raise AssertionError('acceptance must be read only')
    for name in ('write_text','write_bytes','mkdir','unlink','rename','replace'):
        monkeypatch.setattr(Path,name,forbidden)
    monkeypatch.setattr(replay.subprocess,'run',forbidden)
    monkeypatch.setattr(replay,'execute_query',forbidden)
    assert replay.verify()==result
    assert {str(p):(replay.digest(p),p.stat().st_mtime_ns) for p in files}==before


@pytest.mark.parametrize('mutation',['empty_map','subset_map','coverage','tainted','extra_file','call_count'])
def test_resealed_outer_report_cannot_hide_missing_artifacts_or_bad_history(tmp_path,monkeypatch,mutation):
    result,home,publish=sealed_fixture(tmp_path,monkeypatch)
    if mutation=='empty_map':result['query_files_sha256'].clear()
    if mutation=='subset_map':result['query_files_sha256'].pop('query_12.seal.json')
    if mutation=='coverage':result['coverage']['truth_groups_total']=2059
    if mutation=='call_count':result['original_query_evaluator_calls']=24
    publish()
    if mutation=='tainted':replay.atomic(home/'lifecycle.json',dict(status='TAINTED'))
    if mutation=='extra_file':(home/'untracked_result.json').write_text('{}')
    with pytest.raises(ValueError):replay.verify()


def test_missing_formal_pass_cannot_start_a_worker_or_create_output(tmp_path,monkeypatch):
    monkeypatch.setattr(replay,'OUTPUT',tmp_path/'not-created')
    def unavailable():raise ValueError('formal source not accepted')
    def forbidden(*a,**k):raise AssertionError('must not launch')
    monkeypatch.setattr(replay,'source_snapshot',unavailable)
    monkeypatch.setattr(replay.subprocess,'run',forbidden)
    with pytest.raises(ValueError,match='formal source'):replay.replay()
    assert not replay.OUTPUT.exists()


@pytest.mark.parametrize('changed_source', [False, True])
def test_worker_reverse_order_guard_and_immutable_failed_namespace(tmp_path,monkeypatch,changed_source):
    monkeypatch.setattr(replay,'ROOT',tmp_path)
    monkeypatch.setattr(replay,'OUTPUT',tmp_path/'w')
    for name in replay.THREAD_LIMITS:monkeypatch.setenv(name,'1')
    monkeypatch.setenv('DEEPDB_SSB_NATIVE_REPLAY_WORKER','1')
    monkeypatch.setenv('PYTHONHASHSEED','173')
    data=tmp_path/'data';data.mkdir();(data/'facts.csv').write_text('raw')
    model=tmp_path/'model.pkl';model.write_bytes(b'saved-model')
    queries,_,_=fixture_queries()
    snapshot=dict(artifacts=[],model_path=str(model),sample_rows=10)
    snapshots=[]
    def source():
        snapshots.append(1)
        current=copy.deepcopy(snapshot)
        if changed_source and len(snapshots)>1:current['changed']=True
        return current,queries
    monkeypatch.setattr(replay,'source_snapshot',source)
    order=[]
    def actual(index,sql,name,model_path,sample_rows):
        order.append(index)
        assert Path(model_path).read_bytes()==b'saved-model'
        with pytest.raises(ValueError,match='forbidden'):(data/'facts.csv').read_text()
        return dict(query_no=index,query_name=name,sql=sql,
            groups=[dict(key=[],prediction=1.5,model_interval=[1.,2.])],
            nonfinite_original_intervals=[],original_query_evaluator_calls=2,model_loads=1)
    monkeypatch.setattr(replay,'execute_query',actual)
    if changed_source:
        with pytest.raises(ValueError,match='snapshot changed'):replay.worker()
        latest=replay.read(replay.OUTPUT/'last_run.json')
        assert latest['status']=='TAINTED'
        assert not (replay.OUTPUT/'verification.json').exists()
    else:
        result=replay.worker()
        assert result['original_query_evaluator_calls']==26 and result['model_loads']==13
        assert len(result['query_files_sha256'])==26
    assert order==list(reversed(range(13)))
    # Restoring bytes cannot erase the first lifecycle and trigger a rerun.
    monkeypatch.setattr(replay,'source_snapshot',lambda:(snapshot,queries))
    with pytest.raises(ValueError,match='prior replay namespace'):replay.worker()
    assert len(order)==13
