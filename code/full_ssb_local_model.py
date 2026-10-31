"""Local-population I/O and artifact contracts, disjoint from author success."""
import sys
sys.dont_write_bytecode=True
from contextlib import contextmanager
from fractions import Fraction
import math
import os
from pathlib import Path
import pickletools
import full_ssb_local_source as source

base=source.base
ROOT=source.ROOT
OUTPUT='output/full/ssb/local_sf500_models'
RESULT='output/full/results/ssb_local_sf500_model_aqp_ci.json'
PASS='PASS_LOCAL_SSB_SF500_MODEL_AQP_CI'
ERRORS='LOCAL_MODEL_QUERY_ERRORS_RECORDED'
API_PASS='PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH'
MODEL=base.MODEL
require=source.require
read=source.read
atomic=source.atomic
digest=source.digest
artifact=source.artifact
value_hash=source.value_hash


def validate_scope(report):
    require(report.get('status') in (PASS,ERRORS) and report.get('scope')==source.SCOPE
        and report.get('author_different_groups')==1713 and report.get('author_reproduction_complete') is False
        and report.get('full_paper_reproduction_complete') is False,'local result scope must preserve1713 author differences')
    old=report['original_mismatch'];inputs=report['inputs']
    require(old['path']==source.NATIVE_REPORT and old['sha256']==source.NATIVE_REPORT_SHA
        and inputs['status']==source.STATUS and inputs['scope']==source.SCOPE and inputs['different_author_groups']==1713,
        'local source must retain original MISMATCH, never author PASS')


@contextmanager
def local_output(core,directory,root=ROOT):
    require(os.environ.get('DEEPDB_SSB_LOCAL_WORKER')=='1','local I/O requires a fresh local worker')
    directory=Path(directory).resolve();home=(Path(root)/OUTPUT).resolve()
    require(home in directory.parents,'local-only output namespace required')
    original=core.OUTPUT;core.OUTPUT=directory
    try:yield
    finally:core.OUTPUT=original


def truth_projection(inputs):
    base.truth_map(inputs['canonical_truth'])
    aggregates={str(i):{} for i in range(13)}
    for r in inputs['canonical_truth']:aggregates[str(r['query_no'])]['\t'.join(r['group'])]=r['value']
    return dict(scope=source.SCOPE,rows=source.N,sample_rows=inputs['sample_rows'],aggregates=aggregates,
        source_receipt_sha256=inputs['receipt_sha256'],author_different_groups=1713)


def stage_artifacts(r,root=ROOT):
    """Local expected-truth contract; no author-provider swap or model unpickle."""
    validate_scope(r);root=Path(root).resolve();run=Path(r['directory']).resolve();records={}
    require((root/OUTPUT/'runs').resolve() in run.parents,'local model run namespace required')
    def add(path,sha=None):
        item=artifact(path,root);require(sha is None or item['sha256']==sha,'local stage artifact changed: '+item['path']);records[item['path']]=item;return item
    def guard(directory,kind):
        home=base.stage_home(directory,kind.lower());receipt=read(home/'receipt.json');life=read(home/'lifecycle.json')
        add(home/'receipt.json');add(home/'lifecycle.json')
        require(receipt['status']==life['status']=='PASS' and receipt['kind']==kind and receipt['binding']==life['binding']
            and life['receipt_sha256']==digest(home/'receipt.json') and receipt['binding']['dependencies']==r['plan']['dependencies']['environment']['complete']
            and receipt['binding']['guard_source_sha256']==base.FROZEN['code/full_ssb_guard.py'],'complete frozen local '+kind+' guard required')
        return receipt
    prepared=run/'prepared';pg=guard(prepared,'PREPARED');inputs=pg['result']['core_input_artifacts'];seal=read(prepared/'seal.json')
    add(prepared/'seal.json',pg['result']['core_seal_sha256'])
    require(inputs['prepared_files_sha256']==seal['files_sha256'],'local prepared seal/receipt differs')
    hdfs=set()
    for opcode,arg,_ in pickletools.genops((prepared/'meta_data.pkl').read_bytes()):
        if opcode.name in ('UNICODE','BINUNICODE','SHORT_BINUNICODE','BINUNICODE8') and isinstance(arg,str) and arg.endswith('.hdf') and Path(arg).is_absolute():
            p=Path(arg).resolve();require(p.parent==prepared.resolve(),'local metadata HDF path escapes');hdfs.add(p.name)
    require({t+'.hdf' for t in base.TABLES}<=hdfs and hdfs=={p.name for p in prepared.glob('*.hdf')}
        and set(seal['files_sha256'])==hdfs|{'meta_data.pkl','binding.json'},'complete local main/unmatched HDF required set differs')
    for name,sha in seal['files_sha256'].items():require(Path(name).name==name,'local prepared name escapes');add(prepared/name,sha)
    raw={Path(d['path']).name:d for d in r['inputs']['physical_artifacts']}
    require(set(inputs['raw_files'])==set(base.TABLES),'all five local raw input tables required')
    for t in base.TABLES:
        name='lineorder_sampled.csv' if t=='lineorder' else 'date.tbl' if t=='dwdate' else t+'.tbl';entry=inputs['raw_files'][t]
        require(name in raw and entry['sha256']==raw[name]['sha256'] and Path(entry['path']).resolve()==(root/raw[name]['path']).resolve(),'local prepared raw binding differs')
    directory=run/'model';model=r['model'];mg=guard(directory,'MODEL');add(directory/'model_guard.json');mguard=read(directory/'model_guard.json')
    require(mg['result']==model==read(directory/'model.json') and model['training_tables']==r['training_tables']
        and model['spn_count']==r['spn_count']==5 and model['model_path']==r['model_path']==str(directory/'ensemble_single.pkl'),'local model report/path differs')
    binding=model['binding'];require(all(binding[k]==MODEL[k] for k in ('samples_per_spn','seed','ensemble_strategy','rdc_threshold')),'fixed original local model parameters changed')
    pickle_names={t+'.pkl' for t in base.TABLES}|{'ensemble_single.pkl'}
    required=pickle_names|{t+'.json' for t in base.TABLES}|{'model.json','input_guard.json'}
    require(set(model['files_sha256'])==pickle_names=={p.name for p in directory.glob('*.pkl')}
        and set(mguard['model_files_sha256'])==required and mguard['binding']['inputs']==inputs
        and mguard['binding']['model_stage']==binding==read(directory/'input_guard.json')['binding']['model_stage']
        and read(directory/'input_guard.json')['binding']==mguard['binding'],'complete local model/input required set differs')
    for name,sha in mguard['model_files_sha256'].items():add(directory/name,sha)
    for name,sha in model['files_sha256'].items():require(digest(directory/name)==sha,'local model checkpoint changed')
    require(r['model_sha256']==model['files_sha256']['ensemble_single.pkl']
        and mg['binding']['prepared_outer_receipt_sha256']==digest(base.stage_home(prepared,'prepared')/'receipt.json'),'local model/prepared link differs')
    rows={v['table']:v for v in model['training_tables']}
    require(set(rows)==set(base.TABLES) and len(model['training_tables'])==5
        and all(v['actual_training_rows']==(2556 if t=='dwdate' else 1000000) for t,v in rows.items()),'actual local1M/table training rows differ')
    p=r['inputs']['probability'];normalizer=r['actual_sample_rows']/float(Fraction(p['numerator'],p['denominator']))
    require(r['actual_sample_rows']==source.SAMPLE_ROWS and math.isclose(rows['lineorder']['full_join_estimate'],normalizer,rel_tol=2e-15),'local learned fact length must preserve actual n/p')
    for t in base.TABLES:
        ck=read(directory/(t+'.json'));require(ck['binding']==binding and ck['sha256']==model['files_sha256'][t+'.pkl'] and ck['training']==rows[t],'local per-table checkpoint binding differs')
    moments=run/'sample_moments_native';moment=read(moments/'moments.json');ms=read(moments/'seal.json')
    for name,sha in [('moments.json',ms['sha256']),('moments.tsv',ms['tsv_sha256']),('seal.json',None),('process.json',None)]:add(moments/name,sha)
    require(moment['status']=='PASS' and moment['sample_rows']==ms['binding']['sample_rows']==r['actual_sample_rows'] and read(moments/'process.json')['returncode']==0,'local retained-sample moment binding differs')
    sqls=(root/base.SQL_REL).read_text().splitlines();require(digest(root/base.SQL_REL)==base.SQL_SHA and len(sqls)==len(moment['queries'])==13
        and [q['sql'] for q in moment['queries']]==sqls,'all13 exact local SQL identities required')
    build=moment['build'];stem='ci_'+build['binding']['source_sha256'][:16];helper=root/OUTPUT/'runtime/native'
    for suffix,sha in [('.cpp',build['binding']['source_sha256']),('.exe',build['executable_sha256']),('.json',None),('_build.json',None)]:add(helper/(stem+suffix),sha)
    require(read(helper/(stem+'.json'))==build and read(helper/(stem+'_build.json'))['returncode']==0,'local CI helper build differs')
    checkpoint=run/'core_truth_checkpoint.json';add(checkpoint)
    require(read(checkpoint)==truth_projection(r['inputs']),'local lossless truth projection changed')
    eg=guard(run/'evaluation','EVALUATION');e=r['evaluation'];eb=r['evaluation_binding'];edir=Path(r['evaluation_directory']).resolve()
    require(eg['result']==e and e['queries']==r['queries'] and e['binding']==eb and edir.parent==(run/'evaluation').resolve()
        and eg['binding']['model_outer_receipt_sha256']==digest(base.stage_home(directory,'model')/'receipt.json')
        and eg['binding']['model_sha256']==r['model_sha256'] and eg['binding']['truth_sha256']==digest(checkpoint),'local evaluation/source/model links differ')
    require(eb['confidence_sample_size']==r['actual_sample_rows'] and eb['truth_checkpoint_sha256']==digest(checkpoint)
        and eb['model_sha256']==r['model_sha256'] and eb['model_input_artifact_guard_sha256']==digest(directory/'model_guard.json') and eb['sql_sha256']==base.SQL_SHA,'local evaluation binding differs')
    require(len(r['queries'])==len(e['identities'])==13 and {p.name for p in edir.glob('query_*.json')}=={'query_%02d'%i+s for i in range(13) for s in ('.json','.seal.json')},'complete26 local query files required')
    truth=base.truth_map(r['inputs']['canonical_truth'])
    for i,(q,identity) in enumerate(zip(r['queries'],e['identities'])):
        path=edir/('query_%02d.json'%i);qs=path.with_suffix('.seal.json');add(path);add(qs)
        require((q['query_no'],q['query_name'],q['sql'])==(i,base.QUERY_NAMES[i],sqls[i]) and read(path)==q
            and read(qs)==dict(binding=eb,sha256=digest(path)) and identity==dict(query_no=i,query_name=base.QUERY_NAMES[i],exact_sql=sqls[i],global_binding=eb,result_sha256=digest(path),core_seal_sha256=digest(qs)), 'local original query index/name/SQL/receipt differs')
        fields={'key','status','truth','prediction','zero_truth','absolute_error','relative_error','model_interval','model_covers_truth','model_relative_half_width','sample_moments','reference_ci','released_ci_comparison'}
        keys=[tuple(str(x) for x in g['key']) for g in q['groups']]
        require(len(keys)==len(set(keys)) and all(fields<=set(g) and g['status'] in ('MATCHED','MISSING_MODEL_GROUP','EXTRA_MODEL_GROUP') for g in q['groups'])
            and isinstance(q['nonfinite_original_intervals'],list),'complete local group/CI/error states required')
        expected={k:v for (index,k),v in truth.items() if index==i};actual={tuple(str(x) for x in g['key']):g['truth'] for g in q['groups'] if g['status']!='EXTRA_MODEL_GROUP'}
        require(set(actual)==set(expected) and all(actual[k]==float(v) for k,v in expected.items()),'complete2059 LOCAL integer truth, never author substitution, required')
        require(q['missing_model_groups']==sum(g['status']=='MISSING_MODEL_GROUP' for g in q['groups']) and q['extra_model_groups']==sum(g['status']=='EXTRA_MODEL_GROUP' for g in q['groups'])
            and q['truth_groups']==sum(g['status']!='EXTRA_MODEL_GROUP' for g in q['groups']) and q['model_groups']==sum(g['status']!='MISSING_MODEL_GROUP' for g in q['groups']), 'local union group coverage differs')
    require(sum(q['truth_groups'] for q in r['queries'])==2059 and r['point_query_errors']==sum(bool(q['point_error']) for q in r['queries'])
        and r['ci_query_errors']==sum(bool(q['ci_error']) for q in r['queries']),'local query/truth/error totals differ')
    return list(records.values())


def execute_local_formal(plan,memory_approved=False):
    require(plan.get('scope')==source.SCOPE and plan.get('status')=='ROOT_REVIEWED_LOCAL_SSB_MODEL_PLAN' and plan.get('executable') is True,'reviewed local plan/scope required before science')
    return execute_reviewed(plan,memory_approved)


def dependency_snapshot(auxiliary_sources=None):
    auxiliary=dict(auxiliary_sources or {})
    require(set(auxiliary)<= {'code/full_ssb_local_replay.py'},'only explicitly frozen local replay may extend inference dependencies')
    for path,sha in auxiliary.items():require(digest(ROOT/path)==sha,'explicit local replay source changed')
    return dict(environment=base.dependency_snapshot(),local_sources=source.code_snapshot(),auxiliary_sources=auxiliary)


def formal_binding(r):
    return dict(scope=source.SCOPE,plan_binding_sha256=r['plan_binding_sha256'],source_receipt_sha256=r['source_receipt_sha256'],
        dependencies_sha256=value_hash(r['plan']['dependencies']),adapter_source_sha256=r['adapter_source_sha256'],original_mismatch_sha256=source.NATIVE_REPORT_SHA,author_different_groups=1713)


def publication_artifacts(r,root=ROOT):
    records={d['path']:d for d in stage_artifacts(r,root)};root=Path(root)
    def add(path,sha=None):
        d=artifact(path,root);require(sha is None or d['sha256']==sha,'local publication source changed: '+d['path']);records[d['path']]=d;return d
    for item in r['inputs']['physical_artifacts']:add(root/item['path'],item['sha256'])
    for key in ('verification','verification_seal','audit_receipt','audit_lifecycle','publication_receipt','publication_lifecycle'):
        d=r['inputs'][key];require(add(root/d['path'],d['sha256'])==d,'local source gate descriptor differs')
    require(r['source_receipt_sha256']==r['inputs']['verification']['sha256']==r['plan']['source_receipt_sha256'],'model must bind actual local source receipt')
    require(add(root/source.NATIVE_REPORT,source.NATIVE_REPORT_SHA)==r['original_mismatch'],'original author mismatch descriptor differs')
    dependencies=r['plan']['dependencies']
    for d in source.environment_artifacts(dependencies['environment'],root):records[d['path']]=d
    require(set(dependencies['local_sources'])==set(source.LOCAL_FILES),'complete three local adapter sources required')
    for path,sha in dict(dependencies['local_sources'],**dependencies['auxiliary_sources']).items():add(root/path,sha)
    require(r['adapter_source_sha256']==dependencies['local_sources']['code/full_ssb_local_model.py'],'local adapter/context source differs')
    path=root/r['plan_path'];add(path,r['plan_file_sha256']);add(path.with_suffix('.seal.json'))
    require(read(path)==r['plan'] and value_hash(r['plan'])==r['plan_binding_sha256']
        and read(path.with_suffix('.seal.json'))=={'sha256':r['plan_file_sha256']},'local reviewed plan/namespace differs')
    run=Path(r['directory']);home=run/'formal_control';receipt=read(home/'receipt.json');life=read(home/'lifecycle.json')
    add(home/'receipt.json');add(home/'lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='LOCAL_FORMAL' and life['receipt_sha256']==digest(home/'receipt.json')
        and receipt['binding']==life['binding']==formal_binding(r) and receipt['result']==r,'complete local whole FORMAL PASS required')
    add(run/'verification.json');add(root/RESULT)
    require(read(run/'verification.json')==read(root/RESULT)==r,'local published report differs')
    return [records[p] for p in sorted(records)]


def publication_binding(r):
    return dict(scope=source.SCOPE,formal_receipt_sha256=digest(Path(r['directory'])/'formal_control/receipt.json'),report_sha256=value_hash(r))


def publication_result(r,root=ROOT):
    return {key:digest(path) for key,path in [('verification_sha256',Path(r['directory'])/'verification.json'),
        ('seal_sha256',Path(r['directory'])/'verification_seal.json'),('published_result_sha256',Path(root)/RESULT)]}


def write_local_publication(r,root=ROOT):
    run=Path(r['directory']);require(not (Path(root)/RESULT).exists() and not (run/'verification.json').exists(),'local publication cannot replace existing result')
    atomic(run/'verification.json',r);atomic(Path(root)/RESULT,r)
    atomic(run/'verification_seal.json',dict(status='PASS_LOCAL_MODEL_PUBLICATION',scope=source.SCOPE,author_different_groups=1713,
        artifacts=publication_artifacts(r,root),dependencies_sha256=value_hash(r['plan']['dependencies']),source_receipt_sha256=r['source_receipt_sha256']))
    return publication_result(r,root)


def publish_local_model(r,root=ROOT):
    run=Path(r['directory']);formal=read(run/'formal_control/lifecycle.json')
    require(formal['status']=='PASS','local FORMAL PASS required before publication')
    def validate(result):
        verify_local_publication(r,root,require_publication=False);require(result==publication_result(r,root),'local publication links changed')
    try:return base.formal_transaction(run/'publication_control',publication_binding(r),lambda:write_local_publication(r,root),validate,kind='LOCAL_PUBLICATION')
    except BaseException as error:
        formal.update(status='TAINTED',reason='local publication failed: '+repr(error));atomic(run/'formal_control/lifecycle.json',formal);raise


def verify_local_publication(r,root=ROOT,require_publication=True):
    records=publication_artifacts(r,root);run=Path(r['directory']);seal=read(run/'verification_seal.json')
    require(seal==dict(status='PASS_LOCAL_MODEL_PUBLICATION',scope=source.SCOPE,author_different_groups=1713,artifacts=records,
        dependencies_sha256=value_hash(r['plan']['dependencies']),source_receipt_sha256=r['source_receipt_sha256']), 'complete local publication artifact set differs')
    if require_publication:
        home=run/'publication_control';receipt=read(home/'receipt.json');life=read(home/'lifecycle.json')
        require(receipt['status']==life['status']=='PASS' and receipt['kind']=='LOCAL_PUBLICATION' and life['receipt_sha256']==digest(home/'receipt.json')
            and receipt['binding']==life['binding']==publication_binding(r) and receipt['result']==publication_result(r,root), 'complete LOCAL_PUBLICATION PASS required')
        records.extend(artifact(p,root) for p in [home/'receipt.json',home/'lifecycle.json',run/'verification_seal.json'])
    return records


def execute_reviewed(plan,memory_approved):
    require(memory_approved,'root memory release required for local model')
    require(os.environ.get('DEEPDB_SSB_LOCAL_WORKER')=='1','fresh supervised local worker required')
    import full_ssb_local_model_run as runner
    runner.ops.verify_owned_job_membership(os.environ.get('DEEPDB_SSB_LOCAL_JOB'))
    require(all(os.environ.get(n)=='1' for n in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')),'original one-thread local model required')
    p=value_hash(plan);path=ROOT/OUTPUT/'plans'/p[:20]/'plan.json'
    require(runner.read_plan(path,digest(path))==plan,'reviewed local plan required')
    inputs=source.verify_local_source();require(inputs['receipt_sha256']==plan['source_receipt_sha256'],'local source gate differs from plan')
    require(plan['dependencies']==dependency_snapshot(plan['dependencies']['auxiliary_sources']),'local source/runtime dependencies changed')
    probe=runner.ops.operational_resources();resources=base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'])
    run=ROOT/OUTPUT/'runs'/p[:20];run.mkdir(parents=True,exist_ok=True)
    def produce():
        import full_ssb_guard as guard
        core=guard.core;schema=base.make_schema(read(ROOT/source.NATIVE_REPORT));checkpoint=run/'core_truth_checkpoint.json'
        atomic(checkpoint,truth_projection(inputs))
        with local_output(core,ROOT/OUTPUT/'runtime'):
            metadata=guard.guarded_prepare(schema,run/'prepared',chunk_rows=100000)
            expected=inputs['sample_rows']/float(Fraction(inputs['probability']['numerator'],inputs['probability']['denominator']))
            require(math.isclose(metadata['lineorder']['length'],expected,rel_tol=2e-15),'local prepared fact n/p changed')
            moments=core.sample_moments_native(schema,inputs['sample_rows'],run/'sample_moments_native')
            model=guard.guarded_train(schema,run/'prepared',1000000,run/'model')
            truth=core.population_truth_groups(checkpoint)
            evaluation=guard.guarded_evaluate(model,truth,moments['queries'],run/'evaluation')
        r=dict(status=PASS if not evaluation['point_query_errors'] and not evaluation['ci_query_errors'] else ERRORS,
            stage='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI',scope=source.SCOPE,author_different_groups=1713,author_reproduction_complete=False,
            full_paper_reproduction_complete=False,author_population_row_count_and_13_truths_match=False,author_full_row_byte_identity_proven=False,
            original_mismatch=inputs['original_mismatch'],directory=str(run),inputs=inputs,plan=plan,plan_path=path.relative_to(ROOT).as_posix(),
            plan_binding_sha256=p,plan_file_sha256=digest(path),source_receipt=source.RESULT,source_receipt_sha256=inputs['receipt_sha256'],
            population_rows=source.N,actual_sample_rows=inputs['sample_rows'],fact_normalizer=inputs['fact_normalizer'],resources_at_start=resources,
            prepared_directory=str(run/'prepared'),model_directory=str(run/'model'),model_path=model['model_path'],model_sha256=digest(model['model_path']),
            spn_count=model['spn_count'],training_tables=model['training_tables'],model=model,evaluation=evaluation,queries=evaluation['queries'],
            evaluation_binding=evaluation['binding'],evaluation_directory=evaluation['directory'],point_query_errors=evaluation['point_query_errors'],ci_query_errors=evaluation['ci_query_errors'],
            adapter_source_sha256=digest(__file__),core_truth_projection_sha256=digest(checkpoint),
            ci_scope='Original central90 and same actual local retained sample; original warnings retained',normalizer_scope='Original row-order/int64/pandas mean and retained n/p')
        return r
    def validate(r):
        require(inputs==source.verify_local_source(),'local physical source changed during model')
        require(plan['dependencies']==dependency_snapshot(plan['dependencies']['auxiliary_sources']),'local dependencies changed during model')
        stage_artifacts(r)
    binding=dict(scope=source.SCOPE,plan_binding_sha256=p,source_receipt_sha256=inputs['receipt_sha256'],dependencies_sha256=value_hash(plan['dependencies']),
        adapter_source_sha256=digest(__file__),original_mismatch_sha256=source.NATIVE_REPORT_SHA,author_different_groups=1713)
    with base.controller_lock(ROOT/OUTPUT/'controller.lock'):
        report=base.formal_transaction(run/'formal_control',binding,produce,validate,kind='LOCAL_FORMAL');publish_local_model(report)
    return report


def verify_local_model_publication(root=ROOT):
    root=Path(root);path=root/RESULT;require(path.is_file(),'completed local model publication missing')
    r=read(path);validate_scope(r)
    require(r['stage']=='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI' and r['population_rows']==source.N and r['actual_sample_rows']==source.SAMPLE_ROWS
        and r.get('author_population_row_count_and_13_truths_match') is False and r.get('author_full_row_byte_identity_proven') is False,'exact local stage/evidence scope required')
    require(r['inputs']==source.verify_local_source(root),'actual local source gate changed')
    import full_ssb_local_model_run as runner
    require(runner.read_plan(root/r['plan_path'],r['plan_file_sha256'],root)==r['plan'],'local reviewed plan differs')
    require(root==ROOT and r['plan']['dependencies']==dependency_snapshot(r['plan']['dependencies']['auxiliary_sources']),'local complete runtime/source snapshot changed')
    records=verify_local_publication(r,root);run=Path(r['directory'])
    return dict(status=API_PASS+('_WITH_ERRORS' if r['point_query_errors'] or r['ci_query_errors'] else ''),report=r,verification=artifact(run/'verification.json',root),
        verification_seal=artifact(run/'verification_seal.json',root),published_result=artifact(path,root),plan=artifact(root/r['plan_path'],root),
        formal_receipt=artifact(run/'formal_control/receipt.json',root),formal_lifecycle=artifact(run/'formal_control/lifecycle.json',root),artifacts=records,
        dependencies=r['plan']['dependencies'],model_path=r['model_path'],model_sha256=r['model_sha256'],sample_rows=source.SAMPLE_ROWS,population_rows=source.N,
        queries=r['queries'],evaluation_binding=r['evaluation_binding'],original_mismatch=r['original_mismatch'],author_different_groups=1713,scope=source.SCOPE,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,database_connected=False,training_executed=False,inference_executed=False,files_modified=False)


def verify_publication_and_supervisor(root=ROOT):
    result=verify_local_model_publication(root)
    import full_ssb_local_model_run as runner
    result['artifacts'].extend(runner.verify_supervisor(result['report'],root))
    require(len(result['artifacts'])==len({d['path'] for d in result['artifacts']}),'duplicate local science/operational artifact')
    return result


def verify_local_formal(root=ROOT):
    require((Path(root)/RESULT).is_file(),'completed local model publication missing')
    return verify_publication_and_supervisor(root)
