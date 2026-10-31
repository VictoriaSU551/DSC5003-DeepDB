"""Local JOB70 entity-SRS core. No truth, database, model or lifecycle access."""
import sys
sys.dont_write_bytecode=True
from fractions import Fraction
import hashlib
import importlib
import json
from pathlib import Path
import random
import time
import os
import ast
import re

ROOT=Path(__file__).resolve().parents[1]
QUERY_FILE='code/benchmarks/job-light/sql/job_light_queries.sql'
QUERY_SHA='e61da91710ce62d3669be70a8ded2499c6de1d759fcfac9a954b939465e76fdb'
VARIANT='LOCAL_JOB70_SRS_WOR_N1000'
IDENTITY_SQL="SELECT current_database(),current_setting('server_version_num'),inet_server_addr()::text,inet_server_port(),current_setting('data_directory'),pg_backend_pid(),current_setting('transaction_read_only'),current_setting('transaction_isolation'),pg_postmaster_start_time()::text"
EXPECTED_ROWS=dict(title=2528312,movie_info_idx=1380035,movie_info=14835720,cast_info=36244344,movie_keyword=4523930,movie_companies=2609129)
PINS={'code/full_scalar_oracle.py':'a804301149e370eabf1055cdcb94d8157502032ab37a81e33a1b2396225964df',
      'code/full_scalar_oracle_run.py':'513132368b6f2123896be2305b0d4377750ef03113b6dc1fef3bed2d1111f1e7',
      'code/full_scalar_oracle_audit.py':'15912c8e98a620553bc861e3b6dbe1821227f6cf8779bf1ab5eba6bb225f0307',
      'docs/FULL_SCALAR_ORACLE_PROTOCOL.md':'0e8c032eb6b8883ebda0ebdb9a956b41c8ee79f933da22ffee890671573141cc'}
CONFIG=dict(samples_per_table=1000,seed=1,batch_size=128,max_id_attempts_per_table=100000,max_sql_roundtrips=2000,max_query_seconds=30.,statement_timeout_ms=5000)
SCOPE=dict(method=VARIANT,author_method_configuration_identified=False,author_sampling_reproduction_complete=False,
           full_paper_reproduction_complete=False,ibjs_implemented=False,truth_used_for_prediction=False,
           original_csv_current_database_full_value_identity_claimed=False)
BASE='output/full/sampling/job70'
SOURCES=('code/full_job_sampling.py','code/full_job_sampling_run.py','code/full_job_sampling_audit.py',
         'code/tests/test_full_job_sampling.py','code/tests/test_full_job_sampling_run.py',
         'code/tests/test_full_job_sampling_audit.py','docs/FULL_JOB_SAMPLING_PROTOCOL.md')
INPUTS={'data/manifest.json':'ae6a5cef66340bae23325722f0f0d29ee616850851b99b6989ab1d5b6a6f3e13',
        'data/postgresql/imports.json':'b5a2167bd4419aa38f6a0d48dfab7d1b75aada932949cd748e9226e9c8b79f1d',
        'code/full_postgres.py':'5eb6db79110be8e257bb3a8e300eb2b804dc5dc5907432a121cf9206fbe99292'}
GIB=1024**3
POLICY=dict(startup_available_memory_bytes=5*GIB,running_available_memory_bytes=GIB,
            max_client_rss_bytes=512*1024**2,min_free_disk_bytes=8*GIB,work_mem_mb=16,
            temp_file_limit_mb=1024,lock_timeout_ms=5000,preparation_statement_timeout_ms=120000,
            max_parallel_workers_per_gather=0,max_snapshot_bytes_per_table=2*GIB,
            memory_poll_seconds=.1,max_total_seconds=5400)
KERNEL32=Path('C:/Windows/System32/kernel32.dll')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()


def read(path):
    def unique(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def artifact(path,root=ROOT,allow_empty=False):
    p=Path(path).resolve();r=Path(root).resolve()
    require(r in p.parents or p==KERNEL32.resolve(),'Physical containment failure')
    require(p.is_file() and (allow_empty or p.stat().st_size>0),'Missing/empty artifact: '+str(p))
    try:name=p.relative_to(r).as_posix()
    except ValueError:name=str(p)
    return dict(path=name,bytes=p.stat().st_size,sha256=digest(p))


def inventory(paths,root=ROOT,allow_empty=False):
    output={}
    for p in sorted(set(Path(p).resolve() for p in paths),key=str):
        d=artifact(p,root,allow_empty);require(d['path'] not in output,'Duplicate physical path');output[d['path']]=d
    require(bool(output),'Empty inventory');return output


def dependencies(root=ROOT):
    """Only files: invoke the pinned filesystem inventory function, not its module.

    Compiling this single reviewed FunctionDef avoids importing its DB/controller
    module in the offline auditor. No function-level edits or hash caches.
    """
    root=Path(root).resolve()
    for rel,sha in dict(PINS,**INPUTS).items():require(digest(root/rel)==sha,'Prior physical pin changed: '+rel)
    source=(root/'code/full_scalar_oracle_run.py').read_text(encoding='utf-8')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='runtime_paths')
    namespace=dict(Path=Path,sys=sys,os=os,require=require,KERNEL32=KERNEL32)
    tree=ast.Module(body=[node],type_ignores=[]);exec(compile(tree,'<pinned filesystem-only runtime_paths>','exec'),namespace)
    raw=read(root/'data/manifest.json');imports=read(root/'data/postgresql/imports.json')
    require(set(imports)==set(EXPECTED_ROWS),'All six import receipts required')
    files={f['path']:f for f in raw['files']}
    for t,n in EXPECTED_ROWS.items():
        require(imports[t]['rows']==n and imports[t]['sha256']==files['imdb/'+t+'.csv']['sha256'],'Import lineage mismatch')
    return dict(sources=inventory([root/x for x in (*SOURCES,*PINS,*INPUTS,QUERY_FILE)],root),
                runtime=inventory(namespace['runtime_paths'](root),root,allow_empty=True),
                python_version=sys.version,runtime_inventory_function_sha256=hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest(),
                raw_csv_current_bytes_rehashed=False,database_current_all_column_identity_proven=False)


def projection(contract,table):
    cols={'id'} if table=='title' else {'id','movie_id'}
    for p in contract['predicates']:
        if p['table']==table:cols.update(x['column'] for x in p['conditions'])
    return sorted(cols)


def population_sql(table):
    require(table in EXPECTED_ROWS,'Unknown population')
    return 'SELECT COUNT(*), COUNT(DISTINCT "id"), MIN("id"), MAX("id") FROM public."'+table+'"'


def lookup_sql(table,cols):
    require(table in EXPECTED_ROWS and cols==sorted(set(cols)) and 'id' in cols,'Canonical projection required')
    return 'SELECT '+', '.join('"'+c+'"' for c in cols)+' FROM public."'+table+'" WHERE "id" = ANY(%s)'


def make_plan(attempt,dependency,root=ROOT):
    require(type(attempt) is str and re.fullmatch('[a-z0-9_]{1,32}',attempt) is not None,'Safe explicit attempt required')
    body=dict(schema='job70-srs-plan-v1',attempt=attempt,scope=dict(SCOPE),config=dict(CONFIG),policy=dict(POLICY),
              contract=workload(),dependencies=dependency,
              connection=dict(host='127.0.0.1',port=55432,database='deepdb_job',server_version_num=110005,
                              data_directory=str((Path(root)/'data/postgresql/cluster').resolve())),
              source_boundary='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY',
              no_cross_attempt_adoption=True,uncompleted_prediction=None,positive_truth_zero_q_error='INFINITY')
    return dict(body,binding=object_hash(body))


def validate_plan(p,root=ROOT):
    require(p==make_plan(p.get('attempt'),dependencies(root),root),'Plan differs from complete current physical dependencies/configuration')


def validate_approval(a,p,path,root=ROOT):
    require(set(a)=={'status','binding','plan_file','exclusive_window','root_review_reference'}
            and a['status']=='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_SRS_RUN' and a['binding']==p['binding']
            and a['plan_file']==artifact(path,root) and a['exclusive_window'] is True
            and type(a['root_review_reference']) is str and bool(a['root_review_reference'].strip()),
            'Exact source-bound ROOT review and exclusive resource window required')


def require(ok,message):
    if not ok:raise ValueError(message)


def integer(n,name='integer'):
    require(type(n) is int and n>=0,'Nonnegative integer required: '+name);return n


def object_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def pinned_module(name):
    relative='code/'+name+'.py';require(relative in PINS,'Unregistered helper')
    require(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==PINS[relative],'Literal-pinned helper source changed: '+relative)
    module=importlib.import_module(name);require(Path(module.__file__).resolve()==ROOT/relative,'Wrong helper import path');return module


def parse_query(sql,index):return pinned_module('full_scalar_oracle').parse_query(sql,index)


def workload(path=None):
    path=ROOT/QUERY_FILE if path is None else Path(path);raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==QUERY_SHA,'Registered workload bytes changed')
    lines=[q.strip() for q in raw.decode('utf-8').splitlines() if q.strip()];require(len(lines)==70,'Exactly70 queries required')
    parser=pinned_module('full_scalar_oracle');contract=parser.contract_from_queries([parser.parse_query(q,i) for i,q in enumerate(lines)])
    require(contract['tables']==sorted(EXPECTED_ROWS),'All six registered tables required')
    return dict(contract,variant=VARIANT)


def seed_for(query_no,table):
    integer(query_no);require(table in EXPECTED_ROWS,'Registered sampling table required')
    return int(object_hash(dict(method=VARIANT,sql_sha256=QUERY_SHA,seed=CONFIG['seed'],query_no=query_no,table=table)),16)


class SamplingStopped(ValueError):pass


class Budget:
    def __init__(self,clock=time.perf_counter,max_attempts=100000,max_sql=2000,max_seconds=30.):
        self.clock=clock;self.started=clock();self.max_attempts=max_attempts;self.max_sql=max_sql;self.max_seconds=max_seconds;self.attempts={};self.sql_calls=0
    def check(self):
        if self.clock()-self.started>=self.max_seconds:raise SamplingStopped('QUERY_WALL_BUDGET')
    def attempt(self,table):
        self.check()
        if self.attempts.get(table,0)>=self.max_attempts:raise SamplingStopped('ID_ATTEMPT_BUDGET')
        self.attempts[table]=self.attempts.get(table,0)+1
    def sql(self):
        self.check()
        if self.sql_calls>=self.max_sql:raise SamplingStopped('SQL_ROUNDTRIP_BUDGET')
        self.sql_calls+=1


def draw_table(query_no,table,population,projection,fetch,budget,trace,n=1000,rng=None):
    N=integer(population['rows']);lo=population['min_id'];hi=population['max_id'];integer(n)
    require(N>0 and n>0 and type(lo) is int and type(hi) is int and lo<=hi and N<=hi-lo+1,'Nonempty unique integral ID population required')
    require(type(projection) is list and len(projection)==len(set(projection)) and 'id' in projection,'Complete unique projection required')
    k=min(n,N);rng=random.Random(seed_for(query_no,table)) if rng is None else rng;seen=set();selected=[];rows=[];idcol=projection.index('id')
    trace.update(table=table,population=population,projection=projection,seed=str(seed_for(query_no,table)),target=k,batches=[],selected_ids=selected,rows=rows,complete=False)
    while len(selected)<k:
        attempted=[];ids=[];batch=dict(attempted_ids=attempted,ids=ids,rows=None);trace['batches'].append(batch)
        while len(ids)<min(CONFIG['batch_size'],k-len(selected)):
            budget.attempt(table);candidate=rng.randint(lo,hi);attempted.append(candidate)
            if candidate in seen:continue
            seen.add(candidate);ids.append(candidate)
        budget.check();actual=fetch(ids);budget.check()
        require(type(actual) is list and all(type(r) is list and len(r)==len(projection)
            and all(v is None or type(v) is int for v in r) and type(r[idcol]) is int for r in actual),'Exact integral/NULL projected rows required')
        mapping={r[idcol]:r for r in actual};require(len(mapping)==len(actual) and set(mapping)<=set(ids),'Unexpected or duplicate lookup IDs')
        batch['rows']=actual
        for key in ids:
            if key in mapping:selected.append(key);rows.append(mapping[key])
    trace['complete']=True;return trace


def rational(value):
    require(isinstance(value,Fraction) and value>=0,'Nonnegative exact Fraction required')
    return dict(numerator=str(value.numerator),denominator=str(value.denominator))


def estimate(sample_cardinality,population,selected):
    integer(sample_cardinality);require(set(population)==set(selected) and bool(population),'Complete sample cardinalities required')
    result=Fraction(sample_cardinality)
    for t,N in population.items():
        integer(N);integer(selected[t]);require(0<selected[t]<=N,'Positive feasible selected sample size required');result*=Fraction(N,selected[t])
    return result


def sample_count_sql(query,ids):
    require(set(ids)==set(query['tables']),'Complete sampled relations required')
    conditions={p['table']:p['conditions'] for p in query['predicates']};ctes=[];names={};parameters=[]
    for i,t in enumerate(query['tables']):
        require(t in EXPECTED_ROWS and type(ids[t]) is list and ids[t] and len(ids[t])==len(set(ids[t]))
            and all(type(v) is int for v in ids[t]),'Unique nonempty sampled entity IDs required')
        name='s'+str(i);names[t]=name;parameters.append(ids[t]);terms=['"id" = ANY(%s)']
        for term in conditions[t]:terms.append('"'+term['column']+'" '+term['operator']+' %s');parameters.append(term['value'])
        select='"id"' if t=='title' else '"movie_id", COUNT(*)::numeric AS n'
        ctes.append(name+' AS (SELECT '+select+' FROM public."'+t+'" WHERE '+' AND '.join(terms)+('' if t=='title' else ' GROUP BY "movie_id"')+')')
    title=names['title'];children=[names[t] for t in query['tables'] if t!='title'];expr=' * '.join(x+'.n' for x in children)
    statement='WITH '+', '.join(ctes)+' SELECT COALESCE(SUM('+expr+'),0) FROM '+title+' '+ ' '.join('JOIN '+c+' ON '+title+'."id"='+c+'."movie_id"' for c in children)
    return statement,parameters
