"""Explicitly ROOT-approved single-controller SRS. No server lifecycle API."""
import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import threading
import time

import full_job_sampling as core
from full_job_sampling import require,read,digest,artifact,dependencies,population_sql

ROOT=core.ROOT
BASE=core.BASE


def atomic(path,value):
    p=Path(path);temporary=p.with_name(p.name+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(str(temporary),str(p))


def build_plan(attempt='initial',root=ROOT):return core.make_plan(attempt,dependencies(root),root)
def validate_plan(plan,root=ROOT):return core.validate_plan(plan,root)
def validate_approval(a,p,path,root=ROOT):return core.validate_approval(a,p,path,root)


def approval_template(p,path,root=ROOT):
    return dict(status='PENDING_ROOT_REVIEW_NOT_AUTHORIZED',binding=p['binding'],plan_file=artifact(path,root),
                exclusive_window=True,root_review_reference='')


@contextmanager
def exclusive(path):
    p=Path(path);token=(str(os.getpid())+' '+os.urandom(24).hex()).encode()
    # Never unlink a pre-existing controller's lock, even on failed acquisition.
    with p.open('xb') as f:f.write(token);f.flush();os.fsync(f.fileno())
    try:yield
    finally:
        require(p.is_file() and p.read_bytes()==token,'Controller lock identity changed; will not remove it')
        p.unlink()


class LiveMonitor:
    """Permanent resource stop; query deadlines cancel only this connection."""
    def __init__(self,helper,connection,root,clock=time.perf_counter):
        self.helper=helper;self.connection=connection;self.root=root;self.clock=clock;self.started=clock()
        self.errors=[];self.samples=[];self.stop=threading.Event();self.active=None;self.thread=None;self.cancelled_queries=[]
    def check(self):
        require(not self.errors and not self.stop.is_set(),'Permanent resource/controller stop: '+repr(self.errors))
        require(self.clock()-self.started<core.POLICY['max_total_seconds'],'Maximum controller time exceeded')
    def poll(self):
        try:
            self.check();s=self.helper.resources(self.root);self.helper.validate_resources(s)
            self.samples.append(dict(s,seconds=self.clock()-self.started))
        except BaseException as e:
            self.errors.append(repr(e))
            if self.connection is not None:self.connection.cancel()
            return False
        a=self.active
        if a is not None and self.clock()>=a['deadline'] and not a['cancelled']:
            a['cancelled']=True;self.cancelled_queries.append(a['query_no']);self.connection.cancel()
        return True
    def loop(self):
        while not self.stop.wait(core.POLICY['memory_poll_seconds']):
            try:
                if not self.poll():return
            except BaseException as e:self.errors.append('Owned cancellation failed: '+repr(e));return
    def start(self):self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def finish(self):
        self.stop.set()
        if self.thread is not None:self.thread.join(timeout=3)
        require((self.thread is None or not self.thread.is_alive()) and not self.errors,'Monitor failed or did not stop: '+repr(self.errors))


class QueryIO:
    def __init__(self,cursor,monitor,budget,operations,clock=time.perf_counter):
        self.cursor=cursor;self.monitor=monitor;self.budget=budget;self.operations=operations;self.clock=clock
    def one(self,kind,sql,parameters=None,fetch=None,cleanup=False):
        self.monitor.check()
        if not cleanup:self.budget.sql()
        else:require(len(self.operations)<core.CONFIG['max_sql_roundtrips'],'Cleanup exceeds reserved SQL calls')
        start=self.clock();op=dict(kind=kind,sql=sql,parameters=parameters,started_seconds=start-self.budget.started,
                                  seconds=0.,status='RUNNING',response=None,cleanup=cleanup);self.operations.append(op)
        try:
            self.cursor.execute(sql,parameters)
            result=self.cursor.fetchone() if fetch=='one' else self.cursor.fetchall() if fetch=='all' else None
            self.monitor.check()
            if not cleanup:self.budget.check()
            op['response']=None if result is None else [list(r) for r in result] if fetch=='all' else list(result)
            op['status']='PASS';return result
        except BaseException as e:op.update(status='ERROR',error=type(e).__name__);raise
        finally:op['seconds']=self.clock()-start
    def data(self,kind,sql,parameters=None,fetch=None):
        self.budget.check();remaining=self.budget.max_seconds-(self.clock()-self.budget.started)
        timeout=max(1,min(core.CONFIG['statement_timeout_ms'],int(remaining*1000)))
        self.one('statement_limit','SET LOCAL statement_timeout = '+str(timeout))
        return self.one(kind,sql,parameters,fetch)


def run_query(query,metadata,contract,cursor,monitor,binding,clock=time.perf_counter):
    # Three calls are reserved for cleanup after any exhausted online budget.
    budget=core.Budget(clock=clock,max_sql=core.CONFIG['max_sql_roundtrips']-3)
    operations=[];samples={};io=QueryIO(cursor,monitor,budget,operations,clock)
    qno=query['query_no'];active=dict(query_no=qno,deadline=budget.started+budget.max_seconds,cancelled=False)
    monitor.active=active;opened=False
    result=dict(query_no=qno,sql=query['sql'],binding=binding,scope=dict(core.SCOPE),table_samples=samples,
                operations=operations,status='RUNNING',sample_cardinality=None,raw_prediction=None,
                client_pid=os.getpid(),config=dict(core.CONFIG))
    try:
        io.one('savepoint','SAVEPOINT sampling_query');opened=True
        for t in query['tables']:
            trace={};samples[t]=trace;cols=core.projection(contract,t)
            def fetch(ids,t=t,cols=cols,trace=trace):
                rows=io.data('base_lookup/'+t,core.lookup_sql(t,cols),[ids],fetch='all')
                trace['batches'][-1]['operation_index']=len(operations)-1
                return [list(r) for r in rows]
            core.draw_table(qno,t,metadata[t],cols,fetch,budget,trace)
        sql,params=core.sample_count_sql(query,{t:samples[t]['selected_ids'] for t in query['tables']})
        row=io.data('sample_join',sql,params,fetch='one')
        require(row is not None and len(row)==1 and row[0] is not None and row[0]==int(row[0]) and row[0]>=0,'Exact sampled join count required')
        cardinality=int(row[0]);operations[-1]['response']=[cardinality]
        io.one('release','RELEASE SAVEPOINT sampling_query');opened=False;budget.check()
        require(not active['cancelled'],'QUERY_WALL_BUDGET')
        result.update(status='COMPLETE_ZERO' if cardinality==0 else 'COMPLETE',sample_cardinality=cardinality,
                      raw_prediction=core.rational(core.estimate(cardinality,{t:metadata[t]['rows'] for t in samples},
                                                               {t:len(s['selected_ids']) for t,s in samples.items()})))
    except Exception as e:
        monitor.check() # Resource violations taint the entire attempt, not a null leaf.
        if isinstance(e,core.SamplingStopped):reason=str(e)
        elif active['cancelled']:reason='QUERY_WALL_BUDGET'
        elif getattr(e,'pgcode',None)=='57014':reason='STATEMENT_TIMEOUT'
        else:reason='QUERY_ERROR'
        result.update(status=reason,error_type=type(e).__name__,sqlstate=getattr(e,'pgcode',None),sample_cardinality=None,raw_prediction=None)
    finally:
        monitor.active=None
        if opened:
            # Rollback clears the transaction's failed-statement state before SET.
            io.one('rollback','ROLLBACK TO SAVEPOINT sampling_query',cleanup=True)
            io.one('cleanup_limit','SET LOCAL statement_timeout = 5000',cleanup=True)
            io.one('release','RELEASE SAVEPOINT sampling_query',cleanup=True)
        elapsed=clock()-budget.started
        if result['status'] in {'COMPLETE','COMPLETE_ZERO'} and elapsed>=budget.max_seconds:
            result.update(status='QUERY_WALL_BUDGET',error_type='SamplingStopped',sqlstate=None,sample_cardinality=None,raw_prediction=None)
        result.update(wall_seconds=elapsed,id_attempts={t:budget.attempts.get(t,0) for t in samples},
                      sql_roundtrips=len(operations),cleanup_sql_roundtrips=sum(op['cleanup'] for op in operations),
                      deadline_cancelled=active['cancelled'],budget_includes_rng_rejection_base_lookup_and_join=True)
    return result


def collect(plan,directory,root=ROOT):
    """The only actual database entry. Caller has current approval and unique lock."""
    h=core.pinned_module('full_scalar_oracle_run');root=Path(root).resolve();contract=plan['contract']
    startup=h.resources(root);h.validate_resources(startup,startup=True)
    connection=h.connect();monitor=LiveMonitor(h,connection,root);started=time.perf_counter();produced=None
    common=[]
    try:
        monitor.start();monitor.check()
        connection.set_session(isolation_level='REPEATABLE READ',readonly=True,autocommit=False)
        with connection.cursor() as raw:
            cursor=h.GuardedCursor(raw,monitor.check)
            def execute(sql,params=None,fetch=None):
                tick=time.perf_counter();cursor.execute(sql,params)
                value=cursor.fetchone() if fetch=='one' else cursor.fetchall() if fetch=='all' else None
                common.append(dict(sql=sql,parameters=params,seconds=time.perf_counter()-tick,response=list(value) if fetch=='one' else value))
                return value
            execute('SET LOCAL lock_timeout = 5000')
            execute('LOCK TABLE '+', '.join('public."'+t+'"' for t in contract['tables'])+' IN SHARE MODE NOWAIT')
            for sql in ("SET LOCAL search_path = pg_catalog, public","SET LOCAL work_mem = '16MB'","SET LOCAL temp_file_limit = '1GB'",
                        'SET LOCAL statement_timeout = 120000','SET LOCAL max_parallel_workers_per_gather = 0',
                        "SET LOCAL application_name = 'deepdb_local_job70_srs'"):
                execute(sql)
            r=execute(core.IDENTITY_SQL,fetch='one')
            require(r[:4]==('deepdb_job','110005','127.0.0.1',55432) and Path(r[4]).resolve()==(root/'data/postgresql/cluster').resolve()
                    and r[6:8]==('on','repeatable read'),'Unexpected database/RR/read-only identity')
            image=h.backend_image(r[5]);require(Path(image)==(root/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve(),'Wrong backend executable')
            identity=dict(database=r[0],server_version_num=r[1],address=r[2],port=r[3],data_directory=r[4],backend_pid=r[5],
                          read_only=r[6],isolation=r[7],postmaster_start=r[8],image=image)
            before={};after={};metadata={};timings={}
            def snapshot(destination):
                for t in contract['tables']:
                    tick=time.perf_counter();schema=h.schema_record(cursor,contract,t)
                    require(all(oid in {20,21,23} for col,oid in schema['columns'] if col in core.projection(contract,t)),'Integral PostgreSQL column types required')
                    sink=h.HashSink(core.POLICY['max_snapshot_bytes_per_table'],monitor.check)
                    cursor.copy_expert(h.copy_statement(contract,t),sink)
                    destination[t]=dict(schema=schema,projection=core.projection(contract,t),binary_copy=sink.record(),seconds=time.perf_counter()-tick)
            tick=time.perf_counter();snapshot(before);timings['before_projection_seconds']=time.perf_counter()-tick
            tick=time.perf_counter()
            for t in contract['tables']:
                row=execute(population_sql(t),fetch='one')
                require(len(row)==4 and all(type(v) is int for v in row) and row[0]==row[1]==core.EXPECTED_ROWS[t]
                        and row[2]<=row[3] and row[0]<=row[3]-row[2]+1,'Live unique non-NULL ID/count/min/max gate failed')
                metadata[t]=dict(rows=row[0],distinct_ids=row[1],min_id=row[2],max_id=row[3])
            timings['live_population_metadata_seconds']=time.perf_counter()-tick
            tick=time.perf_counter()
            for q in contract['queries']:
                monitor.check();leaf=run_query(q,metadata,contract,cursor,monitor,plan['binding'])
                path=directory/'queries'/('query_%02d.json'%q['query_no']);atomic(path,leaf)
                atomic(path.with_suffix('.seal.json'),dict(binding=plan['binding'],query_no=q['query_no'],artifact=artifact(path,root)))
            timings['all_online_queries_and_leaf_checkpoint_seconds']=time.perf_counter()-tick
            execute('SET LOCAL statement_timeout = 120000')
            tick=time.perf_counter();snapshot(after);timings['after_projection_seconds']=time.perf_counter()-tick
            strip=lambda d:{t:{k:v for k,v in item.items() if k!='seconds'} for t,item in d.items()}
            require(strip(before)==strip(after),'Before/after query-projection physical identity mismatch')
            monitor.check();final=h.resources(root);h.validate_resources(final);monitor.samples.append(dict(final,seconds=time.perf_counter()-monitor.started))
            produced=dict(binding=plan['binding'],scope=dict(core.SCOPE),database_identity=identity,before=before,after=after,
                          metadata=metadata,common_operations=common,timings=timings,seconds=time.perf_counter()-started,
                          client_pid=os.getpid(),startup_resources=startup,resources=monitor.samples,resource_monitor_errors=monitor.errors,
                          resource_monitor_stopped=False,owned_connection_rolled_back_and_closed=False,
                          cancelled_queries=monitor.cancelled_queries,server_started_or_stopped=False,new_model_calls=0,
                          raw_csv_or_truth_read=False,scalar_predicate_counts_used=False,source_boundary=plan['source_boundary'])
    finally:
        try:monitor.finish()
        finally:
            try:connection.rollback()
            finally:connection.close()
        if produced is not None:produced.update(resource_monitor_stopped=True,owned_connection_rolled_back_and_closed=True)
    return produced


def execute(plan_path,approval_path,root=ROOT):
    entered=time.perf_counter();root=Path(root).resolve();plan_path=Path(plan_path).resolve();p=read(plan_path);a=read(approval_path)
    validate_plan(p,root);validate_approval(a,p,plan_path,root)
    admission_seconds=time.perf_counter()-entered
    directory=root/BASE/'runs'/p['binding'][:20];directory.parent.mkdir(parents=True,exist_ok=True)
    require(not directory.exists(),'Prior attempts cannot be rerun, resumed or adopted')
    with exclusive(root/BASE/'controller.lock'):
        directory.mkdir(exist_ok=False);(directory/'queries').mkdir()
        try:
            atomic(directory/'lifecycle.json',dict(status='RUNNING',binding=p['binding'],client_pid=os.getpid()))
            atomic(directory/'plan.json',p);atomic(directory/'approval.json',a)
            tick=time.perf_counter();receipt=collect(p,directory,root);atomic(directory/'collection.json',receipt)
            collection_seconds=time.perf_counter()-tick
            # The connection is already closed. Keep the same native live guard
            # during physical postflight/math, without a non-owned cancel target.
            post=LiveMonitor(core.pinned_module('full_scalar_oracle_run'),None,root)
            try:
                require(post.poll(),'Postflight resource gate failed');post.start()
                tick=time.perf_counter();validate_plan(p,root);postflight_seconds=time.perf_counter()-tick;post.check()
                import full_job_sampling_audit as audit
                predictions=dict(binding=p['binding'],scope=dict(core.SCOPE),
                    queries=[audit.prediction_row(read(directory/'queries'/('query_%02d.json'%i))) for i in range(70)])
                atomic(directory/'predictions.json',predictions);post.check()
                tick=time.perf_counter();verification=audit.validate_bundle(directory,root,prepublication=True)
                precheck_seconds=time.perf_counter()-tick;post.check()
            finally:post.finish()
            atomic(directory/'execution.json',dict(binding=p['binding'],client_pid=os.getpid(),admission_physical_validation_seconds=admission_seconds,
                collection_and_checkpoint_seconds=collection_seconds,fresh_postflight_physical_validation_seconds=postflight_seconds,
                offline_math_prepublication_validation_seconds=precheck_seconds,
                measured_client_wall_seconds_before_final_records=time.perf_counter()-entered,
                postflight_resources=post.samples,postflight_resource_errors=post.errors,postflight_resource_monitor_stopped=True,
                final_record_and_seal_io_in_external_command_wall_only=True,
                root_external_command_wall_required_for_end_to_end_latency=True))
            atomic(directory/'verification.json',verification)
            atomic(directory/'lifecycle.json',dict(status='PASS',binding=p['binding'],client_pid=os.getpid(),verification_sha256=digest(directory/'verification.json')))
            body=dict(schema='job70-srs-final-v1',binding=p['binding'],files={n:artifact(directory/n,root) for n in audit.FILES})
            atomic(directory/'final_seal.json',dict(body,self_sha256=core.object_hash(body)))
            return verification
        except BaseException as e:
            atomic(directory/'lifecycle.json',dict(status='TAINTED',binding=p['binding'],client_pid=os.getpid(),error=repr(e)));raise


def main():
    entered=time.perf_counter()
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','run']);p.add_argument('--plan',required=True)
    p.add_argument('--approval');p.add_argument('--attempt',default='initial');a=p.parse_args()
    if a.action=='plan':
        path=Path(a.plan).resolve();require((ROOT/BASE/'plans').resolve() in path.parents and not path.exists(),'New dedicated plan path required')
        value=build_plan(a.attempt);path.parent.mkdir(parents=True,exist_ok=True);atomic(path,value)
        print(json.dumps(dict(status='PLAN_ONLY_NOT_EXECUTED',binding=value['binding'],approval_template=approval_template(value,path))))
    else:
        require(a.approval is not None,'ROOT approval required');v=execute(a.plan,a.approval)
        print(json.dumps(dict(verification=v,total_command_wall_seconds=time.perf_counter()-entered,
                             root_external_process_wall_still_required=True)))


if __name__=='__main__':main()
