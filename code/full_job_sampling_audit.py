"""Strict filesystem-only receipt audit. Never imports a DB/controller/model API."""
import argparse
from collections import Counter
from fractions import Fraction
import json
import math
from pathlib import Path
import random

import full_job_sampling as core
from full_job_sampling import require,read,artifact

ROOT=core.ROOT
FILES=tuple(['plan.json','approval.json','collection.json','predictions.json','verification.json','lifecycle.json','execution.json']+
            [name for i in range(70) for name in ('queries/query_%02d.json'%i,'queries/query_%02d.seal.json'%i)])
COMPLETE={'COMPLETE','COMPLETE_ZERO'}
INCOMPLETE={'QUERY_WALL_BUDGET','ID_ATTEMPT_BUDGET','SQL_ROUNDTRIP_BUDGET','QUERY_ERROR','STATEMENT_TIMEOUT'}


def nonnegative(value):
    require(type(value) in (int,float) and math.isfinite(value) and value>=0,'Finite nonnegative measurement required');return value


def independent_estimate(cardinality,population,selected):
    core.integer(cardinality);require(bool(population) and set(population)==set(selected),'Complete estimator input required')
    numerator=cardinality;denominator=1
    for t,N in population.items():
        core.integer(N);core.integer(selected[t]);require(0<selected[t]<=N,'Invalid entity inclusion fraction')
        numerator*=N;denominator*=selected[t]
    return Fraction(numerator,denominator)


def independent_sample_count(query,samples):
    """SQL three-valued WHERE; duplicate FK multiplicities; no core estimator."""
    require(set(samples)==set(query['tables']),'Complete independent join input required')
    conditions={p['table']:p['conditions'] for p in query['predicates']};filtered={}
    for t,s in samples.items():
        columns=s['projection'];rows=s['rows'];require(len(columns)==len(set(columns)),'Duplicate projected column')
        output=[]
        for r in rows:
            require(type(r) is list and len(r)==len(columns),'Truncated projected row')
            d=dict(zip(columns,r));accepted=True
            for c in conditions[t]:
                v=d[c['column']];w=c['value'];op=c['operator']
                if v is None:accepted=False;break
                if not {'=':v==w,'!=':v!=w,'<':v<w,'>':v>w,'<=':v<=w,'>=':v>=w}[op]:accepted=False;break
            if accepted:output.append(d)
        filtered[t]=output
    counts={t:Counter(r['movie_id'] for r in rows if r['movie_id'] is not None) for t,rows in filtered.items() if t!='title'}
    total=0
    for title in filtered['title']:
        contribution=1
        for count in counts.values():contribution*=count[title['id']]
        total+=contribution
    return total


def verify_sample(query_no,table,s,metadata,contract,complete):
    require(set(s) in ({'table','population','projection','seed','target','batches','selected_ids','rows','complete'},), 'Incomplete/extra sample trace fields')
    require(s['table']==table and s['population']==metadata and s['projection']==core.projection(contract,table)
            and s['seed']==str(core.seed_for(query_no,table)) and type(s['complete']) is bool,'Sample source/projection/seed changed')
    N=metadata['rows'];target=min(core.CONFIG['samples_per_table'],N)
    require(type(s['target']) is int and s['target']==target and type(s['batches']) is list,'Incorrect sample target')
    rng=random.Random(core.seed_for(query_no,table));seen=set();selected=[];rows=[];attempts=0;idcol=s['projection'].index('id')
    require(type(s['rows']) is list and type(s['selected_ids']) is list,'Missing sample rows/IDs')
    for index,batch in enumerate(s['batches']):
        require(set(batch) in ({'attempted_ids','ids','rows'},{'attempted_ids','ids','rows','operation_index'}),'Unexpected RNG batch fields')
        require(len(selected)<target,'Extra sampling batch after completion');ids=[]
        capacity=min(core.CONFIG['batch_size'],target-len(selected))
        for candidate in batch['attempted_ids']:
            require(len(ids)<capacity,'RNG work after full candidate batch')
            require(type(candidate) is int and candidate==rng.randint(metadata['min_id'],metadata['max_id']),'RNG/ID trace changed')
            attempts+=1;require(attempts<=core.CONFIG['max_id_attempts_per_table'],'ID attempt budget exceeded')
            if candidate not in seen:seen.add(candidate);ids.append(candidate)
        require(batch['ids']==ids,'Duplicate/hole candidate rejection trace changed')
        if batch['rows'] is None:
            require(not s['complete'] and index==len(s['batches'])-1 and 'operation_index' not in batch,'Unfinished batch in completed sample');continue
        require(len(ids)==capacity and type(batch['rows']) is list and type(batch.get('operation_index')) is int,'Completed lookup missing exact batch link')
        found={}
        for row in batch['rows']:
            require(type(row) is list and len(row)==len(s['projection']) and all(v is None or type(v) is int for v in row),'Invalid projected entity row')
            key=row[idcol];require(type(key) is int and key in ids and key not in found,'Unexpected/duplicate lookup ID');found[key]=row
        for key in ids:
            if key in found:selected.append(key);rows.append(found[key])
    require(s['selected_ids']==selected and s['rows']==rows and len(selected)<=target,'Selected sample rows/order changed')
    require(s['complete']==(len(selected)==target) and (not complete or s['complete']),'Incomplete sample marked complete')
    return attempts


def prediction_row(q):
    return {k:q[k] for k in ('query_no','sql','status','sample_cardinality','raw_prediction','wall_seconds','sql_roundtrips','id_attempts')}


def validate_query(q,expected,metadata,contract,binding,pid):
    fields={'query_no','sql','binding','scope','table_samples','operations','status','sample_cardinality','raw_prediction','client_pid',
            'config','wall_seconds','id_attempts','sql_roundtrips','cleanup_sql_roundtrips','deadline_cancelled','budget_includes_rng_rejection_base_lookup_and_join'}
    require(set(q)==(fields if q.get('status') in COMPLETE else fields|{'error_type','sqlstate'}),'Incomplete/extra terminal query fields')
    require(q['query_no']==expected['query_no'] and type(q['query_no']) is int and q['sql']==expected['sql']
            and q['binding']==binding and q['scope']==core.SCOPE and q['config']==core.CONFIG
            and q['client_pid']==pid and type(q['client_pid']) is int,'Query identity/scope/config/PID changed')
    done=q['status'] in COMPLETE;require(done or q['status'] in INCOMPLETE,'Unknown/nonterminal query status')
    elapsed=nonnegative(q['wall_seconds']);require(type(q['deadline_cancelled']) is bool
        and q['budget_includes_rng_rejection_base_lookup_and_join'] is True,'Deadline/timing contract missing')
    require(type(q['operations']) is list and len(q['operations'])<=core.CONFIG['max_sql_roundtrips'],'SQL budget/trace incomplete')
    require(type(q['sql_roundtrips']) is int and q['sql_roundtrips']==len(q['operations'])
            and type(q['cleanup_sql_roundtrips']) is int and q['cleanup_sql_roundtrips']==sum(op['cleanup'] for op in q['operations'])<=3,'SQL/cleanup counts changed')
    if not q['operations']:
        # Budget.sql() can reject before it records or sends the first
        # SAVEPOINT. This is a genuine null terminal, never a missing result.
        require(q['status']=='QUERY_WALL_BUDGET' and elapsed>=core.CONFIG['max_query_seconds']
                and q['table_samples']=={} and q['id_attempts']=={} and q['cleanup_sql_roundtrips']==0
                and q['raw_prediction'] is None and q['sample_cardinality'] is None
                and q['error_type']=='SamplingStopped' and q['sqlstate'] is None,
                'Only an expired pre-SAVEPOINT null terminal may have zero SQL work')
        return prediction_row(q)
    samples=q['table_samples'];require(type(samples) is dict and set(samples)<=set(expected['tables']),'Unexpected sampling table')
    ordered=list(expected['tables']);require(list(samples)==ordered[:len(samples)] or sorted(samples)==ordered[:len(samples)],'Sampling table prefix missing')
    if done:require(set(samples)==set(ordered) and elapsed<core.CONFIG['max_query_seconds'] and not q['deadline_cancelled'],'Completed estimate outside wall/coverage budget')
    attempts={};linked=set();nextstart=0.;joins=[]
    for t,s in samples.items():
        attempts[t]=verify_sample(q['query_no'],t,s,metadata[t],contract,done)
        for b in s['batches']:
            if b['rows'] is not None:
                i=b['operation_index'];require(i not in linked and 0<=i<len(q['operations']),'Duplicate/invalid physical lookup link');linked.add(i)
                op=q['operations'][i]
                require(op['kind']=='base_lookup/'+t and op['sql']==core.lookup_sql(t,s['projection'])
                        and op['parameters']==[b['ids']] and op['response']==b['rows'] and op['status']=='PASS','Sample rows lack exact base SQL receipt')
    require(q['id_attempts']==attempts,'RNG attempt cost changed')
    allowed=dict(savepoint='SAVEPOINT sampling_query',release='RELEASE SAVEPOINT sampling_query',rollback='ROLLBACK TO SAVEPOINT sampling_query',cleanup_limit='SET LOCAL statement_timeout = 5000')
    for i,op in enumerate(q['operations']):
        fields={'kind','sql','parameters','started_seconds','seconds','status','response','cleanup'}
        require(set(op)==(fields if op.get('status')=='PASS' else fields|{'error'}),'Incomplete/extra SQL operation fields')
        start=nonnegative(op['started_seconds']);duration=nonnegative(op['seconds'])
        require(start+1e-6>=nextstart and start+duration<=elapsed+1e-5,'Operation timeline outside query wall');nextstart=start+duration
        require(type(op['cleanup']) is bool and op['status'] in {'PASS','ERROR'},'Incomplete/invalid SQL operation')
        if op['status']=='ERROR':require(op['response'] is None and type(op['error']) is str and bool(op['error']),'Invalid failed operation response')
        k=op['kind']
        if k in allowed:require(op['sql']==allowed[k] and op['parameters'] is None and op['response'] is None,'Control statement changed')
        elif k=='statement_limit':
            prefix='SET LOCAL statement_timeout = ';require(op['sql'].startswith(prefix) and op['parameters'] is None and op['response'] is None,'Statement limit SQL changed')
            value=op['sql'][len(prefix):];require(value.isdigit() and 1<=int(value)<=5000,'Statement timeout exceeds policy')
        elif k.startswith('base_lookup/'):
            t=k.split('/')[1];require(t in samples and op['sql']==core.lookup_sql(t,samples[t]['projection']),'Unregistered base retrieval')
            require(i>0 and q['operations'][i-1]['kind']=='statement_limit','Missing per-statement deadline')
            if op['status']=='PASS':require(i in linked,'Unreferenced successful base response')
        elif k=='sample_join':
            require(set(samples)==set(ordered) and all(s['complete'] for s in samples.values()),'Join before complete base samples')
            sql,params=core.sample_count_sql(expected,{t:samples[t]['selected_ids'] for t in ordered})
            require(op['sql']==sql and op['parameters']==params and i>0 and q['operations'][i-1]['kind']=='statement_limit','Sample join SQL/IDs/predicates changed');joins.append(op)
        else:raise ValueError('Unregistered SQL operation')
    require(q['operations'][0]['kind']=='savepoint' and len(joins)<=1,'Query savepoint/join sequence changed')
    if done:
        require(len(joins)==1 and joins[0]['status']=='PASS' and q['operations'][-1]['kind']=='release'
                and all(op['status']=='PASS' and not op['cleanup'] for op in q['operations']),'Completed query has failed/cleanup operation')
        count=independent_sample_count(expected,samples);require(type(q['sample_cardinality']) is int and count==q['sample_cardinality']
            and joins[0]['response']==[count] and (q['status']=='COMPLETE_ZERO')==(count==0),'Independent sampled join count/zero status differs')
        value=independent_estimate(count,{t:metadata[t]['rows'] for t in ordered},{t:len(samples[t]['rows']) for t in ordered})
        require(q['raw_prediction']==dict(numerator=str(value.numerator),denominator=str(value.denominator)),'Independent Fraction prediction differs')
    else:
        require(q['raw_prediction'] is None and q['sample_cardinality'] is None,'Uncompleted query must be null, never zero')
        require(type(q.get('error_type')) is str and bool(q['error_type']),'Missing failure reason')
        require(q.get('sqlstate') is None or type(q['sqlstate']) is str and len(q['sqlstate'])==5,'Invalid SQLSTATE')
        if q['status']=='STATEMENT_TIMEOUT':require(q['sqlstate']=='57014' and any(op['status']=='ERROR' for op in q['operations']),'Unsupported statement timeout')
        if q['status']=='QUERY_WALL_BUDGET':require(elapsed>=30 or q['deadline_cancelled'],'Unsupported timeout status')
        if q['status']=='ID_ATTEMPT_BUDGET':require(any(v==100000 for v in attempts.values()),'ID budget stop before exhaustion')
        if q['status']=='SQL_ROUNDTRIP_BUDGET':require(len(q['operations'])-q['cleanup_sql_roundtrips']==1997,'SQL stop before exhaustion')
    return prediction_row(q)


def validate_collection(p,r,root):
    require(r['binding']==p['binding'] and r['scope']==core.SCOPE and r['source_boundary']==p['source_boundary'],'Collection binding/scope changed')
    require(type(r['client_pid']) is int and r['client_pid']>0 and r['resource_monitor_stopped'] is True
            and r['owned_connection_rolled_back_and_closed'] is True and r['resource_monitor_errors']==[]
            and r['server_started_or_stopped'] is False and r['new_model_calls']==0 and type(r['new_model_calls']) is int
            and r['raw_csv_or_truth_read'] is False and r['scalar_predicate_counts_used'] is False,'Collection control/scientific boundary incomplete')
    d=r['database_identity'];require(d['database']=='deepdb_job' and d['server_version_num']=='110005' and d['address']=='127.0.0.1'
        and d['port']==55432 and Path(d['data_directory']).resolve()==(Path(root)/'data/postgresql/cluster').resolve()
        and Path(d['image']).resolve()==(Path(root)/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve()
        and type(d['backend_pid']) is int and d['backend_pid']>0 and d['read_only']=='on' and d['isolation']=='repeatable read'
        and type(d['postmaster_start']) is str and bool(d['postmaster_start']),'Wrong historical DB/owned backend identity')
    require(set(r['before'])==set(r['after'])==set(r['metadata'])==set(core.EXPECTED_ROWS),'Missing six-table current projection/metadata')
    for t,N in core.EXPECTED_ROWS.items():
        m=r['metadata'][t];require(set(m)=={'rows','distinct_ids','min_id','max_id'} and all(type(v) is int for v in m.values())
            and m['rows']==m['distinct_ids']==N and m['min_id']<=m['max_id'] and N<=m['max_id']-m['min_id']+1,'Live unconditional ID metadata invalid')
        for side in ('before','after'):
            s=r[side][t];require(set(s)=={'schema','projection','binary_copy','seconds'} and s['projection']==core.projection(p['contract'],t),'Query projection incomplete')
            nonnegative(s['seconds']);b=s['binary_copy'];require(set(b)=={'bytes','sha256'} and type(b['bytes']) is int and 0<b['bytes']<=core.POLICY['max_snapshot_bytes_per_table']
                and type(b['sha256']) is str and len(b['sha256'])==64 and all(c in '0123456789abcdef' for c in b['sha256']),'Invalid full streaming COPY receipt')
            a=s['schema'];cols=dict(a['columns']);require(a['table']==t and type(a['oid']) is int and a['oid']>0
                and type(a['relfilenode']) is int and a['relfilenode']>0 and a['relkind']=='r' and a['inherits'] is False
                and a['primary_key']==['id'] and a['valid_primary_key'] is True and len(cols)==len(a['columns'])
                and all(cols.get(c) in {20,21,23} for c in s['projection']),'Invalid current integral PK/schema identity')
        strip=lambda x:{k:v for k,v in x.items() if k!='seconds'}
        require(strip(r['before'][t])==strip(r['after'][t]),'Before/after full query projection changed')
    ops=r['common_operations'];require(type(ops) is list and len(ops)==17,'Common preparation/control roundtrip set incomplete')
    expected=['SET LOCAL lock_timeout = 5000','LOCK TABLE '+', '.join('public."'+t+'"' for t in p['contract']['tables'])+' IN SHARE MODE NOWAIT',
              'SET LOCAL search_path = pg_catalog, public',"SET LOCAL work_mem = '16MB'","SET LOCAL temp_file_limit = '1GB'",'SET LOCAL statement_timeout = 600000',
              'SET LOCAL max_parallel_workers_per_gather = 0',"SET LOCAL application_name = 'deepdb_local_job70_srs'"]
    require([o['sql'] for o in ops[:8]]==expected and ops[8]['sql']==core.IDENTITY_SQL,'No six-table locks before first SELECT/exact identity query')
    require(ops[8]['response']==[d[k] for k in ('database','server_version_num','address','port','data_directory','backend_pid','read_only','isolation','postmaster_start')],
            'Historical identity SQL result differs from backend receipt')
    require([o['sql'] for o in ops[9:15]]==[core.population_sql(t) for t in p['contract']['tables']]
            and ops[15]['sql']=='SET LOCAL statement_timeout = 5000'
            and ops[16]['sql']=='SET LOCAL statement_timeout = 600000','Unconditional live metadata/preparation/online SQL set changed')
    for i,t in enumerate(p['contract']['tables']):
        m=r['metadata'][t];require(ops[9+i]['response']==[m['rows'],m['distinct_ids'],m['min_id'],m['max_id']],'Metadata SQL receipt differs')
    for op in ops:
        nonnegative(op['seconds']);require(op['parameters'] is None,'Unexpected common metadata parameters')
    startup=r['startup_resources'];measurements=[startup]+r['resources'];require(len(measurements)>=2,'Missing startup/final resource checks')
    for i,s in enumerate(measurements):
        required={'available_memory_bytes','process_rss_bytes','free_disk_bytes'}
        require(set(s)==required if i==0 else set(s)==required|{'seconds'},'Resource record fields changed')
        require(all(type(s[k]) is int and s[k]>=0 for k in required),'Invalid resource measurement')
        require(s['available_memory_bytes']>=core.POLICY['startup_available_memory_bytes' if i==0 else 'running_available_memory_bytes']
            and s['process_rss_bytes']<=core.POLICY['max_client_rss_bytes'] and s['free_disk_bytes']>=core.POLICY['min_free_disk_bytes'],'Resource budget violation')
        if i:nonnegative(s['seconds'])
    require(set(r['timings'])=={'before_projection_seconds','live_population_metadata_seconds','all_online_queries_and_leaf_checkpoint_seconds','after_projection_seconds'},'Preparation/online timing categories incomplete')
    for v in r['timings'].values():nonnegative(v)
    nonnegative(r['seconds']);require(sum(r['timings'].values())<=r['seconds']+1e-5,'Timing components exceed collection wall')


def validate_bundle(directory,root=ROOT,prepublication=False):
    directory=Path(directory).resolve();root=Path(root).resolve();p=read(directory/'plan.json')
    core.validate_plan(p,root)
    require(directory==root/core.BASE/'runs'/p['binding'][:20],'Incorrect scientific namespace')
    a=read(directory/'approval.json');core.validate_approval(a,p,root/a['plan_file']['path'],root)
    r=read(directory/'collection.json');validate_collection(p,r,root);pred=[];cancelled=[]
    for q in p['contract']['queries']:
        path=directory/'queries'/('query_%02d.json'%q['query_no']);s=read(path.with_suffix('.seal.json'))
        require(s==dict(binding=p['binding'],query_no=q['query_no'],artifact=artifact(path,root)),'Query physical seal changed')
        row=read(path);pred.append(validate_query(row,q,r['metadata'],p['contract'],p['binding'],r['client_pid']))
        if row['deadline_cancelled']:cancelled.append(q['query_no'])
    require(r['cancelled_queries']==cancelled,'Owned deadline cancellation receipt changed')
    value=dict(binding=p['binding'],scope=dict(core.SCOPE),queries=pred)
    require(read(directory/'predictions.json')==value,'Predictions omit/change query terminals')
    complete=sum(q['status'] in COMPLETE for q in pred);zeros=sum(q['status']=='COMPLETE_ZERO' for q in pred)
    result=dict(status='PASS_LOCAL_JOB70_SRS_TERMINAL_RECEIPTS_WITH_GAPS' if complete<70 else 'PASS_LOCAL_JOB70_SRS_TERMINAL_RECEIPTS',
                binding=p['binding'],scope=dict(core.SCOPE),queries=70,completed_queries=complete,incomplete_queries=70-complete,
                raw_zero_queries=zeros,complete_finite_70_query_summary_allowed=complete==70 and zeros==0,
                positive_truth_zero_q_error='INFINITY',incomplete_queries_must_not_be_silently_excluded=True,
                collection=artifact(directory/'collection.json',root),predictions=artifact(directory/'predictions.json',root),
                source_boundary=p['source_boundary'],current_database_values_reverified_by_offline_audit=False,
                common_sql_roundtrips=65,common_sql_roundtrips_breakdown=dict(recorded_setup_identity_metadata_reset=17,schema_checks=36,streaming_copy=12),
                online_query_sql_roundtrips=sum(q['sql_roundtrips'] for q in pred),
                all_online_query_wall_seconds=sum(q['wall_seconds'] for q in pred),common_preparation_timings=r['timings'])
    if not prepublication:
        execution=read(directory/'execution.json')
        timing_names={'admission_physical_validation_seconds','collection_and_checkpoint_seconds','fresh_postflight_physical_validation_seconds',
                      'offline_math_prepublication_validation_seconds','measured_client_wall_seconds_before_final_records'}
        require(set(execution)==timing_names|{'binding','client_pid','final_record_and_seal_io_in_external_command_wall_only','root_external_command_wall_required_for_end_to_end_latency',
                                            'postflight_resources','postflight_resource_errors','postflight_resource_monitor_stopped'}
            and execution['binding']==p['binding'] and execution['client_pid']==r['client_pid']
            and execution['final_record_and_seal_io_in_external_command_wall_only'] is True
            and execution['root_external_command_wall_required_for_end_to_end_latency'] is True,'Controller/end-to-end timing ledger incomplete')
        require(execution['postflight_resource_monitor_stopped'] is True and execution['postflight_resource_errors']==[]
                and type(execution['postflight_resources']) is list and bool(execution['postflight_resources']),'Postflight resource monitoring incomplete')
        for s in execution['postflight_resources']:
            require(set(s)=={'available_memory_bytes','process_rss_bytes','free_disk_bytes','seconds'} and all(type(s[k]) is int for k in s if k!='seconds')
                and s['available_memory_bytes']>=core.POLICY['running_available_memory_bytes'] and 0<=s['process_rss_bytes']<=core.POLICY['max_client_rss_bytes']
                and s['free_disk_bytes']>=core.POLICY['min_free_disk_bytes'],'Postflight resource budget violation')
            nonnegative(s['seconds'])
        for key in timing_names:nonnegative(execution[key])
        require(sum(execution[k] for k in timing_names if k!='measured_client_wall_seconds_before_final_records')<=execution['measured_client_wall_seconds_before_final_records']+1e-5
            and execution['collection_and_checkpoint_seconds']>=r['seconds'],'Controller wall ledger omits collection cost')
        require(read(directory/'verification.json')==result,'Verification differs from independent reconstruction')
        require(read(directory/'lifecycle.json')==dict(status='PASS',binding=p['binding'],client_pid=r['client_pid'],verification_sha256=core.digest(directory/'verification.json')),'Whole attempt not PASS')
    else:
        require(read(directory/'lifecycle.json')==dict(status='RUNNING',binding=p['binding'],client_pid=r['client_pid']),'Producer transaction not RUNNING')
    return result


def verify(directory,root=ROOT):
    """No writes, launches, DB imports, repairs, or scientific recomputation."""
    directory=Path(directory).resolve();root=Path(root).resolve();seal=read(directory/'final_seal.json')
    require(set(seal)=={'schema','binding','files','self_sha256'} and seal['schema']=='job70-srs-final-v1'
        and seal['self_sha256']==core.object_hash({k:v for k,v in seal.items() if k!='self_sha256'}),'Final seal invalid')
    require(set(seal['files'])==set(FILES),'Missing/extra required artifacts')
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    require(actual==set(FILES)|{'final_seal.json'},'Incomplete/extra physical namespace')
    for name in FILES:require(seal['files'][name]==artifact(directory/name,root),'Current physical artifact changed: '+name)
    result=validate_bundle(directory,root);require(result['binding']==seal['binding'],'Final binding changed')
    return dict(status='PASS_READ_ONLY_LOCAL_JOB70_SRS_WITH_GAPS' if result['incomplete_queries'] else 'PASS_READ_ONLY_LOCAL_JOB70_SRS',
                verification=result,verification_artifact=artifact(directory/'verification.json',root),
                final_seal=artifact(directory/'final_seal.json',root),artifacts=list(seal['files'].values()),
                dependencies=read(directory/'plan.json')['dependencies'],predictions=read(directory/'predictions.json'),
                controller_timing=read(directory/'execution.json'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);a=p.parse_args();print(json.dumps(verify(a.run)))


if __name__=='__main__':main()
