"""Pure derived-result tests; the scientific verifier is always substituted."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def tables():
    assert importlib.util.find_spec('full_verdict_ssb_local_tables') is not None, \
        'the thin LOCAL Verdict tables exporter must exist'
    return importlib.import_module('full_verdict_ssb_local_tables')


NAMES = ('Q1.1','Q1.2','Q1.3','Q2.1','Q2.2','Q2.3','Q3.1',
         'Q3.2','Q3.3','Q3.4','Q4.1','Q4.2','Q4.3')


def population(key, mode, point=8., truth=10., status='MATCHED'):
    return dict(key=[str(key)], status=status, truth=truth, prediction=point,
        zero_truth=truth == 0, absolute_error=None if point is None else abs(point-truth),
        relative_error=None if point is None or not truth else abs(point/truth-1),
        missing_penalty_relative_error=1. if status == 'MISSING_MODEL_GROUP' else None,
        native_ci95=[6.,10.] if mode == 'subsampling' and point is not None else None,
        native_ci95_covers_truth=True if mode == 'subsampling' and point is not None else None,
        native_ci_status='FINITE' if mode == 'subsampling' else 'NOT_REQUESTED',
        point_status='FINITE' if point is not None else 'MISSING_GROUP', engine_error=None)


def evaluation(counts=None):
    counts = counts or [1]*13
    comparisons, adapters = [], []
    for mode in ('nobound','subsampling'):
        for qno, name in enumerate(NAMES):
            native = []
            roles = ('RAW',) if qno < 10 else ('RAW','SUM_REVENUE','SUM_SUPPLYCOST')
            for role in roles:
                sql = 'SELECT %d /* %s %s */;' % (qno,role,mode)
                call = dict(call_id=name+'.'+role.lower()+'.'+mode, query_no=qno,
                    query_id=name,group_width=1,role=role,mode=mode,sql=sql,
                    sql_sha256=hashlib.sha256(sql.encode()).hexdigest())
                rows = [dict(key=[str(i)],point=4. if role == 'RAW' else 12. if role == 'SUM_REVENUE' else 4.,
                    point_status='FINITE', interval95=[2.,14.] if mode == 'subsampling' else None,
                    halfwidth95=6. if mode == 'subsampling' else None,
                    ci_status='FINITE' if mode == 'subsampling' else 'NOT_REQUESTED',raw_cells=['fixture']) for i in range(counts[qno])]
                native.append(dict(call=call,labels=['key','value'],rows=rows,error=None,
                    elapsed_ns=12345,status='RETURNED',usable_for_point_comparison=True))
                if role == 'RAW':
                    groups = [population(i,mode,point=8. if qno < 10 else 4.) for i in range(counts[qno])]
                    sample = [dict(key=[str(i)],status='MATCHED',expected=8.,prediction=g['prediction'],
                        numeric_gate_pass=qno < 10,engine_error=None) for i,g in enumerate(groups)]
                    comparisons.append(dict(call=call,sample_oracle_status='AVAILABLE_EXACT_RETAINED_EXPRESSION_SUM',
                        sample_groups=sample,population_status='AVAILABLE_LOCAL_FULL_EXPRESSION_TRUTH',population_groups=groups))
                else:
                    comparisons.append(dict(call=call,sample_oracle_status='UNAVAILABLE_COMPONENT_SUM_NOT_STORED',
                        sample_groups=None,population_status='UNAVAILABLE_NO_MATCHING_COMPONENT_TRUTH',population_groups=None))
            if qno >= 10:
                groups = [population(i,'nobound') for i in range(counts[qno])]
                for g in groups:g['native_ci_status']='UNSUPPORTED_NO_COVARIANCE_MODEL'
                adapters.append(dict(query_no=qno,mode=mode,
                    adapter=dict(status='POINT_ADAPTER_RETURNED',query_no=qno,mode=mode,
                        raw_compound=native[0],children=native[1:],
                        groups=[dict(key=g['key'],point=8.,status='MATCHED',method='TWO_ORIGINAL_SUM_POINT_ADAPTER',
                            interval95=None,ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL') for g in groups],
                        ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL'),
                    sample_groups=[dict(key=g['key'],status='MATCHED',expected=8.,prediction=8.,numeric_gate_pass=True,engine_error=None) for g in groups],
                    population_groups=groups,combined_ci='UNSUPPORTED_NO_COVARIANCE_MODEL'))
    return dict(status='PASS_LOCAL_VERDICT_SAMPLE_SCALING_WITH_EXPLICIT_GAPS',point_gate_pass=True,
        comparisons=comparisons,adapters=adapters,original_calls=38,engine_error_calls=0,
        native_ci_rows=sum(counts[:10])+3*sum(counts[10:]),unavailable_native_ci_rows=0,
        scope='LOCAL_SSB_SF500_VERDICT_EXISTING_SAMPLE',author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,
        timing_scope='Existing retained sample; no original3B sampling/end-to-end measurement')


def test_full_shape_and_raw_profit_leak_stay_separate(tables):
    counts = [1,1,1,56,7,7,601,100,11,2,500,650,122]
    result = tables.derive(evaluation(counts))
    assert len(result['query_summary']) == 32
    assert len(result['raw_groups']) == 4118
    assert len(result['adapter_groups']) == 2*sum(counts[10:])
    assert len(result['physical_calls']) == 38
    summaries = result['query_summary']
    raw = next(r for r in summaries if r['query']=='Q4.1' and r['mode']=='nobound' and r['result_kind']=='RAW')
    adapted = next(r for r in summaries if r['query']=='Q4.1' and r['mode']=='nobound' and r['result_kind']=='POINT_ADAPTER')
    assert raw['mean_relative_error_with_missing_penalty'] == pytest.approx(.6)
    assert adapted['mean_relative_error_with_missing_penalty'] == pytest.approx(.2)
    assert raw['sample_gate_component'] is False and adapted['sample_gate_component'] is True
    assert raw['sample_numeric_gate_pass'] is False and adapted['sample_numeric_gate_pass'] is True
    assert result['sample_gate_pass'] is True
    assert all(r['native_ci95'] is None and r['native_ci_confidence'] is None for r in result['adapter_groups'])
    assert all(r['native_ci_confidence'] == .95 for r in result['raw_groups'] if r['mode']=='subsampling')
    component = next(r for r in result['physical_calls'] if r['role']=='SUM_REVENUE')
    assert component['sample_relative_error'] is None and component['population_relative_error'] is None
    assert component['sample_oracle_status']=='UNAVAILABLE_COMPONENT_SUM_NOT_STORED'
    assert json.loads(component['native_rows_json'])[0]['point'] == 12.
    assert next(r for r in result['physical_calls'] if r['query']=='Q1.1')['native_elapsed_ns'] is None


def test_missing_extra_zero_and_conditional_denominators_are_explicit(tables):
    groups = [population('match','nobound'),population('missing','nobound',point=None,status='MISSING_MODEL_GROUP')]
    rows, summary = tables.summarize_groups(groups,[],query='Q1.1',mode='nobound',kind='RAW')
    assert summary['truth_groups']==2 and summary['missing_groups']==1
    assert summary['mean_relative_error_with_missing_penalty']==pytest.approx(.6)
    assert summary['conditional_matched_mean_relative_error']==pytest.approx(.2)
    extra = population('extra','nobound');extra.update(truth=None,zero_truth=False,relative_error=None,absolute_error=None,status='EXTRA_MODEL_GROUP')
    rows, summary = tables.summarize_groups(groups+[extra],[],query='Q1.1',mode='nobound',kind='RAW')
    assert len(rows)==3 and summary['truth_groups']==2 and summary['extra_groups']==1
    zero = population('zero','nobound',truth=0.,point=0.)
    rows, summary = tables.summarize_groups(groups+[zero],[],query='Q1.1',mode='nobound',kind='RAW')
    assert len(rows)==3 and summary['zero_truth_groups']==1
    assert summary['mean_relative_error_with_missing_penalty'] is None
    assert summary['mean_status']=='UNDEFINED_ZERO_TRUTH'


@pytest.mark.parametrize('point,status',[(None,'NONFINITE'),(float('nan'),'NONFINITE'),(float('inf'),'NONFINITE')])
def test_invalid_points_are_records_and_suppress_all_truth_mean(tables,point,status):
    g=population('bad','nobound',point=None);g.update(prediction=point,point_status=status,status='MATCHED')
    rows, summary=tables.summarize_groups([g],[],query='Q1.1',mode='nobound',kind='RAW')
    assert len(rows)==1 and rows[0]['point_status']=='NONFINITE'
    assert summary['invalid_predictions']==1 and summary['mean_relative_error_with_missing_penalty'] is None


def test_engine_error_diagnostics_never_become_valid_accuracy(tables):
    g=population('partial','subsampling');g['engine_error']='original failure after partial rows'
    rows, summary=tables.summarize_groups([g],[],query='Q1.1',mode='subsampling',kind='RAW')
    assert rows[0]['engine_error']==g['engine_error'] and rows[0]['native_ci95']==[6.,10.]
    assert rows[0]['scored_relative_error'] is None
    assert summary['mean_status']=='ENGINE_ERROR'
    assert summary['conditional_matched_mean_relative_error'] is None


def test_failed_scientific_scaling_is_valid_negative_evidence(tables):
    report=evaluation();report['comparisons'][0]['sample_groups'][0]['numeric_gate_pass']=False
    report['comparisons'][0]['population_groups'][0]['engine_error']='native query failure'
    report.update(point_gate_pass=False,status='FAIL_LOCAL_VERDICT_SAMPLE_SCALING',engine_error_calls=1)
    result=tables.derive(report)
    assert result['sample_gate_pass'] is False
    assert result['query_summary'][0]['mean_status']=='ENGINE_ERROR'
    assert result['query_summary'][0]['mean_relative_error_with_missing_penalty'] is None


@pytest.mark.parametrize('mutation',['duplicate_call','missing_call','duplicate_adapter','missing_adapter','component_truth','gate','scope'])
def test_changed_layout_scope_or_gate_is_rejected(tables,mutation):
    report=evaluation()
    if mutation=='duplicate_call':report['comparisons'][-1]=copy.deepcopy(report['comparisons'][0])
    if mutation=='missing_call':report['comparisons'].pop()
    if mutation=='duplicate_adapter':report['adapters'][-1]=copy.deepcopy(report['adapters'][0])
    if mutation=='missing_adapter':report['adapters'].pop()
    if mutation=='component_truth':next(r for r in report['comparisons'] if r['call']['role']!='RAW')['population_groups']=[]
    if mutation=='gate':report['point_gate_pass']=False
    if mutation=='scope':report['author_reproduction_complete']=True
    with pytest.raises(ValueError):tables.derive(report)


def export_fixture(tmp_path,monkeypatch,tables):
    root=tmp_path/'project';home=root/'output/full/verdict_ssb/local_sf500/runs/fresh_v10';home.mkdir(parents=True)
    code=root/'code';code.mkdir();(code/'full_verdict_ssb_local_tables.py').write_bytes(Path(tables.__file__).read_bytes())
    monkeypatch.setattr(tables,'ROOT',root)
    report=evaluation();path=home/'evaluation.json';path.write_text(json.dumps(report),encoding='utf-8')
    for name in ('final.json','plan.json'):(home/name).write_bytes(b'{}')
    def descriptor(p):return dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    accepted=dict(status='PASS_READONLY_LOCAL_VERDICT_EVIDENCE_WITH_AUTHOR_MISMATCH',scope=report['scope'],
        evaluation_status=report['status'],point_gate_pass=True,original_calls=38,population_rows=3000028242,sample_rows=9996946,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        database_connected=False,processes_executed=False,scientific_calls_executed=False,
        evaluation=descriptor(path),final=descriptor(home/'final.json'),plan=descriptor(home/'plan.json'))
    calls=[]
    def verify(p):calls.append(p);return copy.deepcopy(accepted)
    monkeypatch.setitem(sys.modules,'full_verdict_ssb_local_run',SimpleNamespace(verify=verify))
    return SimpleNamespace(root=root,home=home,path=path,accepted=accepted,calls=calls,report=report)


def test_export_verifies_once_and_copies_only_byte_exact_derived_outputs(tmp_path,monkeypatch,tables):
    f=export_fixture(tmp_path,monkeypatch,tables)
    result=tables.export('fresh_v10')
    assert f.calls==[f.home]
    manifest=json.loads((f.root/result['manifest']['path']).read_text())
    assert manifest['row_counts']==dict(query_summary=32,raw_groups=26,adapter_groups=6,physical_calls=38)
    assert manifest['author_different_groups']==1713 and manifest['full_paper_reproduction_complete'] is False
    assert manifest['source_acceptance']==f.accepted
    assert len(result['public_files'])==6
    for item in result['public_files']:
        target=f.root/item['path'];source=f.root/item['source']['path']
        assert target.read_bytes()==source.read_bytes()
        assert hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']
    assert b'native 95%' in (f.root/'output/results/fullpaper_verdict_ssb_local500_RESULTS.md').read_bytes()
    assert b'no covariance' in (f.root/'output/results/fullpaper_verdict_ssb_local500_RESULTS.md').read_bytes()


@pytest.mark.parametrize('mutation',['bytes','sha','outside','name','author','calls','evaluation_status'])
def test_bad_acceptance_or_evaluation_descriptor_fails_before_writes(tmp_path,monkeypatch,tables,mutation):
    f=export_fixture(tmp_path,monkeypatch,tables)
    if mutation=='bytes':f.accepted['evaluation']['bytes']+=1
    if mutation=='sha':f.accepted['evaluation']['sha256']='0'*64
    if mutation=='outside':f.accepted['evaluation']['path']='elsewhere/evaluation.json'
    if mutation=='name':f.accepted['evaluation']['path']=f.accepted['final']['path']
    if mutation=='author':f.accepted['author_reproduction_complete']=True
    if mutation=='calls':f.accepted['original_calls']=37
    if mutation=='evaluation_status':f.accepted['evaluation_status']='other'
    with pytest.raises(ValueError):tables.export('fresh_v10')
    assert len(f.calls)==1 and not (f.root/'output/full/figures').exists()


def test_fresh_verifier_error_propagates_without_export_or_fallback(tmp_path,monkeypatch,tables):
    f=export_fixture(tmp_path,monkeypatch,tables);failure=ValueError('complete source F rejected')
    def verify(p):f.calls.append(p);raise failure
    monkeypatch.setitem(sys.modules,'full_verdict_ssb_local_run',SimpleNamespace(verify=verify))
    with pytest.raises(ValueError) as observed:tables.export('fresh_v10')
    assert observed.value is failure and f.calls==[f.home]
    assert not (f.root/'output/full/figures').exists()


def test_evaluation_changed_during_derivation_fails_before_output(tmp_path,monkeypatch,tables):
    f=export_fixture(tmp_path,monkeypatch,tables);original=tables.derive
    def changed(report):
        result=original(report);f.path.write_bytes(b'changed after acceptance');return result
    monkeypatch.setattr(tables,'derive',changed)
    with pytest.raises(ValueError,match='physical bytes/SHA'):tables.export('fresh_v10')
    assert len(f.calls)==1 and not (f.root/'output/full/figures').exists()


def test_repeated_export_still_verifies_and_rejects_changed_immutable_bundle(tmp_path,monkeypatch,tables):
    f=export_fixture(tmp_path,monkeypatch,tables);result=tables.export('fresh_v10')
    assert tables.export('fresh_v10')==result and len(f.calls)==2
    directory=(f.root/result['manifest']['path']).parent
    (directory/'raw_groups.csv').write_bytes(b'changed')
    with pytest.raises(ValueError,match='existing derived'):tables.export('fresh_v10')
    assert len(f.calls)==3


def test_unsafe_run_name_fails_before_verifier(tmp_path,monkeypatch,tables):
    f=export_fixture(tmp_path,monkeypatch,tables)
    with pytest.raises(ValueError):tables.export('../failed_v9')
    assert f.calls==[]
