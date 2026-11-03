"""Only tiny receipts and a stub offline verifier; no actual scalar acceptance."""
import copy
import csv
from fractions import Fraction
import importlib
import io
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_scalar_oracle_tables.py'
    assert p.exists(),'Independent scalar-only table consumer is missing'
    return importlib.import_module('full_scalar_oracle_tables')


def semantic_fixture():
    queries=[dict(query_no=i,sql='SELECT COUNT(*) FROM fixed_query_'+str(i)+';') for i in range(70)]
    predictions=[dict(query_no=i,sql=q['sql'],estimate=dict(numerator='0' if i==0 else '1',denominator='1' if i==0 else '2')) for i,q in enumerate(queries)]
    labels=[dict(query_no=str(i),query=q['sql'],cardinality_true=str(i+1)) for i,q in enumerate(queries)]
    return dict(queries=queries),predictions,labels,copy.deepcopy(labels)


def test_raw_zero_and_exact_fraction_are_preserved_only_metric_operands_are_floored():
    m=module();contract,pred,official,confirmed=semantic_fixture()
    original=copy.deepcopy(pred);rows=m.score_rows(contract,pred,official,confirmed)
    assert pred==original and len(rows)==70
    assert rows[0]['estimate_numerator']=='0' and rows[0]['estimate_denominator']=='1' and rows[0]['estimate_is_zero'] is True
    assert rows[1]['estimate_numerator']=='1' and rows[1]['estimate_denominator']=='2'
    assert rows[0]['q_error']==1. and rows[1]['q_error']==2.
    assert all(r['evaluation_policy']=='EVALUATION_ONLY_FLOOR1' for r in rows)


@pytest.mark.parametrize('bad',['number','reorder','sql_space','duplicate','short','zero_truth','negative_truth','float_truth','confirmed_sql','confirmed_truth','negative_prediction','float_prediction','zero_denominator','noncanonical_fraction'])
def test_exact_70_sql_number_truth_and_rational_identity_fail_closed(bad):
    m=module();c,p,o,g=semantic_fixture()
    if bad=='number':p[1]['query_no']=1.
    if bad=='reorder':p[0],p[1]=p[1],p[0]
    if bad=='sql_space':p[0]['sql']+=' '
    if bad=='duplicate':o[1]=dict(o[0])
    if bad=='short':p.pop()
    if bad=='zero_truth':o[0]['cardinality_true']=g[0]['cardinality_true']='0'
    if bad=='negative_truth':o[0]['cardinality_true']='-1'
    if bad=='float_truth':o[0]['cardinality_true']='1.0'
    if bad=='confirmed_sql':g[0]['query']+=' '
    if bad=='confirmed_truth':g[0]['cardinality_true']='2'
    if bad=='negative_prediction':p[0]['estimate']['numerator']='-1'
    if bad=='float_prediction':p[0]['estimate']['numerator']=0.
    if bad=='zero_denominator':p[0]['estimate']['denominator']='0'
    if bad=='noncanonical_fraction':p[1]['estimate']=dict(numerator='2',denominator='4')
    with pytest.raises(ValueError):m.score_rows(c,p,o,g)


def test_summary_declares_linear_interpolated_quantiles_and_zero_count():
    m=module();c,p,o,g=semantic_fixture();rows=m.score_rows(c,p,o,g);s=m.summarize(rows)
    assert s==dict(queries=70,median=35.5,p90=63.1,p95=66.55,max=70.,raw_zero_estimates=1)


def test_large_raw_integer_is_not_rounded_and_metrics_match_the_frozen_floor_policy():
    m=module();c,p,o,g=semantic_fixture();p[2]['estimate']=dict(numerator=str(2**60+1),denominator='3')
    rows=m.score_rows(c,p,o,g)
    assert rows[2]['estimate_numerator']==str(2**60+1)
    for row in rows:
        assert row['q_error']==m.audit.qerror(Fraction(int(row['estimate_numerator']),int(row['estimate_denominator'])),row['truth'])


def fixture(tmp_path,monkeypatch):
    m=module();core=m.core;run=m.run;calls=[]
    for name in m.SOURCE_FILES:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    sql=tmp_path/core.QUERY_FILE;sql.parent.mkdir(parents=True,exist_ok=True);sql.write_bytes((ROOT/core.QUERY_FILE).read_bytes())
    c=core.workload(sql)
    labels=[dict(query_no=str(i),query=q['sql'],cardinality_true=str(i+1)) for i,q in enumerate(c['queries'])]
    def write_csv(path,rows):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w',encoding='utf-8',newline='') as s:
            w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_csv(tmp_path/m.OFFICIAL,labels);write_csv(tmp_path/m.CONFIRMED,labels)
    pg=dict(status='PASS',queries=70,all_official_truths_independently_matched=True,server_version='11.5',result_sha256=run.digest(tmp_path/m.CONFIRMED))
    run.atomic(tmp_path/m.CONFIRMATION,pg)
    monkeypatch.setattr(m,'LABEL_PINS',{n:run.digest(tmp_path/n) for n in (m.OFFICIAL,m.CONFIRMED,m.CONFIRMATION)})
    for mod,name in ((m,'code/full_scalar_oracle_tables.py'),(core,'code/full_scalar_oracle.py'),(run,'code/full_scalar_oracle_run.py'),(m.audit,'code/full_scalar_oracle_audit.py')):
        monkeypatch.setattr(mod,'__file__',str(tmp_path/name))
    binding='a'*64;home=tmp_path/run.BASE/'runs'/binding[:20];home.mkdir(parents=True)
    pred=[dict(query_no=i,sql=q['sql'],estimate=dict(numerator='0' if i==0 else '1',denominator='1' if i==0 else '2')) for i,q in enumerate(c['queries'])]
    for n in run.FILES:run.atomic(home/n,dict(fixture=n))
    run.atomic(home/'predictions.json',dict(scope=core.SCOPE,binding=binding,queries=pred))
    run.atomic(home/'final_seal.json',dict(fixture='final'))
    proof=dict(status='PASS_READ_ONLY_LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY',scope=core.SCOPE,binding=binding,queries=70,scalar_predicates=50,
        new_model_calls=0,new_database_calls=0,evaluation_truth_used=False,source_boundary='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY',
        qerror_policy='EVALUATION_ONLY_FLOOR_BOTH_OPERANDS_AT_1_RAW_ZERO_ESTIMATES_PRESERVED',
        artifacts=[run.artifact(p,tmp_path) for p in sorted(home.iterdir())],prediction_artifact=run.artifact(home/'predictions.json',tmp_path),final_seal=run.artifact(home/'final_seal.json',tmp_path))
    monkeypatch.setattr(m.audit,'verify',lambda directory=None,root=tmp_path:calls.append((directory,root)) or proof)
    return m,proof,calls,home


def test_consumer_calls_fresh_verifier_once_without_science_and_reuses_only_exact_bytes(tmp_path,monkeypatch):
    m,p,calls,home=fixture(tmp_path,monkeypatch)
    import socket,subprocess,sqlite3
    def forbidden(*a,**k):pytest.fail('Derived tables attempted scientific/process/database work')
    monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(socket,'create_connection',forbidden);monkeypatch.setattr(sqlite3,'connect',forbidden)
    monkeypatch.setattr(m.run,'collect',forbidden);monkeypatch.setattr(m.run,'connect',forbidden);monkeypatch.setattr(m.core,'predictions',forbidden)
    before={n:(x.read_bytes(),x.stat().st_mtime_ns) for n,x in ((x.name,x) for x in home.iterdir())}
    result=m.build(root=tmp_path)
    assert len(calls)==1 and calls[0][1]==tmp_path
    out=tmp_path/result['directory'];assert {x.name for x in out.iterdir()}=={'predictions_scored.csv','RESULTS.md','manifest.json'}
    manifest=m.run.read(out/'manifest.json')
    assert manifest['status']=='PASS_VERIFIED_LOCAL_SCALAR_ORACLE_DERIVED_TABLES' and manifest['scope']==m.core.SCOPE
    assert manifest['accepted_scalar']['final_seal']==p['final_seal'] and manifest['accepted_scalar']['binding']==p['binding']
    assert manifest['metric_policy']['name']=='EVALUATION_ONLY_FLOOR1'
    assert manifest['summary']['median']==35.5 and manifest['summary']['raw_zero_estimates']==1
    with (out/'predictions_scored.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==70 and rows[0]['estimate_numerator']=='0'
    text=(out/'RESULTS.md').read_text(encoding='utf-8')
    assert 'not the author Perfect Selectivities' in text and 'DeepDB' in text and 'infinity' in text
    out_before={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in out.iterdir()}
    assert m.build(root=tmp_path)==result and len(calls)==2
    assert out_before=={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in out.iterdir()}
    assert before=={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in home.iterdir()}


@pytest.mark.parametrize('bad',['status','scope','truth_flag','model_calls','db_calls','missing_artifact','duplicate_artifact','receipt_hash','policy','query_type','source_boundary'])
def test_wrong_or_incomplete_parent_is_refused_without_export(tmp_path,monkeypatch,bad):
    m,p,calls,home=fixture(tmp_path,monkeypatch)
    if bad=='status':p['status']='PASS'
    if bad=='scope':p['scope']=dict(p['scope'],author_method_configuration_identified=True)
    if bad=='truth_flag':p['evaluation_truth_used']=True
    if bad=='model_calls':p['new_model_calls']=1
    if bad=='db_calls':p['new_database_calls']=True
    if bad=='missing_artifact':p['artifacts'].pop()
    if bad=='duplicate_artifact':p['artifacts'][0]=p['artifacts'][1]
    if bad=='receipt_hash':p['artifacts'][0]=dict(p['artifacts'][0],sha256='0'*64)
    if bad=='policy':p['qerror_policy']='OLD_DEEPDB_ZERO_TO_INFINITY'
    if bad=='query_type':p['queries']=70.
    if bad=='source_boundary':p['source_boundary']='ORIGINAL_CSV_FULL_IDENTITY_PROVEN'
    with pytest.raises(ValueError):m.build(root=tmp_path)
    assert len(calls)==1 and not (tmp_path/'output/full/figures').exists()


@pytest.mark.parametrize('bad',['label','confirmation','source','output','output_extra','output_empty','output_self_resealed'])
def test_label_source_and_export_tampering_are_never_silently_reused(tmp_path,monkeypatch,bad):
    m,p,calls,home=fixture(tmp_path,monkeypatch);result=m.build(root=tmp_path);out=tmp_path/result['directory']
    if bad=='label':(tmp_path/m.OFFICIAL).write_text('changed')
    if bad=='confirmation':(tmp_path/m.CONFIRMATION).write_text('{}')
    if bad=='source':(tmp_path/'code/full_scalar_oracle_audit.py').write_text('changed')
    if bad=='output':(out/'predictions_scored.csv').write_text('changed')
    if bad=='output_extra':(out/'private').write_text('must fail')
    if bad=='output_empty':(out/'RESULTS.md').write_bytes(b'')
    if bad=='output_self_resealed':
        (out/'RESULTS.md').write_text('changed');v=m.run.read(out/'manifest.json');v['files']['RESULTS.md']=m.run.artifact(out/'RESULTS.md',tmp_path)
        v['self_sha256']=m.core.object_hash({k:x for k,x in v.items() if k!='self_sha256'});m.run.atomic(out/'manifest.json',v)
    with pytest.raises(ValueError):m.build(root=tmp_path)


def test_missing_acceptance_is_refused_without_outputs(tmp_path,monkeypatch):
    m,p,calls,home=fixture(tmp_path,monkeypatch)
    def missing(*a,**k):raise ValueError('No accepted result')
    monkeypatch.setattr(m.audit,'verify',missing)
    with pytest.raises(ValueError):m.build(root=tmp_path)
    assert not (tmp_path/'output/full/figures').exists()


def test_redirected_output_parent_is_rejected_before_any_write(tmp_path,monkeypatch):
    m,p,calls,home=fixture(tmp_path,monkeypatch);resolve=Path.resolve;outside=tmp_path.parent/'not_ours'
    def redirected(path,*a,**k):
        if path.parent==tmp_path/'output/full/figures' and path.name.startswith('scalar_oracle_'):return outside
        return resolve(path,*a,**k)
    monkeypatch.setattr(Path,'resolve',redirected)
    with pytest.raises(ValueError):m.build(root=tmp_path)
    assert not (tmp_path/'output/full/figures').exists() and not outside.exists()
