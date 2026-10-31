"""Pure derived DBEst tables; all acceptance is synthetic and counted."""
import copy
import importlib
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'code'))


def module():
    assert (ROOT/'code/full_dbest_flights_routes_tables.py').exists(),'Independent route consumer missing'
    return importlib.import_module('full_dbest_flights_routes_tables')


def raw(i,key,component='value',status='RETURNED',estimate=10):
    return dict(query_no=i,key=key,component=component,parent_sql_sha256='a'*64,status=status,estimate=estimate,fit_attempted=status!='UNAVAILABLE_FIXED_SAMPLE',
        native=dict(api_calls=int(status in ('RETURNED','NATIVE_ERROR','NATIVE_NONFINITE','NATIVE_NULL','NUMERICAL_VALIDATION_FAILED')),error=None,kde_calls=1,kde_evaluations=1),
        job=dict(population_metadata=dict(target_answer_used=False,Nhat=100,estimated=True),fit_rows=3))


def data(m):
    truth=dict(complete=True,population_rows=10**9,queries=[])
    legacy=dict(status='PASS_WITH_GAPS',population_rows=10**9,retained_sample_rows=9997912,unique_fit_rows=20000,
        paper_DBEst_training_configuration_recovered=False,native_method_calls_total_verified=76,queries=[])
    queries=[]
    for i,name in enumerate(m.routes.QUERY_NAMES):
        key=[] if i in (0,1) else ['1995'] if i in (5,10) else ['X']
        truth['queries'].append(dict(query_no=i,query_name=name,sql=m.routes.SQLS[i],groups=[dict(key=key,numerator=10,denominator=1)]))
        legacy['queries'].append(dict(query_no=i,name=name,status='SUPPORTED' if i in m.LEGACY else 'UNSUPPORTED',predictions=[dict(group='all' if not key else key[0],estimate=10,native=dict(integral_verified=True))] if i in m.LEGACY else []))
    for spec in m.routes.route_specs():
        i=spec['query_no'];key=truth['queries'][i]['groups'][0]['key']
        children=[raw(i,key,c,estimate=12 if c=='taxi_out' else 2 if c=='taxi_in' else 10) for c in spec['components']]
        g=dict(key=key,estimate=10,status='POINT_DIFFERENCE_RETURNED' if i==11 else 'RETURNED',native_results=children,
            ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL' if i==11 else 'UNSUPPORTED_ORIGINAL_1D_QUERY_CI')
        if i==11:g['adapter']=dict(interval=None,ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL')
        queries.append(dict(spec,groups=[g],original_api_calls=len(children),target_answers_used_for_training=False))
    return legacy,queries,truth


def test_exact_sql_variant_is_scored_separately_from_author_prefilter_and_two_sum_has_no_joint_ci():
    m=module();old,q,t=data(m);q[1]['groups'][0]['estimate']=8;result=m.derive(old,q,t)
    assert len(result['queries'])==12
    variant=result['queries'][7]
    assert variant['scoring_allowed'] is True and variant['all_nonzero_truth_mean_relative_error']==pytest.approx(.2)
    assert variant['evaluation_sql_match'] is True and variant['author_prefilter_config_match'] is False
    assert variant['scope']=='QUERY_AWARE_EXACT_YEAR_PREFILTER_VARIANT'
    assert variant['finite_output_points']==variant['truth_groups']==variant['finite_matched_groups']==1
    assert variant['missing_groups']==variant['extra_groups']==variant['zero_truth_groups']==0
    rows=[r for r in result['groups'] if r['query_no']==7]
    assert len(rows)==1 and rows[0]['truth_numerator']=='10' and rows[0]['truth_denominator']=='1'
    assert rows[0]['absolute_error']==2 and rows[0]['relative_error']==pytest.approx(.2)
    assert rows[0]['evaluation_sql_match'] is True and rows[0]['author_prefilter_config_match'] is False
    assert rows[0]['status']=='MATCHED' and m.POLICY['shared_method_ranking'] is False
    assert next(r for r in result['groups'] if r['query_no']==11)['ci_status']=='UNSUPPORTED_NO_COVARIANCE_MODEL'
    assert len([r for r in result['components'] if r['query_no']==11])==2


@pytest.mark.parametrize('i',range(12))
def test_wrong_target_sql_is_rejected_for_every_query_including_scored_variant(i):
    m=module();old,q,t=data(m);t['queries'][i]['sql']+=' '
    with pytest.raises(ValueError):m.derive(old,q,t)


def test_source_bound_q3_alias_delegates_once_to_real_helper_and_records_literal_provenance(monkeypatch):
    m=module();old,q,t=data(m)
    actual="SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest_state_abr='CA' GROUP BY unique_carrier;"
    expected="SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND  dest_state_abr='CA' GROUP BY unique_carrier;"
    t['queries'][3]['sql']=actual
    helper=m.routes.validate_truth_identity;calls=[]
    def counted(truth,population_rows):
        calls.append((truth,population_rows));return helper(truth,population_rows)
    monkeypatch.setattr(m.routes,'validate_truth_identity',counted)
    result=m.derive(old,q,t)
    assert len(calls)==1 and calls[0]==(t,1000000000)
    assert result['truth_identity_aliases']==[dict(query_no=3,query_name='F2.2',actual_sql=actual,expected_sql=expected,alias='SOURCE_BOUND_QUERY3_SINGLE_SPACE')]
    assert result['queries'][3]['evaluation_sql_identity']=='SOURCE_BOUND_QUERY3_SINGLE_SPACE'
    assert result['queries'][7]['evaluation_sql_identity']=='EXACT_LITERAL'
    assert t['queries'][3]['sql']==actual


def test_empty_fit_error_unsupported_missing_invalid_zero_negative_null_and_extra_are_not_conditional_full_coverage():
    m=module();old,q,t=data(m);a=q[0];ref=t['queries'][6]
    for label,state in [('empty','UNAVAILABLE_FIXED_SAMPLE'),('fit','FIT_ERROR'),('budget','NUMERICAL_BUDGET_UNSUPPORTED')]:
        key=[label];ref['groups'].append(dict(key=key,numerator=10,denominator=1));a['groups'].append(dict(key=key,status=state,estimate=None,ci_status='UNSUPPORTED_ORIGINAL_1D_QUERY_CI',native_results=[raw(6,key,component='air_time',status=state,estimate=None)]))
    ref['groups'] += [dict(key=['missing'],numerator=10,denominator=1),dict(key=['zero'],numerator=0,denominator=1),dict(key=[None],numerator=-10,denominator=1),dict(key=['None'],numerator=10,denominator=1)]
    for key,p in [(['zero'],0),([None],-8),(['None'],float('nan')),(['extra'],5)]:
        a['groups'].append(dict(key=key,status='RETURNED',estimate=p,ci_status='UNSUPPORTED_ORIGINAL_1D_QUERY_CI',native_results=[raw(6,key,component='air_time',estimate=p)]))
    a['original_api_calls']=sum(r['native']['api_calls'] for g in a['groups'] for r in g['native_results'])
    r=m.derive(old,q,t);s=r['queries'][6]
    assert s['all_nonzero_truth_mean_relative_error'] is None and s['matched_conditional_mean_relative_error']==pytest.approx(.1)
    assert s['missing_groups']==1 and s['unavailable_groups']==3 and s['invalid_points']==1 and s['extra_groups']==1 and s['zero_truth_groups']==1
    assert r['counters']['empty_fixed_sample_components']==1 and r['counters']['fit_errors']==1 and r['counters']['numerical_budget_unsupported']==1
    null=next(g for g in r['groups'] if g['query_no']==6 and g['key_json']=='[null]');assert null['relative_error']==pytest.approx(.2)


@pytest.mark.parametrize('bad',['number','duplicate','sql','variant_flag','training_truth','metadata_truth','ci','difference','group_width','legacy_scope','legacy_calls'])
def test_query_label_component_and_scope_corruption_rejected(bad):
    m=module();old,q,t=data(m)
    if bad=='number':q[0]['query_no']=True
    if bad=='duplicate':q[0]['groups'].append(copy.deepcopy(q[0]['groups'][0]))
    if bad=='sql':t['queries'][0]['sql']+=' '
    if bad=='variant_flag':q[1]['public_prefilter_matches']=True
    if bad=='training_truth':q[0]['target_answers_used_for_training']=True
    if bad=='metadata_truth':q[0]['groups'][0]['native_results'][0]['job']['population_metadata']['target_answer_used']=True
    if bad=='ci':q[-1]['groups'][0]['adapter']['interval']=[1,2]
    if bad=='difference':q[-1]['groups'][0]['estimate']=999
    if bad=='group_width':q[0]['groups'][0]['key']=[];q[0]['groups'][0]['native_results'][0]['key']=[]
    if bad=='legacy_scope':old['population_rows']=200000
    if bad=='legacy_calls':old['native_method_calls_total_verified']=75
    with pytest.raises(ValueError):m.derive(old,q,t)


def fixture(tmp_path,monkeypatch,alias=False):
    m=module();old,q,t=data(m);home=tmp_path/'output/full/dbest_flights_routes/runs/formal_synthetic';home.mkdir(parents=True)
    if alias:t['queries'][3]['sql']="SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest_state_abr='CA' GROUP BY unique_carrier;"
    for name in m.SOURCE_FILES:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    for owner,name in ((m,'code/full_dbest_flights_routes_tables.py'),(m.routes,'code/full_dbest_flights_routes.py'),(m.ops,'code/full_dbest_flights_routes_run.py'),(m.audit,'code/full_dbest_flights_routes_audit.py')):monkeypatch.setattr(owner,'__file__',str(tmp_path/name))
    def save(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True),encoding='utf-8');return m.record(path,tmp_path)
    label='output/full/flights/flights-1b/ground_truth.json';tr=save(tmp_path/label,t);lg=save(tmp_path/m.LEGACY_PATH,old);monkeypatch.setattr(m,'LEGACY_SHA',lg['sha256'])
    d=m.derive(old,q,t);c=d['counters'];source=dict(source_report_sha256=lg['sha256'],files_sha256={m.LEGACY_PATH:lg['sha256']},complete_inventory_sha256='b'*64)
    plan=dict(kind='ROUTES',binding_sha256='a'*64,population=dict(name='FORMAL_1B',population_rows=10**9,retained_rows=9997912,fit_rows=20000,seed=74131,truth=dict(path=label)),population_inputs={label:tr},source=source,original_four_classes_reexecuted=False)
    worker=dict(new_fit_attempts=c['fit_attempts'],new_original_api_calls=c['native_calls'],original_prior_classes_reexecuted=False,new_query_evaluation_only_after_raw_predictions=True)
    for name,value in [('plan.json',plan),('queries.json',q),('worker.json',worker),('support.json',m.routes.support_table()),('evaluation.json',dict(heldout=True))]:save(home/name,value)
    final=dict(binding_sha256=plan['binding_sha256'],files={n:m.record(home/n,tmp_path) for n in ('plan.json','queries.json','worker.json','support.json','evaluation.json')},author_training_configuration_recovered=False,full_paper_reproduction_complete=False)
    fr=save(home/'final.json',final);save(home/'final.seal.json',dict(sha256=fr['sha256']));save(home/'lifecycle.json',dict(status='PASS',final_sha256=fr['sha256']))
    proof=dict(status='PASS_READONLY_ORIGINAL_DBEST_ROUTE_EVIDENCE_WITH_GAPS',kind='ROUTES',population='FORMAL_1B',final=fr,plan=m.record(home/'plan.json',tmp_path),source_complete_inventory_sha256='b'*64,
        native_calls=c['native_calls'],native_fit_errors=c['fit_errors'],coverage_gaps=c['coverage_gaps'],numerical_validation_failures=c['numerical_validation_failures'],author_training_configuration_recovered=False,full_paper_reproduction_complete=False,
        files_written=False,models_loaded=False,scientific_calls_executed=False,processes_executed=False,database_connected=False)
    calls=[];monkeypatch.setattr(m.audit,'verify',lambda h:calls.append(h) or proof)
    return m,home,proof,calls


def test_build_one_strict_audit_no_other_f_or_science_and_exact_derived_reuse(tmp_path,monkeypatch):
    m,h,p,calls=fixture(tmp_path,monkeypatch)
    import io,pickle,socket,sqlite3,subprocess
    def forbidden(*a,**k):pytest.fail('Derived export attempted a second F or scientific operation')
    for n in ('source_proof','scan_category_file','execute_job','selected_rows','plan','run'):monkeypatch.setattr(m.ops,n,forbidden)
    monkeypatch.setattr(m.routes,'gaussian_oracle',forbidden)
    for owner,n in ((pickle,'load'),(pickle,'loads'),(socket,'create_connection'),(sqlite3,'connect'),(subprocess,'Popen')):monkeypatch.setattr(owner,n,forbidden)
    opening=io.open
    def bounded_open(path,mode='r',*a,**k):
        path=Path(path).resolve()
        if any(c in mode for c in 'wax+'):
            assert tmp_path/'output/full/figures' in path.parents
        else:assert path.suffix!='.pkl' and path.name!='sample.csv'
        return opening(path,mode,*a,**k)
    monkeypatch.setattr(io,'open',bounded_open)
    before={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in h.iterdir()}
    out=m.build(h,root=tmp_path);assert len(calls)==1
    folder=tmp_path/out['directory'];manifest=m.ops.strict_read(folder/'manifest.json')
    assert manifest['historical_native_calls']==76 and manifest['new_route_native_calls']==p['native_calls'] and manifest['native_calls_during_export']==0
    assert len(manifest['summary']['queries'])==12 and manifest['full_paper_reproduction_complete'] is False and manifest['author_training_configuration_recovered'] is False
    assert {x.name for x in folder.iterdir()}=={'query_summary.csv','group_results.csv','native_components.csv','RESULTS.md','manifest.json'}
    text=(folder/'RESULTS.md').read_text();assert 'LOCAL F3.3 variant' in text and 'no joint CI' in text and 'conditional' in text
    assert manifest['identity']['policy']['q7_official_truth_applied'] is True
    assert manifest['summary']['queries'][7]['evaluation_sql_match'] is True and manifest['summary']['queries'][7]['author_prefilter_config_match'] is False
    frozen={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in folder.iterdir()}
    assert m.build(h,root=tmp_path)==out and len(calls)==2
    assert frozen=={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in folder.iterdir()} and before=={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in h.iterdir()}


def test_build_binds_explicit_alias_with_raw_label_unchanged_after_one_offline_audit(tmp_path,monkeypatch):
    m,h,p,calls=fixture(tmp_path,monkeypatch,alias=True)
    label=tmp_path/'output/full/flights/flights-1b/ground_truth.json';before=(label.read_bytes(),label.stat().st_mtime_ns)
    out=m.build(h,root=tmp_path);manifest=m.ops.strict_read(tmp_path/out['directory']/'manifest.json')
    assert calls==[h] and (label.read_bytes(),label.stat().st_mtime_ns)==before
    aliases=manifest['identity']['truth_identity_aliases']
    assert len(aliases)==1 and aliases[0]['query_no']==3 and aliases[0]['alias']=='SOURCE_BOUND_QUERY3_SINGLE_SPACE'
    assert manifest['summary']['queries'][3]['evaluation_sql_identity']=='SOURCE_BOUND_QUERY3_SINGLE_SPACE'
    assert manifest['author_training_configuration_recovered'] is manifest['full_paper_reproduction_complete'] is False


@pytest.mark.parametrize('bad',['population','kind','status','loaded','native_counter','old_sha','label','query_file','source','output','output_extra','output_selfseal'])
def test_wrong_acceptance_or_changed_inputs_and_outputs_fail_closed(tmp_path,monkeypatch,bad):
    m,h,p,calls=fixture(tmp_path,monkeypatch);out=m.build(h,root=tmp_path);folder=tmp_path/out['directory']
    if bad=='population':p['population']='GOLDEN_200K'
    if bad=='kind':p['kind']='CATALOG'
    if bad=='status':p['status']='PASS'
    if bad=='loaded':p['models_loaded']=True
    if bad=='native_counter':p['native_calls']+=1
    if bad=='old_sha':(tmp_path/m.LEGACY_PATH).write_text('{}')
    if bad=='label':(tmp_path/'output/full/flights/flights-1b/ground_truth.json').write_text('{}')
    if bad=='query_file':(h/'queries.json').write_text('[]')
    if bad=='source':(tmp_path/'code/full_dbest_flights_routes_audit.py').write_text('changed')
    if bad=='output':(folder/'group_results.csv').write_text('changed')
    if bad=='output_extra':(folder/'private').write_text('changed')
    if bad=='output_selfseal':
        (folder/'RESULTS.md').write_text('changed');v=m.ops.strict_read(folder/'manifest.json');v['files']['RESULTS.md']=m.record(folder/'RESULTS.md',tmp_path)
        v['self_sha256']=m.routes.value_hash({k:x for k,x in v.items() if k!='self_sha256'});(folder/'manifest.json').write_text(json.dumps(v))
    with pytest.raises(ValueError):m.build(h,root=tmp_path)


def test_missing_accepted_result_refuses_export_after_one_offline_entry(tmp_path,monkeypatch):
    m,h,p,calls=fixture(tmp_path,monkeypatch)
    def absent(home):calls.append(home);raise ValueError('No accepted formal result')
    monkeypatch.setattr(m.audit,'verify',absent)
    with pytest.raises(ValueError):m.build(h,root=tmp_path)
    assert calls==[h] and not (tmp_path/'output/full/figures').exists()


def test_redirected_derived_namespace_is_rejected_before_writing(tmp_path,monkeypatch):
    m,h,p,calls=fixture(tmp_path,monkeypatch);resolve=Path.resolve;outside=tmp_path.parent/'outside_dbexport'
    def redirected(path,*a,**k):
        if path.parent==tmp_path/'output/full/figures' and path.name.startswith('dbest_routes_'):return outside
        return resolve(path,*a,**k)
    monkeypatch.setattr(Path,'resolve',redirected)
    with pytest.raises(ValueError):m.build(h,root=tmp_path)
    assert not (tmp_path/'output/full/figures').exists() and not outside.exists()
