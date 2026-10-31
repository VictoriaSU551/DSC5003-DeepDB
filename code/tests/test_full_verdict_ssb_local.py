"""Pure LOCAL source/oracle contracts; no growing outputs or scientific imports."""
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
