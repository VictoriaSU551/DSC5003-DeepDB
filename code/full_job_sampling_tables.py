"""Standalone LOCAL SRS/IBJS tables; held-out labels are evaluation only."""
import sys
sys.dont_write_bytecode=True
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import re

QUERY_FILE='code/benchmarks/job-light/sql/job_light_queries.sql'
QUERY_SHA='e61da91710ce62d3669be70a8ded2499c6de1d759fcfac9a954b939465e76fdb'
LABEL_FILES={
 'official':('code/benchmarks/job-light/sql/job_light_true_cardinalities.csv','87e66a3a5977d38a5e32db43451f7213776d1046f57ea2f85da854c04ba79acc'),
 'confirmed':('output/full/results/postgres_job_light.csv','c65ae65c781936be7da0be91185299d36d763082b5b5de328bc25dedb2c4dc06'),
 'confirmation':('output/full/results/postgres_job_light_verification.json','614426bd8d3a1d837e5db78ef8d1ff7737ff33f9772fcbc240af9b82b931bdaf')}
SRS_PINS={
 'code/full_job_sampling.py':'d656de7c010daf636797b2876bcc8599a25f8be6f341b52e210cb4157c30d1a9',
 'code/full_job_sampling_run.py':'2e7e7a51bec679e718582391ea64142b5a0f05127b6dbb50d6e019e4ad84fec1',
 'code/full_job_sampling_audit.py':'5ea0bbb849db80dd78f241ac78b1e793ac2c80293519ce6c465f121d27b3bd3a',
 'code/tests/test_full_job_sampling.py':'0446ddc2424a706616d396e4bba8266456a9ff376a2c9c4bc6f4676aaca28446',
 'code/tests/test_full_job_sampling_run.py':'aedd9732f051878a9b4ba48acfdf4301cf405d6eba922ddb860a2dce728345e0',
 'code/tests/test_full_job_sampling_audit.py':'f731fb4330e4878c19a0e053b468e24e5d17eacc38200fb5574fe6a5facfa600',
 'docs/FULL_JOB_SAMPLING_PROTOCOL.md':'b67bd20e40ae92d7a2c4d6f6227b49de1a102908dcd61d95411f871dc547dae4',
 'code/full_scalar_oracle.py':'a804301149e370eabf1055cdcb94d8157502032ab37a81e33a1b2396225964df',
 'code/full_scalar_oracle_run.py':'d5d31f3460d84942a2f22a0874f0c73bfcbbecb45a048a2ab78be76496ee9e26',
 'code/full_scalar_oracle_audit.py':'15912c8e98a620553bc861e3b6dbe1821227f6cf8779bf1ab5eba6bb225f0307',
 'docs/FULL_SCALAR_ORACLE_PROTOCOL.md':'1f02d7b591197f8cf4bd318199acb0173741887f149c4f5c80c02647058797fa'}
IBJS_PINS={
 'code/full_job_sampling_ibjs.py':'9a23d974dba56bb055b8abb2def1a10ac06efa1c529f4e2e59e943194f576a93',
 'code/tests/test_full_job_sampling_ibjs.py':'78a2c9c1eb3501221daff90c0a4b618bf94c8b80be5a9d68f173f76ab6932e03',
 'docs/FULL_JOB_IBJS_PROTOCOL.md':'d5c9e34c2465406dd9a85f56c9a69d999cbf4c667ec351379a3f39e609040aeb',
 'code/full_job_sampling_ibjs_run.py':'01aa599026218a0132f0b917fa4c3fba507af9129925a531156761a57a06edb2',
 'code/full_job_sampling_ibjs_audit.py':'e4b5330bdd381e121d3d20d16deab565c88e5ebd53d244bfc9ee03ee62edfe1b',
 'code/tests/test_full_job_sampling_ibjs_run.py':'7a1b5822c640c420015968449a2e12b3554f28ef5d08c425a05983e06bd50e65',
 'code/tests/test_full_job_sampling_ibjs_audit.py':'3916ab821e40e096bc52da6778ec286a9cb5466a8899df1003d96ca125689b15',
 'docs/FULL_JOB_IBJS_RUNTIME.md':'01d1fa811dbb0d4ff0cc63551025281d0bbcaee87eadb09a6f1d13276d07dcc9'}
OWN=('code/full_job_sampling_tables.py','code/tests/test_full_job_sampling_tables.py','docs/FULL_JOB_SAMPLING_TABLES.md')

ROOT=Path(__file__).resolve().parents[1]
INFINITY='Infinity'
METHODS={
 'SRS':dict(method='LOCAL_JOB70_SRS_WOR_N1000',module='full_job_sampling_audit',base='output/full/sampling/job70',
    complete={'COMPLETE','COMPLETE_ZERO'},failure={'QUERY_WALL_BUDGET','ID_ATTEMPT_BUDGET','SQL_ROUNDTRIP_BUDGET','QUERY_ERROR','STATEMENT_TIMEOUT'},common_sql=65),
 'IBJS':dict(method='LOCAL_JOB70_IBJS_SQL_N1000_B100K',module='full_job_sampling_ibjs_audit',base='output/full/sampling/job70_ibjs',
    complete={'COMPLETE','ZERO_SAMPLE','STOP_AFTER_COMPLETE'},failure={'QUERY_WALL_BUDGET','ID_ATTEMPT_BUDGET','SQL_ROUNDTRIP_BUDGET','QUERY_ERROR','STATEMENT_TIMEOUT','LOOKUP_BUDGET_NULL'},common_sql=67)}
TABLES={'title','movie_info_idx','movie_info','cast_info','movie_keyword','movie_companies'}
POLICY=dict(raw_predictions_modified=False,positive_truth_zero='Infinity',unfinished='NULL_NOT_DROPPED',
    whole70='ONLY_IF_ALL70_COMPLETED_INCLUDING_INFINITY',quantiles='LINEAR_EXTENDED_REAL;EXACT_ENDPOINT_BEFORE_INTERPOLATION;POSITIVE_WEIGHT_INFINITY_IS_INFINITY',
    finite_summary='CONDITIONAL_WITH_EXPLICIT_COUNT',shared_author_ranking=False,scalar_floor1_policy_applied=False)


def require(ok,message):
    if not ok:raise ValueError(message)


def object_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def nonnegative(value):
    require(type(value) in (int,float) and math.isfinite(value) and value>=0,'Finite nonnegative cost required');return value


def integer(value):
    require(type(value) is int and value>=0,'Nonnegative integer cost required');return value


def integer_text(value,positive=False):
    require(type(value) is str and re.fullmatch(r'0|[1-9][0-9]*',value) is not None,'Canonical nonnegative integer text required')
    n=int(value);require(not positive or n>0,'Positive truth/denominator required');return n


def score_rows(method,sqls,predictions,official,confirmed):
    require(method in METHODS,'Known independently selected LOCAL method required');spec=METHODS[method]
    require(len(sqls)==len(predictions)==len(official)==len(confirmed)==70,'Exactly70 estimates and both label sets required')
    rows=[]
    for i,(sql,p,o,g) in enumerate(zip(sqls,predictions,official,confirmed)):
        require(type(sql) is str and type(p.get('query_no')) is int and p['query_no']==i and p.get('sql')==o.get('query')==g.get('query')==sql
            and o.get('query_no')==g.get('query_no')==str(i),'Exact70 ordered SQL/number/label identities required')
        truth=integer_text(o['cardinality_true'],True);require(integer_text(g['cardinality_true'],True)==truth,'Independent positive truth differs')
        state=p.get('status');require(state in spec['complete']|spec['failure'],'Unknown terminal sampling status')
        nonnegative(p.get('wall_seconds'));integer(p.get('sql_roundtrips'));attempts=p.get('id_attempts')
        require(type(attempts) is dict and set(attempts)<=TABLES,'Complete registered ID-attempt costs required')
        for n in attempts.values():integer(n)
        logical=integer(p.get('charged_logical_lookups')) if method=='IBJS' else None
        raw=p.get('raw_prediction');done=state in spec['complete'];point=None;error=None
        if done:
            require(type(raw) is dict and set(raw)=={'numerator','denominator'},'Completed raw Fraction required')
            point=Fraction(integer_text(raw['numerator']),integer_text(raw['denominator'],True))
            require(raw==dict(numerator=str(point.numerator),denominator=str(point.denominator)),'Raw Fraction must remain canonical and unchanged')
            error=INFINITY if point==0 else str(max(point/truth,Fraction(truth)/point))
        else:require(raw is None,'Unfinished estimate must remain null')
        rows.append(dict(method=spec['method'],query_no=i,sql=sql,status=state,truth=truth,
            raw_numerator=None if raw is None else raw['numerator'],raw_denominator=None if raw is None else raw['denominator'],
            estimate_is_zero=point==0 if done else False,q_error=error,
            metric_status='UNFINISHED' if not done else 'POSITIVE_TRUTH_ZERO_INFINITY' if point==0 else 'FINITE',
            wall_seconds=p['wall_seconds'],sql_roundtrips=p['sql_roundtrips'],id_attempts_json=json.dumps(attempts,sort_keys=True,separators=(',',':')),
            id_attempts_total=sum(attempts.values()),charged_logical_lookups=logical,physical_rows_scanned=None,physical_rows_scanned_unknown=True,
            n=1000,lookup_budget=100000 if method=='IBJS' else None,fallback_scope='LOCAL_IBJS_ADAPTIVE_STOP_AFTER_COMPLETE' if method=='IBJS' else 'NOT_APPLICABLE',
            author_configuration_identified=False,shared_author_ranking=False,evaluation_policy='RAW_ZERO_TO_INFINITY_NO_FLOOR'))
    return rows


def quantile(values,p):
    require(type(p) is Fraction and 0<=p<=1 and bool(values),'Nonempty extended-real sample and exact probability required')
    require(all(type(v) is Fraction and v>=1 or v==INFINITY for v in values),'Positive finite or explicit infinite q-errors required')
    values=sorted(values,key=lambda v:(1,Fraction(0)) if v==INFINITY else (0,v));position=(len(values)-1)*p
    lo=position.numerator//position.denominator;weight=position-lo
    if not weight:value=values[lo]
    else:
        left,right=values[lo],values[lo+1]
        value=INFINITY if left==INFINITY or right==INFINITY else left+weight*(right-left)
    return dict(status='INFINITE' if value==INFINITY else 'FINITE',value=str(value))


def distribution(values):
    return dict(queries=len(values),median=quantile(values,Fraction(1,2)),p90=quantile(values,Fraction(9,10)),
        p95=quantile(values,Fraction(19,20)),max=quantile(values,Fraction(1)))


def summarize(rows):
    require(len(rows)==70 and [r['query_no'] for r in rows]==list(range(70)),'Whole70 row denominator required')
    complete=[r for r in rows if r['metric_status']!='UNFINISHED'];values=[INFINITY if r['q_error']==INFINITY else Fraction(r['q_error']) for r in complete]
    finite=[v for v in values if v!=INFINITY]
    return dict(queries=70,completed=len(complete),unfinished=70-len(complete),raw_zero=sum(r['estimate_is_zero'] for r in rows),
        infinite=sum(v==INFINITY for v in values),status_counts=dict(sorted(Counter(r['status'] for r in rows).items())),
        whole70=distribution(values) if len(complete)==70 else None,conditional_finite=distribution(finite) if finite else dict(queries=0,median=None,p90=None,p95=None,max=None))


def read(path):
    def unique(items):
        value={}
        for key,item in items:require(key not in value,'Duplicate JSON key');value[key]=item
        return value
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def artifact(path,root):
    path=Path(path).absolute();root=Path(root).resolve()
    require(path==path.resolve() and root in path.parents and path.is_file() and path.stat().st_size>0,'Missing/aliased/outside physical input')
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=h.hexdigest())


def sources(root,methods):
    pins=dict(SRS_PINS)
    if 'IBJS' in methods:pins.update(IBJS_PINS)
    records={name:artifact(Path(root)/name,root) for name in sorted(set(pins)|set(OWN))}
    require(all(records[n]['sha256']==sha for n,sha in pins.items()),'Frozen scientific source pin differs')
    require(Path(__file__).resolve()==(Path(root)/OWN[0]).resolve(),'Loaded consumer source is not the declared physical file')
    return records


def load_auditor(method,root):
    module=importlib.import_module(METHODS[method]['module'])
    require(Path(module.__file__).resolve()==(Path(root)/'code'/(METHODS[method]['module']+'.py')).resolve(),'Shadow auditor import')
    if method=='SRS':require(Path(module.core.__file__).resolve()==(Path(root)/'code/full_job_sampling.py').resolve(),'Shadow SRS core import')
    return module


def expected_scope(method):
    if method=='SRS':return dict(method=METHODS[method]['method'],author_method_configuration_identified=False,author_sampling_reproduction_complete=False,
        full_paper_reproduction_complete=False,ibjs_implemented=False,truth_used_for_prediction=False,original_csv_current_database_full_value_identity_claimed=False)
    return dict(method=METHODS[method]['method'],author_reproduction_complete=False,full_paper_reproduction_complete=False,
        author_configuration_identified=False,adaptive_path_unbiasedness_claimed=False,live_driver_implemented=True,truth_or_scalar_selectivities_used=False)


def expected_config(method):
    if method=='IBJS':return dict(n=1000,lookup_budget=100000,seed=1)
    return dict(samples_per_table=1000,seed=1,batch_size=128,max_id_attempts_per_table=100000,max_sql_roundtrips=2000,max_query_seconds=30.,statement_timeout_ms=5000)


def required_files(method):
    return ['plan.json','approval.json','collection.json','predictions.json','verification.json','lifecycle.json','execution.json']+(
        ['monitor.json'] if method=='IBJS' else [])+[n for i in range(70) for n in ('queries/query_%02d.json'%i,'queries/query_%02d.seal.json'%i)]


def label_inputs(root):
    records={QUERY_FILE:artifact(root/QUERY_FILE,root)}
    require(records[QUERY_FILE]['sha256']==QUERY_SHA,'Exact70 workload source differs')
    sqls=[s.strip() for s in (root/QUERY_FILE).read_text(encoding='utf-8').splitlines() if s.strip()]
    require(len(sqls)==70,'Exactly70 workload SQL required');labels={}
    for key,(name,sha) in LABEL_FILES.items():
        records[name]=artifact(root/name,root);require(records[name]['sha256']==sha,'Held-out label/confirmation pin differs')
        if key!='confirmation':
            with (root/name).open(encoding='utf-8',newline='') as f:
                reader=csv.DictReader(f);require(reader.fieldnames and len(set(reader.fieldnames))==len(reader.fieldnames),'Duplicate CSV columns')
                labels[key]=list(reader)
            require(all(None not in r and all(v is not None for v in r.values()) for r in labels[key]),'Malformed label CSV')
    confirmation=read(root/LABEL_FILES['confirmation'][0])
    require(confirmation['status']=='PASS' and type(confirmation['queries']) is int and confirmation['queries']==70
        and confirmation['all_official_truths_independently_matched'] is True and confirmation['server_version']=='11.5'
        and confirmation['result_sha256']==LABEL_FILES['confirmed'][1],'Independent PostgreSQL confirmation differs')
    return sqls,labels,records


def accept(method,home,root,sqls,labels):
    """Exactly one fresh public verifier; no caller-supplied proof/cache bypass."""
    home=Path(home).absolute();require(home==home.resolve(),'Aliased run path')
    proof=load_auditor(method,root).verify(home,root=root)
    required=required_files(method);allnames=set(required)|{'final_seal.json'}
    require({p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}==allnames,'Exact physical receipt set required')
    records={name:artifact(home/name,root) for name in required};seal_record=artifact(home/'final_seal.json',root)
    seal=read(home/'final_seal.json');require(set(seal)=={'schema','binding','files','self_sha256'}
        and seal['schema']=='job70-'+method.lower()+'-final-v1' and seal['self_sha256']==object_hash({k:v for k,v in seal.items() if k!='self_sha256'})
        and seal['files']==records,'Incomplete or changed final physical seal')
    actual=proof['artifacts'];require(type(actual) is list and len(actual)==len(records) and all(type(d) is dict and set(d)=={'path','bytes','sha256'} for d in actual)
        and len({d['path'] for d in actual})==len(records) and {d['path']:d for d in actual}=={d['path']:d for d in records.values()},'Auditor artifact closure must be exact, complete and unique')
    require(proof['verification_artifact']==records['verification.json'] and proof['final_seal']==seal_record,'Acceptance aliases differ')
    plan=read(home/'plan.json');verification=read(home/'verification.json');predictions=read(home/'predictions.json');execution=read(home/'execution.json')
    binding=plan['binding'];require(binding==object_hash({k:v for k,v in plan.items() if k!='binding'}) and binding==seal['binding']
        and home==root/METHODS[method]['base']/'runs'/binding[:20],'Exact plan/binding/namespace required')
    scope=expected_scope(method);require(plan['scope']==predictions['scope']==verification['scope']==scope and plan['config']==expected_config(method),'LOCAL method/config scope differs')
    require([dict(query_no=i,sql=s) for i,s in enumerate(sqls)]==[dict(query_no=q['query_no'],sql=q['sql']) for q in plan['contract']['queries']],'Plan whole70 SQL identities differ')
    require(proof['verification']==verification and proof['predictions']==predictions and proof['controller_timing']==execution and proof['dependencies']==plan['dependencies'],'Accepted bodies differ from current files')
    require(verification['binding']==predictions['binding']==execution['binding']==binding,'Accepted bindings differ')
    life=read(home/'lifecycle.json');require(life['status']=='PASS' and life['binding']==binding and life['verification_sha256']==records['verification.json']['sha256'],'Only published PASS may be consumed')
    rows=score_rows(method,sqls,predictions['queries'],labels['official'],labels['confirmed']);summary=summarize(rows)
    require(proof['status']=='PASS_READ_ONLY_LOCAL_JOB70_'+method+('_WITH_GAPS' if summary['unfinished'] else '') and verification['queries']==70
        and verification['completed_queries']==summary['completed'] and verification['incomplete_queries']==summary['unfinished'] and verification['raw_zero_queries']==summary['raw_zero'],'Coverage claims differ from complete70 rows')
    for row,pred in zip(rows,predictions['queries']):
        name='queries/query_%02d.json'%row['query_no'];q=read(home/name);qs=read((home/name).with_suffix('.seal.json'))
        require(qs==dict(binding=binding,query_no=row['query_no'],artifact=records[name]) and all(q[k]==v for k,v in pred.items()),'Raw query/accepted prediction/seal differs')
        ops=q['operations'];require(type(ops) is list and len(ops)==row['sql_roundtrips'],'Complete SQL cost trace required')
        compact=[]
        for op in ops:
            require(type(op['kind']) is str and op['status'] in {'PASS','ERROR'} and type(op['cleanup']) is bool,'Malformed operation cost')
            compact.append({k:op[k] for k in ('kind','seconds','status','cleanup')});nonnegative(op['seconds'])
        require(sum(o['seconds'] for o in ops)<=row['wall_seconds']+1e-5,'SQL duration exceeds charged query wall')
        row.update(operation_costs_json=json.dumps(compact,sort_keys=True,separators=(',',':')),base_lookup_sql_calls=sum(o['kind'].startswith('base_lookup/') for o in ops),
            fanout_count_sql_calls=sum(o['kind'].startswith('ibjs_count/') for o in ops),kth_rank_sql_calls=sum(o['kind'].startswith('ibjs_kth/') for o in ops),cleanup_sql_calls=sum(o['cleanup'] for o in ops))
    costs=cost_ledger(method,rows,verification,read(home/'collection.json'),execution)
    inputs={d['path']:d for d in list(records.values())+[seal_record]}
    return rows,dict(scope=scope,config=plan['config'],summary=summary,costs=costs,verification=records['verification.json'],final_seal=seal_record,
        acceptance_sha256=object_hash(proof),source_boundary=verification.get('source_boundary'),current_database_values_reverified_by_offline_audit=False),inputs


def cost_ledger(method,rows,v,c,e):
    common=METHODS[method]['common_sql'];setup=17 if method=='SRS' else 19
    breakdown={('recorded_setup_identity_metadata_reset' if method=='SRS' else 'recorded_setup_identity_metadata_indexes_reset'):setup,'schema_checks':36,'streaming_copy':12}
    require(v['common_sql_roundtrips']==common and v['common_sql_roundtrips_breakdown']==breakdown and len(c['common_operations'])==setup,'Common65/67 SQL ledger differs')
    for op in c['common_operations']:nonnegative(op['seconds'])
    timings=c['timings'];require(set(timings)=={'before_projection_seconds','live_population_metadata_seconds','all_online_queries_and_leaf_checkpoint_seconds','after_projection_seconds'} and v['common_preparation_timings']==timings,'Shared preparation categories incomplete')
    for val in timings.values():nonnegative(val)
    require(sum(timings.values())<=nonnegative(c['seconds'])+1e-5,'Uncharged collection costs')
    wall=sum(r['wall_seconds'] for r in rows);sql=sum(r['sql_roundtrips'] for r in rows)
    require(v['online_query_sql_roundtrips']==sql and abs(v['all_online_query_wall_seconds']-wall)<1e-8 and wall<=timings['all_online_queries_and_leaf_checkpoint_seconds']+1e-5,'Online work omitted')
    copybytes=0
    for side in ('before','after'):
        require(set(c[side])==TABLES,'Two complete six-table COPY passes required')
        for item in c[side].values():copybytes+=integer(item['binary_copy']['bytes'])
    fields=('admission_physical_validation_seconds','collection_and_checkpoint_seconds','fresh_postflight_physical_validation_seconds','offline_math_prepublication_validation_seconds','measured_client_wall_seconds_before_final_records')
    for field in fields:nonnegative(e[field])
    require(sum(e[k] for k in fields[:-1])<=e[fields[-1]]+1e-5 and e['collection_and_checkpoint_seconds']>=c['seconds']
        and e['final_record_and_seal_io_in_external_command_wall_only'] is e['root_external_command_wall_required_for_end_to_end_latency'] is True,'Full controller timing ledger required')
    logical=sum(r['charged_logical_lookups'] for r in rows) if method=='IBJS' else None
    if method=='IBJS':require(v['charged_logical_lookups']==logical,'Logical lookup ledger differs')
    return dict(method=METHODS[method]['method'],common_sql_roundtrips=common,setup_identity_metadata_reset_sql=setup,schema_sql=36,binary_copy_calls=12,binary_copy_bytes_both_passes=copybytes,
        common_recorded_sql_seconds=sum(op['seconds'] for op in c['common_operations']),collection_seconds=c['seconds'],**timings,
        online_query_wall_seconds=wall,online_query_sql_roundtrips=sql,id_attempts_total=sum(r['id_attempts_total'] for r in rows),charged_logical_lookups=logical,
        physical_rows_scanned=None,physical_rows_scanned_unknown=True,external_command_wall_seconds=None,external_command_wall_not_supplied=True,
        end_to_end_latency_claimed=False,**{k:e[k] for k in fields})


def json_bytes(value):return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')


def csv_bytes(rows):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows);return stream.getvalue().encode('utf-8')


def unchanged(records,root):
    require(all(artifact(root/name,root)==r for name,r in records.items()),'Inputs changed during derivation')


def markdown(methods):
    lines=['# LOCAL JOB70 sampling variants','', 'Separate LOCAL methods; author configuration is unidentified. These are not the author Table1 or a shared ranking.',
        '', 'Raw Fraction predictions remain unchanged. Positive-truth zero has q-error Infinity; unfinished queries remain null. Whole70 quantiles exist only when all70 complete. No floor1 is applied.',
        '', 'Physical scanned rows are unknown. Metadata, two full projection COPY passes, common SQL, online work and controller validation are charged separately. External command wall was not supplied; recorded client wall is not end-to-end latency.']
    for method,data in methods.items():
        s=data['summary'];lines+=['','## '+method,'', 'Scope: `'+METHODS[method]['method']+'`; n=1000'+('; b=100000, adaptive stop-after-complete is a LOCAL fallback, not an identified author configuration.' if method=='IBJS' else '.'),
            '', 'Completed '+str(s['completed'])+'/70; unfinished '+str(s['unfinished'])+'; raw zero '+str(s['raw_zero'])+'; infinite q-errors '+str(s['infinite'])+'.',
            '', 'Whole70: `'+json.dumps(s['whole70'],sort_keys=True)+'`', '', 'Conditional finite-only (explicit denominator): `'+json.dumps(s['conditional_finite'],sort_keys=True)+'`',
            '', 'Status counts: `'+json.dumps(s['status_counts'],sort_keys=True)+'`', '', 'Costs: `'+json.dumps(data['costs'],sort_keys=True)+'`']
    return ('\n'.join(lines)+'\n').encode('utf-8')


def build(directories,root=ROOT):
    """Fresh offline acceptance only; creates a separate deterministic export."""
    require(type(directories) is dict and bool(directories) and set(directories)<=set(METHODS),'Select SRS and/or IBJS explicitly')
    root=Path(root).resolve();selected=[k for k in METHODS if k in directories];source_records=sources(root,selected)
    sqls,labels,label_records=label_inputs(root);inputs=dict(source_records,**label_records);allrows=[];methods={}
    for method in selected:
        rows,details,records=accept(method,directories[method],root,sqls,labels);allrows.extend(rows);methods[method]=details
        require(not set(inputs)&set(records),'Duplicate cross-method physical inputs');inputs.update(records)
    unchanged(inputs,root)
    body=dict(schema='local-job70-sampling-tables-v1',policy=POLICY,methods=methods,inputs=inputs)
    binding=object_hash(body);parent=root/'output/full/figures';directory=parent/('sampling_'+binding[:20])
    require(directory.resolve()==directory and root in directory.parents,'Derived output path is aliased/outside workspace')
    payloads={'predictions_scored.csv':csv_bytes(allrows),'method_costs.csv':csv_bytes([methods[m]['costs'] for m in selected]),'RESULTS.md':markdown(methods)}
    manifest=dict(body,binding=binding,files={n:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for n,data in payloads.items()})
    manifest['self_sha256']=object_hash(manifest);payloads['manifest.json']=json_bytes(manifest)
    unchanged(inputs,root)
    if directory.exists():
        require(directory.is_dir() and {p.name for p in directory.iterdir()}==set(payloads),'Existing export has extra/missing entries')
        require(all(p.is_file() and p.resolve()==p and p.read_bytes()==payloads[p.name] for p in directory.iterdir()),'Existing export differs; refusing repair or overwrite')
    else:
        parent.mkdir(parents=True,exist_ok=True);directory.mkdir(exist_ok=False)
        for name,data in payloads.items():
            with (directory/name).open('xb') as f:f.write(data)
    unchanged(inputs,root)
    return directory


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--srs-run');parser.add_argument('--ibjs-run');args=parser.parse_args()
    print(build({method:path for method,path in [('SRS',args.srs_run),('IBJS',args.ibjs_run)] if path}))


if __name__=='__main__':main()
