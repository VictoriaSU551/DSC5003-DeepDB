"""Pure route/cohort/NULL/information-budget fixtures; no engine or real data."""
import copy
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_dbest_flights_routes.py';assert p.exists(),'Independent original DBEst 1D routes module missing'
    s=importlib.util.spec_from_file_location('dbest_routes_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def row(**values):
    result=dict(ORIGIN='ATL',DEST='HPN',ORIGIN_STATE_ABR='CA',DEST_STATE_ABR='HI',UNIQUE_CARRIER='UA',YEAR_DATE='2005',
        DEP_DELAY='2',ARR_DELAY='3',AIR_TIME='10',TAXI_OUT='5',TAXI_IN='1',DISTANCE='100')
    result.update(values);return result


def selected(rows):return dict(row_ids=list(range(10,10+len(rows))),rows=rows)


def test_exact12_support_keeps_prior4_reference_only_and_variants_explicit():
    m=module();support=m.support_table();assert len(support)==12
    assert [s['query_no'] for s in support if s['status']=='REFERENCE_ONLY_FROZEN_76_CALLS']==[0,1,5,8]
    assert support[7]['status']=='QUERY_AWARE_EXACT_YEAR_PREFILTER_VARIANT'
    assert all(support[i]['status']=='NOT_DBEST_KDE_CATEGORY_LEARNING' for i in (2,3,4))
    assert support[9]['status']=='UNSUPPORTED_MULTIDIMENSIONAL'
    sql=(ROOT/'code/benchmarks/flights/sql/aqp_queries.sql').read_text().splitlines();m.validate_sqls(sql)
    bad=sql.copy();bad[-1]=bad[0]
    with pytest.raises(ValueError):m.validate_sqls(bad)


def test_catalog_membership_nonnull_metadata_and_no_truth_dependency():
    m=module();rows=[row(),row(ORIGIN_STATE_ABR='NV',AIR_TIME=None,TAXI_IN=None),row(DEST='OTHER',YEAR_DATE='2006')]
    catalog=m.build_catalog(iter(rows),1,100,3)
    assert catalog['rows']==3 and catalog['probability']=={'numerator':1,'denominator':100}
    ca=next(g for g in catalog['queries']['6'] if g['key']==['CA'])
    nv=next(g for g in catalog['queries']['6'] if g['key']==['NV'])
    assert ca['members']==1 and ca['nonnull']=={'air_time':1} and nv['members']==1 and nv['nonnull']=={'air_time':0}
    prior=m.population_metadata(ca,'air_time',catalog['probability'])
    assert prior['Nhat']==100 and prior['variance']==9900 and prior['estimated'] is True
    # There is no truth argument; adding irrelevant answer fields cannot alter counts.
    changed=[dict(r,COUNT=999999,SUM=-999999,value=123) for r in rows]
    assert m.build_catalog(changed,1,100,3)==catalog
    # Category metadata must not parse, multiply or otherwise use aggregate values.
    changed=[dict(r,**{c:None if r[c] is None else 'unread_aggregate_value' for c in ('AIR_TIME','ARR_DELAY','DEP_DELAY','TAXI_OUT','TAXI_IN')}) for r in rows]
    assert m.build_catalog(changed,1,100,3)==catalog
    with pytest.raises(ValueError):m.build_catalog(rows,1,100,4)


def test_signed_product_is_per_row_and_separate_taxi_null_masks_keep_fixed_ids():
    m=module();rows=[row(ARR_DELAY='1',DEP_DELAY='3',TAXI_IN=None),row(ARR_DELAY='3',DEP_DELAY='1',TAXI_OUT=None),row(ARR_DELAY='-2',DEP_DELAY='0')]
    data=selected(rows);cat=m.build_catalog(rows,1,100,3);jobs=m.make_jobs(data,cat)
    product=next(j for j in jobs if j['query_no']==10)
    assert product['xs']==[3.,3.,0.] and product['row_ids']==data['row_ids']
    assert sum(product['xs'])!=sum(float(r['ARR_DELAY']) for r in rows)*sum(float(r['DEP_DELAY']) for r in rows)/3
    out=next(j for j in jobs if j['query_no']==11 and j['component']=='taxi_out')
    inn=next(j for j in jobs if j['query_no']==11 and j['component']=='taxi_in')
    assert out['row_ids']==[10,12] and inn['row_ids']==[11,12]
    assert out['population_metadata']['retained_nonnull_count']==inn['population_metadata']['retained_nonnull_count']==2
    with pytest.raises(ValueError):m.make_jobs(dict(data,row_ids=[10,10,12]),cat)


def test_year_equality_is_exact_variant_and_fractional_years_are_not_rounded():
    m=module();rows=[row(ORIGIN='PHX',YEAR_DATE=v) for v in ('2004','2005','2005.0','2006')]
    jobs=m.make_jobs(selected(rows),m.build_catalog(rows,1,100,4));year=next(j for j in jobs if j['query_no']==7)
    assert year['row_ids']==[11,12] and year['scope']=='QUERY_AWARE_EXACT_YEAR_PREFILTER_VARIANT'
    with pytest.raises(ValueError):m.build_catalog([row(ORIGIN='PHX',YEAR_DATE='2005.5')],1,100,1)


def test_unknown_and_empty_selected_groups_are_retained_and_child_failures_are_never_zero():
    m=module();rows=[row(),row(ORIGIN_STATE_ABR='NV',DEST_STATE_ABR='TX')];cat=m.build_catalog(rows,1,100,2)
    jobs=m.make_jobs(selected(rows[:1]),cat)
    assert any(j['query_no']==6 and j['key']==['NV'] and j['xs']==[] for j in jobs)
    good=dict(query_no=11,key=['HI'],component='taxi_out',status='RETURNED',estimate=10.,parent_sql_sha256='a'*64)
    right=dict(good,component='taxi_in',estimate=3.)
    assert m.combine_children(good,right)['estimate']==7.
    for bad in (None,dict(right,status='FIT_ERROR',estimate=None),dict(right,estimate=float('nan')),dict(right,estimate=None)):
        assert m.combine_children(good,bad)['estimate'] is None
    with pytest.raises(ValueError):m.combine_children(good,dict(right,key=['OTHER']))


def test_training_selection_and_original_units_are_not_replaced_by_answer_metadata():
    m=module();rows=[row(AIR_TIME='-1.2',ARR_DELAY='-2.5',DEP_DELAY='4')];data=selected(rows)
    jobs=m.make_jobs(data,m.build_catalog(rows,1,100,1))
    assert next(j for j in jobs if j['query_no']==6)['xs']==[-1.2]
    assert next(j for j in jobs if j['query_no']==10)['xs']==[-10.]
    for j in jobs:
        assert set(j['row_ids'])<=set(data['row_ids']) and j['fit_rows']==len(j['row_ids'])
        assert j['population_metadata']['target_answer_used'] is False
    with pytest.raises(ValueError):m.make_jobs(dict(row_ids=list(range(20001)),rows=[row()]*20001),{})


def test_assembled_queries_and_evaluation_preserve_missing_extra_and_zero_truth_without_training_answers():
    m=module();rows=[row()];jobs=m.make_jobs(selected(rows),m.build_catalog(rows,1,100,1))
    results=[]
    for j in jobs:
        results.append(dict(query_no=j['query_no'],key=j['key'],component=j['component'],parent_sql_sha256=j['parent_sql_sha256'],
            job_id=j['job_id'],status='RETURNED',estimate=10. if j['component']=='taxi_out' else 3.,native={'api_calls':1}))
    queries=m.assemble_queries(jobs,results)
    assert [q['query_no'] for q in queries]==[6,7,10,11]
    assert queries[-1]['groups'][0]['estimate']==7. and queries[-1]['groups'][0]['ci_status']=='UNSUPPORTED_NO_COVARIANCE_MODEL'
    truth={'population_rows':m.N,'complete':True,'queries':[dict(query_no=i,query_name=m.QUERY_NAMES[i],sql=m.SQLS[i],groups=[]) for i in range(12)]}
    truth['queries'][6]['groups']=[dict(key=['NV'],numerator=0,denominator=1),dict(key=['XX'],numerator=100,denominator=1)]
    output=m.evaluate(queries,truth);q=next(q for q in output if q['query_no']==6)
    assert q['missing_truth_groups']==[['NV'],['XX']] and q['extra_prediction_groups']==[['CA']]
    assert q['missing_nonzero_penalty_count']==1 and q['zero_truth_groups']==1
    malformed=copy.deepcopy(truth);malformed['queries'][-1]['sql']=malformed['queries'][0]['sql']
    with pytest.raises(ValueError):m.evaluate(queries,malformed)


def identity_truth(m,population_rows=None):
    return dict(population_rows=m.N if population_rows is None else population_rows,complete=True,
        queries=[dict(query_no=i,query_name=m.QUERY_NAMES[i],sql=m.SQLS[i],groups=[]) for i in range(12)])


def test_exact_bound_query3_single_space_truth_is_evaluable_without_changing_sqls_or_math():
    m=module();truth=identity_truth(m)
    queries=[dict(query_no=s['query_no'],name=s['name'],scope=s['scope'],groups=[]) for s in m.route_specs()]
    queries[1]['groups']=[dict(key=['UA'],estimate=7.)]
    truth['queries'][7]['groups']=[dict(key=['UA'],numerator=4,denominator=1)]
    original=m.evaluate(queries,truth)
    assert original[1]['scope']==m.VARIANT and original[1]['groups'][0]['relative_error']==.75
    actual_sql="SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest_state_abr='CA' GROUP BY unique_carrier;"
    truth['queries'][3]['sql']=actual_sql
    assert m.evaluate(queries,truth)==original
    assert m.validate_truth_identity(truth,m.N)==[dict(query_no=3,query_name='F2.2',actual_sql=actual_sql,
        expected_sql=m.SQLS[3],alias='SOURCE_BOUND_QUERY3_SINGLE_SPACE')]
    assert 'AND  dest' in m.SQLS[3]
    assert m.validate_truth_identity(identity_truth(m),m.N)==[]
    assert m.validate_truth_identity(identity_truth(m,200000),200000)==[]


@pytest.mark.parametrize('mutation',[
    lambda t:t['queries'][3].update(sql=t['queries'][3]['sql'].replace("dest_state_abr='CA'","dest_state_abr='HI'")),
    lambda t:t['queries'][3].update(sql=t['queries'][3]['sql'].replace("'LA'","'LA '")),
    lambda t:t['queries'][3].update(sql=t['queries'][3]['sql'].replace('AND  dest','AND   dest')),
    lambda t:t['queries'][7].update(sql=t['queries'][7]['sql'].replace('AND origin','AND  origin')),
    lambda t:t['queries'][3].update(query_no=4),
    lambda t:t['queries'][0].update(query_no=False),
    lambda t:t['queries'][3].update(query_name='F2.3'),
    lambda t:t.update(complete=False),
    lambda t:t.update(population_rows=200000),
    lambda t:t['queries'].pop(),
    lambda t:t['queries'].append(copy.deepcopy(t['queries'][3])),
])
def test_truth_alias_does_not_normalize_other_sql_or_relax_complete12_identity(mutation):
    m=module();truth=identity_truth(m);mutation(truth)
    with pytest.raises(ValueError):m.validate_truth_identity(truth,m.N)
