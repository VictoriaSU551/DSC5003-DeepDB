"""Offline derived tables for a local scalar-oracle variant, never author rankings."""
import argparse
import csv
from fractions import Fraction
import io
import math
import os
from pathlib import Path
import re

import full_scalar_oracle as core
import full_scalar_oracle_run as run
import full_scalar_oracle_audit as audit
from full_scalar_oracle import require,object_hash

ROOT=core.ROOT
OFFICIAL='code/benchmarks/job-light/sql/job_light_true_cardinalities.csv'
CONFIRMED='output/full/results/postgres_job_light.csv'
CONFIRMATION='output/full/results/postgres_job_light_verification.json'
LABEL_PINS={OFFICIAL:'87e66a3a5977d38a5e32db43451f7213776d1046f57ea2f85da854c04ba79acc',
    CONFIRMED:'c65ae65c781936be7da0be91185299d36d763082b5b5de328bc25dedb2c4dc06',
    CONFIRMATION:'614426bd8d3a1d837e5db78ef8d1ff7737ff33f9772fcbc240af9b82b931bdaf'}
SOURCE_PINS={'code/full_scalar_oracle.py':'a804301149e370eabf1055cdcb94d8157502032ab37a81e33a1b2396225964df',
    'code/full_scalar_oracle_run.py':'d5d31f3460d84942a2f22a0874f0c73bfcbbecb45a048a2ab78be76496ee9e26',
    'code/full_scalar_oracle_audit.py':'15912c8e98a620553bc861e3b6dbe1821227f6cf8779bf1ab5eba6bb225f0307'}
SOURCE_FILES=tuple(SOURCE_PINS)+('code/full_scalar_oracle_tables.py','code/tests/test_full_scalar_oracle_tables.py',
    'docs/superpowers/plans/2026-10-31-scalar-oracle-tables.md')
POLICY=dict(name='EVALUATION_ONLY_FLOOR1',floor_both_metric_operands_at=1,raw_predictions_modified=False,
    quantiles='LINEAR_INTERPOLATION_AT_(N_MINUS_1)_TIMES_P',deepdb_existing_zero_estimate_policy='ZERO_TO_INFINITY',shared_ranking=False)
AUDIT_POLICY='EVALUATION_ONLY_FLOOR_BOTH_OPERANDS_AT_1_RAW_ZERO_ESTIMATES_PRESERVED'


def integer_text(value,positive=False):
    require(type(value) is str and re.fullmatch(r'0|[1-9][0-9]*',value) is not None,'Canonical decimal integer text required')
    result=int(value);require(not positive or result>0,'Positive evaluation truth/denominator required');return result


def score_rows(contract,predictions,official,confirmed):
    queries=contract['queries'];require(len(queries)==len(predictions)==len(official)==len(confirmed)==70,'Complete70 query/estimate/label rows required')
    rows=[]
    for i,(q,p,o,g) in enumerate(zip(queries,predictions,official,confirmed)):
        require(type(q['query_no']) is int and q['query_no']==i and type(p.get('query_no')) is int and p['query_no']==i
            and o.get('query_no')==g.get('query_no')==str(i) and p.get('sql')==o.get('query')==g.get('query')==q['sql'],
            'Exact query number and SQL identity required; no reordering/token alignment')
        truth=integer_text(o['cardinality_true'],positive=True)
        require(integer_text(g['cardinality_true'],positive=True)==truth,'Official and independently confirmed truth differ')
        estimate=p.get('estimate',{});require(set(estimate)=={'numerator','denominator'},'Exact raw rational descriptor required')
        n=integer_text(estimate['numerator']);d=integer_text(estimate['denominator'],positive=True);raw=Fraction(n,d)
        require(str(raw.numerator)==estimate['numerator'] and str(raw.denominator)==estimate['denominator'],'Original canonical raw Fraction must be preserved')
        point=max(raw,Fraction(1));target=max(Fraction(truth),Fraction(1));error=max(point/target,target/point);numeric=float(error)
        require(math.isfinite(numeric),'Nonfinite q-error cannot be exported')
        rows.append(dict(query_no=i,sql=q['sql'],truth=truth,estimate_numerator=estimate['numerator'],estimate_denominator=estimate['denominator'],
            estimate_is_zero=raw==0,q_error=numeric,q_error_numerator=str(error.numerator),q_error_denominator=str(error.denominator),
            method=core.VARIANT,evaluation_policy=POLICY['name']))
    return rows


def summarize(rows):
    require(len(rows)==70,'Complete70 scored rows required')
    values=sorted(Fraction(int(r['q_error_numerator']),int(r['q_error_denominator'])) for r in rows)
    def quantile(p):
        index=(len(values)-1)*p;lo=index.numerator//index.denominator;hi=min(lo+1,len(values)-1)
        return float(values[lo]+(index-lo)*(values[hi]-values[lo]))
    return dict(queries=70,median=quantile(Fraction(1,2)),p90=quantile(Fraction(9,10)),p95=quantile(Fraction(19,20)),
        max=float(values[-1]),raw_zero_estimates=sum(r['estimate_is_zero'] for r in rows))


def csv_rows(path):
    with Path(path).open('r',encoding='utf-8-sig',newline='') as s:
        reader=csv.DictReader(s);require(reader.fieldnames is not None and len(reader.fieldnames)==len(set(reader.fieldnames)),'Unique CSV columns required')
        rows=list(reader);require(all(None not in r and None not in r.values() for r in rows),'Malformed CSV rows');return rows


def sources(root):
    for module,name in ((core,'code/full_scalar_oracle.py'),(run,'code/full_scalar_oracle_run.py'),(audit,'code/full_scalar_oracle_audit.py')):
        require(Path(module.__file__).resolve()==root/name and run.digest(root/name)==SOURCE_PINS[name],'Frozen actually loaded scalar source differs')
    require(Path(__file__).resolve()==root/'code/full_scalar_oracle_tables.py','Actually loaded table source differs')
    return {n:run.artifact(root/n,root) for n in SOURCE_FILES+(core.QUERY_FILE,)}


def accepted(proof,root):
    require(proof.get('status')=='PASS_READ_ONLY_LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY' and object_hash(proof.get('scope'))==object_hash(core.SCOPE)
        and type(proof.get('queries')) is int and proof['queries']==70 and type(proof.get('scalar_predicates')) is int and proof['scalar_predicates']==50
        and proof.get('evaluation_truth_used') is False
        and all(type(proof.get(k)) is int and proof[k]==0 for k in ('new_model_calls','new_database_calls'))
        and proof.get('qerror_policy')==AUDIT_POLICY
        and proof.get('source_boundary')=='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY',
        'Complete independently verified local scalar acceptance required')
    require(type(proof.get('binding')) is str and re.fullmatch('[0-9a-f]{64}',proof['binding']) is not None,'Exact scalar binding required')
    home=(root/proof['prediction_artifact']['path']).resolve().parent
    require(home.parent==(root/run.BASE/'runs').resolve() and home.name==proof['binding'][:20],'Scalar run namespace/binding differs')
    required=set(run.FILES)|{'final_seal.json'};records={};physical=set()
    require(isinstance(proof.get('artifacts'),list) and len(proof['artifacts'])==len(required),'Complete seven scalar artifacts required')
    for rec in proof['artifacts']:
        path=(root/rec['path']).resolve();identity=os.path.normcase(str(path))
        require(path.parent==home and path.name in required and identity not in physical and run.artifact(path,root)==rec,'Scalar artifact set/bytes/identity differs')
        physical.add(identity);records[rec['path']]=rec
    require({p.name for p in home.iterdir()}==required and all(p.is_file() for p in home.iterdir()),'Scalar physical artifact set differs')
    for key,name in (('prediction_artifact','predictions.json'),('final_seal','final_seal.json')):
        require(proof[key]==run.artifact(home/name,root),'Scalar acceptance descriptor alias differs')
    return home,records


def render(rows,summary):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    text=('# Local scalar-oracle uniform title-key variant\n\n'
        'This is not the author Perfect Selectivities implementation or configuration. It is a separately declared local method; no cross-method ranking is implied.\n\n'
        'All70 exact SQL identities use positive official truths independently confirmed by PostgreSQL11.5. Raw Fraction estimates, including zero, are unchanged. '
        '`EVALUATION_ONLY_FLOOR1` floors both operands only for q-error evaluation. The existing DeepDB policy sends a zero estimate to infinity; these policies are different.\n\n'
        '| Queries | Median | p90 | p95 | Max | Raw zero estimates |\n| ---: | ---: | ---: | ---: | ---: | ---: |\n'
        '| {queries} | {median:.12g} | {p90:.12g} | {p95:.12g} | {max:.12g} | {raw_zero_estimates} |\n\n').format(**summary)
    text+='Quantiles use linear interpolation on sorted q-errors. Historic import lineage plus current query-column snapshots do not prove original CSV all-field database identity. No database, model, inference or plot is executed by this exporter. Author-method and full-paper completion remain false.\n'
    return {'predictions_scored.csv':stream.getvalue().encode('utf-8'),'RESULTS.md':text.encode('utf-8')}


def build(directory=None,root=ROOT):
    root=Path(root).resolve();inputs=sources(root)
    proof=audit.verify(directory,root=root)  # Exactly one fresh complete offline acceptance per public entry.
    home,records=accepted(proof,root);inputs.update(records)
    for name,sha in LABEL_PINS.items():
        rec=run.artifact(root/name,root);require(rec['sha256']==sha,'Fixed independent label evidence changed');inputs[name]=rec
    pg=run.read(root/CONFIRMATION)
    require(pg.get('status')=='PASS' and type(pg.get('queries')) is int and pg['queries']==70
        and pg.get('all_official_truths_independently_matched') is True and pg.get('server_version')=='11.5'
        and pg.get('result_sha256')==inputs[CONFIRMED]['sha256'],'Independent SQL label confirmation incomplete')
    contract=core.workload(root/core.QUERY_FILE);pred=run.read(home/'predictions.json')
    require(set(pred)=={'scope','binding','queries'} and pred['binding']==proof['binding'] and object_hash(pred['scope'])==object_hash(core.SCOPE),'Accepted prediction envelope differs')
    rows=score_rows(contract,pred['queries'],csv_rows(root/OFFICIAL),csv_rows(root/CONFIRMED));summary=summarize(rows)
    identity=dict(schema='local-scalar-derived-v1',scope=core.SCOPE,metric_policy=POLICY,inputs=inputs,
        accepted_scalar=dict(status=proof['status'],binding=proof['binding'],prediction_artifact=proof['prediction_artifact'],final_seal=proof['final_seal'],
            verification=run.artifact(home/'verification.json',root),verifier_result_sha256=object_hash(proof)),source_boundary=proof['source_boundary'])
    binding=object_hash(identity);out=root/'output/full/figures'/('scalar_oracle_'+binding[:20]);payload=render(rows,summary)
    require(out.resolve()==out and root in out.resolve().parents,'Derived output must stay in its literal project namespace')
    physical=[os.path.normcase(str((root/n).resolve())) for n in inputs];require(len(physical)==len(set(physical)),'Input artifacts must be physically unique')
    for name,rec in inputs.items():require(run.artifact(root/name,root)==rec,'Input changed during scalar derivation')
    if out.exists():require({p.name for p in out.iterdir()}==set(payload)|{'manifest.json'},'Incomplete or extra prior derived output')
    else:
        out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(exist_ok=False)
        for name,data in payload.items():(out/name).write_bytes(data)
    for name,data in payload.items():require((out/name).is_file() and (out/name).read_bytes()==data and len(data)>0,'Prior derived output differs; never overwrite')
    manifest=dict(status='PASS_VERIFIED_LOCAL_SCALAR_ORACLE_DERIVED_TABLES',binding=binding,identity=identity,scope=core.SCOPE,
        accepted_scalar=identity['accepted_scalar'],metric_policy=POLICY,summary=summary,files={n:run.artifact(out/n,root) for n in payload},
        new_database_calls=0,new_model_calls=0,plot_created=False)
    manifest['self_sha256']=object_hash(manifest)
    if (out/'manifest.json').exists():require(object_hash(run.read(out/'manifest.json'))==object_hash(manifest),'Prior derived manifest differs')
    else:run.atomic(out/'manifest.json',manifest)
    return dict(status=manifest['status'],directory=out.relative_to(root).as_posix(),binding=binding,manifest=run.artifact(out/'manifest.json',root),summary=summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory');args=p.parse_args();print(build(args.directory))
