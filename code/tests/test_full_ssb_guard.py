"""Durable publication barriers around the frozen SSB golden implementation."""
import importlib
import json
from pathlib import Path

import pandas as pd
import pytest


def test_failed_final_validation_is_permanently_tainted_even_after_input_restored(tmp_path):
    guard=importlib.import_module('full_ssb_guard');calls=[]
    def producer():calls.append(1);(tmp_path/'premature_core_seal.json').write_text('{}');return {'status':'PASS'}
    def invalid(result):raise ValueError('Input changed at end')
    with pytest.raises(ValueError,match='Input changed'):
        guard.transaction(tmp_path/'state','test',{'input':'original'},producer,invalid)
    with pytest.raises(ValueError,match='TAINTED'):
        guard.transaction(tmp_path/'state','test',{'input':'original'},producer,lambda result:None)
    assert len(calls)==1


def test_residual_running_namespace_is_tainted_before_any_producer(tmp_path):
    guard=importlib.import_module('full_ssb_guard')
    state=tmp_path/'state';state.mkdir()
    (state/'lifecycle.json').write_text(json.dumps({'status':'RUNNING'}))
    def unexpected():raise AssertionError('Residual RUNNING cannot automatically resume')
    with pytest.raises(ValueError,match='TAINTED'):
        guard.transaction(state,'test',{},unexpected,lambda result:None)
    assert json.loads((state/'lifecycle.json').read_text())['status']=='TAINTED'


def test_core_preparation_seal_without_outer_pass_is_rejected(tmp_path):
    guard=importlib.import_module('full_ssb_guard')
    path=tmp_path/'prepared';path.mkdir();(path/'seal.json').write_text('{}')
    with pytest.raises(ValueError,match='outer.*PASS'):
        guard.require_prepared_pass(None,path)


def test_copied_query_zero_pair_cannot_stand_for_query_one(tmp_path):
    guard=importlib.import_module('full_ssb_guard')
    expected=['select 0;','select 1;']
    for index in (0,1):
        path=tmp_path/('query_%02d.json'%index)
        guard.core.atomic_json(path,{'query_no':0,'query_name':'S1.1','sql':expected[0]})
        guard.core.atomic_json(path.with_suffix('.seal.json'),{'binding':{'global':1},'sha256':guard.core.digest(path)})
    with pytest.raises(ValueError,match='identity'):
        guard.query_bundle(tmp_path,{'global':1},expected,['S1.1','S1.2'])


def test_full_dependencies_include_parser_sqlparse_and_non_rdc_spflow():
    guard=importlib.import_module('full_ssb_guard');deps=guard.dependencies()
    assert 'code/evaluation/utils.py' in deps['sources']
    assert any('Inference.py' in name for name in deps['spflow_sources'])
    assert len(deps['spflow_sources'])>50 and len(deps['sqlparse_sources'])>5
    assert 'sqlparse' in deps['versions'] and 'spflow' in deps['versions']


def test_large_integer_mean_matches_actual_original_pandas_and_preparation(tmp_path):
    guard=importlib.import_module('full_ssb_guard')
    from ensemble_compilation.graph_representation import SchemaGraph,Table
    from data_preparation.prepare_single_tables import prepare_all_tables
    values=[2**53,1,0]
    assert sum(values)/3!=pd.Series(values,dtype='int64').mean()
    path=tmp_path/'input.tbl'
    pd.DataFrame({'pk':[1,2,3],'value':values}).to_csv(path,sep='|',header=False,index=False)
    schema=SchemaGraph();schema.add_table(Table('numbers',attributes=['pk','value'],primary_key=['pk'],
                                              csv_file_location=str(path),table_size=3))
    reference_dir=tmp_path/'original';reference_dir.mkdir()
    reference=prepare_all_tables(schema,str(reference_dir),csv_seperator='|')
    with pytest.raises(ValueError,match='Integer reduction'):
        guard.core.profile_table(schema.tables[0],tmp_path/'old_profile',1)
    prepared=tmp_path/'bounded'
    metadata=guard.guarded_prepare(schema,prepared,chunk_rows=1)
    assert guard.core.compare_prepared(reference,metadata)['status']=='PASS'
    assert guard.require_prepared_pass(schema,prepared)['status']=='PASS'


def test_verified_tiny_adoption_never_repeats_preparation_training_or_inference(monkeypatch):
    guard=importlib.import_module('full_ssb_guard')
    def forbidden(*args,**kwargs):raise AssertionError('Completed tiny work must never be repeated')
    for name in ('prepare_bounded','train_single_models','train_original_reference','guarded_train_single_models','evaluate_ssb'):
        monkeypatch.setattr(guard.core,name,forbidden)
    report=guard.seal_small_gate()
    assert report['status']=='PASS_CURRENT_COMPLETE_DEPENDENCIES'
    assert report['model_sha256']==guard.TINY_MODEL_SHA256 and report['query_identities']==13
    assert report['no_preparation_training_or_inference_repeated']
    assert guard.verify_small_gate()==report


def test_evaluation_cannot_first_adopt_existing_unguarded_query_cache(tmp_path,monkeypatch):
    guard=importlib.import_module('full_ssb_guard')
    monkeypatch.setattr(guard,'require_model_pass',lambda model:None)
    path=tmp_path/'ensemble.pkl';path.write_bytes(b'model')
    directory=tmp_path/'evaluation';(directory/'old').mkdir(parents=True)
    (directory/'old/query_00.json').write_text('{}')
    def forbidden(*args,**kwargs):raise AssertionError('Core cache must not be called')
    monkeypatch.setattr(guard.core,'evaluate_ssb',forbidden)
    with pytest.raises(ValueError,match='unguarded.*cache'):
        guard.guarded_evaluate({'model_path':str(path)},{'checkpoint_sha256':'truth'},[],directory)


def test_model_pass_rechecks_core_nonpickle_receipts(tmp_path,monkeypatch):
    guard=importlib.import_module('full_ssb_guard');monkeypatch.setattr(guard,'dependencies',lambda:{})
    directory=tmp_path/'model';directory.mkdir();path=directory/'ensemble.pkl';path.write_bytes(b'model')
    model={'model_path':str(path),'files_sha256':{'ensemble.pkl':guard.core.digest(path)},'binding':{'stage':'test'}}
    binding={'dependencies':{},'guard_source_sha256':guard.core.digest(guard.__file__)}
    guard.core.atomic_json(directory/'model.json',model)
    guard.core.atomic_json(directory/'input_guard.json',{'binding':{'model_stage':model['binding']}})
    guard.core.atomic_json(directory/'model_guard.json',{'binding':{'model_stage':model['binding']},
        'model_files_sha256':{p.name:guard.core.digest(p) for p in directory.iterdir() if p.name!='model_guard.json'}})
    guard.transaction(guard.home_for(directory,'model'),'MODEL',binding,lambda:model,lambda result:None)
    guard.require_model_pass(model)
    (directory/'model.json').write_text('{}')
    with pytest.raises(ValueError,match='core.*checksum|core.*receipt'):
        guard.require_model_pass(model)
