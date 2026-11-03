"""The 1B adapter must separate allowed COUNT metadata from evaluation truth."""
import csv
import importlib
from pathlib import Path

import pytest


def fake_truth():
    queries=[{'query_no':i,'query_name':name,'groups':[]} for i,name in enumerate(
        ['F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2'])]
    for i in [0,1]:queries[i]['groups']=[{'key':[],'count':100+i,'sum':999999999,'value':'DO_NOT_TRAIN_ON_THIS'}]
    queries[5]['groups']=[{'key':[2005],'count':40,'sum':888888888}]
    queries[8]['groups']=[{'key':['CA'],'count':999999,'sum':0}]
    return {'complete':True,'population_rows':1000,'queries':queries}


def test_f4_population_uses_unfiltered_sample_count_not_filtered_truth():
    module=importlib.import_module('full_dbest_flights')
    metadata=module.training_metadata(fake_truth(),{'CA':20,'TX':5},.1)
    assert metadata['counts']['F4.1']['CA']['N']==200
    assert metadata['counts']['F4.1']['TX']['N']==50
    assert metadata['counts']['F1.1']['all']['N']==100
    assert metadata['counts']['F3.1']['2005']['N']==40
    assert metadata['counts']['F4.1']['CA']['estimated'] is True
    assert metadata['counts']['F4.1']['CA']['standard_error']>0
    assert all('sum' not in group and 'value' not in group for query in metadata['counts'].values() for group in query.values())


def test_changing_evaluation_sums_does_not_change_training_metadata():
    module=importlib.import_module('full_dbest_flights')
    first=fake_truth();second=fake_truth()
    second['queries'][0]['groups'][0]['sum']=-7
    second['queries'][5]['groups'][0]['sum']=3
    second['queries'][8]['groups'][0]['count']=1
    assert module.training_metadata(first,{'CA':20},.1)==module.training_metadata(second,{'CA':20},.1)


def test_stream_selection_is_unique_deterministic_and_counts_all_states(tmp_path):
    module=importlib.import_module('full_dbest_flights')
    path=tmp_path/'sample.csv'
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['DEST_STATE_ABR','DISTANCE']);writer.writeheader()
        for i in range(100):writer.writerow({'DEST_STATE_ABR':'CA' if i<90 else 'TX','DISTANCE':3000 if i%2 else 1})
    first=module.stream_selection(path,100,20,91)
    second=module.stream_selection(path,100,20,91)
    assert first==second
    assert len(first['row_ids'])==len(set(first['row_ids']))==20
    assert first['state_counts']=={'CA':90,'TX':10}
    with pytest.raises(ValueError,match='row count'):
        module.stream_selection(path,101,20,91)


@pytest.mark.parametrize('rows',[0,20001])
def test_fit_cap_is_enforced_before_source_io(tmp_path,rows):
    with pytest.raises(ValueError,match='20K'):
        importlib.import_module('full_dbest_flights').stream_selection(tmp_path/'missing.csv',100000,rows,1)


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2]/'output/full/flights/flights-1b/generation_result.json').exists(),
                    reason='Requires finalized 1B input and the independently configured official engine')
def test_actual_one_billion_population_gate():
    report=importlib.import_module('full_dbest_flights').run()
    assert report['status']=='PASS_WITH_GAPS'
    assert report['population_rows']==1000000000 and report['retained_sample_rows']==9997912
    assert report['unique_fit_rows']==20000
    assert report['process_peak_working_set_bytes']<=512*1024*1024
    assert report['original_small_gate_bytes_unchanged']
    assert report['all_native_integrals_verified']
    assert len(report['queries'])==12
    assert sum(x['status']=='UNSUPPORTED' for x in report['queries'])==8
