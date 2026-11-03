"""Only synthetic score rows/receipts and counted stub acceptance; no live audit."""
import copy
from fractions import Fraction
import importlib.util
import json
import csv
import hashlib
import io
import builtins
from types import SimpleNamespace
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_job_sampling_tables.py'
    assert path.is_file(),'Independent sampling table consumer missing'
    spec=importlib.util.spec_from_file_location('sampling_tables_test',str(path))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def inputs(method='SRS'):
    sqls=['SELECT COUNT(*) FROM title t WHERE t.production_year='+str(1900+i)+';' for i in range(70)]
    predictions=[dict(query_no=i,sql=sql,status='COMPLETE',raw_prediction=dict(numerator='10',denominator='1'),
        wall_seconds=.01,sql_roundtrips=3,id_attempts={'title':1000},**({'charged_logical_lookups':1000} if method=='IBJS' else {})) for i,sql in enumerate(sqls)]
    labels=[dict(query_no=str(i),query=sql,cardinality_true='10') for i,sql in enumerate(sqls)]
    return sqls,predictions,labels,copy.deepcopy(labels)


def test_raw_zero_is_infinite_while_null_is_unfinished_and_all70_rows_survive():
    m=module();sqls,p,o,g=inputs();p[0].update(status='COMPLETE_ZERO',raw_prediction=dict(numerator='0',denominator='1'))
    p[1].update(status='QUERY_WALL_BUDGET',raw_prediction=None)
    before=copy.deepcopy(p);rows=m.score_rows('SRS',sqls,p,o,g);summary=m.summarize(rows)
    assert p==before and len(rows)==70
    assert rows[0]['q_error']=='Infinity' and rows[0]['metric_status']=='POSITIVE_TRUTH_ZERO_INFINITY'
    assert rows[0]['raw_numerator']=='0' and rows[0]['raw_denominator']=='1'
    assert rows[1]['q_error'] is None and rows[1]['metric_status']=='UNFINISHED'
    assert summary['whole70'] is None and summary['unfinished']==summary['raw_zero']==1
    assert summary['completed']==69 and summary['conditional_finite']['queries']==68
    assert summary['status_counts']=={'COMPLETE':68,'COMPLETE_ZERO':1,'QUERY_WALL_BUDGET':1}
    assert rows[0]['physical_rows_scanned'] is None and rows[0]['physical_rows_scanned_unknown'] is True


def test_complete70_includes_infinity_without_floor1_or_conditional_replacement():
    m=module();sqls,p,o,g=inputs();p[-1].update(status='COMPLETE_ZERO',raw_prediction=dict(numerator='0',denominator='1'))
    rows=m.score_rows('SRS',sqls,p,o,g);s=m.summarize(rows)
    assert s['whole70']['queries']==70 and s['whole70']['max']['value']=='Infinity'
    assert s['whole70']['median']['value']=='1' and s['whole70']['p95']['value']=='1'
    assert s['conditional_finite']['queries']==69 and s['raw_zero']==1
    assert json.loads(json.dumps(s,allow_nan=False))==s


def test_extended_quantile_does_not_multiply_zero_by_infinity():
    m=module();values=[Fraction(1),m.INFINITY]
    assert m.quantile(values,Fraction(0))['value']=='1'
    assert m.quantile(values,Fraction(1,2))['value']=='Infinity'
    assert m.quantile([m.INFINITY,m.INFINITY],Fraction(0))['value']=='Infinity'
    assert m.quantile([Fraction(1),Fraction(3)],Fraction(1,4))['value']=='3/2'


@pytest.mark.parametrize('damage',['sql','number','label_sql','confirmed_truth','missing','extra','null_complete','value_unfinished','negative','noncanonical'])
def test_exact70_sql_label_and_terminal_fraction_contract(damage):
    m=module();sqls,p,o,g=inputs()
    if damage=='sql':p[3]['sql']+=' '
    elif damage=='number':p[3]['query_no']=4
    elif damage=='label_sql':o[3]['query']+=' '
    elif damage=='confirmed_truth':g[3]['cardinality_true']='11'
    elif damage=='missing':p.pop()
    elif damage=='extra':p.append(copy.deepcopy(p[3]))
    elif damage=='null_complete':p[3]['raw_prediction']=None
    elif damage=='value_unfinished':p[3]['status']='QUERY_ERROR'
    elif damage=='negative':p[3]['raw_prediction']['numerator']='-1'
    elif damage=='noncanonical':p[3]['raw_prediction']=dict(numerator='20',denominator='2')
    with pytest.raises(ValueError):m.score_rows('SRS',sqls,p,o,g)


def test_ibjs_completed_fallback_costs_and_local_tag_are_preserved():
    m=module();sqls,p,o,g=inputs('IBJS');p[0]['status']='STOP_AFTER_COMPLETE';p[0]['raw_prediction']=dict(numerator='21',denominator='2')
    rows=m.score_rows('IBJS',sqls,p,o,g)
    assert rows[0]['raw_numerator']=='21' and rows[0]['raw_denominator']=='2'
    assert rows[0]['q_error']=='21/20' and rows[0]['charged_logical_lookups']==1000
    assert rows[0]['method']=='LOCAL_JOB70_IBJS_SQL_N1000_B100K'
    assert rows[0]['author_configuration_identified'] is False and rows[0]['shared_author_ranking'] is False


@pytest.mark.parametrize('damage',['wall','sql','attempt','lookup'])
def test_incomplete_query_cost_records_are_rejected(damage):
    m=module();sqls,p,o,g=inputs('IBJS')
    if damage=='wall':p[0]['wall_seconds']=float('nan')
    elif damage=='sql':p[0]['sql_roundtrips']=-1
    elif damage=='attempt':p[0]['id_attempts']={'title':False}
    else:del p[0]['charged_logical_lookups']
    with pytest.raises(ValueError):m.score_rows('IBJS',sqls,p,o,g)


def sealed_fixture(tmp_path,monkeypatch,methods=('SRS','IBJS'),unfinished=False):
    m=module();root=tmp_path/'project';root.mkdir();calls=[];proofs={};homes={}
    def put(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True),encoding='utf-8')
    def record(path):return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    sqls,_,official,confirmed=inputs()
    workload=root/'queries.sql';workload.write_text('\n'.join(sqls)+'\n',encoding='utf-8')
    pins={}
    for name,data in [('official.csv',official),('confirmed.csv',confirmed)]:
        path=root/name;stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=list(data[0]));w.writeheader();w.writerows(data);path.write_bytes(stream.getvalue().encode('utf-8'))
        pins[name]=record(path)['sha256']
    confirmation=root/'confirmation.json';put(confirmation,dict(status='PASS',queries=70,all_official_truths_independently_matched=True,server_version='11.5',result_sha256=pins['confirmed.csv']))
    monkeypatch.setattr(m,'QUERY_FILE','queries.sql');monkeypatch.setattr(m,'QUERY_SHA',record(workload)['sha256'])
    monkeypatch.setattr(m,'LABEL_FILES',dict(official=('official.csv',pins['official.csv']),confirmed=('confirmed.csv',pins['confirmed.csv']),confirmation=('confirmation.json',record(confirmation)['sha256'])))
    source=root/'source.py';source.write_text('# fixture source\n',encoding='utf-8')
    monkeypatch.setattr(m,'sources',lambda root,methods:{'source.py':record(source)})
    for method in methods:
        _,pred,_,_=inputs(method)
        if unfinished:pred[1].update(status='QUERY_WALL_BUDGET',raw_prediction=None)
        pred[0].update(status='COMPLETE_ZERO' if method=='SRS' else 'ZERO_SAMPLE',raw_prediction=dict(numerator='0',denominator='1'))
        scope=m.expected_scope(method);plan=dict(scope=scope,config=m.expected_config(method),dependencies={'fixture':'never live'},contract={'queries':[dict(query_no=i,sql=s) for i,s in enumerate(sqls)]})
        plan['binding']=m.object_hash(plan);binding=plan['binding'];home=root/m.METHODS[method]['base']/'runs'/binding[:20];homes[method]=home
        put(home/'plan.json',plan);put(home/'approval.json',{'fixture':True})
        for p in pred:
            if method=='SRS':p['sample_cardinality']=0 if p['query_no']==0 else None if p['raw_prediction'] is None else 1
            kinds=['savepoint','base_lookup/title','release'] if method=='SRS' else ['base_lookup/title','ibjs_count/title','ibjs_kth/title']
            q=dict(p,operations=[dict(kind=k,seconds=.001,status='PASS',cleanup=False) for k in kinds]);f=home/'queries'/('query_%02d.json'%p['query_no']);put(f,q)
            put(f.with_suffix('.seal.json'),dict(binding=binding,query_no=p['query_no'],artifact=record(f)))
        times=dict(before_projection_seconds=1.,live_population_metadata_seconds=1.,all_online_queries_and_leaf_checkpoint_seconds=1.,after_projection_seconds=1.)
        projection={t:dict(binary_copy=dict(bytes=100,sha256='a'*64)) for t in m.TABLES}
        collection=dict(binding=binding,scope=scope,client_pid=17,seconds=4.,timings=times,before=projection,after=projection,
            common_operations=[dict(seconds=.001) for _ in range(17 if method=='SRS' else 19)])
        put(home/'collection.json',collection)
        predictions=dict(binding=binding,scope=scope,queries=pred);put(home/'predictions.json',predictions)
        execution=dict(binding=binding,client_pid=17,admission_physical_validation_seconds=.1,collection_and_checkpoint_seconds=4.,fresh_postflight_physical_validation_seconds=.1,
            offline_math_prepublication_validation_seconds=.1,measured_client_wall_seconds_before_final_records=4.3,
            final_record_and_seal_io_in_external_command_wall_only=True,root_external_command_wall_required_for_end_to_end_latency=True)
        put(home/'execution.json',execution)
        verification=dict(binding=binding,scope=scope,queries=70,completed_queries=69 if unfinished else 70,incomplete_queries=1 if unfinished else 0,raw_zero_queries=1,
            common_sql_roundtrips=m.METHODS[method]['common_sql'],common_sql_roundtrips_breakdown={('recorded_setup_identity_metadata_reset' if method=='SRS' else 'recorded_setup_identity_metadata_indexes_reset'):17 if method=='SRS' else 19,'schema_checks':36,'streaming_copy':12},
            online_query_sql_roundtrips=210,all_online_query_wall_seconds=sum(p['wall_seconds'] for p in pred),common_preparation_timings=times,
            collection=record(home/'collection.json'),predictions=record(home/'predictions.json'))
        if method=='IBJS':verification['charged_logical_lookups']=70000;put(home/'monitor.json',{'fixture':True})
        put(home/'verification.json',verification);put(home/'lifecycle.json',dict(status='PASS',binding=binding,client_pid=17,verification_sha256=record(home/'verification.json')['sha256']))
        files={n:record(home/n) for n in m.required_files(method)};seal=dict(schema='job70-'+method.lower()+'-final-v1',binding=binding,files=files);seal['self_sha256']=m.object_hash(seal);put(home/'final_seal.json',seal)
        proofs[method]=dict(status='PASS_READ_ONLY_LOCAL_JOB70_'+method+('_WITH_GAPS' if unfinished else ''),verification=verification,verification_artifact=record(home/'verification.json'),
            final_seal=record(home/'final_seal.json'),artifacts=list(files.values()),dependencies=plan['dependencies'],predictions=predictions,controller_timing=execution)
    def loader(method,root):
        def verify(home,root):calls.append(method);assert Path(home)==homes[method];return copy.deepcopy(proofs[method])
        return SimpleNamespace(verify=verify)
    monkeypatch.setattr(m,'load_auditor',loader)
    return m,root,homes,proofs,calls,record


def test_build_one_fresh_acceptance_per_method_exact_reuse_and_unchanged_inputs(tmp_path,monkeypatch):
    m,root,homes,proofs,calls,record=sealed_fixture(tmp_path,monkeypatch)
    before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    output=m.build(homes,root=root)
    assert calls==['SRS','IBJS'] and set(p.name for p in output.iterdir())=={'predictions_scored.csv','method_costs.csv','RESULTS.md','manifest.json'}
    manifest=json.loads((output/'manifest.json').read_text());assert manifest['methods']['SRS']['summary']['whole70']['max']['value']=='Infinity'
    assert manifest['methods']['IBJS']['costs']['common_sql_roundtrips']==67 and manifest['methods']['SRS']['costs']['common_sql_roundtrips']==65
    assert manifest['methods']['IBJS']['costs']['external_command_wall_seconds'] is None
    assert manifest['methods']['SRS']['costs']['binary_copy_bytes_both_passes']==1200
    with (output/'predictions_scored.csv').open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
    assert len(rows)==140 and rows[0]['q_error']=='Infinity' and rows[70]['method']=='LOCAL_JOB70_IBJS_SQL_N1000_B100K'
    assert m.build(homes,root=root)==output and calls==['SRS','IBJS','SRS','IBJS']
    assert before=={str(Path(p)):(Path(p).read_bytes(),Path(p).stat().st_mtime_ns) for p in before}


@pytest.mark.parametrize('damage',['subset','duplicate','extra','tampered','wrong_sql','wrong_cost','source_mutation'])
def test_build_rejects_incomplete_self_claimed_or_changed_physical_evidence(tmp_path,monkeypatch,damage):
    m,root,homes,proofs,calls,record=sealed_fixture(tmp_path,monkeypatch,('SRS',));p=proofs['SRS']
    if damage=='subset':p['artifacts'].pop()
    elif damage=='duplicate':p['artifacts'][-1]=p['artifacts'][0]
    elif damage=='extra':p['artifacts'].append(p['final_seal'])
    elif damage=='tampered':(homes['SRS']/'queries/query_03.json').write_text('{}')
    elif damage=='wrong_sql':p['predictions']['queries'][3]['sql']+=' '
    elif damage=='wrong_cost':p['verification']['common_sql_roundtrips']=64
    else:
        original=m.load_auditor
        def load(method,root):
            x=original(method,root);verify=x.verify
            def changed(*a,**kw):
                result=verify(*a,**kw);(root/'source.py').write_text('# changed\n');return result
            return SimpleNamespace(verify=changed)
        monkeypatch.setattr(m,'load_auditor',load)
    with pytest.raises(ValueError):m.build(homes,root=root)
    assert not (root/'output/full/figures').exists()


def test_partial_whole_summary_null_and_existing_export_never_repaired(tmp_path,monkeypatch):
    m,root,homes,proofs,calls,record=sealed_fixture(tmp_path,monkeypatch,('SRS',),unfinished=True);out=m.build(homes,root=root)
    manifest=json.loads((out/'manifest.json').read_text());s=manifest['methods']['SRS']['summary']
    assert s['whole70'] is None and s['unfinished']==1 and s['conditional_finite']['queries']==68
    (out/'RESULTS.md').write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError):m.build(homes,root=root)
    assert (out/'RESULTS.md').read_text()=='tampered'


def reseal(m,home,proof,record):
    def put(path,value):path.write_text(json.dumps(value,sort_keys=True),encoding='utf-8')
    for i in range(70):
        f=home/'queries'/('query_%02d.json'%i);put(f.with_suffix('.seal.json'),dict(binding=proof['verification']['binding'],query_no=i,artifact=record(f)))
    proof['verification']['collection']=record(home/'collection.json');proof['verification']['predictions']=record(home/'predictions.json')
    put(home/'verification.json',proof['verification']);life=json.loads((home/'lifecycle.json').read_text());life['verification_sha256']=record(home/'verification.json')['sha256'];put(home/'lifecycle.json',life)
    seal=json.loads((home/'final_seal.json').read_text());seal['files']={n:record(home/n) for n in seal['files']};seal['self_sha256']=m.object_hash({k:v for k,v in seal.items() if k!='self_sha256'});put(home/'final_seal.json',seal)
    proof['artifacts']=list(seal['files'].values());proof['verification_artifact']=record(home/'verification.json');proof['final_seal']=record(home/'final_seal.json')


@pytest.mark.parametrize('damage',['common64','no_copy_table','query_cost','controller_cost','sql_identity'])
def test_resealed_semantic_damage_is_not_accepted_as_valid_proof(tmp_path,monkeypatch,damage):
    m,root,homes,proofs,calls,record=sealed_fixture(tmp_path,monkeypatch,('SRS',));home=homes['SRS'];p=proofs['SRS']
    if damage=='common64':p['verification']['common_sql_roundtrips']=64
    elif damage=='no_copy_table':
        c=json.loads((home/'collection.json').read_text());c['after'].pop('title');(home/'collection.json').write_text(json.dumps(c))
    elif damage=='query_cost':
        f=home/'queries/query_03.json';q=json.loads(f.read_text());q['operations'][0]['seconds']=100;f.write_text(json.dumps(q))
    elif damage=='controller_cost':
        p['controller_timing']['collection_and_checkpoint_seconds']=0.;(home/'execution.json').write_text(json.dumps(p['controller_timing']))
    else:
        p['predictions']['queries'][3]['sql']+=' ';(home/'predictions.json').write_text(json.dumps(p['predictions']))
        f=home/'queries/query_03.json';q=json.loads(f.read_text());q['sql']+=' ';f.write_text(json.dumps(q))
    reseal(m,home,p,record)
    with pytest.raises(ValueError):m.build(homes,root=root)


def test_synthetic_export_forbids_database_process_model_and_scientific_imports(tmp_path,monkeypatch):
    m,root,homes,proofs,calls,record=sealed_fixture(tmp_path,monkeypatch,('IBJS',));original=builtins.__import__
    def guarded(name,*a,**kw):
        assert name.split('.')[0] not in {'subprocess','sqlite3','psycopg2','pickle','numpy','pandas','spn','rspn'},name
        return original(name,*a,**kw)
    monkeypatch.setattr(builtins,'__import__',guarded)
    m.build(homes,root=root);assert calls==['IBJS']


def test_pinned_sources_require_the_declared_physical_bytes_and_loaded_consumer(tmp_path,monkeypatch):
    m=module();source=tmp_path/'source.py';source.write_text('# source\n');own=tmp_path/'tables.py';own.write_text('# tables\n')
    monkeypatch.setattr(m,'SRS_PINS',{'source.py':hashlib.sha256(source.read_bytes()).hexdigest()});monkeypatch.setattr(m,'OWN',('tables.py',));monkeypatch.setattr(m,'__file__',str(own))
    assert set(m.sources(tmp_path,['SRS']))=={'source.py','tables.py'}
    source.write_text('# modified\n')
    with pytest.raises(ValueError,match='pin'):m.sources(tmp_path,['SRS'])


def test_extra_entry_in_existing_output_and_empty_selection_are_rejected(tmp_path,monkeypatch):
    m,root,homes,proofs,calls,record=sealed_fixture(tmp_path,monkeypatch,('SRS',));out=m.build(homes,root=root);(out/'extra.json').write_text('{}')
    with pytest.raises(ValueError,match='extra'):m.build(homes,root=root)
    with pytest.raises(ValueError,match='Select'):m.build({},root=root)
