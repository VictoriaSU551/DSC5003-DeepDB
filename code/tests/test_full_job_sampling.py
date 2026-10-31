"""Pure SRS contracts and toy callbacks; never PostgreSQL or model execution."""
import importlib.util
from pathlib import Path
from fractions import Fraction
import itertools
import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_job_sampling.py';assert path.exists(),'new SRS core missing'
    s=importlib.util.spec_from_file_location('srs_core_test',str(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_registered_workload_is_exact70_and_core_does_not_open_truth(monkeypatch):
    m=module();original=Path.read_bytes
    def read(p):
        assert 'true_cardinalities' not in str(p) and str(p).lower().endswith('.csv') is False
        return original(p)
    monkeypatch.setattr(Path,'read_bytes',read)
    c=m.workload();assert len(c['queries'])==70 and len(c['tables'])==6
    assert c['variant']=='LOCAL_JOB70_SRS_WOR_N1000' and m.SCOPE['author_method_configuration_identified'] is False
    assert m.SCOPE['ibjs_implemented'] is False


def test_changed_workload_is_rejected_before_parsing(tmp_path):
    m=module();p=tmp_path/'q.sql';p.write_text('SELECT COUNT(*) FROM title t;')
    with pytest.raises(ValueError,match='workload|bytes'):m.workload(p)


class Draws:
    def __init__(self,values):self.values=iter(values)
    def randint(self,a,b):
        value=next(self.values);assert a<=value<=b;return value


def test_entity_sampling_rejects_holes_and_duplicates_before_filtering():
    m=module();seen=[];rows={1:[1,None],3:[3,2005],5:[5,2010]};trace={}
    def fetch(ids):seen.append(list(ids));return [rows[x] for x in sorted(ids) if x in rows]
    m.draw_table(0,'title',{'rows':3,'min_id':1,'max_id':5},['id','production_year'],fetch,m.Budget(clock=lambda:0),trace,n=2,rng=Draws([2,2,1,4,3]))
    assert trace['selected_ids']==[1,3] and trace['rows']==[[1,None],[3,2005]]
    assert seen==[[2,1],[4],[3]] and [a for b in trace['batches'] for a in b['attempted_ids']]==[2,2,1,4,3]


def test_uniform_valid_entity_not_uniform_dense_key_assumption():
    m=module();hits=[]
    # Uniform permutations of the ID domain give each extant entity equal weight.
    for order in itertools.permutations([1,2,3]):
        trace={};m.draw_table(0,'title',{'rows':2,'min_id':1,'max_id':3},['id'],lambda ids:[[x] for x in ids if x!=2],m.Budget(clock=lambda:0),trace,n=1,rng=Draws(order))
        hits+=trace['selected_ids']
    assert hits.count(1)==hits.count(3)==3


@pytest.mark.parametrize('bad',[[[9]],[[1],[1]],[[True]],[[1,'string']]])
def test_lookup_cannot_return_extra_duplicate_noninteger_or_wrong_width_rows(bad):
    m=module()
    with pytest.raises(ValueError):m.draw_table(0,'title',{'rows':1,'min_id':1,'max_id':1},['id'],lambda ids:bad,m.Budget(clock=lambda:0),{},n=1,rng=Draws([1]))


def test_exact_fraction_keeps_raw_zero_and_large_integer_products():
    m=module();population={'title':5,'cast_info':7};selected={'title':2,'cast_info':3}
    assert m.estimate(3,population,selected)==Fraction(35,2)
    assert m.rational(m.estimate(0,population,selected))=={'numerator':'0','denominator':'1'}
    with pytest.raises(ValueError):m.estimate(0,population,{'title':0,'cast_info':3})


@pytest.mark.parametrize('stop',['time','attempts','sql'])
def test_budgets_stop_before_more_rng_or_sql(stop):
    m=module();now=[0.];b=m.Budget(clock=lambda:now[0],max_attempts=1,max_sql=1,max_seconds=30)
    if stop=='time':now[0]=30.001;f=b.check
    elif stop=='attempts':b.attempt('title');f=lambda:b.attempt('title')
    else:b.sql();f=b.sql
    with pytest.raises(m.SamplingStopped):f()


def test_star_count_sql_only_reads_sampled_entities_and_uses_numeric_fanout():
    m=module();q=m.parse_query('SELECT COUNT(*) FROM title t,cast_info ci,movie_keyword mk WHERE t.id=ci.movie_id AND t.id=mk.movie_id AND t.production_year>2005 AND ci.role_id=1;',0)
    statement,params=m.sample_count_sql(q,{'title':[1,2],'cast_info':[3,4],'movie_keyword':[5]})
    assert statement.count('ANY(%s)')==3 and 'GROUP BY "movie_id"' in statement and '::numeric' in statement
    assert 'SUM(' in statement and all(x not in statement.upper() for x in ('CREATE ','INSERT ','UPDATE ','DROP '))
    assert 2005 in params and 1 in params and [1,2] in params


def test_query_seed_is_distinct_and_stable_without_global_rng():
    m=module();assert m.seed_for(0,'title')==m.seed_for(0,'title')
    assert len({m.seed_for(i,t) for i in range(3) for t in ('title','cast_info')})==6


def test_pinned_runtime_filesystem_inventory_never_imports_db_or_controller(monkeypatch):
    m=module();original=__import__('builtins').__import__
    def guard(name,*args,**kwargs):
        assert name not in {'psycopg2','full_scalar_oracle_run','full_job_sampling_run'}
        return original(name,*args,**kwargs)
    monkeypatch.setattr(__import__('builtins'),'__import__',guard)
    d=m.dependencies()
    required=set(m.SOURCES)|set(m.PINS)|set(m.INPUTS)|{m.QUERY_FILE}
    assert set(d['sources'])==required and d['runtime'] and len(d['runtime_inventory_function_sha256'])==64
    assert m.artifact(Path(__import__('sys').executable))['path'] in d['runtime']
    assert d['raw_csv_current_bytes_rehashed'] is False
