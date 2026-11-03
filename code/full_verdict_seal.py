"""Seal existing Verdict evidence; never connects to a DB or executes an engine.

Run with --write only after the focused tests. The default is a read-only audit.
"""
import sys
sys.dont_write_bytecode=True
import argparse
import json
from pathlib import Path
import full_verdict_audit as audit

ROOT=audit.ROOT


def record(path):
    path=Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=audit.digest(path))


def write_json(path,body):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(body,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    temporary.replace(path)


def seal_existing():
    out=ROOT/audit.OUT
    # Failed raw scientific evidence remains required. Unused build caches do not.
    attempts=sorted((out/'attempts').rglob('*'))
    write_json(out/'historical_attempts.json',dict(status='SEALED_FAILED_ATTEMPTS_RETAINED',
        artifacts=[record(p) for p in attempts if p.is_file()]))
    unused=[]
    for relative in ('data/verdict/m2','data/verdict/p/core/target'):
        path=(ROOT/relative).resolve()
        audit.require(ROOT in path.parents,'cache size path outside workspace')
        files=[p for p in path.rglob('*') if p.is_file()]
        unused.append(dict(path=relative,bytes=sum(p.stat().st_size for p in files),files=len(files),
                           required_for_execution=False,deleted=False))
    write_json(out/'cleanup.json',dict(status='BLOCKED_BY_AUTOMATIC_TOOL_POLICY',
        attempted_action='Remove only unused local Maven cache and build target intermediates',
        stated_reason='blocked by policy',deletion_executed=False,unused_paths=unused,
        total_unused_bytes=sum(p['bytes'] for p in unused),excluded_from_required_artifact_closure=True,
        evidence='Validated native PowerShell recursive deletion was rejected; no alternative deletion mechanism attempted. Parent informed user.'))
    for path,expected in audit.FIXED_HASHES.items():
        audit.require(audit.digest(ROOT/path)==expected,'fixed input/runtime hash differs: '+path)
    sqls=(ROOT/audit.SQL).read_text().splitlines();plans=audit.expected_plans(sqls)
    point=audit.read_physical_calls(out/'flights_nobound.tsv',plans)
    ci=audit.read_physical_calls(out/'flights_subsampling.tsv',plans)
    coverage=audit.validate_evaluation(audit.load(ROOT,audit.OUT+'flights_evaluation.json'),
        audit.load(ROOT,audit.TRUTH),sqls,point,ci)
    audit.require(audit.validate_gate(ROOT)==24,'incomplete golden gate')
    calls=audit.validate_receipts(ROOT);archive_counts=audit.check_archives(ROOT)
    test_log=out/'focused_tests.log';test_text=test_log.read_text()
    audit.require('28 passed' in test_text and 'failed' not in test_text.lower(),'complete focused-test evidence required')
    write_json(out/'verification.json',dict(status='PASS_INDEPENDENT_FIXED_SCOPE_EXTERNAL_AUDIT',
        actual_sample_rows=audit.SAMPLE_N,population_prior=audit.N,truth_group_count=331,
        group_coverage=coverage,historical_physical_calls=calls,archive_file_counts=archive_counts,
        tests=dict(passed=28,failed=0,artifact=record(test_log)),
        database_connected=False,engine_sql_executed=False,scientific_artifacts_modified=False,
        fixed_sql_sha256=audit.FIXED_HASHES[audit.SQL],fixed_truth_sha256=audit.FIXED_HASHES[audit.TRUTH],
        native_ci_confidence=.95,compound_adapter_ci='UNSUPPORTED_NO_COVARIANCE_MODEL',
        resource_limits=dict(java_rss_bytes=1024**3,total_new_disk_bytes=8*1024**3,sql_timeout_ms=120000),
        observed_peak_new_disk_bytes=audit.load(ROOT,audit.OUT+'flights_import.json')['budget_peak_bytes'],
        cache_cleanup_status='BLOCKED_BY_AUTOMATIC_TOOL_POLICY',
        scope='Existing uniform-sample execution only. Current files and historical execution/accounting snapshot; no current per-row DB content identity, original1B sampling cost, paper end-to-end timing or full-paper completion.'))
    required=audit.required_artifacts(ROOT)
    artifacts=[record(audit.safe_file(ROOT,path)) for path in sorted(required)]
    body=dict(status='SEALED_EXISTING_SAMPLE_ONLY_VERDICT',result_path=audit.OUT+'flights_evaluation.json',
        historical_physical_calls=calls,artifacts=artifacts,
        original_source=dict(archive=audit.SOURCE,directory='data/verdict/b',files=400),
        excluded_unused_caches=unused,scope='Existing uniform sample only; historical DB evidence, no implicit database access')
    body['seal_sha256']=audit.bhash(body);path=out/'final_seal.json';write_json(path,body)
    return audit.verify(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Write only outer audit/cleanup/seal receipts for existing evidence; never rerun science')
    args=parser.parse_args()
    print(json.dumps(seal_existing() if args.write else audit.verify(),indent=2))


if __name__=='__main__':main()
