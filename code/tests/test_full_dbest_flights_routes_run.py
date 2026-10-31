"""Fake original-API control flow only; no actual fit/KDE/integration."""
import importlib.util
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'code'))


def module():
    p=ROOT/'code/full_dbest_flights_routes_run.py';assert p.exists(),'Independent DBEst route worker missing'
    s=importlib.util.spec_from_file_location('routes_run_test',str(p));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def job(m,xs):
    identity=dict(query_no=6,name='F3.2',key=['CA'],component='air_time',scope='PURE_MICRO_FAKE',parent_sql_sha256='a'*64,
        aggregate='sum',xs=xs,row_ids=list(range(len(xs))),fit_rows=len(xs),population_metadata={'Nhat':100.})
    return dict(identity,job_id='fixture',binding_sha256=m.routes.value_hash(identity))


class FakeAPI:
    BACKEND='PURE_FAKE_NOT_SCIENTIFIC'
    def __init__(self,m,value=None):self.m=m;self.value=value;self.fit_calls=0;self.native_calls=0
    def fit(self,j,path):
        self.fit_calls+=1
        if len(j['xs'])==1:raise ValueError('Fake original singleton failure')
        path.write_bytes(b'FAKE_MODEL_NOT_PICKLE')
        return object(),dict(slope=1.,intercept=0.,bandwidth=1.,seconds=0.)
    def invoke(self,engine,j,lower,upper):
        self.native_calls+=1
        expected=self.m.routes.gaussian_oracle(j['xs'],1.,0.,1.,lower,upper,j['population_metadata']['Nhat'])[j['aggregate']]
        return dict(value=expected if self.value is None else self.value,api_calls=1,kde_calls=2,kde_evaluations=2,seconds=0.,warnings=[],error=None)


def test_original_api_dispatch_keeps_zero_singleton_constant_and_native_counters(tmp_path):
    m=module();driver=FakeAPI(m)
    empty=m.execute_job(job(m,[]),driver,tmp_path/'empty',{'frozen':'fixture'})
    singleton=m.execute_job(job(m,[1.]),driver,tmp_path/'one',{'frozen':'fixture'})
    constant=m.execute_job(job(m,[2.,2.]),driver,tmp_path/'two',{'frozen':'fixture'})
    assert empty['status']=='UNAVAILABLE_FIXED_SAMPLE' and empty['estimate'] is None
    assert singleton['status']=='FIT_ERROR' and singleton['estimate'] is None and singleton['fit_attempted'] is True
    assert constant['status']=='RETURNED' and constant['estimate']==pytest.approx(200.)
    assert driver.fit_calls==2 and driver.native_calls==1
    assert constant['backend']=='PURE_FAKE_NOT_SCIENTIFIC' and constant['native']['api_calls']==1


def test_analytic_oracle_can_reject_but_never_replace_native_value(tmp_path):
    m=module();driver=FakeAPI(m,111.)
    result=m.execute_job(job(m,[-1.,1.]),driver,tmp_path/'bad',{'frozen':'fixture'})
    assert result['status']=='NUMERICAL_VALIDATION_FAILED' and result['estimate']==111.
    assert result['oracle']['sum']==pytest.approx(0.) and result['integral_verified'] is False


def test_wide_product_keeps_uniform_breakpoint_budget_gap_without_rescaling(tmp_path):
    m=module();driver=FakeAPI(m)
    result=m.execute_job(job(m,[0.,100000.]),driver,tmp_path/'wide',{'frozen':'fixture'})
    assert result['status']=='NUMERICAL_BUDGET_UNSUPPORTED' and result['estimate'] is None
    assert driver.native_calls==0 and result['job']['xs']==[0.,100000.]


def test_unapproved_run_and_default_describe_never_load_science(tmp_path,monkeypatch,capsys):
    m=module()
    def forbidden(*args,**kwargs):raise AssertionError('Unapproved route touched original science/source')
    monkeypatch.setattr(m,'verify_plan',forbidden);monkeypatch.setattr(m,'OriginalAPI',forbidden)
    with pytest.raises(ValueError):m.run(tmp_path/'missing.json',tmp_path/'absent_review.json','0'*64,'x')
    m.main(['describe']);assert 'CODE_ONLY_NO_SCIENTIFIC_EXECUTION' in capsys.readouterr().out


def test_training_identity_has_no_target_truth_or_evaluation_parent_influence():
    m=module();catalog={'queries':{'6':[]},'target_answers_read':False};source={'code':'a'*64};runtime={'python':'b'*64}
    first=m.training_identity(catalog,source,runtime)
    assert first==m.training_identity(catalog,source,runtime)
    assert 'truth' not in str(first) and 'source_report' not in str(first)
    assert first!=m.training_identity(dict(catalog,queries={'6':[{'count':1}]}),source,runtime)


def test_closed_controller_evidence_rejects_wrong_command_owned_leak_or_exceeded_limit(tmp_path):
    m=module();plan={'kind':'CATALOG','binding_sha256':'a'*64,'base_python':{'path':'.runtime/python.exe'},'limits':m.limits()}
    token='b'*32;sha='c'*64;cmd=list(map(str,m.bootstrap_command(plan,tmp_path,sha,token)))
    worker=dict(status='PASS',kind='CATALOG',binding_sha256='a'*64,process_id=123,owned_job_verified=True,go_verified=True,worker_peak_bytes=100,original_prior_classes_reexecuted=False)
    controller=dict(status='PASS',command=cmd,review_sha256=sha,token=token,job_name=m.job_name(token),exit_code=0,reason=None,
        seconds=1.,owned_job_assigned_before_go=True,live_owned_descendants_after_exit=[],worker_command=list(map(str,m.worker_command(plan,tmp_path,sha,token))))
    resource=dict(limits=m.limits(),samples=[{'monotonic':1.,'owned_rss_bytes':100,'own_output_bytes':10}],peak_owned_rss_bytes=100,peak_output_bytes=10,
        minimum_available_ram_at_start_bytes=2*1024**3,free_disk_at_start_bytes=1024**3)
    m.validate_execution(tmp_path,plan,controller,worker,resource)
    for bad in (dict(controller,live_owned_descendants_after_exit=[99]),dict(controller,command=['python','other.py']),dict(controller,seconds=float('nan'))):
        with pytest.raises(ValueError):m.validate_execution(tmp_path,plan,bad,worker,resource)
    with pytest.raises(ValueError):m.validate_execution(tmp_path,plan,controller,worker,dict(resource,peak_owned_rss_bytes=1024**3))


def test_category_csv_scanner_hashes_exact_same_pass_and_never_fits_or_reads_answers(tmp_path,monkeypatch):
    import csv,hashlib
    m=module();path=tmp_path/'micro.csv'
    raw=dict(zip(m.COLUMNS,['2005','UA','ATL','CA','HPN','HI','2','5','1','3','10','100']))
    with path.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=m.COLUMNS);writer.writeheader();writer.writerow(raw)
    def forbidden(*a,**k):raise AssertionError('Category scan fitted an engine')
    monkeypatch.setattr(m,'OriginalAPI',forbidden)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    catalog,proof=m.scan_category_file(path,1,sha,path.stat().st_size)
    assert catalog['rows']==1 and proof['category_scans']==1 and proof['aggregate_numeric_values_parsed'] is False
    with pytest.raises(ValueError):m.scan_category_file(path,2,sha,path.stat().st_size)
    with pytest.raises(ValueError):m.scan_category_file(path,1,'0'*64,path.stat().st_size)


def test_golden_and_formal_contracts_keep_selection_seeds_probabilities_and_truth_separate():
    m=module();gold=m.population_spec('GOLDEN_200K');formal=m.population_spec('FORMAL_1B')
    assert (gold['population_rows'],gold['retained_rows'],gold['seed'],gold['probability'])==(200000,200000,74031,{'numerator':1,'denominator':1})
    assert (formal['population_rows'],formal['retained_rows'],formal['seed'])==(1000000000,9997912,74131)
    assert gold['selection']['sha256']!=formal['selection']['sha256'] and gold['truth']['path']!=formal['truth']['path']
    assert m.population_spec('GOLDEN_200K')==gold
    with pytest.raises(ValueError):m.population_spec('ARBITRARY')


def test_golden_scanner_retains_only_existing_ids_and_never_reselects(tmp_path,monkeypatch):
    import csv,hashlib
    m=module();path=tmp_path/'gold.csv'
    rows=[dict(zip(m.COLUMNS,[str(2004+i),'UA','ATL','CA','HPN','HI','2','5','1','3','10','100'])) for i in range(3)]
    with path.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=m.COLUMNS);writer.writeheader();writer.writerows(rows)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    catalog,proof,selected=m.scan_category_file(path,3,sha,path.stat().st_size,probability={'numerator':1,'denominator':1},selection_ids=[0,2],with_selection=True)
    assert catalog['probability']=={'numerator':1,'denominator':1} and selected=={'row_ids':[0,2],'rows':[rows[0],rows[2]]}
    assert proof['selected_rows']==2 and proof['aggregate_values_accumulated'] is False
    with pytest.raises(ValueError):m.scan_category_file(path,3,sha,path.stat().st_size,selection_ids=[2,0],with_selection=True)


def test_worker_summary_cannot_self_reseal_fewer_calls_or_a_fake_backend():
    m=module();body={'kind':'ROUTES','population':m.population_spec('FORMAL_1B')};results=[dict(native={'api_calls':1},fit_attempted=True),dict(native={'api_calls':0},fit_attempted=False)]
    good=dict(new_original_api_calls=1,new_fit_attempts=1,new_query_evaluation_only_after_raw_predictions=True,selected_ids_sha256=m.routes.IDS_SHA,backend=m.ORIGINAL_BACKEND)
    m.validate_worker_results(body,good,results)
    for bad in (dict(good,new_original_api_calls=0),dict(good,backend='PURE_FAKE_NOT_SCIENTIFIC'),dict(good,new_query_evaluation_only_after_raw_predictions=False)):
        with pytest.raises(ValueError):m.validate_worker_results(body,bad,results)


def test_fresh_boundary_constructs_once_without_any_scientific_loader(monkeypatch):
    m=module();calls=[]
    for name in ('source_proof','own_snapshot','runtime_snapshot'):
        monkeypatch.setattr(m,name,lambda name=name:(calls.append(name) or {'fixture':name}))
    proof=m._Boundary()
    assert calls==['source_proof','own_snapshot','runtime_snapshot'] and proof.source=={'fixture':'source_proof'}


def test_owned_windows_helpers_are_extracted_without_importing_ssb_stack(monkeypatch):
    m=module()
    def forbidden(*a,**k):raise AssertionError('Whole SSB scientific module imported for process ownership')
    monkeypatch.setattr(m,'load_module',forbidden)
    common=m.owned_ops()
    assert callable(common.OwnedWindowsJob) and callable(common.windows_process_alive)
    assert set(vars(common))=={'OwnedWindowsJob','windows_process_alive','windows_api'}


def test_formal_routes_cannot_precede_an_actual_original_sum_and_avg_golden():
    m=module();report=dict(population='GOLDEN_200K',native_verified_aggregates=['sum','avg'],numerical_validation_failures=0,native_calls=2)
    m.validate_golden_gate(report)
    for bad in (dict(report,population='FORMAL_1B'),dict(report,native_verified_aggregates=['sum']),dict(report,numerical_validation_failures=1),dict(report,native_calls=0)):
        with pytest.raises(ValueError):m.validate_golden_gate(bad)


def test_fresh_worker_evidence_requires_actual_private_executable_argv_and_threads(tmp_path):
    m=module();token='b'*32;sha='c'*64;plan=dict(kind='CATALOG',binding_sha256='a'*64,base_python={'path':'.runtime/python.exe'},population=m.population_spec('GOLDEN_200K'))
    expected=m.worker_identity(plan,tmp_path,sha,token)
    assert expected['script_argv']==list(map(str,m.worker_command(plan,tmp_path,sha,token)))[2:]
    assert expected['interpreter_flags']=={'dont_write_bytecode':1}
    assert expected['environment']['PYTHONHASHSEED']=='74031' and expected['environment']['OMP_NUM_THREADS']=='1'
    assert expected['executable']==str(m.PRIVATE)


def test_assignment_failure_never_sends_go_and_stops_only_created_bootstrap(tmp_path,monkeypatch):
    import io
    m=module();events=[]
    class Pipe(io.BytesIO):
        def write(self,data):events.append('GO');return super().write(data)
    class Process:
        def __init__(self):self.stdin=Pipe()
        def terminate(self):events.append('created_process_terminate')
        def wait(self,timeout):events.append(('created_process_wait',timeout));return 1
    class Job:
        def assign(self,p):events.append('assign_failed');raise OSError('Fake AssignProcessToJobObject failure')
        def terminate(self):raise AssertionError('Unassigned job cannot stop unrelated processes')
    process=Process();monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:process)
    with pytest.raises(OSError):m.spawn_owned(Job(),['NEVER_EXECUTE'],{},None,None,{'token':'fake'})
    assert events==['assign_failed','created_process_terminate',('created_process_wait',15)] and process.stdin.closed


def test_owned_go_failure_terminates_assigned_tree_not_unrelated_direct_process(monkeypatch):
    m=module();events=[]
    class Pipe:
        closed=False
        def write(self,data):raise BrokenPipeError('fake broken GO')
        def close(self):self.closed=True
    class Process:
        stdin=Pipe()
        def terminate(self):raise AssertionError('Already owned tree must be stopped through job handle')
        def wait(self,timeout):return 1
    class Job:
        def assign(self,p):events.append('assigned')
        def terminate(self):events.append('owned_job_terminate')
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:Process())
    with pytest.raises(BrokenPipeError):m.spawn_owned(Job(),['NEVER_EXECUTE'],{},None,None,{})
    assert events==['assigned','owned_job_terminate']


def test_original_quadrature_adapter_identity_uses_actual_points_and_frozen_failure(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'descriptor',lambda p:dict(path='pure/failure.json',bytes=1,sha256='a'*64))
    expected=m.compatibility_record(-12.,14.,1.)
    assert expected['breakpoints']==6 and expected['source_failure_scope'].startswith('Previously verified original200K')
    assert expected['kind']=='Original scipy.quad points/limit only' and expected['source_failure']['sha256']=='a'*64


def test_worker_observation_distinguishes_sys_argv_from_launch_flags(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=module();plan=dict(population={'seed':74031});token='a'*32;sha='b'*64
    command=list(map(str,m.worker_command(plan,tmp_path,sha,token)))
    assert command[1]=='-B'
    monkeypatch.setattr(m.sys,'executable',command[0]);monkeypatch.setattr(m.sys,'argv',command[2:])
    monkeypatch.setattr(m.sys,'flags',SimpleNamespace(dont_write_bytecode=1))
    expected=m.worker_identity(plan,tmp_path,sha,token)
    for key,value in expected['environment'].items():monkeypatch.setenv(key,value)
    for key in expected['absent_environment']:monkeypatch.delenv(key,raising=False)
    actual=m.observe_worker_identity(expected)
    assert actual==expected
    assert actual['script_argv']==command[2:]
    assert actual['interpreter_flags']=={'dont_write_bytecode':1}
    assert 'command' not in actual
    monkeypatch.setattr(m.sys,'flags',SimpleNamespace(dont_write_bytecode=0))
    assert m.observe_worker_identity(expected)!=expected


def test_worker_observation_cannot_hide_changed_script_or_environment(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=module();expected=m.worker_identity(dict(population={'seed':74031}),tmp_path,'b'*64,'a'*32)
    monkeypatch.setattr(m.sys,'executable',expected['executable']);monkeypatch.setattr(m.sys,'argv',expected['script_argv']+['--unexpected'])
    monkeypatch.setattr(m.sys,'flags',SimpleNamespace(dont_write_bytecode=1))
    for key,value in expected['environment'].items():monkeypatch.setenv(key,value)
    for key in expected['absent_environment']:monkeypatch.delenv(key,raising=False)
    assert m.observe_worker_identity(expected)!=expected
    monkeypatch.setattr(m.sys,'argv',expected['script_argv']);monkeypatch.setenv('OMP_NUM_THREADS','2')
    assert m.observe_worker_identity(expected)!=expected

