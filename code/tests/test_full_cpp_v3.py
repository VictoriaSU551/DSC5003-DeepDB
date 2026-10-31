"""Strict provenance and actual-native gates for the separate canonical runner."""
import copy
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest


def implementation():
    try:
        return importlib.import_module('full_cpp_v3')
    except ModuleNotFoundError as exc:
        if exc.name != 'full_cpp_v3':
            raise
        pytest.fail('Independent canonical native runner is missing')


def query(group='job_light', index=0):
    sql = 'select count(*) from title t;'
    return dict(group=group, query_no=index, sql=sql,
                sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                tables=1, predicates=0, cardinality_true=5)


def test_exact_maps_reject_empty_missing_and_unexpected_groups():
    m = implementation()
    m.require_exact_map({'a':1}, ['a'], 'groups')
    for actual, expected in [({},['a']), ({'a':1},[]), ({'a':1},['a','b']), ({'a':1,'b':2},['a'])]:
        with pytest.raises(ValueError, match='map'):
            m.require_exact_map(actual, expected, 'groups')


def test_asset_gate_rejects_empty_escape_duplicate_and_same_size_tamper(tmp_path):
    m=implementation()
    path=tmp_path/'array.bin';path.write_bytes(b'1234')
    asset=m.record(path,tmp_path)
    m.validate_assets([asset],tmp_path)
    for rows in [[],[asset,asset],[dict(asset,path='../array.bin')]]:
        with pytest.raises(ValueError):m.validate_assets(rows,tmp_path)
    path.write_bytes(b'1243')
    with pytest.raises(ValueError,match='hash|SHA'):m.validate_assets([asset],tmp_path)


@pytest.mark.parametrize('mutation', ['sql','query_no','truth','empty','extra'])
def test_reference_query_identity_is_exact_and_maps_cannot_be_empty(mutation):
    m=implementation(); q=query()
    rows={'job_light':[dict(query_no='0',query=q['sql'],cardinality_true='5',cardinality_predict='7.5')]}
    assert m.validate_references([q],rows)[('job_light',0)]==7.5
    changed=copy.deepcopy(rows)
    if mutation=='sql':changed['job_light'][0]['query']=q['sql'].upper()
    if mutation=='query_no':changed['job_light'][0]['query_no']='1'
    if mutation=='truth':changed['job_light'][0]['cardinality_true']='6'
    if mutation=='empty':changed={}
    if mutation=='extra':changed['unexpected']=changed['job_light']
    with pytest.raises(ValueError):m.validate_references([q],changed)


def test_final_acceptance_rejects_pending_empty_and_wrong_source():
    m=implementation()
    labels=['one','two']; aggregate=dict(labels=labels)
    final=m.seal(dict(status='PASS_CURRENT_CANONICAL_FOUR_SEED_ACCEPTANCE',
        parent_verification_sha256='parent',acceptance_source_sha256='source',
        models=[dict(label=x,queries=753,binding=x) for x in labels],full_paper_reproduction_complete=False))
    m.validate_acceptance_structure(final,aggregate,'source','parent',expected_models=2)
    for changed in [{},m.seal(dict(final,models=[])),m.seal(dict(final,acceptance_source_sha256='wrong'))]:
        with pytest.raises(ValueError):m.validate_acceptance_structure(changed,aggregate,'source','parent',expected_models=2)


def test_native_tracker_counts_successful_physical_calls_and_restores_after_error():
    m=implementation();module=SimpleNamespace(spn0=lambda x:x+1,spn1=lambda x:x*2)
    original=module.spn0
    with pytest.raises(RuntimeError):
        with m.native_tracker(module,2) as tracker:
            tracker.reset();assert module.spn0(3)==4;assert module.spn1(5)==10
            assert tracker.calls=={'spn0':1,'spn1':1}
            assert tracker.total==2
            raise RuntimeError('interrupted')
    assert module.spn0 is original
    with pytest.raises(ValueError):
        with m.native_tracker(SimpleNamespace(),2):pass


@pytest.mark.parametrize('python,native,reference,calls', [(2.,3.,2.,1),(2.,2.,3.,1),(2.,2.,2.,0),(float('nan'),2.,2.,1)])
def test_three_way_comparison_rejects_disagreement_nonfinite_or_no_native(python,native,reference,calls):
    m=implementation()
    with pytest.raises(ValueError):m.check_triplet(python,native,reference,calls)


def test_complete_round_grid_rejects_missing_duplicate_or_wrong_query_identity():
    m=implementation();work=[query()]
    rows=[dict(work[0],repetition=i,ordinal=0,generated_spn_calls=1,native_call_map={'spn0':1},
               cpp_physical_native_ns=1500,cpp_physical_native_ms=.0015) for i in range(3)]
    m.require_round_grid(rows,work,3)
    for changed in [rows[:-1],rows+[rows[0]],[dict(rows[0],sql='wrong')]+rows[1:]]:
        with pytest.raises(ValueError):m.require_round_grid(changed,work,3)


def test_native_every_query_map_must_be_nonempty_and_match_counter():
    m=implementation();work=[query()]
    for mapping in [{},{'spn0':0},{'spn0':2}]:
        rows=[dict(work[0],repetition=i,ordinal=0,generated_spn_calls=1,native_call_map=mapping) for i in range(3)]
        with pytest.raises(ValueError):m.require_round_grid(rows,work,3)


def test_all_fifteen_timing_cells_are_required_with_the_original_scopes():
    m=implementation();rows=[]
    columns=['python_total_ms','cpp_total_ms','python_inference_ms','cpp_inference_ms','cpp_native_bridge_ms',
             'cpp_physical_native_ms']
    for tables in (4,5,6):
        for predicates in range(1,6):
            for repetition in range(3):
                rows.append(dict(tables=tables,predicates=predicates,group='%d_%d_SPN'%(tables,predicates),
                                 **{column:1.5 for column in columns}))
    cells=m.figure8_groups(rows,3)
    assert len(cells)==15 and all(cell['unique_queries']==1 for cell in cells)
    assert all(set(cell['timing_ms'])==set(columns) for cell in cells)
    with pytest.raises(ValueError):m.figure8_groups(rows[3:],3)


def test_resource_cap_terminates_only_the_owned_test_process(tmp_path):
    import sys
    m=implementation()
    report=m.run_guarded([sys.executable,'-B','-c','import time; a=bytearray(4000000); time.sleep(30)'],
                         tmp_path,memory_limit=1024*1024,label='owned_memory_test')
    assert report['stopped_for_memory'] is True
    assert report['returncode']!=0 and report['peak_tree_rss_bytes']>1024*1024
    assert report['scope']=='Owned validation process and observed descendants only'


def test_physical_native_calls_are_primary_when_upstream_stats_omit_successful_calls():
    m=implementation()
    # Actual 3_2_SPN q35: successful spn1 calls=2, author GenCodeStats.calls=1.
    assert m.validate_call_counters('cpp',{'spn1':2},1)==1
    assert m.validate_call_counters('cpp',{'spn1':1},1)==0
    assert m.validate_call_counters('python',{},0)==0
    for mode,calls,stats in [('cpp',{},0),('cpp',{'spn1':1},2),('python',{'spn1':1},0),('python',{},1)]:
        with pytest.raises(ValueError):m.validate_call_counters(mode,calls,stats)


def test_physical_wall_timer_counts_every_successful_call_excludes_failed_calls_and_resets(monkeypatch):
    m=implementation();ticks=iter([100,250,300,700,800])
    monkeypatch.setattr(m.time,'perf_counter_ns',lambda:next(ticks))
    def fail():raise RuntimeError('native failure')
    module=SimpleNamespace(spn0=lambda:7,spn1=lambda:8,spn2=fail)
    with m.native_tracker(module,3) as tracker:
        assert module.spn0()==7 and module.spn1()==8
        assert tracker.nanoseconds==550 and tracker.total==2
        with pytest.raises(RuntimeError):module.spn2()
        assert tracker.nanoseconds==550 and tracker.calls=={'spn0':1,'spn1':1}
        tracker.reset()
        assert tracker.nanoseconds==0 and tracker.calls=={}


@pytest.mark.parametrize('nanoseconds,milliseconds',[(0,0),(-1,-.000001),(1500,.5),(None,.0015)])
def test_native_wall_evidence_is_positive_and_units_are_consistent(nanoseconds,milliseconds):
    m=implementation();work=[query()]
    rows=[dict(work[0],repetition=i,ordinal=0,generated_spn_calls=1,native_call_map={'spn0':1},
               cpp_physical_native_ns=nanoseconds,cpp_physical_native_ms=milliseconds) for i in range(3)]
    with pytest.raises(ValueError,match='wall'):m.require_round_grid(rows,work,3)
