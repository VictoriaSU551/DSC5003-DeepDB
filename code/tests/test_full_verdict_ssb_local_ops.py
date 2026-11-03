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


def load_fixture(m,committed=False):
    rows=[]
    s=m.contract.local_spec();expected={'public.'+t:n for t,n in s['dimension_rows'].items()};expected[s['sample_relation']]=s['sample_rows']
    for table,count in expected.items():
        canonical=dict(bytes=count*30,rows=count,sha256='a'*64)
        proof=dict(status='PASS_SERIAL_SEQSCAN_MONOTONIC_CTID',table=table,rows=count,keep_ctid=False,
            first_ctid=[0,1],last_ctid=[count//100,1+count%100],explain=_scan_plan(table),settings=['off','0'],previous_settings=['on','2'],restored_settings=['on','2'])
        row=dict(table=table,rows=count,canonical_actual=canonical,physical_scan=proof)
        if committed:row.update(status='PASS_COMMITTED_TABLE_IMPORT',canonical_source=canonical,seconds=.5)
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
    db.connect();assert calls[0]['dbname']=='deepdb_verdict_ssb_local500_v10'
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
    m=module();s=m.contract.local_spec();base=dict(owned_files_bytes=1,owned_database_bytes=1,positive_wal_bytes=0,positive_temp_bytes=0,total_bytes=2,python_rss_bytes=1)
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
    from types import SimpleNamespace
    m=module();core=m.contract.load_frozen()
    fake=SimpleNamespace(CLUSTER=tmp_path,budget_total=core.budget_total,lsn_integer=core.lsn_integer,tree_bytes=lambda p:0,process_rss=lambda p:100)
    b=m.LocalBudget.__new__(m.LocalBudget)
    b.spec=m.contract.local_spec();b.home=tmp_path;b.stage=tmp_path;b.core=fake;b.connection=None;b.samples=[]
    b.last_database_bytes=200;b.wal_before=0;b.temp_before=0;b.wal_lsn_before='0/1';b.last_wal_lsn='0/3';b.last_lsn_observed=0.
    monkeypatch.setattr(b,'temp_bytes',lambda:0)
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


def test_v10_database_namespace_matches_java_and_preserves_fixed_resource_caps():
    m=module();s=m.contract.local_spec()
    assert s['database']=='deepdb_verdict_ssb_local500_v10'
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
        def copy_expert(self,sql,sink):
            if ' FROM STDIN ' in sql:
                assert isinstance(sink,io.StringIO);self.tables[sql.split()[1]]=sink.read().encode('utf-8');return
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
