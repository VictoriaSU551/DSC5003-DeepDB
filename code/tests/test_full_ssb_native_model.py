"""Pure synthetic contract tests. No generator, HDF preparation or training runs."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_ssb_native_model.py'
    assert path.exists(),'New native v2 model bridge is missing'
    spec=importlib.util.spec_from_file_location('native_ssb_model',str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def contract(m):
    widths=(0,0,0,2,2,2,3,3,3,3,2,3,3)
    truth=[]
    for q in range(13):
        count=1 if q<3 else 205 if q<12 else 211
        for i in range(count):truth.append(dict(query_no=q,group=[str(i)]+['g']*(widths[q]-1) if widths[q] else [],value=q*100000+i))
    assert len(truth)==2059
    sample=dict(path=str(ROOT/'data/ssb/sf500_native_v2/lineorder_sampled.csv'),bytes=123,sha256='1'*64,rows=1000001)
    dims={name:dict(path=str(ROOT/'data/ssb/sf500_native_v2/dimensions'/(name+'.tbl')),bytes=123,sha256='2'*64,rows=rows)
          for name,rows,width in [('customer',15000000,8),('supplier',1000000,7),('part',1800000,9),('date',2556,17)]}
    desc=lambda path:dict(path=str(ROOT/path),bytes=123,sha256='3'*64)
    artifacts=dict(raw_sample={k:v for k,v in sample.items() if k!='rows'},
        checkpoint=desc('output/full/ssb/native_v2/final/checkpoint.json'),plan=desc('output/full/ssb/native_v2/final/plan.json'),
        queries=desc(m.SQL_REL),author_truth=desc(m.TRUTH_REL))
    artifacts.update({'dimension/'+name:{k:v for k,v in d.items() if k!='rows'} for name,d in dims.items()})
    cutoff=3333*2**64//1000000;p=Fraction(cutoff,2**64)
    binding=dict(scale='500',shards=4000,total_orders=750000000,sample_seed=20261031,actual_cutoff=cutoff,dimensions=dims)
    binding['source_id']=m.value_hash(binding)
    plan=dict(schema='ssb_native_v2_stream_plan_v1',binding=binding,ranges=[[i*187500+1,187500] for i in range(4000)])
    state=dict(schema='ssb_native_v2_checkpoint_v1',binding=binding,complete=True,next_shard=4000,
        committed_shards=[dict(shard=i,first_order=i*187500+1,orders=187500) for i in range(4000)],
        rows=m.N,sample_rows=sample['rows'],aggregates=truth,sample_sha256=sample['sha256'],sample_bytes=sample['bytes'])
    body=dict(schema='ssb_native_v2_final_v1',status='PASS_AUTHOR_TRUTHS',complete=True,
        paper_population_row_count_and_13_truths_match=True,N=m.N,population_rows=m.N,source_id=binding['source_id'],sample_rows=sample['rows'],
        sampling=dict(sample_seed=20261031,actual_cutoff=cutoff,probability_numerator=cutoff,probability_denominator=2**64,
                      effective_probability=float(p),
                      requested_numerator=3333,requested_denominator=1000000,
                      normalizer_numerator=sample['rows']*2**64,normalizer_denominator=cutoff,normalizer_n_over_p=float(sample['rows']/p)),
        canonical_truth=truth,checkpoint=artifacts['checkpoint'],plan=artifacts['plan'],raw_sample=sample,dimensions=dims,artifacts=artifacts)
    return body,copy.deepcopy(truth),state,plan


def test_complete_synthetic_contract_has_exact_n_over_effective_p():
    m=module();body,truth,state,plan=contract(m);r=m.validate_contract(body,truth,state,plan)
    p=Fraction(body['sampling']['actual_cutoff'],2**64)
    assert Fraction(r['fact_normalizer']['numerator'],r['fact_normalizer']['denominator'])==body['sample_rows']/p
    assert r['truth_groups']==2059 and r['population_rows']==m.N


@pytest.mark.parametrize('change',['incomplete','mismatch','N','missing_truth','duplicate_truth','noninteger','wrong_value','unfinished_checkpoint','missing_shard','range_gap','cutoff','nominal_probability','sample_hash','dims_rows','old_namespace'])
def test_synthetic_contract_rejects_resealed_generation_and_truth_gaps(change):
    m=module();b,t,state,plan=contract(m)
    if change=='incomplete':b['complete']=False
    elif change=='mismatch':b['status']='MISMATCH'
    elif change=='N':b['N']+=92
    elif change=='missing_truth':b['canonical_truth'].pop()
    elif change=='duplicate_truth':b['canonical_truth'][-1]=b['canonical_truth'][-2]
    elif change=='noninteger':b['canonical_truth'][0]['value']=1.0
    elif change=='wrong_value':b['canonical_truth'][0]['value']+=1
    elif change=='unfinished_checkpoint':state['next_shard']=3999
    elif change=='missing_shard':state['committed_shards'].pop()
    elif change=='range_gap':state['committed_shards'][1]['first_order']+=1
    elif change=='cutoff':b['sampling']['actual_cutoff']+=1
    elif change=='nominal_probability':b['sampling']['probability_numerator']=1;b['sampling']['probability_denominator']=300
    elif change=='sample_hash':state['sample_sha256']='4'*64
    elif change=='dims_rows':b['dimensions']['part']['rows']-=1
    elif change=='old_namespace':b['raw_sample']['path']=str(ROOT/'data/ssb/sf500_paper/lineorder_sampled.csv')
    with pytest.raises(ValueError):m.validate_contract(b,t,state,plan)


def test_physical_artifact_detects_changed_bytes_counts_and_shape(tmp_path):
    m=module();p=tmp_path/'raw.tbl';p.write_bytes(b'1|a\n2|b\n')
    entry=dict(path='raw.tbl',bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),rows=2,fields=2)
    assert m.verify_artifact(entry,tmp_path)['rows']==2
    with pytest.raises(ValueError):m.verify_artifact(dict(entry,rows=3),tmp_path)
    with pytest.raises(ValueError):m.verify_artifact(dict(entry,fields=3),tmp_path)
    p.write_bytes(b'1|a\n2|c\n')
    with pytest.raises(ValueError):m.verify_artifact(entry,tmp_path)


def test_missing_final_source_rejects_before_sample_or_legacy_modules(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='final.*receipt'):
        m.verify_generation(tmp_path/'missing.json','0'*64,root=tmp_path)


def test_context_restores_output_on_exception_and_requires_fresh_worker(tmp_path,monkeypatch):
    m=module();core=SimpleNamespace(OUTPUT='legacy/output');destination=tmp_path/'output/full/ssb/native_v2_models/runtime'
    with pytest.raises(ValueError,match='fresh'):
        with m.isolated_output(core,destination,root=tmp_path):pass
    monkeypatch.setenv('DEEPDB_SSB_NATIVE_MODEL_WORKER','1')
    with pytest.raises(RuntimeError,match='synthetic stop'):
        with m.isolated_output(core,destination,root=tmp_path):
            assert core.OUTPUT==destination
            raise RuntimeError('synthetic stop')
    assert core.OUTPUT=='legacy/output'
    with m.isolated_output(core,destination,root=tmp_path):assert core.OUTPUT==destination
    assert core.OUTPUT=='legacy/output'


@pytest.mark.parametrize('free,ram,existing',[(8*1024**3-1,4*1024**3,0),(8*1024**3,4*1024**3-1,0),(8*1024**3,4*1024**3,12*1024**3)])
def test_formal_resource_limits(free,ram,existing):
    m=module()
    with pytest.raises(ValueError):m.check_resources(free,ram,existing,additional_bytes=5*1024**3)


def test_formal_entry_is_closed_and_draft_is_not_trainable():
    m=module();assert m.FINAL_RECEIPT_INTERFACE_FROZEN is False
    plan=m.draft_plan()
    assert plan['executable'] is False and plan['formal_training_started'] is False
    assert plan['model']['samples_per_spn']==1000000 and plan['model']['seed']==1 and plan['model']['rdc_threshold']==.3
    with pytest.raises(ValueError,match='frozen'):m.execute_formal({},memory_approved=True)


def test_formal_transaction_reuses_only_validated_pass_without_repeating_producer(tmp_path):
    m=module();calls=[]
    def produce():calls.append('run');return {'scientific':'synthetic fixture only'}
    expected={'source':'fixed synthetic'}
    first=m.formal_transaction(tmp_path/'control',expected,produce,lambda r:None)
    second=m.formal_transaction(tmp_path/'control',expected,produce,lambda r:None)
    assert first==second and calls==['run']
    with pytest.raises(ValueError,match='binding'):
        m.formal_transaction(tmp_path/'control',{'source':'changed'},produce,lambda r:None)
    assert calls==['run']


def test_formal_failure_is_durably_tainted_and_never_retried(tmp_path):
    m=module();calls=[]
    def produce():calls.append(1);return {'partial':'not publishable'}
    def fail(r):raise ValueError('synthetic post-validation failure')
    with pytest.raises(ValueError,match='post-validation'):
        m.formal_transaction(tmp_path/'control',{},produce,fail)
    assert json.loads((tmp_path/'control/lifecycle.json').read_text())['status']=='TAINTED'
    with pytest.raises(ValueError,match='TAINTED'):
        m.formal_transaction(tmp_path/'control',{},produce,lambda r:None)
    assert calls==[1] and not (tmp_path/'control/receipt.json').exists()


def test_formal_leftover_running_and_incomplete_pass_are_rejected(tmp_path):
    m=module();home=tmp_path/'control';home.mkdir()
    m.atomic(home/'lifecycle.json',dict(status='RUNNING',binding={}))
    with pytest.raises(ValueError,match='TAINTED'):
        m.formal_transaction(home,{},lambda:pytest.fail('must not run'),lambda r:None)
    assert json.loads((home/'lifecycle.json').read_text())['status']=='TAINTED'
    other=tmp_path/'missing_pass';other.mkdir();m.atomic(other/'lifecycle.json',dict(status='PASS',binding={},receipt_sha256='0'*64))
    with pytest.raises(ValueError):m.formal_transaction(other,{},lambda:pytest.fail('must not repair'),lambda r:None)
    assert json.loads((other/'lifecycle.json').read_text())['status']=='TAINTED'


def test_unique_controller_lock_blocks_second_controller_and_releases_on_error(tmp_path):
    m=module();path=tmp_path/'controller.lock'
    with pytest.raises(RuntimeError,match='synthetic interrupt'):
        with m.controller_lock(path):
            with pytest.raises(ValueError,match='controller'): 
                with m.controller_lock(path):pytest.fail('two controllers acquired same lock')
            raise RuntimeError('synthetic interrupt')
    with m.controller_lock(path):pass


def test_future_formal_cannot_be_enabled_by_flipping_only_interface_flag(monkeypatch):
    m=module();monkeypatch.setattr(m,'FINAL_RECEIPT_INTERFACE_FROZEN',True)
    with pytest.raises(ValueError,match='closure|publication|control'):m.execute_formal({},memory_approved=True)


def test_unfinished_formal_read_only_api_refuses_without_creating_any_output(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='completed|publication|formal'):m.verify_formal(root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def synthetic_stages(m,root,run_id='synthetic',complete=None):
    """Real physical fixture bytes; intentionally no trained model or HDF claims."""
    run=root/m.OUTPUT_REL/'runs'/run_id;run.mkdir(parents=True)
    sql=root/m.SQL_REL;sql.parent.mkdir(parents=True);sql.write_bytes((ROOT/m.SQL_REL).read_bytes())
    author=m.load_author_groups(ROOT);complete=complete if complete is not None else {'sources':{'synthetic':'fixture'}}
    report=dict(directory=str(run),plan={'dependencies':{'complete':complete}},actual_sample_rows=1000001,
        source_receipt_sha256='a'*64,point_query_errors=0,ci_query_errors=0,spn_count=5)
    inputs=dict(probability={'numerator':1,'denominator':300},physical_artifacts=[])
    raw={}
    for table in m.TABLES:
        name='lineorder_sampled.csv' if table=='lineorder' else 'date.tbl' if table=='dwdate' else table+'.tbl'
        path=root/'data/ssb/sf500_native_v2'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'SYNTHETIC raw fixture\n')
        item=m.artifact_record(path,root);inputs['physical_artifacts'].append(item);raw[table]={'path':str(path),'sha256':item['sha256']}
    report['inputs']=inputs
    prepared=run/'prepared';prepared.mkdir();meta={}
    for table in m.TABLES:
        path=prepared/(table+'.hdf');path.write_bytes(('SYNTHETIC HDF bytes '+table).encode());meta[table]={'hdf_path':str(path)}
    unmatched=prepared/'customer.hdflineorder.hdf';unmatched.write_bytes(b'SYNTHETIC unmatched HDF bytes')
    meta['customer']['fk']={'path':str(unmatched)}
    (prepared/'meta_data.pkl').write_bytes(pickle.dumps(meta,protocol=4));m.atomic(prepared/'binding.json',{'synthetic':'not a scientific receipt'})
    recorded={p.name:m.digest(p) for p in prepared.iterdir()};m.atomic(prepared/'seal.json',{'files_sha256':recorded})
    partifact=dict(prepared_files_sha256=recorded,raw_files=raw)
    def outer(directory,kind,result,extra=None):
        home=m.stage_home(directory,kind.lower());binding=dict(dependencies=complete,guard_source_sha256=m.FROZEN['code/full_ssb_guard.py'])
        binding.update(extra or {});m.atomic(home/'receipt.json',dict(status='PASS',kind=kind,binding=binding,result=result))
        m.atomic(home/'lifecycle.json',dict(status='PASS',binding=binding,receipt_sha256=m.digest(home/'receipt.json')))
    outer(prepared,'PREPARED',dict(core_input_artifacts=partifact,core_seal_sha256=m.digest(prepared/'seal.json')))
    model_dir=run/'model';model_dir.mkdir()
    binding=dict(samples_per_spn=1000000,seed=1,ensemble_strategy='single',rdc_threshold=.3)
    training=[]
    for table in m.TABLES:
        path=model_dir/(table+'.pkl');path.write_bytes(('SYNTHETIC checkpoint '+table).encode())
        row=dict(table=table,actual_training_rows=2556 if table=='dwdate' else 1000000,
                 full_join_estimate=1000001*300 if table=='lineorder' else 1000000)
        training.append(row);m.atomic(path.with_suffix('.json'),dict(binding=binding,sha256=m.digest(path),training=row))
    ensemble=model_dir/'ensemble_single.pkl';ensemble.write_bytes(b'SYNTHETIC no executable model')
    model=dict(status='PASS',binding=binding,model_path=str(ensemble),spn_count=5,training_tables=training,
        files_sha256={p.name:m.digest(p) for p in model_dir.glob('*.pkl')})
    m.atomic(model_dir/'model.json',model);guard_binding=dict(model_stage=binding,inputs=partifact)
    m.atomic(model_dir/'input_guard.json',dict(binding=guard_binding))
    m.atomic(model_dir/'model_guard.json',dict(binding=guard_binding,model_files_sha256={p.name:m.digest(p) for p in model_dir.iterdir()}))
    outer(model_dir,'MODEL',model,dict(prepared_outer_receipt_sha256=m.digest(m.stage_home(prepared,'prepared')/'receipt.json')))
    report.update(model=model,model_path=str(ensemble),model_sha256=m.digest(ensemble),training_tables=training)
    helper=root/m.OUTPUT_REL/'runtime/native';helper.mkdir(parents=True)
    source=b'SYNTHETIC CI helper';source_sha=hashlib.sha256(source).hexdigest();stem='ci_'+source_sha[:16]
    (helper/(stem+'.cpp')).write_bytes(source);(helper/(stem+'.exe')).write_bytes(b'SYNTHETIC executable bytes')
    build=dict(binding={'source_sha256':source_sha},executable_sha256=m.digest(helper/(stem+'.exe')))
    m.atomic(helper/(stem+'.json'),build);m.atomic(helper/(stem+'_build.json'),dict(returncode=0))
    sqls=sql.read_text().splitlines();moments=run/'sample_moments_native';moments.mkdir()
    m.atomic(moments/'moments.json',dict(status='PASS',sample_rows=1000001,build=build,queries=[{'sql':s} for s in sqls]))
    (moments/'moments.tsv').write_bytes(b'SYNTHETIC integer moments\n')
    m.atomic(moments/'seal.json',dict(binding={'sample_rows':1000001},sha256=m.digest(moments/'moments.json'),tsv_sha256=m.digest(moments/'moments.tsv')))
    m.atomic(moments/'process.json',dict(returncode=0))
    checkpoint=run/'core_truth_checkpoint.json';m.atomic(checkpoint,dict(source_receipt_sha256='a'*64))
    ebinding=dict(confidence_sample_size=1000001,truth_checkpoint_sha256=m.digest(checkpoint));queries=[];identities=[]
    evaluation_dir=run/'evaluation'/'synthetic';evaluation_dir.mkdir(parents=True)
    for i,(name,s) in enumerate(zip(m.QUERY_NAMES,sqls)):
        groups=[]
        for row in author:
            if row['query_no']!=i:continue
            value=float(row['value']);groups.append(dict(key=row['group'],truth=value,prediction=value,status='MATCHED',
                zero_truth=value==0,absolute_error=0,relative_error=0 if value else None,model_interval=None,model_covers_truth=None,
                model_relative_half_width=None,sample_moments={},reference_ci={},released_ci_comparison={}))
        query=dict(query_no=i,query_name=name,sql=s,groups=groups,truth_groups=len(groups),model_groups=len(groups),
            missing_model_groups=0,extra_model_groups=0,point_error=None,ci_error=None,nonfinite_original_intervals=[])
        path=evaluation_dir/('query_%02d.json'%i);m.atomic(path,query);seal=path.with_suffix('.seal.json');m.atomic(seal,dict(binding=ebinding,sha256=m.digest(path)))
        identities.append(dict(query_no=i,query_name=name,exact_sql=s,global_binding=ebinding,result_sha256=m.digest(path),core_seal_sha256=m.digest(seal)))
        queries.append(query)
    evaluation=dict(queries=queries,binding=ebinding,identities=identities,directory=str(evaluation_dir))
    outer(run/'evaluation','EVALUATION',evaluation)
    report.update(queries=queries,evaluation=evaluation,evaluation_binding=ebinding,evaluation_directory=str(evaluation_dir))
    return report,author


def test_required_stage_inventory_uses_real_frozen_shapes_without_unpickling(tmp_path,monkeypatch):
    m=module();report,author=synthetic_stages(m,tmp_path)
    monkeypatch.setattr(pickle,'load',lambda *a,**k:pytest.fail('read-only inventory must not unpickle'))
    records=m.required_stage_artifacts(report,tmp_path,author)
    assert any(r['path'].endswith('customer.hdflineorder.hdf') for r in records)
    assert sum('/query_' in r['path'] for r in records)==26
    assert sum(r['path'].endswith('/receipt.json') for r in records)==3


@pytest.mark.parametrize('damage',['unmatched_omitted','guard_missing','query_subset','query_identity','truth_value','model_pickle_subset','moment_sample_size'])
def test_required_stage_inventory_rejects_self_resealed_subsets(tmp_path,damage):
    m=module();report,author=synthetic_stages(m,tmp_path);run=Path(report['directory'])
    if damage=='unmatched_omitted':
        p=run/'prepared';seal=m.read(p/'seal.json');seal['files_sha256'].pop('customer.hdflineorder.hdf');m.atomic(p/'seal.json',seal)
        outer=m.stage_home(p,'prepared');receipt=m.read(outer/'receipt.json');receipt['result']['core_input_artifacts']['prepared_files_sha256']=seal['files_sha256']
        receipt['result']['core_seal_sha256']=m.digest(p/'seal.json');m.atomic(outer/'receipt.json',receipt)
        state=m.read(outer/'lifecycle.json');state['receipt_sha256']=m.digest(outer/'receipt.json');m.atomic(outer/'lifecycle.json',state)
    elif damage=='guard_missing':(m.stage_home(run/'prepared','prepared')/'receipt.json').unlink()
    elif damage=='query_subset':report['queries']=report['queries'][:12]
    elif damage=='query_identity':report['queries'][1]['query_name']=m.QUERY_NAMES[0]
    elif damage=='truth_value':report['queries'][0]['groups'][0]['truth']+=1
    elif damage=='model_pickle_subset':report['model']['files_sha256'].pop('supplier.pkl')
    elif damage=='moment_sample_size':
        path=run/'sample_moments_native/moments.json';body=m.read(path);body['sample_rows']-=1;m.atomic(path,body)
    with pytest.raises((ValueError,OSError)):m.required_stage_artifacts(report,tmp_path,author)


def synthetic_publication(m,root,publish=True):
    """Only controller/inventory synthetic fixture; never accepted by verify_formal."""
    def place(relative,contents):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(contents);return path
    for relative in m.FROZEN:place(relative,(ROOT/relative).read_bytes())
    place('code/full_ssb_native_model.py',Path(m.__file__).read_bytes())
    launcher=place('code/full_ssb_native_model_run.py',(ROOT/'code/full_ssb_native_model_run.py').read_bytes())
    place(m.TRUTH_REL,(ROOT/m.TRUTH_REL).read_bytes())
    sqlparse={}
    for i in range(22):
        name='synthetic_%02d.py'%i;path=place('.venv/Lib/site-packages/sqlparse/'+name,b'# synthetic parser bytes\n');sqlparse[name]=m.digest(path)
    spn=place('.venv/Lib/site-packages/spn/synthetic.py',b'# synthetic spn bytes\n')
    python=place('.venv/Scripts/python.exe',b'SYNTHETIC NOT AN EXE')
    library=place('.venv/Lib/site-packages/synthetic.pyd',b'SYNTHETIC native bytes')
    base=place('.runtime/python/python38.dll',b'SYNTHETIC Python base DLL')
    base_exe=place('.runtime/python/python.exe',b'SYNTHETIC direct base EXE')
    config=place('.venv/pyvenv.cfg',b'home = synthetic\n')
    complete=dict(sources={'code/full_ssb_native_model.py':m.digest(root/'code/full_ssb_native_model.py')},
        sqlparse_sources=sqlparse,spflow_sources={'synthetic.py':m.digest(spn)})
    dependencies=dict(complete=complete,python_executable={'path':str(python),'sha256':m.digest(python)},
        frozen_sources=m.FROZEN,physical_native_libraries={library.relative_to(root).as_posix():m.digest(library)},
        python_base_native_files={base.relative_to(root).as_posix():m.digest(base),base_exe.relative_to(root).as_posix():m.digest(base_exe),config.relative_to(root).as_posix():m.digest(config)},
        python_base_executable=m.artifact_record(base_exe,root),
        actual_module_roots={'synthetic':{'path':spn.relative_to(root).as_posix(),'sha256':m.digest(spn)}})
    dependencies['operational_launcher']=m.artifact_record(launcher,root)
    generation=place(m.GEN_RESULT_REL,b'{"synthetic_only":true}\n');source_sha=m.digest(generation)
    m.atomic(generation.with_name(generation.stem+'_seal.json'),{'sha256':source_sha})
    import full_ssb_native_model_run as runner
    candidate=dict(schema='ssb_native_v2_model_plan_v1',status='CANDIDATE_REQUIRES_ROOT_REVIEW',executable=False,
        model=m.MODEL,dependencies=dependencies,source_receipt_sha256=source_sha,operational_policy=runner.OPERATIONAL_POLICY)
    plan=dict(candidate,status='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN',executable=True,root_reviewed_candidate_sha256=m.value_hash(candidate))
    binding_sha=m.value_hash(plan);report,author=synthetic_stages(m,root,binding_sha[:20],complete)
    report['inputs']['sample_rows']=report['actual_sample_rows']
    report['plan']=plan;report['source_receipt_sha256']=source_sha
    checkpoint=Path(report['directory'])/'core_truth_checkpoint.json';m.atomic(checkpoint,dict(source_receipt_sha256=source_sha))
    # Rebind the synthetic truth-checkpoint digest if its source SHA changed.
    ebinding=report['evaluation_binding'];ebinding['truth_checkpoint_sha256']=m.digest(checkpoint)
    for i,identity in enumerate(report['evaluation']['identities']):
        path=Path(report['evaluation_directory'])/('query_%02d.json'%i)
        m.atomic(path.with_suffix('.seal.json'),dict(binding=ebinding,sha256=m.digest(path)))
        identity['core_seal_sha256']=m.digest(path.with_suffix('.seal.json'))
    home=m.stage_home(Path(report['directory'])/'evaluation','evaluation');receipt=m.read(home/'receipt.json')
    receipt['result']=report['evaluation'];m.atomic(home/'receipt.json',receipt)
    state=m.read(home/'lifecycle.json');state['receipt_sha256']=m.digest(home/'receipt.json');m.atomic(home/'lifecycle.json',state)
    plan_path=root/m.OUTPUT_REL/'plans'/binding_sha[:20]/'plan.json';m.atomic(plan_path,plan)
    m.atomic(plan_path.with_suffix('.seal.json'),{'sha256':m.digest(plan_path)})
    report.update(status='PASS',stage='SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI',population_rows=m.N,
        plan_binding_sha256=binding_sha,plan_path=plan_path.relative_to(root).as_posix(),plan_file_sha256=m.digest(plan_path),
        adapter_source_sha256=m.digest(Path(m.__file__)))
    m.formal_transaction(Path(report['directory'])/'formal_control',m.formal_binding(report),lambda:report,
                         lambda result:m.required_stage_artifacts(result,root,author))
    if publish:m.publish_formal(report,root)
    return report


def test_synthetic_whole_formal_publication_and_read_only_inventory(tmp_path_factory,monkeypatch):
    tmp_path=tmp_path_factory.mktemp('p')
    m=module();report=synthetic_publication(m,tmp_path);before={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}
    records=m.verify_publication(report,tmp_path)
    assert len(records)>80 and len(records)==len({r['path'] for r in records})
    assert before=={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}
    # Synthetic publication shape is never a real-source acceptance loophole.
    with pytest.raises(ValueError,match='unreviewed'):m.verify_formal(tmp_path)


@pytest.mark.parametrize('damage',['omit','duplicate','extra','whole_formal_state','launcher_source'])
def test_self_resealed_publication_never_accepts_subset_or_incomplete_formal(tmp_path_factory,damage):
    tmp_path=tmp_path_factory.mktemp('p')
    m=module();report=synthetic_publication(m,tmp_path);run=Path(report['directory'])
    path=run/'verification_seal.json';seal=m.read(path)
    if damage=='omit':seal['artifacts']=[r for r in seal['artifacts'] if not r['path'].endswith('customer.hdflineorder.hdf')]
    elif damage=='duplicate':seal['artifacts'].append(seal['artifacts'][0])
    elif damage=='extra':seal['artifacts'].append({'path':'unexecuted_fake_query.json','bytes':1,'sha256':'0'*64})
    elif damage=='launcher_source':(tmp_path/'code/full_ssb_native_model_run.py').write_bytes(b'changed launcher, same path')
    else:
        m.atomic(run/'formal_control/lifecycle.json',dict(status='RUNNING',binding=m.formal_binding(report)))
    m.atomic(path,seal)
    with pytest.raises((ValueError,KeyError)):m.verify_publication(report,tmp_path)


def test_base_python_native_closure_detects_dll_and_cfg_changes(tmp_path):
    m=module();base=tmp_path/'.runtime/python';base.mkdir(parents=True);(base/'DLLs').mkdir()
    for name in ('python.exe','python38.dll','vcruntime140.dll'):(base/name).write_bytes(name.encode())
    (base/'DLLs/_ssl.pyd').write_bytes(b'ssl binary')
    env=tmp_path/'.venv';env.mkdir();(env/'pyvenv.cfg').write_bytes(b'home = local\n')
    before=m.base_python_files(base,env,base/'python.exe',tmp_path)
    assert len(before)==5
    (base/'python38.dll').write_bytes(b'changed binary, same version')
    assert m.base_python_files(base,env,base/'python.exe',tmp_path)!=before
    (env/'pyvenv.cfg').write_bytes(b'home = changed\n')
    assert m.base_python_files(base,env,base/'python.exe',tmp_path)!=before


def test_publication_failure_and_running_tail_taint_whole_formal(tmp_path_factory,monkeypatch):
    tmp_path=tmp_path_factory.mktemp('p')
    m=module();report=synthetic_publication(m,tmp_path);run=Path(report['directory'])
    # Leave a durable PUBLICATION RUNNING, as an abrupt process loss would.
    m.atomic(run/'publication_control/lifecycle.json',dict(status='RUNNING',kind='PUBLICATION',binding=m.publication_binding(report,tmp_path)))
    with pytest.raises(ValueError,match='TAINTED'):m.publish_formal(report,tmp_path)
    assert m.read(run/'formal_control/lifecycle.json')['status']=='TAINTED'
    assert m.read(run/'publication_control/lifecycle.json')['status']=='TAINTED'
    with pytest.raises(ValueError):m.verify_publication(report,tmp_path)


def test_scientific_stage_helper_is_also_closed_before_importing_model_stack():
    m=module()
    with pytest.raises(ValueError,match='closed'):m.execute_stages(None,None,None,None,None)


def test_fixed_runtime_tree_rejects_changed_and_self_subset_inventory(tmp_path):
    m=module();tree=tmp_path/'runtime';tree.mkdir();(tree/'a.dll').write_bytes(b'a');(tree/'b.exe').write_bytes(b'b')
    expected={p.name:m.digest(p) for p in tree.iterdir()};pin=m.value_hash(expected)
    assert len(m.verify_runtime_tree(tree,pin,2,tmp_path))==2
    (tree/'b.exe').unlink()
    with pytest.raises(ValueError):m.verify_runtime_tree(tree,pin,2,tmp_path)
    (tree/'b.exe').write_bytes(b'changed binary same filename')
    with pytest.raises(ValueError):m.verify_runtime_tree(tree,pin,2,tmp_path)


def test_obsolete_proposed_contract_aliases_are_not_accepted():
    m=module();body,truth,state,plan=contract(m)
    body['truth_groups']=body.pop('canonical_truth')
    with pytest.raises(ValueError,match='actual native'):m.validate_contract(body,truth,state,plan)


def test_external_runtime_artifacts_only_allow_two_exact_system32_imports(tmp_path):
    m=module();path=tmp_path.parent/'unapproved.dll';path.write_bytes(b'not system runtime')
    with pytest.raises(ValueError,match='external'):m.artifact_record(path,tmp_path)


def test_actual_sampling_descriptive_probability_is_mandatory():
    m=module();body,truth,state,plan=contract(m)
    body['sampling'].pop('effective_probability',None)
    with pytest.raises(ValueError,match='effective probability'):m.validate_contract(body,truth,state,plan)


def test_publication_writer_failure_persistently_taints_both_layers(tmp_path_factory,monkeypatch):
    tmp_path=tmp_path_factory.mktemp('p')
    m=module();report=synthetic_publication(m,tmp_path,publish=False);calls=[]
    def fail(*args):calls.append(1);raise RuntimeError('synthetic publication disk failure')
    monkeypatch.setattr(m,'write_publication',fail)
    with pytest.raises(RuntimeError,match='disk failure'):m.publish_formal(report,tmp_path)
    run=Path(report['directory'])
    assert m.read(run/'formal_control/lifecycle.json')['status']=='TAINTED'
    assert m.read(run/'publication_control/lifecycle.json')['status']=='TAINTED'
    with pytest.raises(ValueError):m.publish_formal(report,tmp_path)
    assert calls==[1]


@pytest.mark.parametrize('damage',[None,'final_running','final_report','final_review','stream_running','stream_plan','seconds','peak','missing_stderr'])
def test_native_outer_and_stream_guards_are_physical_required_inputs(tmp_path,damage):
    m=module();home=tmp_path/'output/full/ssb/native_v2/formal500/stream';home.mkdir(parents=True)
    plan={'binding':{'formal_review_plan_sha256':'d'*64},'ranges':[]}
    body={'plan':{'path':str(home/'plan.json')},'review_plan':{'path':'synthetic review plan'},
          'stream_seconds':3.5,'peak_native_working_set_bytes':123}
    report_sha='a'*64
    final=dict(status='FINAL_PASS',review_plan_sha256='d'*64,final_report_sha256=report_sha)
    stream=dict(status='STREAM_COMPLETE',plan_sha256=m.value_hash(plan),seconds=3.5,peak_native_working_set_bytes=123)
    if damage=='final_running':final['status']='RUNNING'
    elif damage=='final_report':final['final_report_sha256']='b'*64
    elif damage=='final_review':final['review_plan_sha256']='b'*64
    elif damage=='stream_running':stream['status']='RUNNING'
    elif damage=='stream_plan':stream['plan_sha256']='b'*64
    elif damage=='seconds':stream['seconds']=float('inf')
    elif damage=='peak':stream['peak_native_working_set_bytes']=-1
    m.atomic(home.parent/'lifecycle.json',final)
    if damage=='seconds':(home/'lifecycle.json').write_bytes(json.dumps(stream).encode())
    else:m.atomic(home/'lifecycle.json',stream)
    if damage!='missing_stderr':(home/'native.stderr.log').write_bytes(b'')
    final_descriptor=m.artifact_record(home.parent/'lifecycle.json',tmp_path);final_descriptor['path']=str(home.parent/'lifecycle.json')
    checked=dict(report_sha256=report_sha,review_plan=body['review_plan'],final_guard=final_descriptor)
    if damage is None:
        records=m.native_final_boundary(body,checked,plan,tmp_path)
        assert len(records)==3 and any(r['path'].endswith('native.stderr.log') for r in records)
    else:
        with pytest.raises((ValueError,OSError)):m.native_final_boundary(body,checked,plan,tmp_path)


def test_short_namespace_guard_temporary_paths_fit_and_write_on_real_root_length(tmp_path_factory):
    m=module();base=tmp_path_factory.getbasetemp()
    padded=base/('x'*max(1,len(str(ROOT))-len(str(base))-1));padded.mkdir(exist_ok=True)
    run=padded/m.OUTPUT_REL/'runs'/('a'*20)
    for stage,kind in [('prepared','prepared'),('model','model'),('evaluation','evaluation')]:
        home=m.stage_home(run/stage,kind);home.mkdir(parents=True)
        for name in ('lifecycle.json.tmp','receipt.json.tmp'):
            path=home/name
            assert len(str(path))<260
            path.write_bytes(b'PURE synthetic path gate\n')
            assert path.read_bytes()==b'PURE synthetic path gate\n'


def test_default_formal_acceptance_requires_successful_supervisor_even_after_validated_science(tmp_path_factory,monkeypatch):
    tmp_path=tmp_path_factory.mktemp('p');m=module();report=synthetic_publication(m,tmp_path)
    monkeypatch.setattr(m,'ROOT',tmp_path)
    for name in ('FINAL_RECEIPT_INTERFACE_FROZEN','GENERATOR_CLOSURE_INTERFACE_FROZEN','FORMAL_PUBLICATION_REVIEW_COMPLETE'):monkeypatch.setattr(m,name,True)
    monkeypatch.setattr(m,'verify_generation',lambda **kwargs:report['inputs'])
    monkeypatch.setattr(m,'dependency_snapshot',lambda:report['plan']['dependencies'])
    with pytest.raises((ValueError,OSError),match='supervisor|SUPERVISOR'):m.verify_formal(tmp_path)

