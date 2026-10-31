import importlib.util
from pathlib import Path
import json

import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_verdict_flights.py'
    assert path.exists(),'Formal existing-sample Verdict adapter is missing'
    spec=importlib.util.spec_from_file_location('full_verdict_flights',str(path))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def test_compound_plan_retains_raw_and_two_original_grouped_sums_without_ci_composition():
    m=module()
    sql='SELECT origin, SUM(taxi_out)-SUM(taxi_in) FROM flights WHERE distance>2500 GROUP BY origin;'
    plan=m.projection_plan(sql)
    assert plan['raw_sql']==sql
    assert plan['adapter_sqls']==[sql.replace('SUM(taxi_out)-SUM(taxi_in)','SUM(taxi_out)'),sql.replace('SUM(taxi_out)-SUM(taxi_in)','SUM(taxi_in)')]
    assert plan['adapter_ci_status']=='UNSUPPORTED_NO_COVARIANCE_MODEL'
    assert m.projection_plan('SELECT COUNT(*) FROM flights;')['adapter_sqls']==[]


def test_import_contract_uses_generation_sample_bytes_and_no_truth(tmp_path,monkeypatch):
    m=module();sample=tmp_path/'sample.csv';sample.write_text(','.join(m.COLUMNS)+'\n2000,AA,A,X,B,Y,1,2,3,4,5,6\n')
    expected=dict(offset=sample.stat().st_size,sha256=m.digest(sample))
    binding=dict(config=dict(rows=1000000000))
    checkpoint=dict(binding=m.bhash(binding),binding_details=binding,rows_generated=1000000000,sample_rows=1,files={'sample.csv':expected})
    checkpoint['checkpoint_sha256']=m.bhash(checkpoint)
    report=dict(status='PASS',rows_generated=1000000000,sample_rows=1,paper_scale_reached=True,binding=checkpoint['binding'],files={'sample.csv':expected})
    cp=tmp_path/'checkpoint.json';cp.write_text(json.dumps(checkpoint));rp=tmp_path/'generation_result.json';rp.write_text(json.dumps(report))
    contract=m.source_contract(rp,cp,sample)
    assert contract['population_rows']==1000000000 and contract['sample_rows']==1
    assert contract['query_truth_used_for_registration'] is False
    assert 'truth' not in contract
    sample.write_text(sample.read_text()+'corrupt\n')
    with pytest.raises(ValueError,match='sample'):m.source_contract(rp,cp,sample)


def test_all_group_comparison_keeps_missing_extra_zero_and_engine_error():
    m=module()
    truth=[dict(key=['a'],numerator=0,denominator=1),dict(key=['b'],numerator=4,denominator=1)]
    result=m.compare_groups(truth,{('a',):1.,('c',):2.},error='timeout')
    assert {r['status'] for r in result}=={'MATCHED','MISSING_MODEL_GROUP','EXTRA_MODEL_GROUP'}
    zero=next(r for r in result if r['key']==['a'])
    assert zero['zero_truth'] is True and zero['relative_error'] is None
    assert all(r['engine_error']=='timeout' for r in result)
