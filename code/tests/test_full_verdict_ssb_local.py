"""Pure LOCAL contracts; no parent F, data scan or scientific operations."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    p=ROOT/'code/full_verdict_ssb_local.py'
    assert p.exists(),'LOCAL Verdict source/oracle module missing'
    s=importlib.util.spec_from_file_location('local_verdict_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_explicit_local_spec_has_no_sf2_population_or_database_alias():
    m=module();s=m.local_spec()
    assert s['database']=='deepdb_verdict_ssb_local500' and s['population_rows']==3000028242 and s['sample_rows']==9996946
    assert s['protected_databases']==['deepdb_job','deepdb_verdict','deepdb_verdict_ssb']
    assert s['sampling_ratio']=={'numerator':9996946,'denominator':3000028242}
    old=m.load_frozen();assert old.DB=='deepdb_verdict_ssb' and old.LIMITS['total_new_bytes']==1024**3


def micro(queries):
    return {'status':'PASS','sample_rows':3,'queries':[{'sql':q['sql'],'kind':'DIFF' if q['query_no']>=10 else 'SUM','groups':[]} for q in queries]}


def test_moment_oracle_exact_integer_rational_and_scalar_null():
    m=module();queries=m.raw_queries();moment=micro(queries)
    moment['queries'][0]['groups']=[dict(key=[],count=2,filter_count=2,sum_integer=7,square_sum_integer=25,scale=1,component_non_null_counts=[])]
    rows=m.moments_oracle(moment,10,3,queries)
    assert rows[0]['groups'][0]['expected']=={'numerator':70,'denominator':3}
    assert rows[1]['groups'][0]['sample_sum'] is None
    assert rows[3]['groups']==[]
    assert rows[10]['component_oracle_status']=='UNAVAILABLE_ONLY_PROFIT_SUM_STORED'


def test_moment_oracle_refuses_sql_shift_fractional_sum_duplicate_and_null_unsafe_difference():
    m=module();queries=m.raw_queries();good=micro(queries)
    for change in ('sql','float','duplicate','diff_null','scale','key_string'):
        value=copy.deepcopy(good)
        row=dict(key=['1997','X'],count=2,filter_count=2,sum_integer=7,square_sum_integer=25,scale=1,component_non_null_counts=[2,2])
        if change=='sql':value['queries'][0]['sql']='SELECT 1'
        if change=='float':value['queries'][0]['groups']=[dict(row,key=[],sum_integer=7.)]
        if change=='duplicate':value['queries'][10]['groups']=[row,row]
        if change=='diff_null':value['queries'][10]['groups']=[dict(row,component_non_null_counts=[1,2])]
        if change=='scale':value['queries'][0]['groups']=[dict(row,key=[],scale=2)]
        if change=='key_string':value['queries'][10]['groups']=[dict(row,key='AB')]
        with pytest.raises(ValueError):m.moments_oracle(value,10,3,queries)


def test_missing_parent_fails_before_importing_any_model_or_reading_growing_moments(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('Imported scientific parent before complete final publication')
    monkeypatch.setattr(m.importlib,'import_module',forbidden)
    with pytest.raises(ValueError,match='final parent'):m.collect_lineage({})


def test_unreviewed_or_partial_measurement_cannot_enable_formal_plan():
    m=module()
    with pytest.raises(ValueError):m.validate_measurement({})
    with pytest.raises(ValueError):m.validate_measurement({'status':'PASS','database':'deepdb_verdict_ssb','relations':[]})


@pytest.mark.parametrize('name,size,sha',[
    ('kernel32.dll',861992,'e132eba4166256e2f414b91fe7d5386590bc5ea8626aee5af9c9738383cf2ae1'),
    ('msvcrt.dll',716104,'fc1447db4e4814cbcb002179a8003a41f383fc417879f628727043cab8c25093')])
def test_exact_direct_windows_import_descriptor_retains_scope_without_opening_system_file(name,size,sha,tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path)
    path=Path('C:/Windows/System32')/name
    descriptor=dict(path=str(path.resolve()),bytes=size,sha256=sha,external_scope='windows_direct_native_import')
    monkeypatch.setattr(Path,'is_file',lambda p:True)
    monkeypatch.setattr(Path,'stat',lambda p,**kwargs:SimpleNamespace(st_size=size))
    monkeypatch.setattr(m,'digest',lambda p:sha)
    assert m.artifact(path)==descriptor
    assert m.verify_parent_descriptor(descriptor)==descriptor
    for bad in (dict(descriptor,external_scope='other'),{k:v for k,v in descriptor.items() if k!='external_scope'},dict(descriptor,sha256='0'*64)):
        with pytest.raises(ValueError):m.verify_parent_descriptor(bad)
    with pytest.raises(ValueError):m.artifact(Path('C:/Windows/System32/user32.dll'))


def test_all_final_publications_must_exist_before_any_parent_is_hashed(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'ROOT',tmp_path);s=m.local_spec();parents={}
    for role in ('source','model','canonical','reverse'):
        path=s.get(role+'_report','output/full/ssb/local_sf500_continuation/runs/tiny/reverse/verification.json');parents[role]=dict(path=path,bytes=0,sha256='0'*64)
        if role!='reverse':
            p=tmp_path/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    def forbidden(*args,**kwargs):raise AssertionError('Hashed parent before all final publications existed')
    monkeypatch.setattr(m,'artifact',forbidden)
    with pytest.raises(ValueError,match='publication missing'):m.collect_lineage(parents)


@pytest.mark.parametrize('text',['{"rows":1,"rows":2}','{"value":NaN}','{"value":Infinity}'])
def test_json_duplicate_keys_and_nonfinite_numbers_are_rejected(text,tmp_path):
    m=module();p=tmp_path/'receipt.json';p.write_text(text,encoding='utf-8')
    with pytest.raises(ValueError):m.read(p)


def test_one_entry_collects_fresh_lineage_once_and_reuses_private_proof_for_pilot(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=module();core=m.load_frozen();calls=[];seen=[];expected={'complete_fixture':True}
    monkeypatch.setattr(m,'collect_lineage',lambda e:calls.append(e) or {'fixture':'full-proof'})
    monkeypatch.setattr(m,'dependency_snapshot',lambda:{'source_files':{},'runtime':{}})
    monkeypatch.setattr(m,'call_plan',lambda:[])
    fake_runner=SimpleNamespace(_verify_pilot_from_boundary=lambda path,b:seen.append(b) or {'measurement':{},'parent_expected':expected})
    monkeypatch.setattr(m.importlib,'import_module',lambda n:fake_runner)
    monkeypatch.setattr(m,'validate_measurement',lambda v:v)
    p=tmp_path/'final.json';p.write_text('{}');measurement={'path':'fixture','bytes':2,'sha256':'a'*64}
    monkeypatch.setattr(m,'artifact',lambda p:measurement)
    review=dict(status='APPROVED_LOCAL_VERDICT_RESOURCE_PLAN',measurement_sha256='a'*64,limits=m.local_spec()['limits'],projected_owned_database_bytes=1,projected_total_new_bytes=2)
    plan=m.build_plan(expected,measurement,review)
    assert calls==[expected] and len(seen)==1 and isinstance(seen[0],m._PlanningBoundary)
    assert plan['lineage']=={'fixture':'full-proof'} and plan['measurement_verification']['parent_expected']==expected
    # A second public entry must collect again; there is no cross-entry cache.
    m.build_plan(expected,measurement,review);assert calls==[expected,expected]


def test_supplied_model_cannot_repin_a_changed_delegate_before_scientific_import(tmp_path,monkeypatch):
    import json
    m=module();s=m.local_spec();monkeypatch.setattr(m,'ROOT',tmp_path)
    local={
        'code/full_ssb_local_source.py':'699f85ec4d24c326a7b491cd4cbf9c5746a98e7947d5b79db60200d08c0e3ca3',
        'code/full_ssb_local_model.py':'0b736cb30e7f1e93c66d2ac632c9b8a0ac0023595440c46b8d9215962184bced',
        'code/full_ssb_local_model_run.py':'fd676fb41780ae96074a08f2478a7cef9820b7c55a65717b9b8e28ea9545dee3'}
    flags=dict(author_reproduction_complete=False,full_paper_reproduction_complete=False)
    values=dict(source=dict(flags,status='PASS_LOCAL_SOURCE_PHYSICAL_GATE_ONLY',source_id=s['source_id'],different_author_groups=1713,local_sources=local),
        model=dict(flags,scope='LOCAL_SSB_SF500',status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI',author_different_groups=1713,
            plan={'dependencies':{'auxiliary_sources':{'code/full_ssb_local_replay.py':'b'*64}}}),
        canonical=dict(flags,status='PASS_LOCAL_SSB_SF500_CANONICAL_AQP_CI',author_different_groups=1713),
        reverse=dict(flags,status='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',author_different_groups=1713))
    expected={}
    for role,body in values.items():
        name=s.get(role+'_report','output/full/ssb/local_sf500_continuation/runs/tiny/reverse/verification.json');p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(body),encoding='utf-8')
        expected[role]=dict(path=name,bytes=p.stat().st_size,sha256=s['source_report_sha256'] if role=='source' else 'a'*64)
    monkeypatch.setattr(m,'artifact',lambda p:next(r for r in expected.values() if tmp_path/r['path']==Path(p)))
    monkeypatch.setattr(m,'digest',lambda p:local.get(Path(p).relative_to(tmp_path).as_posix(),'b'*64))
    def forbidden(*args,**kwargs):raise AssertionError('Re-pinned untrusted delegate reached import')
    monkeypatch.setattr(m.importlib,'import_module',forbidden)
    with pytest.raises(ValueError,match='delegate|Delegate'):m.collect_lineage(expected)


@pytest.mark.parametrize('changed',[
    'full_ssb_local_source.py','full_ssb_local_model.py','full_ssb_local_model_run.py','full_ssb_local_replay.py',
    'full_ssb_replay.py','full_ssb_native_replay.py','full_ssb_native_model.py','full_ssb_native_model_run.py',
    'full_ssb_model.py','full_ssb_guard.py','full_ssb_native_v2.py','full_ssb_native_v2_stream.py','full_ssb_native_v2_formal.py',
    'full_ssb_local_canonical.py','full_ssb_local_canonical_run.py','full_ssb_group_order.py',
    'full_ssb_local_continuation.py','full_ssb_local_continuation_run.py'])
def test_every_delegated_entry_provider_and_strict_upper_source_has_independent_fixed_pin(changed,monkeypatch):
    m=module();assert len(m.PARENT_PINS)==18
    monkeypatch.setattr(m,'digest',lambda p:m.PARENT_PINS[Path(p).relative_to(m.ROOT).as_posix()])
    assert m.verify_delegate_sources()==m.PARENT_PINS
    def changed_digest(path):
        name=Path(path).relative_to(m.ROOT).as_posix()
        return '0'*64 if name=='code/'+changed else m.PARENT_PINS[name]
    monkeypatch.setattr(m,'digest',changed_digest)
    with pytest.raises(ValueError,match='before import'):m.verify_delegate_sources()


def canonical_fixture(tmp_path,monkeypatch):
    """Tiny complete saved parent aliases; delegated verifier is counted, never run."""
    from contextlib import nullcontext
    from types import SimpleNamespace
    import json
    m=module();native_queries=m.raw_queries();monkeypatch.setattr(m,'ROOT',tmp_path);s=m.local_spec();flags=dict(author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False)
    def save(path,body):
        p=tmp_path/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(body),encoding='utf-8');return m.artifact(p)
    run=tmp_path/'output/full/ssb/local_sf500_models/runs/tiny'
    model=dict(flags,status='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI',scope='LOCAL_SSB_SF500',directory=str(run),
        training_tables=[dict(table='lineorder',actual_training_rows=9996946)],
        plan={'dependencies':{'auxiliary_sources':{'code/full_ssb_local_replay.py':m.PARENT_PINS['code/full_ssb_local_replay.py']}}})
    source=dict(flags,status='PASS_LOCAL_SOURCE_PHYSICAL_GATE_ONLY',source_id=s['source_id'],different_author_groups=1713,
        local_sources={k:m.PARENT_PINS[k] for k in ('code/full_ssb_local_source.py','code/full_ssb_local_model.py','code/full_ssb_local_model_run.py')})
    cdir='output/full/ssb/local_sf500_continuation/runs/tiny'
    protocol='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
    reverse=dict(flags,status='PASS_CONTINUATION_REVERSE_EVALUATION',scope='LOCAL_SSB_SF500_CANONICAL_CONTINUATION',execution_protocol=protocol,phase='REVERSE',directory=str(tmp_path/cdir),
        group_order_adapter_sha256='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c')
    expected=dict(source=save(s['source_report'],source),model=save(s['model_report'],model),reverse=save(cdir+'/reverse/verification.json',reverse))
    original_asset=save('output/tmp/parent_asset.json',{'old':'all science and supervisor assets'})
    canonical_asset=save('output/tmp/canonical_asset.json',{'new':'both phases and root control'})
    canonical=dict(flags,status='PASS_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_AQP_CI',scope='LOCAL_SSB_SF500_CANONICAL_CONTINUATION',execution_protocol=protocol,directory=str(tmp_path/cdir),adopted_forward=True,forward_reexecuted=False,
        variant='CANONICAL_PAIRED_DECODED_GROUP_ORDER',evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',
        group_order_adapter_sha256=reverse['group_order_adapter_sha256'],historical_reverse_accepted=False,parent_formal=expected['model'],reverse=expected['reverse'])
    expected['canonical']=save(s.get('canonical_report','output/full/results/ssb_local_sf500_canonical_aqp_ci.json'),canonical)
    s.update(source_report_sha256=expected['source']['sha256'],model_report_sha256=expected['model']['sha256'])
    monkeypatch.setattr(m,'local_spec',lambda:s)
    parent=dict(flags,status='PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH',scope='LOCAL_SSB_SF500',report=model,published_result=expected['model'],artifacts=[original_asset])
    proof=dict(canonical,status='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH',report=canonical,parent_snapshot=parent,
        published_result=expected['canonical'],sample_rows=s['sample_rows'],population_rows=s['population_rows'],artifacts=[canonical_asset],
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False)
    moment=micro(native_queries);moment['sample_rows']=s['sample_rows']
    save(str((run/'sample_moments_native/moments.json').relative_to(tmp_path)),moment)
    raw=run/'sample_moments_native/moments.tsv';raw.write_text('tiny integer moments\n')
    save(str(raw.with_name('seal.json').relative_to(tmp_path)),dict(sha256=m.digest(raw.with_name('moments.json')),tsv_sha256=m.digest(raw)))
    save(str(raw.with_name('process.json').relative_to(tmp_path)),dict(returncode=0))
    calls=[]
    monkeypatch.setattr(m,'verify_delegate_sources',lambda:m.PARENT_PINS)
    realdigest=m.digest
    monkeypatch.setattr(m,'digest',lambda p:m.FROZEN['code/full_windows_fingerprint.py'] if Path(p)==tmp_path/'code/full_windows_fingerprint.py' else realdigest(p))
    monkeypatch.setattr(m,'raw_queries',lambda:native_queries)
    monkeypatch.setattr(m,'load_frozen',lambda:SimpleNamespace())
    def importer(name):
        if name=='full_windows_fingerprint':return SimpleNamespace(verified_platform=lambda *a:nullcontext())
        if name=='full_verdict_ssb_audit':return SimpleNamespace(forbid_science=lambda *a:nullcontext())
        if name=='full_ssb_local_continuation':return SimpleNamespace(__file__=str(tmp_path/'code/full_ssb_local_continuation.py'),verify_canonical=lambda:calls.append('CANONICAL') or proof)
        pytest.fail('No failed 9c verifier or other scientific import allowed: '+name)
    monkeypatch.setattr(m.importlib,'import_module',importer)
    return m,s,expected,proof,calls,original_asset,canonical_asset


def test_canonical_parent_once_inherits_full_original_and_new_artifacts_without_failed_replay(tmp_path,monkeypatch):
    m,s,expected,proof,calls,old,new=canonical_fixture(tmp_path,monkeypatch)
    lineage=m.collect_lineage(expected)
    assert calls==['CANONICAL']
    assert lineage['parent_canonical']==expected['canonical'] and lineage['parent_reverse']==expected['reverse'] and lineage['parent_formal']==expected['model']
    assert lineage['evaluation_variant']=='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
    assert lineage['group_order_adapter_sha256']==m.PARENT_PINS['code/full_ssb_group_order.py']
    assert lineage['files'][old['path']]==old and lineage['files'][new['path']]==new
    assert lineage['historical_reverse_accepted'] is False and lineage['author_different_groups']==1713
    assert lineage['author_reproduction_complete'] is lineage['full_paper_reproduction_complete'] is False
    assert lineage['canonical_execution_protocol']=='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
    assert lineage['adopted_forward'] is True and lineage['forward_reexecuted'] is False


@pytest.mark.parametrize('bad',['status','scope','variant','adapter','n','N','parent_formal','parent_report','canonical_report','reverse','author','complete','historical',
    'no_original_artifacts','no_canonical_artifacts','database_connected','training_executed','inference_executed','files_modified',
    'protocol','adopted_forward','forward_reexecuted'])
def test_canonical_parent_bad_proof_or_alias_is_refused_even_with_saved_publications(tmp_path,monkeypatch,bad):
    m,s,expected,p,calls,old,new=canonical_fixture(tmp_path,monkeypatch)
    if bad=='status':p['status']='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH'
    if bad=='scope':p['scope']='LOCAL_SSB_SF500'
    if bad=='variant':p['evaluation_variant']='ORIGINAL_HASH_DEPENDENT_PROTOTYPE'
    if bad=='adapter':p['group_order_adapter_sha256']='a'*64
    if bad=='n':p['sample_rows']-=1
    if bad=='N':p['population_rows']-=1
    if bad=='parent_formal':p['parent_formal']=dict(expected['model'],sha256='a'*64)
    if bad=='parent_report':p['parent_snapshot']['report']=dict(p['parent_snapshot']['report'],directory='other')
    if bad=='canonical_report':p['report']=dict(p['report'],status='other')
    if bad=='reverse':p['reverse']=dict(expected['reverse'],sha256='a'*64)
    if bad=='author':p['author_different_groups']=0
    if bad=='complete':p['full_paper_reproduction_complete']=True
    if bad=='historical':p['historical_reverse_accepted']=True
    if bad=='protocol':p['execution_protocol']='ORIGINAL_TWO_FRESH_PHASES'
    if bad=='adopted_forward':p['report']=dict(p['report'],adopted_forward=False)
    if bad=='forward_reexecuted':p['report']=dict(p['report'],forward_reexecuted=True)
    if bad=='no_original_artifacts':p['parent_snapshot']['artifacts']=[]
    if bad=='no_canonical_artifacts':p['artifacts']=[]
    if bad in ('database_connected','training_executed','inference_executed','files_modified'):p[bad]=True
    with pytest.raises(ValueError):m.collect_lineage(expected)


def test_shadow_loaded_canonical_module_is_rejected_before_its_verifier(tmp_path,monkeypatch):
    m,s,expected,p,calls,old,new=canonical_fixture(tmp_path,monkeypatch);original=m.importlib.import_module
    def shadow(name):
        value=original(name)
        if name=='full_ssb_local_continuation':value.__file__=str(tmp_path/'elsewhere/canonical.py')
        return value
    monkeypatch.setattr(m.importlib,'import_module',shadow)
    with pytest.raises(ValueError,match='loaded|Loaded'):m.collect_lineage(expected)
    assert calls==[]


def test_sqlite_definition_import_in_pinned_native_provider_preserves_one_lineage_call(tmp_path,monkeypatch):
    """Reproduce v6's exact import boundary without running a parent verifier."""
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m,s,expected,p,calls,old,new=canonical_fixture(tmp_path,monkeypatch)
    original=m.importlib.import_module
    imported=[]
    def importer(name):
        if name=='full_verdict_ssb_audit':return audit
        provider=original(name)
        if name=='full_ssb_local_continuation':
            def definitions_only():
                spec=importlib.util.spec_from_file_location('verdict_local_native_definition_probe',str(ROOT/'code/full_ssb_native_v2.py'))
                native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
                assert native.sqlite3.sqlite_version
                imported.append('native definitions only')
                return provider.verify_canonical()
            return SimpleNamespace(__file__=provider.__file__,verify_canonical=definitions_only)
        return provider
    monkeypatch.setattr(m.importlib,'import_module',importer)
    lineage=m.collect_lineage(expected)
    assert imported==['native definitions only'] and calls==['CANONICAL']
    assert lineage['files'][old['path']]==old and lineage['files'][new['path']]==new


@pytest.mark.parametrize('statement',[
    'import sqlite3; sqlite3.connect(":memory:")',
    'import sqlite3; sqlite3.Connection(":memory:")',
    'import sqlite3; sqlite3.Cursor(None)',
    'import sqlite3.dbapi2 as db; db.connect(":memory:")',
    'import sqlite3.dbapi2 as db; db.Connection(":memory:")',
    'import sqlite3.dbapi2 as db; db.Cursor(None)',
    'import _sqlite3 as native; native.connect(":memory:")',
    'import _sqlite3 as native; native.Connection(":memory:")',
    'import _sqlite3 as native; native.Cursor(None)',
    'from sqlite3 import connect as alias; alias(":memory:")',
    'from sqlite3.dbapi2 import Connection as alias; alias(":memory:")',
    'from _sqlite3 import connect as alias; alias(":memory:")',
    'from _sqlite3 import Connection as alias; alias(":memory:")'])
def test_parent_operations_forbid_sqlite_calls_and_imported_aliases_without_opening_a_DB(monkeypatch,statement):
    import sqlite3,sqlite3.dbapi2,_sqlite3
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();attempts=[]
    def tripwire(*a,**k):attempts.append('bypass');raise AssertionError('real connection API must never be reached')
    for native in (sqlite3,sqlite3.dbapi2,_sqlite3):
        for name in ('connect','Connection','Cursor'):monkeypatch.setattr(native,name,tripwire)
    with m.forbid_parent_operations(audit,SimpleNamespace()):
        with pytest.raises(RuntimeError,match='SQLite'):exec(statement,{})
    assert attempts==[]


@pytest.mark.parametrize('raises',[False,True])
def test_parent_operations_delegate_all_frozen_blocks_and_restore_hooks_on_exception(monkeypatch,raises):
    import builtins,os,sqlite3,sqlite3.dbapi2,_sqlite3,subprocess
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();attempts=[]
    def tripwire(*a,**k):attempts.append('bypass');raise AssertionError('operational API must never be reached')
    names=('connect','pg_control','start_owned_server','bounded_process','run_sf2','run_oracle','import_postgres','execute_original','adopt_oracle','adopt_registered_files')
    core=SimpleNamespace(**{name:tripwire for name in names})
    for name in ('run','Popen','call','check_call','check_output'):monkeypatch.setattr(subprocess,name,tripwire)
    for name in ('system','startfile','popen'):
        if hasattr(os,name):monkeypatch.setattr(os,name,tripwire)
    importer=builtins.__import__;module_importer=m.importlib.import_module
    saved=[(native,name,getattr(native,name)) for native in (sqlite3,sqlite3.dbapi2,_sqlite3) for name in ('connect','Connection','Cursor')]
    class BodyFailure(Exception):pass
    try:
        with m.forbid_parent_operations(audit,core):
            for name in names:
                with pytest.raises(RuntimeError,match='Forbidden operational'):getattr(core,name)()
            for name in ('run','Popen','call','check_call','check_output'):
                with pytest.raises(RuntimeError,match='Forbidden operational'):getattr(subprocess,name)(['forbidden'])
            for name in ('system','startfile','popen'):
                if hasattr(os,name):
                    with pytest.raises(RuntimeError,match='Forbidden operational'):getattr(os,name)('forbidden')
            for pg in ('psycopg2','psycopg2.extensions'):
                with pytest.raises(RuntimeError):builtins.__import__(pg)
                with pytest.raises(RuntimeError):m.importlib.import_module(pg)
            with pytest.raises(RuntimeError):m.importlib.import_module('.extensions','psycopg2')
            with pytest.raises(RuntimeError):builtins.__import__('sqlite3.dump')
            with pytest.raises(RuntimeError):m.importlib.import_module('sqlite3.dump')
            assert m.importlib.import_module('sqlite3') is sqlite3
            assert m.importlib.import_module('sqlite3.dbapi2') is sqlite3.dbapi2
            assert m.importlib.import_module('_sqlite3') is _sqlite3
            if raises:raise BodyFailure('restore after delegated verifier failure')
    except BodyFailure:
        assert raises
    assert builtins.__import__ is importer and m.importlib.import_module is module_importer
    assert all(getattr(obj,name) is value for obj,name,value in saved)
    assert all(getattr(core,name) is tripwire for name in names)
    assert subprocess.Popen is tripwire and os.system is tripwire and attempts==[]


def test_parent_operations_enter_frozen_guard_before_wrapper_definitions(monkeypatch):
    from contextlib import contextmanager
    import sqlite3,sqlite3.dbapi2,_sqlite3
    from types import SimpleNamespace
    m=module();events=[];loader=m.importlib.__import__
    @contextmanager
    def frozen_guard(core):
        events.append('enter unchanged delegated guard');yield;events.append('leave unchanged delegated guard')
    def definitions(*args,**kwargs):
        assert events==['enter unchanged delegated guard']
        with pytest.raises(RuntimeError,match='SQLite'):_sqlite3.Connection(':memory:')
        return loader(*args,**kwargs)
    monkeypatch.setattr(m.importlib,'__import__',definitions)
    with m.forbid_parent_operations(SimpleNamespace(forbid_science=frozen_guard),SimpleNamespace()):
        events.append('provider may import definitions')
    assert events==['enter unchanged delegated guard','provider may import definitions','leave unchanged delegated guard']


def test_parent_operations_support_cold_sqlite_definitions_inside_existing_frozen_guard(monkeypatch):
    import builtins,sys,sqlite3,sqlite3.dbapi2,_sqlite3
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();attempts=[]
    def tripwire(*a,**k):attempts.append('bypass');raise AssertionError('no actual database connection')
    for name in ('connect','Connection','Cursor'):monkeypatch.setattr(_sqlite3,name,tripwire)
    monkeypatch.delitem(sys.modules,'sqlite3.dbapi2');monkeypatch.delitem(sys.modules,'sqlite3')
    before=builtins.__import__;module_importer=m.importlib.import_module
    with audit.forbid_science(SimpleNamespace()):
        outer=builtins.__import__
        with m.forbid_parent_operations(audit,SimpleNamespace()):
            import sqlite3 as definitions
            assert definitions.sqlite_version
            with pytest.raises(RuntimeError,match='SQLite'):definitions.connect(':memory:')
            with pytest.raises(RuntimeError):__import__('psycopg2')
        assert builtins.__import__ is outer
        with pytest.raises(RuntimeError):__import__('sqlite3')
    assert builtins.__import__ is before and m.importlib.import_module is module_importer
    assert _sqlite3.connect is tripwire and attempts==[]


@pytest.mark.parametrize('raises',[False,True])
def test_fresh_sqlite_definitions_restore_actual_original_API_identities_without_DB_calls(monkeypatch,raises):
    import builtins,sys,sqlite3,sqlite3.dbapi2,_sqlite3
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();names=('connect','Connection','Cursor')
    original={name:getattr(_sqlite3,name) for name in names}
    monkeypatch.delitem(sys.modules,'sqlite3.dbapi2');monkeypatch.delitem(sys.modules,'sqlite3')
    before=builtins.__import__;module_importer=m.importlib.import_module
    class ExitFailure(Exception):pass
    with audit.forbid_science(SimpleNamespace()):
        outer=builtins.__import__
        try:
            with m.forbid_parent_operations(audit,SimpleNamespace()):
                fresh=[sys.modules[n] for n in ('sqlite3','sqlite3.dbapi2','_sqlite3')]
                assert all(getattr(obj,name) is not original[name] for obj in fresh for name in names)
                if raises:raise ExitFailure('cold initialization followed by verifier exception')
        except ExitFailure:assert raises
        assert all(getattr(obj,name) is original[name] for obj in fresh for name in names)
        assert builtins.__import__ is outer and m.importlib.import_module is module_importer
        with pytest.raises(RuntimeError):__import__('sqlite3')
    assert builtins.__import__ is before


def test_nested_parent_operations_keep_all_frozen_bans_after_inner_exception(monkeypatch):
    import builtins,os,sqlite3,sqlite3.dbapi2,_sqlite3,subprocess
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();attempts=[]
    def tripwire(*a,**k):attempts.append('bypass');raise AssertionError('no actual operations')
    names=('connect','pg_control','start_owned_server','bounded_process','run_sf2','run_oracle','import_postgres','execute_original','adopt_oracle','adopt_registered_files')
    core=SimpleNamespace(**{name:tripwire for name in names})
    for name in ('run','Popen','call','check_call','check_output'):monkeypatch.setattr(subprocess,name,tripwire)
    for name in ('system','startfile','popen'):
        if hasattr(os,name):monkeypatch.setattr(os,name,tripwire)
    def assert_bans():
        for name in names:
            with pytest.raises(RuntimeError):getattr(core,name)()
        for name in ('run','Popen','call','check_call','check_output'):
            with pytest.raises(RuntimeError):getattr(subprocess,name)(['forbidden'])
        for name in ('system','startfile','popen'):
            if hasattr(os,name):
                with pytest.raises(RuntimeError):getattr(os,name)('forbidden')
        with pytest.raises(RuntimeError):__import__('psycopg2')
        with pytest.raises(RuntimeError):m.importlib.import_module('psycopg2')
        for obj in (sqlite3,sqlite3.dbapi2,_sqlite3):
            # Identity check is enough here; the tripwire API tests cover calls.
            assert obj.connect is sqlite3.connect and obj.Connection is sqlite3.Connection
    before=builtins.__import__;module_importer=m.importlib.import_module
    native={name:getattr(_sqlite3,name) for name in ('connect','Connection','Cursor')}
    with m.forbid_parent_operations(audit,core):
        outer=builtins.__import__;outer_module=m.importlib.import_module;outer_connect=sqlite3.connect
        assert_bans()
        with pytest.raises(ValueError,match='inner verifier failed'):
            with m.forbid_parent_operations(audit,core):assert_bans();raise ValueError('inner verifier failed')
        assert sqlite3.connect is outer_connect and builtins.__import__ is outer and m.importlib.import_module is outer_module
        assert_bans()
    assert builtins.__import__ is before and m.importlib.import_module is module_importer
    assert all(getattr(_sqlite3,name) is value for name,value in native.items())
    assert all(getattr(core,name) is tripwire for name in names) and attempts==[]


def test_parent_operations_restore_partially_initialized_wrapper_apis_on_entry_failure(monkeypatch):
    import builtins,sys,sqlite3,sqlite3.dbapi2,_sqlite3
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();names=('connect','Connection','Cursor');original={n:getattr(_sqlite3,n) for n in names}
    monkeypatch.delitem(sys.modules,'sqlite3.dbapi2');monkeypatch.delitem(sys.modules,'sqlite3')
    loader=m.importlib.__import__;before=builtins.__import__;module_importer=m.importlib.import_module
    class InitializationFailure(Exception):pass
    def broken_loader(*a,**k):
        result=loader(*a,**k)
        raise InitializationFailure('stdlib definitions loaded but context entry failed')
    monkeypatch.setattr(m.importlib,'__import__',broken_loader)
    with pytest.raises(InitializationFailure):
        with m.forbid_parent_operations(audit,SimpleNamespace()):pytest.fail('provider cannot be called')
    wrappers=[sys.modules[n] for n in ('sqlite3','sqlite3.dbapi2') if n in sys.modules]
    assert wrappers  # At least one completed child remains after its parent import failed.
    assert all(getattr(obj,name) is original[name] for obj in wrappers+[_sqlite3] for name in names)
    assert builtins.__import__ is before and m.importlib.import_module is module_importer


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='actual sealed Windows stdlib definition only')
def test_frozen_guard_reproduces_cold_windows_Popen_class_definition_failure():
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    import sys
    path=Path(sys.base_prefix)/'Lib/asyncio/windows_utils.py'
    spec=importlib.util.spec_from_file_location('verdict_v8_cold_windows_definition',str(path))
    definition=importlib.util.module_from_spec(spec)
    with audit.forbid_science(SimpleNamespace()):
        with pytest.raises(TypeError,match='function|code'):spec.loader.exec_module(definition)


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='actual Windows module; no synthetic cross-platform PASS')
def test_load_frozen_prepares_only_stdlib_definition_before_real_outer_guard(tmp_path,monkeypatch):
    import asyncio,sys,subprocess
    import full_verdict_ssb_audit as audit
    m=module();old=asyncio.windows_utils
    monkeypatch.setattr(asyncio,'windows_utils',old)
    monkeypatch.delitem(sys.modules,'asyncio.windows_utils',raising=False)
    core=m.load_frozen()  # The real runner calls this before entering its guard.
    assert 'asyncio.windows_utils' in sys.modules
    definitions=sys.modules['asyncio.windows_utils'];assert definitions is not old
    assert Path(definitions.__file__).resolve()==(Path(sys.base_prefix)/'Lib/asyncio/windows_utils.py').resolve()
    def tripwire(*a,**k):raise AssertionError('no native process constructor may run')
    monkeypatch.setattr(definitions.Popen,'__init__',tripwire)
    monkeypatch.setattr(subprocess,'Popen',tripwire)
    with audit.forbid_science(core):
        assert m.load_frozen()  # Cached definition loading works inside the outer guard.
        with m.forbid_parent_operations(audit,core):
            import asyncio.windows_utils as loaded
            assert loaded is definitions
            with pytest.raises(RuntimeError,match='process'):loaded.Popen(['forbidden'])
            with pytest.raises(RuntimeError):subprocess.Popen(['forbidden'])
            with pytest.raises(RuntimeError):__import__('psycopg2')
    assert definitions.Popen.__init__ is tripwire and subprocess.Popen is tripwire


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='actual Windows cached subclass constructor')
@pytest.mark.parametrize('raises',[False,True])
def test_parent_operations_block_cached_windows_Popen_alias_and_restore_nested_identity(monkeypatch,raises):
    import sys,subprocess
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();m.load_frozen();cls=sys.modules['asyncio.windows_utils'].Popen
    def tripwire(*a,**k):raise AssertionError('no native Popen constructor')
    monkeypatch.setattr(cls,'__init__',tripwire);monkeypatch.setattr(subprocess,'Popen',tripwire)
    class Failure(Exception):pass
    with m.forbid_parent_operations(audit,SimpleNamespace()):
        outer=cls.__init__
        with pytest.raises(RuntimeError,match='process'):cls(['forbidden'])
        try:
            with m.forbid_parent_operations(audit,SimpleNamespace()):
                with pytest.raises(RuntimeError,match='process'):cls(['forbidden'])
                with pytest.raises(RuntimeError):subprocess.Popen(['forbidden'])
                if raises:raise Failure('nested callback failed')
        except Failure:assert raises
        assert cls.__init__ is outer
        with pytest.raises(RuntimeError,match='process'):cls(['forbidden'])
    assert cls.__init__ is tripwire and subprocess.Popen is tripwire


def test_import_and_describe_do_not_prepare_stdlib_or_run_parent(monkeypatch,capsys):
    m=module()
    monkeypatch.setattr(m,'load_frozen',lambda:pytest.fail('describe must remain inert'))
    monkeypatch.setattr(m,'collect_lineage',lambda *a:pytest.fail('describe cannot verify parent'))
    spec=importlib.util.spec_from_file_location('local_verdict_v8_describe_probe',str(ROOT/'code/full_verdict_ssb_local_run.py'))
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner);runner.contract=m
    runner.main(['describe'])
    import json
    assert json.loads(capsys.readouterr().out)['status']=='CANDIDATE_CODE_ONLY'


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='actual Windows stdlib pin')
def test_changed_windows_stdlib_source_is_rejected_before_definition_import(monkeypatch):
    import sys
    m=module();path=(Path(sys.base_prefix)/'Lib/asyncio/windows_utils.py').resolve();original=m.digest
    monkeypatch.setattr(m,'digest',lambda p:'0'*64 if Path(p).resolve()==path else original(p))
    monkeypatch.setattr(m.importlib,'import_module',lambda *a:pytest.fail('changed source must fail before import'))
    with pytest.raises(ValueError,match='definition source'):m.load_frozen()


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='cold Windows definition must not bypass process guard')
def test_cold_windows_definition_inside_existing_guard_fails_closed_without_live_Popen_swap(monkeypatch):
    import sys,asyncio,subprocess
    import full_verdict_ssb_audit as audit
    from types import SimpleNamespace
    m=module();monkeypatch.setattr(asyncio,'windows_utils',asyncio.windows_utils)
    monkeypatch.delitem(sys.modules,'asyncio.windows_utils',raising=False)
    with audit.forbid_science(SimpleNamespace()):
        forbidden=subprocess.Popen
        with pytest.raises(ValueError,match='prepared before'):m.preload_readonly_definitions()
        assert subprocess.Popen is forbidden and 'asyncio.windows_utils' not in sys.modules
        with pytest.raises(RuntimeError):subprocess.Popen(['forbidden'])


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='physical Windows stdlib artifact closure')
def test_windows_definition_is_bound_in_planning_source_closure_without_runtime_or_parent_F(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    m=module();definition=m.preload_readonly_definitions();spec=m.local_spec()
    core=SimpleNamespace(runtime_closure=lambda:{'fixture':'no runtime scan'},candidate=lambda:SimpleNamespace(SQL_PATH=ROOT/'query.sql',SCHEMA_PATH=ROOT/'schema.sql'))
    monkeypatch.setattr(m,'load_frozen',lambda:core)
    monkeypatch.setattr(m,'local_spec',lambda:spec)
    monkeypatch.setattr(m.importlib,'import_module',lambda name:SimpleNamespace(verified_platform=lambda *a:nullcontext()))
    monkeypatch.setattr(m,'SOURCES',[]);monkeypatch.setattr(m,'FROZEN',{});monkeypatch.setattr(m,'PARENT_PINS',{})
    monkeypatch.setattr(m,'artifact',lambda p:dict(path=str(p),bytes=1,sha256='a'*64))
    checked=m.dependency_snapshot()
    assert str(definition.__file__) in checked['source_files']
    assert checked['runtime']=={'fixture':'no runtime scan'}
