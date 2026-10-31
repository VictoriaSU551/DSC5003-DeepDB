"""Independent, coverage-aware formal DBEst route tables. No scientific work."""
import argparse
import csv
from fractions import Fraction
import io
import json
import math
import os
from pathlib import Path
import full_dbest_flights_routes as routes
import full_dbest_flights_routes_run as ops
import full_dbest_flights_routes_audit as audit

ROOT=routes.ROOT
LEGACY=(0,1,5,8)
LEGACY_PATH='output/full/dbest_flights/verification.json'
LEGACY_SHA='de73e1110d7299e8fdd092e0ab2e0502b8502da783a0e35602889b2e56159b30'
PINS={
 'code/full_dbest_flights_routes.py':'247fa00d77d47ecf94597f69b9b0b5f72f6c23e9caabc0f36f7701e93e4f531c',
 'code/full_dbest_flights_routes_audit.py':'497b51d93e423e047562053f24c121ae79a41bb7993a436e930365c40f325dca',
 'code/full_dbest_flights_routes_run.py':'881ccff6f32fb55a5674fad58ba21e4699576601d3397a996094717781afec73',
 'code/tests/test_full_dbest_flights_routes.py':'2276d068bb4c88df5d7a1fb57c1c638264036cf6e3327d8c397ea4c26cddb297',
 'code/tests/test_full_dbest_flights_routes_audit.py':'83c1d06d8950f92bc3d1f30dd28144c583207aa4b078fe8efce06d854adc1004',
 'code/tests/test_full_dbest_flights_routes_run.py':'2b92ab1d86adbea5cefd56aac9bfcd7a89e045d9ef526549278876061fa4163f',
 'docs/FULL_DBEST_FLIGHTS_ROUTES.md':'67b6ef111f7ec30c82745dd107e0e3311bef90bcfe1a9b6228f0f8d3b583dd73'}
SOURCE_FILES=tuple(PINS)+('code/full_dbest_flights_routes_tables.py','code/tests/test_full_dbest_flights_routes_tables.py','docs/FULL_DBEST_FLIGHTS_ROUTES_TABLES.md')
STATES={'RETURNED','UNAVAILABLE_FIXED_SAMPLE','FIT_ERROR','NUMERICAL_BUDGET_UNSUPPORTED','NATIVE_ERROR','NATIVE_NULL','NATIVE_NONFINITE','NUMERICAL_VALIDATION_FAILED'}
require=routes.require
POLICY=dict(conditional_metric='FINITE_MATCHED_NONZERO_TRUTH_ONLY_WITH_EXPLICIT_COVERAGE',complete_metric='NULL_UNLESS_ALL_TRUTH_POINTS_FINITE_AND_NO_EXTRAS',
    missing_point_imputation=False,q7_official_truth_applied=True,q7_evaluation_scope='LOCAL_QUERY_AWARE_EXACT_YEAR_PREFILTER_VARIANT',q11_joint_ci=False,shared_method_ranking=False)


def record(path,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve()
    require(root in path.parents and path.is_file() and 0<path.stat().st_size<=16*1024**2,'Bounded nonempty project evidence required')
    return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=ops.digest(path))


def key(value):
    require(type(value) is list and len(value)<=1 and all(v is None or type(v) in (str,int) for v in value),'Exact scalar/one-column group key required')
    return tuple(None if v is None else str(v) for v in value)


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def derive(legacy,queries,truth):
    require(legacy.get('status')=='PASS_WITH_GAPS' and legacy.get('population_rows')==10**9 and legacy.get('retained_sample_rows')==9997912
        and legacy.get('unique_fit_rows')==20000 and legacy.get('native_method_calls_total_verified')==76
        and legacy.get('paper_DBEst_training_configuration_recovered') is False,'Original four-class1B evidence required')
    aliases=routes.validate_truth_identity(truth,population_rows=10**9)
    require(len(legacy['queries'])==12,'Complete original12-query report required')
    sql_identity={a['query_no']:a['alias'] for a in aliases}
    require([q.get('query_no') for q in queries]==[6,7,10,11] and all(type(q['query_no']) is int for q in queries),'Four exact new route identities required')
    new={q['query_no']:q for q in queries};component_rows=[];group_rows=[];summary=[];raw_results=[]
    for q,s in zip(queries,routes.route_specs()):
        require(all(q.get(k)==v for k,v in s.items()) and q.get('target_answers_used_for_training') is False,'Exact route/variant identity and no training answers required')
        seen=set();api_calls=0
        for g in q['groups']:
            k=key(g['key']);require(len(k)==1 and k not in seen,'Duplicate or wrong-width route group');seen.add(k)
            expected=s['components'];require(len(g['native_results'])==len(expected) and {r['component'] for r in g['native_results']}==set(expected),'Complete unique native components required')
            if q['query_no']==11:
                require(g.get('adapter',{}).get('interval') is None and g['ci_status']==g['adapter'].get('ci_status')=='UNSUPPORTED_NO_COVARIANCE_MODEL','Two SUM difference cannot invent a joint CI')
                children={r['component']:r for r in g['native_results']};combined=routes.combine_children(children['taxi_out'],children['taxi_in'])
                require(g['estimate']==combined['estimate'] and g['status']==combined['status'],'Two original SUM point difference differs')
            for r in g['native_results']:
                n=r['native'];meta=r['job']['population_metadata']
                require(type(r.get('query_no')) is int and r['query_no']==q['query_no'] and key(r['key'])==k and r['status'] in STATES
                    and type(r.get('fit_attempted')) is bool and type(n.get('api_calls')) is int and n['api_calls'] in (0,1)
                    and meta.get('target_answer_used') is False and finite(meta.get('Nhat')) and meta['Nhat']>=0 and type(meta.get('estimated')) is bool
                    and type(r['job'].get('fit_rows')) is int and r['job']['fit_rows']>=0,'Native component identity/counters or held-out label boundary differs')
                api_calls+=n['api_calls'];raw_results.append(r)
                component_rows.append(dict(query_no=q['query_no'],query=q['name'],scope=q['scope'],key_json=json.dumps(k,separators=(',',':')),component=r['component'],
                    status=r['status'],raw_native_estimate=r['estimate'] if finite(r['estimate']) else None,fit_attempted=r['fit_attempted'],native_calls=n['api_calls'],
                    fit_rows=r['job']['fit_rows'],metadata_Nhat=meta['Nhat'],metadata_estimated=meta['estimated'],target_answer_used=False,
                    ci_scope='NO_JOINT_CI' if q['query_no']==11 else 'NO_ORIGINAL_QUERY_CI'))
        require(type(q.get('original_api_calls')) is int and q['original_api_calls']==api_calls,'Actual native query counter differs')
    for i,(ref,old) in enumerate(zip(truth['queries'],legacy['queries'])):
        require(type(old.get('query_no')) is int and old['query_no']==i and old['name']==routes.QUERY_NAMES[i],'Exact original12 report no/name identity differs')
        require(old['status']==('SUPPORTED' if i in LEGACY else 'UNSUPPORTED') and (i in LEGACY or not old['predictions']),'Legacy support scope differs')
        exact={}
        for g in ref['groups']:
            k=key(g['key']);require(len(k)==(0 if i in (0,1) else 1) and k not in exact and type(g['numerator']) is int and type(g['denominator']) is int and g['denominator']>0,'Unique exact rational truth required')
            exact[k]=Fraction(g['numerator'],g['denominator'])
        supported=i in LEGACY or i in new;variant=i==7;points={}
        if i in LEGACY:
            for p in old['predictions']:
                k=key([] if i in (0,1) and p['group']=='all' else [p['group']]);require(k not in points,'Duplicate legacy prediction group')
                require(p.get('native',{}).get('integral_verified') is True,'Legacy native numerical validation required')
                points[k]=dict(estimate=p['estimate'],status='RETURNED',ci_status='UNSUPPORTED_ORIGINAL_DBEST_CI')
        elif i in new:
            points={key(g['key']):g for g in new[i]['groups']}
        rows=[]
        for k in sorted(set(exact)|set(points),key=repr):
            g=points.get(k);v=exact.get(k);value=None if g is None else g['estimate'];ok=g is not None and g['status'] in ('RETURNED','POINT_DIFFERENCE_RETURNED') and finite(value)
            invalid=g is not None and (g['status'] in ('NATIVE_ERROR','NATIVE_NONFINITE','NUMERICAL_VALIDATION_FAILED') or value is not None and not finite(value))
            state='UNSUPPORTED_QUERY' if not supported else 'MISSING_PREDICTION_GROUP' if g is None else 'EXTRA_PREDICTION_GROUP' if k not in exact else 'INVALID_POINT' if invalid else 'PRESENT_WITHOUT_USABLE_POINT' if not ok else 'MATCHED'
            error=abs(float(value)-float(v)) if supported and ok and v is not None else None
            row=dict(query_no=i,query=routes.QUERY_NAMES[i],scope=new[i]['scope'] if i in new else 'FROZEN_ORIGINAL_FOUR' if i in LEGACY else routes.support_table()[i]['status'],
                key_json=json.dumps(k,separators=(',',':')),status=state,model_status=None if g is None else g['status'],estimate=value if finite(value) else None,
                truth_numerator=None if v is None else str(v.numerator),truth_denominator=None if v is None else str(v.denominator),absolute_error=error,
                relative_error=error/abs(float(v)) if error is not None and v else None,zero_truth=v==0 if v is not None else False,
                ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL' if i==11 else 'UNSUPPORTED_ORIGINAL_QUERY_CI',scoring_allowed=supported,
                evaluation_sql_match=True,evaluation_sql_identity=sql_identity.get(i,'EXACT_LITERAL'),author_prefilter_config_match=False if variant else True if supported else None,
                finite_output_point=ok,finite_matched_point=ok and v is not None,invalid_point=invalid)
            rows.append(row);group_rows.append(row)
        errors=[r['relative_error'] for r in rows if r['relative_error'] is not None];coverage=sum(r['finite_matched_point'] for r in rows)
        extras=sum(r['status']=='EXTRA_PREDICTION_GROUP' for r in rows);complete=supported and coverage==len(exact) and extras==0
        summary.append(dict(query_no=i,query=routes.QUERY_NAMES[i],scope=new[i]['scope'] if i in new else 'FROZEN_ORIGINAL_FOUR' if i in LEGACY else routes.support_table()[i]['status'],
            scoring_allowed=supported,evaluation_sql_match=True,evaluation_sql_identity=sql_identity.get(i,'EXACT_LITERAL'),author_prefilter_config_match=False if variant else True if supported else None,
            public_prefilter_matches=False if variant else True if supported else None,truth_groups=len(exact),output_groups=len(points),finite_output_points=sum(r['finite_output_point'] for r in rows),finite_matched_groups=coverage,
            missing_groups=sum(r['status']=='MISSING_PREDICTION_GROUP' for r in rows),unavailable_groups=sum(r['status']=='PRESENT_WITHOUT_USABLE_POINT' for r in rows),invalid_points=sum(r['invalid_point'] for r in rows),
            extra_groups=extras,zero_truth_groups=sum(r['zero_truth'] for r in rows),matched_conditional_mean_relative_error=sum(errors)/len(errors) if errors else None,
            all_nonzero_truth_mean_relative_error=sum(errors)/len(errors) if complete and errors else None,original_calls_this_route=0 if i not in new else new[i]['original_api_calls']))
    counters=dict(native_calls=sum(r['native']['api_calls'] for r in raw_results),fit_attempts=sum(r['fit_attempted'] for r in raw_results),
        empty_fixed_sample_components=sum(r['status']=='UNAVAILABLE_FIXED_SAMPLE' for r in raw_results),fit_errors=sum(r['status']=='FIT_ERROR' for r in raw_results),
        numerical_budget_unsupported=sum(r['status']=='NUMERICAL_BUDGET_UNSUPPORTED' for r in raw_results),numerical_validation_failures=sum(r['status']=='NUMERICAL_VALIDATION_FAILED' for r in raw_results),
        native_errors=sum(r['status']=='NATIVE_ERROR' for r in raw_results),native_nulls=sum(r['status']=='NATIVE_NULL' for r in raw_results),native_nonfinite=sum(r['status']=='NATIVE_NONFINITE' for r in raw_results),
        coverage_gaps=sum(r['status']!='RETURNED' for r in raw_results),native_components=len(raw_results))
    return dict(queries=summary,groups=group_rows,components=component_rows,counters=counters,truth_identity_aliases=aliases)


def csv_bytes(rows):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);return s.getvalue().encode('utf-8')


def sources(root):
    for m,n in ((routes,'code/full_dbest_flights_routes.py'),(ops,'code/full_dbest_flights_routes_run.py'),(audit,'code/full_dbest_flights_routes_audit.py')):
        require(Path(m.__file__).resolve()==root/n,'Actually loaded route source differs')
    require(Path(__file__).resolve()==root/'code/full_dbest_flights_routes_tables.py','Actually loaded table consumer differs')
    for n,sha in PINS.items():require(ops.digest(root/n)==sha,'Frozen scientific route source changed')
    return {n:record(root/n,root) for n in SOURCE_FILES}


def build(home,root=ROOT):
    root=Path(root).resolve();home=Path(home).resolve();require((root/'output/full/dbest_flights_routes/runs') in home.parents,'Only own completed route namespace allowed')
    inputs=sources(root);proof=audit.verify(home)  # Includes the old76-call audit once; no second parent proof here.
    require(proof.get('status')=='PASS_READONLY_ORIGINAL_DBEST_ROUTE_EVIDENCE_WITH_GAPS' and proof.get('kind')=='ROUTES' and proof.get('population')=='FORMAL_1B'
        and all(proof.get(k) is False for k in ('author_training_configuration_recovered','full_paper_reproduction_complete','files_written','models_loaded','scientific_calls_executed','processes_executed','database_connected')),
        'Complete read-only FORMAL_1B routes required; a200K golden is not a1B comparison')
    for n,k in (('final.json','final'),('plan.json','plan')):require(record(home/n,root)==proof[k],'Accepted final/plan alias changed')
    final=ops.strict_read(home/'final.json');plan=ops.strict_read(home/'plan.json')
    require(ops.strict_read(home/'final.seal.json')==dict(sha256=proof['final']['sha256']) and ops.strict_read(home/'lifecycle.json')==dict(status='PASS',final_sha256=proof['final']['sha256'])
        and bool(final.get('files')) and final['binding_sha256']==plan['binding_sha256'],'Accepted final/PASS/binding incomplete')
    for n in ('plan.json','queries.json','worker.json','support.json','evaluation.json'):
        r=record(home/n,root);require(final['files'].get(n)==r,'Consumed scientific artifact differs from accepted seal');inputs[r['path']]=r
    for n in ('final.json','final.seal.json','lifecycle.json'):r=record(home/n,root);inputs[r['path']]=r
    require(plan['kind']=='ROUTES' and plan['population']['name']=='FORMAL_1B' and plan['population']['population_rows']==10**9 and plan['population']['retained_rows']==9997912
        and plan['population']['fit_rows']==20000 and plan.get('original_four_classes_reexecuted') is False,'Exact formal population/information budget required')
    require(ops.strict_read(home/'support.json')==routes.support_table(),'Frozen12-query support states changed')
    label=plan['population']['truth']['path'];require(label=='output/full/flights/flights-1b/ground_truth.json','Only separately sealed formal Flights labels may be scored')
    lr=record(root/label,root);require(plan['population_inputs'].get(label)==lr,'Held-out full truth differs from reviewed plan');inputs[label]=lr
    old=record(root/LEGACY_PATH,root);source=plan['source']
    require(old['sha256']==LEGACY_SHA==source['source_report_sha256']==source['files_sha256'].get(LEGACY_PATH)
        and proof['source_complete_inventory_sha256']==source['complete_inventory_sha256'],'Original76-call report not in the same complete accepted closure');inputs[LEGACY_PATH]=old
    summary=derive(ops.strict_read(root/LEGACY_PATH),ops.strict_read(home/'queries.json'),ops.strict_read(root/label));c=summary['counters'];worker=ops.strict_read(home/'worker.json')
    for field,wanted in (('native_calls',c['native_calls']),('native_fit_errors',c['fit_errors']),('coverage_gaps',c['coverage_gaps']),('numerical_validation_failures',c['numerical_validation_failures'])):
        require(type(proof.get(field)) is int and proof[field]==wanted,'Accepted native/gap counter differs')
    require(type(worker['new_original_api_calls']) is type(worker['new_fit_attempts']) is int and worker['new_original_api_calls']==c['native_calls'] and worker['new_fit_attempts']==c['fit_attempts'] and worker['original_prior_classes_reexecuted'] is False
        and worker['new_query_evaluation_only_after_raw_predictions'] is True,'Actual worker accounting/training-label boundary differs')
    identity=dict(inputs=inputs,acceptance=proof,policy=POLICY,truth_identity_aliases=summary['truth_identity_aliases'],scope='LOCAL_FORMAL_DBEST_1D_ROUTES_WITH_GAPS');binding=routes.value_hash(identity)
    out=root/'output/full/figures'/('dbest_routes_'+binding[:20]);require(out.resolve()==out and root in out.parents,'Literal project derived namespace required')
    text='# Partial original DBEst Flights coverage\n\nHistorical four classes:76 native calls; new1D routes:{native_calls} calls/{fit_attempts} fit attempts. Export executes0 calls.\n\n'.format(**c)
    text+='New native components:{native_components}; empty fixed-subset:{empty_fixed_sample_components}; fit errors:{fit_errors}; numerical-budget unsupported:{numerical_budget_unsupported}; numerical-validation failures:{numerical_validation_failures}; native errors/NULL/nonfinite:{native_errors}/{native_nulls}/{native_nonfinite}.\n\n'.format(**c)
    text+='F3.3 has matching evaluation SQL and is scored against its exact full-population truth, separately as a **LOCAL F3.3 variant** with a query-aware exact-year fitting prefilter. Its author prefilter configuration does not match; this is not recovered author configuration or a shared ranking. F5.2 is two SUM points with **no joint CI**. Empty fixed-subset, native unsupported/fit errors and missing groups remain gaps. Matched means are conditional; all-truth means stay null without complete finite coverage.\n\n'
    text+='Metadata budget: old declared full-stream/count metadata or estimated state counts; new complete9,997,912 retained-category/non-NULL count/p metadata, with only20,000 unique fitting rows. Plug-in count uncertainty is not a query CI. Aggregate target answers are held out until evaluation. Author training configuration/full-paper completion remain false.\n\n'
    text+='Truth SQL identity: the pinned V4 helper permits only the explicit source-bound query3 single-space literal alias for1B. Applied aliases: '+json.dumps(summary['truth_identity_aliases'],sort_keys=True)+'. No general SQL normalization or label rewriting occurs.\n\n'
    text+='| Query | Scope | Finite matched / truth | All-nonzero-truth mean relative error |\n| --- | --- | --- | --- |\n'
    for q in summary['queries']:
        if q['query_no']!=7:text+='| {query} | {scope} | {finite_matched_groups}/{truth_groups} | {all_nonzero_truth_mean_relative_error} |\n'.format(**q)
    text+='\nLOCAL F3.3 variant (evaluation SQL matches; author prefilter configuration does not match):\n\n'
    text+='| Query | Scope | Finite matched / truth | All-nonzero-truth mean relative error |\n| --- | --- | --- | --- |\n'
    text+='| {query} | {scope} | {finite_matched_groups}/{truth_groups} | {all_nonzero_truth_mean_relative_error} |\n'.format(**summary['queries'][7])
    payload={'query_summary.csv':csv_bytes(summary['queries']),'group_results.csv':csv_bytes(summary['groups']),'native_components.csv':csv_bytes(summary['components']),'RESULTS.md':text.encode('utf-8')}
    paths=[os.path.normcase(str((root/n).resolve())) for n in inputs];require(len(paths)==len(set(paths)),'Physically unique consumed inputs required')
    for n,r in inputs.items():require(record(root/n,root)==r,'Source/label/accepted evidence changed during derivation')
    if out.exists():require({p.name for p in out.iterdir()}==set(payload)|{'manifest.json'},'Exact prior derived output set required')
    else:
        out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(exist_ok=False)
        for n,data in payload.items():(out/n).write_bytes(data)
    for n,data in payload.items():require((out/n).is_file() and (out/n).read_bytes()==data,'Prior derived bytes differ; never overwrite')
    manifest=dict(status='PASS_VERIFIED_FORMAL_DBEST_ROUTES_DERIVED_TABLES_WITH_GAPS',binding=binding,identity=identity,summary=dict(queries=summary['queries'],counters=c),
        historical_native_calls=76,new_route_native_calls=c['native_calls'],native_calls_during_export=0,author_training_configuration_recovered=False,full_paper_reproduction_complete=False,
        files={n:record(out/n,root) for n in payload})
    manifest['self_sha256']=routes.value_hash(manifest)
    if (out/'manifest.json').exists():require(ops.strict_read(out/'manifest.json')==manifest,'Prior derived manifest differs')
    else:ops.atomic(out/'manifest.json',manifest)
    return dict(status=manifest['status'],directory=out.relative_to(root).as_posix(),binding=binding,manifest=record(out/'manifest.json',root))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',required=True);a=p.parse_args();print(build(a.home))
