"""Synthetic controller semantics; no real parent/model/database/runtime calls."""
import copy
import importlib.util
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_verdict_ssb_local_run.py';assert p.exists(),'LOCAL original-engine controller missing'
    s=importlib.util.spec_from_file_location('local_verdict_run_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_commands_have_local_class_population_and_never_sf2_registration(tmp_path):
    m=module();s=m.contract.local_spec();reg=list(map(str,m.command('registration',s,tmp_path)))
    assert reg[-4:]==['register','9996946','3000028242',str(tmp_path/'registration.tsv')]
    assert 'full_verdict_ssb_local_bridge' in reg and 'full_verdict_ssb_bridge' not in reg
    call=m.contract.call_plan()[0];query=list(map(str,m.command('query',s,tmp_path,call)))
    assert query[-5:]==['query','nobound',call['call_id'],str(tmp_path/'calls'/call['call_id']/'input.sql'),str(tmp_path/'calls'/call['call_id']/'result.tsv')]


def test_required_set_rejects_empty_missing_and_extra_receipts():
    m=module();plan={'spec':m.contract.local_spec(),'queries':m.contract.call_plan()}
    files={name:{} for name in m.required_files(plan)};m.check_required(plan,files)
    for bad in ({},{k:v for k,v in files.items() if k!='calls/Q1.1.raw.nobound/receipt.json'},dict(files,foreign={})):
        with pytest.raises(ValueError):m.check_required(plan,bad)


def test_child_population_truth_is_never_profit_truth_and_adapter_has_no_ci():
    m=module();calls=m.contract.call_plan();call=next(c for c in calls if c['role']=='SUM_REVENUE')
    actual={'rows':[],'error':None,'usable_for_point_comparison':True}
    result=m.compare_call(call,actual,{'groups':[]},[{'query_no':10,'group':[],'value':100}])
    assert result['sample_oracle_status']=='UNAVAILABLE_COMPONENT_SUM_NOT_STORED'
    assert result['population_status']=='UNAVAILABLE_NO_MATCHING_COMPONENT_TRUTH' and result['population_groups'] is None


def test_approval_fails_before_any_plan_revalidation_or_pg_if_sha_wrong(tmp_path,monkeypatch):
    m=module();review=tmp_path/'review.json';review.write_text('{}')
    def forbidden(*args,**kwargs):raise AssertionError('Unapproved operation reached parent/science')
    monkeypatch.setattr(m,'revalidate_plan',forbidden)
    with pytest.raises(ValueError):m.run(tmp_path/'absent_plan.json',review,'0'*64,'test',False)


def test_default_describe_is_inert_and_new_outputs_never_sealed_sf2(monkeypatch,capsys,tmp_path):
    m=module()
    def forbidden(*a,**k):raise AssertionError('Describe consumed a scientific source')
    monkeypatch.setattr(m.contract,'collect_lineage',forbidden);monkeypatch.setattr(m,'revalidate_plan',forbidden)
    m.main(['describe']);assert 'CANDIDATE_CODE_ONLY' in capsys.readouterr().out
    with pytest.raises(ValueError):m.write_new(tmp_path/'outside.json',{})


def test_output_preflight_refuses_sealed_namespaces_and_overwrite_before_parent_work(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.contract,'ROOT',tmp_path);base=tmp_path/m.contract.local_spec()['output']
    def forbidden(*args,**kwargs):raise AssertionError('Invalid output reached parent/measurement')
    monkeypatch.setattr(m.contract,'build_pilot_plan',forbidden)
    for folder in ('runs','measurements','../runs'):
        with pytest.raises(ValueError):m.main(['pilot-plan','--output',str(base/folder/'sealed.json')])
    allowed=base/'plans'/'new.json';m.write_new(allowed,{'candidate':True})
    with pytest.raises(FileExistsError):m.main(['pilot-plan','--output',str(allowed)])


def valid_header(m,plan):
    return dict(schema='local_verdict_ssb_final_v1',binding_sha256=plan['binding_sha256'],scope=plan['spec']['scope'],author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,
        actual_stages=dict(imported_tables=5,javac=1,registrations=1,original_query_calls=38,sqlite_queries=0,new_population_sampling=0))


def test_final_header_cannot_self_reseal_author_pass_or_other_stage_counts():
    m=module();plan=dict(spec=m.contract.local_spec(),binding_sha256='a'*64);good=valid_header(m,plan);m.validate_final_header(plan,good)
    for field,value in [('author_different_groups',0),('author_reproduction_complete',True),('scope','AUTHOR_SF500'),('actual_stages',dict(good['actual_stages'],original_query_calls=37))]:
        with pytest.raises(ValueError):m.validate_final_header(plan,dict(good,**{field:value}))


def scan_fixture(m):
    return dict(status='NO_CONFLICTING_SCIENCE_ACTIVE',command=m.ops.SCIENCE_SCAN_COMMAND,
        scan_method='WHOLE_CIM_RESCAN_ON_UNINSPECTABLE_COMMANDLINE_V1',max_additional_rescans=3,additional_rescans=0,
        attempts=[dict(attempt=0,processes=[],python_processes_checked=0,process_ids=[],uninspectable_process_ids=[])],
        processes=[],python_processes_checked=0,process_ids=[])


def write_json(m,path,body):
    import json
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(body,sort_keys=True,allow_nan=False),encoding='utf-8')


def native_fixture(m,home):
    import base64
    token=lambda x:'V'+base64.b64encode(x.encode()).decode()
    call=m.contract.call_plan()[0];plan={'spec':m.contract.local_spec()};folder=home/'calls'/call['call_id'];folder.mkdir(parents=True)
    (folder/'input.sql').write_text(call['sql'],encoding='utf-8')
    raw='META\t'+call['call_id']+'\t'+token('sum')+'\nROW\t'+call['call_id']+'\t'+token('123.0')+'\nTIME\t'+call['call_id']+'\t1000\n'
    (folder/'result.tsv').write_text(raw,encoding='utf-8')
    log='A query to db: SELECT SUM(1) FROM '+plan['spec']['sample_relation']+', public.dwdate WHERE 1=1\n'
    (folder/'java.stdout.log').write_text(log,encoding='utf-8');(folder/'java.stderr.log').write_text('',encoding='utf-8')
    process=dict(command=list(map(str,m.command('query',plan['spec'],home,call))),exit_code=0,reason=None,seconds=.1,peak_rss_bytes=1024)
    result=m.contract.load_frozen().candidate().parse_engine(raw,[call])[call['call_id']]
    receipt=dict(call=call,result=result,process=process,rewrite=m.rewrite_proof(log,call,plan['spec']),science_window=scan_fixture(m))
    return plan,call,folder,process,receipt


def test_raw_native_decode_exact_sql_argv_and_science_guard_are_independently_rechecked(tmp_path):
    m=module();plan,call,folder,process,receipt=native_fixture(m,tmp_path)
    def save(p,r):
        write_json(m,folder/'java.process.json',p);write_json(m,folder/'receipt.json',r)
        write_json(m,folder/'receipt.seal.json',{'sha256':m.contract.digest(folder/'receipt.json')})
    save(process,receipt);assert m.verify_call(plan,tmp_path,call)==receipt
    for kind in ('argv','point','seconds','rss','busy'):
        p=copy.deepcopy(process);r=copy.deepcopy(receipt)
        if kind=='argv':p['command'][-2]='other.sql';r['process']=p
        if kind=='point':r['result']['rows'][0]['point']=999.
        if kind=='seconds':p['seconds']=-1;r['process']=p
        if kind=='rss':p['peak_rss_bytes']=2*1024**3;r['process']=p
        if kind=='busy':
            row=dict(Name='python.exe',ProcessId=1,CommandLine='python code/full_ssb_local_ci_run.py _worker')
            r['science_window'].update(processes=[row],process_ids=[1],python_processes_checked=1)
        save(p,r)
        with pytest.raises(ValueError):m.verify_call(plan,tmp_path,call)


def budget_fixture(m):
    s=m.contract.local_spec();core=m.contract.load_frozen();limits=s['limits']
    start=dict(limits=limits,available_ram_bytes=5*1024**3,free_disk_bytes=20*1024**3,model_scan=scan_fixture(m))
    sample=core.budget_total(100,200,110,100,15,10)
    sample.update(monotonic=10.,python_rss_bytes=1000,wal_lsn='0/2',wal_generated_bytes=1,wal_lsn_observed_monotonic=9.,monitor_connection_live=False)
    sample['resource_scan']=m.ops.resource_scan_receipt(dict(home=0,staging=0,wal=1,temp=0))
    budget=dict(spec_limits=limits,samples=[sample],peak_total_bytes=sample['total_bytes'],wal_lsn_before='0/1',
        resource_scan_baseline=m.ops.resource_scan_receipt(dict(wal=0,temp=0)),resource_scan_failure=None)
    return {'spec':s},start,budget


def test_readonly_resource_semantics_refuse_undersized_start_corrupt_wal_and_overbudget():
    m=module();plan,start,budget=budget_fixture(m);m.validate_budget(plan,budget,start)
    for kind in ('ram','lsn','total','temp','timestamp','negative_raw_wal'):
        b=copy.deepcopy(budget);s=copy.deepcopy(start)
        if kind=='ram':s['available_ram_bytes']=1
        if kind=='lsn':b['samples'][0]['wal_generated_bytes']=0
        if kind=='total':b['samples'][0]['total_bytes']-=1
        if kind=='temp':b['samples'][0].update(positive_temp_bytes=2*1024**3,total_bytes=2*1024**3+310)
        if kind=='timestamp':b['samples'][0]['wal_lsn_observed_monotonic']=11.
        if kind=='negative_raw_wal':
            b['samples'][0].update(wal_now_bytes=-1,positive_wal_bytes=0,total_bytes=305);b['peak_total_bytes']=305
        with pytest.raises(ValueError):m.validate_budget(plan,b,s)


@pytest.mark.parametrize('kind',['method','bound','bool_retry','negative','too_many','missing','failure'])
def test_offline_resource_audit_cannot_self_reseal_wrong_baseline_method_or_retry_evidence(kind):
    m=module();plan,start,budget=budget_fixture(m);m.validate_budget(plan,budget,start)
    if kind=='method':budget['resource_scan_baseline']['method']='IGNORE_SINGLE_MISSING_FILE'
    if kind=='bound':budget['resource_scan_baseline']['max_additional_rescans']=4
    if kind=='bool_retry':budget['resource_scan_baseline']['retries']['wal']=True
    if kind=='negative':budget['resource_scan_baseline']['retries']['wal']=-1
    if kind=='too_many':budget['resource_scan_baseline']['retries']['wal']=4
    if kind=='missing':del budget['resource_scan_baseline']
    if kind=='failure':budget['resource_scan_failure']={'scope':'wal','error':'failed scan'}
    with pytest.raises(ValueError):m.validate_budget(plan,budget,start)


@pytest.mark.parametrize('action',['run','pilot'])
def test_first_budget_failure_is_logged_by_both_controllers_without_replacing_original_error(tmp_path,monkeypatch,action):
    from types import SimpleNamespace
    m=module();s=m.contract.local_spec();short=tmp_path.parent/('first_'+action);short.mkdir()
    monkeypatch.setattr(m.contract,'ROOT',short)
    error=FileNotFoundError(2,'first sampler exhausted','owned_resource_segment');reports=[]
    failure={'samples':[],'peak_total_bytes':0,'resource_scan_failure':{'scope':'wal','scan':m.ops.resource_scan_receipt({'wal':3}),'error':repr(error)}}
    class Budget:
        samples=[]
        def attach(self,db):raise error
        def close(self):pass
        def report(self):reports.append(True);return failure
    core=SimpleNamespace(available_ram=lambda:5*1024**3,atomic_json=lambda p,v:write_json(m,p,v),pg_control=lambda *a:{'exit_code':3},start_owned_server=lambda *a:{'exit_code':0})
    monkeypatch.setattr(m.contract,'load_frozen',lambda:core)
    monkeypatch.setattr(m.ops,'LocalBudget',lambda *a:Budget());monkeypatch.setattr(m.ops,'LocalDatabase',lambda *a:SimpleNamespace(no_external_clients=lambda:None))
    monkeypatch.setattr(m.ops,'assert_no_science_processes',lambda:scan_fixture(m));monkeypatch.setattr(m.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*1024**3))
    plan=dict(spec=s,binding_sha256='a'*64,parent_expected={},lineage={'oracle':[]},queries=[])
    monkeypatch.setattr(m,'revalidate_plan',lambda p:p);monkeypatch.setattr(m.contract,'build_pilot_plan',lambda p:plan)
    plan_path=short/'plan.json';review=short/'review.json';write_json(m,plan_path,plan)
    status='APPROVED_LOCAL_VERDICT_EXECUTION' if action=='run' else 'APPROVED_LOCAL_VERDICT_SF2_MEASUREMENT'
    write_json(m,review,dict(status=status,binding_sha256='a'*64,limits=s['limits']))
    call=m.run if action=='run' else m.pilot
    with pytest.raises(FileNotFoundError) as raised:call(plan_path,review,m.contract.digest(review),'first',True)
    assert raised.value is error and reports==[True]
    home=short/s['output']/('runs' if action=='run' else 'measurements')/'first'
    assert m.contract.read(home/'failed_budget.json')==failure and m.contract.read(home/'lifecycle.json')['status']=='TAINTED'


@pytest.mark.parametrize('action',['run','pilot'])
@pytest.mark.parametrize('writer_fails',[False,True])
def test_owned_scanner_failure_persists_private_history_without_masking_error_or_owned_shutdown(tmp_path,monkeypatch,action,writer_fails):
    from types import SimpleNamespace
    m=module();s=m.contract.local_spec();monkeypatch.setattr(m.contract,'ROOT',tmp_path)
    diagnostic=dict(status='UNINSPECTABLE_COMMANDLINE',attempt=3,max_additional_rescans=3,
        attempts=[{'attempt':i,'processes':[dict(Name='python.exe',ProcessId=123,CommandLine=None)]} for i in range(4)])
    error=ValueError('Uninspectable process PIDs=[123]');error.scan_diagnostics=diagnostic
    events=[];identity={'pid':987};failed_budget={'samples':[],'resource_scan_failure':None}
    class Budget:
        def attach(self,db):raise error
        def close(self):events.append('budget_closed')
        def report(self):return failed_budget
    def writer(path,value):
        if path.name=='failed_science_scan.json' and writer_fails:raise OSError('diagnostic write failed')
        write_json(m,path,value)
    def pg_control(action,*args):events.append(action);return {'exit_code':0 if action=='stop' else 3}
    def start(home,initial,owned):owned['identity']=identity;events.append('owned_started');return {'exit_code':0}
    core=SimpleNamespace(available_ram=lambda:5*1024**3,atomic_json=writer,pg_control=pg_control,
        start_owned_server=start,postmaster_identity=lambda:identity)
    monkeypatch.setattr(m.contract,'load_frozen',lambda:core)
    monkeypatch.setattr(m.ops,'LocalBudget',lambda *a:Budget())
    monkeypatch.setattr(m.ops,'LocalDatabase',lambda *a:SimpleNamespace(no_external_clients=lambda:None))
    monkeypatch.setattr(m.ops,'assert_no_science_processes',lambda:scan_fixture(m))
    monkeypatch.setattr(m.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*1024**3))
    plan=dict(spec=s,binding_sha256='a'*64,parent_expected={},lineage={'oracle':[]},queries=[])
    monkeypatch.setattr(m,'revalidate_plan',lambda p:p);monkeypatch.setattr(m.contract,'build_pilot_plan',lambda p:plan)
    plan_path=tmp_path/'plan.json';review=tmp_path/'review.json';write_json(m,plan_path,plan)
    status='APPROVED_LOCAL_VERDICT_EXECUTION' if action=='run' else 'APPROVED_LOCAL_VERDICT_SF2_MEASUREMENT'
    write_json(m,review,dict(status=status,binding_sha256='a'*64,limits=s['limits']))
    with pytest.raises(ValueError) as caught:getattr(m,action)(plan_path,review,m.contract.digest(review),'scanner',True)
    assert caught.value is error and events==['status','owned_started','budget_closed','stop','status']
    home=tmp_path/s['output']/('runs' if action=='run' else 'measurements')/'scanner'
    assert m.contract.read(home/'failed_budget.json')==failed_budget
    assert m.contract.read(home/'lifecycle.json')=={'status':'TAINTED','error':repr(error)}
    assert m.contract.read(home/'failed_shutdown.json')['stop']['exit_code']==0
    if writer_fails:assert error.science_scan_diagnostic_write_failed=='OSError'
    else:assert m.contract.read(home/'failed_science_scan.json')==diagnostic


def test_empty_self_resealed_final_map_still_fails_under_forbidden_operations(tmp_path,monkeypatch):
    import subprocess
    m=module();plan=dict(spec=m.contract.local_spec(),binding_sha256='a'*64,queries=m.contract.call_plan());core=m.contract.load_frozen()
    monkeypatch.setattr(m.contract,'ROOT',tmp_path)
    home=tmp_path/plan['spec']['output']/'runs'/'mock';final=dict(valid_header(m,plan),files={})
    for name,value in [('plan.json',plan),('final.json',final)]:write_json(m,home/name,value)
    sha=m.contract.digest(home/'final.json')
    write_json(m,home/'final.seal.json',{'sha256':sha});write_json(m,home/'lifecycle.json',{'status':'PASS','final_sha256':sha})
    monkeypatch.setattr(m,'revalidate_plan',lambda p:p)
    # Frozen utility load needs real small sources; this does not inspect parent models.
    monkeypatch.setattr(m.contract,'load_frozen',lambda:core)
    def forbidden(*args,**kwargs):raise AssertionError('Read-only verification attempted operation')
    monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(m.ops,'LocalDatabase',forbidden)
    with pytest.raises(ValueError,match='required set'):m.verify(home)


def test_pilot_code_runtime_binding_change_fails_before_database_construction(tmp_path,monkeypatch):
    m=module();plan={'binding_sha256':'a'*64,'parent_expected':{}};path=tmp_path/'plan.json';write_json(m,path,plan)
    review=tmp_path/'review.json';write_json(m,review,dict(status='APPROVED_LOCAL_VERDICT_SF2_MEASUREMENT',binding_sha256='a'*64,limits=m.contract.local_spec()['limits']))
    monkeypatch.setattr(m.contract,'build_pilot_plan',lambda x:dict(plan,binding_sha256='b'*64))
    def forbidden(*args,**kwargs):raise AssertionError('Changed pilot source reached PG')
    monkeypatch.setattr(m.ops,'LocalDatabase',forbidden)
    with pytest.raises(ValueError,match='code/runtime/parents'):m.pilot(path,review,m.contract.digest(review),'test',True)


def test_registration_evidence_cannot_reuse_sf2_counts_native_p_or_trailing_cells():
    m=module();s=m.contract.local_spec();prefix='REGISTER\t'+s['sample_relation']+'\t'+str(s['sample_rows'])+'\t'+str(s['population_rows'])+'\t'
    good=prefix+str(s['sample_rows']/s['population_rows'])+'\n';m.validate_registration(s,good)
    for bad in (good.replace('9996946','39587'),prefix+'0.003333',good.strip()+'\textra',prefix+'NaN'):
        with pytest.raises(ValueError):m.validate_registration(s,bad)


def test_fresh_operational_names_are_bounded_before_long_windows_child_paths():
    m=module();assert m.safe_name('a'*32)=='a'*32
    for bad in ('a'*33,'a'*64,'../other','','x/y'):
        with pytest.raises(ValueError):m.safe_name(bad)


@pytest.mark.parametrize('tamper',['missing','sort','keep_ctid','range','restore'])
def test_offline_snapshot_requires_the_auxiliary_physical_scan_proof(monkeypatch,tmp_path,tamper):
    m=module();s=m.contract.local_spec();n=s['sample_rows'];protected={k:{} for k in s['protected_databases']}
    def proof(target,rows,keep=False):
        schema,table=target.split('.')
        return dict(status='PASS_SERIAL_SEQSCAN_MONOTONIC_CTID',table=target,rows=rows,keep_ctid=keep,
            first_ctid=[0,1],last_ctid=[rows,1],settings=['off','0'],previous_settings=['on','2'],restored_settings=['on','2'],
            explain=[{'Plan':{'Node Type':'Seq Scan','Parallel Aware':False,'Schema':schema,'Relation Name':table,'Alias':table}}])
    loads=[]
    for target,rows in [('public.'+t,r) for t,r in s['dimension_rows'].items()]+[(s['sample_relation'],n)]:
        canonical=dict(bytes=rows*20,rows=rows,sha256='a'*64)
        loads.append(dict(status='PASS_COMMITTED_TABLE_IMPORT',table=target,rows=rows,seconds=.1,
            canonical_source=canonical,canonical_actual=canonical,physical_scan=proof(target,rows),
            import_protocol='FRESH_CREATE_SINGLE_COPY_SAME_TRANSACTION_V1',created_and_copied_same_transaction=True,
            copy_from_calls=1,source_eof=True,source_normalized_rows=rows))
    plan={'spec':s,'schema_contract':{t:{'columns':[['id','integer']]} for t in ('dwdate','customer','supplier','part','lineorder')}}
    snapshot=dict(status='PASS_LOCAL_LOCKED_FULL_INPUT_SNAPSHOT',original_fact_rows=0,loads=loads,schema=m.ops.expected_schema(plan),catalog={},
        aux_accounting=[n,n/s['population_rows'],n/s['population_rows'],0,99],probability_hex=[m.ops.probability_hex(s)]*2,
        partition_histogram=[[i,n//100+(i<n%100)] for i in range(100)],
        metadata_size=[['public_verdict',s['sample_relation'].split('.')[1],n,s['population_rows']]],
        metadata_name=[['public','lineorder','public_verdict',s['sample_relation'].split('.')[1],'uniform',n/s['population_rows'],'']],
        protected_before=protected,protected_after=protected,aux_rows=dict(bytes=n*40,rows=n,sha256='c'*64,physical_scan=proof(s['sample_relation'],n,True)))
    imported=dict(status='PASS_LOCAL_FULL_DIMENSIONS_RETAINED_FACT_IMPORT',loads=loads,population_rows=s['population_rows'],sample_rows=n,
        original_fact_rows=0,original_queries_executed=0,dimension_policy=s['dimension_policy'])
    files={'import.json':imported,'snapshot_before.json':snapshot,'snapshot_after.json':snapshot,'protected_before.json':protected,
        'post_run.json':dict(status='PASS_LOCAL_SHARE_LOCKED_38_CALLS',share_lock_held_across_calls=38,before_sha256='b'*64,after_sha256='b'*64)}
    for table in ('dwdate','customer','part','supplier','lineorder'):
        target=s['sample_relation'] if table=='lineorder' else 'public.'+table
        files['import_'+table+'.json']=next(row for row in loads if row['table']==target)
    monkeypatch.setattr(m.contract,'read',lambda p:files[Path(p).name]);monkeypatch.setattr(m.contract,'digest',lambda p:'b'*64)
    monkeypatch.setattr(m.ops,'validate_catalog',lambda *args:None)
    m.validate_snapshots(plan,tmp_path)
    aux=snapshot['aux_rows']['physical_scan']
    if tamper=='missing':del snapshot['aux_rows']['physical_scan']
    elif tamper=='sort':aux['explain'][0]['Plan']['Node Type']='Sort'
    elif tamper=='keep_ctid':aux['keep_ctid']=False
    elif tamper=='range':aux['last_ctid']=[0,1]
    elif tamper=='restore':aux['restored_settings']=['off','0']
    with pytest.raises(ValueError):m.validate_snapshots(plan,tmp_path)
