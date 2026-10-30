"""Independent local-only source gate; original author MISMATCH stays immutable."""
import sys
sys.dont_write_bytecode=True
from fractions import Fraction
from pathlib import Path
import math
import full_ssb_native_model as base

ROOT=base.ROOT
SCOPE='LOCAL_SSB_SF500'
N=3000028242
SAMPLE_ROWS=9996946
CUTOFF=61482997997673935
NATIVE_REPORT='output/full/results/ssb_native_v2.json'
NATIVE_REPORT_SHA='740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e'
DIAGNOSTIC='output/full/ssb/native_v2/author_gap_diagnostic.json'
DIAGNOSTIC_SHA='7ee4e56e98a2d6db6828634e0139c7bd132dd90631ddef9cc57563a52db2da9a'
DECISION='output/full/ssb/local_sf500_source/root_local_decision.json'
DECISION_SHA='cb2d7f0164570edc3e199a0875f92922b06b44978452f680e40130c76bf250ad'
OUTPUT='output/full/ssb/local_sf500_source'
RESULT='output/full/results/ssb_local_sf500_source.json'
STATUS='PASS_LOCAL_SOURCE_PHYSICAL_GATE_ONLY'
LOCAL_FILES=('code/full_ssb_local_source.py','code/full_ssb_local_model.py','code/full_ssb_local_model_run.py')
STRICT_PINS={'code/full_ssb_native_model.py':'7c50feb8d9248ae5f8bfc7f29aac39d86ecc687b38c407ca380fb3bef4558312',
 'code/full_ssb_native_model_run.py':'117b507a95c9333828e7d0069327d9771395e5fd42a62bc398862059a78d23f0'}
require=base.require
read=base.read
digest=base.digest
atomic=base.atomic
value_hash=base.value_hash
artifact=base.artifact_record


def validate_decision(d):
    expected=dict(schema='root_local_ssb_scope_decision_v1',status='ROOT_LOCAL_SCOPE_DECISION',scope=SCOPE,
        local_model_experiment_in_scope=True,source_audit_allowed_after_code_review=True,
        model_execution_authorized_by_this_record=False,model_execution_requires_separate_reviewed_plan_and_memory_release=True,
        generator_reexecution_authorized=False,author_gate_pass_authorized=False,strict_author_latches_must_remain_false=True,full_paper_complete=False,
        population_rows=N,actual_sample_rows=SAMPLE_ROWS,local_truth_groups=2059,matching_author_groups=346,different_author_groups=1713)
    require(all(type(d.get(k)) is type(v) and d[k]==v for k,v in expected.items()),'root local decision scope/authorization changed')
    require(d['original_report']['path']==NATIVE_REPORT and d['original_report']['sha256']==NATIVE_REPORT_SHA
        and d['author_gap_diagnostic']['path']==DIAGNOSTIC and d['author_gap_diagnostic']['sha256']==DIAGNOSTIC_SHA,'root decision original mismatch/diagnostic binding changed')
    return d


def strict_unchanged(root=ROOT):
    for path,sha in dict(STRICT_PINS,**base.NATIVE_API_SOURCE_PINS,**base.FROZEN).items():
        require(digest(Path(root)/path)==sha,'frozen strict/scientific/native source changed: '+path)
    require(not any((base.FINAL_RECEIPT_INTERFACE_FROZEN,base.GENERATOR_CLOSURE_INTERFACE_FROZEN,base.FORMAL_PUBLICATION_REVIEW_COMPLETE)),
        'author strict latches must remain false in local experiment')


def code_snapshot(root=ROOT):
    return {path:digest(Path(root)/path) for path in LOCAL_FILES}


def compare_author(local,author):
    left=base.truth_map(local);right=base.truth_map(author)
    require(set(left)==set(right),'local/author complete group identities differ')
    different=[dict(query_no=q,group=list(group),actual=left[(q,group)],author=right[(q,group)])
        for q,group in sorted(left) if left[(q,group)]!=right[(q,group)]]
    return dict(match=False,author_rows=N,actual_rows=N,row_difference=0,author_groups=2059,actual_groups=2059,missing=[],extra=[],different_values=different)


def validate_metadata(b,state,plan,author):
    require(b.get('schema')=='ssb_native_v2_final_v1' and b.get('status')=='MISMATCH' and b.get('complete') is False
        and b.get('paper_population_row_count_and_13_truths_match') is False and b.get('raw_snapshot_identity_claimed') is False,
        'original native MISMATCH must not be relabelled as author PASS')
    require(type(b['N']) is int and b['N']==N and type(b['population_rows']) is int and b['population_rows']==N
        and type(b['sample_rows']) is int and b['sample_rows']==SAMPLE_ROWS,'local exact population/sample counts differ')
    comparison=compare_author(b['canonical_truth'],author)
    require(comparison==b['author_comparison'] and len(comparison['different_values'])==1713
        and {d['query_no'] for d in comparison['different_values']}==set(range(6,13)), 'local1713 author gap changed')
    local=base.truth_map(b['canonical_truth']);different={(d['query_no'],tuple(d['group'])) for d in comparison['different_values']}
    require(different=={key for key in local if key[0]>=6},'all346 noncustomer groups must match and all1713 customer groups differ')
    s=b['sampling'];expected=dict(sample_seed=20261030,actual_cutoff=CUTOFF,probability_numerator=CUTOFF,probability_denominator=2**64,
        requested_numerator=3333,requested_denominator=1000000,normalizer_numerator=SAMPLE_ROWS*2**64,normalizer_denominator=CUTOFF,
        effective_probability=float(Fraction(CUTOFF,2**64)),normalizer_n_over_p=float(Fraction(SAMPLE_ROWS*2**64,CUTOFF)))
    require(s==expected and all(type(s[k]) is int for k in expected if k not in ('effective_probability','normalizer_n_over_p')),'local actual n/p/probability metadata changed')
    require(plan['schema']=='ssb_native_v2_stream_plan_v1' and state['schema']=='ssb_native_v2_checkpoint_v1','local checkpoint/plan schemas changed')
    binding=plan['binding'];copy=dict(binding);identity=copy.pop('source_id')
    require(identity==b['source_id']==value_hash(copy) and state['binding']==binding and binding['scale']=='500'
        and binding['total_orders']==750000000 and binding['shards']==4000 and binding['actual_cutoff']==CUTOFF
        and binding['sample_seed']==20261030 and binding['dimensions']==b['dimensions']
        and binding['formal_review_plan_sha256']==base.NATIVE_REVIEW_PLAN_SHA,'native local source/plan binding changed')
    require(state['complete'] is True and state['next_shard']==4000 and len(state['committed_shards'])==len(plan['ranges'])==4000,'local checkpoint unfinished')
    first=1
    for i,(record,order_range) in enumerate(zip(state['committed_shards'],plan['ranges'])):
        require(type(record['shard']) is int and record['shard']==i and record['first_order']==first and record['orders']>0
            and [record['first_order'],record['orders']]==order_range,'local shard/range gap or overlap')
        first+=record['orders']
    require(first==750000001 and state['rows']==N and state['sample_rows']==SAMPLE_ROWS
        and state['sample_bytes']==b['raw_sample']['bytes'] and state['sample_sha256']==b['raw_sample']['sha256']
        and state['aggregates']==b['canonical_truth'] and b['raw_sample']['rows']==SAMPLE_ROWS,'local checkpoint/final accounting differs')
    require(set(b['dimensions'])==set(base.DIMENSIONS)
        and all(b['dimensions'][name]['rows']==rows for name,(rows,_) in base.DIMENSIONS.items()),'all local dimensions required')
    p=Fraction(CUTOFF,2**64);normalizer=Fraction(SAMPLE_ROWS*2**64,CUTOFF)
    return dict(scope=SCOPE,population_rows=N,sample_rows=SAMPLE_ROWS,truth_groups=2059,source_id=identity,
        probability=dict(numerator=p.numerator,denominator=p.denominator),fact_normalizer=dict(numerator=normalizer.numerator,denominator=normalizer.denominator),
        author_truth_match=False,matching_author_groups=346,different_author_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False)


def environment_artifacts(dependencies,root=ROOT):
    """Explicit complete frozen environment roles; no report-provided subset."""
    paths=set(dependencies['complete']['sources'])|set(dependencies['frozen_sources'])|set(dependencies['physical_native_libraries'])|set(dependencies['python_base_native_files'])
    paths.update('.venv/Lib/site-packages/'+package+'/'+p for package,field in [('spn','spflow_sources'),('sqlparse','sqlparse_sources')] for p in dependencies['complete'][field])
    paths.update(e['path'] for e in dependencies['actual_module_roots'].values())
    paths.update(e['path'] for e in dependencies['generator_runtime']['artifacts'])
    paths.update([dependencies['operational_launcher']['path'],dependencies['python_executable']['path'],dependencies['python_base_executable']['path'],'code/full_ssb_native_model.py'])
    return [artifact(Path(root)/p,root) for p in sorted(paths)]


def collect_physical_source(root=ROOT):
    """Actual read-only audit. Called only through explicit reviewed commands."""
    root=Path(root).resolve();require(root==ROOT,'actual local source audit requires original project root');strict_unchanged(root)
    decision_path=root/DECISION
    require(digest(decision_path)==DECISION_SHA and read(decision_path.with_suffix('.seal.json'))=={'sha256':DECISION_SHA},'exact root local decision/seal required')
    d=validate_decision(read(decision_path));report_path=root/NATIVE_REPORT
    require(artifact(report_path,root)==d['original_report'] and digest(report_path)==NATIVE_REPORT_SHA,'original mismatch report changed')
    require(artifact(root/DIAGNOSTIC,root)==d['author_gap_diagnostic'],'author gap diagnostic changed')
    b=read(report_path);plan=read(b['plan']['path']);state=read(b['checkpoint']['path']);home=Path(b['plan']['path']).parent
    for path,sha in base.NATIVE_API_SOURCE_PINS.items():require(digest(root/path)==sha,'native readonly verifier source changed')
    import full_ssb_native_v2_formal as native
    import full_ssb_native_v2_stream as controller
    require(digest(root/'output/full/ssb/native_v2/readiness/readiness.json')==base.NATIVE_READINESS_SHA,'fixed native readiness changed')
    native.verify_review_plan(base.NATIVE_REVIEW_PLAN_SHA);controller.check_plan(plan,True)
    native.verify_dimensions(home.parent/'dimensions',base.NATIVE_REVIEW_PLAN_SHA)
    result=validate_metadata(b,state,plan,base.load_author_groups(root))
    controller.validate_restore(b['raw_sample']['path'],state,plan['binding'],home,plan['ranges'],truncate=False)
    expected=native.manifest_paths(plan,home,b['raw_sample']['path'])
    require(set(expected)==set(b['artifacts']),'independent exact native artifact set differs')
    records={}
    def add(path):
        item=artifact(path,root);records[item['path']]=item;return item
    for key,path in expected.items():
        actual=add(path);old=b['artifacts'][key]
        require(Path(old['path']).resolve()==Path(path).resolve() and actual['bytes']==old['bytes'] and actual['sha256']==old['sha256'],'native physical artifact changed: '+key)
    sample=base.native_descriptor(b['raw_sample'],root,17);base.verify_artifact(sample,root)
    for name,(_,width) in base.DIMENSIONS.items():base.verify_artifact(base.native_descriptor(b['dimensions'][name],root,width),root)
    outer=read(home.parent/'lifecycle.json');stream=read(home/'lifecycle.json')
    require(outer==dict(status='TAINTED',review_plan_sha256=base.NATIVE_REVIEW_PLAN_SHA,
        error="ValueError('Corrected final author comparison MISMATCH; preserved, no model may start')"),'only exact historical author rejection is eligible for independent local audit')
    require(stream['status']=='STREAM_COMPLETE' and stream['plan_sha256']==value_hash(plan)
        and type(stream['peak_native_working_set_bytes']) is int and stream['peak_native_working_set_bytes']>=0
        and type(stream['seconds']) in (int,float) and math.isfinite(stream['seconds']) and stream['seconds']>=0
        and stream['seconds']==b['stream_seconds'] and stream['peak_native_working_set_bytes']==b['peak_native_working_set_bytes'],'complete local stream/lifecycle timing differs')
    for path in [report_path,report_path.with_name(report_path.stem+'_seal.json'),decision_path,decision_path.with_suffix('.seal.json'),root/DIAGNOSTIC,
                 home.parent/'lifecycle.json',home/'lifecycle.json',home/'native.stderr.log']:add(path)
    require(read(report_path.with_name(report_path.stem+'_seal.json'))=={'sha256':NATIVE_REPORT_SHA},'original MISMATCH seal changed')
    dependencies=base.dependency_snapshot()
    for item in environment_artifacts(dependencies,root):records[item['path']]=item
    codes=code_snapshot(root)
    for path in codes:add(root/path)
    require(digest(report_path)==NATIVE_REPORT_SHA,'original mismatch changed during audit')
    result.update(schema='ssb_local_sf500_source_v1',status=STATUS,local_physical_gate_complete=True,
        original_report_status='MISMATCH',original_outer_status='TAINTED',original_mismatch=artifact(report_path,root),
        decision=artifact(decision_path,root),diagnostic=artifact(root/DIAGNOSTIC,root),canonical_truth=b['canonical_truth'],
        canonical_truth_sha256=value_hash(b['canonical_truth']),author_comparison=b['author_comparison'],sampling=b['sampling'],
        raw_sample=sample,dimensions=b['dimensions'],dependencies=dependencies,local_sources=codes,
        physical_artifacts=[records[k] for k in sorted(records)],evidence_scope='Existing LP64/SQLite gates at recorded scales plus complete local stream reductions; no new3B traversal or author raw-byte identity')
    return result


def audit_local_source(root_decision_sha256,reviewed_local_codes_sha256,root=ROOT):
    require(root_decision_sha256==DECISION_SHA,'exact root local decision required before audit')
    require(reviewed_local_codes_sha256==value_hash(code_snapshot(root)),'explicit matching local code review required before audit')
    binding=dict(scope=SCOPE,decision_sha256=DECISION_SHA,native_report_sha256=NATIVE_REPORT_SHA,local_codes_sha256=reviewed_local_codes_sha256)
    home=Path(root)/OUTPUT/'audits'/value_hash(binding)[:20]
    def validate(result):require(result==collect_physical_source(root),'local physical source changed')
    with base.controller_lock(Path(root)/OUTPUT/'controller.lock'):
        report=base.formal_transaction(home,binding,lambda:collect_physical_source(root),validate,kind='LOCAL_SOURCE_AUDIT')
        publish_source(report,home,root)
    return verify_local_source(root)


def source_publication_binding(report,home):
    return dict(scope=SCOPE,report_sha256=value_hash(report),audit_receipt_sha256=digest(Path(home)/'receipt.json'))


def source_publication_result(root=ROOT):
    return dict(report_sha256=digest(Path(root)/RESULT),seal_sha256=digest(Path(root)/RESULT.replace('.json','_seal.json')))


def write_source_publication(report,home,root=ROOT):
    target=Path(root)/RESULT;seal=Path(root)/RESULT.replace('.json','_seal.json')
    require(not target.exists() and not seal.exists(),'existing local source publication cannot be resealed')
    atomic(target,report)
    atomic(seal,dict(status=STATUS,sha256=digest(target),audit_receipt=artifact(Path(home)/'receipt.json',root),audit_lifecycle=artifact(Path(home)/'lifecycle.json',root)))
    return source_publication_result(root)


def publish_source(report,home,root=ROOT):
    home=Path(home);audit=read(home/'receipt.json');life=read(home/'lifecycle.json')
    require(audit['status']==life['status']=='PASS' and audit['result']==report
        and life['receipt_sha256']==digest(home/'receipt.json'),'LOCAL_SOURCE_AUDIT PASS required before publication')
    def validate(result):
        require(result==source_publication_result(root) and read(Path(root)/RESULT)==report,'local source publication differs')
    try:return base.formal_transaction(home/'publication_control',source_publication_binding(report,home),
        lambda:write_source_publication(report,home,root),validate,kind='LOCAL_SOURCE_PUBLICATION')
    except BaseException as error:
        life.update(status='TAINTED',reason='local source publication failed: '+repr(error));atomic(home/'lifecycle.json',life);raise


def verify_local_source(root=ROOT):
    path=Path(root)/RESULT;require(path.is_file(),'completed local source verification missing')
    report=read(path);seal=read(Path(root)/RESULT.replace('.json','_seal.json'))
    require(report.get('status')==STATUS and seal.get('status')==STATUS and seal['sha256']==digest(path),'local source report/seal status differs')
    for key in ('audit_receipt','audit_lifecycle'):
        require(artifact(Path(root)/seal[key]['path'],root)==seal[key],'local audit controller artifact changed')
    receipt=read(Path(root)/seal['audit_receipt']['path']);life=read(Path(root)/seal['audit_lifecycle']['path'])
    expected_binding=dict(scope=SCOPE,decision_sha256=DECISION_SHA,native_report_sha256=NATIVE_REPORT_SHA,local_codes_sha256=value_hash(report['local_sources']))
    expected_home=Path(root)/OUTPUT/'audits'/value_hash(expected_binding)[:20]
    require(set(report['local_sources'])==set(LOCAL_FILES) and receipt['binding']==expected_binding
        and (Path(root)/seal['audit_receipt']['path']).resolve()==(expected_home/'receipt.json').resolve()
        and (Path(root)/seal['audit_lifecycle']['path']).resolve()==(expected_home/'lifecycle.json').resolve(),'exact local audit binding/namespace required')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='LOCAL_SOURCE_AUDIT' and life['binding']==receipt['binding']
        and life['receipt_sha256']==seal['audit_receipt']['sha256'] and receipt['result']==report,'complete LOCAL_SOURCE_AUDIT PASS required')
    home=(Path(root)/seal['audit_receipt']['path']).parent;pub=home/'publication_control'
    pr=read(pub/'receipt.json');pl=read(pub/'lifecycle.json')
    require(pr['status']==pl['status']=='PASS' and pr['kind']=='LOCAL_SOURCE_PUBLICATION' and pl['receipt_sha256']==digest(pub/'receipt.json')
        and pr['binding']==pl['binding']==source_publication_binding(report,home) and pr['result']==source_publication_result(root), 'complete LOCAL_SOURCE_PUBLICATION PASS required')
    require(report==collect_physical_source(root),'current local source physical closure differs')
    result=dict(report);result.update(receipt_path=RESULT,receipt_sha256=digest(path),verification=artifact(path,root),
        verification_seal=artifact(Path(root)/RESULT.replace('.json','_seal.json'),root),audit_receipt=seal['audit_receipt'],audit_lifecycle=seal['audit_lifecycle'],
        publication_receipt=artifact(pub/'receipt.json',root),publication_lifecycle=artifact(pub/'lifecycle.json',root))
    return result
