import csv
import importlib
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = ('YEAR_DATE','UNIQUE_CARRIER','ORIGIN','ORIGIN_STATE_ABR','DEST','DEST_STATE_ABR',
           'DEP_DELAY','TAXI_OUT','TAXI_IN','ARR_DELAY','AIR_TIME','DISTANCE')


def module():
    assert importlib.util.find_spec('full_flights_model') is not None, 'Flights model driver is not implemented'
    return importlib.import_module('full_flights_model')


def sample(tmp_path, rows, header=COLUMNS):
    path = tmp_path / 'sample.csv'
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(header); writer.writerows(rows)
    return path


def row(delay=1, distance=2500, taxi_out=4, taxi_in=1, carrier='AA'):
    return [2001,carrier,'ATL','GA','JFK','NY',delay,taxi_out,taxi_in,2,100,distance]


def test_header_aware_reader_preserves_numeric_columns(tmp_path):
    frame = module().read_sample_header(sample(tmp_path, [row()]))
    assert list(frame.columns) == [c.lower() for c in COLUMNS]
    assert frame.shape == (1,12)
    assert frame['distance'].dtype.kind in 'fi'
    assert frame['year_date'].tolist() == [2001]


def test_wrong_header_is_rejected_before_numeric_preparation(tmp_path):
    bad = list(COLUMNS); bad[0] = 'YEAR'
    with pytest.raises(ValueError, match='header'):
        module().read_sample_header(sample(tmp_path, [row()], bad))


def test_real_golden_source_uses_200k_normalizer_and_1993_actual_rows():
    report = module().load_generated_input('golden-200k/continuous', paper=False)
    assert report['population_rows'] == 200000
    assert report['sample_rows'] == 1993
    assert report['paper_scale_reached'] is False
    with pytest.raises(ValueError, match='1B|1000000000'):
        module().load_generated_input('golden-200k/continuous', paper=True)


def test_all_group_union_preserves_missing_extra_and_zero_truth():
    truths = [{'key':['A'],'numerator':0,'denominator':1},
              {'key':['B'],'numerator':8,'denominator':1}]
    result = module().compare_groups(truths, {('A',):3., ('C',):7.}, {})
    keyed = {tuple(r['key']):r for r in result}
    assert set(keyed) == {('A',),('B',),('C',)}
    assert keyed[('A',)]['relative_error'] is None
    assert keyed[('A',)]['zero_truth'] is True
    assert keyed[('B',)]['status'] == 'MISSING_MODEL_GROUP'
    assert keyed[('C',)]['status'] == 'EXTRA_MODEL_GROUP'


def test_integer_sample_moments_obey_null_strict_bounds_product_and_sum_difference(tmp_path):
    rows = [row(delay=1,distance=2500,taxi_out=4,taxi_in=1),
            row(delay=2,distance=2500.1,taxi_out=5,taxi_in=None),
            row(delay=None,distance=2600,taxi_out=None,taxi_in=2,carrier=None)]
    sqls = ["SELECT COUNT(*) FROM flights WHERE distance>2500;",
            "SELECT AVG(dep_delay) FROM flights;",
            "SELECT SUM(arr_delay*dep_delay) FROM flights;",
            "SELECT SUM(taxi_out)-SUM(taxi_in) FROM flights;",
            "SELECT unique_carrier,COUNT(*) FROM flights WHERE dep_delay IS NULL GROUP BY unique_carrier;"]
    result = module().sample_moments(sample(tmp_path, rows), sqls)
    assert result[0]['groups'][0]['count'] == 2
    avg = result[1]['groups'][0]
    assert (avg['count'],avg['sum_integer'],avg['square_sum_integer'],avg['scale']) == (2,30,500,10)
    prod = result[2]['groups'][0]
    assert (prod['count'],prod['sum_integer'],prod['square_sum_integer'],prod['scale']) == (2,600,200000,100)
    diff = result[3]['groups'][0]
    assert (diff['count'],diff['sum_integer'],diff['square_sum_integer'],diff['scale']) == (3,60,3800,10)
    assert result[4]['groups'][0]['key']==[None]
    assert result[4]['groups'][0]['count']==1


def test_reference_ci_uses_count_scale_sum_variance_and_central_90pct():
    m = module()
    moments = {'count':10,'filter_count':10,'sum_integer':55,'square_sum_integer':385,'scale':1}
    avg = m.reference_ci(moments,'AVG',200,20)
    count = m.reference_ci(moments,'COUNT',200,20)
    total = m.reference_ci(moments,'SUM',200,20)
    assert avg['standard_error'] ** 2 == pytest.approx(11/12)
    assert count['point'] == 100
    assert count['standard_error'] ** 2 == pytest.approx(500)
    assert total['point'] == 550
    assert total['standard_error'] ** 2 == pytest.approx(24750)
    assert total['z'] == pytest.approx(1.6448536269514722)


def test_large_integer_squares_do_not_cancel_away_variance():
    base = 10**12
    moments = {'count':10,'filter_count':10,'sum_integer':10*base+55,
               'square_sum_integer':10*base*base+110*base+385,'scale':1}
    result = module().reference_ci(moments,'AVG',200,20)
    assert result['standard_error']**2 == pytest.approx(11/12)


def test_sample_count_below_ten_is_saved_as_excluded():
    result = module().reference_ci({'count':9,'filter_count':9,'sum_integer':45,
                                    'square_sum_integer':285,'scale':1},'AVG',200,20)
    assert result['eligible'] is False
    assert result['status'] == 'EXCLUDED_SAMPLE_COUNT_LT_10'
    assert result['interval'] is None


def test_sealed_preparation_refuses_changed_artifact(tmp_path):
    m = module()
    target = tmp_path/'values.npy'; np.save(target,np.arange(4))
    record = m.seal_record(target,tmp_path)
    target.write_bytes(b'changed')
    with pytest.raises(ValueError,match='sealed artifact'):
        m.verify_artifacts([record],tmp_path)


def test_golden_preparation_and_model_reuse_preserve_numeric_fd_and_exact_population(monkeypatch):
    m=module()
    assert hasattr(m,'prepare_input'), 'Sealed Flights preparation is not implemented'
    source=m.load_generated_input('golden-200k/continuous',paper=False)
    prepared=m.prepare_input(source,max_rows=10000000,seed=1)
    assert prepared['actual_training_rows']==1993
    assert {'flights.dep_delay','flights.distance','flights.arr_delay','flights.taxi_in','flights.taxi_out','flights.air_time'} <= set(prepared['columns'])
    assert 'flights.origin_state_abr' not in prepared['columns']
    assert 'flights.dest_state_abr' not in prepared['columns']
    assert hasattr(m,'train_model'), 'Recoverable Flights model stage is not implemented'
    trained=m.train_model(prepared)
    from ensemble_compilation.spn_ensemble import read_ensemble
    from aqp_spn.aqp_spn import AQPSPN
    model=read_ensemble(str(ROOT/trained['model_path'])).spns[0]
    assert model.full_join_size==200000
    assert model.full_sample_size==1993
    before=(ROOT/trained['model_path']).stat().st_mtime_ns
    preparation_mtimes={r['path']:(ROOT/r['path']).stat().st_mtime_ns for r in prepared['artifacts']}
    import data_preparation.prepare_single_tables as original
    monkeypatch.setattr(original,'prepare_single_table',lambda *a,**k: (_ for _ in ()).throw(AssertionError('trusted preparation repeated')))
    assert m.prepare_input(source,max_rows=10000000,seed=1)==prepared
    assert {r['path']:(ROOT/r['path']).stat().st_mtime_ns for r in prepared['artifacts']}==preparation_mtimes
    monkeypatch.setattr(AQPSPN,'learn',lambda *a,**k: (_ for _ in ()).throw(AssertionError('trusted model retrained')))
    again=m.train_model(prepared)
    assert again==trained
    assert (ROOT/again['model_path']).stat().st_mtime_ns==before


def test_golden_all12_queries_keep_all296_truth_groups_and_reference_exclusions():
    m=module()
    assert hasattr(m,'evaluate_model'), 'Flights all-group AQP/CI evaluation is not implemented'
    source=m.load_generated_input('golden-200k/continuous',paper=False)
    prepared=m.prepare_input(source,max_rows=10000000,seed=1)
    trained=m.train_model(prepared)
    result=m.evaluate_model(trained,source)
    assert result['paper_scale_reached'] is False
    assert result['population_rows']==200000 and result['actual_training_rows']==1993
    assert len(result['queries'])==12
    assert result['query_errors']==0
    assert sum(q['truth_groups'] for q in result['queries'])==296
    assert sum(q['ci_excluded_groups'] for q in result['queries'])>0
    for truth,actual in zip(source['truth']['queries'],result['queries']):
        assert {tuple(g['key']) for g in truth['groups']} <= {tuple(g['key']) for g in actual['groups']}


def test_released_sum_reference_dimensional_mismatch_is_visible():
    m=module()
    moment={'count':10,'filter_count':10,'sum_integer':55,'square_sum_integer':385,'scale':1}
    corrected=m.reference_ci(moment,'SUM',200,20)
    comparison=m.legacy_comparison(moment,'SUM',200,20,corrected)
    assert corrected['standard_error']**2==pytest.approx(24750)
    assert (comparison['released_reference_half_width']/corrected['z'])**2==pytest.approx(15606.25)
    assert comparison['status']=='COMPARED_NOT_USED_AS_TRUTH'


def test_formal_training_is_blocked_without_memory_release():
    import copy
    m=module()
    source=m.load_generated_input('golden-200k/continuous',paper=False)
    prepared=copy.deepcopy(m.prepare_input(source,max_rows=10000000,seed=1))
    prepared['source']['population_rows']=1000000000
    with pytest.raises(ValueError,match='memory release'):
        m.train_model(prepared)


def test_incomplete_generation_is_rejected_before_sample_access(tmp_path,monkeypatch):
    import json
    m=module()
    output=tmp_path/'flights/incomplete'; output.mkdir(parents=True)
    original=ROOT/'output/full/flights/golden-200k/continuous'
    for name in ['generation_result.json','ground_truth.json','checkpoint.json']:
        body=json.loads((original/name).read_text())
        if name=='generation_result.json': body['status']='PARTIAL'
        (output/name).write_text(json.dumps(body))
    monkeypatch.setattr(m,'FULL',tmp_path)
    with pytest.raises(ValueError,match='incomplete'):
        m.load_generated_input('incomplete',paper=False)


def test_original_model_aggregates_ignore_null_sentinel_and_respect_strict_boundary():
    from aqp_spn.aqp_spn import AQPSPN
    from ensemble_compilation.spn_ensemble import SPNEnsemble
    from evaluation.utils import parse_query
    from full_factor_cache import model_aware_factor_cache
    from rspn.structure.leaves import IdentityNumericLeaf
    from spn.structure.Base import assign_ids
    from spn.structure.StatisticalTypes import MetaType
    m=module(); schema=m.schema_for_input('unused.csv',4)
    model=AQPSPN([MetaType.REAL],[9999.],4,schema,[],full_sample_size=4,
                 table_set={'flights'},column_names=['flights.distance'],
                 table_meta_data={'flights':{'fd_dict':{},'categorical_columns_dict':{}}})
    model.mspn=IdentityNumericLeaf([2500.,2500.1,2600.,9999.],[.25]*4,9999.,[0],cardinality=4)
    assign_ids(model.mspn)
    ensemble=SPNEnsemble(schema,[model])
    with model_aware_factor_cache():
        for sql,expected in [("SELECT AVG(distance) FROM flights;",7600.1/3),
                             ("SELECT COUNT(*) FROM flights WHERE distance>2500;",2.),
                             ("SELECT COUNT(*) FROM flights WHERE distance>=2500;",3.)]:
            ensemble.cached_expecation_vals={}
            _,actual=ensemble.evaluate_query(parse_query(sql,schema))
            assert float(actual)==pytest.approx(expected)
