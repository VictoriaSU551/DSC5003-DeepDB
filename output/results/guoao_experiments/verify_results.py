"""Check compact result files using only the Python standard library."""
import argparse,csv,hashlib,json,math,statistics
from pathlib import Path
def load(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def quantile(values,p):
    a=sorted(values);i=(len(a)-1)*p/100;lo=math.floor(i);hi=math.ceil(i)
    return a[lo]+(i-lo)*(a[hi]-a[lo])
def check(condition,message):
    if not condition:raise ValueError(message)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,help='Also check repository benchmark SQL and official counts')
    args=parser.parse_args();base=Path(__file__).resolve().parent
    ms=load(base/'metrics.csv');ps=load(base/'predictions.csv');ts=load(base/'truth_audit.csv')
    check(len(ms)==14 and len(ps)==len(ts)==70,'Expected 14 settings and 70 queries')
    check([int(x['query_id']) for x in ps]==list(range(70)),'Prediction IDs differ')
    check([int(x['query_id']) for x in ts]==list(range(70)),'Audit IDs differ')
    ids=[x['run_id'] for x in ms]
    expected={'relationship_%d_s%d'%(n,s) for s in [1,2,3] for n in [10000,100000,1000000]}
    expected|={'rdc_100000_s1','rdc_1000000_s1','rdc_1000000_s2','rdc_1000000_s3','postgresql'}
    check(len(set(ids))==14 and set(ids)==expected,'Run settings differ')
    check(set(ps[0])=={'query_id','query_sha256','true_count'}|expected,'Prediction columns differ')
    for p,t in zip(ps,ts):
        check(int(p['true_count'])==int(t['actual_count'])==int(t['official_count'])>0,'Truth mismatch')
        check(t['method'] in {'original_sql','equivalent_exact_grouped_sql'},'Unknown audit method')
    check([int(x['query_id']) for x in ts if x['method']!='original_sql']==[59],'Expected 69 direct and one equivalent count')
    for m in ms:
        check(int(m['queries'])==70,'Query count differs')
        if m['method']=='relationship':
            check(int(m['spns'])==5 and int(m['seed']) in [1,2,3],'Baseline config differs')
        elif m['method']=='rdc_selection':
            check(int(m['spns'])==7 and int(m['seed']) in [1,2,3],'RDC config differs')
        else:check(m['method']=='postgresql','Unknown method')
        q=[]
        for p in ps:
            v=float(p[m['run_id']]);actual=int(p['true_count'])
            check(math.isfinite(v) and v>0,'Non-positive or non-finite prediction')
            q.append(max(v/actual,actual/v))
        actuals={'median_q_error':quantile(q,50),'p95_q_error':quantile(q,95),'max_q_error':max(q),'mean_q_error':statistics.mean(q)}
        for key,value in actuals.items():check(math.isclose(value,float(m[key]),rel_tol=1e-10,abs_tol=1e-9),'Metric mismatch: '+m['run_id']+' '+key)
    external=False
    if args.repo_root:
        benchmark=args.repo_root/'code/benchmarks/job-light/sql'
        sqls=(benchmark/'job_light_queries.sql').read_text().splitlines();official=load(benchmark/'job_light_true_cardinalities.csv')
        check(len(sqls)==len(official)==70,'Benchmark size differs')
        for i,(sql,p,o) in enumerate(zip(sqls,ps,official)):
            check(int(o['query_no'])==i and int(o['cardinality_true'])==int(p['true_count']),'Official truth differs')
            check(sql.strip()==o['query'].strip(),'Official SQL differs')
            check(hashlib.sha256(sql.strip().encode()).hexdigest()==p['query_sha256'],'Query hash differs')
        external=True
    paired=[]
    for seed in [1,2,3]:
        wins=0;losses=0
        for p in ps:
            t=int(p['true_count']);b=float(p['relationship_1000000_s%d'%seed]);r=float(p['rdc_1000000_s%d'%seed])
            bq=max(b/t,t/b);rq=max(r/t,t/r);wins+=rq<bq;losses+=rq>bq
        paired.append({'seed':seed,'RDC_wins':wins,'RDC_losses':losses,'ties':70-wins-losses})
    print(json.dumps({'status':'PASS','settings':14,'distinct_queries':70,'predictions_checked':980,'truth_matches':70,'official_benchmark_checked':external,'rdc_1m_comparison':paired},indent=2))
if __name__=='__main__':main()
