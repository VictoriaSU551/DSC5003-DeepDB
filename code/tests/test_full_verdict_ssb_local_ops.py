"""Pure explicit-target/storage semantics; no real DB or process."""
import importlib.util
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_verdict_ssb_local_ops.py';assert p.exists(),'Explicit LOCAL database operations missing'
    s=importlib.util.spec_from_file_location('local_verdict_ops_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


@pytest.mark.parametrize('script,action',[
    ('full_ssb_local_ci_run.py','_worker'),('full_ssb_local_ci_run.py','supervise'),
    ('full_ssb_local_ci_replay.py','worker'),('full_ssb_local_replay.py','replay'),
    ('full_ssb_local_model_run.py','_worker'),('full_training.py','train'),
    ('full_ssb_local_canonical_run.py','_worker'),('full_ssb_local_canonical_run.py','supervise'),
    ('full_ssb_local_ci_group_replay.py','worker'),('full_ssb_scoped_replay.py','worker'),
    ('full_ssb_local_continuation_run.py','_bootstrap'),('full_ssb_local_continuation_run.py','_worker'),
    ('full_ssb_local_continuation_run.py','supervise')])
def test_busy_science_guard_covers_actual_ci_model_and_reverse_entrypoints(script,action):
    m=module();command='"C:\\project\\.venv\\Scripts\\python.exe" "C:\\project\\code\\'+script+'" '+action
    rows=[dict(Name='python.exe',ProcessId=123,CommandLine=command)]
    with pytest.raises(ValueError,match='science'):m.check_science_processes(rows)
    # Pure imports, pytest and this controller itself do not match a scientific entry point.
    m.check_science_processes([dict(Name='python.exe',ProcessId=124,CommandLine='python code/full_verdict_ssb_local_run.py describe')])


def _python_row(pid=123,command='python ordinary_audit.py'):
    return dict(Name='python.exe',ProcessId=pid,CommandLine=command)


def _cim_responses(m,monkeypatch,snapshots):
    import json
    from types import SimpleNamespace
    calls=[];remaining=iter(snapshots)
    def run(command,**kwargs):
        calls.append(list(command))
        value=next(remaining)
        if isinstance(value,Exception):raise value
        return SimpleNamespace(stdout=json.dumps(value).encode('utf-8'))
    monkeypatch.setattr(m.subprocess,'run',run)
    return calls


@pytest.mark.parametrize('snapshots',[
    [[_python_row(command=None)],[_python_row()]],
    [[_python_row(command='')],[]],
    [[_python_row(command=None)],[_python_row(124,command='')],[_python_row(125,command=None)],[_python_row(126)]],
])
def test_whole_cim_rescan_keeps_every_raw_attempt_and_only_accepts_complete_fresh_snapshot(monkeypatch,snapshots):
    m=module();calls=_cim_responses(m,monkeypatch,snapshots)
    result=m.assert_no_science_processes()
    assert result['scan_method']=='WHOLE_CIM_RESCAN_ON_UNINSPECTABLE_COMMANDLINE_V1'
    assert result['max_additional_rescans']==3 and result['additional_rescans']==len(snapshots)-1
    assert [a['processes'] for a in result['attempts']]==snapshots
    assert result['processes']==snapshots[-1] and result['python_processes_checked']==len(snapshots[-1])
    assert result['process_ids']==[r['ProcessId'] for r in snapshots[-1]]
    assert len(calls)==len(snapshots) and all(c==m.SCIENCE_SCAN_COMMAND for c in calls)
    m.validate_science_scan(result)


def test_whole_cim_rescan_exhaustion_reports_only_pids_and_status_without_skipping(monkeypatch):
    m=module();calls=_cim_responses(m,monkeypatch,[[_python_row(command=None)]]*4+[[]])
    with pytest.raises(ValueError,match='Uninspectable') as caught:m.assert_no_science_processes()
    assert len(calls)==4 and '123' in str(caught.value)
    diagnostic=caught.value.scan_diagnostics
    assert {k:diagnostic[k] for k in ('status','attempt','max_additional_rescans','process_ids')}==dict(status='UNINSPECTABLE_COMMANDLINE',attempt=3,max_additional_rescans=3,process_ids=[123])


@pytest.mark.parametrize('kind',['exhausted','bad_header','known_conflict','unavailable'])
def test_failed_cim_scan_retains_every_acquired_snapshot_including_rejected_terminal_rows(monkeypatch,kind):
    m=module();first=[_python_row(command=None)];private='private_scanner_argument'
    if kind=='exhausted':snapshots=[first]*4
    elif kind=='bad_header':snapshots=[first,[dict(Name='python.exe',ProcessId=124,CommandLine='',extra=True)]]
    elif kind=='known_conflict':snapshots=[first,[_python_row(124,'python full_ssb_local_ci_run.py _worker '+private)]]
    else:snapshots=[first,PermissionError('CIM unavailable')]
    calls=_cim_responses(m,monkeypatch,snapshots)
    with pytest.raises((ValueError,PermissionError)) as caught:m.assert_no_science_processes()
    diagnostic=caught.value.scan_diagnostics
    assert diagnostic['scan_method']=='WHOLE_CIM_RESCAN_ON_UNINSPECTABLE_COMMANDLINE_V1'
    assert diagnostic['command']==m.SCIENCE_SCAN_COMMAND and diagnostic['additional_rescans']==len(snapshots)-1
    assert len(diagnostic['attempts'])==len(calls)==len(snapshots)
    for index,(attempt,original) in enumerate(zip(diagnostic['attempts'],snapshots)):
        assert attempt['attempt']==index
        if isinstance(original,Exception):
            assert attempt['raw_rows_available'] is False and attempt['processes'] is None and attempt['status']=='SNAPSHOT_UNAVAILABLE'
        else:
            assert attempt['raw_rows_available'] is True and attempt['processes']==original
            assert attempt['raw_row_count']==len(original)
    assert private not in str(caught.value)


@pytest.mark.parametrize('attempt',[0,1,2,3])
def test_whole_cim_rescan_known_conflict_in_any_attempt_fails_even_beside_unreadable_row(monkeypatch,attempt):
    m=module();secret='private_arg_should_not_be_in_error'
    conflict=_python_row(777,'python full_ssb_local_ci_run.py _worker '+secret)
    snapshots=[[_python_row(command=None)]]*attempt+[[_python_row(command=None),conflict],[]]
    calls=_cim_responses(m,monkeypatch,snapshots)
    with pytest.raises(ValueError,match='science') as caught:m.assert_no_science_processes()
    assert len(calls)==attempt+1 and '777' in str(caught.value) and secret not in str(caught.value)


@pytest.mark.parametrize('rows',[
    {},None,[dict(Name='python.exe',ProcessId=123)],[_python_row(True)],[_python_row(0)],
    [dict(Name=123,ProcessId=123,CommandLine='python audit.py')],
    [dict(Name='java.exe',ProcessId=123,CommandLine='python audit.py')],
    [_python_row(command=123)],[_python_row(command=False)],[_python_row(),_python_row()],
    [_python_row(command=None),dict(Name='python.exe',ProcessId=124,CommandLine=[],extra=True)],
])
def test_whole_cim_rescan_bad_headers_types_and_duplicate_ids_never_trigger_retry(monkeypatch,rows):
    m=module();calls=_cim_responses(m,monkeypatch,[rows,[]])
    with pytest.raises(ValueError):m.assert_no_science_processes()
    assert len(calls)==1


def test_whole_cim_rescan_process_errors_are_not_retried(monkeypatch):
    m=module();error=PermissionError('CIM unavailable');calls=_cim_responses(m,monkeypatch,[error,[]])
    with pytest.raises(PermissionError) as caught:m.assert_no_science_processes()
    assert caught.value is error and len(calls)==1


@pytest.mark.parametrize('snapshot',[_python_row(),[]])
def test_whole_cim_rescan_accepts_original_single_object_and_empty_cim_output_without_extra_snapshot(monkeypatch,snapshot):
    m=module();calls=_cim_responses(m,monkeypatch,[snapshot])
    result=m.assert_no_science_processes()
    expected=[snapshot] if isinstance(snapshot,dict) else []
    assert result['processes']==expected and result['additional_rescans']==0 and len(result['attempts'])==1 and len(calls)==1


def test_whole_cim_rescan_malformed_json_fails_without_retry(monkeypatch):
    from types import SimpleNamespace
    m=module();calls=[]
    def run(*args,**kwargs):calls.append(args);return SimpleNamespace(stdout=b'{not json')
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(ValueError) as caught:m.assert_no_science_processes()
    assert len(calls)==1 and caught.value.scan_diagnostics['status']=='SNAPSHOT_REJECTED'


def _literal_cim_receipt(m):
    return dict(status='NO_CONFLICTING_SCIENCE_ACTIVE',command=m.SCIENCE_SCAN_COMMAND,
        scan_method='WHOLE_CIM_RESCAN_ON_UNINSPECTABLE_COMMANDLINE_V1',max_additional_rescans=3,additional_rescans=1,
        attempts=[dict(attempt=0,processes=[_python_row(command=None)],python_processes_checked=1,process_ids=[123],uninspectable_process_ids=[123]),
                  dict(attempt=1,processes=[_python_row(124)],python_processes_checked=1,process_ids=[124],uninspectable_process_ids=[])],
        processes=[_python_row(124)],python_processes_checked=1,process_ids=[124])


def test_offline_cim_scan_audit_revalidates_recorded_rows_without_running_processes(monkeypatch):
    m=module()
    def forbidden(*args,**kwargs):raise AssertionError('Offline evidence triggered a live process')
    monkeypatch.setattr(m.subprocess,'run',forbidden)
    m.validate_science_scan(_literal_cim_receipt(m))


@pytest.mark.parametrize('kind',['method','bound','bool_bound','count','bool_count','attempt_index','bool_index',
    'attempt_count','bool_attempt_count','attempt_ids','uninspectable_ids','nonterminal_complete','terminal_uninspectable',
    'duplicate_ids','bad_schema','conflict','last_rows','last_count','bool_last_count','last_ids','missing_attempts','unknown_field','too_many'])
def test_offline_cim_scan_audit_rejects_self_resealed_incomplete_or_mutated_attempts(kind):
    m=module();good=_literal_cim_receipt(m);m.validate_science_scan(good)
    if kind=='method':good['scan_method']='IGNORE_UNREADABLE'
    if kind=='bound':good['max_additional_rescans']=4
    if kind=='bool_bound':good['max_additional_rescans']=True
    if kind=='count':good['additional_rescans']=0
    if kind=='bool_count':good['additional_rescans']=True
    if kind=='attempt_index':good['attempts'][0]['attempt']=1
    if kind=='bool_index':good['attempts'][0]['attempt']=False
    if kind=='attempt_count':good['attempts'][0]['python_processes_checked']=0
    if kind=='bool_attempt_count':good['attempts'][0]['python_processes_checked']=True
    if kind=='attempt_ids':good['attempts'][0]['process_ids']=[]
    if kind=='uninspectable_ids':good['attempts'][0]['uninspectable_process_ids']=[]
    if kind=='nonterminal_complete':good['attempts'][0]['processes'][0]['CommandLine']='python audit.py';good['attempts'][0]['uninspectable_process_ids']=[]
    if kind=='terminal_uninspectable':good['attempts'][1]['processes'][0]['CommandLine']=None
    if kind=='duplicate_ids':good['attempts'][0]['processes']*=2
    if kind=='bad_schema':good['attempts'][0]['processes'][0]['extra']=True
    if kind=='conflict':good['attempts'][0]['processes'][0]['CommandLine']='python full_ssb_local_continuation_run.py supervise'
    if kind=='last_rows':good['processes']=[]
    if kind=='last_count':good['python_processes_checked']=0
    if kind=='bool_last_count':good['python_processes_checked']=True
    if kind=='last_ids':good['process_ids']=[]
    if kind=='missing_attempts':del good['attempts']
    if kind=='unknown_field':good['skip_uninspectable']=True
    if kind=='too_many':good['additional_rescans']=4;good['attempts']=good['attempts'][:1]*4+good['attempts'][1:]
    with pytest.raises(ValueError):m.validate_science_scan(good)


def load_fixture(m,committed=False):
    rows=[]
    s=m.contract.local_spec();expected={'public.'+t:n for t,n in s['dimension_rows'].items()};expected[s['sample_relation']]=s['sample_rows']
    for table,count in expected.items():
        canonical=dict(bytes=count*30,rows=count,sha256='a'*64)
        proof=dict(status='PASS_SERIAL_SEQSCAN_MONOTONIC_CTID',table=table,rows=count,keep_ctid=False,
            first_ctid=[0,1],last_ctid=[count//100,1+count%100],explain=_scan_plan(table),settings=['off','0'],previous_settings=['on','2'],restored_settings=['on','2'])
        row=dict(table=table,rows=count,canonical_actual=canonical,physical_scan=proof)
        if committed:row.update(status='PASS_COMMITTED_TABLE_IMPORT',canonical_source=canonical,seconds=.5,
            import_protocol='FRESH_CREATE_SINGLE_COPY_SAME_TRANSACTION_V1',created_and_copied_same_transaction=True,
            copy_from_calls=1,source_eof=True,source_normalized_rows=count)
        rows.append(row)
    return rows


@pytest.mark.parametrize('committed',[False,True])
def test_complete_five_unique_full_field_snapshots_reject_duplicate_missing_wrong_rows_and_malformed_hash(committed):
    import copy
    m=module();good=load_fixture(m,committed);m.validate_loads(m.contract.local_spec(),good,committed)
    for kind in ('duplicate','rows','canonical_rows','zero_bytes','sha','seconds','scan_plan','scan_rows','scan_restore','scan_range'):
        if kind=='seconds' and not committed:continue
        bad=copy.deepcopy(good)
        if kind=='duplicate':bad[1]=copy.deepcopy(bad[0])
        if kind=='rows':bad[1]['rows']-=1
        if kind=='canonical_rows':bad[-1]['canonical_actual']['rows']-=1
        if kind=='zero_bytes':bad[0]['canonical_actual']['bytes']=0
        if kind=='sha':bad[0]['canonical_actual']['sha256']='fake'
        if kind=='seconds':bad[0]['seconds']=float('inf')
        if kind=='scan_plan':bad[0]['physical_scan']['explain'][0]['Plan']['Node Type']='Sort'
        if kind=='scan_rows':bad[0]['physical_scan']['rows']-=1
        if kind=='scan_restore':bad[0]['physical_scan']['restored_settings']=['off','0']
        if kind=='scan_range':bad[0]['physical_scan']['last_ctid']=[0,1]
        with pytest.raises(ValueError):m.validate_loads(m.contract.local_spec(),bad,committed)


def test_connection_uses_local_database_and_never_changes_frozen_sf2_globals(monkeypatch):
    m=module();db=m.LocalDatabase();calls=[]
    class Driver:
        @staticmethod
        def connect(**kw):calls.append(kw);return type('Connection',(),{})()
    monkeypatch.setitem(sys.modules,'psycopg2',Driver)
    db.connect();assert calls[0]['dbname']=='deepdb_verdict_ssb_local500_v13'
    assert 'extra_float_digits=3' in calls[0]['options'] and 'temp_file_limit=1048576' in calls[0]['options']
    assert db.core.DB=='deepdb_verdict_ssb' and db.core.LIMITS['total_new_bytes']==1024**3
    with pytest.raises(ValueError):db.connect('unowned')


def test_local_metadata_requires_actual_n_over_N_and_full_dimensions_unregistered():
    m=module();s=m.contract.local_spec();size=[['public_verdict','vs_lineorder_uf_0_0033',s['sample_rows'],s['population_rows']]]
    names=[['public','lineorder','public_verdict','vs_lineorder_uf_0_0033','uniform',s['sample_rows']/s['population_rows'],'']]
    m.validate_metadata(s,size,names)
    with pytest.raises(ValueError):m.validate_metadata(s,[['public_verdict','vs_lineorder_uf_0_0033',39587,11997996]],names)
    with pytest.raises(ValueError):m.validate_metadata(s,size,names+[['public','customer','public','customer','uniform',1.,'']])


def test_independent_12gib_budget_rejects_component_cap_even_if_total_is_below_cap():
    m=module();s=m.contract.local_spec();base=dict(owned_files_bytes=1,owned_database_bytes=1,positive_wal_bytes=0,positive_temp_bytes=0,total_bytes=2,python_rss_bytes=1,resource_scan=_scan_receipt())
    m.validate_budget_sample(s,base)
    bad=dict(base,positive_temp_bytes=2*1024**3,total_bytes=2+2*1024**3)
    with pytest.raises(ValueError):m.validate_budget_sample(s,bad)
    with pytest.raises(ValueError):m.validate_budget_sample(s,dict(base,total_bytes=1))


def test_local_aux_probability_native_bits_differ_from_sf2_and_partition_coverage_is_exact():
    m=module();s=m.contract.local_spec();account=[s['sample_rows'],s['sample_rows']/s['population_rows'],s['sample_rows']/s['population_rows'],0,99]
    parts=[[i,s['sample_rows']//100+(i<s['sample_rows']%100)] for i in range(100)]
    m.validate_aux(s,account,parts,[m.probability_hex(s)]*2)
    assert m.probability_hex(s)!='3f6b077c38a5b19d'
    with pytest.raises(ValueError):m.validate_aux(s,account,parts[:-1],[m.probability_hex(s)]*2)


def test_stopped_budget_samples_keep_last_live_lsn_without_a_new_database_call(monkeypatch,tmp_path):
    m=module();core=m.contract.load_frozen()
    fake,home,stage=_resource_roots(m,tmp_path,monkeypatch)
    fake.budget_total=core.budget_total;fake.lsn_integer=core.lsn_integer;fake.tree_bytes=lambda p:0;fake.process_rss=lambda p:100
    b=m.LocalBudget.__new__(m.LocalBudget)
    b.spec=m.contract.local_spec();b.home=home;b.stage=stage;b.core=fake;b.connection=None;b.samples=[]
    b.last_database_bytes=200;b.wal_before=0;b.temp_before=0;b.wal_lsn_before='0/1';b.last_wal_lsn='0/3';b.last_lsn_observed=0.
    last=b.tick(force=True)
    assert last['wal_generated_bytes']==2 and last['wal_lsn']=='0/3' and last['monitor_connection_live'] is False
    assert last['wal_lsn_observed_monotonic']==0. and last['owned_database_bytes']==200


class _HashSink:
    def __init__(self,watch=None):
        import hashlib
        self.hash=hashlib.sha256();self.bytes=0;self.rows=0;self.watch=watch
    def write(self,data):
        if isinstance(data,str):data=data.encode('utf-8')
        self.hash.update(data);self.bytes+=len(data);self.rows+=data.count(b'\n')
        if self.watch is not None:self.watch.tick()
        return len(data)
    def result(self):return dict(bytes=self.bytes,rows=self.rows,sha256=self.hash.hexdigest())


def _scan_plan(target='public.customer'):
    schema,relation=target.split('.')
    return [{'Plan':{'Node Type':'Seq Scan','Parallel Aware':False,'Schema':schema,'Relation Name':relation,'Alias':relation}}]


class _CopyCursor:
    def __init__(self,fragments,plan=None,fail_copy=None,fail_restore=False):
        self.fragments=fragments;self.plan=_scan_plan() if plan is None else plan
        self.settings=('on','2');self.calls=[];self.copies=[];self.fail_copy=fail_copy;self.fail_restore=fail_restore
    def execute(self,sql,args=None):
        self.calls.append((sql,args))
        if sql.startswith('SET LOCAL synchronize_seqscans'):self.settings=('off',self.settings[1])
        elif sql.startswith('SET LOCAL max_parallel_workers_per_gather'):self.settings=(self.settings[0],'0')
        elif 'set_config(' in sql:
            if self.fail_restore:raise RuntimeError('restore failed')
            self.settings=tuple(args)
    def fetchone(self):
        return (self.plan,) if self.calls[-1][0].startswith('EXPLAIN') else self.settings
    def copy_expert(self,sql,sink):
        self.copies.append(sql)
        assert self.settings==('off','0')
        if self.fail_copy:raise self.fail_copy
        for fragment in self.fragments:sink.write(fragment)


@pytest.mark.parametrize('keep_ctid',[False,True])
def test_physical_copy_keeps_exact_utf8_csv_duplicates_and_aux_ctid_for_every_split(keep_ctid):
    import hashlib
    from types import SimpleNamespace
    m=module();payload='1|""|"\\N"|"a""b"|中文\n'.encode('utf-8')
    raw=b'(0,1)|'+payload+b'(0,2)|'+payload+b'(2,1)|9|last\n'
    expected=raw if keep_ctid else payload*2+b'9|last\n'
    for cut in range(len(raw)+1):
        c=_CopyCursor([raw[:cut],raw[cut:]])
        sink=m.copy_physical(c,'public.customer','"id","value"',SimpleNamespace(CopyHashSink=_HashSink),None,keep_ctid)
        assert sink.result()==dict(bytes=len(expected),rows=3,sha256=hashlib.sha256(expected).hexdigest())
        assert c.settings==('on','2') and len(c.copies)==1 and ' FROM ONLY public.customer)' in c.copies[0]
        assert 'ORDER BY' not in c.copies[0] and 'WHERE' not in c.copies[0]
        assert sink.physical_scan['first_ctid']==[0,1] and sink.physical_scan['last_ctid']==[2,1]
        m.validate_physical_scan(sink.physical_scan,'public.customer',3,keep_ctid)


@pytest.mark.parametrize('raw',[
    b'',b'(0,1)|a',b'(0,1)|a\npartial',b'(0,1)|a\n(0,1)|a\n',b'(2,1)|a\n(1,1)|b\n',
    b'"(0,1)"|a\n',b'(0,0)|a\n',b'(0,65536)|a\n',b'(4294967295,1)|a\n',b'(0,1)|\n',
    b'(0,1)|a\rb\n',b'(0,1)|a\x00b\n',b'(0,1)|"a\nb"\n'])
def test_physical_copy_rejects_empty_truncated_or_nonmonotonic_records_and_restores(raw):
    from types import SimpleNamespace
    m=module();c=_CopyCursor([raw])
    with pytest.raises(ValueError):m.copy_physical(c,'public.customer','"id"',SimpleNamespace(CopyHashSink=_HashSink),None)
    assert c.settings==('on','2')


@pytest.mark.parametrize('kind',['sort','gather','child','alias','relation','schema','parallel','missing','multiple'])
def test_physical_copy_refuses_any_nonserial_or_wrong_relation_plan_before_copy(kind):
    from types import SimpleNamespace
    m=module();plan=_scan_plan();node=plan[0]['Plan']
    if kind in ('sort','gather'):node['Node Type']={'sort':'Sort','gather':'Gather'}[kind]
    elif kind=='child':node['Plans']=[]
    elif kind=='alias':node['Alias']='other'
    elif kind=='relation':node['Relation Name']='supplier'
    elif kind=='schema':node['Schema']='other'
    elif kind=='parallel':node['Parallel Aware']=True
    elif kind=='missing':del node['Parallel Aware']
    elif kind=='multiple':plan*=2
    c=_CopyCursor([b'(0,1)|a\n'],plan)
    with pytest.raises(ValueError):m.copy_physical(c,'public.customer','"id"',SimpleNamespace(CopyHashSink=_HashSink),None)
    assert not c.copies and c.settings==('on','2')


def test_physical_copy_first_error_survives_restore_failure_and_success_needs_restore():
    from types import SimpleNamespace
    m=module();core=SimpleNamespace(CopyHashSink=_HashSink)
    c=_CopyCursor([],fail_copy=RuntimeError('original COPY failure'),fail_restore=True)
    with pytest.raises(RuntimeError,match='original COPY failure'):m.copy_physical(c,'public.customer','"id"',core,None)
    c=_CopyCursor([b'(0,1)|a\n'],fail_restore=True)
    with pytest.raises(RuntimeError,match='restore failed'):m.copy_physical(c,'public.customer','"id"',core,None)


def test_physical_copy_record_and_fragment_memory_bounds_fail_closed():
    from types import SimpleNamespace
    m=module();core=SimpleNamespace(CopyHashSink=_HashSink)
    for fragments in ([b'(0,1)|'+b'a'*65536+b'\n'],[b'(0,1)|',b'a'*65536],[b'a'*(8*1024**2+1)]):
        with pytest.raises(ValueError):m.copy_physical(_CopyCursor(fragments),'public.customer','"id"',core,None)


def test_v13_database_namespace_matches_java_and_preserves_fixed_resource_caps():
    m=module();s=m.contract.local_spec()
    assert s['database']=='deepdb_verdict_ssb_local500_v13'
    java=(ROOT/s['java_source']).read_text(encoding='utf-8')
    assert 'static final String DATABASE="'+s['database']+'";' in java
    assert s['limits']['python_rss_bytes']==512*1024**2 and s['limits']['work_mem_kib']==16384
    assert s['limits']['temp_file_limit_kib']==1048576 and s['limits']['total_new_bytes']==12*1024**3


def test_auxiliary_physical_copy_keeps_ctid_in_the_original_hash():
    import hashlib
    from types import SimpleNamespace
    m=module();db=m.LocalDatabase.__new__(m.LocalDatabase);db.spec=m.contract.local_spec();db.core=SimpleNamespace(CopyHashSink=_HashSink)
    target=db.spec['sample_relation'];raw=b'(0,1)|3f6b077c38a5b19d|12\n(0,2)|3f6b077c38a5b19d|39\n'
    c=_CopyCursor([raw],_scan_plan(target));result=db.aux_hash(c,None)
    assert result['sha256']==hashlib.sha256(raw).hexdigest() and result['bytes']==len(raw) and result['rows']==2
    m.validate_physical_scan(result['physical_scan'],target,2,True)
    assert "encode(float8send(verdict_vprob),'hex'),verdict_vpart" in c.copies[0]


def test_all_five_import_roundtrips_use_one_linear_physical_copy_each(monkeypatch,tmp_path):
    import io
    from types import SimpleNamespace
    m=module();saved={};original='1|""|"\\N"|"a""b"|中文\n';payload=original.encode('utf-8')
    budget=SimpleNamespace(tick=lambda **kw:None)
    class Cursor(_CopyCursor):
        def __init__(self):super().__init__([]);self.tables={}
        def __enter__(self):return self
        def __exit__(self,*unused):pass
        def execute(self,sql,args=None):
            super().execute(sql,args)
            if sql.startswith('EXPLAIN'):self.plan=_scan_plan(sql.rsplit(' FROM ONLY ',1)[1])
        def fetchone(self):
            sql=self.calls[-1][0]
            if sql=='SHOW server_version':return ('11.5',)
            if sql=='SHOW data_directory':return (str(tmp_path),)
            if sql.startswith('SELECT 1 FROM pg_database'):return None
            if sql=='SELECT COUNT(*) FROM public.lineorder':return (0,)
            return super().fetchone()
        def copy_expert(self,sql,sink,**kwargs):
            if ' FROM STDIN ' in sql:
                chunks=[]
                while True:
                    value=sink.read(65536)
                    if not value:break
                    chunks.append(value.encode('utf-8') if isinstance(value,str) else value)
                self.tables[sql.split()[1]]=b''.join(chunks);return
            target=sql.split(' FROM ONLY ',1)[1].split(')',1)[0]
            assert self.tables[target]==payload
            self.fragments=[b'(0,1)|'+self.tables[target]];super().copy_expert(sql,sink)
    c=Cursor()
    connection=SimpleNamespace(cursor=lambda:c,commit=lambda:None,close=lambda:None)
    db=m.LocalDatabase.__new__(m.LocalDatabase);db.spec=m.contract.local_spec()
    db.core=SimpleNamespace(CLUSTER=tmp_path,CopyHashSink=_HashSink,atomic_json=lambda p,v:saved.__setitem__(Path(p).name,v),
        raw_chunks=lambda *a:iter([(1,[],original)]),create_table_sql=lambda t,s,k:'CREATE TABLE '+t)
    monkeypatch.setattr(db,'connect',lambda *a:connection);monkeypatch.setattr(db,'no_external_clients',lambda:None)
    monkeypatch.setattr(db,'protected',lambda:{k:{} for k in db.spec['protected_databases']})
    monkeypatch.setattr(m,'assert_no_science_processes',lambda:None)
    tables=['dwdate','customer','part','supplier','lineorder']
    monkeypatch.setattr(m,'expected_inputs',lambda p:[(t,tmp_path/t,True,1) for t in tables])
    result=db.import_data({'schema_contract':{t:{'columns':[['id','int'],['empty','text'],['literal','text'],['quote','text'],['unicode','text']]} for t in tables}},tmp_path,budget)
    assert len(c.copies)==5 and result['original_queries_executed']==0 and saved['import.json']==result
    for row in result['loads']:
        assert row['canonical_source']==row['canonical_actual'] and row['canonical_actual']['bytes']==len(payload)
        m.validate_physical_scan(row['physical_scan'],row['table'],1)
    assert c.settings==('on','2') and not any('ORDER BY ctid' in sql for sql in c.copies)


def test_locked_snapshot_delegates_full_field_readback_to_the_same_physical_guard(monkeypatch,tmp_path):
    m=module();db=m.LocalDatabase.__new__(m.LocalDatabase);db.spec=m.contract.local_spec();db.core=object()
    before={k:{} for k in db.spec['protected_databases']};c=object();budget=object();calls=[]
    monkeypatch.setattr(m.contract,'read',lambda path:before if Path(path).name=='protected_before.json' else {'loads':[]})
    monkeypatch.setattr(db,'protected',lambda:before)
    monkeypatch.setattr(m,'expected_inputs',lambda plan:[('customer',tmp_path/'not_read',True,15_000_000)])
    class ReachedPhysicalGuard(Exception):pass
    def guard(*args):calls.append(args);raise ReachedPhysicalGuard
    monkeypatch.setattr(m,'copy_physical',guard)
    with pytest.raises(ReachedPhysicalGuard):db.locked_snapshot({'schema_contract':{'customer':{'columns':[['id','int']]}}},tmp_path,c,budget)
    assert calls==[(c,'public.customer','"id"',db.core,budget)]


@pytest.mark.parametrize('size',[1,3,17,65536])
def test_single_copy_reader_is_bounded_exact_and_requires_complete_eof(size):
    m=module();source=_HashSink();payload='1|""|中文\n2|"\\N"|"a""b"\n'.encode('utf-8')
    chunks=iter([(1,[],'1|""|中文\n'),(1,[],'2|"\\N"|"a""b"\n')])
    reader=m.NormalizedCopyReader(chunks,source)
    with pytest.raises(ValueError):reader.finish(2)
    result=[]
    while True:
        block=reader.read(size)
        if not block:break
        assert isinstance(block,bytes) and len(block)<=size;result.append(block)
    reader.finish(2);assert b''.join(result)==payload and source.rows==reader.normalized_rows==2
    expected=_HashSink();expected.write(payload);assert source.result()==expected.result()
    for bad in (-1,65537,True):
        with pytest.raises(ValueError):reader.read(bad)
    with pytest.raises(ValueError):reader.finish(3)
    reader.close()
    with pytest.raises(ValueError):reader.read(1)


@pytest.mark.parametrize('chunk',[(True,[],'x\n'),(2,[],'x\n'),(1,[],b'x\n'),(0,[],''),(1,[],'x'*(8*1024**2+1)),(1,[],'x\ntrailing')])
def test_single_copy_reader_rejects_malformed_or_oversized_normalized_chunks(chunk):
    m=module();reader=m.NormalizedCopyReader(iter([chunk]),_HashSink())
    with pytest.raises(ValueError):reader.read(65536)
    reader.close()


def test_single_copy_reader_resource_denial_precedes_source_consumption():
    from types import SimpleNamespace
    m=module();started=[];source=_HashSink()
    def chunks():started.append(True);yield 1,[],'1|value\n'
    def deny():raise ValueError('resource window closed')
    reader=m.NormalizedCopyReader(chunks(),source,SimpleNamespace(tick=deny))
    with pytest.raises(ValueError,match='resource window'):reader.read(65536)
    assert not started and source.bytes==source.rows==0 and not reader.eof
    reader.close()


@pytest.mark.parametrize('failure',[None,'COPY_FROM','EARLY_RETURN','READBACK_HASH','SOURCE_CLOSE','COPY_FROM_CLOSE'])
def test_import_creates_each_target_in_its_single_copy_transaction_and_keeps_failure_stats(monkeypatch,tmp_path,failure):
    from types import SimpleNamespace
    m=module();saved={};state={'tx':0,'created':{},'copies':0};original=['1|alpha\n','2|beta\n'];target='public.customer'
    budget=SimpleNamespace(tick=lambda **kw:None)
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*unused):pass
        def execute(self,sql,args=None):
            self.sql=sql
            if sql.startswith('CREATE TABLE '):state['created'][sql.split()[2]]=state['tx']
        def fetchone(self):
            if self.sql=='SHOW server_version':return ('11.5',)
            if self.sql=='SHOW data_directory':return (str(tmp_path),)
            if self.sql.startswith('SELECT 1 FROM pg_database'):return None
            if self.sql=='SELECT COUNT(*) FROM public.lineorder':return (0,)
            raise AssertionError(self.sql)
        def copy_expert(self,sql,reader,**kwargs):
            assert state['created'][target]==state['tx'],'COPY target was committed before import'
            state['copies']+=1;assert state['copies']==1,'Each target must have exactly one COPY FROM'
            assert kwargs.get('size')==65536
            if failure=='EARLY_RETURN':reader.read(4);return
            blocks=[]
            while True:
                data=reader.read(65536)
                if not data:break
                blocks.append(data)
                if failure in ('COPY_FROM','COPY_FROM_CLOSE'):raise RuntimeError('simulated backend COPY failure')
            assert b''.join(blocks)==''.join(original).encode('utf-8')
    c=Cursor()
    def commit():state['tx']+=1
    connection=SimpleNamespace(cursor=lambda:c,commit=commit,close=lambda:None)
    db=m.LocalDatabase.__new__(m.LocalDatabase);db.spec=m.contract.local_spec()
    class Chunks:
        def __init__(self):self.items=iter([(1,[],text) for text in original])
        def __iter__(self):return self
        def __next__(self):return next(self.items)
        def close(self):
            if failure in ('SOURCE_CLOSE','COPY_FROM_CLOSE'):raise RuntimeError('simulated source close failure')
    db.core=SimpleNamespace(CLUSTER=tmp_path,CopyHashSink=_HashSink,atomic_json=lambda p,v:saved.__setitem__(Path(p).name,v),
        raw_chunks=lambda *a:Chunks(),create_table_sql=lambda t,s,k:'CREATE TABLE public.'+t)
    monkeypatch.setattr(db,'connect',lambda *a:connection);monkeypatch.setattr(db,'no_external_clients',lambda:None)
    monkeypatch.setattr(db,'protected',lambda:{k:{} for k in db.spec['protected_databases']})
    monkeypatch.setattr(m,'assert_no_science_processes',lambda:None)
    monkeypatch.setattr(m,'expected_inputs',lambda p:[('customer',tmp_path/'not_actual_data',True,2)])
    def readback(*args):
        sink=_HashSink();sink.write(''.join(original) if failure!='READBACK_HASH' else '9|alpha\n2|beta\n')
        sink.physical_scan={'fixture':True};return sink
    monkeypatch.setattr(m,'copy_physical',readback)
    plan={'schema_contract':{t:{'columns':[['id','integer'],['value','text']]} for t in ('dwdate','customer','part','supplier','lineorder')}}
    if failure is None:
        result=db.import_data(plan,tmp_path,budget);row=result['loads'][0]
        assert row['copy_from_calls']==1 and row['created_and_copied_same_transaction'] is True and row['source_eof'] is True
        assert row['source_normalized_rows']==row['rows']==2 and not any('failure' in n for n in saved)
    else:
        with pytest.raises((ValueError,RuntimeError)) as raised:db.import_data(plan,tmp_path,budget)
        if failure in ('COPY_FROM','COPY_FROM_CLOSE'):assert 'backend COPY failure' in str(raised.value)
        diag=saved['import_customer_failure.json']
        assert diag['table']==target and diag['expected_rows']==2 and diag['copy_from_calls']==1
        assert diag['source']['bytes']>0 and diag['source']['sha256'] and diag['error']
        assert diag['actual'] is None if failure!='READBACK_HASH' else diag['source']!=diag['actual']
        assert diag['source_eof'] is (failure!='EARLY_RETURN')
        if failure=='SOURCE_CLOSE':assert diag['stage']=='SOURCE_CLOSE'


@pytest.mark.parametrize('field,value',[('import_protocol','other'),('created_and_copied_same_transaction',False),('copy_from_calls',2),('copy_from_calls',True),('source_eof',False),('source_normalized_rows',1)])
def test_committed_import_protocol_cannot_be_self_resealed_as_multi_copy_or_early_eof(field,value):
    m=module();rows=load_fixture(m,True);rows[0][field]=value
    with pytest.raises(ValueError):m.validate_loads(m.contract.local_spec(),rows,True)


def _scan_receipt(kinds=('home','staging','wal','temp'),**retries):
    return dict(method='WHOLE_RESOURCE_RESCAN_ON_IN_ROOT_FILENOTFOUND_V1',max_additional_rescans=3,retries={k:retries.get(k,0) for k in kinds})


def _resource_roots(m,tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(m.contract,'ROOT',tmp_path)
    cluster=tmp_path/'cluster';home=tmp_path/'owned_home';stage=tmp_path/'owned_stage'
    for path in (cluster/'pg_wal',cluster/'base',home,stage):path.mkdir(parents=True,exist_ok=True)
    return SimpleNamespace(CLUSTER=cluster),home,stage


@pytest.mark.parametrize('kind',['home','staging','wal'])
def test_whole_resource_scan_discards_raced_walk_and_returns_only_complete_fresh_count(tmp_path,monkeypatch,kind):
    m=module();core,home,stage=_resource_roots(m,tmp_path,monkeypatch)
    root={'home':home,'staging':stage,'wal':core.CLUSTER/'pg_wal'}[kind];calls=[]
    def count(path):
        calls.append(Path(path))
        if len(calls)==1:raise FileNotFoundError(2,'raced rename/rotation',str(root/'rolling.tmp'))
        return 73
    core.tree_bytes=count;trace={}
    assert m.resource_tree_bytes(core,kind,home,stage,trace)==(73,1)
    assert calls==[root,root] and trace['retries']==1


def test_temp_resource_race_reenumerates_and_recounts_the_entire_group(tmp_path,monkeypatch):
    m=module();core,home,stage=_resource_roots(m,tmp_path,monkeypatch)
    top=core.CLUSTER/'base/pgsql_tmp';db=core.CLUSTER/'base/16384/pgsql_tmp';top.mkdir();db.mkdir(parents=True)
    calls=[]
    def count(path):
        path=Path(path);calls.append(path)
        if len(calls)==2:raise FileNotFoundError(2,'temporary segment removed',str(db/'temp.tmp'))
        return {1:11,3:101,4:202}[len(calls)]
    core.tree_bytes=count
    assert m.resource_tree_bytes(core,'temp',home,stage)==(303,1)
    assert calls==[top,db,top,db] # The first incomplete11 is never retained.


@pytest.mark.parametrize('succeed',[False,True])
def test_resource_race_has_exactly_three_extra_whole_attempts_and_never_uses_old_value(tmp_path,monkeypatch,succeed):
    m=module();core,home,stage=_resource_roots(m,tmp_path,monkeypatch);calls=[];root=core.CLUSTER/'pg_wal'
    def count(path):
        calls.append(path)
        if not succeed or len(calls)<4:raise FileNotFoundError(2,'continues to rotate',str(root/'segment'))
        return 91
    core.tree_bytes=count;trace={}
    if succeed:assert m.resource_tree_bytes(core,'wal',home,stage,trace)==(91,3)
    else:
        with pytest.raises(FileNotFoundError):m.resource_tree_bytes(core,'wal',home,stage,trace)
    assert len(calls)==4 and trace['retries']==3


@pytest.mark.parametrize('kind',['permission','oserror','no_filename','relative','outside','dot_escape','root_itself','non_temp','unknown_scope'])
def test_resource_scan_never_retries_unrelated_or_uninspectable_errors(tmp_path,monkeypatch,kind):
    m=module();core,home,stage=_resource_roots(m,tmp_path,monkeypatch);root=core.CLUSTER/'pg_wal';scope='wal';calls=[]
    if kind=='permission':error=PermissionError(13,'denied',str(root/'segment'))
    elif kind=='oserror':error=OSError(5,'I/O error',str(root/'segment'))
    elif kind=='no_filename':error=FileNotFoundError('filename absent')
    elif kind=='relative':error=FileNotFoundError(2,'not absolute','segment')
    elif kind=='outside':error=FileNotFoundError(2,'outside',str(tmp_path/'other/segment'))
    elif kind=='dot_escape':error=FileNotFoundError(2,'escaped',str(root/'../other/segment'))
    elif kind=='root_itself':error=FileNotFoundError(2,'root gone',str(root))
    elif kind=='non_temp':scope='temp';error=FileNotFoundError(2,'not temp',str(core.CLUSTER/'base/16384/12345'))
    else:scope='source_data';error=AssertionError('Unrecognized scope reached filesystem')
    def count(path):calls.append(path);raise error
    core.tree_bytes=count
    if kind=='unknown_scope':
        with pytest.raises(ValueError):m.resource_tree_bytes(core,scope,home,stage)
        assert not calls
    else:
        with pytest.raises(type(error)) as raised:m.resource_tree_bytes(core,scope,home,stage)
        assert raised.value is error and len(calls)==1


def test_resource_scan_rejects_project_escape_and_missing_required_root_without_zero(tmp_path,monkeypatch):
    m=module();core,home,stage=_resource_roots(m,tmp_path,monkeypatch);calls=[]
    core.tree_bytes=lambda p:calls.append(p) or 0
    core.CLUSTER=tmp_path.parent/'outside_project'
    with pytest.raises(ValueError):m.resource_tree_bytes(core,'wal',home,stage)
    core.CLUSTER=tmp_path/'never_created_cluster'
    with pytest.raises(FileNotFoundError):m.resource_tree_bytes(core,'wal',home,stage)
    assert not calls


@pytest.mark.parametrize('kind',['method','bound','bool_bound','bool_retry','negative','too_many','missing','extra'])
def test_resource_scan_receipt_requires_fixed_method_bound_and_exact_integer_counters(kind):
    m=module();good=_scan_receipt(wal=2);m.validate_resource_scan(good,('home','staging','wal','temp'))
    if kind=='method':good['method']='IGNORE_MISSING_FILE'
    if kind=='bound':good['max_additional_rescans']=4
    if kind=='bool_bound':good['max_additional_rescans']=True
    if kind=='bool_retry':good['retries']['wal']=True
    if kind=='negative':good['retries']['wal']=-1
    if kind=='too_many':good['retries']['wal']=4
    if kind=='missing':del good['retries']['wal']
    if kind=='extra':good['retries']['source_data']=0
    with pytest.raises(ValueError):m.validate_resource_scan(good,('home','staging','wal','temp'))


def test_budget_records_actual_baseline_and_sample_retries_and_exhaustion_without_cached_bytes(tmp_path,monkeypatch):
    m=module();frozen=m.contract.load_frozen();core,home,stage=_resource_roots(m,tmp_path,monkeypatch)
    counts={'wal':0,'home':0};mode={'sampling':False,'exhaust':False}
    def count(path):
        path=Path(path)
        if path==core.CLUSTER/'pg_wal':
            counts['wal']+=1
            if mode['exhaust'] or counts['wal'] in (1,3,4):raise FileNotFoundError(2,'rotated segment',str(path/'segment'))
            return 100 if not mode['sampling'] else 160
        if path==home:
            counts['home']+=1
            if counts['home']==1:raise FileNotFoundError(2,'atomic rename',str(path/'result.json.tmp'))
            return 12
        if path==stage:return 13
        return 0 if not mode['sampling'] else 4
    core.tree_bytes=count;core.budget_total=frozen.budget_total;core.lsn_integer=frozen.lsn_integer;core.process_rss=lambda p:100
    monkeypatch.setattr(m.contract,'load_frozen',lambda:core)
    b=m.LocalBudget(m.contract.local_spec(),home,stage);assert b.resource_scan_baseline==_scan_receipt(('wal','temp'),wal=1)
    mode['sampling']=True;sample=b.tick(force=True)
    assert sample['resource_scan']==_scan_receipt(home=1,wal=2) and sample['wal_now_bytes']==160 and sample['owned_files_bytes']==25
    assert b.report()['resource_scan_failure'] is None
    mode['exhaust']=True
    with pytest.raises(FileNotFoundError):b.tick(force=True)
    report=b.report();assert len(report['samples'])==1
    assert report['resource_scan_failure']['scope']=='wal' and report['resource_scan_failure']['scan']==_scan_receipt(('wal',),wal=3)


def test_resource_scan_permission_error_after_one_race_still_propagates_immediately(tmp_path,monkeypatch):
    m=module();core,home,stage=_resource_roots(m,tmp_path,monkeypatch);calls=[];root=core.CLUSTER/'pg_wal'
    error=PermissionError(13,'denied',str(root/'segment'))
    def count(path):
        calls.append(path)
        if len(calls)==1:raise FileNotFoundError(2,'race',str(root/'previous'))
        raise error
    core.tree_bytes=count;trace={}
    with pytest.raises(PermissionError) as raised:m.resource_tree_bytes(core,'wal',home,stage,trace)
    assert raised.value is error and len(calls)==2 and trace['retries']==1


def test_first_sample_exhaustion_report_preserves_failure_without_a_secondary_empty_peak_error(tmp_path,monkeypatch):
    m=module();frozen=m.contract.load_frozen();core,home,stage=_resource_roots(m,tmp_path,monkeypatch);mode={'fail':False}
    first=FileNotFoundError(2,'resource rotation exhausted',str(core.CLUSTER/'pg_wal/segment'))
    def count(path):
        if mode['fail'] and Path(path)==core.CLUSTER/'pg_wal':raise first
        return 1
    core.tree_bytes=count;core.budget_total=frozen.budget_total;core.process_rss=lambda p:100
    monkeypatch.setattr(m.contract,'load_frozen',lambda:core)
    budget=m.LocalBudget(m.contract.local_spec(),home,stage);mode['fail']=True
    with pytest.raises(FileNotFoundError) as raised:budget.tick(force=True)
    assert raised.value is first
    report=budget.report()
    assert report['samples']==[] and report['peak_total_bytes']==0
    assert report['resource_scan_failure']['scan']['retries']=={'wal':3} and 'rotation exhausted' in report['resource_scan_failure']['error']
