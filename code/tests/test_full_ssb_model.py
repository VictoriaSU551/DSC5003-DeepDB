"""Preparation must agree with the actual original routine, including NULLs."""
import importlib
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ensemble_compilation.graph_representation import SchemaGraph,Table
from data_preparation.prepare_single_tables import prepare_all_tables


def synthetic_schema(directory):
    directory.mkdir(parents=True,exist_ok=True)
    parent=pd.DataFrame({'id':np.arange(1,10006),'category':['B' if i%2==0 else 'A' for i in range(10005)],
                         'region':['R2' if i%2==0 else 'R1' for i in range(10005)],
                         'name':['unique_'+str(i) for i in range(10005)],
                         'value':[None if i%17==0 else i+.25 for i in range(10005)],
                         'allnull':[None]*10005})
    child=pd.DataFrame({'id':[None if i==23 else i+1 for i in range(40)],
                        'pid':[None if i==39 else i%25+1 for i in range(40)],
                        'metric':[i*3 for i in range(40)],'category':['late' if i>20 else None for i in range(40)]})
    parent.to_csv(directory/'parent.csv',sep='|',header=False,index=False)
    child.to_csv(directory/'child.csv',sep='|',header=False,index=False)
    schema=SchemaGraph()
    schema.add_table(Table('parent',attributes=list(parent),primary_key=['id'],table_size=len(parent),
                           csv_file_location=str(directory/'parent.csv'),fd_list=[('category','region')]))
    schema.add_table(Table('child',attributes=list(child),primary_key=['id'],table_size=len(child)*4,sample_rate=.25,
                           csv_file_location=str(directory/'child.csv')))
    schema.add_relationship('child','pid','parent','id')
    return schema


def test_bounded_matches_original_high_cardinality_fd_multipliers_and_nulls(tmp_path):
    module=importlib.import_module('full_ssb_model')
    schema=synthetic_schema(tmp_path/'input')
    original=tmp_path/'original'; original.mkdir()
    reference=prepare_all_tables(schema,str(original),csv_seperator='|')
    bounded=module.prepare_bounded(schema,tmp_path/'bounded',chunk_rows=73)
    comparison=module.compare_prepared(reference,bounded)
    assert comparison['status']=='PASS'
    assert comparison['tables']==2 and comparison['null_tuple_files']>=1
    assert 'name' not in bounded['parent']['relevant_attributes']
    assert 'allnull' not in bounded['parent']['relevant_attributes']
    assert bounded['child']['child.pid = parent.id']['length']==4
    assert bounded['parent']['categorical_columns_dict']['parent.category']['B']==1
    assert bounded['parent']['categorical_columns_dict']['parent.category']['A']==2
    # A completed preparation is reusable, but changed input must never be reused.
    assert module.normalized(module.prepare_bounded(schema,tmp_path/'bounded',chunk_rows=73))==module.normalized(bounded)
    with Path(schema.tables[0].csv_file_location).open('a') as stream:stream.write('\n')
    with pytest.raises(ValueError,match='binding'):
        module.prepare_bounded(schema,tmp_path/'bounded',chunk_rows=73)


def test_chunk_budget_rejects_zero_before_io(tmp_path):
    module=importlib.import_module('full_ssb_model')
    with pytest.raises(ValueError,match='chunk'):
        module.prepare_bounded(SchemaGraph(),tmp_path/'bad',chunk_rows=0)


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2]/'data/ssb/sf2_gate_v2/lineorder_sampled.csv').exists(),
                    reason='Requires the previously sealed SF2 input; does not regenerate it')
def test_sealed_sf2_actual_original_preparation_golden():
    report=importlib.import_module('full_ssb_model').run_sf2_gate()
    assert report['status']=='PASS'
    assert report['comparison']['all_frame_values_and_dtypes_exact']
    assert report['comparison']['metadata_exact']
    assert report['comparison']['tables']==5
    assert report['comparison']['rows']['lineorder']==39712
    assert report['input_and_original_bytes_unchanged']


def test_preparation_seal_does_not_invalidate_when_only_future_training_entry_is_added():
    module=importlib.import_module('full_ssb_model')
    source=Path(module.__file__).read_text()
    original=module.preparation_code_sha256(source)
    assert module.preparation_code_sha256(source+'\ndef future_training_entry():\n    return 1\n')==original
    assert module.preparation_code_sha256(source.replace('MAX_DISTINCT=10000','MAX_DISTINCT=9999'))!=original


def tiny_ssb_with_nulls_and_duplicate_facts(directory):
    from schemas.ssb.schema import gen_500gb_ssb_schema
    directory.mkdir(parents=True,exist_ok=True)
    schema=gen_500gb_ssb_schema(str(directory/'{}.tbl'))
    dim={
        'customer':[1,'name','address','UNITED ST1','UNITED STATES','AMERICA','phone','segment'],
        'supplier':[1,'name','address','UNITED ST2','UNITED STATES','AMERICA','phone'],
        'part':[1,'name','MFGR#1','MFGR#14','MFGR#141','color','type',1,'container'],
        'dwdate':[19930101,'date','Friday','January',1993,199301,'Jan1993',1,1,1,1,1,'season',0,0,0,1]}
    base=[1,1,1,1,1,19930101,'HIGH',0,10,100000000000,1,2,1000000000000,999999999999,0,19930101,'SHIP']
    rows=[list(base),list(base)]
    for revenue,cost in [(None,7),(9,None),(None,None)]:
        row=list(base);row[12]=revenue;row[13]=cost;rows.append(row)
    missing=list(base);missing[2]=None;missing[3]=None;missing[4]=None;missing[9]=None;rows.append(missing)
    no_date=list(base);no_date[5]=None;rows.append(no_date)
    for table in schema.tables:
        table.csv_file_location=str(directory/(table.table_name+'.tbl'))
        table.table_size=len(rows) if table.table_name=='lineorder' else 1
        table.sample_rate=1
        with Path(table.csv_file_location).open('w',newline='') as stream:
            csv.writer(stream,delimiter='|').writerows(rows if table.table_name=='lineorder' else [dim[table.table_name]])
    return schema,len(rows)


def test_ci_native_matches_independent_sql_with_nulls_duplicates_and_large_integer_squares(tmp_path):
    module=importlib.import_module('full_ssb_model')
    schema,rows=tiny_ssb_with_nulls_and_duplicate_facts(tmp_path/'input')
    sql=module.sample_moments_sqlite(schema,tmp_path/'reference.sqlite')
    native=module.sample_moments_native(schema,rows,tmp_path/'native')
    assert module.normalized_moments(native['queries'])==module.normalized_moments(sql)
    profit=native['queries'][10]['groups'][0]
    assert profit['count']==profit['filter_count']==5
    assert profit['sum_integer']==4 and profit['square_sum_integer']==132
    assert profit['component_non_null_counts']==[3,3]
    scalar=native['queries'][0]['groups'][0]
    assert scalar['filter_count']==6 and scalar['count']==5
    assert scalar['square_sum_integer']>2**63


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2]/'output/full/ssb/models/sf2_preparation_gate_latest.json').exists(),
                    reason='Requires independently sealed SF2 preparation; no regeneration')
def test_small_original_single_table_ensemble_all_thirteen_queries_and_ci():
    report=importlib.import_module('full_ssb_model').run_small_model(sample_cap=10000)
    assert report['stage']=='SF2_SMALL_SINGLE_MODEL_AQP_CI_ONLY'
    assert report['point_query_errors']==0
    assert len(report['queries'])==13 and report['spn_count']==5
    assert all(x['actual_training_rows']<=10000 for x in report['training_tables'])
    assert report['sample_moments_native_sqlite_exact']
    assert report['preparation_reused_without_recomputation']


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2]/'output/full/ssb/paper/sf2_gate_v2/checkpoint.json').exists(),
                    reason='Requires original sealed stream state')
def test_native_stream_numeric_query_ids_are_aligned_to_thirteen_sqls():
    module=importlib.import_module('full_ssb_model')
    truth=module.population_truth_groups(module.ROOT/'output/full/ssb/paper/sf2_gate_v2/checkpoint.json')
    assert len(truth['queries'])==13
    assert truth['queries'][0]['query_name']=='S1.1'
    assert truth['queries'][12]['query_name']=='S4.3'


def test_model_guard_checks_actual_unmatched_hdf_before_returning_cached_model(tmp_path):
    module=importlib.import_module('full_ssb_model')
    schema=synthetic_schema(tmp_path/'input')
    prepared=tmp_path/'prepared'
    module.prepare_bounded(schema,prepared,chunk_rows=73)
    binding=module.model_input_artifacts(schema,prepared)
    assert len(binding['prepared_files_sha256'])>=5
    unmatched=next(prepared.glob('parent.hdf*.hdf'))
    # Metadata and its seal remain unchanged. The dependency's physical bytes do not.
    with unmatched.open('ab') as stream:stream.write(b'changed after preparation')
    with pytest.raises(ValueError,match='artifact'):
        module.model_input_artifacts(schema,prepared)


def test_formal_gate_rejects_incomplete_generation_before_reading_sample(tmp_path):
    module=importlib.import_module('full_ssb_model')
    result=tmp_path/'result.json'
    module.atomic_json(result,{'status':'CHECKPOINTED','complete':False,'rows':3000028242})
    with pytest.raises(ValueError,match='complete.*author'):
        module.sf500_final_inputs(result_path=result,checkpoint_path=tmp_path/'MISSING.json')


def test_formal_gate_rejects_author_mismatch_even_at_target_row_count(tmp_path):
    module=importlib.import_module('full_ssb_model')
    result=tmp_path/'result.json'
    module.atomic_json(result,{'status':'PASS','complete':True,'rows':3000028242,
                              'row_count_matches_author':True,'author_truth_comparison':{'match':False}})
    with pytest.raises(ValueError,match='author'):
        module.sf500_final_inputs(result_path=result,checkpoint_path=tmp_path/'MISSING.json')


def test_formal_worker_requires_root_memory_release_before_inputs(monkeypatch):
    module=importlib.import_module('full_ssb_model')
    def unexpected(*args,**kwargs):raise AssertionError('Must not inspect/generate formal data before resource gate')
    monkeypatch.setattr(module,'sf500_final_inputs',unexpected)
    with pytest.raises(ValueError,match='memory'):
        module.formal_worker(memory_approved=False)


def test_final_raw_hash_counts_unterminated_last_record_and_empty_input(tmp_path):
    import hashlib
    module=importlib.import_module('full_ssb_model')
    source=tmp_path/'sample.tbl';source.write_bytes(b'1|a|\r\n2|b|')
    assert module.raw_hash_and_rows(source)==(hashlib.sha256(source.read_bytes()).hexdigest(),2)
    source.write_bytes(b'')
    assert module.raw_hash_and_rows(source)==(hashlib.sha256(b'').hexdigest(),0)


def test_formal_plan_checksum_rejected_before_memory_and_data_access(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_model')
    monkeypatch.setattr(module,'OUTPUT',tmp_path)
    module.atomic_json(tmp_path/'formal_plan.json',{'resources':{}})
    module.atomic_json(tmp_path/'formal_plan.seal.json',{'sha256':'stale'})
    def unexpected():raise AssertionError('Must reject stale plan before memory/data access')
    monkeypatch.setattr(module,'available_memory_bytes',unexpected)
    with pytest.raises(ValueError,match='plan checksum'):
        module.formal_worker_locked()
