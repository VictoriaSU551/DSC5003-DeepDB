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
        row=dict(table=table,rows=count,canonical_actual=canonical)
        if committed:row.update(status='PASS_COMMITTED_TABLE_IMPORT',canonical_source=canonical,seconds=.5)
        rows.append(row)
    return rows


@pytest.mark.parametrize('committed',[False,True])
def test_complete_five_unique_full_field_snapshots_reject_duplicate_missing_wrong_rows_and_malformed_hash(committed):
    import copy
    m=module();good=load_fixture(m,committed);m.validate_loads(m.contract.local_spec(),good,committed)
    for kind in ('duplicate','rows','canonical_rows','zero_bytes','sha','seconds'):
        if kind=='seconds' and not committed:continue
        bad=copy.deepcopy(good)
        if kind=='duplicate':bad[1]=copy.deepcopy(bad[0])
        if kind=='rows':bad[1]['rows']-=1
        if kind=='canonical_rows':bad[-1]['canonical_actual']['rows']-=1
        if kind=='zero_bytes':bad[0]['canonical_actual']['bytes']=0
        if kind=='sha':bad[0]['canonical_actual']['sha256']='fake'
        if kind=='seconds':bad[0]['seconds']=float('inf')
        with pytest.raises(ValueError):m.validate_loads(m.contract.local_spec(),bad,committed)


def test_connection_uses_local_database_and_never_changes_frozen_sf2_globals(monkeypatch):
    m=module();db=m.LocalDatabase();calls=[]
    class Driver:
        @staticmethod
        def connect(**kw):calls.append(kw);return type('Connection',(),{})()
    monkeypatch.setitem(sys.modules,'psycopg2',Driver)
    db.connect();assert calls[0]['dbname']=='deepdb_verdict_ssb_local500'
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
