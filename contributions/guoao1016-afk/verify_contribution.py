"""Verify the published evidence offline using only the Python standard library.

This checks saved artifacts, not a fresh model replay or fresh database query.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

BASE=Path(__file__).resolve().parent

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def read_json(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def percentile(values,p):
    values=sorted(values);position=(len(values)-1)*p/100
    lower=math.floor(position);upper=math.ceil(position)
    return values[lower]+(values[upper]-values[lower])*(position-lower)

def q_error(estimate,truth):
    estimate=float(estimate);truth=float(truth)
    assert math.isfinite(estimate) and math.isfinite(truth) and estimate>0 and truth>0
    return max(estimate/truth,truth/estimate)

def main():
    seed_summary=read_json(BASE/'results/seed_summary.json')
    assert len(seed_summary['runs'])==9
    canonical=None;models={};predictions={}
    for seed in [1,2,3]:
        for size in [10000,100000,1000000]:
            folder=BASE/'results/seed_runs'/('seed_%d'%seed)/('samples_%d'%size)
            rows=read_csv(folder/('job_light_%d.csv'%size))
            saved=read_json(folder/('verification_%d.json'%size))
            assert saved['status']=='PASS' and saved['queries']==saved['replayed_predictions']==70
            assert len(rows)==70 and [int(r['query_no']) for r in rows]==list(range(70))
            workload=[(r['query'].strip(),int(float(r['cardinality_true']))) for r in rows]
            if canonical is None:canonical=workload
            assert workload==canonical
            qs=[q_error(r['cardinality_predict'],r['cardinality_true']) for r in rows]
            for p in [50,95,100]:assert math.isclose(percentile(qs,p),saved['q_error'][str(p)],rel_tol=1e-8,abs_tol=1e-8)
            entry=next(r for r in seed_summary['runs'] if r['seed']==seed and r['samples']==size)
            for p,key in [(50,'median'),(95,'p95'),(100,'maximum')]:assert math.isclose(percentile(qs,p),entry[key],rel_tol=1e-8)
            models[(seed,size)]=saved['model_sha256']
            for i,r in enumerate(rows):predictions[(seed,size,i)]=float(r['cardinality_predict'])
    for size in [10000,100000,1000000]:assert len({models[(seed,size)] for seed in [1,2,3]})==3
    pg=read_csv(BASE/'results/postgresql/postgresql_estimates.csv')
    plans=read_json(BASE/'results/postgresql/explain_plans.json')
    pg_summary=read_json(BASE/'results/postgresql/comparison_verification.json')
    assert len(pg)==len(plans)==70 and pg_summary['status']=='PASS'
    for i,(r,p) in enumerate(zip(pg,plans)):
        assert int(r['query_no'])==p['query_no']==i
        assert (r['query'].strip(),int(r['cardinality_true']))==canonical[i]
        top=p['explain']['Plan'];assert top['Node Type']=='Aggregate' and top['Plan Rows']==1
        assert float(top['Plans'][0]['Plan Rows'])==float(r['cardinality_predict'])
        assert math.isclose(q_error(r['cardinality_predict'],r['cardinality_true']),float(r['q_error']),rel_tol=1e-8)
    for p in [50,95,100]:assert math.isclose(percentile([float(r['q_error']) for r in pg],p),pg_summary['postgres_q_error'][str(p)],rel_tol=1e-8)
    paired=read_csv(BASE/'results/postgresql/matched_comparison.csv');assert len(paired)==630
    keys=set()
    for r in paired:
        key=(int(r['seed']),int(r['samples']),int(r['query_no']));assert key not in keys;keys.add(key)
        assert float(r['deepdb_estimate'])==predictions[key]
        assert float(r['postgres_estimate'])==float(pg[key[2]]['cardinality_predict'])
    audit=read_csv(BASE/'results/truth_audit/truth_counts.csv')
    attempts=[json.loads(line) for line in (BASE/'results/truth_audit/attempts.jsonl').read_text().splitlines() if line.strip()]
    latest={r['query_no']:r for r in attempts}
    assert len(audit)==70
    for i,r in enumerate(audit):
        assert int(r['query_no'])==i and r['status']=='MATCH' and int(r['difference'])==0
        assert (r['sql'].strip(),int(r['actual_count']))==canonical[i]
        assert int(r['official_count'])==int(r['actual_count'])==latest[i]['actual_count']
        if i==59:assert r['execution_method']=='factorized_exact_sql' and r['executed_sql']!=r['sql']
        else:assert r['execution_method']=='original_sql' and r['executed_sql']==r['sql']
    proof=read_json(BASE/'results/truth_audit/verification.json')
    assert proof['status']=='PASS' and proof['original_sql_successes']==69 and proof['factorized_query_ids']==[59]
    cross=read_json(BASE/'results/truth_audit/factorized_cross_checks.json')
    assert [r['query_no'] for r in cross]==[0,14,34,57]
    assert all(r['grouped_count']==r['original_count']==canonical[r['query_no']][1] for r in cross)
    canonical_counts=read_csv(BASE/'results/truth_audit/job_light_recomputed_cardinalities.csv')
    assert len(canonical_counts)==70
    assert [(r['query'].strip(),int(r['cardinality_true'])) for r in canonical_counts]==canonical
    manifest=read_csv(BASE/'MANIFEST.csv')
    actual_files={p.relative_to(BASE).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.name!='MANIFEST.csv'}
    assert {r['file'] for r in manifest}==actual_files
    for r in manifest:
        content=(BASE/r['file']).read_bytes()
        assert len(content)==int(r['bytes']) and hashlib.sha256(content).hexdigest()==r['sha256']
    print('PASS: nine saved model runs, 70 PostgreSQL plans, 630 pairings, 70 actual counts (69 raw + 1 equivalent), four grouped-count cross-checks, and published file hashes.')

if __name__=='__main__':main()
