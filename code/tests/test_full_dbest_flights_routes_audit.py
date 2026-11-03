"""Synthetic evidence closure and forbidden-operation tests only."""
import importlib.util
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_dbest_flights_routes_audit.py';assert p.exists(),'Independent read-only route audit missing'
    s=importlib.util.spec_from_file_location('routes_audit_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_required_set_is_independent_nonempty_and_rejects_missing_extra_duplicate_jobs():
    m=module();plan=dict(kind='ROUTES',jobs=[{'job_id':'a'},{'job_id':'b'}]);states={'a':'PASS','b':'FIT_ERROR'}
    required=m.required_files(plan,states);assert 'jobs/0000/model.pkl' in required and 'jobs/0001/model.pkl' not in required
    m.check_required(plan,states,{p:{} for p in required})
    for bad in ({},{p:{} for p in required if p!='jobs/0001/result.json'},dict({p:{} for p in required},foreign={})):
        with pytest.raises(ValueError):m.check_required(plan,states,bad)
    with pytest.raises(ValueError):m.required_files(dict(plan,jobs=[{'job_id':'a'},{'job_id':'a'}]),states)


def test_readonly_guard_blocks_process_database_model_unpickle_and_write(tmp_path):
    import pickle,subprocess,sqlite3
    m=module();p=tmp_path/'input.json';p.write_text('{"ok":1}',encoding='utf-8')
    with m.forbid_operations():
        assert m.strict_read(p)=={'ok':1}
        for call in (lambda:subprocess.Popen(['NEVER_EXECUTE']),lambda:sqlite3.connect(':memory:'),lambda:pickle.loads(b'N.'),lambda:p.write_text('{}')):
            with pytest.raises(RuntimeError):call()
        import io,os
        for call in (lambda:pickle.Unpickler(io.BytesIO(b'N.')).load(),lambda:os.spawnv(os.P_WAIT,'NEVER_EXECUTE',[])):
            with pytest.raises(RuntimeError):call()
    for text in ('{"x":1,"x":2}','{"x":NaN}'):
        p.write_text(text,encoding='utf-8')
        with pytest.raises(ValueError):m.strict_read(p)


def test_finite_native_output_and_metadata_cannot_be_replaced_by_self_resealed_analytic_answer():
    m=module();j=dict(query_no=6,key=['CA'],component='air_time',parent_sql_sha256='a'*64,xs=[-1.,1.],aggregate='sum',population_metadata={'Nhat':100.})
    fit=dict(status='PASS',attempted=True,slope=1.,intercept=0.,bandwidth=1.,seconds=0.)
    native=dict(api_calls=1,kde_calls=2,kde_evaluations=2,seconds=0.,value=111.,warnings=[],error=None)
    derived=m.derive_result(j,fit,native)
    assert derived['status']=='NUMERICAL_VALIDATION_FAILED' and derived['estimate']==111. and derived['oracle']['sum']==pytest.approx(0.)
    assert m.derive_result(j,dict(status='FIT_ERROR',attempted=True),dict(api_calls=0,kde_calls=0,kde_evaluations=0,seconds=0.,value=None,error=None))['estimate'] is None
    with pytest.raises(ValueError):m.derive_result(j,dict(fit,bandwidth=2.),native)


def test_actual_request_training_binding_is_recomputed_without_loading_model(tmp_path,monkeypatch):
    from test_full_dbest_flights_routes_run import FakeAPI,job
    m=module();j=job(m.ops,[2.,2.]);driver=FakeAPI(m.ops)
    driver.BACKEND=m.ops.ORIGINAL_BACKEND
    binding=dict(evidence_plan_binding_sha256='a'*64,training_binding_sha256='b'*64)
    m.ops.execute_job(j,driver,tmp_path/'job',binding)
    expected=dict(kind='PURE_FAKE_ADAPTER_RECEIPT_ONLY');monkeypatch.setattr(m.ops,'compatibility_record',lambda *a:expected)
    native=m.strict_read(tmp_path/'job/native.json');native['compatibility_adapter']=expected;m.ops.atomic(tmp_path/'job/native.json',native)
    result=m.strict_read(tmp_path/'job/result.json');result['native']=native;m.ops.atomic(tmp_path/'job/result.json',result)
    m.ops.atomic(tmp_path/'job/result.seal.json',dict(sha256=m.ops.digest(tmp_path/'job/result.json'),request_sha256=m.ops.digest(tmp_path/'job/request.json')))
    with m.forbid_operations():m.verify_job(tmp_path/'job',j,binding)
    fit=m.strict_read(tmp_path/'job/fit.json');fit['training_binding_sha256']='0'*64
    m.ops.atomic(tmp_path/'job/fit.json',fit)
    with m.forbid_operations(),pytest.raises(ValueError):m.verify_job(tmp_path/'job',j,binding)


def test_empty_final_manifest_rejected_before_any_parent_source_audit(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.ops,'OUT',tmp_path)
    home=tmp_path/'runs/empty';home.mkdir(parents=True)
    plan={'kind':'CATALOG','binding_sha256':'a'*64}
    final=dict(schema='dbest_routes_final_v1',binding_sha256='a'*64,files={},author_training_configuration_recovered=False,full_paper_reproduction_complete=False)
    for name,body in [('plan.json',plan),('final.json',final)]:m.ops.atomic(home/name,body)
    sha=m.ops.digest(home/'final.json');m.ops.atomic(home/'final.seal.json',{'sha256':sha});m.ops.atomic(home/'lifecycle.json',dict(status='PASS',final_sha256=sha))
    def expensive():raise AssertionError('Invalid manifest reached full original/source audit')
    monkeypatch.setattr(m.ops,'_Boundary',expensive)
    with pytest.raises(ValueError,match='required set'):m.verify(home)


def test_sealed_golden_integer_truth_is_converted_in_original_units_without_sqlite():
    m=module();aggregates=[dict(query_no=i,query_name=m.routes.QUERY_NAMES[i],groups=[dict(key=[],sum=120,count=3)]) for i in range(12)]
    truth=m.ops.golden_truth({'aggregates':aggregates})
    assert truth['population_rows']==200000 and truth['queries'][7]['groups'][0]['denominator']==30
    assert truth['queries'][10]['groups'][0]['denominator']==100 and truth['queries'][11]['groups'][0]['denominator']==10
    bad=[dict(g) for g in aggregates];bad[6]['query_no']=7
    with pytest.raises(ValueError):m.ops.golden_truth({'aggregates':bad})


def test_native_zero_call_gap_cannot_hide_kde_work_or_bad_warning_diagnostics():
    m=module();j=dict(xs=[],aggregate='sum',population_metadata={'Nhat':100.})
    with pytest.raises(ValueError):m.derive_result(j,dict(status='NOT_ATTEMPTED_EMPTY_FIXED_SAMPLE'),dict(api_calls=0,kde_calls=1,kde_evaluations=1,seconds=0.,value=None,error=None))
    j['xs']=[1.,2.];fit=dict(status='PASS',attempted=True,slope=1.,intercept=0.,bandwidth=1.,seconds=0.)
    with pytest.raises(ValueError):m.derive_result(j,fit,dict(api_calls=1,kde_calls=0,kde_evaluations=0,seconds=0.,value=100.,error=None,warnings='Not a list'))


def fixture_complete_catalog(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.ops,'ROOT',tmp_path);monkeypatch.setattr(m.ops,'OUT',tmp_path/'output/full/dbest_flights_routes')
    home=m.ops.OUT/'runs/fixture';home.mkdir(parents=True)
    p=m.ops.population_spec('FORMAL_1B');body=dict(kind='CATALOG',binding_sha256='a'*64,population=p,base_python={'path':'.runtime/python.exe'},source={'complete_inventory_sha256':'d'*64})
    review=dict(status='APPROVED_DBEST_ROUTES_CATALOG',binding_sha256=body['binding_sha256'],limits=m.ops.limits())
    for name,value in [('plan.json',body),('review.json',review),('source_before.json',body['source']),('source_after.json',body['source'])]:m.ops.atomic(home/name,value)
    sha=m.ops.digest(home/'review.json');token='b'*32
    controller=dict(status='PASS',command=list(map(str,m.ops.bootstrap_command(body,home,sha,token))),worker_command=list(map(str,m.ops.worker_command(body,home,sha,token))),review_sha256=sha,token=token,
        job_name=m.ops.job_name(token),exit_code=0,reason=None,seconds=1.,owned_job_assigned_before_go=True,live_owned_descendants_after_exit=[])
    worker=dict(status='PASS',kind='CATALOG',binding_sha256=body['binding_sha256'],process_id=123,owned_job_verified=True,go_verified=True,worker_peak_bytes=100,original_prior_classes_reexecuted=False,
        new_original_api_calls=0,new_fit_attempts=0,new_query_evaluation_only_after_raw_predictions=True,selected_ids_sha256=p['row_ids_sha256'],backend='CATEGORY_MEMBERSHIP_ONLY')
    worker['identity']=m.ops.worker_identity(body,home,sha,token)
    resource=dict(limits=m.ops.limits(),samples=[dict(monotonic=1.,owned_rss_bytes=100,own_output_bytes=10)],peak_owned_rss_bytes=100,peak_output_bytes=10,minimum_available_ram_at_start_bytes=2*1024**3,free_disk_at_start_bytes=1024**3)
    catalog=m.routes.build_catalog([],1,100,0);catalog['rows']=p['retained_rows']
    scan=dict(rows=p['retained_rows'],sha256=p['sample']['sha256'],bytes=p['sample']['bytes'],aggregate_numeric_values_parsed=False,aggregate_values_accumulated=False,category_scans=1,selected_rows=0,seconds=0.)
    for name,value in [('controller.json',controller),('worker.json',worker),('resource.json',resource),('catalog.json',catalog),('sample_scan.json',scan)]:m.ops.atomic(home/name,value)
    (home/'stdout.log').write_text('PURE FIXTURE ONLY');(home/'stderr.log').write_text('')
    def reseal():
        files={n:m.ops.descriptor(home/n) for n in sorted(m.required_files(body,{}))}
        final=dict(schema='dbest_routes_final_v1',binding_sha256=body['binding_sha256'],review_sha256=sha,files=files,author_training_configuration_recovered=False,full_paper_reproduction_complete=False)
        m.ops.atomic(home/'final.json',final);fsha=m.ops.digest(home/'final.json');m.ops.atomic(home/'final.seal.json',{'sha256':fsha});m.ops.atomic(home/'lifecycle.json',dict(status='PASS',final_sha256=fsha))
    reseal()
    monkeypatch.setattr(m.ops,'_Boundary',lambda:object());monkeypatch.setattr(m.ops,'_verify_plan_from_boundary',lambda supplied,proof:supplied)
    def forbidden(*a,**k):raise AssertionError('Pure default auditor touched fitting, CSV scan, or engine')
    monkeypatch.setattr(m.ops,'OriginalAPI',forbidden);monkeypatch.setattr(m.ops,'scan_category_file',forbidden)
    return m,home,reseal


def test_complete_default_verifier_remains_readonly_and_rejects_resealed_operational_violation(tmp_path,monkeypatch):
    m,home,reseal=fixture_complete_catalog(tmp_path,monkeypatch)
    before={p:m.ops.digest(p) for p in home.rglob('*') if p.is_file()}
    report=m.verify(home)
    assert report['native_calls']==0 and report['files_written'] is False and report['models_loaded'] is False
    assert before=={p:m.ops.digest(p) for p in before}
    worker=m.strict_read(home/'worker.json');worker['new_original_api_calls']=1;m.ops.atomic(home/'worker.json',worker);reseal()
    with pytest.raises(ValueError):m.verify(home)


def test_self_resealed_resource_cap_and_tainted_lifecycle_cannot_pass(tmp_path,monkeypatch):
    m,home,reseal=fixture_complete_catalog(tmp_path,monkeypatch)
    resource=m.strict_read(home/'resource.json');resource['free_disk_at_start_bytes']=0;m.ops.atomic(home/'resource.json',resource);reseal()
    with pytest.raises(ValueError):m.verify(home)
    m.ops.atomic(home/'lifecycle.json',dict(status='TAINTED',error='Preserved failed attempt'))
    with pytest.raises(ValueError):m.verify(home)
