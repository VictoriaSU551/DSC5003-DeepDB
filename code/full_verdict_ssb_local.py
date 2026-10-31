"""Explicit LOCAL SF500 Verdict contracts and exact retained-moment oracles.

Import/describe are inert. Parent scientific providers are imported lazily only
after exact, complete final publications have been supplied and checked.
"""
import copy
from fractions import Fraction
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
FROZEN={
 'code/full_verdict_ssb_run.py':'e1416b4201ea22df9ca7abaa2ce5fecb38ee70ee716ede7323acdaeff778b5c8',
 'code/full_verdict_ssb.py':'2068722a30f99f40ddc3be17a5663322300c2eb48b7218da426dfea568058082',
 'code/full_verdict_ssb_bridge.java':'9264e946a0efb4e44abb3630ffa980e91f1b985e5fb8e0546a26efcef36b041d',
 'code/full_windows_fingerprint.py':'a9e9034efad01e258c521934aea43f0f405ff78c42caffb7841a73fd03d96784',
 'code/full_verdict_ssb_audit.py':'c707b17ebc00fdbd3033b8bd333d73f04fae256cdc62094c7f1ea6bae511c22b'}
PARENT_PINS={
 'code/full_ssb_local_source.py':'699f85ec4d24c326a7b491cd4cbf9c5746a98e7947d5b79db60200d08c0e3ca3',
 'code/full_ssb_local_model.py':'0b736cb30e7f1e93c66d2ac632c9b8a0ac0023595440c46b8d9215962184bced',
 'code/full_ssb_local_model_run.py':'fd676fb41780ae96074a08f2478a7cef9820b7c55a65717b9b8e28ea9545dee3',
 'code/full_ssb_local_replay.py':'9c2211af6b6385944010e079eef2fbc1f1dae381ccd39590f4acef9479c98aac',
 'code/full_ssb_replay.py':'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab',
 'code/full_ssb_native_replay.py':'6c8de16e03a8ba20448121fd4659c092c668d4db0f7214b932a40bf20d30302d',
 'code/full_ssb_native_model.py':'7c50feb8d9248ae5f8bfc7f29aac39d86ecc687b38c407ca380fb3bef4558312',
 'code/full_ssb_native_model_run.py':'117b507a95c9333828e7d0069327d9771395e5fd42a62bc398862059a78d23f0',
 'code/full_ssb_model.py':'5b6d31a15884cf09ba29c19d3c49db2c5a79d82a5fba40e4aa1d7e714f23aa27',
 'code/full_ssb_guard.py':'fc19133d00216ceac72198eed747107d81e82f224804c69440290931a201f842',
 'code/full_ssb_native_v2.py':'9dc407892acaa14042cf4c9645b455747efbbba46d63fb8385946ee30a60eaeb',
 'code/full_ssb_native_v2_stream.py':'ddcd3b3d387b8b6a28324ceb89b39f1b0911db8f4130ccf5dbd4567424e422b1',
 'code/full_ssb_native_v2_formal.py':'52de0f43faf554a761f8dacca3cee5e9d919113402743aacf1a211ddcd882b40',
 'code/full_ssb_local_canonical.py':'9c041ffc8ca40386ad9e3582fd81cb1f0e76fd3db1a337cb97bb686a521ff6b6',
 'code/full_ssb_local_canonical_run.py':'8d561253786e8acd68e03c3b89fce46c2655f04cdd0c4b34492b369a6d757636',
 'code/full_ssb_group_order.py':'48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'}
SOURCES=['code/full_verdict_ssb_local.py','code/full_verdict_ssb_local_ops.py','code/full_verdict_ssb_local_run.py',
 'code/full_verdict_ssb_local_bridge.java','code/tests/test_full_verdict_ssb_local.py','code/tests/test_full_verdict_ssb_local_ops.py',
 'code/tests/test_full_verdict_ssb_local_run.py','docs/FULL_VERDICT_LOCAL_SSB_IMPLEMENTATION.md','docs/FULL_VERDICT_LOCAL_SSB_PROPOSAL.md']


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def read(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'Duplicate JSON object key: '+key);result[key]=value
        return result
    def nonfinite(value):raise ValueError('Nonfinite JSON number: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=nonfinite)


def value_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def artifact(path):
    path=Path(path).resolve()
    if ROOT.resolve() not in path.parents:
        allowed={Path('C:/Windows/System32')/name for name in ('KERNEL32.dll','msvcrt.dll')}
        require(path in {p.resolve() for p in allowed} and path.is_file(),'External artifact is not an allowed direct Windows import')
        return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path),external_scope='windows_direct_native_import')
    require(path.is_file(),'Required project artifact missing')
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=digest(path))


def verify_parent_descriptor(record):
    """Keep only the two frozen direct-import exceptions, including scope."""
    require(isinstance(record,dict) and {'path','bytes','sha256'}<=set(record),'Complete parent descriptor required')
    actual=artifact(ROOT/record['path']);keys=set(actual)
    require({k:record.get(k) for k in keys}==actual and ('external_scope' not in record or record['external_scope']==actual.get('external_scope')),
        'Parent descriptor physical bytes/scope differ')
    return actual


def load_frozen():
    for path,sha in FROZEN.items():require(digest(ROOT/path)==sha,'Frozen source differs: '+path)
    p=ROOT/'code/full_verdict_ssb_run.py';s=importlib.util.spec_from_file_location('local_verdict_frozen_utilities',str(p))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def verify_delegate_sources():
    """Independent constants precede every delegated import; no payload trust."""
    for name,sha in PARENT_PINS.items():
        require((ROOT/name).is_file() and digest(ROOT/name)==sha,'Frozen delegated verifier source changed before import: '+name)
    return dict(PARENT_PINS)


def local_spec():
    gib=1024**3
    return dict(scope='LOCAL_SSB_SF500_VERDICT_EXISTING_SAMPLE',database='deepdb_verdict_ssb_local500',
        protected_databases=['deepdb_job','deepdb_verdict','deepdb_verdict_ssb'],
        population_rows=3000028242,sample_rows=9996946,
        source_id='a574cd95f8ba184c809c66e438c88f69ddb1ddcc7b984c9ea99bcbb4c476dcf9',
        source_report='output/full/results/ssb_local_sf500_source.json',
        source_report_sha256='75fef537963dcbc183a720f2abc1b47b6972550822ba4591dec8f8336183e712',
        model_report='output/full/results/ssb_local_sf500_model_aqp_ci.json',
        model_report_sha256='da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82',
        canonical_report='output/full/results/ssb_local_sf500_canonical_aqp_ci.json',
        canonical_namespace='output/full/ssb/local_sf500_canonical/runs',
        reverse_report_policy='CANONICAL_RUN_REVERSE_VERIFICATION',
        evaluation_variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1',
        group_order_adapter_sha256=PARENT_PINS['code/full_ssb_group_order.py'],
        historical_failed_reverse_report='output/full/ssb/local_sf500_replay/verification.json',
        original_mismatch_sha256='740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e',
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        sampling_ratio=dict(numerator=9996946,denominator=3000028242),
        generator_probability=dict(numerator=61482997997673935,denominator=2**64),
        sample_relation='public_verdict.vs_lineorder_uf_0_0033',original_relation='public.lineorder',
        dimension_rows=dict(customer=15000000,supplier=1000000,part=1800000,dwdate=2556),
        dimension_policy='FULL_UNSAMPLED_NO_VPART',
        output='output/full/verdict_ssb/local_sf500',staging='data/verdict_ssb/local_sf500',
        java_class='full_verdict_ssb_local_bridge',java_source='code/full_verdict_ssb_local_bridge.java',
        partition_seed=.271828,partitions=100,confidence_probability=.95,
        platform='Windows-10-10.0.26200-SP0',machine='AMD64',
        limits=dict(total_new_bytes=12*gib,owned_database_bytes=8*gib,positive_wal_bytes=2*gib,
            positive_temp_bytes=gib,owned_files_bytes=gib,minimum_available_ram_bytes=4*gib,
            minimum_free_disk_bytes=18*gib,java_rss_bytes=gib,python_rss_bytes=512*1024**2,
            statement_timeout_ms=600000,work_mem_kib=16384,temp_file_limit_kib=1048576,
            native_process_timeout_seconds=660),
        sampling_cost_scope='Existing retained sample; no original3B sampling/end-to-end measurement')


def raw_queries():
    c=load_frozen().candidate();return [q for q in c.call_plan(c.load_queries()) if q['mode']=='nobound' and q['role']=='RAW']


def call_plan():
    c=load_frozen().candidate();return c.call_plan(c.load_queries())


def canonical_key(values):
    require(isinstance(values,list) and all(v is None or type(v) in (str,int) for v in values),'Moment key must preserve exact list/string/integer/NULL identity')
    return [None if v is None else str(v) for v in values]


def moments_oracle(moment,N,n,queries):
    require(type(N) is int and type(n) is int and 0<n<=N,'Exact positive N/n required')
    require(moment.get('status')=='PASS' and moment.get('sample_rows')==n and len(queries)==len(moment.get('queries',[]))==13,'All13 sealed retained-moment queries required')
    result=[]
    for index,(q,m) in enumerate(zip(queries,moment['queries'])):
        require(q['query_no']==index and q['role']=='RAW' and m['sql']==q['sql'],'Retained moment SQL/index differs')
        require(m['kind']==('DIFF' if index>=10 else 'SUM'),'Retained expression kind differs')
        groups=[];seen=set()
        for g in m['groups']:
            key=canonical_key(g['key']);identity=tuple(key)
            require(identity not in seen and len(key)==q['group_width'],'Duplicate/wrong-width moment group')
            seen.add(identity)
            require(all(type(g[k]) is int for k in ('count','filter_count','sum_integer','square_sum_integer','scale')),'Moment arithmetic must remain integer')
            count,filtered,total,squares,scale=(g[k] for k in ('count','filter_count','sum_integer','square_sum_integer','scale'))
            require(0<=count<=filtered<=n and squares>=0 and scale==1,'Invalid integer SSB moment count/scale/square bounds')
            require((count and total*total<=count*squares) or (count==0 and total==squares==0),'Impossible exact integer moments')
            if index>=10:require(g['component_non_null_counts']==[filtered,filtered] and count==filtered,'Profit adapter is unsafe under unequal component NULL patterns')
            expected=Fraction(total*N,n*scale) if count else None
            groups.append(dict(key=key,sample_sum=total if count else None,scale=scale,count=count,filter_count=filtered,
                square_sum_integer=squares,expected=None if expected is None else dict(numerator=expected.numerator,denominator=expected.denominator)))
        if not groups and q['group_width']==0:groups=[dict(key=[],sample_sum=None,scale=1,count=0,filter_count=0,square_sum_integer=0,expected=None)]
        result.append(dict(query_no=index,sql=q['sql'],sql_sha256=q['sql_sha256'],kind=m['kind'],groups=groups,
            component_oracle_status='UNAVAILABLE_ONLY_PROFIT_SUM_STORED' if index>=10 else 'NOT_A_COMPONENT_QUERY'))
    return result


def verify_artifacts(records):
    require(isinstance(records,dict) and bool(records),'Nonempty independent physical artifact set required')
    for path,rec in records.items():require(path==rec['path'] and verify_parent_descriptor(rec)==rec,'Physical artifact changed: '+path)


def collect_lineage(expected):
    """Read-only, lazy, complete parents; never touch an unfinished moments file."""
    spec=local_spec();require(isinstance(expected,dict) and set(expected)=={'source','model','canonical','reverse'},'Exact final parent source/model/canonical/reverse descriptors required')
    require(all(isinstance(r,dict) and type(r.get('path')) is str for r in expected.values()),'Complete final parent physical descriptors required')
    mapping={key:spec[key+'_report'] for key in ('source','model','canonical')};mapping['reverse']=expected['reverse']['path']
    reverse_path=(ROOT/mapping['reverse']).resolve();canonical_home=(ROOT/spec['canonical_namespace']).resolve()
    require(canonical_home in reverse_path.parents and reverse_path.name=='verification.json' and reverse_path.parent.name=='reverse',
        'Only the final canonical run reverse publication is eligible')
    for key,path in mapping.items():
        require(expected[key].get('path')==path and (ROOT/path).is_file(),'Required final parent publication missing')
    verify_delegate_sources()
    for key,path in mapping.items():
        require(artifact(ROOT/path)==expected[key],'Explicit final parent descriptor differs')
    source,model,canonical,reverse=(read(ROOT/mapping[key]) for key in ('source','model','canonical','reverse'))
    require(source['status']=='PASS_LOCAL_SOURCE_PHYSICAL_GATE_ONLY' and source['source_id']==spec['source_id'] and expected['source']['sha256']==spec['source_report_sha256'],'Accepted LOCAL physical source differs')
    require(model.get('scope')=='LOCAL_SSB_SF500' and model.get('status') in ('PASS_LOCAL_SSB_SF500_MODEL_AQP_CI','LOCAL_MODEL_QUERY_ERRORS_RECORDED')
        and expected['model']['sha256']==spec['model_report_sha256'],'Complete unchanged original model publication required')
    def canonical_scope(value):
        require(value.get('scope')=='LOCAL_SSB_SF500_CANONICAL_CI' and value.get('group_order_adapter_sha256')==spec['group_order_adapter_sha256']
            and value.get('author_different_groups')==1713 and value.get('author_reproduction_complete') is False
            and value.get('full_paper_reproduction_complete') is False,'Canonical scope, adapter and author mismatch must remain explicit')
    canonical_scope(canonical);canonical_scope(reverse)
    require(canonical.get('status')=='PASS_LOCAL_SSB_SF500_CANONICAL_AQP_CI'
        and canonical.get('variant')=='CANONICAL_PAIRED_DECODED_GROUP_ORDER' and canonical.get('evaluation_variant')==spec['evaluation_variant']
        and canonical.get('historical_reverse_accepted') is False and canonical.get('parent_formal')==expected['model']
        and canonical.get('reverse')==expected['reverse'],'Complete canonical publication and parent/reverse aliases required')
    require(reverse.get('status')=='PASS_CANONICAL_REVERSE_EVALUATION' and reverse.get('phase')=='REVERSE'
        and Path(reverse.get('directory','')).resolve()==Path(canonical.get('directory','')).resolve()
        and (Path(canonical['directory'])/'reverse/verification.json').resolve()==reverse_path,'Canonical reverse phase/run identity differs')
    require(all(x.get('author_reproduction_complete') is False and x.get('full_paper_reproduction_complete') is False for x in (source,model)),'Author mismatch scope must remain explicit')
    require(source['different_author_groups']==model['author_different_groups']==1713,'Author mismatch count changed')
    local_names=('code/full_ssb_local_source.py','code/full_ssb_local_model.py','code/full_ssb_local_model_run.py')
    require(source['local_sources']=={name:PARENT_PINS[name] for name in local_names},'Exact independently pinned three parent providers required')
    replay_pin=model['plan']['dependencies']['auxiliary_sources'].get('code/full_ssb_local_replay.py')
    require(replay_pin==PARENT_PINS['code/full_ssb_local_replay.py'],'Original historical model source pin differs; it does not accept the failed reverse')
    # Only now may read-only parent verifiers import their modules. Actual PG,
    # SQLite, JVM, training/inference and all launch paths remain forbidden.
    helper=importlib.import_module('full_windows_fingerprint')
    require(digest(ROOT/'code/full_windows_fingerprint.py')==FROZEN['code/full_windows_fingerprint.py'],'Native helper changed')
    audit=importlib.import_module('full_verdict_ssb_audit');core=load_frozen()
    with audit.forbid_science(core),helper.verified_platform(spec['platform'],spec['machine']):
        provider=importlib.import_module('full_ssb_local_canonical')
        require(Path(getattr(provider,'__file__','')).resolve()==(ROOT/'code/full_ssb_local_canonical.py').resolve(),
            'Actually loaded canonical provider differs from the pinned physical source')
        actual=provider.verify_canonical()
    # One complete canonical verification contains one complete original formal
    # proof. Consume its actual original snapshot; never call failed replay9c.
    canonical_scope(actual)
    require(actual.get('status')=='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH'
        and actual.get('evaluation_variant')==spec['evaluation_variant'] and actual.get('variant')=='CANONICAL_PAIRED_DECODED_GROUP_ORDER'
        and actual.get('historical_reverse_accepted') is False and actual.get('sample_rows')==spec['sample_rows']
        and actual.get('population_rows')==spec['population_rows'] and actual.get('published_result')==expected['canonical']
        and actual.get('report')==canonical and actual.get('parent_formal')==expected['model'] and actual.get('reverse')==expected['reverse']
        and all(actual.get(k) is False for k in ('database_connected','training_executed','inference_executed','files_modified')),
        'Complete read-only canonical verifier result/aliases differ')
    formal=actual.get('parent_snapshot',{})
    require(formal.get('status')=='PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH' and formal.get('scope')=='LOCAL_SSB_SF500'
        and formal.get('published_result')==expected['model'] and formal.get('report')==model,
        'Canonical snapshot must retain the full verified original formal report')
    require(all(isinstance(v,dict) and isinstance(v.get('artifacts'),list) and bool(v['artifacts']) for v in (formal,actual)),
        'Complete nonempty original and canonical artifact closures required')
    report=formal['report'];run=Path(report['directory']).resolve()
    require((ROOT/'output/full/ssb/local_sf500_models').resolve() in run.parents,'Parent model namespace differs')
    moment=run/'sample_moments_native/moments.json';seal=moment.with_name('seal.json');raw=moment.with_name('moments.tsv');process=moment.with_name('process.json')
    s=read(seal);m=read(moment)
    require(digest(moment)==s['sha256'] and digest(raw)==s['tsv_sha256'] and read(process)['returncode']==0 and m['sample_rows']==spec['sample_rows'],'Final13 native moments physical seal differs')
    oracle=moments_oracle(m,spec['population_rows'],spec['sample_rows'],raw_queries())
    records={}
    def add(path):
        r=artifact(path);records[r['path']]=r
    def walk(value):
        if isinstance(value,dict):
            if set(('path','bytes','sha256'))<=set(value) and isinstance(value['path'],str):
                previous=records.get(value['path'])
                if previous is None:
                    rec=verify_parent_descriptor(value);records[rec['path']]=rec
                else:require(all(value.get(k)==v for k,v in previous.items()),'Conflicting repeated parent descriptor')
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(formal);walk(actual)
    for path in list(mapping.values())+[str(moment),str(seal),str(raw),str(process)]:add(ROOT/path)
    return dict(status='PASS_COMPLETE_LOCAL_CANONICAL_MODEL_REVERSE_INTEGER_MOMENT_LINEAGE',source=source,model=expected['model'],canonical=expected['canonical'],reverse=expected['reverse'],
        parent_canonical=expected['canonical'],parent_reverse=expected['reverse'],parent_formal=expected['model'],
        evaluation_variant=spec['evaluation_variant'],group_order_adapter_sha256=spec['group_order_adapter_sha256'],historical_reverse_accepted=False,
        source_expected=expected,files=records,moments=artifact(moment),oracle=oracle,
        actual_training_rows={x['table']:x['actual_training_rows'] for x in report['training_tables']},author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False)


def validate_measurement(value):
    spec=local_spec()
    require(value.get('status')=='PASS_READONLY_SF2_RELATION_WIDTH_MEASUREMENT' and value.get('database')=='deepdb_verdict_ssb','Actual SF2 relation measurement required')
    rows=value.get('relations',[]);expected={'public.dwdate':2556,'public.customer':60000,'public.supplier':4000,'public.part':400000,spec['sample_relation']:39587}
    require(len(rows)==5 and {r['relation']:r['rows'] for r in rows}==expected,'Complete independently measured SF2 relation rows required')
    for r in rows:
        require(all(type(r[k]) is int and r[k]>=0 for k in ('heap_bytes','index_bytes','total_bytes','max_row_bytes','rows')) and r['total_bytes']>=r['heap_bytes']+r['index_bytes'] and r['max_row_bytes']>0,'Invalid actual relation byte measurement')
        require(type(r['average_row_bytes']) in (int,float) and math.isfinite(r['average_row_bytes']) and 0<r['average_row_bytes']<=r['max_row_bytes'],'Invalid actual row-width measurement')
    require(value.get('data_modified') is False and value.get('scientific_calls')==0,'Measurement must be catalog/row-width only')
    return value


def dependency_snapshot():
    spec=local_spec();core=load_frozen()
    helper=importlib.import_module('full_windows_fingerprint')
    with helper.verified_platform(spec['platform'],spec['machine']):runtime=core.runtime_closure()
    own={p:artifact(ROOT/p) for p in SOURCES}
    for p in FROZEN:own[p]=artifact(ROOT/p)
    for p in PARENT_PINS:own[p]=artifact(ROOT/p)
    for p in (core.candidate().SQL_PATH,core.candidate().SCHEMA_PATH):own[p]=artifact(ROOT/p)
    return dict(source_files=own,runtime=runtime)


class _PlanningBoundary:
    """Private, entry-local complete proof; never persisted or accepted publicly."""
    def __init__(self,expected):
        self.expected=copy.deepcopy(expected);self.lineage=collect_lineage(expected);self.dependencies=dependency_snapshot();self.plan=None


def _require_boundary(boundary,expected):
    require(type(boundary) is _PlanningBoundary and boundary.expected==expected,'Private same-entry complete planning proof required')


def _pilot_plan_from_boundary(boundary):
    _require_boundary(boundary,boundary.expected)
    body=dict(schema='local_verdict_readonly_measurement_plan_v1',kind='READONLY_SF2_RELATION_WIDTH',spec=local_spec(),parent_expected=boundary.expected,
        lineage=boundary.lineage,dependencies=boundary.dependencies,scope='LOCAL_VERDICT_RESOURCE_MEASUREMENT_ONLY',scientific_calls=0,data_mutation=False)
    return dict(body,binding_sha256=value_hash(body))


def build_pilot_plan(expected):return _pilot_plan_from_boundary(_PlanningBoundary(expected))


def _reviewed_measurement(measurement,resource_review):
    spec=local_spec()
    require(set(measurement)=={'path','bytes','sha256'} and artifact(ROOT/measurement['path'])==measurement,'Exact completed pilot final descriptor required')
    require(resource_review.get('status')=='APPROVED_LOCAL_VERDICT_RESOURCE_PLAN' and resource_review.get('measurement_sha256')==measurement['sha256']
        and resource_review.get('limits')==spec['limits'],'Independent actual resource review required before executable plan')
    for field,cap in [('projected_owned_database_bytes','owned_database_bytes'),('projected_total_new_bytes','total_new_bytes')]:
        require(type(resource_review.get(field)) is int and 0<resource_review[field]<=spec['limits'][cap],'Reviewed measured storage projection exceeds fixed component/total cap')


def _plan_from_boundary(expected,measurement,resource_review,boundary):
    _require_boundary(boundary,expected);_reviewed_measurement(measurement,resource_review);spec=local_spec()
    runner=importlib.import_module('full_verdict_ssb_local_run')
    pilot=runner._verify_pilot_from_boundary(ROOT/measurement['path'],boundary);validate_measurement(pilot['measurement'])
    require(pilot['parent_expected']==expected,'Measurement and formal parent lineage differ')
    lineage=boundary.lineage;dependencies=boundary.dependencies;core=load_frozen()
    body=dict(schema='local_verdict_ssb_plan_v1',spec=spec,scope=spec['scope'],parent_expected=expected,lineage=lineage,
        queries=call_plan(),schema_contract=core.schema_contract((ROOT/core.candidate().SCHEMA_PATH).read_text(encoding='utf-8')),
        measurement=measurement,measurement_verification=pilot,resource_review=resource_review,source_files=dependencies['source_files'],runtime=dependencies['runtime'],
        reuse_whitelist=['candidate','digest','atomic_json','schema_contract','create_table_sql','raw_chunks','CopyHashSink','budget_total','process_rss','available_ram','tree_bytes','java_environment','bounded_process','pg_control','pg_control_artifacts','start_owned_server','postmaster_identity','validate_owned_identity','validate_pg_control','validate_pg_files','validate_process','lsn_integer','compare_oracle','population_statistics','runtime_closure'],
        reused_global_scope='Same project PG cluster/path/start options; same1GiB JVM cap. No frozen DB/N/n/LIMITS mutation or SF2 import/plan/execute calls.',
        executable=True,engine_calls_executed=0,author_reproduction_complete=False,full_paper_reproduction_complete=False)
    return dict(body,binding_sha256=value_hash(body))


def build_plan(expected,measurement,resource_review):
    _reviewed_measurement(measurement,resource_review)
    return _plan_from_boundary(expected,measurement,resource_review,_PlanningBoundary(expected))
