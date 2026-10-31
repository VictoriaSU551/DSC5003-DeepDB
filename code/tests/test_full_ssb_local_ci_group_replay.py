"""New CI behavior must explicitly depend on canonical groups, never old PASS."""
from contextlib import contextmanager
import builtins
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import full_ssb_local_ci_group_replay as target


def test_worker_warms_seed_resetting_inference_import_before_generic_seeding(monkeypatch):
    events=[]
    original=builtins.__import__
    def import_probe(name,*args,**kwargs):
        if name=='ensemble_compilation.spn_ensemble':
            events.append('import-time-seed-1')
            return SimpleNamespace()
        return original(name,*args,**kwargs)
    def generic_worker():
        assert events==['import-time-seed-1']
        events.append('generic-worker-seed-74031')
        return {'status':'fixture'}
    monkeypatch.setattr(builtins,'__import__',import_probe)
    monkeypatch.setattr(target,'engine',lambda:SimpleNamespace(worker=generic_worker))
    assert target.worker()=={'status':'fixture'}
    assert events==['import-time-seed-1','generic-worker-seed-74031']


def test_executor_enters_adapter_before_original_call_and_restores_on_error(monkeypatch):
    events=[]
    @contextmanager
    def context():
        events.append('enter')
        try:yield
        finally:events.append('exit')
    def execute(*args):
        assert events==['enter'];events.append('original')
        raise RuntimeError('native failure retained')
    module=SimpleNamespace(__file__=str(target.ROOT/target.ADAPTER),canonical_group_order=context)
    monkeypatch.setitem(sys.modules,'full_ssb_group_order',module)
    monkeypatch.setattr(target,'digest',lambda p:target.ADAPTER_SHA)
    monkeypatch.setattr(target,'execute_query',execute)
    with pytest.raises(RuntimeError):target.canonical_execute_query(12,'SQL','S4.3','model',9996946)
    assert events==['enter','original','exit']


def test_changed_adapter_fails_before_import_or_inference(monkeypatch):
    monkeypatch.setattr(target,'digest',lambda p:'0'*64)
    monkeypatch.setattr(target,'execute_query',lambda *args:pytest.fail('must not predict'))
    with pytest.raises(ValueError,match='adapter'):target.canonical_execute_query(0,'SQL','name','model',9996946)


def test_engine_uses_separate_namespace_and_canonical_callback():
    engine=target.engine()
    assert engine.execute_query is target.canonical_execute_query
    assert engine.OUTPUT.name=='local_sf500_ci10m_group_replay'
    assert target.METADATA['evaluation_variant']=='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
    assert target.METADATA['group_order_adapter_sha256']==target.ADAPTER_SHA
    assert target.METADATA['training_cap_per_table']==10000000


@pytest.mark.parametrize('mutation',['missing','old','hash','path','descriptor'])
def test_canonical_lineage_cannot_be_replaced_by_old_reverse_success(mutation):
    formal=dict(evaluation_variant=target.VARIANT,group_order_adapter_sha256=target.ADAPTER_SHA,
        lineage=dict(parent_canonical=dict(path=target.PARENT_CANONICAL,bytes=1024,sha256='a'*64)))
    if mutation=='missing':formal['lineage'].pop('parent_canonical')
    if mutation=='old':formal['evaluation_variant']='OLD_GROUP_SET_ORDER'
    if mutation=='hash':formal['group_order_adapter_sha256']='b'*64
    if mutation=='path':formal['lineage']['parent_canonical']['path']='output/full/results/ssb_local_sf500_model_aqp_ci.json'
    if mutation=='descriptor':formal['lineage']['parent_canonical']['bytes']=0
    with pytest.raises(ValueError):target.validate_canonical_lineage(formal)


def test_exact_canonical_lineage_is_accepted_as_header_only():
    formal=dict(evaluation_variant=target.VARIANT,group_order_adapter_sha256=target.ADAPTER_SHA,
        lineage=dict(parent_canonical=dict(path=target.PARENT_CANONICAL,bytes=1024,sha256='a'*64)))
    target.validate_canonical_lineage(formal)
    # Header acceptance is deliberately not the public scientific verifier.


@pytest.mark.parametrize('mutation',[None,'policy','wrong_adapter','old_parent','missing_aux'])
def test_source_boundary_calls_real_provider_once_and_rejects_stale_contract(tmp_path,monkeypatch,mutation):
    monkeypatch.setattr(target,'ROOT',tmp_path)
    sqls=['SELECT SUM(x) FROM t WHERE k=%d;'%i for i in range(13)]
    queries=[dict(query_no=i,query_name=target.QUERY_NAMES[i],sql=sqls[i],point_error=None,ci_error=None) for i in range(13)]
    sql=tmp_path/'code/benchmarks/ssb/sql/aqp_queries.sql';sql.parent.mkdir(parents=True);sql.write_text('\n'.join(sqls))
    mismatch=tmp_path/'output/full/results/ssb_native_v2.json';mismatch.parent.mkdir(parents=True);mismatch.write_text('retained mismatch fixture')
    pins={'full_ssb_replay.py':target.OLD_REPLAY_SHA,'full_ssb_native_replay.py':target.NATIVE_GUARD_SHA,
        'full_ssb_scoped_replay.py':target.SCOPED_SHA,'full_ssb_group_order.py':target.ADAPTER_SHA,
        'full_ssb_local_ci_group_replay.py':'entry-sha','ssb_native_v2.json':target.ORIGINAL_MISMATCH_SHA}
    monkeypatch.setattr(target,'digest',lambda p:pins[Path(p).name])
    formal=dict(target.METADATA,status='PASS_READ_ONLY_LOCAL_SSB_10M_CI_WITH_AUTHOR_MISMATCH',population_rows=3000028242,
        sample_rows=9996946,queries=queries,model_path='model.pkl',model_sha256='model-sha',artifacts=[],
        original_mismatch=dict(path=mismatch.relative_to(tmp_path).as_posix(),bytes=mismatch.stat().st_size,sha256=target.ORIGINAL_MISMATCH_SHA),
        lineage=dict(parent_canonical=dict(path=target.PARENT_CANONICAL,bytes=1024,sha256='a'*64),
            parent_formal=dict(path='formal.json',bytes=1,sha256='b'*64),parent_reverse=dict(path='canonical_reverse.json',bytes=1,sha256='c'*64)),
        dependencies=dict(auxiliary_sources={p:pins[Path(p).name] for p in target.AUXILIARY}))
    for name in ('verification','verification_seal','published_result','plan','formal_receipt','formal_lifecycle','evaluation_binding'):formal[name]={}
    calls=[]
    def verify():calls.append('fresh-provider');return formal
    monkeypatch.setitem(sys.modules,'full_ssb_local_ci',SimpleNamespace(verify_local_ci=verify))
    if mutation=='policy':formal['paper_figure11_training_budget_policy_applied']=False
    if mutation=='wrong_adapter':formal['group_order_adapter_sha256']='0'*64
    if mutation=='old_parent':formal['lineage']['parent_canonical']['path']='old_replay.json'
    if mutation=='missing_aux':formal['dependencies']['auxiliary_sources'].pop(target.ADAPTER)
    if mutation is None:
        snapshot,actual=target.source_snapshot()
        assert snapshot['evaluation_variant']==target.VARIANT and actual==queries
        assert snapshot['lineage']==formal['lineage']
    else:
        with pytest.raises(ValueError):target.source_snapshot()
    assert calls==['fresh-provider']
