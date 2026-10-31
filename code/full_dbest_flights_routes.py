"""Pure original-DBEst 1D routing contracts; import never reads real inputs."""
from decimal import Decimal,InvalidOperation
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
N,RETAINED,FIT_ROWS,SEED=1000000000,9997912,20000,74131
PROBABILITY={'numerator':1,'denominator':100}
SELECTION_PICKLE_SHA='f10dbadfacf8319db2e2dae9d8942bb10d23d4a182dbe9a02b9f61bbfd647318'
IDS_SHA='6ba5ab3ea6d3d56ddef63bff0aa1f0f7e2c953dfc7791ca6c7a9798a261561e4'
SAMPLE_SHA='9d9c78d0e03b403472e34da73af9f3dccde070036c3ed02c649ce4ee880d6f45'
QUERY_NAMES=('F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2')
SQLS=(
 "SELECT AVG(dep_delay) FROM flights WHERE origin='ATL';",
 "SELECT AVG(distance) FROM flights WHERE unique_carrier='TW';",
 "SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' GROUP BY unique_carrier;",
 "SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND  dest_state_abr='CA' GROUP BY unique_carrier;",
 "SELECT year_date, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest='JFK' GROUP BY year_date;",
 "SELECT year_date, SUM(distance) FROM flights WHERE unique_carrier='9E' GROUP BY year_date;",
 "SELECT origin_state_abr, SUM(air_time) FROM flights WHERE dest='HPN' GROUP BY origin_state_abr;",
 "SELECT unique_carrier, AVG(dep_delay) FROM flights WHERE year_date=2005 AND origin='PHX' GROUP BY unique_carrier;",
 "SELECT dest_state_abr, COUNT(*) FROM flights WHERE distance>2500 GROUP BY dest_state_abr;",
 "SELECT unique_carrier, COUNT(*) FROM flights WHERE air_time>1000 AND dep_delay>1500 GROUP BY unique_carrier;",
 "SELECT year_date, SUM(arr_delay*dep_delay) FROM flights WHERE origin_state_abr = 'CA' AND dest_state_abr = 'HI' GROUP BY year_date;",
 "SELECT dest_state_abr, SUM(taxi_out)-SUM(taxi_in) FROM flights WHERE unique_carrier = 'UA' AND origin = 'ATL' GROUP BY dest_state_abr;")
VARIANT='QUERY_AWARE_EXACT_YEAR_PREFILTER_VARIANT'


def require(condition,message):
    if not condition:raise ValueError(message)


def value_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_sqls(sqls):require(list(sqls)==list(SQLS),'Exactly12 original SQL identities required')


def route_specs():
    return [dict(query_no=i,name=QUERY_NAMES[i],sql=SQLS[i],sql_sha256=hashlib.sha256(SQLS[i].encode()).hexdigest(),
        group_column={6:'ORIGIN_STATE_ABR',7:'UNIQUE_CARRIER',10:'YEAR_DATE',11:'DEST_STATE_ABR'}[i],
        aggregate='avg' if i==7 else 'sum',components={6:['air_time'],7:['dep_delay'],10:['product'],11:['taxi_out','taxi_in']}[i],
        scope=VARIANT if i==7 else 'ORIGINAL_1D_API_ROUTING_WITH_ESTIMATED_CATEGORY_METADATA',public_prefilter_matches=i!=7)
        for i in (6,7,10,11)]


def support_table():
    result=[]
    for i,name in enumerate(QUERY_NAMES):
        status=('REFERENCE_ONLY_FROZEN_76_CALLS' if i in (0,1,5,8) else 'NOT_DBEST_KDE_CATEGORY_LEARNING' if i in (2,3,4)
            else 'UNSUPPORTED_MULTIDIMENSIONAL' if i==9 else VARIANT if i==7 else 'NEW_ORIGINAL_1D_ROUTE_CANDIDATE')
        result.append(dict(query_no=i,name=name,sql=SQLS[i],status=status,new_native_calls=0))
    return result


def numeric(value):
    if value is None:return None
    require(type(value) in (str,int,float,Decimal),'Numeric field type differs')
    try:number=Decimal(str(value))
    except InvalidOperation:raise ValueError('Invalid original numeric field')
    require(number.is_finite(),'Nonfinite original numeric field');return number


def integer_year(value):
    number=numeric(value)
    if number is None:return None
    require(number==number.to_integral_value() and -(2**31)<=number<2**31,'Noninteger YEAR_DATE cannot be rounded')
    return int(number)


def member(row,index):
    if index==6:return row.get('DEST')=='HPN'
    if index==7:return row.get('ORIGIN')=='PHX' and integer_year(row.get('YEAR_DATE'))==2005
    if index==10:return row.get('ORIGIN_STATE_ABR')=='CA' and row.get('DEST_STATE_ABR')=='HI'
    if index==11:return row.get('UNIQUE_CARRIER')=='UA' and row.get('ORIGIN')=='ATL'
    raise ValueError('Not a new route')


def group_key(row,spec):
    raw=integer_year(row.get('YEAR_DATE')) if spec['group_column']=='YEAR_DATE' else row.get(spec['group_column'])
    require(raw is None or type(raw) in (str,int),'Exact category key type differs')
    return [None if raw is None else str(raw)]


def projection(row,component):
    if component=='product':
        a,b=numeric(row.get('ARR_DELAY')),numeric(row.get('DEP_DELAY'))
        value=None if a is None or b is None else a*b
    else:value=numeric(row.get(component.upper()))
    if value is None:return None
    result=float(value);require(math.isfinite(result),'Projection overflow in original units');return result


def nonnull_member(row,component):
    columns=('ARR_DELAY','DEP_DELAY') if component=='product' else (component.upper(),)
    require(all(c in row for c in columns),'Raw aggregate field missing')
    return all(row[c] is not None for c in columns)


def population_metadata(group,component,probability):
    p=Fraction(probability['numerator'],probability['denominator']);require(0<p<=1,'Exact positive retained probability required')
    count=group['nonnull'][component];nhat=Fraction(count)/p;variance=float(Fraction(count)*(1-p)/(p*p))
    return dict(Nhat=float(nhat),Nhat_fraction=dict(numerator=nhat.numerator,denominator=nhat.denominator),estimated=p!=1,
        retained_members=group['members'],retained_nonnull_count=count,probability=dict(probability),variance=variance,standard_error=math.sqrt(variance),
        source='Independent retained-sample prefilter/group/aggregate-nonNULL count divided by p',target_answer_used=False,
        uncertainty_scope='Bernoulli metadata plug-in variance; not a full query CI; not independent of fixed20K subset')


def build_catalog(rows,probability_numerator,probability_denominator,expected_rows):
    require(type(probability_numerator) is int and type(probability_denominator) is int and type(expected_rows) is int and expected_rows>=0,'Integer probability/count contract required')
    p=Fraction(probability_numerator,probability_denominator);require(0<p<=1,'Invalid retained probability')
    specs=route_specs();queries={str(s['query_no']):{} for s in specs};seen=0
    for row in rows:
        require(isinstance(row,dict),'Raw row mapping required');seen+=1
        for spec in specs:
            i=spec['query_no']
            if not member(row,i):continue
            key=group_key(row,spec);encoded=json.dumps(key,separators=(',',':'))
            g=queries[str(i)].setdefault(encoded,dict(key=key,members=0,nonnull={c:0 for c in spec['components']}));g['members']+=1
            for c in spec['components']:g['nonnull'][c]+=nonnull_member(row,c)
    require(seen==expected_rows,'Complete retained category scan row count differs')
    return dict(schema='dbest_routes_category_catalog_v1',status='PASS_CATEGORY_MEMBERSHIP_ONLY',rows=seen,
        probability=dict(numerator=p.numerator,denominator=p.denominator),target_answers_read=False,
        queries={k:[mapping[key] for key in sorted(mapping)] for k,mapping in queries.items()})


def validate_catalog(catalog):
    require(catalog.get('schema')=='dbest_routes_category_catalog_v1' and catalog.get('status')=='PASS_CATEGORY_MEMBERSHIP_ONLY' and
        catalog.get('target_answers_read') is False and type(catalog.get('rows')) is int and catalog['rows']>=0 and set(catalog['queries'])=={'6','7','10','11'},'Complete four-route category-only catalog required')
    p=catalog['probability'];require(set(p)=={'numerator','denominator'} and all(type(v) is int for v in p.values()) and 0<Fraction(p['numerator'],p['denominator'])<=1,'Catalog probability differs')
    for spec in route_specs():
        rows=catalog['queries'][str(spec['query_no'])];keys=set();total=0
        for group in rows:
            require(isinstance(group['key'],list) and len(group['key'])==1 and all(k is None or isinstance(k,str) for k in group['key']),'Exact one-column catalog key required')
            key=tuple(group['key']);require(key not in keys,'Duplicate category catalog key');keys.add(key)
            require(type(group['members']) is int and group['members']>0 and set(group['nonnull'])==set(spec['components']) and
                all(type(n) is int and 0<=n<=group['members'] for n in group['nonnull'].values()),'Invalid nonNULL category counts')
            total+=group['members']
        require(total<=catalog['rows'],'Category catalog membership exceeds retained rows')


def validate_selected(selected,formal=False):
    ids=selected['row_ids'];rows=selected['rows']
    require(isinstance(ids,list) and isinstance(rows,list) and len(ids)==len(rows)<=FIT_ROWS and len(ids)==len(set(ids)) and
        all(type(i) is int and i>=0 for i in ids) and ids==sorted(ids),'Fixed unique ordered <=20K selection required; no top-up')
    if formal:
        require(ids==sorted(random.Random(SEED).sample(range(RETAINED),FIT_ROWS)) and len(rows)==FIT_ROWS and
            hashlib.sha256(json.dumps(ids).encode()).hexdigest()==IDS_SHA,'Exact frozen seed74131 selection required')


def component_sql(spec,component):
    if spec['query_no']!=11:return spec['sql']
    return spec['sql'].replace('SUM(taxi_out)-SUM(taxi_in)','SUM('+component+')')


def make_jobs(selected,catalog):
    validate_selected(selected);validate_catalog(catalog);jobs=[]
    for spec in route_specs():
        cohorts={tuple(g['key']):dict(group=g,rows={c:[] for c in spec['components']},ids={c:[] for c in spec['components']},members=0) for g in catalog['queries'][str(spec['query_no'])]}
        for row_id,row in zip(selected['row_ids'],selected['rows']):
            if not member(row,spec['query_no']):continue
            key=tuple(group_key(row,spec));require(key in cohorts,'Selected group absent from same-source complete category catalog')
            c=cohorts[key];c['members']+=1
            for component in spec['components']:
                value=projection(row,component)
                if value is not None:c['ids'][component].append(row_id);c['rows'][component].append(value)
        for key,c in sorted(cohorts.items(),key=lambda kv:json.dumps(kv[0])):
            require(c['members']<=c['group']['members'],'Selected category membership exceeds retained catalog')
            for component in spec['components']:
                ids=c['ids'][component];xs=c['rows'][component]
                require(len(ids)<=c['group']['nonnull'][component],'Selected nonNULL cohort exceeds same-source catalog')
                identity=dict(query_no=spec['query_no'],key=list(key),component=component)
                job=dict(identity,job_id='q%02d.'%spec['query_no']+component+'.'+value_hash(identity),name=spec['name'],scope=spec['scope'],
                    public_prefilter_matches=spec['public_prefilter_matches'],parent_sql=spec['sql'],parent_sql_sha256=spec['sql_sha256'],
                    component_sql=component_sql(spec,component),aggregate=spec['aggregate'],row_ids=ids,xs=xs,fit_rows=len(xs),
                    population_metadata=population_metadata(c['group'],component,catalog['probability']),feature_scope='Scalar original-unit X=Y projection; no category KDE/no numerical rescaling')
                job['binding_sha256']=value_hash(job);jobs.append(job)
    require(len(jobs)==len({j['job_id'] for j in jobs}),'Duplicate original native job identity');return jobs


def combine_children(left,right):
    present=[r for r in (left,right) if r is not None];require(bool(present),'At least one child identity required')
    reference=present[0]
    for component,child in (('taxi_out',left),('taxi_in',right)):
        if child is not None:require(child['query_no']==11 and child['component']==component and child['key']==reference['key'] and
            child['parent_sql_sha256']==reference['parent_sql_sha256'],'Two original SUM child identities differ')
    valid=all(r is not None and r.get('status')=='RETURNED' and type(r.get('estimate')) in (int,float) and math.isfinite(r['estimate']) for r in (left,right))
    value=left['estimate']-right['estimate'] if valid else None
    if value is not None and not math.isfinite(value):value=None
    return dict(query_no=11,key=reference['key'],parent_sql_sha256=reference['parent_sql_sha256'],children=[left,right],estimate=value,
        status='POINT_DIFFERENCE_RETURNED' if value is not None else 'UNAVAILABLE_CHILD_RESULT',method='TWO_ORIGINAL_SUM_POINT_ADAPTER',
        interval=None,ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL')


def gaussian_oracle(xs,slope,intercept,bandwidth,lower,upper,population):
    require(bool(xs) and math.isfinite(bandwidth) and bandwidth>0 and lower<upper and population>=0,'Valid fitted1D oracle configuration required')
    phi=lambda z:0. if not math.isfinite(z) else math.exp(-z*z/2)/math.sqrt(2*math.pi)
    cdf=lambda z:math.erfc(-z/math.sqrt(2))/2
    mass=[];first=[]
    for x in xs:
        a,b=(lower-x)/bandwidth,(upper-x)/bandwidth;prob=cdf(b)-cdf(a)
        mass.append(prob);first.append(x*prob+bandwidth*(phi(a)-phi(b)))
    p=math.fsum(mass)/len(xs);weighted=slope*math.fsum(first)/len(xs)+intercept*p
    return dict(count=population*p,sum=population*weighted,avg=weighted/p if p else None)


def assemble_queries(jobs,results):
    require(len(jobs)==len(results) and len({j['job_id'] for j in jobs})==len(jobs),'Complete unique native job results required')
    actual={r['job_id'] if 'job_id' in r else r['job']['job_id']:r for r in results}
    require(set(actual)=={j['job_id'] for j in jobs},'Native result job identity differs')
    for j in jobs:
        r=actual[j['job_id']]
        require(all(r[k]==j[k] for k in ('query_no','key','component','parent_sql_sha256')),'Native result query/component identity differs')
    queries=[]
    for spec in route_specs():
        selected=[j for j in jobs if j['query_no']==spec['query_no']];groups={}
        for j in selected:groups.setdefault(tuple(j['key']),{})[j['component']]=actual[j['job_id']]
        out=[]
        for key,components in sorted(groups.items(),key=lambda kv:json.dumps(kv[0])):
            require(set(components)==set(spec['components']),'Incomplete independent SUM components')
            if spec['query_no']==11:
                value=combine_children(components['taxi_out'],components['taxi_in'])
                out.append(dict(key=list(key),estimate=value['estimate'],status=value['status'],ci_status=value['ci_status'],native_results=list(components.values()),adapter=value))
            else:
                r=next(iter(components.values()));out.append(dict(key=list(key),estimate=r['estimate'] if r['status']=='RETURNED' else None,status=r['status'],
                    ci_status='UNSUPPORTED_ORIGINAL_1D_QUERY_CI',native_results=[r]))
        queries.append(dict(spec,groups=out,original_api_calls=sum(r['native']['api_calls'] for group in out for r in group['native_results']),
            target_answers_used_for_training=False))
    return queries


def evaluate(queries,truth,population_rows=N):
    require(population_rows in (N,200000) and truth.get('complete') is True and truth.get('population_rows')==population_rows and len(truth['queries'])==12 and
        [(q['query_no'],q['query_name'],q['sql']) for q in truth['queries']]==list(zip(range(12),QUERY_NAMES,SQLS)),
        'Complete exact original12 truth identities required only after prediction')
    require([q['query_no'] for q in queries]==[6,7,10,11],'Exactly four new routed queries required')
    output=[]
    for query in queries:
        reference=truth['queries'][query['query_no']];actual={tuple(g['key']):g for g in query['groups']};exact={}
        require(len(actual)==len(query['groups']),'Duplicate predicted groups')
        for group in reference['groups']:
            key=tuple(None if k is None else str(k) for k in group['key'])
            require(key not in exact and type(group['numerator']) is int and type(group['denominator']) is int and group['denominator']>0,'Exact rational full-truth group required')
            exact[key]=Fraction(group['numerator'],group['denominator'])
        rows=[]
        for key in sorted(set(actual)|set(exact),key=repr):
            a=actual.get(key);v=exact.get(key);estimate=None if a is None else a['estimate']
            finite=type(estimate) in (int,float) and math.isfinite(estimate)
            status='EXTRA_PREDICTION_GROUP' if key not in exact else 'MISSING_PREDICTION_GROUP' if a is None or not finite else 'MATCHED'
            difference=abs(estimate-float(v)) if finite and v is not None else None
            rows.append(dict(key=list(key),status=status,estimate=estimate,truth=None if v is None else dict(numerator=v.numerator,denominator=v.denominator),
                absolute_error=difference,relative_error=difference/abs(float(v)) if difference is not None and v else None,
                zero_truth=v==0 if v is not None else False,missing_penalty_relative_error=1. if status=='MISSING_PREDICTION_GROUP' and v else None))
        output.append(dict(query_no=query['query_no'],name=query['name'],scope=query['scope'],groups=rows,
            missing_truth_groups=[r['key'] for r in rows if r['status']=='MISSING_PREDICTION_GROUP'],extra_prediction_groups=[r['key'] for r in rows if r['status']=='EXTRA_PREDICTION_GROUP'],
            missing_nonzero_penalty_count=sum(r['missing_penalty_relative_error']==1 for r in rows),zero_truth_groups=sum(r['zero_truth'] for r in rows),
            evaluation_only_no_training_answers=True))
    return output
