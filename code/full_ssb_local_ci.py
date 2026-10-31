"""Separate local 10M CI experiment; frozen 1M bytes and author failure stay intact."""
import sys
sys.dont_write_bytecode=True
import ast
from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import os
import re
from pathlib import Path
import full_ssb_local_model as previous

source=previous.source
base=source.base
ROOT=source.ROOT
SCOPE='LOCAL_SSB_10M_CI'
STAGE='LOCAL_SSB_SF500_SINGLE_10M_CI'
OUTPUT='output/full/ssb/local_sf500_ci10m'
RESULT='output/full/results/ssb_local_sf500_ci10m.json'
PASS='PASS_LOCAL_SSB_SF500_10M_CI_WITH_AUTHOR_MISMATCH'
ERRORS='LOCAL_SSB_10M_CI_QUERY_ERRORS_RECORDED'
API_PASS='PASS_READ_ONLY_LOCAL_SSB_10M_CI_WITH_AUTHOR_MISMATCH'
PARAMETERS=dict(previous.MODEL,samples_per_spn=10000000)
MODEL=PARAMETERS
SOURCE_RECEIPT_SHA='75fef537963dcbc183a720f2abc1b47b6972550822ba4591dec8f8336183e712'
GOLDEN_RESULT='output/full/results/ssb_local_ci10m_cap_golden.json'
WINDOWS_HELPER='code/full_windows_fingerprint.py'
WINDOWS_HELPER_SHA='a9e9034efad01e258c521934aea43f0f405ff78c42caffb7841a73fd03d96784'
INFERENCE_PINS={'code/full_ssb_scoped_replay.py':'f2514ac1e35cfea892096a7c9c338ab7c3aad6d905b4b35bfe6025f9ebca200c',
    'code/full_ssb_local_ci_group_replay.py':'4b73cf6bed9bb001ec1bf289fadb6950bdd4f0c644e1837406eaef402b0a827c',
    'code/full_ssb_group_order.py':'48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'}
GROUP_ADAPTER='code/full_ssb_group_order.py'
EVALUATION_METADATA=dict(evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',group_order_adapter_sha256=INFERENCE_PINS[GROUP_ADAPTER])
PARENT_CANONICAL_RESULT='output/full/results/ssb_local_sf500_canonical_aqp_ci.json'
PARENT_PROVIDER='code/full_ssb_local_continuation.py'
PARENT_SCOPE='LOCAL_SSB_SF500_CANONICAL_CONTINUATION'
PARENT_STATUS='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH'
PARENT_PROTOCOL='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
PARENT_REVERSE_PATTERN='output/full/ssb/local_sf500_continuation/runs/[a-f0-9]{20}/reverse/verification.json'
PARENT_METADATA=dict(canonical_parent_scope=PARENT_SCOPE,canonical_parent_status=PARENT_STATUS,canonical_execution_protocol=PARENT_PROTOCOL,
    canonical_adopted_forward=True,canonical_forward_reexecuted=False)
PARENT_RESULT_SHA='da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82'
EXPECTED_ROWS=dict(lineorder=9996946,dwdate=2556,customer=10000000,part=1800000,supplier=1000000)
BUDGET_METADATA=dict(paper_figure11_training_budget_policy_applied=True,exact10000000_fact_training_rows_claimed=False)
OPERATIONAL_RESERVE_BYTES=2*2**30+64*2**20
MINIMUM_LAUNCH_MEMORY_BYTES=7*2**30
FILES=('code/full_ssb_local_ci.py','code/full_ssb_local_ci_run.py','code/full_ssb_local_stage_validation.py')
PRIOR_PINS=dict(source.STRICT_PINS,**{'code/full_ssb_local_source.py':'699f85ec4d24c326a7b491cd4cbf9c5746a98e7947d5b79db60200d08c0e3ca3',
    'code/full_ssb_local_model.py':'0b736cb30e7f1e93c66d2ac632c9b8a0ac0023595440c46b8d9215962184bced',
    'code/full_ssb_local_model_run.py':'fd676fb41780ae96074a08f2478a7cef9820b7c55a65717b9b8e28ea9545dee3'})
PARENT_CANONICAL_PINS={'code/full_ssb_local_canonical.py':'9c041ffc8ca40386ad9e3582fd81cb1f0e76fd3db1a337cb97bb686a521ff6b6',
    'code/full_ssb_local_canonical_run.py':'8d561253786e8acd68e03c3b89fce46c2655f04cdd0c4b34492b369a6d757636',
    'code/full_ssb_local_continuation.py':'7a1bf30793e0484482bda3548c9d65dc3c3732af286287e62a2a054fd5e15563',
    'code/full_ssb_local_continuation_run.py':'763c9c46ce34fa0b4b0e59fbeea4f43d081945b8d6e20b91dde0b91eb937c7a0',
    GROUP_ADAPTER:EVALUATION_METADATA['group_order_adapter_sha256'],
    'code/full_ssb_local_replay.py':'9c2211af6b6385944010e079eef2fbc1f1dae381ccd39590f4acef9479c98aac',
    'code/full_ssb_replay.py':'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab',
    'code/full_ssb_native_replay.py':'6c8de16e03a8ba20448121fd4659c092c668d4db0f7214b932a40bf20d30302d'}
require=source.require
read=source.read
atomic=source.atomic
digest=source.digest
artifact=source.artifact
value_hash=source.value_hash


@contextmanager
def native_platform():
    require(digest(ROOT/WINDOWS_HELPER)==WINDOWS_HELPER_SHA,'frozen native Windows adapter changed')
    receipt=ROOT/source.RESULT;require(digest(receipt)==SOURCE_RECEIPT_SHA,'exact accepted source platform reference changed')
    expected=read(receipt)['dependencies']['platform']
    from full_windows_fingerprint import verified_platform
    with verified_platform(expected,'AMD64') as proof:
        require(proof['helper_sha256']==WINDOWS_HELPER_SHA and proof['subprocess_executed'] is False,'native platform proof differs');yield proof


def native_boundary(function):
    @wraps(function)
    def checked(*args,**kwargs):
        with native_platform():return function(*args,**kwargs)
    return checked


def original_training_source():
    path=ROOT/'code/full_ssb_model.py';require(digest(path)==base.FROZEN['code/full_ssb_model.py'],'frozen cap source changed')
    raw=path.read_text(encoding='utf-8');nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='train_single_models']
    require(len(nodes)==1,'exact frozen training function required');return ast.get_source_segment(raw,nodes[0])+'\n'


def result_path(kind):
    require(kind in ('GOLDEN','FORMAL'),'known CI publication kind required');return GOLDEN_RESULT if kind=='GOLDEN' else RESULT


def adapt_training_source(raw):
    old='100<=sample_cap<=1000000';new='100<=sample_cap<=10000000'
    require(raw==original_training_source() and raw.count(old)==1,'exact frozen source and one engineering-cap comparison required')
    changed=raw.replace(old,new)
    return changed,dict(frozen_core_sha256=base.FROZEN['code/full_ssb_model.py'],adapter_source_sha256=digest(__file__),replacement_count=1,
        original_source_sha256=hashlib.sha256(raw.encode()).hexdigest(),adapted_source_sha256=hashlib.sha256(changed.encode()).hexdigest(),
        old_comparison=old,new_comparison=new,scope='Only cap admissibility; original sampler/learn/checkpoint/RNG unchanged')


@contextmanager
def runtime_cap_adapter(core,namespace=None):
    require(os.environ.get('DEEPDB_SSB_LOCAL_CI_WORKER')=='1','fresh dedicated10M CI worker required')
    changed,binding=adapt_training_source(original_training_source());original=core.train_single_models
    globals_copy=dict(original.__globals__ if namespace is None else namespace)
    exec(compile(changed,'<sealed-local-10m-cap>','exec'),globals_copy)
    core.train_single_models=globals_copy['train_single_models']
    try:yield binding
    finally:core.train_single_models=original


@contextmanager
def canonical_evaluation():
    require(digest(ROOT/GROUP_ADAPTER)==EVALUATION_METADATA['group_order_adapter_sha256'],'frozen canonical evaluation adapter changed')
    import full_ssb_group_order as adapter
    require(Path(adapter.__file__).resolve()==ROOT/GROUP_ADAPTER,'canonical evaluation adapter loaded from a different path')
    with adapter.canonical_group_order():yield


def run_golden(reviewed_codes_sha256,memory_approved=False):
    require(memory_approved,'separate reviewed golden memory release required')
    raise ValueError('Use root-reviewed GOLDEN plan through the owned supervisor')


def execute_formal(plan,memory_approved=False):
    require(memory_approved and plan.get('status')=='ROOT_REVIEWED_LOCAL_SSB_10M_CI_PLAN' and plan.get('scope')==SCOPE,'separate reviewed10M plan and memory required')
    return execute_reviewed(plan)


def validation_config():
    return dict(scope=SCOPE,output=OUTPUT,parameters=PARAMETERS,expected_rows=EXPECTED_ROWS,statuses=[PASS,ERRORS],**EVALUATION_METADATA,**PARENT_METADATA)


def code_snapshot():
    for path,sha in PRIOR_PINS.items():require(digest(ROOT/path)==sha,'frozen prior provider changed: '+path)
    source.strict_unchanged();return {path:digest(ROOT/path) for path in FILES}


def validate_lineage_headers(formal,canonical):
    require(formal.get('status')==previous.API_PASS and formal.get('scope')==source.SCOPE and formal.get('sample_rows')==source.SAMPLE_ROWS
        and formal.get('population_rows')==source.N and formal.get('author_different_groups')==1713 and formal.get('author_reproduction_complete') is False
        and formal.get('full_paper_reproduction_complete') is False and formal['report']['plan']['model']==previous.MODEL,'complete accepted1M formal prerequisite required')
    require(canonical.get('status')==PARENT_STATUS and canonical.get('scope')==PARENT_SCOPE and canonical.get('execution_protocol')==PARENT_PROTOCOL and canonical.get('sample_rows')==source.SAMPLE_ROWS
        and canonical.get('population_rows')==source.N and canonical.get('author_different_groups')==1713
        and canonical.get('author_reproduction_complete') is False and canonical.get('full_paper_reproduction_complete') is False
        and canonical.get('historical_reverse_accepted') is False
        and canonical.get('variant')=='CANONICAL_PAIRED_DECODED_GROUP_ORDER'
        and all(canonical.get(k)==v for k,v in EVALUATION_METADATA.items()),'complete successful continuation1M evaluation prerequisite required')
    require(formal.get('proof_method')=='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL'
        and canonical['parent_formal']==formal['published_result'] and canonical['published_result']['path']==PARENT_CANONICAL_RESULT
        and all(canonical[k]==formal[k] for k in ('model_path','model_sha256')),'canonical delegated original formal identity differs')
    r=canonical['report']
    require(r.get('status')=='PASS_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_AQP_CI' and r.get('stage')=='LOCAL_SSB_SF500_CANONICAL_CONTINUATION_1M_AQP_CI'
        and r.get('scope')==PARENT_SCOPE and r.get('execution_protocol')==PARENT_PROTOCOL and r.get('variant')==canonical['variant']
        and r.get('adopted_forward') is True and all(r.get(k) is False for k in ('forward_reexecuted','preparation_executed','training_executed','moments_executed','historical_result_changed'))
        and all(r.get(k)==v for k,v in EVALUATION_METADATA.items()) and all(r[k]==canonical[k] for k in ('parent_formal','forward','reverse')),
        'exact adopted-forward/fresh-reverse continuation report required')
    require(re.fullmatch(PARENT_REVERSE_PATTERN,canonical['reverse']['path']) is not None
        and re.fullmatch('output/full/ssb/local_sf500_canonical/runs/[a-f0-9]{20}/forward/verification.json',canonical['forward']['path']) is not None,
        'old accepted forward and new continuation reverse namespaces required')
    require(type(formal.get('artifacts')) is list and bool(formal['artifacts']) and type(formal.get('dependencies')) is dict
        and all(k in formal for k in ('report','published_result','verification','verification_seal','evaluation_binding','original_mismatch')),
        'complete direct original formal parent_snapshot required, not digest-only proof')


def lineage_snapshot(full):
    result={key:value for key,value in full.items() if key not in ('inputs','artifacts','prior_dependencies')}
    result.update(inputs_sha256=value_hash(full['inputs']),artifacts_sha256=value_hash(full['artifacts']),prior_dependencies_sha256=value_hash(full['prior_dependencies']))
    return result


def inherited_extras(full):
    raw={d['path'] for d in full['inputs']['physical_artifacts']};return [d for d in full['artifacts'] if d['path'] not in raw]


def golden_snapshot(checked):
    return dict(status=checked['status'],published_result=checked['published_result'],verification=checked['verification'],verification_seal=checked['verification_seal'],artifacts_sha256=value_hash(checked['artifacts']))


def prepared_shapes(report):
    """Only HDF metadata is opened; no frame/sample/moments are recomputed."""
    import pandas as pd
    shapes={};directory=Path(report['prepared_directory'])
    for table in base.TABLES:
        path=directory/(table+'.hdf')
        with pd.HDFStore(str(path),mode='r') as store:
            storer=store.get_storer('df');columns=list(storer.non_index_axes[0][1]);rows=int(storer.nrows)
            shapes[table]=dict(hdf_rows=rows,hdf_columns=columns,storage_dtype=str(storer.table.dtype),
                actual_training_columns=next(v['columns'] for v in report['training_tables'] if v['table']==table),target_training_rows=EXPECTED_ROWS[table])
    require(shapes['lineorder']['hdf_rows']==9996946 and shapes['customer']['hdf_rows']==15000000,'actual reused HDF rows differ')
    return shapes


def _verified_parent_canonical(root):
    require(Path(root).resolve()==ROOT,'real1M canonical verifier requires original root')
    for path,sha in dict(PRIOR_PINS,**PARENT_CANONICAL_PINS).items():
        require(digest(ROOT/path)==sha,'frozen delegated parent verifier pin changed: '+path)
    import full_ssb_local_continuation as canonical
    require(Path(canonical.__file__).resolve()==ROOT/PARENT_PROVIDER,'delegated frozen continuation module loaded from a different path')
    return canonical.verify_canonical()


def _read_delegated_parent(canonical,root):
    """Inherit canonical's direct frozen formal proof, never certify the failed9c reverse."""
    snap=canonical['parent_snapshot'];validate_lineage_headers(snap,canonical)
    require((Path(root)/canonical['reverse']['path']).resolve()==(Path(canonical['report']['directory'])/'reverse/verification.json').resolve(),'continuation reverse report/directory alias differs')
    d=snap['published_result'];path=Path(root)/previous.RESULT
    require(set(d)=={'path','bytes','sha256'} and d['path']==previous.RESULT and d['sha256']==PARENT_RESULT_SHA
        and type(d['bytes']) is int and d['bytes']>0,'exact delegated parent publication descriptor required')
    raw=path.read_bytes();require(len(raw)==d['bytes'] and hashlib.sha256(raw).hexdigest()==d['sha256'],'delegated parent publication physical bytes/SHA differ')
    r=json.loads(raw)
    require(r.get('status')==previous.PASS and r.get('stage')=='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI' and r.get('scope')==source.SCOPE
        and r.get('population_rows')==source.N and r.get('actual_sample_rows')==source.SAMPLE_ROWS and r.get('author_different_groups')==1713
        and all(r.get(k) is False for k in ('author_reproduction_complete','full_paper_reproduction_complete','author_population_row_count_and_13_truths_match','author_full_row_byte_identity_proven'))
        and r.get('point_query_errors')==r.get('ci_query_errors')==0 and r['plan']['model']==previous.MODEL,'delegated successful1M report fields differ')
    require(r==snap['report'] and r['plan']['dependencies']==snap['dependencies'] and all(r[k]==snap[k] for k in ('model_path','model_sha256','evaluation_binding','original_mismatch'))
        and r['inputs']['receipt_sha256']==SOURCE_RECEIPT_SHA and r['original_mismatch']['path']==source.NATIVE_REPORT
        and r['original_mismatch']['sha256']==source.NATIVE_REPORT_SHA,'delegated1M report/source snapshot binding differs')
    return snap,r


@native_boundary
def collect_lineage(root=ROOT):
    root=Path(root);canonical=_verified_parent_canonical(root);formal,r=_read_delegated_parent(canonical,root)
    records={}
    for group in (formal['artifacts'],canonical['artifacts']):
        require(type(group) is list and bool(group) and len(group)==len({d['path'] for d in group}),'nonempty unique complete original/continuation closure required')
        for d in group:
            require(d['path'] not in records or records[d['path']]==d,'conflicting original/continuation artifact alias');records[d['path']]=d
    require(read(root/canonical['published_result']['path'])==canonical['report'] and canonical['dependencies']==canonical['report']['plan'],'complete physical continuation report/plan alias differs')
    for key in ('accepted_forward_artifacts','retained_failure_provenance','worker_artifacts'):
        required=canonical['report']['plan'][key]
        require(type(required) is list and bool(required) and len(required)==len({d['path'] for d in required})
            and all(records.get(d['path'])==d for d in required),'complete consumed original-forward/fresh-reverse control closure missing: '+key)
    for path,sha in dict(PRIOR_PINS,**PARENT_CANONICAL_PINS).items():
        d=artifact(root/path,root);require(d['sha256']==sha,'delegated parent source changed after verification');records[d['path']]=d
    for d in (formal['published_result'],formal['verification'],formal['verification_seal'],canonical['published_result'],canonical['verification'],canonical['verification_seal'],canonical['forward'],canonical['reverse']):
        require(records.get(d['path'])==d and artifact(root/d['path'],root)==d,'complete accepted canonical lineage descriptor absent/changed')
    monitor=read(Path(r['directory'])/'supervisor_control/monitor.json')
    return dict(parent_formal=formal['published_result'],formal_verification=formal['verification'],formal_seal=formal['verification_seal'],
        parent_canonical=canonical['published_result'],parent_reverse=canonical['reverse'],canonical_verification=canonical['verification'],canonical_seal=canonical['verification_seal'],
        reverse=canonical['reverse'],parent_forward=canonical['forward'],
        inputs=r['inputs'],prepared_directory=r['prepared_directory'],moments_directory=str(Path(r['directory'])/'sample_moments_native'),
        moments_helper_directory=str(root/previous.OUTPUT/'runtime/native'),truth_projection_path=str(Path(r['directory'])/'core_truth_checkpoint.json'),
        delegated_formal_proof=dict(method='Frozen continuation.verify_canonical -> parent_snapshot -> direct complete previous.verify_local_formal',
            frozen_sources=dict(PRIOR_PINS,**PARENT_CANONICAL_PINS),published_result=formal['published_result'],canonical_result=canonical['published_result'],direct_formal_reexecuted=False),
        prior_dependencies=formal['dependencies'],prior_peak_owned_rss_bytes=monitor['peak_owned_rss_bytes'],actual_prepared_shapes=prepared_shapes(r),
        artifacts=[records[p] for p in sorted(records)],author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        historical_reverse_accepted=False,**EVALUATION_METADATA,**PARENT_METADATA)


@native_boundary
def dependency_snapshot(auxiliary_sources=None):
    auxiliary=validate_auxiliary_sources(auxiliary_sources)
    import full_ssb_local_stage_validation as stages
    import full_ssb_local_ci_run as runner
    with native_platform() as proof:
        return dict(environment=base.dependency_snapshot(),prior_provider_sources=PRIOR_PINS,delegated_parent_sources=PARENT_CANONICAL_PINS,ci_sources=code_snapshot(),auxiliary_sources=auxiliary,
            runtime_cap=adapt_training_source(original_training_source())[1],stage_validation=stages.binding(validation_config()),operational_capsule=runner.capsule_binding(),
            windows_fingerprint=dict(adapter=artifact(ROOT/WINDOWS_HELPER),proof=proof),**EVALUATION_METADATA,**PARENT_METADATA)


def validate_auxiliary_sources(auxiliary_sources):
    auxiliary=dict(auxiliary_sources or {})
    require(set(auxiliary)<=set(INFERENCE_PINS) and all(INFERENCE_PINS[p]==sha and digest(ROOT/p)==sha for p,sha in auxiliary.items()),'only explicit matching root-frozen CI replay sources may extend dependencies')
    return auxiliary


def formal_binding(r):
    return dict(scope=SCOPE,kind=r['kind'],plan_binding_sha256=r['plan_binding_sha256'],source_receipt_sha256=SOURCE_RECEIPT_SHA,
        dependencies_sha256=value_hash(r['plan']['dependencies']),runtime_cap_sha256=value_hash(r['runtime_cap']),author_different_groups=1713)


def validate_reuse(r):
    require(all(r[key]==r['lineage'][key] for key in ('prepared_directory','moments_directory','moments_helper_directory','truth_projection_path'))
        and value_hash(r['inputs'])==r['lineage']['inputs_sha256']
        and r['source_receipt_sha256']==r['inputs']['receipt_sha256']==SOURCE_RECEIPT_SHA,'only actual accepted1M prepared/moments/truth inputs may be reused')


def dependency_artifacts(r,root=ROOT):
    records={d['path']:d for d in r['inputs']['physical_artifacts']+r['inherited_artifacts']};root=Path(root)
    require(value_hash([records[p] for p in sorted(records)])==r['lineage']['artifacts_sha256'],'complete inherited1M required artifact set differs')
    for path,item in list(records.items()):require(artifact(root/path,root)==item,'inherited1M physical descriptor changed')
    for item in r.get('golden_artifacts',[]):
        require(artifact(root/item['path'],root)==item,'prior scientific golden dependency changed');records[item['path']]=item
    deps=r['plan']['dependencies']
    for d in source.environment_artifacts(deps['environment'],root):records[d['path']]=d
    require(deps['prior_provider_sources']==PRIOR_PINS and deps['delegated_parent_sources']==PARENT_CANONICAL_PINS and set(deps['ci_sources'])==set(FILES)
        and all(deps.get(k)==v for k,v in EVALUATION_METADATA.items()) and all(type(deps.get(k)) is type(v) and deps[k]==v for k,v in PARENT_METADATA.items()),'complete prior/new continuation provider source sets required')
    for path,sha in {**PRIOR_PINS,**PARENT_CANONICAL_PINS,**deps['ci_sources'],**deps['auxiliary_sources']}.items():
        d=artifact(root/path,root);require(d['sha256']==sha,'10M closure source changed');records[d['path']]=d
    helper=artifact(root/WINDOWS_HELPER,root);require(helper==deps['windows_fingerprint']['adapter'] and helper['sha256']==WINDOWS_HELPER_SHA,'physical native fingerprint adapter differs');records[helper['path']]=helper
    require(r['runtime_cap']==deps['runtime_cap']==adapt_training_source(original_training_source())[1],'executed cap adapter binding changed')
    if r['kind']=='FORMAL':
        import full_ssb_local_stage_validation as stages
        require(r['validation_binding']==deps['stage_validation']==stages.binding(validation_config()),'configured required-set source changed')
        for key in ('parent_formal','parent_reverse','parent_canonical'):
            item=r['lineage'][key];require(item['path'] in records and records[item['path']]==item,'actual complete1M lineage descriptors required')
    return list(records.values())


def publication_artifacts(r,root=ROOT):
    root=Path(root);run=Path(r['directory']);kind=r['kind']
    if kind=='FORMAL':
        validate_reuse(r)
        import full_ssb_local_stage_validation as stages
        records={d['path']:d for d in stages.validate(r,validation_config(),root)}
    else:records={d['path']:d for d in golden_artifacts(r,root)}
    def add(path,sha=None):
        d=artifact(path,root);require(sha is None or d['sha256']==sha,'10M publication physical artifact changed');records[d['path']]=d;return d
    for d in dependency_artifacts(r,root):records[d['path']]=d
    path=root/r['plan_path'];add(path,r['plan_file_sha256']);add(path.with_suffix('.seal.json'))
    require(read(path)==r['plan'] and value_hash(r['plan'])==r['plan_binding_sha256'] and read(path.with_suffix('.seal.json'))=={'sha256':r['plan_file_sha256']},'10M plan/receipt binding differs')
    home=run/'formal_control';receipt=read(home/'receipt.json');life=read(home/'lifecycle.json');add(home/'receipt.json');add(home/'lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='LOCAL_CI_'+kind and life['receipt_sha256']==digest(home/'receipt.json')
        and life['binding']==receipt['binding']==formal_binding(r) and receipt['result']==r,'whole10M stage FORMAL PASS required')
    add(run/'verification.json');add(root/result_path(kind))
    require(read(run/'verification.json')==read(root/result_path(kind))==r,'10M published result differs')
    return [records[p] for p in sorted(records)]


def publication_binding(r):return dict(scope=SCOPE,report_sha256=value_hash(r),formal_receipt_sha256=digest(Path(r['directory'])/'formal_control/receipt.json'))


def publication_result(r,root=ROOT):
    run=Path(r['directory']);return dict(published_result_sha256=digest(Path(root)/result_path(r['kind'])),verification_sha256=digest(run/'verification.json'),seal_sha256=digest(run/'verification_seal.json'))


def write_publication(r,root=ROOT):
    run=Path(r['directory']);target=Path(root)/result_path(r['kind']);require(not target.exists() and not (run/'verification.json').exists(),'10M scientific publication cannot replace existing result')
    atomic(run/'verification.json',r);atomic(target,r)
    atomic(run/'verification_seal.json',dict(status='PASS_LOCAL_CI_PUBLICATION',scope=SCOPE,kind=r['kind'],artifacts=publication_artifacts(r,root)))
    return publication_result(r,root)


def publish(r,root=ROOT):
    home=Path(r['directory']);life=read(home/'formal_control/lifecycle.json');require(life['status']=='PASS','10M whole FORMAL PASS required before publication')
    def validate(result):verify_publication(r,root,require_publication=False);require(result==publication_result(r,root),'10M publication result links differ')
    try:return base.formal_transaction(home/'publication_control',publication_binding(r),lambda:write_publication(r,root),validate,kind='LOCAL_CI_PUBLICATION')
    except BaseException as error:
        life.update(status='TAINTED',reason='10M publication failed: '+repr(error));atomic(home/'formal_control/lifecycle.json',life);raise


def verify_publication(r,root=ROOT,require_publication=True):
    home=Path(r['directory']);records=publication_artifacts(r,root)
    require(read(home/'verification_seal.json')==dict(status='PASS_LOCAL_CI_PUBLICATION',scope=SCOPE,kind=r['kind'],artifacts=records),'complete10M publication required set differs')
    if require_publication:
        pub=home/'publication_control';receipt=read(pub/'receipt.json');life=read(pub/'lifecycle.json')
        require(receipt['status']==life['status']=='PASS' and receipt['kind']=='LOCAL_CI_PUBLICATION' and life['receipt_sha256']==digest(pub/'receipt.json')
            and life['binding']==receipt['binding']==publication_binding(r) and receipt['result']==publication_result(r,root),'complete10M PUBLICATION PASS required')
        records.extend(artifact(p,root) for p in (pub/'receipt.json',pub/'lifecycle.json',home/'verification_seal.json'))
    return records


def require_worker(plan):
    require(os.environ.get('DEEPDB_SSB_LOCAL_CI_WORKER')=='1','fresh reviewed CI worker required')
    import full_ssb_local_ci_run as runner
    runner.ops.verify_owned_job_membership(os.environ.get('DEEPDB_SSB_LOCAL_CI_JOB'))
    require(all(os.environ.get(k)=='1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')),'original one-thread CI execution required')
    key=value_hash(plan);path=ROOT/OUTPUT/'plans'/key[:20]/'plan.json'
    require(runner.read_plan(path,digest(path))==plan and plan['reviewed_codes_sha256']==value_hash(code_snapshot()),'reviewed actual10M plan/code set required')
    require(plan['dependencies']==dependency_snapshot(plan['dependencies']['auxiliary_sources']),'10M execution dependency closure changed')
    return key,path


def execute_worker(plan):
    if plan['kind']=='GOLDEN':return execute_golden(plan['reviewed_codes_sha256'],plan)
    return execute_formal(plan,memory_approved=True)


@native_boundary
def execute_reviewed(plan):
    key,path=require_worker(plan);require(plan['kind']=='FORMAL','formal10M plan required');full,golden=_verify_prerequisites('FORMAL');lineage=lineage_snapshot(full)
    require(plan['lineage']==lineage and plan['golden']==golden_snapshot(golden),'complete1M/golden prerequisites changed')
    inputs=full['inputs'];require(inputs['receipt_sha256']==SOURCE_RECEIPT_SHA,'exact accepted local source receipt required')
    import full_ssb_local_ci_run as runner
    probe=runner.ops.operational_resources();resources=base.check_resources(probe['free_disk_bytes'],probe['available_memory_bytes'],probe['existing_ssb_bytes'],additional_bytes=OPERATIONAL_RESERVE_BYTES)
    run=ROOT/OUTPUT/'runs'/key[:20]
    def produce():
        import full_ssb_guard as guard
        core=guard.core;schema=base.make_schema(read(ROOT/source.NATIVE_REPORT));moments=read(Path(lineage['moments_directory'])/'moments.json')
        # No preparation, native moments invocation or1M model adoption occurs.
        with runtime_cap_adapter(core) as cap:
            learned=guard.guarded_train(schema,Path(lineage['prepared_directory']),10000000,run/'model')
        truth=core.population_truth_groups(Path(lineage['truth_projection_path']))
        with canonical_evaluation():evaluated=guard.guarded_evaluate(learned,truth,moments['queries'],run/'evaluation')
        r=dict(status=PASS if not evaluated['point_query_errors'] and not evaluated['ci_query_errors'] else ERRORS,stage=STAGE,scope=SCOPE,kind='FORMAL',directory=str(run),plan=plan,
            plan_path=path.relative_to(ROOT).as_posix(),plan_file_sha256=digest(path),plan_binding_sha256=key,lineage=lineage,inputs=inputs,inherited_artifacts=inherited_extras(full),
            golden_artifacts=[d for d in golden['artifacts'] if d['path'] not in {p['path'] for p in full['artifacts']}],source_receipt_sha256=SOURCE_RECEIPT_SHA,
            original_mismatch=inputs['original_mismatch'],population_rows=source.N,actual_sample_rows=source.SAMPLE_ROWS,fact_normalizer=inputs['fact_normalizer'],author_different_groups=1713,
            author_reproduction_complete=False,full_paper_reproduction_complete=False,author_population_row_count_and_13_truths_match=False,author_full_row_byte_identity_proven=False,
            training_cap_per_table=10000000,actual_training_rows_per_table={v['table']:v['actual_training_rows'] for v in learned['training_tables']},spn_count=learned['spn_count'],
            prepared_directory=lineage['prepared_directory'],moments_directory=lineage['moments_directory'],moments_helper_directory=lineage['moments_helper_directory'],truth_projection_path=lineage['truth_projection_path'],
            model=learned,model_path=learned['model_path'],model_sha256=digest(learned['model_path']),training_tables=learned['training_tables'],
            evaluation=evaluated,queries=evaluated['queries'],evaluation_directory=evaluated['directory'],evaluation_binding=evaluated['binding'],point_query_errors=evaluated['point_query_errors'],ci_query_errors=evaluated['ci_query_errors'],
            runtime_cap=cap,validation_binding=plan['dependencies']['stage_validation'],adapter_source_sha256=digest(__file__),resources_at_start=resources,
            ci_scope='Original central90, actual retained9996946 reference sample, count<10 exclusion; all original errors retained',
            model_training_cap_per_table=10000000,**BUDGET_METADATA,**EVALUATION_METADATA,**PARENT_METADATA)
        return r
    def validate(r):
        import full_ssb_local_stage_validation as stages
        after,after_golden=_verify_prerequisites('FORMAL')
        require(lineage_snapshot(after)==lineage and golden_snapshot(after_golden)==plan['golden']
            and dependency_snapshot(plan['dependencies']['auxiliary_sources'])==plan['dependencies'],'reused1M/source/golden/runtime changed during10M model')
        require(r['actual_training_rows_per_table']==EXPECTED_ROWS,'actual10M per-table rows differ');stages.validate(r,validation_config())
    binding=dict(scope=SCOPE,kind='FORMAL',plan_binding_sha256=key,source_receipt_sha256=SOURCE_RECEIPT_SHA,dependencies_sha256=value_hash(plan['dependencies']),runtime_cap_sha256=value_hash(plan['dependencies']['runtime_cap']),author_different_groups=1713)
    with base.controller_lock(ROOT/OUTPUT/'controller.lock'):
        r=base.formal_transaction(run/'formal_control',binding,produce,validate,kind='LOCAL_CI_FORMAL');publish(r)
    return r


@native_boundary
def verify_scientific_publication(kind,root=ROOT):
    require((Path(root)/result_path(kind)).is_file(),'completed10M scientific publication missing')
    current,golden=_verify_prerequisites(kind,root)
    return _verify_scientific_publication(kind,root,current,golden)


def _verify_prerequisites(kind,root=ROOT):
    """One fresh complete parent per boundary; this result never crosses a command or training interval."""
    current=collect_lineage(root)
    return current,(_verify_golden_with_parent(root,current) if kind=='FORMAL' else golden_inputs())


def _verify_scientific_publication(kind,root,current,golden):
    """Private same-stack composition; callers cannot inject proofs into public verification."""
    root=Path(root);path=root/result_path(kind);require(path.is_file(),'completed10M scientific publication missing');r=read(path)
    require(r['kind']==kind and r['scope']==SCOPE and r['plan']['kind']==kind,'distinct10M publication kind/scope required')
    require(all(r.get(k)==v for k,v in EVALUATION_METADATA.items()),'exact canonical evaluation variant/adapter required')
    require(all(type(r.get(k)) is type(v) and r[k]==v for k,v in PARENT_METADATA.items()),'exact continuation provenance required')
    import full_ssb_local_ci_run as runner
    require(runner.read_plan(root/r['plan_path'],r['plan_file_sha256'],root)==r['plan'] and Path(r['directory']).resolve()==root/OUTPUT/'runs'/r['plan_binding_sha256'][:20], '10M actual plan/run namespace differs')
    if kind=='FORMAL':
        require(r['stage']==STAGE and r['status'] in (PASS,ERRORS) and r['training_cap_per_table']==10000000 and r['actual_training_rows_per_table']==EXPECTED_ROWS,'exact10M training budget/actual row fields required')
        require(r['plan']['golden']==golden_snapshot(golden),'actual complete scientific cap golden differs')
    else:require(r['plan']['golden']==golden,'current independently complete golden prepared inputs differ')
    require(r['lineage']==r['plan']['lineage']==lineage_snapshot(current) and r['inputs']==current['inputs'] and r['inherited_artifacts']==inherited_extras(current),'current complete1M parent lineage differs')
    if kind=='FORMAL':
        needed=[d for d in golden['artifacts'] if d['path'] not in {p['path'] for p in current['artifacts']}]
        require(r['golden_artifacts']==needed,'complete physical cap-golden artifact closure differs')
    require(root==ROOT and r['plan']['dependencies']==dependency_snapshot(r['plan']['dependencies']['auxiliary_sources']),'current10M runtime/source closure differs')
    records=verify_publication(r,root);run=Path(r['directory'])
    return dict(report=r,verification=artifact(run/'verification.json',root),verification_seal=artifact(run/'verification_seal.json',root),published_result=artifact(path,root),plan=artifact(root/r['plan_path'],root),
        formal_receipt=artifact(run/'formal_control/receipt.json',root),formal_lifecycle=artifact(run/'formal_control/lifecycle.json',root),artifacts=records,dependencies=r['plan']['dependencies'])


def verify_published(root=ROOT):
    result=verify_scientific_publication('FORMAL',root);r=result['report']
    import full_ssb_local_ci_run as runner
    result['artifacts'].extend(runner.verify_supervisor(r,root));require(len(result['artifacts'])==len({d['path'] for d in result['artifacts']}),'duplicate10M publication artifacts')
    result.update(status=API_PASS+('_WITH_ERRORS' if r['point_query_errors'] or r['ci_query_errors'] else ''),model_path=r['model_path'],model_sha256=r['model_sha256'],
        sample_rows=source.SAMPLE_ROWS,population_rows=source.N,queries=r['queries'],evaluation_binding=r['evaluation_binding'],original_mismatch=r['original_mismatch'],
        scope=SCOPE,author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,training_cap_per_table=10000000,
        actual_training_rows_per_table=EXPECTED_ROWS,lineage=r['lineage'],database_connected=False,training_executed=False,inference_executed=False,files_modified=False,**BUDGET_METADATA,**EVALUATION_METADATA,**PARENT_METADATA)
    return result


@native_boundary
def golden_inputs():
    """Existing SF2 algorithm fixture only; no preparation, fit or SQL execution."""
    import full_ssb_model as core
    schema,_,directory=core.sf2_preparation_reuse();inputs=core.model_input_artifacts(schema,directory)
    home=base.stage_home(directory,'prepared');receipt=read(home/'receipt.json');life=read(home/'lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['kind']=='PREPARED' and life['receipt_sha256']==digest(home/'receipt.json')
        and receipt['result']['core_input_artifacts']==inputs and receipt['binding']==life['binding'],'existing complete SF2 prepared guard required')
    records=[artifact(directory/name) for name in inputs['prepared_files_sha256']]
    records += [artifact(p) for p in (directory/'seal.json',home/'receipt.json',home/'lifecycle.json')]
    for description in inputs['raw_files'].values():records.append(artifact(description['path']))
    return dict(prepared_directory=str(directory),inputs=inputs,artifacts=records,scope='Existing SF2 algorithm-equivalence fixture only; no correctedSF500/author-fidelity claim')


def compare_golden(expected,actual):
    names={'lineorder','dwdate','customer','part','supplier'}
    require(set(expected)==set(actual)==names,'all five golden components required')
    fields=('sample_matrix_sha256','structure_sha256','numpy_rng_sha256','python_rng_sha256')
    require(all(expected[t]['table']==actual[t]['table']==t and all(expected[t][f]==actual[t][f] for f in fields) for t in names),'golden matrices/structures/both RNG states differ')
    return [dict(table=t,**{f:actual[t][f] for f in fields}) for t in sorted(names)]


def golden_artifacts(r,root=ROOT):
    run=Path(r['directory']);records={d['path']:d for d in r['plan']['golden']['artifacts']}
    for d in list(records.values()):require(artifact(Path(root)/d['path'],root)==d,'golden physical prepared input changed')
    def add(path,sha=None):
        d=artifact(path,root);require(sha is None or d['sha256']==sha,'golden result physical checksum differs');records[d['path']]=d
    require(r['status']=='PASS_LOCAL_10M_CAP_GOLDEN_ONLY' and r['sample_cap']==10000 and r['resumed_actual_fit_calls']==3
        and r['cap10m_boundary_only_verified'] is True and r['scientific_scope']=='Small SF2 equivalence only; no SF500 training or author truth PASS','complete scientific golden semantics required')
    expected_names=set(base.TABLES)
    for key,name in [('whole_model','whole'),('resumed_model','resumed')]:
        model=r[key];directory=run/name;home=base.stage_home(directory,'model');g=read(directory/'model_guard.json')
        pkls={t+'.pkl' for t in expected_names}|{'ensemble_single.pkl'};needed=pkls|{t+'.json' for t in expected_names}|{'model.json','input_guard.json'}
        require(model['binding']['samples_per_spn']==10000 and set(model['files_sha256'])==pkls and set(g['model_files_sha256'])==needed
            and read(directory/'model.json')==model,'complete golden model file set required')
        for filename,sha in g['model_files_sha256'].items():add(directory/filename,sha)
        add(directory/'model_guard.json');add(home/'receipt.json');add(home/'lifecycle.json')
        outer=read(home/'receipt.json');life=read(home/'lifecycle.json')
        require(outer['status']==life['status']=='PASS' and outer['kind']=='MODEL' and outer['result']==model and outer['binding']==life['binding']
            and life['receipt_sha256']==digest(home/'receipt.json') and outer['binding']['dependencies']==r['plan']['dependencies']['environment']['complete'],'golden outer model guard differs')
    reference=run/'reference';body=read(reference/'reference.json')
    require(body==r['original_reference'] and body['binding']['samples_per_spn']==10000 and len(body['observations'])==5,'complete original naive reference required')
    add(reference/'reference.json');add(reference/'ensemble_single_sf2_reference_10000.pkl',body['sha256'])
    for name in ('reference_rng.json','comparison.json'):add(run/name)
    evidence=read(run/'comparison.json');require(evidence==r['comparisons'] and len(evidence['whole'])==len(evidence['resumed'])==5,'all5 golden comparisons required')
    rng=read(run/'reference_rng.json');expected={v['table']:dict(v,**rng[v['table']]) for v in body['observations']}
    require(set(rng)==expected_names and set(r['preserved_first_two'])=={'lineorder.pkl','lineorder.json','dwdate.pkl','dwdate.json'},'complete RNG/recovery evidence required')
    for label,model in [('whole',r['whole_model']),('resumed',r['resumed_model'])]:
        actual={v['table']:v for v in evidence[label]};compare_golden(expected,actual)
        rows={v['table']:v for v in model['training_tables']}
        require(set(rows)==expected_names and all(rows[t]['sample_matrix_sha256']==expected[t]['sample_matrix_sha256']
            and rows[t]['structure_sha256']==expected[t]['structure_sha256'] for t in expected_names),'golden checkpoint matrices/nodes disagree with complete comparison')
    for name,sha in r['preserved_first_two'].items():require(digest(run/'whole'/name)==digest(run/'resumed'/name)==sha,'completed prefix checkpoints changed during recovery')
    return list(records.values())


@native_boundary
def execute_golden(reviewed_codes_sha256,plan=None):
    require(plan is not None and plan.get('kind')=='GOLDEN','reviewed owned GOLDEN plan required');key,path=require_worker(plan)
    require(reviewed_codes_sha256==value_hash(code_snapshot()),'reviewed golden source set changed')
    full,fixture=_verify_prerequisites('GOLDEN');require(fixture==plan['golden'] and lineage_snapshot(full)==plan['lineage'],'actual golden fixture/complete1M prerequisites changed')
    run=ROOT/OUTPUT/'runs'/key[:20]
    def produce():
        import full_ssb_guard as guard
        import full_ssb_model as core
        import numpy as np
        import pickle,random,shutil
        from aqp_spn.aqp_spn import AQPSPN
        schema,_,prepared=core.sf2_preparation_reuse();original=AQPSPN.learn;rng={}
        def state_hash(state):return hashlib.sha256(pickle.dumps(state,protocol=4)).hexdigest()
        def capture(model,*args,**kwargs):
            result=original(model,*args,**kwargs);table=next(iter(model.table_set))
            rng[table]=dict(numpy_rng_sha256=state_hash(np.random.get_state()),python_rng_sha256=state_hash(random.getstate()));return result
        AQPSPN.learn=capture
        try:reference=core.train_original_reference(schema,prepared,10000,run/'reference')
        finally:AQPSPN.learn=original
        atomic(run/'reference_rng.json',rng)
        expected={v['table']:dict(v,**rng[v['table']]) for v in reference['observations']}
        with runtime_cap_adapter(core) as cap:whole=guard.guarded_train(schema,prepared,10000,run/'whole')
        def observed(model):
            result={}
            for row in model['training_tables']:
                with (Path(model['model_path']).parent/(row['table']+'.pkl')).open('rb') as stream:state=pickle.load(stream)
                result[row['table']]=dict(row,numpy_rng_sha256=state_hash(state['numpy_rng']),python_rng_sha256=state_hash(state['python_rng']))
            return result
        whole_comparison=compare_golden(expected,observed(whole));resumed=run/'resumed';resumed.mkdir(parents=True,exist_ok=False);preserved={}
        for t in ('lineorder','dwdate'):
            for suffix in ('.pkl','.json'):
                name=t+suffix;shutil.copyfile(run/'whole'/name,resumed/name);preserved[name]=digest(resumed/name)
        calls=[]
        def count(model,*args,**kwargs):calls.append(next(iter(model.table_set)));return original(model,*args,**kwargs)
        AQPSPN.learn=count
        try:
            with runtime_cap_adapter(core):recovered=guard.guarded_train(schema,prepared,10000,resumed)
        finally:AQPSPN.learn=original
        require(calls==['customer','part','supplier'],'recovery must fit only the three missing components')
        comparisons=dict(whole=whole_comparison,resumed=compare_golden(expected,observed(recovered)));atomic(run/'comparison.json',comparisons)
        guard_node=next(n for n in ast.parse(adapt_training_source(original_training_source())[0]).body[0].body if isinstance(n,ast.If))
        exec(compile(ast.Module(body=[guard_node],type_ignores=[]),'<cap-boundary-only>','exec'),{'sample_cap':10000000})
        return dict(status='PASS_LOCAL_10M_CAP_GOLDEN_ONLY',stage='LOCAL_10M_CAP_SMALL_GOLDEN',scope=SCOPE,kind='GOLDEN',directory=str(run),plan=plan,
            plan_path=path.relative_to(ROOT).as_posix(),plan_file_sha256=digest(path),plan_binding_sha256=key,source_receipt_sha256=SOURCE_RECEIPT_SHA,
            runtime_cap=cap,adapter_source_sha256=digest(__file__),lineage=lineage_snapshot(full),inputs=full['inputs'],inherited_artifacts=inherited_extras(full),
            sample_cap=10000,original_reference=reference,whole_model=whole,resumed_model=recovered,
            comparisons=comparisons,preserved_first_two=preserved,resumed_actual_fit_calls=len(calls),cap10m_boundary_only_verified=True,
            scientific_scope='Small SF2 equivalence only; no SF500 training or author truth PASS',author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,**EVALUATION_METADATA,**PARENT_METADATA)
    def validate(r):
        after,after_fixture=_verify_prerequisites('GOLDEN')
        require(lineage_snapshot(after)==lineage_snapshot(full) and after_fixture==fixture
            and plan['dependencies']==dependency_snapshot(plan['dependencies']['auxiliary_sources']),'golden parent/input/runtime/source changed');golden_artifacts(r)
    binding=dict(scope=SCOPE,kind='GOLDEN',plan_binding_sha256=key,source_receipt_sha256=SOURCE_RECEIPT_SHA,dependencies_sha256=value_hash(plan['dependencies']),runtime_cap_sha256=value_hash(plan['dependencies']['runtime_cap']),author_different_groups=1713)
    with base.controller_lock(ROOT/OUTPUT/'controller.lock'):
        r=base.formal_transaction(run/'formal_control',binding,produce,validate,kind='LOCAL_CI_GOLDEN');publish(r)
    return r


def verify_golden(root=ROOT):
    require((Path(root)/GOLDEN_RESULT).is_file(),'completed10M cap scientific golden missing')
    current,fixture=_verify_prerequisites('GOLDEN',root)
    return _verify_golden_with_parent(root,current,fixture)


def _verify_golden_with_parent(root,current,fixture=None):
    result=_verify_scientific_publication('GOLDEN',root,current,golden_inputs() if fixture is None else fixture);r=result['report']
    import full_ssb_local_ci_run as runner
    result['artifacts'].extend(runner.verify_supervisor(r,root));result.update(status='PASS_READ_ONLY_LOCAL_10M_CAP_GOLDEN_ONLY',training_executed=False,inference_executed=False,files_modified=False)
    return result


def verify_local_ci(root=ROOT):
    require((Path(root)/RESULT).is_file(),'completed10M CI publication missing')
    return verify_published(root)
