"""Pure LOCAL IBJS kernel. Callback probes only; no SQL/controller/truth API."""
import sys
sys.dont_write_bytecode=True
from bisect import bisect_right
from fractions import Fraction
import hashlib
import importlib
import itertools
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
VARIANT='LOCAL_JOB70_IBJS_SQL_N1000_B100K'
CONFIG=dict(n=1000,lookup_budget=100000,seed=1)
SCOPE=dict(method=VARIANT,author_reproduction_complete=False,full_paper_reproduction_complete=False,
           author_configuration_identified=False,adaptive_path_unbiasedness_claimed=False,
           live_driver_implemented=False,truth_or_scalar_selectivities_used=False)
PINS={'code/full_job_sampling.py': 'd656de7c010daf636797b2876bcc8599a25f8be6f341b52e210cb4157c30d1a9',
 'code/full_job_sampling_run.py': '2e7e7a51bec679e718582391ea64142b5a0f05127b6dbb50d6e019e4ad84fec1',
 'code/full_job_sampling_audit.py': '5ea0bbb849db80dd78f241ac78b1e793ac2c80293519ce6c465f121d27b3bd3a',
 'code/tests/test_full_job_sampling.py': '0446ddc2424a706616d396e4bba8266456a9ff376a2c9c4bc6f4676aaca28446',
 'code/tests/test_full_job_sampling_run.py': 'aedd9732f051878a9b4ba48acfdf4301cf405d6eba922ddb860a2dce728345e0',
 'code/tests/test_full_job_sampling_audit.py': 'f731fb4330e4878c19a0e053b468e24e5d17eacc38200fb5574fe6a5facfa600',
 'docs/FULL_JOB_SAMPLING_PROTOCOL.md': 'b67bd20e40ae92d7a2c4d6f6227b49de1a102908dcd61d95411f871dc547dae4',
 'code/full_scalar_oracle.py': 'a804301149e370eabf1055cdcb94d8157502032ab37a81e33a1b2396225964df',
 'code/full_scalar_oracle_run.py': 'd5d31f3460d84942a2f22a0874f0c73bfcbbecb45a048a2ab78be76496ee9e26',
 'code/full_scalar_oracle_audit.py': '15912c8e98a620553bc861e3b6dbe1821227f6cf8779bf1ab5eba6bb225f0307',
 'docs/FULL_SCALAR_ORACLE_PROTOCOL.md': '1f02d7b591197f8cf4bd318199acb0173741887f149c4f5c80c02647058797fa'}


def require(ok,message):
    if not ok:raise ValueError(message)


def integer(v):require(type(v) is int and v>=0,'Exact nonnegative integer required');return v
def cap(n):require(type(n) is int and 0<n<=1000,'Capacity must be in1..1000');return n
def value_hash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def rational(x):return dict(numerator=str(x.numerator),denominator=str(x.denominator))
def clone(bag):return {t:dict(row) for t,row in bag.items()}


def frozen_srs():
    for p,sha in PINS.items():require(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha,'Frozen prior source changed: '+p)
    m=importlib.import_module('full_job_sampling');require(Path(m.__file__).resolve()==ROOT/'code/full_job_sampling.py','Wrong frozen pure module');return m


def parse_query(sql,index):return frozen_srs().parse_query(sql,index)
def workload():return dict(frozen_srs().workload(),variant=VARIANT)


def accepts(query,table,row):
    for term in next(p['conditions'] for p in query['predicates'] if p['table']==table):
        v=row[term['column']];w=term['value'];op=term['operator']
        if v is None:return False
        if not {'=':v==w,'!=':v!=w,'<':v<w,'>':v>w,'<=':v<=w,'>=':v>=w}[op]:return False
    return True


class State:
    def __init__(self,tables,rows,cardinality):
        self.tables=tuple(tables);self.rows=rows;self.cardinality=cardinality
        require(self.tables==tuple(sorted(set(self.tables))) and bool(self.tables),'Canonical nonempty table subset required')
        require(type(rows) is list and len(rows)<=1000 and isinstance(cardinality,Fraction) and cardinality>=0,'Bounded exact state required')
        require((len(rows)==0)==(cardinality==0),'Zero sample/estimate state must agree')
        seen=set();entities={}
        for bag in rows:
            require(type(bag) is dict and set(bag)==set(self.tables),'Incomplete bag tuple')
            for t,row in bag.items():
                require(type(row) is dict and all(type(c) is str for c in row) and type(row.get('id')) is int
                        and all(v is None or type(v) is int for v in row.values()),'Exact entity rows required')
                key=(t,row['id']);require(key not in entities or entities[key]==row,'Same entity ID has inconsistent values');entities[key]=row
            identity=tuple(bag[t]['id'] for t in self.tables);require(identity not in seen,'Duplicate complete bag tuple');seen.add(identity)
    def fingerprint(self):return value_hash(dict(tables=self.tables,rows=self.rows,cardinality=rational(self.cardinality)))


def validate_state(query,s,n):
    State(s.tables,s.rows,s.cardinality);require(set(s.tables)<=set(query['tables']) and len(s.rows)<=n,'State outside query/capacity')
    require(len(s.tables)==1 or 'title' in s.tables,'Disconnected state rejected')
    for bag in s.rows:
        require(all(t=='title' or 'movie_id' in row for t,row in bag.items()),'Child join key missing')
        require(all(accepts(query,t,row) for t,row in bag.items()),'Unfiltered state row')
        if 'title' in bag:
            require(all(t=='title' or row['movie_id'] is not None and row['movie_id']==bag['title']['id'] for t,row in bag.items()),'Nonjoining bag tuple')


def base_state(query,table,raw):
    require(table in query['tables'] and raw['table']==table and raw['complete'] is True,'Complete unfiltered base sample required')
    rows=raw['rows'];cols=raw['projection'];N=integer(raw['population']['rows']);k=len(rows)
    require(N>0 and 0<k<=min(N,1000) and len(cols)==len(set(cols)) and 'id' in cols,'Invalid base sample/domain')
    require(len(raw['selected_ids'])==k and len(set(raw['selected_ids']))==k,'Unique sampled entity IDs required')
    kept=[]
    for identity,row in zip(raw['selected_ids'],rows):
        require(type(row) is list and len(row)==len(cols) and all(v is None or type(v) is int for v in row),'Incomplete/nonintegral base row');record=dict(zip(cols,row))
        require(type(identity) is int and type(record['id']) is int and record['id']==identity,'Base ID/order mismatch')
        if accepts(query,table,record):kept.append({table:record})
    return State((table,),kept,Fraction(N*len(kept),k))


def draw_base(query,table,population,projection,fetch,budget,trace,n=1000):
    cap(n);srs=frozen_srs();raw={};trace.update(raw_sample=raw,base_rng_method=srs.VARIANT)
    srs.draw_table(query['query_no'],table,population,projection,fetch,budget,raw,n=n)
    out=base_state(query,table,raw);trace.update(cardinality=rational(out.cardinality));return out


class LookupStopped(ValueError):pass


class Reservation:
    def __init__(self,budget,amount):self.budget=budget;self.remaining=amount;self.refunded=0;self.closed=False
    def charge(self,amount):
        integer(amount);require(not self.closed and amount<=self.remaining,'Invalid/double logical lookup charge')
        self.remaining-=amount;self.budget.held-=amount;self.budget.spent+=amount
    def close(self):
        require(not self.closed,'Reservation already released');self.refunded=self.remaining
        self.budget.held-=self.remaining;self.remaining=0;self.closed=True


class LookupBudget:
    def __init__(self,limit=100000):
        integer(limit);require(limit<=100000,'Cannot exceed registered lookup cap');self.limit=limit;self.spent=0;self.held=0;self.stopped=False
    def reserve(self,amount):
        integer(amount);require(self.held==0,'Only one active expansion reservation allowed')
        if self.stopped or self.spent+amount>self.limit:self.stopped=True;raise LookupStopped('LOOKUP_BUDGET')
        self.held=amount;return Reservation(self,amount)


def sample_ranks(total,k,rng,check=lambda:None):
    integer(total);integer(k);require(k<=total and k<=1000,'Invalid global rank sample size')
    selected=set();out=[]
    # Floyd: O(k) memory, including totals exceeding Py_ssize_t/range.__len__.
    for j in range(total-k,total):
        check();draw=rng.randrange(j+1);require(type(draw) is int and 0<=draw<=j,'Invalid rank RNG')
        chosen=j if draw in selected else draw;selected.add(chosen);out.append(chosen)
    return out


def star_graph(tables):
    tables=tuple(sorted(tables));require(2<=len(tables)<=5 and len(set(tables))==len(tables) and 'title' in tables,'Registered2..5-table star required')
    require(set(tables)<=set(frozen_srs().EXPECTED_ROWS),'Unknown relation')
    states=sorted([subset for k in range(1,len(tables)+1) for subset in itertools.combinations(tables,k)
                   if k==1 or 'title' in subset],key=lambda x:(len(x),x))
    edges=[]
    for subset in states:
        for t in tables:
            if t in subset or ('title' not in subset and t!='title'):continue
            edges.append((subset,t,tuple(sorted(subset+(t,)))))
    return states,edges


def extend(query,state,added,probe,budget,trace,n=1000,rng=None,check=lambda:None):
    # Alg1's n bounds the output. Its already materialized input is independently
    # bounded by the registered1000, even in toy tests requesting smaller output.
    cap(n);validate_state(query,state,1000)
    require(added in query['tables'] and added not in state.tables and ('title' in state.tables or added=='title'),'Connected new base relation required')
    m=len(state.rows);tables=tuple(sorted(state.tables+(added,)));token=None
    trace.update(input_tables=state.tables,added=added,input_sha256=state.fingerprint(),input_cardinality=rational(state.cardinality),
        reservation_requested=0 if m==0 else m+n,reserved=0,charged_counts=0,charged_kth=0,refunded=0,
        fanouts=[],ranks=[],choices=[],status='RUNNING',population_zero_proven=False)
    try:
        check()
        if m==0:
            trace.update(status='ZERO_INPUT',output_rows=[],output_cardinality=rational(Fraction(0)));return State(tables,[],Fraction(0))
        token=budget.reserve(m+n);trace['reserved']=m+n
        token.charge(m);trace['charged_counts']=m
        counts=probe.count_many([clone(bag) for bag in state.rows],added,query);check()
        require(type(counts) is list and len(counts)==m and all(type(d) is int and d>=0 for d in counts),'Truncated/invalid fanout counts')
        trace['fanouts']=counts;total=sum(counts);k=min(n,total);ends=list(itertools.accumulate(counts))
        if rng is None:rng=random.Random(int(value_hash(dict(method=VARIANT,sql=query['sql'],query_no=query['query_no'],seed=1,input=state.tables,added=added)),16))
        ranks=sample_ranks(total,k,rng,check);trace['ranks']=ranks;requests=[]
        for rank in ranks:
            i=bisect_right(ends,rank);offset=rank-(ends[i-1] if i else 0)
            trace['choices'].append([i,offset]);requests.append((clone(state.rows[i]),offset))
        out=[]
        if k:
            check();token.charge(k);trace['charged_kth']=k
            partners=probe.kth_many(requests,added,query);check()
            require(type(partners) is list and len(partners)==k,'Truncated kth partner response')
            ordered={}
            for (bag,offset),row,(origin,_) in zip(requests,partners,trace['choices']):
                check();require(type(row) is dict and type(row.get('id')) is int and accepts(query,added,row),'Unfiltered/invalid kth partner')
                ordered.setdefault(origin,[]).append((offset,row['id']))
                joins=(row['id']==next(iter(bag.values()))['movie_id']) if added=='title' else row['movie_id'] is not None and row['movie_id']==bag['title']['id']
                require(joins,'kth partner violates SQL NULL/join equality');bag[added]=dict(row);out.append(bag)
            for items in ordered.values():
                items.sort();require(all(a[1]<b[1] for a,b in zip(items,items[1:])),'kth partner IDs contradict offset order/uniqueness')
        result=State(tables,out,state.cardinality*Fraction(total,m));validate_state(query,result,n);check()
        trace.update(status='ZERO_FANOUT' if total==0 else 'COMPLETE',output_rows=result.rows,output_cardinality=rational(result.cardinality));return result
    except BaseException as error:
        trace.update(status='LOOKUP_BUDGET' if isinstance(error,LookupStopped) else 'ERROR',error_type=type(error).__name__);raise
    finally:
        if token is not None:token.close();trace['refunded']=token.refunded


def estimate_query(query,bases,probe,trace,n=1000,budget=None,check=lambda:None):
    cap(n);budget=LookupBudget() if budget is None else budget;_,edges=star_graph(query['tables'])
    require(set(bases)==set(query['tables']),'Complete independently sampled bases required')
    states={}
    for t,s in bases.items():
        require(s.tables==(t,),'Base relation identity mismatch');validate_state(query,s,n);states[(t,)]=s
    whole=tuple(sorted(query['tables']));trace.update(attempts=[],skipped_edges=[],scope=dict(SCOPE));status='COMPLETE';error=None
    try:
        for i,(subset,added,target) in enumerate(edges):
            check()
            if subset not in states:continue
            if target in states and len(states[target].rows)*10>=n:trace['skipped_edges'].append(i);continue
            step=dict(edge_index=i,replaces_existing=target in states);trace['attempts'].append(step)
            states[target]=extend(query,states[subset],added,probe,budget,step,n=n,check=check)
    except LookupStopped:status='STOP_AFTER_COMPLETE' if whole in states else 'LOOKUP_BUDGET_NULL'
    except Exception as e:status='ERROR_NULL';error=type(e).__name__
    require(budget.held==0 and budget.spent<=budget.limit,'Unclosed/overspent lookup budget')
    final=states.get(whole);prediction=None if status in {'ERROR_NULL','LOOKUP_BUDGET_NULL'} or final is None else final.cardinality
    if status=='COMPLETE' and prediction==0:status='ZERO_SAMPLE'
    require(final is not None or status in {'ERROR_NULL','LOOKUP_BUDGET_NULL'},'Complete enumeration lost its target state')
    return dict(status=status,prediction=prediction,states=states,budget_spent=budget.spent,error_type=error)
