"""Derived LOCAL1M views of an independently accepted canonical continuation."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
SCOPE='LOCAL_SSB_SF500_CANONICAL_CONTINUATION'
PROTOCOL='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
API_PASS='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH'
REPORT_PASS='PASS_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_AQP_CI'
EXECUTION_VARIANT='CANONICAL_PAIRED_DECODED_GROUP_ORDER'
VARIANT='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
ADAPTER_SHA='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'
PARENT_RESULT_SHA='da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82'
MISMATCH_SHA='740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e'
PROVIDER_FILES=('code/full_ssb_local_continuation.py','code/full_ssb_local_continuation_run.py','code/full_ssb_group_order.py')
PINS={
    PROVIDER_FILES[0]:'151b29aac633aa85902578ccb115de749a31be74d8f525b1e62d5d99257dd6d1',
    PROVIDER_FILES[1]:'e3135eea0469eb00df42ea8c27370d6af445356bb4c136f2c71ee2e11ebf41be',
    PROVIDER_FILES[2]:ADAPTER_SHA,
    'code/full_ssb_local_tables.py':'be1738ebb9b6e1947684a35b7af403226e6dc043244ff26c12b1f1cc2522ae63',
    'code/full_ssb_tables.py':'c1957f5a5709c76086a88d7e828fd018b83db0a7a4ed7c2e85369d5fbce79a14',
    'code/full_aqp_tables.py':'99fc82b496b78c87e87601736624033f29effddbf71cc3a2bfafb8b31b3ef03b',
    'code/full_common.py':'59bd9c378a236c5c47c9bda01602fcab49bf6bf93a745299ca58e7e7b5f57e3b',
    'code/full_ssb_local_replay.py':'9c2211af6b6385944010e079eef2fbc1f1dae381ccd39590f4acef9479c98aac',
    'code/full_ssb_replay.py':'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab',
    'code/full_ssb_native_replay.py':'6c8de16e03a8ba20448121fd4659c092c668d4db0f7214b932a40bf20d30302d'}
DESCRIPTORS=('published_result','verification','verification_seal','plan','formal_receipt','formal_lifecycle')
READONLY=('database_connected','training_executed','inference_executed','files_modified')


def require(condition,message):
    if not condition:raise ValueError(message)


def value_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def check_sources():
    for path,sha in PINS.items():
        require(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,'frozen derived source differs: '+path)


def inventory(records):
    """Check the just-verified inventory structurally; do not repeat physical F."""
    require(type(records) is list and bool(records),'complete nonempty artifact inventory required')
    paths=set()
    for item in records:
        require(type(item) is dict and isinstance(item.get('path'),str) and bool(item['path'])
            and type(item.get('bytes')) is int and item['bytes']>=0
            and isinstance(item.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',item['sha256']) is not None,
            'complete physical artifact descriptor required')
        path=(ROOT/item['path']).resolve();key=os.path.normcase(str(path))
        require(key not in paths,'artifact inventory contains a physical path alias');paths.add(key)
        if ROOT.resolve() not in path.parents:
            require(path in {Path('C:/Windows/System32')/n for n in ('KERNEL32.dll','msvcrt.dll')}
                and item.get('external_scope')=='windows_direct_native_import','unexpected external artifact')
    return {item['path']:item for item in records}


def accepted():
    check_sources()
    provider=importlib.import_module('full_ssb_local_continuation')
    require(Path(provider.__file__).resolve()==(ROOT/PROVIDER_FILES[0]).resolve(),'shadow continuation provider')
    checked=provider.verify_canonical()  # The sole public call: one complete original formal F.
    r=checked['report'];parent=checked['parent_snapshot']
    for obj in (checked,r):
        require(obj['scope']==SCOPE and obj['execution_protocol']==PROTOCOL and obj['variant']==EXECUTION_VARIANT
            and obj['evaluation_variant']==VARIANT and obj['group_order_adapter_sha256']==ADAPTER_SHA
            and obj['author_reproduction_complete'] is False and obj['full_paper_reproduction_complete'] is False
            and type(obj['author_different_groups']) is int and obj['author_different_groups']==1713
            and obj['historical_reverse_accepted'] is False,'separate continuation/LOCAL mismatch contract required')
    require(checked['status']==API_PASS and r['status']==REPORT_PASS
        and all(checked[k] is False for k in READONLY)
        and type(checked['population_rows']) is int and checked['population_rows']==3000028242
        and type(checked['sample_rows']) is int and checked['sample_rows']==9996946,
        'accepted read-only continuation with exact population/sample required')
    require(r['adopted_forward'] is True and all(r[k] is False for k in
        ('forward_reexecuted','preparation_executed','training_executed','moments_executed','historical_result_changed'))
        and r['phase_model_loads']==dict(FORWARD=1,REVERSE=13)
        and r['phase_evaluator_calls']==dict(FORWARD=26,REVERSE=26),'accepted forward adoption/fresh reverse accounting required')
    require(parent['proof_method']=='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL'
        and parent['status']=='PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH'
        and parent['scope']=='LOCAL_SSB_SF500' and parent['sample_rows']==9996946 and parent['population_rows']==3000028242
        and parent['author_different_groups']==1713 and parent['author_reproduction_complete'] is False
        and parent['full_paper_reproduction_complete'] is False and all(parent[k] is False for k in READONLY)
        and type(parent['report']) is dict and len(parent['report']['queries'])==13
        and type(parent['dependencies']) is dict and bool(parent['dependencies'])
        and all(k in parent for k in ('queries','evaluation_binding','model_path','model_sha256')),
        'complete original formal parent proof required; summaries and failed replay cannot certify it')
    records=inventory(checked['artifacts']);original=inventory(parent['artifacts'])
    require(value_hash(parent['artifacts'])==parent['closure_sha256']
        and all(records.get(p)==d for p,d in original.items()),'full original parent artifact union required')
    for obj in (checked,parent):
        require(all(obj[k] in checked['artifacts'] and obj[k]['bytes']>0 for k in DESCRIPTORS),
            'complete current publication/parent descriptors must be in the artifact union')
    require(checked['parent_formal']==r['parent_formal']==parent['published_result']
        and parent['published_result']['path']=='output/full/results/ssb_local_sf500_model_aqp_ci.json'
        and parent['published_result']['sha256']==PARENT_RESULT_SHA
        and checked['model_path']==parent['model_path'] and checked['model_sha256']==parent['model_sha256']
        and checked['original_mismatch']==r['original_mismatch']==parent['original_mismatch']
        and parent['original_mismatch']['path']=='output/full/results/ssb_native_v2.json'
        and parent['original_mismatch']['sha256']==MISMATCH_SHA and parent['original_mismatch'] in checked['artifacts'],
        'original model, report and author-mismatch lineage differs')
    for path in PROVIDER_FILES:
        require(path in records and records[path]['sha256']==PINS[path],'complete current provider source closure required')
    home=Path(r['directory']).resolve();relative=home.relative_to(ROOT.resolve()).as_posix()
    require(re.fullmatch('output/full/ssb/local_sf500_continuation/runs/[0-9a-f]{20}',relative) is not None
        and checked['published_result']['path']=='output/full/results/ssb_local_sf500_canonical_aqp_ci.json'
        and checked['verification']['path']==relative+'/verification.json'
        and checked['verification_seal']['path']==relative+'/verification_seal.json'
        and checked['reverse']==r['reverse'] and checked['reverse']['path']==relative+'/reverse/verification.json'
        and checked['forward']==r['forward'] and checked['forward']['path']==
            'output/full/ssb/local_sf500_canonical/runs/93ea10ffd9ae559ab77e/forward/verification.json'
        and all(checked[k] in checked['artifacts'] for k in ('forward','reverse')),
        'distinct new reverse namespace and original accepted forward required')
    from full_ssb_local_tables import validate_formal_report
    from full_ssb_local_replay import validate_query_identities,QUERY_NAMES
    from full_ssb_replay import coverage
    validate_formal_report(r,checked['sample_rows'],configuration())
    validate_query_identities(r['queries'],(ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines(),QUERY_NAMES)
    require(checked['queries']==r['queries'] and r['coverage']==coverage(r)
        and sum(sum(g['truth'] is not None for g in q['groups']) for q in r['queries'])==2059
        and r['coverage']['truth_groups_total']==2059,'complete thirteen-query/2059-truth coverage required')
    compact={k:checked[k] for k in DESCRIPTORS+('forward','reverse','parent_formal','original_mismatch')}
    compact.update(artifacts_sha256=value_hash(checked['artifacts']),parent_snapshot_sha256=value_hash(parent),
        parent_artifacts_sha256=parent['closure_sha256'],adopted_forward=True,forward_reexecuted=False,
        execution_protocol=PROTOCOL,phase_model_loads=r['phase_model_loads'],phase_evaluator_calls=r['phase_evaluator_calls'])
    return dict(status=API_PASS,scope=SCOPE,execution_protocol=PROTOCOL,evaluation_variant=VARIANT,
        group_order_adapter_sha256=ADAPTER_SHA,continuation_validation=compact,
        source_snapshot=dict(published_result=checked['published_result'],sample_rows=checked['sample_rows'],population_rows=checked['population_rows']),
        coverage=r['coverage'],author_different_groups=1713,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,historical_reverse_accepted=False,**{k:False for k in READONLY})


def configuration():
    return dict(stage='LOCAL_SSB_SF500_CANONICAL_CONTINUATION_1M_AQP_CI',scope=SCOPE,
        cap=1000000,training_rows=dict(lineorder=1000000,dwdate=2556,customer=1000000,part=1000000,supplier=1000000),
        verify=accepted,result='ssb_local_sf500_canonical_aqp_ci.json',prefix='aqp_ssb_local_continuation_',
        pointer='ssb_local_continuation_tables_latest.json',policy_applied=False,
        evaluation_variant=VARIANT,group_order_adapter_sha256=ADAPTER_SHA,
        normalizer_scope='Model retains original n/p fact normalizer and full dimensions; independent reference uses exact N3000028242.',
        ci_scope='Canonical paired GROUP BY prototype; original RSPN CI and central90 Bernoulli reference from retained fact sample joined to full dimensions; count<10 excluded; one realization, not calibration.',
        evaluation_note='Continuation adopts the accepted forward and verifies a fresh reverse; the five saved1M models are unchanged.',
        helpers=['code/full_ssb_local_continuation_tables.py']+list(PINS))


def main():
    from full_ssb_local_tables import main as build
    build(configuration())


if __name__=='__main__':main()
