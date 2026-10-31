"""LOCAL Verdict controller: inert describe, gated plan/pilot/run, read-only verify.

No command is launched at import. Actual calls require completed model/reverse/
moments, a separately reviewed measurement/resource plan and root approval.
"""
import argparse
import copy
from fractions import Fraction
import importlib
import json
import math
from pathlib import Path
import re
import shutil
import time
import full_verdict_ssb_local as contract
import full_verdict_ssb_local_ops as ops


def output_path(path):
    path=Path(path).resolve();base=(contract.ROOT/contract.local_spec()['output']).resolve()
    contract.require(any((base/name) in path.parents for name in ('plans','audits')),'LOCAL output must be in new plans/audits, never sealed runs or measurements')
    if path.exists():raise FileExistsError('Refuse existing LOCAL output: '+str(path))
    return path


def safe_name(value):
    contract.require(isinstance(value,str) and re.fullmatch('[a-zA-Z0-9_-]{1,32}',value),'Fresh safe LOCAL name requires1--32 ASCII characters')
    return value


def write_new(path,value):
    path=output_path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as out:json.dump(value,out,sort_keys=True,indent=2,allow_nan=False);out.write('\n')


def command(kind,spec,home,call=None):
    core=contract.load_frozen();home=Path(home);classes=home/'classes'
    if kind=='compile':return [core.JAVAC,'-J-Xmx256m','-encoding','UTF-8','-cp',core.JAR,'-d',classes,contract.ROOT/spec['java_source']]
    java=[core.JAVA,'-Xmx384m','-XX:MaxMetaspaceSize=192m','-Duser.language=en','-Duser.country=US','-Duser.timezone=UTC',
        '-cp',str(classes)+';'+str(core.JAR),spec['java_class']]
    if kind=='registration':return java+['register',str(spec['sample_rows']),str(spec['population_rows']),home/'registration.tsv']
    contract.require(kind=='query' and call is not None,'Known LOCAL command role required')
    folder=home/'calls'/call['call_id'];return java+['query',call['mode'],call['call_id'],folder/'input.sql',folder/'result.tsv']


def required_files(plan):
    required=set('plan.json review.json lineage.json oracle.json resource_start.json protected_before.json import.json registration.tsv snapshot_before.json snapshot_after.json post_run.json evaluation.json budget.json server.json'.split())
    required.add('classes/'+plan['spec']['java_class']+'.class')
    required.update('import_'+t+'.json' for t in ('dwdate','customer','part','supplier','lineorder'))
    for role in ('compile','registration'):required.update(role+suffix for suffix in ('.stdout.log','.stderr.log','.process.json'))
    calls=plan['queries'];contract.require(len(calls)==len({c['call_id'] for c in calls})==38,'Exactly38 unique LOCAL original calls required')
    for call in calls:required.update('calls/'+call['call_id']+'/'+name for name in ('input.sql','result.tsv','java.stdout.log','java.stderr.log','java.process.json','receipt.json','receipt.seal.json'))
    return required


def check_required(plan,files):contract.require(set(files)==required_files(plan),'Exact LOCAL result required set differs')


def rewrite_proof(log,call,spec):
    sqls=[line.split('A query to db: ',1)[1] for line in log.splitlines() if 'A query to db: ' in line]
    sqls=[s for s in sqls if re.search(r'(?:public_verdict\.vs_lineorder_|public\.lineorder)',s,re.I)]
    contract.require(len(sqls)==1,'Missing/ambiguous original LOCAL physical rewrite')
    sql=sqls[0];contract.require(not re.search(r'public\.lineorder\b',sql,re.I) and spec['sample_relation'] in sql.lower(),'Original query did not use LOCAL retained fact')
    tables=re.search(r'\bfrom\s+(.*?)\s+where\b',call['sql'],re.I).group(1)
    dims=set(t.strip().lower() for t in tables.split(','))-{'lineorder'}
    contract.require(set(re.findall(r'\bpublic\.([a-z_0-9]+)',sql,re.I))==dims and
        set(re.findall(r'\bpublic_verdict\.(vs_[a-z_0-9]+)',sql,re.I))=={spec['sample_relation'].split('.')[1]},'Original LOCAL full-dimension rewrite differs')
    contract.require(call['mode']!='subsampling' or 'verdict_vpart' in sql,'Missing original LOCAL CI partition rewrite')
    return dict(physical_sql=sql,full_dimensions=sorted(dims),fact_sample=spec['sample_relation'],native_ci_partition_present='verdict_vpart' in sql)


def verify_call(plan,home,call):
    core=contract.load_frozen();folder=Path(home)/'calls'/call['call_id'];receipt=contract.read(folder/'receipt.json')
    contract.require(contract.read(folder/'receipt.seal.json')=={'sha256':contract.digest(folder/'receipt.json')} and
        receipt['call']==call and (folder/'input.sql').read_text(encoding='utf-8')==call['sql'],'LOCAL exact call/SQL/seal identity differs')
    actual=core.candidate().parse_engine((folder/'result.tsv').read_text(encoding='utf-8'),[call])[call['call_id']]
    process=contract.read(folder/'java.process.json');core.validate_process(process,command('query',plan['spec'],home,call))
    ops.validate_science_scan(receipt['science_window'])
    contract.require(process['seconds']<=plan['spec']['limits']['native_process_timeout_seconds']+15,'Recorded native elapsed time exceeds operational bound')
    log=(folder/'java.stdout.log').read_text(encoding='utf-8')+'\n'+(folder/'java.stderr.log').read_text(encoding='utf-8')
    try:proof=rewrite_proof(log,call,plan['spec'])
    except ValueError as error:
        contract.require(actual['status']=='ENGINE_ERROR','Successful native LOCAL call lacks actual rewrite')
        proof=dict(status='UNAVAILABLE_ENGINE_ERROR',diagnostic=str(error))
    contract.require(receipt==dict(call=call,result=actual,process=process,rewrite=proof,science_window=receipt['science_window']),'LOCAL raw decode/command/rewrite receipt differs')
    return receipt


def compare_call(call,actual,oracle,truth):
    core=contract.load_frozen()
    if call['role']!='RAW':return dict(call=call,sample_oracle_status='UNAVAILABLE_COMPONENT_SUM_NOT_STORED',sample_groups=None,
        population_status='UNAVAILABLE_NO_MATCHING_COMPONENT_TRUTH',population_groups=None)
    expected=[dict(key=g['key'],verdict_expected=g['expected']) for g in oracle['groups']]
    exact=[x for x in truth if x['query_no']==call['query_no']]
    return dict(call=call,sample_oracle_status='AVAILABLE_EXACT_RETAINED_EXPRESSION_SUM',sample_groups=core.compare_oracle(actual,expected),
        population_status='AVAILABLE_LOCAL_FULL_EXPRESSION_TRUTH',population_groups=core.population_statistics(actual,exact))


def evaluate(plan,home):
    core=contract.load_frozen();candidate=core.candidate();oracle=plan['lineage']['oracle'];truth=plan['lineage']['source']['canonical_truth'];results={};comparisons=[];adapters=[]
    for call in plan['queries']:
        r=verify_call(plan,home,call)['result'];results[call['call_id']]=r;comparisons.append(compare_call(call,r,oracle[call['query_no']],truth))
    for mode in ('nobound','subsampling'):
        for qno in (10,11,12):
            calls=[c for c in plan['queries'] if c['mode']==mode and c['query_no']==qno]
            adapter=candidate.profit_adapter(*(results[c['call_id']] for c in calls))
            actual=dict(error=None if adapter['status']=='POINT_ADAPTER_RETURNED' else 'CHILD_ENGINE_ERROR',usable_for_point_comparison=adapter['status']=='POINT_ADAPTER_RETURNED',
                rows=[dict(r,point_status='FINITE' if r['point'] is not None else 'NULL') for r in adapter['groups']])
            expected=[dict(key=g['key'],verdict_expected=g['expected']) for g in oracle[qno]['groups']]
            adapters.append(dict(query_no=qno,mode=mode,adapter=adapter,sample_groups=core.compare_oracle(actual,expected),
                population_groups=core.population_statistics(actual,[x for x in truth if x['query_no']==qno]),combined_ci='UNSUPPORTED_NO_COVARIANCE_MODEL'))
    checks=[g for c in comparisons if c['call']['mode']=='nobound' and c['call']['role']=='RAW' and c['call']['query_no']<10 for g in c['sample_groups']]
    checks += [g for a in adapters if a['mode']=='nobound' for g in a['sample_groups']]
    point=bool(checks) and all(g['numeric_gate_pass'] for g in checks)
    return dict(status='PASS_LOCAL_VERDICT_SAMPLE_SCALING_WITH_EXPLICIT_GAPS' if point else 'FAIL_LOCAL_VERDICT_SAMPLE_SCALING',point_gate_pass=point,
        comparisons=comparisons,adapters=adapters,original_calls=38,engine_error_calls=sum(r['error'] is not None for r in results.values()),
        native_ci_rows=sum(len(r['rows']) for r in results.values() if r['call']['mode']=='subsampling'),
        unavailable_native_ci_rows=sum(row['ci_status']!='FINITE' for r in results.values() if r['call']['mode']=='subsampling' for row in r['rows']),
        scope=plan['spec']['scope'],author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        timing_scope=plan['spec']['sampling_cost_scope'])


def revalidate_plan(plan):
    _prove_plan(plan);return plan


def _prove_plan(plan):
    boundary=contract._PlanningBoundary(plan['parent_expected'])
    expected=contract._plan_from_boundary(plan['parent_expected'],plan['measurement'],plan['resource_review'],boundary)
    contract.require(expected==plan,'Current complete LOCAL plan/source/parents/runtime differs')
    boundary.plan=copy.deepcopy(plan);return boundary


def approval(path,sha,status,binding):
    contract.require(path and sha and Path(path).is_file() and contract.digest(path)==sha,'Exact root approval bytes required before operation')
    r=contract.read(path);contract.require(r.get('status')==status and r.get('binding_sha256')==binding and
        r.get('limits')==contract.local_spec()['limits'],'Root approval scope/binding/resource limits differ');return r


def validate_budget(plan,budget,start):
    s=plan['spec'];limits=s['limits'];samples=budget['samples']
    scan=start['model_scan'];ops.validate_science_scan(scan)
    contract.require(start['limits']==limits and type(start.get('available_ram_bytes')) is int and type(start.get('free_disk_bytes')) is int and
        start['available_ram_bytes']>=limits['minimum_available_ram_bytes'] and start['free_disk_bytes']>=limits['minimum_free_disk_bytes'] and
        budget['spec_limits']==limits and bool(samples),'LOCAL startup/resource history missing')
    previous=-1.;core=contract.load_frozen()
    for sample in samples:
        ops.validate_budget_sample(s,sample)
        contract.require(all(type(sample[k]) is int and sample[k]>=0 for k in ('wal_now_bytes','wal_before_bytes','temp_now_bytes','temp_before_bytes')),'Nonnegative actual physical WAL/temp counters required')
        expected=core.budget_total(sample['owned_files_bytes'],sample['owned_database_bytes'],sample['wal_now_bytes'],sample['wal_before_bytes'],sample['temp_now_bytes'],sample['temp_before_bytes'])
        contract.require(all(sample[k]==v for k,v in expected.items()) and type(sample['monotonic']) in (int,float) and math.isfinite(sample['monotonic']) and sample['monotonic']>=max(0,previous),'LOCAL resource arithmetic/order differs')
        contract.require(sample['wal_before_bytes']==samples[0]['wal_before_bytes'] and sample['temp_before_bytes']==samples[0]['temp_before_bytes'],'LOCAL resource baseline changed')
        contract.require(sample['wal_generated_bytes']==core.lsn_integer(sample['wal_lsn'])-core.lsn_integer(budget['wal_lsn_before']) and sample['wal_generated_bytes']>=0,'LOCAL exact WAL LSN accounting missing')
        contract.require(type(sample.get('wal_lsn_observed_monotonic')) in (int,float) and math.isfinite(sample['wal_lsn_observed_monotonic']) and
            0<=sample['wal_lsn_observed_monotonic']<=sample['monotonic'] and type(sample.get('monitor_connection_live')) is bool,'LOCAL LSN observation window evidence missing')
        previous=sample['monotonic']
    contract.require(budget['peak_total_bytes']==max(x['total_bytes'] for x in samples),'LOCAL peak resource differs')


def validate_snapshots(plan,home):
    s=plan['spec'];before=contract.read(home/'snapshot_before.json');after=contract.read(home/'snapshot_after.json');imported=contract.read(home/'import.json')
    imported_loads=ops.validate_loads(s,imported['loads'],True)
    contract.require(imported['status']=='PASS_LOCAL_FULL_DIMENSIONS_RETAINED_FACT_IMPORT' and imported['population_rows']==s['population_rows'] and imported['sample_rows']==s['sample_rows'] and
        imported['original_fact_rows']==imported['original_queries_executed']==0 and imported['dimension_policy']==s['dimension_policy'],'LOCAL complete committed import scope differs')
    for table in ('dwdate','customer','part','supplier','lineorder'):
        target=s['sample_relation'] if table=='lineorder' else 'public.'+table
        contract.require(contract.read(home/('import_'+table+'.json'))==imported_loads[target],'Committed per-table receipt differs from complete import')
    for snap in (before,after):
        contract.require(snap['status']=='PASS_LOCAL_LOCKED_FULL_INPUT_SNAPSHOT' and snap['original_fact_rows']==0 and snap['schema']==ops.expected_schema(plan),'LOCAL schema/skeleton snapshot differs')
        ops.validate_catalog(s,snap['catalog']);ops.validate_aux(s,snap['aux_accounting'],snap['partition_histogram'],snap['probability_hex']);ops.validate_metadata(s,snap['metadata_size'],snap['metadata_name'])
        contract.require(snap['protected_before']==snap['protected_after']==contract.read(home/'protected_before.json') and set(snap['protected_before'])==set(s['protected_databases']),'LOCAL protected3 catalog scope differs')
        contract.require(snap['aux_rows']['rows']==s['sample_rows'] and re.fullmatch('[0-9a-f]{64}',snap['aux_rows']['sha256']),'Complete LOCAL auxiliary snapshot missing')
        snapshot_loads=ops.validate_loads(s,snap['loads'])
        for load in imported['loads']:
            expected=snapshot_loads[load['table']]
            contract.require(load['status']=='PASS_COMMITTED_TABLE_IMPORT' and load['canonical_source']==load['canonical_actual']==expected['canonical_actual'] and load['rows']==expected['rows'],'LOCAL committed import/full fields differ')
    contract.require(before==after,'LOCAL locked input/catalog/auxiliary state changed across native calls')
    post=contract.read(home/'post_run.json');contract.require(post['status']=='PASS_LOCAL_SHARE_LOCKED_38_CALLS' and post['share_lock_held_across_calls']==38 and post['before_sha256']==contract.digest(home/'snapshot_before.json') and post['after_sha256']==contract.digest(home/'snapshot_after.json'),'LOCAL38-call lock receipt differs')


def verify(home):
    """Strictly read only; all scientific and subprocess operations forbidden."""
    return _verify_from_boundary(home)


def _verify_from_boundary(home,boundary=None):
    home=Path(home).resolve();s=contract.local_spec();root=(contract.ROOT/s['output']/'runs').resolve()
    contract.require(root in home.parents,'LOCAL run outside own namespace')
    final=contract.read(home/'final.json');sha=contract.digest(home/'final.json')
    contract.require(contract.read(home/'final.seal.json')=={'sha256':sha} and contract.read(home/'lifecycle.json')=={'status':'PASS','final_sha256':sha},'LOCAL complete final lifecycle/seal missing')
    core=contract.load_frozen();guard=importlib.import_module('full_verdict_ssb_audit');helper=importlib.import_module('full_windows_fingerprint')
    with guard.forbid_science(core),helper.verified_platform(s['platform'],s['machine']):
        plan=contract.read(home/'plan.json')
        validate_final_header(plan,final);check_required(plan,final['files'])
        if boundary is None:boundary=_prove_plan(plan)
        else:
            contract._require_boundary(boundary,plan['parent_expected'])
            contract.require(boundary.plan==plan,'Private exit proof differs from completed output plan')
        for name,rec in final['files'].items():contract.require(contract.artifact(home/name)==rec,'LOCAL final artifact changed: '+name)
        approval(home/'review.json',final['review_sha256'],'APPROVED_LOCAL_VERDICT_EXECUTION',plan['binding_sha256'])
        contract.require(contract.read(home/'lineage.json')==plan['lineage'] and contract.read(home/'oracle.json')==plan['lineage']['oracle'],'LOCAL independent moment lineage/oracle changed')
        validate_snapshots(plan,home);validate_budget(plan,contract.read(home/'budget.json'),contract.read(home/'resource_start.json'))
        for role,limit in [('compile',105),('registration',135)]:
            process=contract.read(home/(role+'.process.json'));core.validate_process(process,command(role,s,home));contract.require(process['seconds']<=limit,'Recorded setup time exceeds bound')
        validate_registration(s,(home/'registration.tsv').read_text(encoding='utf-8'))
        server=contract.read(home/'server.json');validate_server(core,home,server,final['pg_control_files'])
        contract.require(contract.artifact(home/'postgresql.log')==final['postgresql_log'],'LOCAL stopped PG log changed')
        result=evaluate(plan,home);contract.require(result==contract.read(home/'evaluation.json') and final['evaluation_status']==result['status'] and final['point_gate_pass']==result['point_gate_pass'],'LOCAL raw result derivation differs')
    return dict(status='PASS_READONLY_LOCAL_VERDICT_EVIDENCE_WITH_AUTHOR_MISMATCH',final_sha256=sha,point_gate_pass=result['point_gate_pass'],evaluation_status=result['status'],
        scope=s['scope'],author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        parent_canonical=plan['lineage']['parent_canonical'],parent_reverse=plan['lineage']['parent_reverse'],parent_formal=plan['lineage']['parent_formal'],
        evaluation_variant=plan['lineage']['evaluation_variant'],group_order_adapter_sha256=plan['lineage']['group_order_adapter_sha256'],historical_reverse_accepted=False,
        final=contract.artifact(home/'final.json'),plan=contract.artifact(home/'plan.json'),evaluation=contract.artifact(home/'evaluation.json'),
        population_rows=s['population_rows'],sample_rows=s['sample_rows'],sampling_ratio=s['sampling_ratio'],original_calls=38,
        database_connected=False,processes_executed=False,scientific_calls_executed=False)


def validate_server(core,home,server,files):
    contract.require(server['status']=='PROJECT_SERVER_STOPPED_BY_OWNER' and server['started_by_controller'] is True and server['startup_requested'] is True and
        server['started_postmaster_pid']==server['stopped_postmaster_pid']==server['startup_ownership']['identity']['pid'],'LOCAL owned project PG must be proven stopped')
    for key,action,code in [('initial_status','status',3),('start','start',0),('stop','stop',0),('post_stop_status','status',3)]:core.validate_pg_control(server[key],action,home,code)
    core.validate_owned_identity(server['startup_ownership']['identity'],server['startup_ownership']['intent']);core.validate_pg_files(home,server,files)


def validate_final_header(plan,final):
    contract.require(final.get('schema')=='local_verdict_ssb_final_v1' and final.get('binding_sha256')==plan['binding_sha256'] and
        final.get('scope')==plan['spec']['scope'] and final.get('author_different_groups')==1713 and
        final.get('author_reproduction_complete') is False and final.get('full_paper_reproduction_complete') is False and
        final.get('actual_stages')==dict(imported_tables=5,javac=1,registrations=1,original_query_calls=38,sqlite_queries=0,new_population_sampling=0),
        'LOCAL result cannot change scope/author gap/actual stage counts')


def validate_registration(spec,text):
    fields=text.strip().split('\t')
    contract.require(len(fields)==5 and fields[:4]==['REGISTER',spec['sample_relation'],str(spec['sample_rows']),str(spec['population_rows'])],
        'Exact original LOCAL registration identity/counts required')
    try:ratio=float(fields[4])
    except (TypeError,ValueError):raise ValueError('Invalid original registration ratio')
    contract.require(math.isfinite(ratio) and ratio==spec['sample_rows']/spec['population_rows'],'Original LOCAL n/N registration result differs')


def run(plan_path,review_path,review_sha,name,start_project_postgres):
    # Approval bytes are checked before even reading an untrusted plan.
    contract.require(review_path and review_sha and Path(review_path).is_file() and contract.digest(review_path)==review_sha,'Exact root approval bytes required before LOCAL operation')
    safe_name(name)
    plan=contract.read(plan_path);approval(review_path,review_sha,'APPROVED_LOCAL_VERDICT_EXECUTION',plan['binding_sha256']);revalidate_plan(plan)
    s=plan['spec'];core=contract.load_frozen();db=ops.LocalDatabase(s)
    contract.require(start_project_postgres,'Explicit PG startup and fresh safe LOCAL name required')
    ram=core.available_ram();free=shutil.disk_usage(contract.ROOT).free
    contract.require(ram>=s['limits']['minimum_available_ram_bytes'] and free>=s['limits']['minimum_free_disk_bytes'],'LOCAL startup resource gate failed')
    model_scan=ops.assert_no_science_processes();home=contract.ROOT/s['output']/'runs'/name;stage=contract.ROOT/s['staging']/name
    home.parent.mkdir(parents=True,exist_ok=True);home.mkdir(exist_ok=False);core.atomic_json(home/'lifecycle.json',{'status':'RUNNING','binding_sha256':plan['binding_sha256']})
    owned={};budget=None
    try:
        stage.mkdir(parents=True,exist_ok=False);budget=ops.LocalBudget(s,home,stage)
        for filename,value in [('plan.json',plan),('lineage.json',plan['lineage']),('oracle.json',plan['lineage']['oracle']),('resource_start.json',dict(limits=s['limits'],available_ram_bytes=ram,free_disk_bytes=free,model_scan=model_scan))]:core.atomic_json(home/filename,value)
        shutil.copyfile(str(review_path),str(home/'review.json'))
        initial=core.pg_control('status',home);contract.require(initial['exit_code']==3,'LOCAL operation requires stopped project PG; do not adopt an unowned server')
        started=core.start_owned_server(home,initial,owned);db.no_external_clients();budget.attach(db)
        db.import_data(plan,home,budget);(home/'classes').mkdir()
        ops.assert_no_science_processes()
        core.bounded_process(command('compile',s,home),home/'compile',budget,90)
        ops.assert_no_science_processes()
        core.bounded_process(command('registration',s,home),home/'registration',budget,120)
        validate_registration(s,(home/'registration.tsv').read_text(encoding='utf-8'))
        execute_queries(plan,home,db,budget)
        evaluation=evaluate(plan,home);core.atomic_json(home/'evaluation.json',evaluation)
        exit_boundary=_prove_plan(plan);budget.tick(force=True);budget.close();db.no_external_clients()
        contract.require(core.postmaster_identity()==owned['identity'],'LOCAL postmaster ownership changed; refuse stop')
        stopped=core.pg_control('stop',home);status_after=core.pg_control('status',home,'status_after');contract.require(status_after['exit_code']==3,'LOCAL PG not stopped')
        server=dict(status='PROJECT_SERVER_STOPPED_BY_OWNER',started_by_controller=True,startup_requested=True,initial_status=initial,start=started,stop=stopped,post_stop_status=status_after,
            started_postmaster_pid=owned['identity']['pid'],stopped_postmaster_pid=owned['identity']['pid'],startup_ownership=contract.read(home/'startup_ownership.json'))
        owned.clear();core.atomic_json(home/'server.json',server);budget.tick(force=True);core.atomic_json(home/'budget.json',budget.report())
        final=dict(schema='local_verdict_ssb_final_v1',binding_sha256=plan['binding_sha256'],review_sha256=review_sha,files={name:contract.artifact(home/name) for name in sorted(required_files(plan))},
            pg_control_files=core.pg_control_artifacts(home,server),postgresql_log=contract.artifact(home/'postgresql.log'),evaluation_status=evaluation['status'],
            point_gate_pass=evaluation['point_gate_pass'],
            scope=s['scope'],author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
            actual_stages=dict(imported_tables=5,javac=1,registrations=1,original_query_calls=38,sqlite_queries=0,new_population_sampling=0))
        core.atomic_json(home/'final.json',final);core.atomic_json(home/'final.seal.json',{'sha256':contract.digest(home/'final.json')});core.atomic_json(home/'lifecycle.json',{'status':'PASS','final_sha256':contract.digest(home/'final.json')})
        return _verify_from_boundary(home,exit_boundary)
    except BaseException as error:
        if budget is not None:core.atomic_json(home/'failed_budget.json',budget.report() if budget.samples else {'samples':[]})
        core.atomic_json(home/'lifecycle.json',{'status':'TAINTED','error':repr(error)});raise
    finally:
        if budget is not None:budget.close()
        if owned:
            try:
                db.no_external_clients();contract.require(core.postmaster_identity()==owned['identity'],'Unproven LOCAL failed-run ownership; refuse stop')
                core.atomic_json(home/'failed_shutdown.json',dict(identity=owned['identity'],stop=core.pg_control('stop',home,'failed_stop'),status_after=core.pg_control('status',home,'failed_status')))
            except BaseException as error:core.atomic_json(home/'unresolved_shutdown.json',dict(status='TAINTED_UNRESOLVED_OWNERSHIP',error=repr(error)))


def execute_queries(plan,home,db,budget):
    s=plan['spec'];core=db.core;db.no_external_clients();connection=db.connect()
    try:
        with connection.cursor() as c:
            c.execute('SET lock_timeout=10000')
            c.execute('LOCK TABLE public.lineorder,public.dwdate,public.customer,public.part,public.supplier,'+s['sample_relation']+',public_verdict.verdict_meta_size,public_verdict.verdict_meta_name IN SHARE MODE')
            c.execute('SELECT clock_timestamp()::text,txid_current_snapshot()::text,pg_backend_pid()');begin=list(c.fetchone())
            before=db.locked_snapshot(plan,home,c,budget);core.atomic_json(home/'snapshot_before.json',before)
            (home/'calls').mkdir()
            for call in plan['queries']:
                scan=ops.assert_no_science_processes();folder=home/'calls'/call['call_id'];folder.mkdir();(folder/'input.sql').write_text(call['sql'],encoding='utf-8')
                process=core.bounded_process(command('query',s,home,call),folder/'java',budget,s['limits']['native_process_timeout_seconds'])
                result=core.candidate().parse_engine((folder/'result.tsv').read_text(encoding='utf-8'),[call])[call['call_id']]
                log=(folder/'java.stdout.log').read_text(encoding='utf-8')+'\n'+(folder/'java.stderr.log').read_text(encoding='utf-8')
                try:proof=rewrite_proof(log,call,s)
                except ValueError as error:
                    contract.require(result['status']=='ENGINE_ERROR','Successful LOCAL native call lacks rewrite');proof=dict(status='UNAVAILABLE_ENGINE_ERROR',diagnostic=str(error))
                core.atomic_json(folder/'receipt.json',dict(call=call,result=result,process=process,rewrite=proof,science_window=scan));core.atomic_json(folder/'receipt.seal.json',{'sha256':contract.digest(folder/'receipt.json')})
            after=db.locked_snapshot(plan,home,c,budget);contract.require(before==after,'LOCAL locked inputs changed across38 calls');core.atomic_json(home/'snapshot_after.json',after)
            c.execute('SELECT clock_timestamp()::text,txid_current_snapshot()::text');end=list(c.fetchone())
            core.atomic_json(home/'post_run.json',dict(status='PASS_LOCAL_SHARE_LOCKED_38_CALLS',share_lock_held_across_calls=38,lock_begin=begin,lock_end=end,
                before_sha256=contract.digest(home/'snapshot_before.json'),after_sha256=contract.digest(home/'snapshot_after.json')))
        connection.rollback()
    finally:connection.close()


def pilot_files():return set('plan.json review.json measurement.json protected_before.json protected_after.json resource_start.json budget.json server.json'.split())


def verify_pilot(final_path):
    """Read-only physical/semantic acceptance of a completed owned PG probe."""
    return _verify_pilot_from_boundary(final_path)


def _verify_pilot_from_boundary(final_path,boundary=None):
    path=Path(final_path).resolve();root=(contract.ROOT/contract.local_spec()['output']/'measurements').resolve()
    contract.require(root in path.parents and path.name=='final.json','Exact completed LOCAL measurement final required')
    home=path.parent;final=contract.read(path);sha=contract.digest(path);s=contract.local_spec();core=contract.load_frozen()
    contract.require(contract.read(home/'final.seal.json')=={'sha256':sha} and contract.read(home/'lifecycle.json')=={'status':'PASS','final_sha256':sha},'Complete pilot final lifecycle/seal missing')
    guard=importlib.import_module('full_verdict_ssb_audit');helper=importlib.import_module('full_windows_fingerprint')
    with guard.forbid_science(core),helper.verified_platform(s['platform'],s['machine']):
        plan=contract.read(home/'plan.json')
        if boundary is None:boundary=contract._PlanningBoundary(plan['parent_expected'])
        contract._require_boundary(boundary,plan['parent_expected'])
        contract.require(plan==contract._pilot_plan_from_boundary(boundary) and final['binding_sha256']==plan['binding_sha256'] and
            final['schema']=='local_verdict_resource_measurement_final_v1','Pilot current complete code/parent/runtime plan differs')
        contract.require(set(final['files'])==pilot_files(),'Exact pilot required artifact set differs')
        for name,rec in final['files'].items():contract.require(contract.artifact(home/name)==rec,'Pilot physical artifact changed')
        approval(home/'review.json',final['review_sha256'],'APPROVED_LOCAL_VERDICT_SF2_MEASUREMENT',plan['binding_sha256'])
        measurement=contract.read(home/'measurement.json');contract.validate_measurement(measurement)
        contract.require(measurement['parent_expected']==plan['parent_expected'] and measurement['binding_sha256']==plan['binding_sha256'],'Pilot measured parent/config differs')
        before=contract.read(home/'protected_before.json');after=contract.read(home/'protected_after.json')
        contract.require(before==after==measurement['protected_before']==measurement['protected_after'] and set(before)==set(s['protected_databases']),'Pilot protected3 catalog identities changed')
        validate_budget({'spec':s},contract.read(home/'budget.json'),contract.read(home/'resource_start.json'))
        validate_server(core,home,contract.read(home/'server.json'),final['pg_control_files'])
        contract.require(contract.artifact(home/'postgresql.log')==final['postgresql_log'],'Pilot stopped PostgreSQL log changed')
        server=measurement['server'];contract.require(server['version'].startswith('11.5') and Path(server['data_directory']).resolve()==core.CLUSTER.resolve(),'Pilot actual PG version/cluster differs')
    return dict(status='PASS_READONLY_MEASUREMENT_CLOSURE',final=contract.artifact(path),parent_expected=plan['parent_expected'],measurement=measurement,
        database_connected=False,processes_executed=False,scientific_calls_executed=False)


def pilot(plan_path,review_path,review_sha,name,start_project_postgres):
    contract.require(review_path and review_sha and Path(review_path).is_file() and contract.digest(review_path)==review_sha,'Exact pilot root approval bytes required before plan/source/PG')
    safe_name(name)
    plan=contract.read(plan_path);s=contract.local_spec();binding=plan['binding_sha256'];expected=plan['parent_expected']
    approval(review_path,review_sha,'APPROVED_LOCAL_VERDICT_SF2_MEASUREMENT',binding)
    contract.require(plan==contract.build_pilot_plan(expected),'Pilot current code/runtime/parents differ')
    core=contract.load_frozen();db=ops.LocalDatabase(s)
    contract.require(start_project_postgres,'Explicit stopped-PG pilot startup/fresh name required')
    ram=core.available_ram();free=shutil.disk_usage(contract.ROOT).free
    contract.require(ram>=s['limits']['minimum_available_ram_bytes'] and free>=s['limits']['minimum_free_disk_bytes'],'Pilot resource window closed')
    scan=ops.assert_no_science_processes();home=contract.ROOT/s['output']/'measurements'/name;home.parent.mkdir(parents=True,exist_ok=True);home.mkdir(exist_ok=False)
    core.atomic_json(home/'lifecycle.json',{'status':'RUNNING','binding_sha256':binding});owned={};budget=None
    try:
        stage=contract.ROOT/s['staging']/('measurement_'+name);stage.mkdir(parents=True,exist_ok=False);budget=ops.LocalBudget(s,home,stage)
        core.atomic_json(home/'plan.json',plan);shutil.copyfile(str(review_path),str(home/'review.json'))
        core.atomic_json(home/'resource_start.json',dict(limits=s['limits'],available_ram_bytes=ram,free_disk_bytes=free,model_scan=scan))
        initial=core.pg_control('status',home);contract.require(initial['exit_code']==3,'Pilot never adopts existing PG')
        started=core.start_owned_server(home,initial,owned);db.no_external_clients();budget.attach(db);before=db.protected();connection=db.connect('deepdb_verdict_ssb')
        try:
            rows=[]
            with connection.cursor() as c:
                c.execute('SET TRANSACTION READ ONLY');c.execute('SET LOCAL statement_timeout=30000');c.execute('SET LOCAL lock_timeout=10000')
                c.execute('SHOW server_version');version=c.fetchone()[0];c.execute('SHOW data_directory');directory=c.fetchone()[0]
                contract.require(version.startswith('11.5') and Path(directory).resolve()==core.CLUSTER.resolve(),'Pilot actual server not projectPG11.5')
                started_measurement=time.monotonic()
                for relation in ('public.dwdate','public.customer','public.supplier','public.part',s['sample_relation']):
                    ops.assert_no_science_processes()
                    c.execute('LOCK TABLE '+relation+' IN SHARE MODE')
                    c.execute('SELECT COUNT(*),AVG(pg_column_size(t)),MAX(pg_column_size(t)) FROM '+relation+' t');count,average,maximum=c.fetchone()
                    c.execute('SELECT pg_relation_size(%s::regclass),pg_indexes_size(%s::regclass),pg_total_relation_size(%s::regclass)',(relation,)*3);heap,index,total=c.fetchone()
                    rows.append(dict(relation=relation,rows=count,average_row_bytes=float(average),max_row_bytes=maximum,heap_bytes=heap,index_bytes=index,total_bytes=total))
                    budget.tick(force=True);contract.require(time.monotonic()-started_measurement<=180,'Bounded measurement deadline exceeded')
            connection.rollback()
        finally:connection.close()
        after=db.protected();contract.require(before==after,'Pilot changed protected3 identities')
        measurement=dict(status='PASS_READONLY_SF2_RELATION_WIDTH_MEASUREMENT',database='deepdb_verdict_ssb',relations=rows,data_modified=False,scientific_calls=0,
            parent_expected=expected,binding_sha256=binding,protected_before=before,protected_after=after,server=dict(version=version,data_directory=directory))
        contract.validate_measurement(measurement);db.no_external_clients();contract.require(core.postmaster_identity()==owned['identity'],'Pilot postmaster identity changed')
        exit_boundary=contract._PlanningBoundary(expected)
        contract.require(plan==contract._pilot_plan_from_boundary(exit_boundary),'Pilot source/runtime/parents changed before publication')
        budget.tick(force=True);budget.close();stopped=core.pg_control('stop',home);status=core.pg_control('status',home,'status_after');contract.require(status['exit_code']==3,'Pilot server not stopped')
        server=dict(status='PROJECT_SERVER_STOPPED_BY_OWNER',started_by_controller=True,startup_requested=True,initial_status=initial,start=started,stop=stopped,post_stop_status=status,
            started_postmaster_pid=owned['identity']['pid'],stopped_postmaster_pid=owned['identity']['pid'],startup_ownership=contract.read(home/'startup_ownership.json'))
        owned.clear();budget.tick(force=True)
        for filename,value in [('measurement.json',measurement),('protected_before.json',before),('protected_after.json',after),('server.json',server),('budget.json',budget.report())]:core.atomic_json(home/filename,value)
        final=dict(schema='local_verdict_resource_measurement_final_v1',binding_sha256=binding,review_sha256=review_sha,
            files={n:contract.artifact(home/n) for n in sorted(pilot_files())},pg_control_files=core.pg_control_artifacts(home,server),postgresql_log=contract.artifact(home/'postgresql.log'))
        core.atomic_json(home/'final.json',final);core.atomic_json(home/'final.seal.json',{'sha256':contract.digest(home/'final.json')})
        core.atomic_json(home/'lifecycle.json',{'status':'PASS','final_sha256':contract.digest(home/'final.json')})
        return _verify_pilot_from_boundary(home/'final.json',exit_boundary)
    except BaseException as error:
        if budget is not None:core.atomic_json(home/'failed_budget.json',budget.report() if budget.samples else {'samples':[]})
        core.atomic_json(home/'lifecycle.json',{'status':'TAINTED','error':repr(error)});raise
    finally:
        if budget is not None:budget.close()
        if owned:
            try:
                db.no_external_clients();contract.require(core.postmaster_identity()==owned['identity'],'Unproven pilot failed-run ownership')
                core.atomic_json(home/'failed_shutdown.json',dict(identity=owned['identity'],stop=core.pg_control('stop',home,'failed_stop'),status_after=core.pg_control('status',home,'failed_status')))
            except BaseException as error:core.atomic_json(home/'unresolved_shutdown.json',dict(status='TAINTED_UNRESOLVED_OWNERSHIP',error=repr(error)))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',nargs='?',default='describe',choices=['describe','pilot-plan','plan','pilot','run','verify','verify-pilot'])
    p.add_argument('--parents',type=Path);p.add_argument('--measurement',type=Path);p.add_argument('--resource-review',type=Path);p.add_argument('--plan',type=Path)
    p.add_argument('--review',type=Path);p.add_argument('--review-sha256');p.add_argument('--name');p.add_argument('--start-project-postgres',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    if args.output:output_path(args.output) # Before parent hashing or actual work.
    if args.action=='describe':result=dict(status='CANDIDATE_CODE_ONLY',spec=contract.local_spec(),actual_execution_allowed=False,requirements=['completed exact original source/model and canonical forward/reverse/native13moments','actual relation-width measurement and independent resource review','frozen plan/code and exact root approval'])
    elif args.action=='pilot-plan':
        contract.require(args.parents,'Complete final parent descriptors required');result=contract.build_pilot_plan(contract.read(args.parents))
    elif args.action=='plan':
        contract.require(args.parents and args.measurement and args.resource_review,'Complete reviewed plan inputs required')
        result=contract.build_plan(contract.read(args.parents),contract.artifact(args.measurement),contract.read(args.resource_review))
    elif args.action=='pilot':
        contract.require(args.plan,'Frozen reviewed measurement plan required');result=pilot(args.plan,args.review,args.review_sha256,args.name,args.start_project_postgres)
    elif args.action=='run':result=run(args.plan,args.review,args.review_sha256,args.name,args.start_project_postgres)
    elif args.action=='verify':
        safe_name(args.name);result=verify(contract.ROOT/contract.local_spec()['output']/'runs'/args.name)
    else:
        contract.require(args.measurement,'Completed measurement final required');result=verify_pilot(args.measurement)
    if args.output:write_new(args.output,result)
    else:print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))


if __name__=='__main__':main()
