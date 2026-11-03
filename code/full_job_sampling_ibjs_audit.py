"""Stdlib-only independent IBJS receipt audit; no engine/DB/controller imports."""
import sys
sys.dont_write_bytecode=True
import argparse
import ast
from fractions import Fraction
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import re

ROOT=Path(__file__).resolve().parents[1]
BASE='output/full/sampling/job70_ibjs'
ANCHORS={'code/full_job_sampling_ibjs.py':'9a23d974dba56bb055b8abb2def1a10ac06efa1c529f4e2e59e943194f576a93',
 'code/tests/test_full_job_sampling_ibjs.py':'78a2c9c1eb3501221daff90c0a4b618bf94c8b80be5a9d68f173f76ab6932e03',
 'docs/FULL_JOB_IBJS_PROTOCOL.md':'d5c9e34c2465406dd9a85f56c9a69d999cbf4c667ec351379a3f39e609040aeb'}
OWN=('code/full_job_sampling_ibjs_run.py','code/full_job_sampling_ibjs_audit.py',
     'code/tests/test_full_job_sampling_ibjs_run.py','code/tests/test_full_job_sampling_ibjs_audit.py','docs/FULL_JOB_IBJS_RUNTIME.md')
VARIANT='LOCAL_JOB70_IBJS_SQL_N1000_B100K'
PURE_SCOPE=dict(method=VARIANT,author_reproduction_complete=False,full_paper_reproduction_complete=False,
    author_configuration_identified=False,adaptive_path_unbiasedness_claimed=False,live_driver_implemented=False,truth_or_scalar_selectivities_used=False)
SCOPE=dict(PURE_SCOPE,live_driver_implemented=True)
CONFIG=dict(n=1000,lookup_budget=100000,seed=1)
POPULATION=dict(title=2528312,movie_info_idx=1380035,movie_info=14835720,cast_info=36244344,movie_keyword=4523930,movie_companies=2609129)
LIMITS=dict(max_query_seconds=30.,statement_timeout_ms=5000,max_sql_roundtrips=2000,cleanup_reserve=3,
    max_id_attempts_per_table=100000,max_query_output_bytes=32*1024**2,max_total_output_bytes=1024**3,max_total_seconds=5400)
KERNEL32=Path('C:/Windows/System32/kernel32.dll')
COMPLETE={'COMPLETE','ZERO_SAMPLE','STOP_AFTER_COMPLETE'}
FAILURE={'QUERY_WALL_BUDGET','ID_ATTEMPT_BUDGET','SQL_ROUNDTRIP_BUDGET','STATEMENT_TIMEOUT','QUERY_ERROR','LOOKUP_BUDGET_NULL'}
INDEX_SQL="SELECT t.relname,x.relname,i.indisprimary,i.indisunique,i.indisvalid,i.indisready,i.indpred IS NULL,i.indexprs IS NULL,am.amname,a.attname,i.indnatts::integer FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class t ON t.oid=i.indrelid JOIN pg_catalog.pg_namespace ns ON ns.oid=t.relnamespace JOIN pg_catalog.pg_class x ON x.oid=i.indexrelid JOIN pg_catalog.pg_am am ON am.oid=x.relam JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid AND a.attnum=i.indkey[0] WHERE ns.nspname='public' AND t.relname=ANY(%s) ORDER BY t.relname,x.relname"


def require(ok,message):
    if not ok:raise ValueError(message)


def value_hash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
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
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def artifact(path,root=ROOT,allow_empty=False):
    p=Path(path).resolve();root=Path(root).resolve();require(root in p.parents or p==KERNEL32.resolve(),'External/aliased artifact')
    require(p.is_file() and (allow_empty or p.stat().st_size>0),'Missing/empty artifact')
    try:name=p.relative_to(root).as_posix()
    except ValueError:name=str(p)
    return dict(path=name,bytes=p.stat().st_size,sha256=digest(p))


def _constants(path,names,namespace=None):
    scope={} if namespace is None else dict(namespace)
    nodes=[n for n in ast.parse(Path(path).read_text()).body if isinstance(n,ast.Assign) and len(n.targets)==1
           and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names]
    require({n.targets[0].id for n in nodes}==set(names),'Missing source-bound declarative constants')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pinned declarative constants>','exec'),scope);return scope


def prior_pins():
    for p,sha in ANCHORS.items():require(digest(ROOT/p)==sha,'Frozen kernel anchor changed: '+p)
    c=_constants(ROOT/'code/full_job_sampling_ibjs.py',{'VARIANT','CONFIG','SCOPE','PINS'})
    expected={*('code/'+s+'.py' for s in ('full_job_sampling','full_job_sampling_run','full_job_sampling_audit','full_scalar_oracle','full_scalar_oracle_run','full_scalar_oracle_audit')),
              *('code/tests/test_full_job_sampling'+s+'.py' for s in ('','_run','_audit')),'docs/FULL_JOB_SAMPLING_PROTOCOL.md','docs/FULL_SCALAR_ORACLE_PROTOCOL.md'}
    require(c['VARIANT']==VARIANT and c['SCOPE']==PURE_SCOPE and c['CONFIG']==CONFIG and set(c['PINS'])==expected,'Frozen kernel/source set differs')
    for p,sha in c['PINS'].items():require(digest(ROOT/p)==sha,'Frozen prior pin changed: '+p)
    return dict(ANCHORS,**c['PINS'])


def _functions(path,names,scope):
    raw=Path(path).read_text();nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in names]
    require({n.name for n in nodes}==set(names),'Missing pinned pure/filesystem function')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<unmodified pinned FunctionDefs>','exec'),scope)
    return {n.name:hashlib.sha256(ast.get_source_segment(raw,n).encode()).hexdigest() for n in nodes}


def _srs_namespace():
    prior_pins();path=ROOT/'code/full_job_sampling.py'
    constants={'GIB','POLICY','CONFIG','EXPECTED_ROWS','INPUTS','PINS','SOURCES','QUERY_FILE','QUERY_SHA','IDENTITY_SQL'}
    return _constants(path,constants,dict(ROOT=ROOT,Path=Path,sys=sys,os=os,json=json,hashlib=hashlib,ast=ast,require=require,KERNEL32=KERNEL32))


def dependencies(root=ROOT):
    s=_srs_namespace();original=tuple(s['SOURCES']);s['SOURCES']=tuple(dict.fromkeys((*original,*ANCHORS,*OWN)))
    hashes=_functions(ROOT/'code/full_job_sampling.py',{'read','digest','artifact','inventory','dependencies'},s)
    result=s['dependencies'](root)
    expected=set(s['SOURCES'])|set(s['PINS'])|set(s['INPUTS'])|{s['QUERY_FILE']}
    require(set(result['sources'])==expected,'Incomplete explicit source required-set')
    return dict(result,inventory_adapter=dict(functions=hashes,globals_override={'SOURCES':list(s['SOURCES'])},algorithm_engine_imported=False))


def parse_query(sql,index):
    s=_srs_namespace();p=ROOT/'code/full_scalar_oracle.py';c=_constants(p,{'COLUMNS','VARIANT'})
    ns=dict(require=require,object_hash=value_hash,re=re,COLUMNS=c['COLUMNS'],VARIANT=c['VARIANT'])
    _functions(p,{'predicate','parse_query','contract_from_queries'},ns);return ns['parse_query'](sql,index)


def workload():
    s=_srs_namespace();raw=(ROOT/s['QUERY_FILE']).read_bytes();require(hashlib.sha256(raw).hexdigest()==s['QUERY_SHA'],'Pinned70 SQL changed')
    lines=[x.strip() for x in raw.decode().splitlines() if x.strip()];require(len(lines)==70,'Exactly70 SQL required')
    # Compile the pinned grammar once for this call, never import its module.
    p=ROOT/'code/full_scalar_oracle.py';ns=dict(require=require,object_hash=value_hash,re=re,**{k:v for k,v in _constants(p,{'COLUMNS','VARIANT'}).items() if k in {'COLUMNS','VARIANT'}})
    _functions(p,{'predicate','parse_query','contract_from_queries'},ns)
    result=ns['contract_from_queries']([ns['parse_query'](x,i) for i,x in enumerate(lines)])
    require(result['tables']==sorted(POPULATION),'Complete six-table workload required');return dict(result,variant=VARIANT)


def projection(contract,t):
    cols={'id'} if t=='title' else {'id','movie_id'}
    for p in contract['predicates']:
        if p['table']==t:cols.update(x['column'] for x in p['conditions'])
    return sorted(cols)


def expected_files():
    return tuple(['plan.json','approval.json','collection.json','predictions.json','monitor.json','execution.json','verification.json','lifecycle.json']+
                 [f'queries/query_{i:02d}{suffix}' for i in range(70) for suffix in ('.json','.seal.json')])


def make_plan(attempt,dependency,root=ROOT):
    require(type(attempt) is str and re.fullmatch('[a-z0-9_]{1,32}',attempt),'Safe explicit attempt required')
    s=_srs_namespace();body=dict(schema='job70-ibjs-plan-v1',attempt=attempt,scope=dict(SCOPE),pure_scope=dict(PURE_SCOPE),config=dict(CONFIG),limits=dict(LIMITS),
        policy=s['POLICY'],contract=workload(),dependencies=dependency,connection=dict(host='127.0.0.1',port=55432,database='deepdb_job',server_version_num=110005,
        data_directory=str((Path(root)/'data/postgresql/cluster').resolve())),no_cross_attempt_adoption=True,positive_truth_zero_q_error='INFINITY',
        source_boundary='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY')
    return dict(body,binding=value_hash(body))


def validate_plan(p,root=ROOT):require(p==make_plan(p.get('attempt'),dependencies(root),root),'Plan differs from complete current closure/configuration')
def approval(a,p,path,root=ROOT):
    require(set(a)=={'status','binding','plan_file','exclusive_window','root_review_reference'}
        and a['status']=='APPROVED_BY_ROOT_FOR_SINGLE_JOB70_IBJS_RUN' and a['binding']==p['binding']
        and a['plan_file']==artifact(path,root) and a['exclusive_window'] is True and type(a['root_review_reference']) is str
        and bool(a['root_review_reference'].strip()),'Exact ROOT approval and exclusive window required')


def validate_indexes(rows):
    require(type(rows) is list and len(rows)==11,'Six PK and five FK index records required');seen=set()
    for r in rows:
        require(type(r) is list and len(r)==11 and r[0] in POPULATION and all(type(v) is bool for v in r[2:8]),'Invalid catalog record')
        t,name,pk,unique,valid,ready,nonpartial,noexpr,am,key,natts=r
        require((t,name) not in seen and valid and ready and nonpartial and noexpr and am=='btree' and type(natts) is int and natts==1,'Invalid/duplicate index')
        expected=t+'_pkey' if pk else t+'_movie_id_idx'
        require(name==expected and unique is pk and key==('id' if pk else 'movie_id') and (pk or t!='title'),'Unexpected index identity/key')
        seen.add((t,name))
    require(seen=={(t,t+'_pkey') for t in POPULATION}|{(t,t+'_movie_id_idx') for t in POPULATION if t!='title'},'Missing required index')


def nonnegative(v):
    require(type(v) in (int,float) and math.isfinite(v) and v>=0,'Finite nonnegative measurement required');return v
def rational(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def accepts(query,t,row):
    for c in next(p['conditions'] for p in query['predicates'] if p['table']==t):
        a=row[c['column']];b=c['value']
        if a is None or not {'=':a==b,'!=':a!=b,'<':a<b,'>':a>b,'<=':a<=b,'>=':a>=b}[c['operator']]:return False
    return True
def projected(row,columns):
    require(type(row) is list and len(row)==len(columns) and all(v is None or type(v) is int and -(2**63)<=v<2**63 for v in row),'Incomplete/inexact integral projected row')
    value=dict(zip(columns,row));require(type(value['id']) is int,'NULL/noninteger entity ID');return value
def base_sql(t,cols):return 'SELECT '+', '.join('"'+c+'"' for c in cols)+' FROM public."'+t+'" WHERE "id" = ANY(%s)'
def population_sql(t):return 'SELECT COUNT(*), COUNT(DISTINCT "id"), MIN("id"), MAX("id") FROM public."'+t+'"'


def probe_sql(kind,t,values,q,cols):
    # Deliberately independent construction, never import the producer template.
    count=kind=='count';require(kind in {'count','kth'} and 0<len(values)<=1000,'Invalid probe shape')
    rows=['(%s::integer,%s::bigint)' if count else '(%s::integer,%s::bigint,%s::bigint)' for _ in values]
    start='WITH v(i,k'+('' if count else ',o')+') AS (VALUES '+','.join(rows)+') '
    predicates=['a."'+('id' if t=='title' else 'movie_id')+'" = v.k'];parameters=list(itertools.chain.from_iterable(values))
    for term in next(p['conditions'] for p in q['predicates'] if p['table']==t):
        predicates.append('a."'+term['column']+'" '+term['operator']+' %s');parameters.append(term['value'])
    body=' FROM public."'+t+'" a WHERE '+' AND '.join(predicates)
    if count:return start+'SELECT v.i,(SELECT COUNT(*)'+body+') FROM v ORDER BY v.i',parameters
    return start+'SELECT v.i,'+','.join('p."'+c+'"' for c in cols)+' FROM v CROSS JOIN LATERAL (SELECT '+','.join('a."'+c+'"' for c in cols)+body+' ORDER BY a."id" OFFSET v.o LIMIT 1) p ORDER BY v.i',parameters


def _segment(event,ops,kind,sql,params,linked):
    fields={'io_start','io_end','status'};require(fields<=set(event) and event['status'] in {'PASS','ERROR'},'Incomplete physical dispatch')
    a,b=event['io_start'],event['io_end'];require(type(a) is int and type(b) is int and 1<=a<=b<=len(ops) and b-a<=2,'Invalid physical dispatch range')
    require(not(set(range(a,b))&linked),'Repeated physical operation');linked.update(range(a,b))
    if event['status']=='PASS':require(b-a==2 and all(op['status']=='PASS' for op in ops[a:b]),'Successful dispatch lacks both SQL calls')
    else:require(type(event.get('error_type')) is str and event['error_type'],'Failed dispatch reason missing')
    if b>a:require(ops[a]['kind']=='statement_limit','Data call lacks preceding statement timeout')
    if b-a==2:require(ops[a+1]['kind']==kind and ops[a+1]['sql']==sql and ops[a+1]['parameters']==params,'Data SQL/predicates/positions changed')
    if b-a<2:return None
    return ops[a+1]['response'] if ops[a+1]['status']=='PASS' else None


def replay_bases(q,expected,metadata,contract,linked):
    samples=q['table_samples'];require(type(samples) is dict and sorted(samples)==expected['tables'][:len(samples)],'Base sample is not a registered table prefix')
    events=q['base_events'];require(type(events) is list,'Base dispatches missing');by={};order=[]
    for e in events:
        require(set(e)=={'table','batch','io_start','io_end','status'}|({'error_type'} if e['status']=='ERROR' else set()),'Extra base dispatch fields')
        key=(e['table'],e['batch']);require(key not in by,'Duplicate base dispatch');by[key]=e;order.append(key)
    expected_order=[];states={};attempts={}
    for t in expected['tables'][:len(samples)]:
        wrapper=samples[t];require(set(wrapper) in ({'raw_sample','base_rng_method'},{'raw_sample','base_rng_method','cardinality'}),'Base wrapper fields changed')
        s=wrapper['raw_sample'];cols=projection(contract,t);m=metadata[t];target=min(1000,m['rows'])
        seed=int(value_hash(dict(method='LOCAL_JOB70_SRS_WOR_N1000',sql_sha256='e61da91710ce62d3669be70a8ded2499c6de1d759fcfac9a954b939465e76fdb',seed=1,query_no=q['query_no'],table=t)),16)
        require(wrapper['base_rng_method']=='LOCAL_JOB70_SRS_WOR_N1000' and set(s)=={'table','population','projection','seed','target','batches','selected_ids','rows','complete'}
            and s['table']==t and s['population']==m and s['projection']==cols and s['seed']==str(seed) and type(s['target']) is int and s['target']==target and type(s['complete']) is bool,'Base metadata/seed/projection changed')
        rng=random.Random(seed);seen=set();chosen=[];rows=[];attempts[t]=0;require(type(s['batches']) is list,'Base batches missing')
        for j,batch in enumerate(s['batches']):
            require(set(batch) in ({'attempted_ids','ids','rows'},{'attempted_ids','ids','rows','operation_index'}),'Invalid base batch fields')
            require(len(chosen)<target,'Extra work after sample completion');capacity=min(128,target-len(chosen));ids=[]
            for candidate in batch['attempted_ids']:
                require(len(ids)<capacity and type(candidate) is int and candidate==rng.randint(m['min_id'],m['max_id']),'Base ID RNG/rejection changed');attempts[t]+=1
                require(attempts[t]<=100000,'ID attempts exceeded')
                if candidate not in seen:seen.add(candidate);ids.append(candidate)
            require(batch['ids']==ids,'Candidate duplicate rejection changed');e=by.get((t,j));actual=None
            if e is not None:
                require(len(ids)==capacity,'SQL lookup before full candidate batch');expected_order.append((t,j))
                actual=_segment(e,q['operations'],'base_lookup/'+t,base_sql(t,cols),[ids],linked)
                if 'operation_index' in batch:require(e['status']=='PASS' and batch['operation_index']==e['io_end']-1,'Base committed-operation link changed')
            if batch['rows'] is None:
                require(not s['complete'] and j==len(s['batches'])-1,'Uncommitted batch in complete sample');continue
            require(e is not None and e['status']=='PASS' and batch['rows']==actual and type(actual) is list and 'operation_index' in batch,'Sample row lacks physical lookup receipt')
            mapping={}
            for row in actual:
                d=projected(row,cols);key=d['id'];require(key in ids and key not in mapping,'Duplicate/unrequested base ID');mapping[key]=row
            for key in ids:
                if key in mapping:chosen.append(key);rows.append(mapping[key])
        require(s['selected_ids']==chosen and s['rows']==rows and s['complete']==(len(chosen)==target),'Base WOR selected row/order/completion changed')
        if s['complete']:
            bags=[{t:projected(row,cols)} for row in rows if accepts(expected,t,projected(row,cols))];cardinality=Fraction(m['rows']*len(bags),len(rows))
            require(wrapper.get('cardinality')==rational(cardinality),'Filtered base estimator changed');states[(t,)]=(bags,cardinality)
    require(order==expected_order,'Extra/unordered base dispatch');require(q['id_attempts']==attempts,'ID attempt cost changed');return states


def replay_algorithm(q,expected,contract,metadata,states,linked):
    a=q['algorithm'];events=q['probe_events'];require(type(events) is list,'Probe dispatch trace missing')
    if not a:require(not events,'Probes without enumeration');return None,0
    require(set(a)=={'attempts','skipped_edges','scope','status','budget_spent','error_type'} and a['scope']==PURE_SCOPE,'Pure kernel scope/trace changed')
    require(set(states)=={(t,) for t in expected['tables']},'Enumeration before complete base samples')
    observed={}
    for t,wrapper in q['table_samples'].items():
        for row in wrapper['raw_sample']['rows']:
            d=projected(row,projection(contract,t));observed[t,d['id']]=d
    tables=tuple(expected['tables']);subsets=sorted([x for k in range(1,len(tables)+1) for x in itertools.combinations(tables,k) if k==1 or 'title' in x],key=lambda s:(len(s),s))
    edges=[(s,t,tuple(sorted(s+(t,)))) for s in subsets for t in tables if t not in s and ('title' in s or t=='title')]
    require(len(subsets)<=20 and len(edges)<=36,'Registered graph bound exceeded');steps=a['attempts'];si=0;ei=0;skipped=[];spent=0;stopped=None
    def dispatch(kind,added,values,index):
        nonlocal ei
        require(ei<len(events),'Charged lookup lacks dispatch');e=events[ei];ei+=1
        require(set(e)=={'edge_index','kind','added','values','io_start','io_end','status'}|({'error_type'} if e['status']=='ERROR' else set())
            and type(e['edge_index']) is int and e['edge_index']==index and e['kind']==kind and e['added']==added and e['values']==values,'Probe requests/order/join keys changed')
        sql,params=probe_sql(kind,added,values,expected,projection(contract,added));response=_segment(e,q['operations'],'ibjs_'+kind+'/'+added,sql,params,linked)
        if e['status']=='PASS':require(type(response) is list and len(response)==len(values) and all(type(r) is list and r and type(r[0]) is int and r[0]==i for i,r in enumerate(response)),'Probe response positions incomplete')
        return e,response
    for index,(subset,added,target) in enumerate(edges):
        if a['status']=='ERROR_NULL' and si>=len(steps) and index not in a['skipped_edges']:stopped='ERROR';break
        if subset not in states:continue
        if target in states and len(states[target][0])*10>=1000:skipped.append(index);continue
        if si>=len(steps):stopped='ERROR';break
        s=steps[si];si+=1;bags,C=states[subset];m=len(bags);request=0 if not m else m+1000
        standard={'edge_index','replaces_existing','rng_draws','input_tables','added','input_sha256','input_cardinality','reservation_requested','reserved','charged_counts','charged_kth','refunded','fanouts','ranks','choices','status','population_zero_proven'}
        extra={'output_rows','output_cardinality'} if s['status'] in {'ZERO_INPUT','ZERO_FANOUT','COMPLETE'} else {'error_type'}
        require(set(s)==standard|extra and type(s['edge_index']) is int and s['edge_index']==index and type(s['replaces_existing']) is bool and s['replaces_existing']==(target in states)
            and tuple(s['input_tables'])==subset and s['added']==added and s['input_cardinality']==rational(C)
            and s['input_sha256']==value_hash(dict(tables=subset,rows=bags,cardinality=rational(C))) and s['reservation_requested']==request and s['population_zero_proven'] is False,'Expansion identity/input/fields changed')
        require(all(type(s[k]) is int and s[k]>=0 for k in ('reserved','charged_counts','charged_kth','refunded')),'Nonintegral lookup ledger')
        reserved=s['reserved'];cc=s['charged_counts'];ck=s['charged_kth'];refund=s['refunded'];require(reserved==cc+ck+refund,'Reservation refund does not conserve budget')
        if spent+request>100000:
            require(s['status']=='LOOKUP_BUDGET' and s['error_type']=='LookupStopped' and reserved==cc==ck==refund==0 and s['fanouts']==s['ranks']==s['choices']==s['rng_draws']==[],'Invalid logical budget stop');stopped='LOOKUP';break
        if m==0:
            require(s['status'] in {'ZERO_INPUT','ERROR'} and reserved==cc==ck==refund==0 and s['fanouts']==s['ranks']==s['choices']==s['rng_draws']==[],'Zero input charged/looked up')
            output=[];value=Fraction(0)
        elif reserved==0:
            require(s['status']=='ERROR' and cc==ck==refund==0 and s['fanouts']==s['ranks']==s['choices']==s['rng_draws']==[],'Unreserved expansion has work');stopped='ERROR';break
        else:
            require(reserved==request and cc==m,'Fanout logical dispatch charge changed');spent+=cc
            values=[[i,next(iter(b.values()))['movie_id'] if added=='title' else b['title']['id']] for i,b in enumerate(bags)]
            event,response=dispatch('count',added,values,index);fan=s['fanouts']
            if fan==[]:
                require(s['status']=='ERROR' and ck==0 and s['ranks']==s['choices']==s['rng_draws']==[],'Failed fanout returned estimate');stopped='ERROR';break
            require(event['status']=='PASS' and all(len(r)==2 and type(r[1]) is int and 0<=r[1]<=metadata[added]['rows'] for r in response) and fan==[r[1] for r in response] and len(fan)==m,'Fanout counts/physical response differ')
            total=sum(fan);k=min(1000,total);rng=random.Random(int(value_hash(dict(method=VARIANT,sql=expected['sql'],query_no=expected['query_no'],seed=1,input=subset,added=added)),16));chosen=set();ranks=[]
            require(len(s['rng_draws'])<=k,'Extra RNG work')
            for j,record in zip(range(total-k,total),s['rng_draws']):
                draw=rng.randrange(j+1);require(record==[j+1,draw],'Rank RNG stop/value changed');rank=j if draw in chosen else draw;chosen.add(rank);ranks.append(rank)
            if len(ranks)<k:
                require(s['status']=='ERROR' and s['ranks']==s['choices']==[] and ck==0,'Partial rank generation became output');stopped='ERROR';break
            require(s['ranks']==ranks,'Floyd weighted-rank WOR changed');choices=[]
            for rank in ranks:
                origin=0;offset=rank
                while origin<m and offset>=fan[origin]:offset-=fan[origin];origin+=1
                require(origin<m,'Rank outside concatenated fanout');choices.append([origin,offset])
            require(s['choices']==choices,'Global-rank origin/offset differs');output=[]
            if k:
                if ck==0:require(s['status']=='ERROR','Uncharged kth execution');stopped='ERROR';break
                require(ck==k,'Kth dispatch logical cost changed');spent+=ck
                vals=[[i,next(iter(bags[o].values()))['movie_id'] if added=='title' else bags[o]['title']['id'],offset] for i,(o,offset) in enumerate(choices)]
                event,response=dispatch('kth',added,vals,index)
                if s['status']=='ERROR':stopped='ERROR';break
                require(event['status']=='PASS','Output from failed kth dispatch');order={};cols=projection(contract,added)
                for row,(origin,offset) in zip(response,choices):
                    r=projected(row[1:],cols);bag={t:dict(v) for t,v in bags[origin].items()};require(accepts(expected,added,r),'Unfiltered added partner')
                    key=(added,r['id']);require(key not in observed or observed[key]==r,'Same entity changed between base/kth/state observations');observed[key]=r
                    require(r['id']==next(iter(bag.values()))['movie_id'] if added=='title' else r['movie_id'] is not None and r['movie_id']==bag['title']['id'],'NULL/nonjoining kth partner')
                    order.setdefault(origin,[]).append((offset,r['id']));bag[added]=r;output.append(bag)
                for pairs in order.values():
                    pairs.sort();require(all(x[1]<y[1] for x,y in zip(pairs,pairs[1:])),'Kth ID order/uniqueness contradicts rank offsets')
            else:require(ck==0,'Zero fanout kth charge')
            value=C*Fraction(total,m)
            if s['status']=='ERROR':stopped='ERROR';break
            require(s['status']==('ZERO_FANOUT' if total==0 else 'COMPLETE'),'Completed fanout status differs')
        if s['status']=='ERROR':stopped='ERROR';break
        require(s['output_rows']==output and s['output_cardinality']==rational(value),'Independent expansion output/Fraction recursion differs')
        ids=[tuple(b[t]['id'] for t in target) for b in output];require(len(set(ids))==len(ids),'Repeated complete bag ID tuple')
        entities={}
        for bag in output:
            for t,row in bag.items():
                key=(t,row['id']);require(key not in entities or entities[key]==row,'Inconsistent entity projection');entities[key]=row
        states[target]=(output,value)
    require(si==len(steps) and ei==len(events) and a['skipped_edges']==skipped and type(a['budget_spent']) is int and a['budget_spent']==spent<=100000,'Enumeration omitted/repeated edges/dispatches/costs')
    final=states.get(tables);status=('STOP_AFTER_COMPLETE' if final is not None else 'LOOKUP_BUDGET_NULL') if stopped=='LOOKUP' else 'ERROR_NULL' if stopped=='ERROR' else 'ZERO_SAMPLE' if final is not None and final[1]==0 else 'COMPLETE'
    require(a['status']==status and (type(a['error_type']) is str if status=='ERROR_NULL' else a['error_type'] is None),'Enumeration termination changed')
    return None if status in {'ERROR_NULL','LOOKUP_BUDGET_NULL'} or final is None else final[1],spent


def prediction_row(q):return {k:q[k] for k in ('query_no','sql','status','raw_prediction','wall_seconds','sql_roundtrips','id_attempts','charged_logical_lookups')}


def validate_query(q,expected,metadata,contract,binding,pid):
    fields={'query_no','sql','binding','scope','config','client_pid','table_samples','base_events','probe_events','algorithm','operations','status','raw_prediction','error_type','sqlstate','wall_seconds','id_attempts','sql_roundtrips','cleanup_sql_roundtrips','deadline_cancelled','charged_logical_lookups','budget_includes_all_sampling_rng_sql_math_and_controls'}
    require(set(q)==fields and type(q['query_no']) is int and q['query_no']==expected['query_no'] and q['sql']==expected['sql'] and q['binding']==binding and q['scope']==SCOPE and q['config']==CONFIG
        and type(q['client_pid']) is int and q['client_pid']==pid and pid>0 and q['budget_includes_all_sampling_rng_sql_math_and_controls'] is True,'Query identity/scope/input fields changed')
    require(q['status'] in COMPLETE|FAILURE and type(q['deadline_cancelled']) is bool,'Unknown query terminal');elapsed=nonnegative(q['wall_seconds']);ops=q['operations']
    require(type(ops) is list and type(q['sql_roundtrips']) is int and q['sql_roundtrips']==len(ops)<=2000 and type(q['cleanup_sql_roundtrips']) is int and q['cleanup_sql_roundtrips']==sum(op['cleanup'] for op in ops)<=3,'Physical SQL cost changed')
    require(type(q['charged_logical_lookups']) is int and 0<=q['charged_logical_lookups']<=100000,'Logical query cost invalid')
    done=q['status'] in COMPLETE
    if done:require(elapsed<30 and not q['deadline_cancelled'] and q['error_type'] is q['sqlstate'] is None,'Completed result after deadline/error')
    else:
        require(q['raw_prediction'] is None,'Unfinished query must remain null')
        if q['status']!='LOOKUP_BUDGET_NULL':require(type(q['error_type']) is str and bool(q['error_type']),'Failure reason missing')
    if not ops:
        require(q['status']=='QUERY_WALL_BUDGET' and elapsed>=30 and q['table_samples']==q['id_attempts']==q['algorithm']=={}
            and q['base_events']==q['probe_events']==[] and q['charged_logical_lookups']==q['cleanup_sql_roundtrips']==0
            and q['error_type']=='SamplingStopped' and q['sqlstate'] is None,'Only true pre-SAVEPOINT deadline may have no operations');return prediction_row(q)
    previous=0.;linked=set();control={'savepoint':'SAVEPOINT sampling_query','release':'RELEASE SAVEPOINT sampling_query','rollback':'ROLLBACK TO SAVEPOINT sampling_query','cleanup_limit':'SET LOCAL statement_timeout = 5000'}
    for i,op in enumerate(ops):
        require(set(op)=={'kind','sql','parameters','started_seconds','seconds','status','response','cleanup'}|({'error'} if op['status']=='ERROR' else set()),'Extra/incomplete SQL operation fields')
        start=nonnegative(op['started_seconds']);duration=nonnegative(op['seconds']);require(start+1e-6>=previous and start+duration<=elapsed+1e-5,'SQL timeline outside wall');previous=start+duration
        require(type(op['cleanup']) is bool and op['status'] in {'PASS','ERROR'},'Incomplete SQL receipt')
        if op['status']=='ERROR':require(op['response'] is None and type(op['error']) is str and op['error'],'Failed operation response changed')
        if op['kind'] in control:
            require(op['sql']==control[op['kind']] and op['parameters'] is op['response'] is None,'Control SQL changed');linked.add(i)
        elif op['kind']=='statement_limit':
            prefix='SET LOCAL statement_timeout = ';suffix=op['sql'][len(prefix):];require(op['sql'].startswith(prefix) and suffix.isdigit() and 1<=int(suffix)<=5000 and op['parameters'] is op['response'] is None and not op['cleanup'],'Online SQL timeout changed')
        else:require(not op['cleanup'],'Data SQL marked cleanup')
    require(ops[0]['kind']=='savepoint' and not ops[0]['cleanup'],'Initial savepoint missing')
    cleanup=[o for o in ops if o['cleanup']];require(not cleanup or cleanup==ops[-3:] and [o['kind'] for o in cleanup]==['rollback','cleanup_limit','release'] and all(o['status']=='PASS' for o in cleanup),'Incomplete cleanup sequence')
    states=replay_bases(q,expected,metadata,contract,linked);prediction,spent=replay_algorithm(q,expected,contract,metadata,states,linked)
    require(linked==set(range(len(ops))) and spent==q['charged_logical_lookups'],'Unregistered SQL or changed logical cost')
    if done:
        require(not cleanup and all(o['status']=='PASS' for o in ops) and ops[-1]['kind']=='release' and q['status']==q['algorithm']['status']
            and prediction is not None and q['raw_prediction']==rational(prediction),'Complete estimate differs from independent replay')
    elif q['status']=='LOOKUP_BUDGET_NULL':require(q['algorithm'].get('status')=='LOOKUP_BUDGET_NULL','False logical budget null')
    if q['status']=='QUERY_WALL_BUDGET':require(elapsed>=30 or q['deadline_cancelled'],'Unsubstantiated deadline stop')
    if q['status']=='ID_ATTEMPT_BUDGET':require(100000 in q['id_attempts'].values(),'Unsubstantiated ID budget stop')
    if q['status']=='SQL_ROUNDTRIP_BUDGET':require(len(ops)-len(cleanup)==1997,'Unsubstantiated SQL budget stop')
    if q['status']=='STATEMENT_TIMEOUT':require(q['sqlstate']=='57014' and any(o['status']=='ERROR' for o in ops),'Unsubstantiated statement timeout')
    return prediction_row(q)


def validate_collection(p,r,root):
    fields={'binding','scope','source_boundary','client_pid','database_identity','before','after','indexes_before','indexes_after','metadata','common_operations','timings','seconds','server_started_or_stopped','new_model_calls','raw_csv_or_truth_read','scalar_predicate_counts_used','owned_connection_rolled_back_and_closed','cancelled_queries'}
    require(set(r)==fields and r['binding']==p['binding'] and r['scope']==SCOPE and r['source_boundary']==p['source_boundary'] and type(r['client_pid']) is int and r['client_pid']>0,'Collection fields/identity changed')
    require(r['server_started_or_stopped'] is False and type(r['new_model_calls']) is int and r['new_model_calls']==0 and r['raw_csv_or_truth_read'] is r['scalar_predicate_counts_used'] is False and r['owned_connection_rolled_back_and_closed'] is True,'Collection boundary/owned close changed')
    d=r['database_identity'];require(set(d)=={'database','server_version_num','address','port','data_directory','backend_pid','read_only','isolation','postmaster_start','image'}
        and d['database']=='deepdb_job' and d['server_version_num']=='110005' and d['address']=='127.0.0.1' and type(d['port']) is int and d['port']==55432
        and Path(d['data_directory']).resolve()==(Path(root)/'data/postgresql/cluster').resolve() and Path(d['image']).resolve()==(Path(root)/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve()
        and type(d['backend_pid']) is int and d['backend_pid']>0 and d['read_only']=='on' and d['isolation']=='repeatable read' and type(d['postmaster_start']) is str and d['postmaster_start'],'Wrong historical DB/owned backend identity')
    require(set(r['before'])==set(r['after'])==set(r['metadata'])==set(POPULATION),'Incomplete six-table projection/metadata')
    for t,N in POPULATION.items():
        m=r['metadata'][t];require(set(m)=={'rows','distinct_ids','min_id','max_id'} and all(type(v) is int for v in m.values()) and m['rows']==m['distinct_ids']==N and m['min_id']<=m['max_id'] and N<=m['max_id']-m['min_id']+1,'Invalid unconditional ID/count/min/max domain')
        for side in ('before','after'):
            v=r[side][t];require(set(v)=={'schema','projection','binary_copy','seconds'} and v['projection']==projection(p['contract'],t),'Current projection columns incomplete');nonnegative(v['seconds'])
            b=v['binary_copy'];require(set(b)=={'bytes','sha256'} and type(b['bytes']) is int and 0<b['bytes']<=2*1024**3 and type(b['sha256']) is str and re.fullmatch('[a-f0-9]{64}',b['sha256']),'Invalid complete binary COPY receipt')
            a=v['schema'];require(set(a)=={'table','oid','relkind','relfilenode','inherits','columns','primary_key','valid_primary_key'} and a['table']==t and type(a['oid']) is int and a['oid']>0 and type(a['relfilenode']) is int and a['relfilenode']>0 and a['relkind']=='r' and a['inherits'] is False and a['primary_key']==['id'] and a['valid_primary_key'] is True,'Invalid ordinary current PK/schema identity')
            cols=dict(a['columns']);require(len(cols)==len(a['columns']) and all(cols.get(c) in {20,21,23} for c in v['projection']),'Invalid current integral projection type')
        require({k:v for k,v in r['before'][t].items() if k!='seconds'}=={k:v for k,v in r['after'][t].items() if k!='seconds'},'Before/after full query-projection mismatch')
    validate_indexes(r['indexes_before']);validate_indexes(r['indexes_after']);require(r['indexes_before']==r['indexes_after'],'Before/after index catalog changed')
    ops=r['common_operations'];require(type(ops) is list and len(ops)==19,'Exact common19 operations missing')
    setup=['SET LOCAL lock_timeout = 5000','LOCK TABLE '+', '.join('public."'+t+'"' for t in p['contract']['tables'])+' IN SHARE MODE NOWAIT','SET LOCAL search_path = pg_catalog, public',"SET LOCAL work_mem = '16MB'","SET LOCAL temp_file_limit = '1GB'",'SET LOCAL statement_timeout = 600000','SET LOCAL max_parallel_workers_per_gather = 0',"SET LOCAL application_name = 'deepdb_local_job70_ibjs'",_srs_namespace()['IDENTITY_SQL'],INDEX_SQL]
    sqls=setup+[population_sql(t) for t in p['contract']['tables']]+['SET LOCAL statement_timeout = 5000','SET LOCAL statement_timeout = 600000',INDEX_SQL]
    require([o['sql'] for o in ops]==sqls,'Lock/identity/metadata/index/600s prep/5s online SQL sequence changed')
    for i,op in enumerate(ops):
        require(set(op)=={'sql','parameters','response','seconds'} and op['parameters']==([p['contract']['tables']] if i in (9,18) else None),'Common parameters/fields changed');nonnegative(op['seconds'])
        if i not in (8,9,10,11,12,13,14,15,18):require(op['response'] is None,'Unexpected control response')
    require(ops[8]['response']==[d[k] for k in ('database','server_version_num','address','port','data_directory','backend_pid','read_only','isolation','postmaster_start')] and ops[9]['response']==r['indexes_before'] and ops[18]['response']==r['indexes_after'],'Historical identity/index response differs')
    for i,t in enumerate(p['contract']['tables']):require(ops[10+i]['response']==[r['metadata'][t][k] for k in ('rows','distinct_ids','min_id','max_id')],'Unconditional metadata response differs')
    require(set(r['timings'])=={'before_projection_seconds','live_population_metadata_seconds','all_online_queries_and_leaf_checkpoint_seconds','after_projection_seconds'},'Preparation/online timing categories incomplete')
    for v in r['timings'].values():nonnegative(v)
    require(sum(r['timings'].values())<=nonnegative(r['seconds'])+1e-5,'Preparation cost exceeds collection wall')


def validate_monitor(m,p,pid,publishing=False):
    require(set(m)=={'binding','client_pid','startup_resources','resources','errors','cancelled_queries','stopped','started_before_physical_preflight','seconds'} and m['binding']==p['binding'] and m['client_pid']==pid and type(m['client_pid']) is int and m['errors']==[] and m['started_before_physical_preflight'] is True
        and (type(m['stopped']) is bool if publishing else m['stopped'] is True),'Continuous monitor incomplete/not stopped')
    end=nonnegative(m['seconds']);require(end<5400 and type(m['resources']) is list and len(m['resources'])>=2,'Monitor total wall/samples invalid');previous=0.
    for i,s in enumerate([m['startup_resources']]+m['resources']):
        require(set(s)==({'available_memory_bytes','process_rss_bytes','free_disk_bytes'}|({'seconds'} if i else set())) and all(type(s[k]) is int and s[k]>=0 for k in ('available_memory_bytes','process_rss_bytes','free_disk_bytes')),'Invalid native resource sample')
        require(s['available_memory_bytes']>=(5 if not i else 1)*1024**3 and s['process_rss_bytes']<=512*1024**2 and s['free_disk_bytes']>=8*1024**3,'Resource cap violated')
        if i:
            tick=nonnegative(s['seconds']);require(previous<=tick<=end,'Resource sample timeline changed');previous=tick


def validate_bundle(directory,root=ROOT,publishing=False):
    """Internal producer math check; public verify always requires a final seal."""
    directory=Path(directory).resolve();root=Path(root).resolve();p=read(directory/'plan.json');validate_plan(p,root)
    require(directory==root/BASE/'runs'/p['binding'][:20],'Wrong isolated attempt namespace')
    a=read(directory/'approval.json');original=(root/a['plan_file']['path']).resolve();require((root/BASE/'plans').resolve() in original.parents,'Approval points outside dedicated plans');approval(a,p,original,root)
    require(read(original)==p,'Approved source plan differs from published plan')
    r=read(directory/'collection.json');validate_collection(p,r,root);pred=[];cancelled=[]
    for expected in p['contract']['queries']:
        f=directory/'queries'/('query_%02d.json'%expected['query_no']);require(read(f.with_suffix('.seal.json'))==dict(binding=p['binding'],query_no=expected['query_no'],artifact=artifact(f,root)),'Query physical seal differs')
        q=read(f);pred.append(validate_query(q,expected,r['metadata'],p['contract'],p['binding'],r['client_pid']))
        if q['deadline_cancelled']:cancelled.append(q['query_no'])
    require(r['cancelled_queries']==cancelled,'Owned cancellation/query list differs')
    value=dict(binding=p['binding'],scope=SCOPE,queries=pred);require(read(directory/'predictions.json')==value,'Predictions changed/missing70 terminals')
    m=read(directory/'monitor.json');validate_monitor(m,p,r['client_pid'],publishing);require(m['cancelled_queries']==cancelled and m['seconds']>=r['seconds'],'Monitor omits collection/cancellations')
    complete=sum(q['status'] in COMPLETE for q in pred);zero=sum(q['raw_prediction']==rational(Fraction(0)) for q in pred)
    querywall=sum(q['wall_seconds'] for q in pred);require(querywall<=r['timings']['all_online_queries_and_leaf_checkpoint_seconds']+1e-5,'Uncharged query client wall')
    result=dict(status='PASS_LOCAL_JOB70_IBJS_TERMINAL_RECEIPTS'+('_WITH_GAPS' if complete<70 else ''),binding=p['binding'],scope=SCOPE,pure_scope=PURE_SCOPE,
        queries=70,completed_queries=complete,incomplete_queries=70-complete,raw_zero_queries=zero,complete_finite_70_query_summary_allowed=complete==70 and zero==0,
        positive_truth_zero_q_error='INFINITY',incomplete_queries_must_not_be_silently_excluded=True,collection=artifact(directory/'collection.json',root),predictions=artifact(directory/'predictions.json',root),
        source_boundary=p['source_boundary'],current_database_values_reverified_by_offline_audit=False,common_sql_roundtrips=67,
        common_sql_roundtrips_breakdown=dict(recorded_setup_identity_metadata_indexes_reset=19,schema_checks=36,streaming_copy=12),
        online_query_sql_roundtrips=sum(q['sql_roundtrips'] for q in pred),charged_logical_lookups=sum(q['charged_logical_lookups'] for q in pred),all_online_query_wall_seconds=querywall,common_preparation_timings=r['timings'])
    if publishing:require(read(directory/'lifecycle.json')==dict(status='RUNNING',binding=p['binding'],client_pid=r['client_pid']),'Producer lifecycle not RUNNING')
    else:
        e=read(directory/'execution.json');timings={'admission_physical_validation_seconds','collection_and_checkpoint_seconds','fresh_postflight_physical_validation_seconds','offline_math_prepublication_validation_seconds','measured_client_wall_seconds_before_final_records'}
        require(set(e)==timings|{'binding','client_pid','final_record_and_seal_io_in_external_command_wall_only','root_external_command_wall_required_for_end_to_end_latency'} and e['binding']==p['binding'] and e['client_pid']==r['client_pid'] and type(e['client_pid']) is int and e['final_record_and_seal_io_in_external_command_wall_only'] is e['root_external_command_wall_required_for_end_to_end_latency'] is True,'Controller/end-to-end ledger incomplete')
        for k in timings:nonnegative(e[k])
        require(sum(e[k] for k in timings if k!='measured_client_wall_seconds_before_final_records')<=e['measured_client_wall_seconds_before_final_records']+1e-5 and e['collection_and_checkpoint_seconds']>=r['seconds'],'Uncharged controller/preparation costs')
        require(read(directory/'verification.json')==result and read(directory/'lifecycle.json')==dict(status='PASS',binding=p['binding'],client_pid=r['client_pid'],verification_sha256=digest(directory/'verification.json')),'Final lifecycle/independent verification differs')
    return result


def verify(directory,root=ROOT):
    """Strict current-file/receipt/math audit; no DB import, query, launch or repair."""
    directory=Path(directory).resolve();root=Path(root).resolve();seal=read(directory/'final_seal.json')
    require(set(seal)=={'schema','binding','files','self_sha256'} and seal['schema']=='job70-ibjs-final-v1' and seal['self_sha256']==value_hash({k:v for k,v in seal.items() if k!='self_sha256'}),'Invalid final seal')
    files=expected_files();require(set(seal['files'])==set(files),'Incomplete/extra required artifact set')
    actual=[p for p in directory.rglob('*') if p.is_file()];require({p.relative_to(directory).as_posix() for p in actual}==set(files)|{'final_seal.json'} and sum(p.stat().st_size for p in actual)<=LIMITS['max_total_output_bytes'],'Extra/missing physical namespace or output cap exceeded')
    require(all(p.resolve()==p for p in actual),'Aliased physical publication path')
    for name in files:
        record=artifact(directory/name,root);require(seal['files'][name]==record and (record['bytes']<=LIMITS['max_query_output_bytes'] if name.startswith('queries/query_') else True),'Current artifact changed/oversized: '+name)
    result=validate_bundle(directory,root);require(result['binding']==seal['binding'],'Final binding differs')
    return dict(status='PASS_READ_ONLY_LOCAL_JOB70_IBJS'+('_WITH_GAPS' if result['incomplete_queries'] else ''),verification=result,scope=SCOPE,pure_scope=PURE_SCOPE,
        verification_artifact=artifact(directory/'verification.json',root),final_seal=artifact(directory/'final_seal.json',root),artifacts=list(seal['files'].values()),
        dependencies=read(directory/'plan.json')['dependencies'],predictions=read(directory/'predictions.json'),controller_timing=read(directory/'execution.json'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);a=p.parse_args();print(json.dumps(verify(a.run)))
if __name__=='__main__':main()
