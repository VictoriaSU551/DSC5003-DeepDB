"""Source-bound LOCAL IBJS SQL bridge; actual run needs exact ROOT approval."""
import sys
sys.dont_write_bytecode=True
import argparse
import importlib
import json
import os
import random
from pathlib import Path
import time

import full_job_sampling_ibjs_audit as audit
from full_job_sampling_ibjs_audit import require,read,digest,artifact
ROOT=audit.ROOT
BASE=audit.BASE


class OutputBudget:
    def __init__(self,directory,cap=audit.LIMITS['max_total_output_bytes'],per_query=audit.LIMITS['max_query_output_bytes']):
        self.directory=Path(directory);self.cap=cap;self.per_query=per_query
        self.sizes={p:p.stat().st_size for p in self.directory.rglob('*') if p.is_file()};self.total=sum(self.sizes.values())
    def admit(self,path,size,query=False):
        require(size<=(self.per_query if query else self.cap),'Per-file output cap exceeded')
        require(self.total+size<=self.cap,'Total output cap exceeded')
    def committed(self,path,size):
        self.total+=size-self.sizes.get(path,0);self.sizes[path]=size


def atomic(path,value,sink=None,query=False,check=lambda:None):
    path=Path(path);temporary=path.with_name(path.name+'.tmp');n=0
    with temporary.open('xb') as f:
        pending=bytearray()
        for part in json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).iterencode(value):
            pending.extend(part.encode())
            if len(pending)>=65536:
                check();n+=len(pending)
                if sink is not None:sink.admit(path,n,query)
                f.write(pending);pending.clear()
        check();pending.extend(b'\n');n+=len(pending)
        if sink is not None:sink.admit(path,n,query)
        f.write(pending)
        f.flush();os.fsync(f.fileno())
    os.replace(str(temporary),str(path))
    if sink is not None:sink.committed(path,n)


def taint(directory,binding,error):
    # A failed RUNNING/PASS write may have its original .tmp already present.
    # Keep that evidence and use a distinct, one-shot emergency record.
    path=Path(directory)/'lifecycle.json';temporary=path.with_name('lifecycle.tainted.tmp')
    with temporary.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(dict(status='TAINTED',binding=binding,client_pid=os.getpid(),error=repr(error)),f,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(str(temporary),str(path))


def _helpers():
    audit.prior_pins();modules=[]
    for name in ('full_job_sampling_ibjs','full_job_sampling_run','full_scalar_oracle_run'):
        m=importlib.import_module(name);require(Path(m.__file__).resolve()==ROOT/'code'/(name+'.py'),'Wrong actual helper module');modules.append(m)
    return modules


def build_plan(attempt='initial',root=ROOT):return audit.make_plan(attempt,audit.dependencies(root),root)
def approval_template(p,path,root=ROOT):return dict(status='PENDING_ROOT_REVIEW_NOT_AUTHORIZED',binding=p['binding'],plan_file=artifact(path,root),exclusive_window=True,root_review_reference='')


def probe_statement(kind,added,values,query,columns):
    require(kind in {'count','kth'} and added in query['tables'] and 0<len(values)<=1000,'One bounded added base required')
    arity=2 if kind=='count' else 3;require(all(len(v)==arity and type(v[0]) is int and v[0]==i for i,v in enumerate(values)),'Exact ordered request indexes required')
    casts='(%s::integer,%s::bigint)' if kind=='count' else '(%s::integer,%s::bigint,%s::bigint)'
    prefix='WITH v(i,k'+('' if kind=='count' else ',o')+') AS (VALUES '+','.join([casts]*len(values))+') '
    join='id' if added=='title' else 'movie_id';where=['a."'+join+'" = v.k'];params=[v for row in values for v in row]
    for p in next(x['conditions'] for x in query['predicates'] if x['table']==added):
        where.append('a."'+p['column']+'" '+p['operator']+' %s');params.append(p['value'])
    relation=' FROM public."'+added+'" a WHERE '+' AND '.join(where)
    if kind=='count':sql=prefix+'SELECT v.i,(SELECT COUNT(*)'+relation+') FROM v ORDER BY v.i'
    else:
        projected=','.join('a."'+c+'"' for c in columns)
        sql=prefix+'SELECT v.i,'+','.join('p."'+c+'"' for c in columns)+' FROM v CROSS JOIN LATERAL (SELECT '+projected+relation+' ORDER BY a."id" OFFSET v.o LIMIT 1) p ORDER BY v.i'
    return sql,params


def enumerate_states(core,query,bases,probe,trace,check=lambda:None):
    """Only orchestration differs: expose partial RNG draws; frozen extend owns math."""
    states={(t,):s for t,s in bases.items()};whole=tuple(sorted(query['tables']));budget=core.LookupBudget()
    trace.update(attempts=[],skipped_edges=[],scope=dict(core.SCOPE));error=None;status='COMPLETE'
    try:
        for i,(subset,added,target) in enumerate(core.star_graph(query['tables'])[1]):
            check()
            if subset not in states:continue
            if target in states and len(states[target].rows)*10>=1000:trace['skipped_edges'].append(i);continue
            step=dict(edge_index=i,replaces_existing=target in states,rng_draws=[]);trace['attempts'].append(step)
            seed=int(core.value_hash(dict(method=core.VARIANT,sql=query['sql'],query_no=query['query_no'],seed=1,input=subset,added=added)),16)
            class LoggedRandom:
                def __init__(self):self.rng=random.Random(seed)
                def randrange(self,stop):
                    value=self.rng.randrange(stop);step['rng_draws'].append([stop,value]);return value
            probe.edge_index=i
            states[target]=core.extend(query,states[subset],added,probe,budget,step,rng=LoggedRandom(),check=check)
    except core.LookupStopped:status='STOP_AFTER_COMPLETE' if whole in states else 'LOOKUP_BUDGET_NULL'
    except Exception as e:status='ERROR_NULL';error=e
    require(budget.held==0 and budget.spent<=100000,'Unclosed logical budget')
    final=states.get(whole);prediction=None if status in {'ERROR_NULL','LOOKUP_BUDGET_NULL'} or final is None else final.cardinality
    if status=='COMPLETE' and prediction==0:status='ZERO_SAMPLE'
    trace.update(status=status,budget_spent=budget.spent,error_type=None if error is None else type(error).__name__)
    return dict(status=status,prediction=prediction,states=states,budget_spent=budget.spent,error=error)


class SQLProbe:
    def __init__(self,io,query,contract,metadata,events):
        self.io=io;self.query=query;self.contract=contract;self.metadata=metadata;self.events=events;self.edge_index=None
    def dispatch(self,kind,added,values):
        cols=audit.projection(self.contract,added);sql,params=probe_statement(kind,added,values,self.query,cols)
        event=dict(edge_index=self.edge_index,kind=kind,added=added,values=[list(v) for v in values],io_start=len(self.io.operations),io_end=None,status='RUNNING')
        self.events.append(event)
        try:
            response=self.io.data('ibjs_'+kind+'/'+added,sql,params,fetch='all')
            require(type(response) is list and len(response)==len(values) and all(type(r[0]) is int and r[0]==i for i,r in enumerate(response)),'Incomplete/unaligned probe response')
            if kind=='count':
                require(all(len(r)==2 and type(r[1]) is int and 0<=r[1]<=self.metadata[added]['rows'] for r in response),'Invalid fanout count')
                value=[r[1] for r in response]
            else:
                require(all(len(r)==len(cols)+1 and all(v is None or type(v) is int and -(2**63)<=v<2**63 for v in r[1:]) for r in response),'Incomplete integral kth projection')
                value=[dict(zip(cols,r[1:])) for r in response]
            event['status']='PASS';return value
        except BaseException as error:event.update(status='ERROR',error_type=type(error).__name__);raise
        finally:event['io_end']=len(self.io.operations)
    def count_many(self,bags,added,query):
        require(query==self.query,'Probe query changed');return self.dispatch('count',added,[(i,next(iter(b.values()))['movie_id'] if added=='title' else b['title']['id']) for i,b in enumerate(bags)])
    def kth_many(self,requests,added,query):
        require(query==self.query,'Probe query changed');return self.dispatch('kth',added,[(i,next(iter(b.values()))['movie_id'] if added=='title' else b['title']['id'],offset) for i,(b,offset) in enumerate(requests)])


def run_query(query,metadata,contract,cursor,monitor,binding,clock=time.perf_counter,helpers=None):
    core,srsrun=(_helpers()[:2] if helpers is None else helpers);srs=srsrun.core
    budget=srs.Budget(clock=clock,max_sql=1997);ops=[];samples={};base_events=[];events=[];algorithm={}
    io=srsrun.QueryIO(cursor,monitor,budget,ops,clock);active=dict(query_no=query['query_no'],deadline=budget.started+30,cancelled=False)
    monitor.active=active;opened=False
    q=dict(query_no=query['query_no'],sql=query['sql'],binding=binding,scope=dict(audit.SCOPE),config=dict(audit.CONFIG),client_pid=os.getpid(),
        table_samples=samples,base_events=base_events,probe_events=events,algorithm=algorithm,operations=ops,status='RUNNING',raw_prediction=None,error_type=None,sqlstate=None)
    try:
        io.one('savepoint','SAVEPOINT sampling_query');opened=True;bases={}
        for t in query['tables']:
            trace={};samples[t]=trace;cols=srs.projection(contract,t)
            def fetch(ids,t=t,cols=cols,trace=trace):
                e=dict(table=t,batch=len(trace['raw_sample']['batches'])-1,io_start=len(ops),io_end=None,status='RUNNING');base_events.append(e)
                try:
                    rows=io.data('base_lookup/'+t,srs.lookup_sql(t,cols),[ids],fetch='all')
                    trace['raw_sample']['batches'][-1]['operation_index']=len(ops)-1;e['status']='PASS';return [list(r) for r in rows]
                except BaseException as error:e.update(status='ERROR',error_type=type(error).__name__);raise
                finally:e['io_end']=len(ops)
            bases[t]=core.draw_base(query,t,metadata[t],cols,fetch,budget,trace)
        outcome=enumerate_states(core,query,bases,SQLProbe(io,query,contract,metadata,events),algorithm,check=lambda:(monitor.check(),budget.check()))
        if outcome['error'] is not None:raise outcome['error']
        io.one('release','RELEASE SAVEPOINT sampling_query');opened=False;budget.check()
        require(not active['cancelled'],'QUERY_WALL_BUDGET')
        q.update(status=outcome['status'],raw_prediction=None if outcome['prediction'] is None else core.rational(outcome['prediction']))
    except Exception as error:
        monitor.check()
        if isinstance(error,srs.SamplingStopped):status=str(error)
        elif active['cancelled']:status='QUERY_WALL_BUDGET'
        elif getattr(error,'pgcode',None)=='57014':status='STATEMENT_TIMEOUT'
        else:status='QUERY_ERROR'
        q.update(status=status,raw_prediction=None,error_type=type(error).__name__,sqlstate=getattr(error,'pgcode',None))
    finally:
        monitor.active=None
        if opened:
            io.one('rollback','ROLLBACK TO SAVEPOINT sampling_query',cleanup=True)
            io.one('cleanup_limit','SET LOCAL statement_timeout = 5000',cleanup=True)
            io.one('release','RELEASE SAVEPOINT sampling_query',cleanup=True)
        elapsed=clock()-budget.started
        if q['status'] in audit.COMPLETE and elapsed>=30:q.update(status='QUERY_WALL_BUDGET',raw_prediction=None,error_type='SamplingStopped',sqlstate=None)
        q.update(wall_seconds=elapsed,id_attempts={t:budget.attempts.get(t,0) for t in samples},sql_roundtrips=len(ops),cleanup_sql_roundtrips=sum(op['cleanup'] for op in ops),
            deadline_cancelled=active['cancelled'],charged_logical_lookups=algorithm.get('budget_spent',0),budget_includes_all_sampling_rng_sql_math_and_controls=True)
    return q


def collect(plan,directory,monitor,root=ROOT,sink=None):
    core,srsrun,h=_helpers();srs=core.frozen_srs();contract=plan['contract'];common=[];started=time.perf_counter();connection=h.connect()
    monitor.connection=connection;produced=None
    try:
        connection.set_session(isolation_level='REPEATABLE READ',readonly=True,autocommit=False)
        with connection.cursor() as raw:
            cursor=h.GuardedCursor(raw,monitor.check)
            def execute(sql,params=None,fetch=None):
                tick=time.perf_counter();cursor.execute(sql,params)
                v=cursor.fetchone() if fetch=='one' else cursor.fetchall() if fetch=='all' else None
                result=None if v is None else [list(r) for r in v] if fetch=='all' else list(v)
                common.append(dict(sql=sql,parameters=params,response=result,seconds=time.perf_counter()-tick));return v
            execute('SET LOCAL lock_timeout = 5000')
            execute('LOCK TABLE '+', '.join('public."'+t+'"' for t in contract['tables'])+' IN SHARE MODE NOWAIT')
            for sql in ('SET LOCAL search_path = pg_catalog, public',"SET LOCAL work_mem = '16MB'","SET LOCAL temp_file_limit = '1GB'",'SET LOCAL statement_timeout = 600000',
                        'SET LOCAL max_parallel_workers_per_gather = 0',"SET LOCAL application_name = 'deepdb_local_job70_ibjs'"):execute(sql)
            r=execute(srs.IDENTITY_SQL,fetch='one')
            require(r[:4]==('deepdb_job','110005','127.0.0.1',55432) and Path(r[4]).resolve()==(Path(root)/'data/postgresql/cluster').resolve()
                and type(r[5]) is int and r[5]>0 and r[6:8]==('on','repeatable read'),'Unexpected database/RR/read-only identity')
            image=h.backend_image(r[5]);require(Path(image)==(Path(root)/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve(),'Wrong backend executable')
            identity=dict(zip(('database','server_version_num','address','port','data_directory','backend_pid','read_only','isolation','postmaster_start'),r));identity['image']=image
            indexes_before=[list(r) for r in execute(audit.INDEX_SQL,[contract['tables']],fetch='all')];audit.validate_indexes(indexes_before)
            before={};after={};metadata={};timings={}
            def snapshot(destination):
                for t in contract['tables']:
                    tick=time.perf_counter();schema=h.schema_record(cursor,contract,t)
                    require(all(oid in {20,21,23} for c,oid in schema['columns'] if c in srs.projection(contract,t)),'Integral PostgreSQL projection required')
                    stream=h.HashSink(srs.POLICY['max_snapshot_bytes_per_table'],monitor.check)
                    cursor.copy_expert(h.copy_statement(contract,t),stream)
                    destination[t]=dict(schema=schema,projection=srs.projection(contract,t),binary_copy=stream.record(),seconds=time.perf_counter()-tick)
            tick=time.perf_counter();snapshot(before);timings['before_projection_seconds']=time.perf_counter()-tick;tick=time.perf_counter()
            for t in contract['tables']:
                row=execute(srs.population_sql(t),fetch='one')
                require(len(row)==4 and all(type(v) is int for v in row) and row[0]==row[1]==audit.POPULATION[t] and row[2]<=row[3] and row[0]<=row[3]-row[2]+1,'Live unique non-NULL ID/count/min/max gate failed')
                metadata[t]=dict(zip(('rows','distinct_ids','min_id','max_id'),row))
            timings['live_population_metadata_seconds']=time.perf_counter()-tick
            execute('SET LOCAL statement_timeout = 5000');tick=time.perf_counter()
            for q in contract['queries']:
                monitor.check();leaf=run_query(q,metadata,contract,cursor,monitor,plan['binding'],helpers=(core,srsrun))
                path=directory/'queries'/('query_%02d.json'%q['query_no']);atomic(path,leaf,sink,query=True,check=monitor.check)
                atomic(path.with_suffix('.seal.json'),dict(binding=plan['binding'],query_no=q['query_no'],artifact=artifact(path,root)),sink,check=monitor.check)
            timings['all_online_queries_and_leaf_checkpoint_seconds']=time.perf_counter()-tick
            execute('SET LOCAL statement_timeout = 600000');tick=time.perf_counter();snapshot(after);timings['after_projection_seconds']=time.perf_counter()-tick
            indexes_after=[list(r) for r in execute(audit.INDEX_SQL,[contract['tables']],fetch='all')];audit.validate_indexes(indexes_after)
            strip=lambda d:{t:{k:v for k,v in r.items() if k!='seconds'} for t,r in d.items()}
            require(strip(before)==strip(after) and indexes_before==indexes_after,'Before/after complete projection/index identity changed')
            monitor.check();produced=dict(binding=plan['binding'],scope=dict(audit.SCOPE),source_boundary=plan['source_boundary'],client_pid=os.getpid(),database_identity=identity,
                before=before,after=after,indexes_before=indexes_before,indexes_after=indexes_after,metadata=metadata,common_operations=common,timings=timings,seconds=time.perf_counter()-started,
                server_started_or_stopped=False,new_model_calls=0,raw_csv_or_truth_read=False,scalar_predicate_counts_used=False,
                owned_connection_rolled_back_and_closed=False,cancelled_queries=list(monitor.cancelled_queries))
    finally:
        try:connection.rollback()
        finally:
            try:connection.close()
            finally:monitor.connection=None
        if produced is not None:produced['owned_connection_rolled_back_and_closed']=True
    return produced


def execute(plan_path,approval_path,root=ROOT):
    entered=time.perf_counter();root=Path(root).resolve();plan_path=Path(plan_path).resolve();p=read(plan_path)
    binding=p.get('binding');require(type(binding) is str and len(binding)==64 and all(c in '0123456789abcdef' for c in binding),'Invalid namespace binding')
    directory=root/BASE/'runs'/binding[:20];require(not directory.exists(),'Prior attempts cannot be rerun, resumed or adopted')
    require((root/BASE/'plans').resolve() in plan_path.parents,'Dedicated plan path required')
    core,srsrun,h=_helpers();monitor=srsrun.LiveMonitor(h,None,root);monitor.started=entered
    startup=h.resources(root);h.validate_resources(startup,startup=True)
    require(monitor.poll(),'Initial native resource gate failed');monitor.start()
    def record_monitor(stopped):
        return dict(binding=binding,client_pid=os.getpid(),startup_resources=startup,resources=list(monitor.samples),errors=list(monitor.errors),
            cancelled_queries=list(monitor.cancelled_queries),stopped=stopped,started_before_physical_preflight=True,seconds=time.perf_counter()-monitor.started)
    try:
        audit.validate_plan(p,root);a=read(approval_path);audit.approval(a,p,plan_path,root);monitor.check();admission=time.perf_counter()-entered
        directory.parent.mkdir(parents=True,exist_ok=True)
        with srsrun.exclusive(root/BASE/'controller.lock'):
            directory.mkdir(exist_ok=False);(directory/'queries').mkdir();sink=OutputBudget(directory)
            def write(name,value):atomic(directory/name,value,sink,check=monitor.check)
            try:
                write('lifecycle.json',dict(status='RUNNING',binding=binding,client_pid=os.getpid()));write('plan.json',p);write('approval.json',a)
                tick=time.perf_counter();receipt=collect(p,directory,monitor,root,sink);write('collection.json',receipt);collection=time.perf_counter()-tick
                tick=time.perf_counter();audit.validate_plan(p,root);postflight=time.perf_counter()-tick;monitor.check()
                predictions=dict(binding=binding,scope=dict(audit.SCOPE),queries=[audit.prediction_row(read(directory/'queries'/('query_%02d.json'%i))) for i in range(70)])
                write('predictions.json',predictions);require(monitor.poll(),'Final live resource gate failed');write('monitor.json',record_monitor(False))
                tick=time.perf_counter();verification=audit.validate_bundle(directory,root,publishing=True);math_seconds=time.perf_counter()-tick;monitor.check()
                # No SQL remains; this continuous monitor stayed active through
                # both current physical closures and all independent math.
                require(monitor.poll(),'Last resource gate failed');monitor.finish()
                atomic(directory/'monitor.json',record_monitor(True),sink)
                atomic(directory/'execution.json',dict(binding=binding,client_pid=os.getpid(),admission_physical_validation_seconds=admission,
                    collection_and_checkpoint_seconds=collection,fresh_postflight_physical_validation_seconds=postflight,offline_math_prepublication_validation_seconds=math_seconds,
                    measured_client_wall_seconds_before_final_records=time.perf_counter()-entered,final_record_and_seal_io_in_external_command_wall_only=True,
                    root_external_command_wall_required_for_end_to_end_latency=True),sink)
                atomic(directory/'verification.json',verification,sink)
                atomic(directory/'lifecycle.json',dict(status='PASS',binding=binding,client_pid=os.getpid(),verification_sha256=digest(directory/'verification.json')),sink)
                body=dict(schema='job70-ibjs-final-v1',binding=binding,files={n:artifact(directory/n,root) for n in audit.expected_files()})
                atomic(directory/'final_seal.json',dict(body,self_sha256=audit.value_hash(body)),sink);return verification
            except BaseException as error:
                # Preserve all provisional leaves/temp bytes. Never resume or
                # silently fall back to a successful subset after interruption.
                taint(directory,binding,error);raise
    finally:
        if not monitor.stop.is_set():monitor.finish()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','run']);p.add_argument('--plan',required=True);p.add_argument('--approval');p.add_argument('--attempt',default='initial');a=p.parse_args()
    if a.action=='plan':
        target=Path(a.plan).resolve();require((ROOT/BASE/'plans').resolve() in target.parents and not target.exists(),'New dedicated plan path required')
        value=build_plan(a.attempt);target.parent.mkdir(parents=True,exist_ok=True);atomic(target,value)
        print(json.dumps(dict(status='PLAN_ONLY_NOT_EXECUTED',binding=value['binding'],approval_template=approval_template(value,target))))
    else:
        require(a.approval is not None,'Exact ROOT approval required');entered=time.perf_counter();result=execute(a.plan,a.approval)
        print(json.dumps(dict(verification=result,total_command_wall_seconds=time.perf_counter()-entered,root_external_process_wall_still_required=True)))
if __name__=='__main__':main()
