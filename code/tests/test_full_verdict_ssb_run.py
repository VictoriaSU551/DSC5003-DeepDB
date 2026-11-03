"""Controller pure gates only; SQLite/PG/JVM are deliberately not started."""
import base64
import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module():
    path = ROOT / 'code/full_verdict_ssb_run.py'
    assert path.exists(), 'Concrete SF2 controller is missing'
    spec = importlib.util.spec_from_file_location('verdict_ssb_run_test', str(path))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_schema_preserves_all_seventeen_fact_fields_and_dimension_keys():
    m = module(); schema = m.schema_contract((ROOT / 'code/benchmarks/ssb/setup-sql/schema.sql').read_text())
    assert {k:len(v['columns']) for k,v in schema.items()} == {'lineorder':17,'dwdate':17,'customer':8,'supplier':7,'part':9}
    assert schema['lineorder']['primary_key'] == []
    assert schema['customer']['primary_key'] == ['c_custkey']
    assert schema['lineorder']['columns'][0] == ['lo_orderkey','BIGINT']
    assert 'lo_orderpriority' in m.create_table_sql('lineorder', schema['lineorder'], 'postgres')
    assert 'PRIMARY KEY' not in m.create_table_sql('lineorder', schema['lineorder'], 'sqlite')


def test_oracle_uses_integer_sample_sum_and_separates_two_weights():
    rows = module().oracle_records([(1997,'A',7)], 2, 3, 10, 2**63)
    assert rows == [{'key':['1997','A'],'sample_sum':7,
                     'verdict_expected':{'numerator':70,'denominator':3},
                     'native_p_expected':{'numerator':14,'denominator':1}}]
    with pytest.raises(ValueError): module().oracle_records([(1997,'A',7.5)],2,3,10,2**63)


def test_oracle_preserves_sql_null_and_rejects_duplicate_or_wrong_width_groups():
    m=module()
    assert m.oracle_records([(None,)],0,3,10,2**63)[0]['sample_sum'] is None
    for rows in [[('A',1),('A',2)],[('A',1,2)]]:
        with pytest.raises(ValueError): m.oracle_records(rows,1,3,10,2**63)


def test_comparison_keeps_missing_extra_zero_truth_null_and_engine_error():
    m=module()
    expected=[{'key':['A'],'sample_sum':0,'verdict_expected':{'numerator':0,'denominator':1}},
              {'key':['B'],'sample_sum':2,'verdict_expected':{'numerator':20,'denominator':1}}]
    actual={'error':'timeout','usable_for_point_comparison':False,'rows':[{'key':['A'],'point':1.,'point_status':'FINITE'},{'key':['C'],'point':None,'point_status':'NULL'}]}
    rows=m.compare_oracle(actual,expected)
    assert {tuple(x['key']):x['status'] for x in rows} == {('A',):'MATCHED',('B',):'MISSING_MODEL_GROUP',('C',):'EXTRA_MODEL_GROUP'}
    assert rows[0]['relative_error'] is None and rows[0]['zero_expected']
    assert not any(x['numeric_gate_pass'] for x in rows)
    assert all(x['engine_error']=='timeout' for x in rows)


def test_known_scale_difference_is_detected_without_using_population_truth():
    m=module(); expected=m.oracle_records([(7,)],0,3,10,2**63)
    wrong={'error':None,'usable_for_point_comparison':True,'rows':[{'key':[],'point':14.,'point_status':'FINITE'}]}
    assert m.compare_oracle(wrong,expected)[0]['numeric_gate_pass'] is False
    wrong['rows'][0]['point']=70/3
    assert m.compare_oracle(wrong,expected)[0]['numeric_gate_pass'] is True


def test_actual_rewrite_requires_fact_sample_full_dimensions_and_fact_ci_partition():
    m=module(); c={'sql':'select sum(lo_revenue) from lineorder, dwdate where lo_orderdate=d_datekey;','mode':'subsampling'}
    sql='SELECT sum(vt1.lo_revenue), vt1."verdict_vpart" FROM public_verdict.vs_lineorder_uf_0_0033 AS vt1 INNER JOIN public.dwdate AS vt2 ON vt1.lo_orderdate=vt2.d_datekey'
    proof=m.rewrite_proof('DEBUG - [ApproxAggregatedRelation] A query to db: '+sql+'\n',c)
    assert proof['physical_sql']==sql and proof['full_dimensions']==['dwdate']
    for bad in [sql.replace('public_verdict.vs_lineorder_uf_0_0033','public.lineorder'),sql.replace('public.dwdate','public_verdict.vs_dwdate_uf_1_0000'),sql.replace('"verdict_vpart"','"other"')]:
        with pytest.raises(ValueError):m.rewrite_proof('A query to db: '+bad+'\n',c)


def test_namespace_atomic_claim_refuses_empty_preexisting_and_tainted_namespaces(tmp_path):
    m=module(); home=tmp_path/'claimed';m.claim_namespace(home,{'input':'A'})
    with pytest.raises(FileExistsError):m.claim_namespace(home,{'input':'A'})
    empty=tmp_path/'empty';empty.mkdir()
    with pytest.raises(FileExistsError):m.claim_namespace(empty,{})
    m.mark_tainted(home,'diagnostic')
    assert json.loads((home/'lifecycle.json').read_text())['status']=='TAINTED'
    with pytest.raises(FileExistsError):m.claim_namespace(home,{'input':'A'})


def test_budget_includes_only_owned_new_bytes_and_positive_wal_and_tmp_growth():
    m=module(); usage=m.budget_total(100,200,wal_now=70,wal_before=50,tmp_now=30,tmp_before=10)
    assert usage['total_bytes']==340 and usage['positive_wal_bytes']==20 and usage['positive_temp_bytes']==20
    assert m.budget_total(100,200,wal_now=20,wal_before=50,tmp_now=0,tmp_before=10)['total_bytes']==300


def test_review_approval_binds_scope_plan_hash_source_and_exact_resource_cap(tmp_path):
    m=module();plan={'binding_sha256':'a'*64,'scope':'SF2_ONLY','limits':{'total_new_bytes':1024**3}}
    body={'status':'APPROVED_SF2_EXECUTION','binding_sha256':'a'*64,'scope':'SF2_ONLY','limits':{'total_new_bytes':1024**3}}
    p=tmp_path/'review.json';p.write_text(json.dumps(body));m.check_review(p,m.digest(p),plan)
    for change in [('status','CANDIDATE'),('scope','SF500'),('binding_sha256','b'*64),('limits',{'total_new_bytes':2*1024**3})]:
        bad=dict(body);bad[change[0]]=change[1];p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):m.check_review(p,m.digest(p),plan)


def test_protected_identity_check_is_exact_but_claims_catalog_scope_only():
    m=module();before={'deepdb_job':{'oid':1,'relations':[['public','title',1,2]]},'deepdb_verdict':{'oid':2,'relations':[]}}
    assert m.check_protected(before,json.loads(json.dumps(before)))['scope']=='CATALOG_IDENTITIES_ONLY_NOT_ROW_CONTENT'
    after=json.loads(json.dumps(before));after['deepdb_job']['relations'][0][-1]=3
    with pytest.raises(ValueError):m.check_protected(before,after)


def test_missing_approval_blocks_before_database_sqlite_process_or_source_inspection(tmp_path,monkeypatch):
    m=module()
    def forbidden(*args,**kwargs):raise AssertionError('Premature operation')
    monkeypatch.setattr(m,'prepare_plan',forbidden)
    monkeypatch.setattr(m,'connect',forbidden)
    with pytest.raises(ValueError,match='review approval'):
        m.run_sf2('fixture',None,None)


def test_result_closure_requires_each_call_not_a_self_declared_subset():
    m=module();c=m.candidate();plan={'queries':c.call_plan(c.load_queries())}
    required=m.required_result_paths(plan)
    assert len([p for p in required if p.endswith('/result.tsv')])==38
    assert 'oracle.json' in required and 'oracle_execution.json' in required
    assert 'import.json' in required and 'post_run.json' in required
    assert 'calls/Q4.3.sum_supplycost.subsampling/receipt.json' in required
    with pytest.raises(ValueError):m.check_result_set(plan,{})
    with pytest.raises(ValueError):m.check_result_set(plan,{p:{} for p in required if not p.endswith('/result.tsv')})
    with pytest.raises(ValueError):m.check_result_set(plan,dict({p:{} for p in required},foreign={}))


def test_execution_rejects_bad_review_before_namespace_or_pg_creation(tmp_path,monkeypatch):
    m=module();p=tmp_path/'approval.json';p.write_text('{}')
    monkeypatch.setattr(m,'prepare_plan',lambda *args:{'binding_sha256':'a'*64,'limits':m.LIMITS})
    def forbidden(*args,**kwargs):raise AssertionError('Started science with unapproved review')
    monkeypatch.setattr(m,'claim_namespace',forbidden);monkeypatch.setattr(m,'connect',forbidden)
    with pytest.raises(ValueError,match='review approval'):
        m.run_sf2('test',p,'b'*64)


def test_sqlite_progress_applies_budget_while_query_is_executing():
    m=module()
    class Watch:
        def __init__(self):self.checked=0
        def tick(self):self.checked+=1
    watch=Watch();callback=m.sqlite_progress(float('inf'),watch)
    assert callback()==0 and watch.checked==1
    assert m.sqlite_progress(-1,watch)()==1
    class Exceeded:
        def tick(self):raise ValueError('budget exceeded')
    assert m.sqlite_progress(float('inf'),Exceeded())()==1


def call_evidence_fixture(m,home):
    c=m.candidate();call=c.call_plan(c.load_queries())[0]
    run_home=home;home=home/'calls'/call['call_id'];home.mkdir(parents=True,exist_ok=True)
    (home/'input.sql').write_text(call['sql'])
    cells='V'+base64.b64encode(b'100').decode()
    text='META\t'+call['call_id']+'\tV'+base64.b64encode(b'sum').decode()+'\nROW\t'+call['call_id']+'\t'+cells+'\nTIME\t'+call['call_id']+'\t123\n'
    (home/'result.tsv').write_text(text)
    log='A query to db: SELECT SUM(lo_extendedprice*lo_discount/verdict_vprob) FROM '+m.SAMPLE_TABLE+' AS vt1 INNER JOIN public.dwdate AS vt2 ON vt1.lo_orderdate=vt2.d_datekey\n'
    (home/'java.stdout.log').write_text(log);(home/'java.stderr.log').write_text('')
    process={'exit_code':0,'reason':None,'seconds':.1,'peak_rss_bytes':1000,'command':list(map(str,m.expected_command('query',run_home,call)))}
    (home/'java.process.json').write_text(json.dumps(process))
    receipt={'call':call,'result':c.parse_engine(text,[call])[call['call_id']],'rewrite':m.rewrite_proof(log,call),'process':process}
    (home/'receipt.json').write_text(json.dumps(receipt));(home/'receipt.seal.json').write_text(json.dumps({'sha256':m.digest(home/'receipt.json')}))
    return call


def test_per_call_audit_rejects_resealed_wrong_sql_identity_or_stale_decoding(tmp_path):
    m=module();call=call_evidence_fixture(m,tmp_path)
    folder=tmp_path/'calls'/call['call_id']
    assert m.verify_call_evidence(folder,call)['call']==call
    saved=json.loads((folder/'receipt.json').read_text());saved['result']['rows'][0]['point']=999
    (folder/'receipt.json').write_text(json.dumps(saved));(folder/'receipt.seal.json').write_text(json.dumps({'sha256':m.digest(folder/'receipt.json')}))
    with pytest.raises(ValueError):m.verify_call_evidence(folder,call)
    call_evidence_fixture(m,tmp_path);(folder/'input.sql').write_text(call['sql'].replace('1993','1994'))
    with pytest.raises(ValueError):m.verify_call_evidence(folder,call)


def test_oracle_audit_recomputes_weights_and_rejects_subset_or_duplicate_identities():
    m=module();c=m.candidate();calls=c.call_plan(c.load_queries());selected=[x for x in calls if x['mode']=='nobound']
    oracle={'status':'PASS_INDEPENDENT_SQLITE_INTEGER_SAMPLE_SUMS','population_rows':11997996,'sample_rows':39587,'query_truth_used':False,
            'queries':{x['call_id']:{'call':x,'groups':m.oracle_records([tuple(['A']*x['group_width']+[7])],x['group_width'],39587,11997996,61482997997673935),'seconds':.1} for x in selected}}
    m.validate_oracle({'queries':calls},oracle)
    original=json.loads(json.dumps(oracle));oracle['queries'][selected[0]['call_id']]['groups'][0]['verdict_expected']['numerator']+=1
    with pytest.raises(ValueError):m.validate_oracle({'queries':calls},oracle)
    original['queries'].pop(selected[-1]['call_id'])
    with pytest.raises(ValueError):m.validate_oracle({'queries':calls},original)


def test_import_stream_hash_preserves_all_fields_duplicates_and_rejects_changed_value(tmp_path):
    m=module();p=tmp_path/'fixture.tbl';p.write_bytes(b'1|  A"B  ||\r\n1|  A"B  ||\r\n')
    expected=m.canonical_input_hash(p,3,True)
    sink=m.CopyHashSink();sink.write('1|"  A""B  "|""\n');sink.write(b'1|"  A""B  "|""\n')
    m.require_import_identity(expected,sink.result())
    wrong=m.CopyHashSink();wrong.write('1|CHANGED|""\n1|"  A""B  "|""\n')
    with pytest.raises(ValueError):m.require_import_identity(expected,wrong.result())


def test_native_metadata_must_register_only_fact_with_actual_fraction():
    m=module()
    size=[['public_verdict','vs_lineorder_uf_0_0033',39587,11997996]]
    name=[['public','lineorder','public_verdict','vs_lineorder_uf_0_0033','uniform',39587/11997996,'']]
    m.check_native_metadata(size,name)
    for bad in [name+[['public','dwdate','public','dwdate','uniform',1.,'']], [['public','lineorder','public_verdict','vs_lineorder_uf_0_0033','uniform',.003333,'']]]:
        with pytest.raises(ValueError):m.check_native_metadata(size,bad)


def test_formal_training_process_forbids_sf2_window_but_generator_does_not():
    m=module();m.check_model_processes([{'Name':'python.exe','ProcessId':1,'CommandLine':'python code/full_ssb_native_v2_formal.py stream'}])
    for command in ['python code/full_ssb_native_model_run.py run','python code/full_ssb_model.py formal-all','python code/full_training.py train','python -c "import full_ssb_native_model_run; run()"']:
        with pytest.raises(ValueError):m.check_model_processes([{'Name':'python.exe','ProcessId':42,'CommandLine':command}])


def test_plan_output_is_utf8_new_file_and_refuses_overwrite(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'OUT',tmp_path);monkeypatch.setattr(m,'prepare_plan',lambda *args:{'scope':'SF2_ONLY','formal_allowed':False})
    path=tmp_path/'operational_plan.json'
    m.main(['plan','--output',str(path)])
    assert json.loads(path.read_text(encoding='utf-8'))=={'scope':'SF2_ONLY','formal_allowed':False}
    with pytest.raises(FileExistsError):m.main(['plan','--output',str(path)])


def accounting_fixture():
    sizes={'public.dwdate':2556,'public.customer':60000,'public.part':400000,'public.supplier':4000,'public_verdict.vs_lineorder_uf_0_0033':39587}
    imported={'status':'PASS_IMPORTED_EXISTING_SAMPLE_FULL_DIMENSIONS','original_fact_rows':0,'population_rows':11997996,'sample_rows':39587,'actual_probability':39587/11997996,'dimension_policy':'FULL_UNSAMPLED_NO_VPART','query_truth_used_for_registration':False,
              'loads':[{'table':t,'rows':n,'canonical_source':{'sha256':'a'*64,'rows':n,'bytes':n},'canonical_actual':{'sha256':'a'*64,'rows':n,'bytes':n}} for t,n in sizes.items()]}
    before={'deepdb_job':{'oid':1},'deepdb_verdict':{'oid':2}}
    post={'status':'PASS_LOCKED_INPUT_CATALOG_ACCOUNTING','original_fact_rows':0,'share_lock_held_across_calls':38,
          'aux_accounting':[39587,39587/11997996,39587/11997996,0,99],
          'partition_histogram':[[i,395] for i in range(99)]+[[99,482]],
          'metadata_size':[['public_verdict','vs_lineorder_uf_0_0033',39587,11997996]],
          'metadata_name':[['public','lineorder','public_verdict','vs_lineorder_uf_0_0033','uniform',39587/11997996,'']],
          'protected':{'scope':'CATALOG_IDENTITIES_ONLY_NOT_ROW_CONTENT','before':before,'after':before}}
    return imported,post


def test_historical_input_accounting_rejects_missing_dimension_or_wrong_partition_total():
    m=module();imported,post=accounting_fixture();m.validate_accounting(imported,post)
    imported['loads'].pop()
    with pytest.raises(ValueError):m.validate_accounting(imported,post)
    imported,post=accounting_fixture();post['partition_histogram'][-1][-1]=483
    with pytest.raises(ValueError):m.validate_accounting(imported,post)


def test_historical_accounting_never_accepts_nonempty_original_fact_or_registered_dimension():
    m=module();imported,post=accounting_fixture();post['original_fact_rows']=1
    with pytest.raises(ValueError):m.validate_accounting(imported,post)
    imported,post=accounting_fixture();post['metadata_name'].append(['public','dwdate','public','dwdate','uniform',1.,''])
    with pytest.raises(ValueError):m.validate_accounting(imported,post)


def test_population_statistics_preserve_missing_extra_zero_nonfinite_and_actual_ci():
    m=module()
    exact=[{'group':['A'],'value':100},{'group':['B'],'value':0},{'group':['C'],'value':5}]
    rows=[{'key':['A'],'point':110.,'point_status':'FINITE','interval95':[90.,130.],'ci_status':'FINITE'},
          {'key':['B'],'point':None,'point_status':'NONFINITE','interval95':None,'ci_status':'NONFINITE'},
          {'key':['EXTRA'],'point':5.,'point_status':'FINITE','interval95':[4.,6.],'ci_status':'FINITE'}]
    result=m.population_statistics({'rows':rows,'error':None,'usable_for_point_comparison':True},exact)
    values={tuple(x['key']):x for x in result}
    assert values[('A',)]['relative_error']==.1 and values[('A',)]['native_ci95_covers_truth'] is True
    assert values[('B',)]['zero_truth'] and values[('B',)]['relative_error'] is None
    assert values[('C',)]['status']=='MISSING_MODEL_GROUP' and values[('C',)]['missing_penalty_relative_error']==1.
    assert values[('EXTRA',)]['status']=='EXTRA_MODEL_GROUP'


def test_java_child_environment_cannot_inject_an_external_agent_or_classpath():
    env=module().java_environment({'PATH':'preserve','SystemRoot':'C:\\WINDOWS','JAVA_TOOL_OPTIONS':'-javaagent:foreign.jar','_JAVA_OPTIONS':'-Xbootclasspath/a:foreign.jar','JDK_JAVA_OPTIONS':'foreign','CLASSPATH':'foreign.jar'})
    assert env=={'PATH':'preserve','SystemRoot':'C:\\WINDOWS'}


def test_profit_component_cannot_inherit_profit_population_truth_or_coverage():
    m=module();c=m.candidate();calls=[x for x in c.call_plan(c.load_queries()) if x['query_no']==10 and x['mode']=='nobound']
    actual={'rows':[],'error':None,'usable_for_point_comparison':True};truth=[{'query_no':10,'group':['1997','A'],'value':100}]
    assert m.population_comparison(calls[0],actual,truth)['status']=='AVAILABLE_EXACT_EXPRESSION_TRUTH'
    for child in calls[1:]:
        result=m.population_comparison(child,actual,truth)
        assert result=={'status':'UNAVAILABLE_NO_MATCHING_FULL_POPULATION_COMPONENT_TRUTH','groups':None}


def test_process_receipt_requires_exact_fixed_java_command_finite_timing_and_rss(tmp_path):
    m=module();call=m.candidate().call_plan(m.candidate().load_queries())[0]
    expected=m.expected_command('query',tmp_path,call)
    assert str(expected[0]).replace('\\','/').endswith('/.runtime/java/jdk8u462-b08/bin/java.exe')
    assert list(map(str,expected[-5:]))==['query','nobound',call['call_id'],str(tmp_path/'calls'/call['call_id']/'input.sql'),str(tmp_path/'calls'/call['call_id']/'result.tsv')]
    good={'command':list(map(str,expected)),'exit_code':0,'reason':None,'seconds':.1,'peak_rss_bytes':1000}
    m.validate_process(good,expected)
    bads=[{k:v for k,v in good.items() if k!='command'},dict(good,command=['foreign-java.exe']),dict(good,seconds=-1),dict(good,seconds=float('nan')),dict(good,peak_rss_bytes=2*1024**3)]
    for bad in bads:
        with pytest.raises(ValueError):m.validate_process(bad,expected)


def resource_fixture(m,home):
    start={'available_ram_bytes':4*1024**3,'free_disk_bytes':4*1024**3,'limits':m.LIMITS,'model_scan':{'status':'NO_FORMAL_RSPN_ACTIVE','python_processes_checked':1,'process_ids':[1]}}
    sample=m.budget_total(100,200,70,50,30,10);sample.update(monotonic=1.,python_rss_bytes=1024)
    budget={'samples':[sample],'peak_total_bytes':340,'limits':m.LIMITS,'wal_lsn_before':None}
    server={'status':'EXISTING_SERVER_NOT_STOPPED','startup_requested':False,'started_by_controller':False,'initial_status':{'command':list(map(str,m.pg_control_command('status',home))),'exit_code':0,'seconds':.1,'stdout':'','stderr':'','capture':'EXCLUSIVE_FILES_NO_PIPE','status':'RETURNED'},'start':None,'stop':None,'post_stop_status':None,'protected_scope':'CATALOG_IDENTITIES_ONLY_NOT_ROW_CONTENT'}
    return start,budget,server


def test_readonly_resource_gate_rejects_resealed_overbudget_wrong_total_and_low_startup(tmp_path):
    m=module();start,budget,server=resource_fixture(m,tmp_path);m.validate_resources(start,budget,server,tmp_path)
    import copy
    for mutation in ['ram','free','sum','peak','cap','python','limits','server','owned_not_stopped']:
        a,b,s=copy.deepcopy((start,budget,server))
        if mutation=='ram':a['available_ram_bytes']=1
        if mutation=='free':a['free_disk_bytes']=1
        if mutation=='sum':b['samples'][0]['total_bytes']=1
        if mutation=='peak':b['peak_total_bytes']=1
        if mutation=='cap':b['samples'][0]['owned_files_bytes']=2*1024**3;b['samples'][0]['total_bytes']=2*1024**3+240;b['peak_total_bytes']=b['samples'][0]['total_bytes']
        if mutation=='python':b['samples'][0]['python_rss_bytes']=1024**3
        if mutation=='limits':a['limits']={}
        if mutation=='server':s['initial_status']['command']=['foreign-pgctl']
        if mutation=='owned_not_stopped':s['started_by_controller']=True
        with pytest.raises(ValueError):m.validate_resources(a,b,s,tmp_path)


def test_selected_java_is_fixed_and_must_be_present_in_reviewed_manifest(tmp_path,monkeypatch):
    m=module();selected_java=m.descriptor(m.JAVA);selected_javac=m.descriptor(m.JAVAC)
    plan={'selected_java':selected_java,'selected_javac':selected_javac,'source_runtime_files':{selected_java['path']:selected_java,selected_javac['path']:selected_javac}}
    m.verify_java_selection(plan)
    monkeypatch.setattr(Path,'glob',lambda *a,**k:iter([tmp_path/'foreign-jdk/bin/java.exe']))
    assert m.java_command(tmp_path/'classes')[0]==m.ROOT/'.runtime/java/jdk8u462-b08/bin/java.exe'
    plan['source_runtime_files'].pop(selected_java['path'])
    with pytest.raises(ValueError):m.verify_java_selection(plan)


def test_owned_server_requires_successful_start_stop_and_same_postmaster_identity(tmp_path):
    m=module();start,budget,server=resource_fixture(m,tmp_path)
    server.update(status='PROJECT_SERVER_STOPPED_BY_OWNER',startup_requested=True,started_by_controller=True,
                  started_postmaster_pid=123,stopped_postmaster_pid=123)
    for key,action,code in [('initial_status','status',3),('start','start',0),('stop','stop',0),('post_stop_status','status',3)]:
        server[key]={'command':list(map(str,m.pg_control_command(action,tmp_path))),'exit_code':code,'seconds':.1,'stdout':'','stderr':'','capture':'EXCLUSIVE_FILES_NO_PIPE','status':'RETURNED'}
    server['startup_ownership']={'status':'OWNED_THIS_START_ATTEMPT',
        'intent':{'initial_exit_code':3,'command':list(map(str,m.pg_control_command('start',tmp_path))),'started_epoch':100.,'deadline_epoch':190.},
        'identity':{'pid':123,'image':str(m.PG/'postgres.exe'),'cluster':str(m.CLUSTER),'port':55432,
                    'command':['postgres.exe','-D',str(m.CLUSTER)],'start_epoch':100,'creation_epoch':100.1}}
    m.validate_resources(start,budget,server,tmp_path)
    server['stopped_postmaster_pid']=124
    with pytest.raises(ValueError):m.validate_resources(start,budget,server,tmp_path)


def test_pg_control_uses_exclusive_files_not_inherited_capture_pipes(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    def run(command,**kwargs):
        assert kwargs.get('capture_output') is not True
        assert kwargs['stdin']==m.subprocess.DEVNULL and kwargs['close_fds'] is True
        assert hasattr(kwargs['stdout'],'write') and hasattr(kwargs['stderr'],'write')
        kwargs['stdout'].write(b'started\n');kwargs['stderr'].write(b'diagnostic\n')
        return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(m.subprocess,'run',run)
    result=m.pg_control('start',tmp_path)
    assert result['stdout']=='started\n' and result['stderr']=='diagnostic\n'
    assert result['capture']=='EXCLUSIVE_FILES_NO_PIPE'
    assert (tmp_path/'pg_start.stdout.log').read_bytes()==b'started\n'
    with pytest.raises(FileExistsError):m.pg_control('start',tmp_path)


def test_pg_control_timeout_persists_file_evidence_before_raising(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    def run(command,**kwargs):
        assert kwargs.get('capture_output') is not True
        kwargs['stdout'].write(b'server may already be started\n')
        raise m.subprocess.TimeoutExpired(command,90)
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(m.subprocess.TimeoutExpired):m.pg_control('start',tmp_path)
    evidence=json.loads((tmp_path/'pg_start.process.json').read_text())
    assert evidence['status']=='TIMEOUT' and evidence['exit_code'] is None
    assert evidence['stdout']=='server may already be started\n'


def test_start_failure_still_acquires_only_this_attempt_verified_ownership(tmp_path,monkeypatch):
    m=module();owned={};monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'CLUSTER',tmp_path/'cluster');m.CLUSTER.mkdir()
    def start(action,home,label=None):
        assert json.loads((home/'startup_intent.json').read_text())['initial_exit_code']==3
        raise m.subprocess.TimeoutExpired(['pg_ctl'],90)
    monkeypatch.setattr(m,'pg_control',start)
    identity={'pid':123,'image':str(m.PG/'postgres.exe'),'command':['postgres.exe','-D',str(m.CLUSTER)],
              'cluster':str(m.CLUSTER),'port':55432,'start_epoch':100.,'creation_epoch':100.}
    monkeypatch.setattr(m.time,'time',lambda:100.)
    monkeypatch.setattr(m,'postmaster_identity',lambda:identity)
    with pytest.raises(m.subprocess.TimeoutExpired):m.start_owned_server(tmp_path,{'exit_code':3},owned)
    assert owned['identity']==identity
    assert json.loads((tmp_path/'startup_ownership.json').read_text())['status']=='OWNED_THIS_START_ATTEMPT'


def test_start_failure_never_adopts_foreign_or_old_postmaster(tmp_path,monkeypatch):
    m=module();owned={};monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'CLUSTER',tmp_path/'cluster');m.CLUSTER.mkdir()
    monkeypatch.setattr(m.time,'time',lambda:100.)
    def failed(*args,**kwargs):raise m.subprocess.TimeoutExpired(['pg_ctl'],90)
    monkeypatch.setattr(m,'pg_control',failed)
    identity={'pid':123,'image':'foreign/postgres.exe','command':['postgres.exe','-D',str(m.CLUSTER)],
              'cluster':str(m.CLUSTER),'port':55432,'start_epoch':1.,'creation_epoch':1.}
    monkeypatch.setattr(m,'postmaster_identity',lambda:identity)
    with pytest.raises(m.subprocess.TimeoutExpired):m.start_owned_server(tmp_path,{'exit_code':3},owned)
    assert not owned
    assert json.loads((tmp_path/'startup_ownership.json').read_text())['status']=='UNRESOLVED_NOT_OWNED'


def test_owned_identity_requires_exact_cluster_command_and_current_process_epoch(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'CLUSTER',tmp_path/'cluster')
    intent={'started_epoch':100.,'deadline_epoch':190.}
    good={'pid':123,'image':str(m.PG/'postgres.exe'),'command':['postgres.exe','-D',str(m.CLUSTER)],
          'cluster':str(m.CLUSTER),'port':55432,'start_epoch':100.,'creation_epoch':100.1}
    m.validate_owned_identity(good,intent)
    for bad in (dict(good,command=['postgres.exe','-D',str(tmp_path/'other')]),dict(good,start_epoch=1.),
                dict(good,creation_epoch=300.),dict(good,image=str(tmp_path/'postgres.exe')),dict(good,port=5432)):
        with pytest.raises(ValueError):m.validate_owned_identity(bad,intent)


def test_oracle_adoption_refuses_different_inputs_sql_or_nonfailed_source():
    m=module();plan={'source_audit':{'source_id':'same'},'schema_contract':{},'queries':[],'population_rows':11997996,'sample_rows':39587}
    old=dict(plan);execution={'database':{'path':'data/verdict_ssb/sf2_golden_v2/oracle.sqlite','bytes':43941888,
        'sha256':'f0e1cb60ecfff25bc30ffb5d6c06d54d5ed8d09dbfa1ea95403837f3f3a4f908'},'queries_executed':19,'full_fact_recreated':False}
    life={'status':'TAINTED','error':'TimeoutExpired pg_ctl'}
    diagnostic={'source_sha256':'737c6c559615b1e2769335691cede77070d519df25638b08545dec895dcf112b','recovery_exit_code':0,
                'active_external_database_clients':[]}
    m.check_oracle_adoption_lineage(plan,old,execution,life,diagnostic)
    import copy
    for target in ('source','sql','database','lifecycle','recovery'):
        p,e,l,d=copy.deepcopy((old,execution,life,diagnostic))
        if target=='source':p['source_audit']['source_id']='other'
        if target=='sql':p['queries']=[{'sql':'other'}]
        if target=='database':e['database']['sha256']='0'*64
        if target=='lifecycle':l['status']='PASS'
        if target=='recovery':d['recovery_exit_code']=1
        with pytest.raises(ValueError):m.check_oracle_adoption_lineage(plan,p,e,l,d)


def test_start_timeout_cleanup_reaches_owned_server_without_marking_run_pass(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'OUT',tmp_path/'output')
    monkeypatch.setattr(m,'DATA',tmp_path/'data');m.DATA.mkdir()
    monkeypatch.setattr(m,'CLUSTER',tmp_path/'cluster');m.CLUSTER.mkdir()
    plan={'source_audit':{},'runtime':{},'binding_sha256':'a'*64}
    monkeypatch.setattr(m,'prepare_plan',lambda *args:plan);monkeypatch.setattr(m,'check_review',lambda *args:None)
    monkeypatch.setattr(m,'available_ram',lambda:5*m.GIB)
    monkeypatch.setattr(m.shutil,'disk_usage',lambda *args:type('Disk',(),{'free':5*m.GIB})())
    monkeypatch.setattr(m,'assert_no_model_processes',lambda:{'status':'NO_FORMAL_RSPN_ACTIVE'})
    monkeypatch.setattr(m,'Budget',lambda *args:type('Watch',(),{'samples':[]})())
    monkeypatch.setattr(m,'run_oracle',lambda *args:None)
    monkeypatch.setattr(m,'no_external_clients',lambda:None)
    monkeypatch.setattr(m.time,'time',lambda:100.)
    identity={'pid':123,'image':str(m.PG/'postgres.exe'),'command':['postgres.exe','-D',str(m.CLUSTER)],
              'cluster':str(m.CLUSTER),'port':55432,'start_epoch':100.,'creation_epoch':100.}
    monkeypatch.setattr(m,'postmaster_identity',lambda:identity)
    calls=[]
    def pg(action,home,label=None):
        calls.append((action,label))
        if action=='start':raise m.subprocess.TimeoutExpired(['pg_ctl'],90)
        return {'exit_code':3 if action=='status' else 0}
    monkeypatch.setattr(m,'pg_control',pg)
    review=tmp_path/'review.json';review.write_text('{}')
    with pytest.raises(m.subprocess.TimeoutExpired):m.run_sf2('failure',review,'b'*64,True)
    home=m.OUT/'runs/failure'
    assert calls==[('status',None),('start',None),('stop','failed_stop'),('status','failed_status')]
    assert json.loads((home/'lifecycle.json').read_text())['status']=='TAINTED'
    assert json.loads((home/'failed_shutdown.json').read_text())['identity']==identity
    assert not (home/'final.json').exists()


def test_postmaster_command_parser_preserves_windows_cluster_path_with_spaces():
    m=module();command='"C:\\project space\\postgres.exe" "-D" "C:\\project space\\cluster" -p 55432'
    assert m.split_windows_command(command)==['C:\\project space\\postgres.exe','-D','C:\\project space\\cluster','-p','55432']


def test_pg_file_closure_rejects_empty_map_and_resealed_raw_receipt_disagreement(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    unused,unused2,server=resource_fixture(m,tmp_path)
    record=server['initial_status']
    m.atomic_json(tmp_path/'pg_status.process.json',record)
    (tmp_path/'pg_status.stdout.log').write_bytes(b'');(tmp_path/'pg_status.stderr.log').write_bytes(b'')
    files=m.pg_control_artifacts(tmp_path,server)
    m.validate_pg_files(tmp_path,server,files)
    with pytest.raises(ValueError):m.validate_pg_files(tmp_path,server,{})
    (tmp_path/'pg_status.stdout.log').write_bytes(b'changed even if rehashed')
    with pytest.raises(ValueError):m.validate_pg_files(tmp_path,server,m.pg_control_artifacts(tmp_path,server))


def test_connect_requires_roundtrip_float8_precision_for_postgres11(monkeypatch):
    m=module();calls=[]
    class Driver:
        @staticmethod
        def connect(**kwargs):
            calls.append(kwargs);return type('Connection',(),{})()
    import sys
    monkeypatch.setitem(sys.modules,'psycopg2',Driver)
    m.connect()
    assert '-c extra_float_digits=3' in calls[0]['options']
    assert float('0.00329946767776885')!=39587/11997996
    assert float('0.003299467677768854')==39587/11997996


def test_registered_snapshot_requires_exact_original_fields_aux_bits_types_and_partitions():
    m=module();imported,unused=accounting_fixture()
    snapshot={'status':'PASS_LOCKED_REGISTERED_INPUT_ADOPTION','loads':imported['loads'],
        'aux_accounting':[39587,39587/11997996,39587/11997996,0,99],
        'probability_hex':['3f6b077c38a5b19d','3f6b077c38a5b19d'],
        'types':[['verdict_vprob','double precision',True],['verdict_vpart','integer',True]],
        'partition_histogram':[[i,396 if i<87 else 395] for i in range(100)],
        'metadata_size':unused['metadata_size'],'metadata_name':unused['metadata_name'],
        'original_fact_rows':0,'original_canonical_fields_match':True,
        'aux_rows':{'rows':39587,'bytes':1000,'sha256':'a'*64},
        'catalog':{'database':{'oid':123,'name':m.DB,'owner':1,'encoding':6,'collation':'C','ctype':'C'},'relations':[]},'owned_database_bytes':50000000,
        'schema':m.expected_owned_schema(m.schema_contract((ROOT/m.candidate().SCHEMA_PATH).read_text())),
        'steps_executed':dict(imports=0,analyzes=0,javac=0,registrations=0,sqlite_queries=0)}
    table_names=[('public',t) for t in ('dwdate','customer','part','supplier','lineorder')]+[('public_verdict',t) for t in ('vs_lineorder_uf_0_0033','verdict_meta_size','verdict_meta_name')]
    for i,(ns,table) in enumerate(table_names):snapshot['catalog']['relations'].append([ns,table,'r',i+10,i+20])
    for i,table in enumerate(('dwdate','customer','part','supplier')):snapshot['catalog']['relations'].append(['public',table+'_pkey','i',i+30,i+40])
    m.validate_registered_snapshot(snapshot,imported)
    import copy
    for mutation in ('fields','bits','types','parts','empty','bytes','catalog','schema','reimport'):
        bad=copy.deepcopy(snapshot)
        if mutation=='fields':bad['loads'][0]['canonical_actual']['sha256']='b'*64
        if mutation=='bits':bad['probability_hex'][0]='0'*16
        if mutation=='types':bad['types'][0][1]='numeric'
        if mutation=='parts':bad['partition_histogram'].pop()
        if mutation=='empty':bad['original_fact_rows']=1
        if mutation=='bytes':bad['owned_database_bytes']=0
        if mutation=='catalog':bad['catalog']['relations']=[]
        if mutation=='schema':bad['schema']['public.customer'][0][1]='text'
        if mutation=='reimport':bad['steps_executed']['imports']=1
        with pytest.raises(ValueError):m.validate_registered_snapshot(bad,imported)


def test_adopted_execution_never_recompiles_or_reregisters_before_query_lock(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    home=tmp_path/'run';(home/'classes').mkdir(parents=True)
    cls=home/'classes/full_verdict_ssb_bridge.class';cls.write_bytes(b'already compiled original class')
    (home/'registration.tsv').write_text('REGISTER\t'+m.SAMPLE_TABLE+'\t39587\t11997996\t'+repr(39587/11997996)+'\n')
    plan={'registered_reuse':{'classes':m.descriptor(cls)}}
    monkeypatch.setattr(m,'verify_java_selection',lambda *args:None)
    def forbidden(*args,**kwargs):raise AssertionError('Repeated compile/register')
    monkeypatch.setattr(m,'bounded_process',forbidden)
    class BeforeLock(Exception):pass
    def connect(*args,**kwargs):raise BeforeLock('Reached query lock without compile/register')
    monkeypatch.setattr(m,'connect',connect)
    with pytest.raises(BeforeLock):m.execute_original(plan,home,tmp_path,object())
    assert cls.read_bytes()==b'already compiled original class'


def test_budget_retains_measured_owned_database_bytes_after_monitor_close(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'CLUSTER',tmp_path/'cluster')
    monkeypatch.setattr(m,'process_rss',lambda *args:1024)
    home=tmp_path/'out';home.mkdir();stage=tmp_path/'stage';stage.mkdir()
    budget=m.Budget(home,stage);budget.last_database_bytes=50000000
    result=budget.tick(force=True)
    assert result['owned_database_bytes']==50000000 and result['total_bytes']>=50000000
