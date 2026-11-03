"""Small exact populations/callbacks only: no PostgreSQL or scientific driver."""
from collections import Counter
from fractions import Fraction
import importlib.util
import itertools
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_job_sampling_ibjs.py';assert p.exists(),'IBJS pure kernel missing'
    spec=importlib.util.spec_from_file_location('ibjs_test',str(p));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def query(m,sql=None):
    return m.parse_query(sql or 'SELECT COUNT(*) FROM title t,cast_info c WHERE t.id=c.movie_id;',0)


class Draws:
    def __init__(self,values):self.values=iter(values)
    def randrange(self,n):
        v=next(self.values);assert 0<=v<n;return v


def state(m,estimate=20):return m.State(('title',),[{'title':{'id':1}},{'title':{'id':3}}],Fraction(estimate))


class Index:
    def __init__(self,m,relations):self.m=m;self.relations=relations;self.count_calls=[];self.kth_calls=[]
    def matches(self,bag,added,q):
        out=[]
        for row in self.relations[added]:
            if not self.m.accepts(q,added,row):continue
            if added=='title':join=row['id']==next(iter(bag.values()))['movie_id']
            else:join=row['movie_id'] is not None and row['movie_id']==bag['title']['id']
            if join:out.append(dict(row))
        return sorted(out,key=lambda r:r['id'])
    def count_many(self,rows,added,q):
        self.count_calls.append(len(rows));return [len(self.matches(r,added,q)) for r in rows]
    def kth_many(self,requests,added,q):
        self.kth_calls.append(len(requests));return [self.matches(bag,added,q)[offset] for bag,offset in requests]


def index(m):return Index(m,{'cast_info':[{'id':10,'movie_id':1},{'id':30,'movie_id':3},{'id':31,'movie_id':3},{'id':32,'movie_id':3}]})


def test_fixed70_source_scope_and_no_truth_database_controller_import(monkeypatch):
    import builtins
    original=builtins.__import__
    def guard(name,*a,**k):
        assert name not in {'psycopg2','full_job_sampling_run','full_scalar_oracle_run'} and not name.startswith('ensemble_compilation')
        return original(name,*a,**k)
    monkeypatch.setattr(builtins,'__import__',guard);op=Path.open
    def files(p,*a,**k):
        assert p.suffix!='.csv' and 'true_cardinalities' not in str(p)
        return op(p,*a,**k)
    monkeypatch.setattr(Path,'open',files);m=module();c=m.workload()
    assert len(c['queries'])==70 and c['variant']=='LOCAL_JOB70_IBJS_SQL_N1000_B100K'
    assert m.SCOPE['author_reproduction_complete'] is False and m.SCOPE['full_paper_reproduction_complete'] is False
    assert m.SCOPE['live_driver_implemented'] is False and m.CONFIG==dict(n=1000,lookup_budget=100000,seed=1)


@pytest.mark.parametrize('changed',['code/full_job_sampling.py','code/full_job_sampling_run.py','code/full_scalar_oracle_run.py'])
def test_each_prior_literal_is_required_before_any_delegate_import(monkeypatch,changed):
    m=module();m.PINS[changed]='0'*64
    monkeypatch.setattr(m.importlib,'import_module',lambda *a:pytest.fail('Rejected source must not be imported'))
    with pytest.raises(ValueError,match='Frozen prior source changed'):m.frozen_srs()


def test_all_global_ranks_weight_sources_by_fanout_and_exact_recursion():
    m=module();hits=Counter()
    for rank in range(4):
        b=m.LookupBudget(3);trace={};p=index(m)
        out=m.extend(query(m),state(m),'cast_info',p,b,trace,n=1,rng=Draws([rank]))
        hits[out.rows[0]['title']['id']]+=1
        assert out.cardinality==40 and b.spent==3 and b.held==0 and trace['fanouts']==[1,3]
        assert trace['charged_counts']==2 and trace['charged_kth']==1 and trace['refunded']==0
    assert hits=={1:1,3:3}


def test_floyd_rank_subsets_have_equal_exact_small_probability():
    m=module();subsets=Counter()
    for a,b in itertools.product(range(3),range(4)):
        ranks=m.sample_ranks(4,2,Draws([a,b]));assert len(set(ranks))==2
        subsets[tuple(sorted(ranks))]+=1
    assert len(subsets)==6 and set(subsets.values())=={2}


def test_huge_rank_space_is_never_materialized():
    m=module();ranks=m.sample_ranks(10**40,3,Draws([0,0,0]))
    assert len(set(ranks))==3 and all(0<=r<10**40 for r in ranks)


def test_zero_weight_prefixes_map_to_correct_nonempty_origin_and_offset():
    m=module();s=m.State(('title',),[{'title':{'id':i}} for i in (1,2,3,4)],Fraction(4))
    p=Index(m,{'cast_info':[{'id':20,'movie_id':2}]+[{'id':40+i,'movie_id':4} for i in range(3)]})
    for rank,wanted in enumerate(([1,0],[3,0],[3,1],[3,2])):
        trace={};out=m.extend(query(m),s,'cast_info',p,m.LookupBudget(),trace,n=1,rng=Draws([rank]))
        assert trace['fanouts']==[0,1,0,3] and trace['choices']==[wanted] and out.cardinality==4


@pytest.mark.parametrize('empty',[False,True])
def test_empty_input_or_zero_fanout_is_raw_zero_not_population_proof(empty):
    m=module();p=Index(m,{'cast_info':[]});b=m.LookupBudget();trace={}
    s=m.State(('title',),[],Fraction(0)) if empty else state(m)
    out=m.extend(query(m),s,'cast_info',p,b,trace)
    assert out.rows==[] and out.cardinality==0 and trace['status'] in {'ZERO_INPUT','ZERO_FANOUT'}
    assert p.kth_calls==[] and b.spent==(0 if empty else 2) and b.held==0
    assert trace['population_zero_proven'] is False


def test_reservation_prevents_any_callbacks_and_cap_is_not_reset():
    m=module();b=m.LookupBudget();token=b.reserve(99999);token.charge(99999);token.close()
    p=index(m);trace={}
    with pytest.raises(m.LookupStopped):m.extend(query(m),state(m),'cast_info',p,b,trace,n=1)
    assert p.count_calls==p.kth_calls==[] and b.spent==99999 and b.held==0 and b.stopped
    with pytest.raises(m.LookupStopped):b.reserve(1)


def test_unused_reservation_refunded_but_truncated_count_keeps_dispatched_cost():
    m=module();p=index(m);p.count_many=lambda *a:[0];b=m.LookupBudget();trace={}
    with pytest.raises(ValueError):m.extend(query(m),state(m),'cast_info',p,b,trace)
    assert b.spent==2 and b.held==0 and trace['refunded']==1000 and trace['status']=='ERROR'


def test_small_fanout_refunds_only_unused_slots_and_keeps_fractional_recursion():
    m=module();p=Index(m,{'cast_info':[{'id':10,'movie_id':1}]});b=m.LookupBudget();trace={}
    out=m.extend(query(m),state(m,Fraction(5,3)),'cast_info',p,b,trace)
    assert out.cardinality==Fraction(5,6) and len(out.rows)==1
    assert trace['reserved']==1002 and trace['charged_counts']==2 and trace['charged_kth']==1
    assert trace['refunded']==999 and b.spent==3 and b.held==0


def test_truncated_or_duplicate_kth_response_cannot_become_completed_state():
    m=module()
    for responses in ([{'id':10,'movie_id':1}], [{'id':10,'movie_id':1},{'id':10,'movie_id':1}]):
        p=index(m);p.kth_many=lambda *a:responses;b=m.LookupBudget();trace={}
        with pytest.raises(ValueError):m.extend(query(m),state(m),'cast_info',p,b,trace,n=2,rng=Draws([0,0]))
        assert b.spent==4 and b.held==0 and trace['refunded']==0 and trace['status']=='ERROR'


@pytest.mark.parametrize('ids',[[30,30],[32,30]])
def test_same_origin_kth_ids_must_be_distinct_and_monotone_by_offset(ids):
    m=module();p=index(m);p.kth_many=lambda *a:[dict(id=i,movie_id=3) for i in ids]
    one=m.State(('title',),[{'title':{'id':3}}],Fraction(1));b=m.LookupBudget()
    with pytest.raises(ValueError):m.extend(query(m),one,'cast_info',p,b,{},n=2,rng=Draws([0,0]))
    assert b.spent==3 and b.held==0


@pytest.mark.parametrize('counts',[[True,3],[-1,3],[1]])
def test_invalid_or_truncated_counts_keep_attempted_cost_and_release_only_unused(counts):
    m=module();p=index(m);p.count_many=lambda *a:counts;b=m.LookupBudget();trace={}
    with pytest.raises(ValueError):m.extend(query(m),state(m),'cast_info',p,b,trace)
    assert b.spent==2 and b.held==0 and trace['refunded']==1000


def test_connected_star_enumeration_bounds_and_order_cover_registered_queries():
    m=module()
    for q in m.workload()['queries']:
        states,edges=m.star_graph(q['tables'])
        assert len(states)<=20 and len(edges)<=36 and list(states)==sorted(states,key=lambda x:(len(x),x))
        assert all(set(a)<set(c) and set(c)-set(a)=={r} for a,r,c in edges)
    states,edges=m.star_graph(['title','cast_info','movie_info','movie_keyword','movie_companies'])
    assert len(states)==20 and len(edges)==36


def small_relations():
    return {'title':[{'id':1,'production_year':2005},{'id':3,'production_year':2006},{'id':7,'production_year':None}],
        'cast_info':[{'id':2,'movie_id':3,'role_id':1},{'id':8,'movie_id':3,'role_id':1},{'id':11,'movie_id':1,'role_id':1},
                     {'id':15,'movie_id':None,'role_id':1},{'id':23,'movie_id':3,'role_id':2},{'id':24,'movie_id':999,'role_id':1}],
        'movie_keyword':[{'id':4,'movie_id':3,'keyword_id':99},{'id':10,'movie_id':3,'keyword_id':100},
                         {'id':18,'movie_id':1,'keyword_id':99},{'id':20,'movie_id':None,'keyword_id':99}]}


def test_complete_population_goldens_with_holes_nulls_duplicate_fk_and_strict_boundary():
    m=module();q=m.parse_query('SELECT COUNT(*) FROM title t,cast_info c,movie_keyword k WHERE t.id=c.movie_id AND t.id=k.movie_id AND t.production_year>2005 AND c.role_id=1 AND k.keyword_id=99;',0)
    relations=small_relations();bases={};traces={}
    for t,rows in relations.items():
        cols=sorted(rows[0]);pop=dict(rows=len(rows),min_id=min(x['id'] for x in rows),max_id=max(x['id'] for x in rows))
        trace={};traces[t]=trace
        def fetch(ids,rows=rows,cols=cols):return [[row[c] for c in cols] for row in rows if row['id'] in ids]
        bases[t]=m.draw_base(q,t,pop,cols,fetch,m.frozen_srs().Budget(),trace)
        assert len(trace['raw_sample']['selected_ids'])==len(rows)
    # Independent tiny complete join, not passed to the algorithm.
    truth=sum(t['production_year'] is not None and t['production_year']>2005 and c['role_id']==1 and k['keyword_id']==99
        and c['movie_id'] is not None and c['movie_id']==t['id'] and k['movie_id'] is not None and k['movie_id']==t['id']
        for t,c,k in itertools.product(*(relations[x] for x in ('title','cast_info','movie_keyword'))))
    qt={};out=m.estimate_query(q,bases,Index(m,relations),qt)
    assert truth==2 and out['prediction']==Fraction(truth) and out['status']=='COMPLETE'
    assert all(len(s.rows)<=1000 for s in out['states'].values())
    assert sum(step['charged_counts']+step['charged_kth'] for step in qt['attempts'])==out['budget_spent']
    assert all(step['reserved']==step['charged_counts']+step['charged_kth']+step['refunded'] for step in qt['attempts'])


def test_filtered_base_estimate_divides_by_unfiltered_sample_size():
    m=module();q=m.parse_query('SELECT COUNT(*) FROM title t,cast_info c WHERE t.id=c.movie_id AND t.production_year>2005;',0)
    raw=dict(table='title',population=dict(rows=100),projection=['id','production_year'],complete=True,selected_ids=[1,3,7],rows=[[1,2005],[3,2006],[7,None]])
    s=m.base_state(q,'title',raw)
    assert len(s.rows)==1 and s.cardinality==Fraction(100,3)


@pytest.mark.parametrize('bad',[[True,2005],[1,'2005']])
def test_invalid_raw_rows_cannot_hide_behind_filter_rejection(bad):
    m=module();q=m.parse_query('SELECT COUNT(*) FROM title t,cast_info c WHERE t.id=c.movie_id AND t.production_year>2005;',0)
    raw=dict(table='title',population=dict(rows=100),projection=['id','production_year'],complete=True,selected_ids=[1],rows=[bad])
    with pytest.raises(ValueError):m.base_state(q,'title',raw)


def test_bottomup_revisits_only_below_n_div_ten_without_unbounded_retry():
    m=module();q=query(m);bases={'title':state(m,2),'cast_info':m.State(('cast_info',),[{'cast_info':{'id':10,'movie_id':1}}],Fraction(1))}
    p=Index(m,{'title':[{'id':1},{'id':3}],'cast_info':[{'id':10,'movie_id':1}]});trace={}
    out=m.estimate_query(q,bases,p,trace,n=10)
    assert len(trace['attempts'])==1 and len(out['states'][tuple(q['tables'])].rows)==1
    assert out['status']=='COMPLETE'


def test_zero_sample_is_replaced_by_next_incoming_path_without_truth_fallback():
    m=module();q=query(m);bases={'title':state(m,2),'cast_info':m.State(('cast_info',),[],Fraction(0))}
    p=Index(m,{'title':[{'id':1},{'id':3}],'cast_info':[{'id':10,'movie_id':1}]});trace={}
    out=m.estimate_query(q,bases,p,trace)
    assert out['prediction']==1 and out['status']=='COMPLETE' and len(trace['attempts'])==2
    assert trace['attempts'][0]['status']=='ZERO_INPUT' and trace['attempts'][1]['replaces_existing'] is True


def test_budget_admission_stop_retains_complete_full_state_but_inflight_failure_nulls_it():
    m=module();q=query(m);bases={'title':state(m,2),'cast_info':m.State(('cast_info',),[{'cast_info':{'id':10,'movie_id':1}}],Fraction(1))}
    p=Index(m,{'title':[{'id':1},{'id':3}],'cast_info':[{'id':10,'movie_id':1}]});trace={}
    out=m.estimate_query(q,bases,p,trace,budget=m.LookupBudget(1001))
    assert out['status']=='STOP_AFTER_COMPLETE' and out['prediction']==1 and out['budget_spent']==2
    p=Index(m,p.relations);original=p.count_many
    def fail_second(*a):
        if p.count_calls:raise RuntimeError('synthetic next path failure')
        return original(*a)
    p.count_many=fail_second;out=m.estimate_query(q,bases,p,{})
    assert out['status']=='ERROR_NULL' and out['prediction'] is None and tuple(q['tables']) in out['states']


def test_budget_stop_without_complete_target_is_null_and_sql_error_never_zero():
    m=module();q=query(m);bases={'title':state(m,2),'cast_info':m.State(('cast_info',),[{'cast_info':{'id':10,'movie_id':1}}],Fraction(1))}
    out=m.estimate_query(q,bases,index(m),{},budget=m.LookupBudget(0))
    assert out['status']=='LOOKUP_BUDGET_NULL' and out['prediction'] is None
    class Bad:
        def count_many(self,*a):raise RuntimeError('synthetic SQL failure')
    out=m.estimate_query(q,bases,Bad(),{})
    assert out['status']=='ERROR_NULL' and out['prediction'] is None and out['budget_spent']>0
