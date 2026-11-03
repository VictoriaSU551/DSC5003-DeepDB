"""Read-only CURRENT POSTHOC sqlparse binding above the frozen Flights replay.

This does not establish which parser bytes the historical 24 calls used.
No producer, worker, model load or receipt-repair path exists in verify().
"""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import sys

import full_flights_replay as legacy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/full/flights-replay-audit'
LEGACY_MODULE_SHA='e4c97c63c74e64edb6cb404f3c9e35f249bdf94653df2d4026769d8a7bab4762'
LEGACY_FINAL_SHA='c6bd2cea5f75d8a7c57f8fc7228854babf405bd35d6822662b15558aa0b70ee6'
LEGACY_VERIFICATION_SHA='49a534196321f53ee66cb06a220b2942b087dcf7c00c394db4f82b72a06244ec'
RECEIPT_STATUS='PASS_CURRENT_POSTHOC_SQLPARSE_AND_FLIGHTS_REPLAY_AUDIT'
FINAL_STATUS='SEALED_CURRENT_POSTHOC_FLIGHTS_PARSER_BINDING'
STATUS='PASS_READ_ONLY_FLIGHTS_REPLAY_WITH_CURRENT_PARSER_BINDING'
SCOPE='CURRENT_POSTHOC_NOT_HISTORICAL_PARSER_PROOF'
SOURCES=('code/full_flights_replay_audit.py','code/tests/test_full_flights_replay_audit.py',
         'docs/FULL_FLIGHTS_REPLAY_AUDIT.md','code/full_flights_replay.py',
         'code/evaluation/utils.py','code/full_inventory.py','code/full_common.py')
CANONICAL=ROOT/'output/full/results/paper_proxy_public_scale_rdc_n10000000_b0p5_evaluation_v3.json'
SSB=ROOT/'output/full/ssb/models/.sf2_bounded_b2882fff98a26652_20046e789fafdc04_prepared_guard_c4a2d6853e6ab235'


def validate_source_set(records,root):
    if not isinstance(records,list) or not records:raise ValueError('Source inventory is empty')
    names=[row['path'].replace('\\','/').casefold() for row in records]
    if len(names)!=len(set(names)):raise ValueError('Source inventory contains duplicate/case-alias paths')
    legacy.validate_assets(records,root)


def package_snapshot(root,distribution_version,module_version):
    root=Path(root).resolve()
    if not isinstance(distribution_version,str) or not distribution_version or distribution_version!=module_version:
        raise ValueError('Distribution and loaded parser versions are empty or disagree')
    paths=sorted(root.rglob('*.py'))
    sources=[legacy.record(path,root) for path in paths]
    validate_source_set(sources,root)
    if '__init__.py' not in {row['path'] for row in sources}:raise ValueError('Parser package entry source is missing')
    return dict(distribution_version=distribution_version,module_version=module_version,root=str(root),
                python_sources=sources,python_source_count=len(sources),python_sources_sha256=legacy.digest(sources))


def require_package(expected,current):
    validate_source_set(expected['python_sources'],Path(expected['root']))
    validate_source_set(current['python_sources'],Path(current['root']))
    if expected!=current:raise ValueError('Current parser version/location/complete Python source set changed')


def compare_peer_dependencies(parser,canonical,ssb):
    version=parser['distribution_version']
    current={row['path']:row['sha256'] for row in parser['python_sources']}
    if (not current or canonical['versions'].get('sqlparse')!=version or ssb['versions'].get('sqlparse')!=version
            or not ssb.get('sqlparse_sources') or ssb['sqlparse_sources']!=current):
        raise ValueError('Current parser differs from recorded canonical version or full SSB source set')
    if canonical.get('sqlparse_sources'):
        if canonical['sqlparse_sources']!=current:raise ValueError('Canonical parser source set differs')
        canonical_status='CURRENT_VERSION_AND_COMPLETE_PYTHON_SOURCES_MATCH'
    else:canonical_status='VERSION_ONLY_SOURCE_SET_NOT_RECORDED'
    return dict(canonical=canonical_status,ssb='CURRENT_VERSION_AND_COMPLETE_PYTHON_SOURCES_MATCH',
                proves_historical_flights_parser=False)


def current_binding():
    import sqlparse
    distribution=importlib.metadata.distribution('sqlparse')
    root=Path(sqlparse.__file__).resolve().parent
    parser=package_snapshot(root,distribution.version,sqlparse.__version__)
    if Path(distribution.locate_file('sqlparse/__init__.py')).resolve()!=Path(sqlparse.__file__).resolve():
        raise ValueError('Loaded parser source does not belong to the named distribution')
    metadata=distribution.read_text('METADATA')
    if not metadata:raise ValueError('Parser distribution METADATA is empty')
    parser.update(module_entry=legacy.record(sqlparse.__file__,root),
                  distribution_metadata_sha256=hashlib.sha256(metadata.encode()).hexdigest())
    if legacy.sha(ROOT/'code/full_flights_replay.py')!=LEGACY_MODULE_SHA or legacy.sha(legacy.OUT/'final_seal.json')!=LEGACY_FINAL_SHA:
        raise ValueError('Frozen Flights module or54-file outer seal changed')
    canonical=legacy.read_json(CANONICAL);legacy.require_seal(canonical)
    if canonical.get('status')!='PASS':raise ValueError('Canonical peer receipt is not PASS')
    ssb=legacy.read_json(SSB/'receipt.json');lifecycle=legacy.read_json(SSB/'lifecycle.json')
    if (ssb.get('status')!='PASS' or lifecycle.get('status')!='PASS' or lifecycle.get('binding')!=ssb.get('binding')
            or lifecycle.get('receipt_sha256')!=legacy.sha(SSB/'receipt.json')):
        raise ValueError('Recorded SSB peer receipt/lifecycle checksum differs')
    comparison=compare_peer_dependencies(parser,canonical['configuration']['dependencies'],ssb['binding']['dependencies'])
    sources=[legacy.record(ROOT/name) for name in SOURCES];validate_source_set(sources,ROOT)
    return dict(scope=SCOPE,parser_bound_during_original_inference=False,sqlparse=parser,outer_sources=sources,
        frozen_replay_module=legacy.record(ROOT/'code/full_flights_replay.py'),
        frozen_replay_outer_seal=legacy.record(legacy.OUT/'final_seal.json'),
        peer_comparison=comparison,peer_records=[legacy.record(path) for path in [CANONICAL,SSB/'receipt.json',SSB/'lifecycle.json']],
        runtime=dict(python=sys.version,executable=legacy.record(sys.executable)))


def checked_legacy_audit():
    if legacy.sha(ROOT/'code/full_flights_replay.py')!=LEGACY_MODULE_SHA or legacy.sha(legacy.OUT/'final_seal.json')!=LEGACY_FINAL_SHA:
        raise ValueError('Frozen accepted replay source/seal changed')
    result=legacy.audit()
    if (result.get('status')!='PASS_READ_ONLY_FLIGHTS_REVERSE_AUDIT' or result.get('actual_new_predictions')!=0
            or result.get('queries')!=12 or result.get('groups')!=331 or result.get('successful_prior_calls')!=24
            or result.get('verification',{}).get('sha256')!=LEGACY_VERIFICATION_SHA
            or result.get('final_seal_sha256')!=LEGACY_FINAL_SHA):raise ValueError('Frozen legacy read-only audit result differs')
    return result


def verify():
    # Missing evidence fails before runtime discovery, delegation or any mkdir.
    receipt_path=OUT/'verification.json';receipt=legacy.read_json(receipt_path);legacy.require_seal(receipt)
    final_path=OUT/'final_seal.json';final=legacy.read_json(final_path);legacy.require_seal(final)
    if receipt.get('status')!=RECEIPT_STATUS or final.get('status')!=FINAL_STATUS:
        raise ValueError('Posthoc parser verification/final status differs')
    assets=final.get('artifacts',[]);paths=[item['path'] for item in assets]
    actual={path.relative_to(OUT).as_posix() for path in OUT.rglob('*') if path.is_file() and path!=final_path}
    if not paths or len(set(paths))!=len(paths) or set(paths)!=actual:raise ValueError('Posthoc artifact namespace is empty or incomplete')
    legacy.validate_assets(assets,OUT);validate_source_set(final['sources'],ROOT)
    current=current_binding();require_package(receipt['current_binding']['sqlparse'],current['sqlparse'])
    if current!=receipt['current_binding']:raise ValueError('Current posthoc parser/outer source/peer binding differs')
    result=checked_legacy_audit()
    if result!=receipt['legacy_audit_result']:raise ValueError('Fresh frozen read-only audit no longer matches its captured result')
    if current_binding()!=current:raise ValueError('Parser/outer sources changed during read-only verification')
    return dict(result,status=STATUS,legacy_status=result['status'],parser_binding_status='PASS_CURRENT_POSTHOC_PARSER_BINDING',
        parser_bound_during_original_inference=False,parser_binding_scope=SCOPE,parser_binding=current['sqlparse'],
        posthoc_verification=legacy.record(receipt_path,ROOT),posthoc_final_seal=legacy.record(final_path,ROOT))


def main():
    import json
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',nargs='?',default='verify',choices=['verify'])
    parser.parse_args();result=verify()
    print(json.dumps({key:value for key,value in result.items() if key not in ('parser_binding','resource')},sort_keys=True))


if __name__=='__main__':main()
