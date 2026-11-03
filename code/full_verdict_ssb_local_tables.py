"""Thin LOCAL Verdict exports after exactly one fresh complete read-only audit."""
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'LOCAL_SSB_SF500_VERDICT_EXISTING_SAMPLE'
NAMES = ('Q1.1','Q1.2','Q1.3','Q2.1','Q2.2','Q2.3','Q3.1',
         'Q3.2','Q3.3','Q3.4','Q4.1','Q4.2','Q4.3')
MODES = ('nobound','subsampling')
PREFIX = 'fullpaper_verdict_ssb_local500_'
NO_COVARIANCE = 'UNSUPPORTED_NO_COVARIANCE_MODEL'
SOURCE = 'code/full_verdict_ssb_local_tables.py'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def safe_numbers(value):
    """Preserve nonfinite diagnostics as explicit strings in derived cells."""
    if isinstance(value, float) and not math.isfinite(value):
        return 'NaN' if math.isnan(value) else 'Infinity' if value > 0 else '-Infinity'
    if isinstance(value, dict):
        return {k:safe_numbers(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_numbers(v) for v in value]
    return value


def compact(value):
    return json.dumps(safe_numbers(value), sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)


def strict_json(payload):
    def unique(items):
        result = {}
        for key,value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite source JSON literal: '+value)
    return json.loads(payload.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def mean(values):
    return math.fsum(v/len(values) for v in values) if values else None


def scope(value):
    require(value.get('scope') == SCOPE and value.get('author_different_groups') == 1713
        and value.get('author_reproduction_complete') is False
        and value.get('full_paper_reproduction_complete') is False,
        'Explicit LOCAL SF500 author mismatch/incomplete scope required')


def summarize_groups(groups, sample_groups, *, query, mode, kind, source_error=None):
    """Truth union scoring; undefined/failed results stay visible, never dropped."""
    require(mode in MODES and kind in ('RAW','POINT_ADAPTER'), 'Known result kind/mode required')
    require(isinstance(groups,list) and isinstance(sample_groups,list), 'Explicit comparison lists required')
    sample = {}
    for item in sample_groups:
        key = compact(item['key'])
        require(key not in sample, 'Duplicate sample oracle group')
        sample[key] = item
    errors = {str(g['engine_error']) for g in groups if g.get('engine_error') is not None}
    if source_error is not None:
        errors.add(str(source_error))
    engine_error = '; '.join(sorted(errors)) if errors else None
    rows, scored, matched, seen = [], [], [], set()
    truths = missing = extras = zeros = invalid = invalid_metrics = 0
    for group in groups:
        key = compact(group['key']); require(key not in seen, 'Duplicate population group')
        seen.add(key)
        status, truth, prediction = group['status'], group['truth'], group['prediction']
        require(status in ('MATCHED','MISSING_MODEL_GROUP','EXTRA_MODEL_GROUP'), 'Unknown population presence status')
        is_missing, is_extra = status == 'MISSING_MODEL_GROUP', status == 'EXTRA_MODEL_GROUP'
        require(is_extra == (truth is None) and (truth is None or finite(truth)), 'Finite truth/presence contract differs')
        require(not is_missing or prediction is None, 'Missing group cannot contain a point')
        truths += not is_extra; missing += is_missing; extras += is_extra; zeros += truth == 0
        bad = not is_missing and not finite(prediction)
        invalid += bad
        error = None
        if engine_error is None and not is_extra and not bad:
            if is_missing:
                error = 1.
            elif truth != 0:
                error = abs(prediction-truth)/abs(truth)
            if error is not None:
                if finite(error):
                    scored.append(error)
                    if not is_missing:matched.append(error)
                else:
                    invalid_metrics += 1
                    error = None
        interval = group.get('native_ci95') if kind == 'RAW' else None
        require(kind == 'RAW' or group.get('native_ci95') is None, 'Point adapters cannot expose a composite interval')
        point_status = group.get('point_status')
        if point_status is None:
            point_status = 'MISSING_GROUP' if is_missing else 'FINITE' if finite(prediction) else 'INVALID'
        sample_row = sample.get(key)
        rows.append(dict(query=query,mode=mode,result_kind=kind,key_json=key,status=status,
            truth=truth,prediction=safe_numbers(prediction),point_status=point_status,
            prediction_finite=finite(prediction),zero_truth=truth == 0,
            scored_relative_error=error,missing_penalty_relative_error=1. if is_missing else None,
            engine_error=engine_error,sample_oracle_status=None if sample_row is None else sample_row.get('status'),
            sample_numeric_gate_pass=None if sample_row is None else sample_row.get('numeric_gate_pass'),
            native_ci_confidence=.95 if kind == 'RAW' and mode == 'subsampling' else None,
            native_ci95=safe_numbers(interval),native_ci_status=group.get('native_ci_status') if kind == 'RAW' else NO_COVARIANCE,
            native_ci95_covers_truth=group.get('native_ci95_covers_truth') if kind == 'RAW' and engine_error is None else None))
    if engine_error is not None:mean_status = 'ENGINE_ERROR'
    elif invalid or invalid_metrics:mean_status = 'INVALID_PREDICTION_OR_METRIC'
    elif zeros:mean_status = 'UNDEFINED_ZERO_TRUTH'
    elif not truths:mean_status = 'NO_TRUTH_GROUPS'
    else:mean_status = 'AVAILABLE_ALL_TRUTH_GROUPS_WITH_MISSING_PENALTY'
    summary = dict(query=query,mode=mode,result_kind=kind,truth_groups=truths,
        union_groups=len(rows),missing_groups=missing,extra_groups=extras,zero_truth_groups=zeros,
        invalid_predictions=invalid,invalid_relative_errors=invalid_metrics,engine_error=engine_error,
        mean_relative_error_with_missing_penalty=mean(scored) if mean_status.startswith('AVAILABLE_') else None,
        mean_status=mean_status,scored_truth_groups=len(scored),
        conditional_matched_mean_relative_error=mean(matched) if engine_error is None else None,
        conditional_matched_nonzero_truth_groups=len(matched),
        conditional_metric_scope='Finite matched nonzero truth groups only; excludes missing/extra/invalid/zero; explicit denominator',
        sample_numeric_gate_pass=bool(sample_groups) and all(g.get('numeric_gate_pass') is True for g in sample_groups),
        sample_oracle_union_groups=len(sample_groups),
        sample_gate_component=mode == 'nobound' and ((kind == 'RAW' and NAMES.index(query) < 10) or kind == 'POINT_ADAPTER'),
        native_ci_confidence=.95 if kind == 'RAW' and mode == 'subsampling' else None,
        native_ci_scope='Original native 95%; distinct from DeepDB central 90%' if kind == 'RAW' else NO_COVARIANCE,
        physical_calls_consumed=1 if kind == 'RAW' else 2,
        additional_native_calls_executed_by_export=0)
    return rows, summary


def call_identity(call):
    qno, mode, role = call['query_no'], call['mode'], call['role']
    require(type(qno) is int and 0 <= qno < 13 and mode in MODES,
            'Known ordered query number/mode required')
    require(role in (('RAW',) if qno < 10 else ('RAW','SUM_REVENUE','SUM_SUPPLYCOST')),
            'Known original call role required')
    require(call['query_id'] == NAMES[qno]
        and call['call_id'] == NAMES[qno]+'.'+role.lower()+'.'+mode
        and call['sql_sha256'] == digest(call['sql'].encode('utf-8')),
        'Original call/SQL identity differs')
    return qno,mode,role


def derive(report):
    scope(report)
    require(report.get('original_calls') == 38 and type(report.get('point_gate_pass')) is bool,
            'Complete 38-call evaluation and explicit point gate required')
    comparisons, adapters = report['comparisons'], report['adapters']
    require(len(comparisons) == 38 and len(adapters) == 6, 'Exactly38 original calls and6 derived point adapters required')
    indexed = {}
    for item in comparisons:
        identity = call_identity(item['call'])
        require(identity not in indexed, 'Duplicate original call')
        indexed[identity] = item
        if identity[2] != 'RAW':
            require(item.get('sample_groups') is None and item.get('population_groups') is None
                and item.get('sample_oracle_status') == 'UNAVAILABLE_COMPONENT_SUM_NOT_STORED'
                and item.get('population_status') == 'UNAVAILABLE_NO_MATCHING_COMPONENT_TRUTH',
                'Individual component SUM errors are unavailable, never inferred from profit moments')
    expected = {(q,mode,role) for mode in MODES for q in range(13)
        for role in (('RAW',) if q < 10 else ('RAW','SUM_REVENUE','SUM_SUPPLYCOST'))}
    require(set(indexed) == expected, 'Complete original physical call matrix required')
    native, adapter_index = {}, {}
    for item in adapters:
        identity = item['query_no'],item['mode']
        require(identity in {(q,m) for q in (10,11,12) for m in MODES}
            and identity not in adapter_index and item.get('combined_ci') == NO_COVARIANCE,
            'Unique complete profit adapters without composite CI required')
        adapter_index[identity] = item
        adapter = item['adapter']
        require((adapter['query_no'],adapter['mode']) == identity and adapter['ci_status'] == NO_COVARIANCE,
                'Adapter identity/CI scope differs')
        bodies = [adapter['raw_compound']]+adapter['children']
        require(len(bodies) == 3, 'Original raw plus two distinct native SUM results required')
        for body,role in zip(bodies,('RAW','SUM_REVENUE','SUM_SUPPLYCOST')):
            key = call_identity(body['call'])
            require(key == identity+(role,) and body['call'] == indexed[key]['call'],
                    'Embedded native original call identity differs')
            native[key] = body
    summary, raw_groups, adapter_groups, physical = [], [], [], []
    gate_groups = []
    for mode in MODES:
        for qno,query in enumerate(NAMES):
            item = indexed[qno,mode,'RAW']; body = native.get((qno,mode,'RAW'))
            error = None if body is None else body['error']
            rows, row = summarize_groups(item['population_groups'],item['sample_groups'],
                query=query,mode=mode,kind='RAW',source_error=error)
            row.update(source_status='COMPARISON_ONLY_NATIVE_RESULT_BODY_NOT_RETAINED' if body is None else body['status'],
                sample_oracle_status=item['sample_oracle_status'],population_status=item['population_status'],
                raw_compound_sum_unadapted=qno >= 10)
            raw_groups.extend(rows);summary.append(row)
            if mode == 'nobound' and qno < 10:gate_groups.extend(item['sample_groups'])
            if qno >= 10:
                adapted = adapter_index[qno,mode]
                adapter = adapted['adapter']
                rows, row = summarize_groups(adapted['population_groups'],adapted['sample_groups'],
                    query=query,mode=mode,kind='POINT_ADAPTER',
                    source_error=None if adapter['status'] == 'POINT_ADAPTER_RETURNED' else 'CHILD_ENGINE_ERROR')
                row.update(source_status=adapter['status'],sample_oracle_status='AVAILABLE_EXACT_RETAINED_EXPRESSION_SUM',
                    population_status='AVAILABLE_LOCAL_FULL_EXPRESSION_TRUTH',raw_compound_sum_unadapted=False)
                adapter_groups.extend(rows);summary.append(row)
                if mode == 'nobound':gate_groups.extend(adapted['sample_groups'])
            for role in (('RAW',) if qno < 10 else ('RAW','SUM_REVENUE','SUM_SUPPLYCOST')):
                item = indexed[qno,mode,role]; call = item['call']; body = native.get((qno,mode,role))
                groups = item.get('population_groups')
                errors = sorted({str(g['engine_error']) for g in groups or [] if g.get('engine_error') is not None})
                physical.append(dict(query=query,mode=mode,role=role,call_id=call['call_id'],
                    sql=call['sql'],sql_sha256=call['sql_sha256'],sample_oracle_status=item['sample_oracle_status'],
                    population_status=item['population_status'],sample_relative_error=None,population_relative_error=None,
                    metric_location='raw_groups.csv' if role == 'RAW' else 'UNAVAILABLE_NO_INDIVIDUAL_COMPONENT_MOMENTS_OR_TRUTH',
                    native_result_detail_status='COMPARISON_ONLY_NATIVE_BODY_NOT_RETAINED' if body is None else 'AVAILABLE_IN_SEALED_ADAPTER_BRANCH',
                    native_status=None if body is None else body['status'],
                    native_error=('; '.join(errors) if errors else None) if body is None else body['error'],
                    native_elapsed_ns=None if body is None else body['elapsed_ns'],
                    native_output_groups=None if body is None else len(body['rows']),
                    native_rows_json=None if body is None else compact(body['rows']),
                    native_ci_confidence=.95 if mode == 'subsampling' else None,
                    physical_native_calls=1,new_calls_executed_by_export=0))
    point_gate = bool(gate_groups) and all(g.get('numeric_gate_pass') is True for g in gate_groups)
    require(point_gate is report['point_gate_pass'], 'Recorded sample gate differs from Q1-Q3 raw plus Q4 point adapters')
    expected_status = 'PASS_LOCAL_VERDICT_SAMPLE_SCALING_WITH_EXPLICIT_GAPS' if point_gate else 'FAIL_LOCAL_VERDICT_SAMPLE_SCALING'
    require(report['status'] == expected_status, 'Recorded sample-gate evaluation status differs')
    return dict(query_summary=summary,raw_groups=raw_groups,adapter_groups=adapter_groups,
                physical_calls=physical,sample_gate_pass=point_gate)


def record(path):
    path = Path(path).resolve();root = ROOT.resolve()
    require(root in path.parents and path.is_file(), 'Artifact must be physically project-contained')
    payload = path.read_bytes()
    return dict(path=path.relative_to(root).as_posix(),bytes=len(payload),sha256=digest(payload))


def checked_payload(expected_path, descriptor):
    declared = Path(expected_path)
    expected_path = declared.resolve()
    require(expected_path == declared and ROOT.resolve() in expected_path.parents,
            'Accepted evaluation must retain its exact physical run namespace')
    require(isinstance(descriptor,dict) and set(descriptor) == {'path','bytes','sha256'}
        and type(descriptor['bytes']) is int and descriptor['bytes'] >= 0
        and descriptor['path'] == expected_path.relative_to(ROOT.resolve()).as_posix(),
        'Exact accepted evaluation descriptor/path required')
    require(expected_path.is_file(), 'Accepted evaluation artifact missing')
    payload = expected_path.read_bytes()
    require(len(payload) == descriptor['bytes'] and digest(payload) == descriptor['sha256'],
            'Accepted evaluation physical bytes/SHA differ')
    return payload


def csv_bytes(rows):
    require(bool(rows), 'Nonempty derived table required')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k:compact(v) if isinstance(v,(list,dict)) else safe_numbers(v) for k,v in row.items()})
    return stream.getvalue().encode('utf-8')


def json_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8')


def report_bytes(accepted, report, derived):
    lines = ['# LOCAL SSB SF500 Verdict: retained-sample results','',
        'LOCAL generated population: 3,000,028,242 rows; retained fact sample: 9,996,946 rows.',
        '1,713 of 2,059 author truth groups differ. Author reproduction and full-paper completion remain false.','',
        'Verdict registers the realized n/N sampling fraction and scales points by N/n. Original DeepDB retains its n/p normalizer; the two normalizers are not silently equated.',
        'A fresh complete read-only verifier accepted the source run before this export. No native calls, database access, sampling, training or inference are executed by this exporter.',
        'The 38 original physical calls are recorded separately. The 32 query rows contain 26 RAW results and 6 external two-SUM point adapters; adapters reuse child calls and add no physical calls.',
        'The sample scaling gate uses Q1-Q3 RAW nobound results and Q4 point adapters. Original Q4 compound-SUM behavior remains visible as RAW evidence.',
        'Individual component SUM errors are unavailable: retained profit moments do not identify their separate sample sums or population truths.',
        'Verdict native 95% intervals remain distinct from DeepDB central 90%. Composite adapter intervals are unavailable: no covariance model. No repeated-sampling calibration or latency ranking is claimed.',
        'All-truth means assign 100% relative error to missing groups, exclude extra groups from the truth denominator, and are suppressed on engine errors, invalid predictions/metrics, or zero truth (relative error undefined). Zero, missing, extra, nonfinite and failed records remain in the CSVs.',
        'Conditional matched means include only finite matched nonzero truth groups and report their denominator separately. They are not all-truth means.',
        'Q1-Q3 native result bodies/timings are absent from the sealed evaluation; unavailable fields stay empty. Q4 RAW/child bodies are retained in physical_calls.csv. Native error rows remain diagnostics.','',
        'Sample gate: '+str(derived['sample_gate_pass'])+'. Evaluation: '+report['status']+'.',
        'Recorded engine-error calls: '+str(report['engine_error_calls'])+'.',
        'Recorded unavailable native CI rows: '+str(report['unavailable_native_ci_rows'])+'.',
        'Timing scope: '+report['timing_scope'],
        'Accepted evaluation SHA256: `'+accepted['evaluation']['sha256']+'`.','',
        'Files: query_summary.csv, raw_groups.csv, adapter_groups.csv, physical_calls.csv and source_manifest.json.',
        'The public copies use the fullpaper_verdict_ssb_local500_ prefix. Their exact bytes and source identities are recorded in the source manifest.','']
    return '\n'.join(lines).encode('utf-8')


def atomic_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('xb') as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


def export(name):
    require(isinstance(name,str) and re.fullmatch('[a-zA-Z0-9_-]{1,32}',name) is not None,
            'Fresh safe LOCAL run name required')
    root = ROOT.resolve()
    home = root/'output/full/verdict_ssb/local_sf500/runs'/name
    require(home.resolve() == home, 'LOCAL run path must not redirect outside its fixed namespace')
    from full_verdict_ssb_local_run import verify
    accepted = verify(home)  # Exactly one fresh complete source F, including on repeated exports.
    scope(accepted)
    require(accepted.get('status') == 'PASS_READONLY_LOCAL_VERDICT_EVIDENCE_WITH_AUTHOR_MISMATCH'
        and accepted.get('original_calls') == 38 and accepted.get('population_rows') == 3000028242
        and accepted.get('sample_rows') == 9996946
        and all(accepted.get(k) is False for k in ('database_connected','processes_executed','scientific_calls_executed')),
        'Complete fresh read-only LOCAL Verdict acceptance required')
    payload = checked_payload(home/'evaluation.json',accepted['evaluation'])
    report = strict_json(payload);derived = derive(report)
    require(accepted['evaluation_status'] == report['status'] and accepted['point_gate_pass'] is derived['sample_gate_pass'],
            'Accepted evaluation status/sample gate differs')
    binding = dict(schema='local_verdict_ssb_derived_tables_v1',source_acceptance=accepted,
                   exporter=record(root/SOURCE),scope=SCOPE)
    binding_sha = digest(compact(binding).encode('utf-8'))
    directory = root/'output/full/figures'/('local_verdict_ssb_sf500_'+binding_sha[:20])
    files = {name+'.csv':csv_bytes(derived[name]) for name in ('query_summary','raw_groups','adapter_groups','physical_calls')}
    files['RESULTS.md'] = report_bytes(accepted,report,derived)
    artifacts = [dict(path=(directory/name).relative_to(root).as_posix(),bytes=len(body),sha256=digest(body)) for name,body in sorted(files.items())]
    manifest = dict(status='PASS_LOCAL_VERDICT_DERIVED_TABLES_WITH_EXPLICIT_GAPS',schema=binding['schema'],
        binding_sha256=binding_sha,exporter=binding['exporter'],source_acceptance=accepted,
        scope=SCOPE,author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        sample_gate_pass=derived['sample_gate_pass'],evaluation_status=report['status'],
        original_physical_calls=38,query_summary_rows=32,
        row_counts={name:len(derived[name]) for name in ('query_summary','raw_groups','adapter_groups','physical_calls')},
        native_ci_confidence=.95,deepdb_ci_confidence_comparison_only=.90,deepdb_intervals_exported=False,
        adapter_ci=NO_COVARIANCE,individual_component_errors='UNAVAILABLE_NO_INDIVIDUAL_COMPONENT_MOMENTS_OR_TRUTH',
        original_engine_error_calls=report['engine_error_calls'],unavailable_native_ci_rows=report['unavailable_native_ci_rows'],
        complete_verifier_calls_this_export=1,additional_verifier_calls=0,native_calls_executed_by_export=0,artifacts=artifacts,
        public_copy_policy='Only these derived files plus this manifest; copied byte-for-byte with fullpaper_verdict_ssb_local500_ prefix')
    files['source_manifest.json'] = json_bytes(manifest)
    require(checked_payload(home/'evaluation.json',accepted['evaluation']) == payload,
            'Accepted evaluation changed during derivation')
    if directory.exists():
        require(directory.is_dir() and {p.name for p in directory.iterdir()} == set(files)
            and all((directory/name).is_file() and (directory/name).resolve() == directory/name
                    and (directory/name).read_bytes() == body for name,body in files.items()),
            'existing derived bundle differs; refuse repair or overwrite')
    else:
        directory.mkdir(parents=True,exist_ok=False)
        for name,body in files.items():atomic_bytes(directory/name,body)
    public = []
    for name,body in sorted(files.items()):
        target = root/'output/results'/(PREFIX+name)
        if not target.exists() or target.read_bytes() != body:atomic_bytes(target,body)
        public.append(dict(record(target),source=record(directory/name)))
    return dict(status=manifest['status'],manifest=record(directory/'source_manifest.json'),
                public_files=public,scope=SCOPE,author_different_groups=1713,
                author_reproduction_complete=False,full_paper_reproduction_complete=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True,help='Completed accepted LOCAL run name; failed runs cannot export')
    args = parser.parse_args(argv)
    print(json.dumps(export(args.name),sort_keys=True,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
