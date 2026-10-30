"""Derive an honest full-paper coverage ledger from verified stage receipts."""
import json
from datetime import datetime, timezone
import os
from pathlib import Path

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import workload_files
from full_canonical_acceptance import verify_current as verify_canonical_evaluation
from full_evaluation_v3 import PROTOCOL


def progress_json(path, default=None):
    """Minimize Windows sharing conflicts; writer retries remain necessary."""
    path = Path(path)
    if not path.exists():
        return default
    if os.name != 'nt':
        return load_json(path, default)
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    handle = kernel.CreateFileW(str(path.resolve()), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    with os.fdopen(descriptor, 'rb') as stream:
        content = stream.read()
    return json.loads(content.decode('utf-8'))


def verified_evaluation(label, queries):
    """Legacy v2 API, retained for the frozen historical postprocessor only."""
    from full_evidence_audit import require_current_audit
    path = FULL / 'results' / (label + '_evaluation_v2.json')
    stage = dict(status='PENDING', evidence=path.relative_to(ROOT).as_posix())
    if not path.exists():
        return stage
    try:
        require_current_audit(label, queries)
        result = load_json(path)
        stage.update(status='PASS_LOCAL_VARIANT', queries=queries,
                     job_light_qerror=result['groups']['job_light']['q_error'], prediction_generation='v2',
                     scope='Historical v2 with fresh dependency replay; not canonical four-hash-seed acceptance')
    except (KeyError, ValueError, OSError) as error:
        stage.update(status='EVIDENCE_INVALID', reason=str(error))
    return stage


def verified_current_evaluation(label, queries):
    path = FULL / 'results' / (label + '_evaluation_v3.json')
    result = load_json(path)
    stage = dict(status='PENDING', evidence=path.relative_to(ROOT).as_posix())
    if result is None:
        stage['reason'] = 'canonical traversal and four hash-seed inference gate pending; v1/v2 are historical'
        return stage
    replay_paths = [FULL / 'results' / (label + '_replay_v3_seed%d.json' % seed) for seed in [1, 2, 3]]
    if not all(p.exists() for p in replay_paths) or not (FULL / 'results/canonical_inference_verification.json').exists():
        stage['reason'] = 'canonical evaluation exists; three fresh hash-seed reverse replays pending'
        return stage
    try:
        result = verify_canonical_evaluation(label, queries)
        stage.update(status='PASS_LOCAL_VARIANT', queries=queries,
                     job_light_qerror=result['groups']['job_light']['q_error'],
                     independently_replayed=True, hash_seeds=[0, 1, 2, 3], prediction_generation='v3')
    except (KeyError, ValueError, OSError) as error:
        stage.update(status='EVIDENCE_INVALID', reason=str(error))
    return stage


def ssb_model_stages():
    evidence = 'output/full/results/ssb_model_aqp_ci.json; output/full/ssb/replay/verification.json'
    model = dict(status='PENDING', evidence=evidence,
        scope='SF500, single-table RSPNs capped1M/table; exact population truth, original n/p model normalizer')
    intervals = dict(status='PENDING', evidence=evidence,
        scope='Actual retained fact sample for central90 reference; count<10 excluded; one sample, not coverage calibration')
    path = FULL/'results/ssb_model_aqp_ci.json'
    if not path.exists():
        return model, intervals
    if load_json(path).get('status') != 'PASS':
        model['status'] = intervals['status'] = 'FORMAL_QUERY_ERRORS_RECORDED'
        return model, intervals
    model['status'] = intervals['status'] = 'FORMAL_COMPLETE_REPLAY_PENDING'
    if not (FULL/'ssb/replay/verification.json').exists():
        return model, intervals
    try:
        from full_ssb_replay import verify
        accepted = verify()
        report = load_json(path)
        if (accepted['status'] != 'PASS_INDEPENDENT_REVERSE_REPLAY_CURRENT_DEPENDENCIES'
                or file_sha256(path) != accepted['source_snapshot']['formal_result_sha256']):
            raise ValueError('SSB formal report does not match its replay acceptance')
        coverage = accepted['coverage']
        model_gaps = any(coverage[k] for k in ['missing_model_groups_total', 'extra_model_groups_total', 'nonfinite_point_groups'])
        interval_gaps = model_gaps or any(coverage[k] for k in ['nonfinite_original_ci_groups', 'missing_or_nonfinite_model_interval_groups'])
        model.update(status='PASS_REPLAY_WITH_GROUP_GAPS' if model_gaps else 'PASS_VERIFIED_LOCAL_SF500_AQP',
            population_rows=report['inputs']['population_rows'], actual_fact_sample_rows=report['inputs']['sample_rows'],
            training_rows={t['table']:t['actual_training_rows'] for t in report['training_tables']},
            queries=13, coverage=coverage)
        intervals.update(status='PASS_REPLAY_WITH_CI_GAPS' if interval_gaps else 'PASS_LOCAL_CI_WITH_EXCLUSIONS',
            confidence_fact_sample_rows=report['inputs']['sample_rows'],
            eligible_truth_groups=coverage['reference_ci_eligible_truth_groups'],
            excluded_truth_groups=coverage['reference_ci_excluded_truth_groups'], coverage=coverage)
        if not coverage['reference_ci_eligible_truth_groups']:
            intervals['status'] = 'NO_ELIGIBLE_REFERENCE_INTERVALS'
    except (KeyError, ValueError, OSError) as error:
        model.update(status='EVIDENCE_INVALID', reason=str(error))
        intervals.update(status='EVIDENCE_INVALID', reason=str(error))
    return model, intervals


def ssb_generation_stage(checkpoint, result):
    stage = dict(status='PARTIAL_CHECKPOINT', generated_rows=checkpoint.get('rows', 0),
        requested_rows=3000028242, sample_rows=checkpoint.get('sample_rows', 0),
        committed_shards=len(checkpoint.get('committed_shards', [])),
        scope='Requires all author integer aggregates and exact fact row count at completion')
    if result.get('status') == 'PASS':
        stage['status'] = 'PASS_AUTHOR_POPULATION'
    elif result.get('status') == 'MISMATCH':
        stage.update(status='FAILED_AUTHOR_POPULATION_GATE',
            author_aggregate_value_differences=len(result.get('author_truth_comparison', {}).get('different_values', [])),
            scope='Traversal completed but author row count/truth differs. Original formal model gate remains closed.')
    return stage


def main():
    stages = {}
    inventory = load_json(FULL / 'results/source_inventory.json', {})
    stages['paper_and_public_input_audit'] = dict(status=inventory.get('status', 'PENDING'),
        evidence='docs/FULL_REPRODUCTION_PROTOCOL.md; output/full/results/source_inventory.json')
    pg = load_json(FULL / 'results/postgres_job_light_verification.json', {})
    stages['independent_70_truths_and_postgres_11_5'] = dict(
        status='PASS' if pg.get('all_official_truths_independently_matched') and pg.get('queries') == 70 else 'PENDING',
        evidence='output/full/results/postgres_job_light_verification.json')
    for label, count in [('rdc_n100000_b0p0', 70), ('joblight_single_n10000000', 70),
                         ('paper_proxy_joblight_rdc_n10000000_b0p5', 70),
                         ('public_scale_rdc_n100000_b0p0', 753),
                         ('public_scale_rdc_n10000000_b0p5', 753)]:
        stages[label] = verified_current_evaluation(label, count)
    stages['sample_size_sweep_public_profile'] = {str(n): verified_current_evaluation(
        'public_scale_rdc_n%d_b%s' % (n, '0p5' if n == 10000000 else '0p0'), 753)
        for n in [1000, 10000, 100000, 1000000, 10000000]}
    stages['budget_sweep_public_paper_cost_proxy'] = {str(b): verified_current_evaluation(
        'paper_proxy_public_scale_rdc_n10000000_b%s' % str(b).replace('.', 'p'), 753)
        for b in [0., .5, 1., 2., 3.]}
    stages['temporal_10m_joblight'] = {str(c): verified_current_evaluation(
        'temporal_joblight_rdc_n10000000_b0p0_year%d' % c, 70) for c in [2019, 2011, 2009, 2004, 1991]}
    stages['literal_point3_ensemble_threshold'] = {profile: {str(b): verified_current_evaluation(
        'threshold03_%s_rdc_n10000000_b%s' % (profile, str(b).replace('.', 'p')), 70 if profile == 'joblight' else 753)
        for b in [0., .5, 1., 2., 3.]} for profile in ['joblight', 'public_scale']}
    stages['all_relationships_joblight'] = {str(n): verified_current_evaluation(
        'relationship_n%d_b0p0' % n, 70) for n in [100000, 10000000]}
    cpp = load_json(FULL / 'results/cpp_verification.json', {})
    stages['cpp_existing_model_correctness'] = dict(status=cpp.get('status', 'PENDING'),
        scope='Existing 1M model correctness and repeated JOB-light timing; not full Figure 8',
        evidence='output/full/results/cpp_verification.json')
    aqp = load_json(FULL / 'results/aqp_sources.json', {})
    stages['flights_source_5m'] = dict(status=aqp.get('status', 'PENDING'),
                                    scope='Source inputs only; not generated 1B')
    golden = load_json(FULL / 'flights/golden-200k/golden_validation.json', {})
    stages['flights_streaming_golden_200k'] = dict(status=golden.get('status', 'PENDING'),
                                               scope='Adapter correctness at 200K, not full-size experiment')
    flight = progress_json(FULL / 'flights/flights-1b/checkpoint.json', {})
    generated = load_json(FULL / 'flights/flights-1b/generation_result.json', {})
    stages['flights_1b_generated'] = dict(
        status='PASS_ORIGINAL_SCALE_GENERATION' if generated.get('paper_scale_reached') else 'PARTIAL_CHECKPOINT',
        generated_rows=flight.get('rows_generated', 0), requested_rows=1000000000,
        sample_rows=flight.get('sample_rows', 0), committed_batches=flight.get('next_batch', 0),
        scope='Streaming population traversal and own exact truth, no full population database retained')
    ssb = progress_json(FULL / 'ssb/paper/sf500/checkpoint.json', {})
    ssb_result = load_json(FULL / 'results/ssb_paper.json', {})
    stages['ssb_sf500_generated'] = ssb_generation_stage(ssb, ssb_result)
    mscn_dir = FULL / 'mscn/table1_job_light_seed1'
    mscn = progress_json(mscn_dir / 'checkpoints/latest.json', {})
    mscn_eval = load_json(mscn_dir / 'evaluation.json', {})
    from full_mscn_verify import reuse_verification
    try:
        mscn_final = reuse_verification(mscn_dir) or {}
    except (KeyError, ValueError, OSError) as error:
        mscn_final = dict(status='EVIDENCE_INVALID', reason=str(error))
    stages['mscn_100_epochs'] = dict(
        status='PASS_LOCAL_TABLE1_RERUN' if mscn_eval.get('status') == 'TABLE1_LOCAL_RERUN_COMPLETE'
                     and mscn_eval.get('completed_epochs') == mscn.get('completed_epochs') == 100
                     and mscn_final.get('status') == 'PASS' else 'PARTIAL_CHECKPOINT',
        committed_epochs=mscn.get('completed_epochs', 0), target_epochs=100,
        independent_final_audit=mscn_final.get('status', 'PENDING'), final_qerror=mscn_final.get('qerror'),
        scope='Official matched 100K input bitmaps; public 683 generalization bitmaps not recovered')
    rebuilt = progress_json(FULL / 'mscn/rebuilt_seed1/results/checkpoints/latest.json', {})
    rebuilt_stage = dict(
        status='PARTIAL_CHECKPOINT', committed_epochs=rebuilt.get('completed_epochs', 0), target_epochs=100,
        scope='Separate rebuilt same-sample train/evaluation bitmaps; final 753-query and local-truth acceptance required')
    if (FULL / 'mscn/rebuilt_seed1/results/final_seal.json').exists():
        try:
            from full_mscn_rebuilt_audit import verify as verify_rebuilt
            audited = verify_rebuilt()
            rebuilt_stage.update(status='PASS_SEALED_REBUILT_100_EPOCHS_LOCAL_WORKLOAD', queries=audited['queries'],
                                 public_3to6=audited['public_3to6'], public_4to6=audited['public_4to6'])
        except (KeyError, ValueError, OSError) as error:
            rebuilt_stage.update(status='EVIDENCE_INVALID', reason=str(error))
    stages['mscn_rebuilt_consistent_sample_generalization'] = rebuilt_stage
    cpp_scale = load_json(FULL / 'cpp-scale/public_scale_verification.json', {})
    stages['cpp_5spn_public_workload'] = dict(status=cpp_scale.get('cold_cache_python_cpp_gate', 'PENDING'),
        queries=cpp_scale.get('queries', 0),
        historical_cache_gate=cpp_scale.get('historical_python_reference_gate', 'PENDING'),
        scope='Same cold-cache path differential, separate from later model-aware v2 gate')
    sealed_path = FULL / 'cpp-scale/sealed_paper_proxy_6spn.json'
    sealed = load_json(sealed_path, {})
    native = dict(status='PENDING', evidence=sealed_path.relative_to(ROOT).as_posix())
    if sealed.get('status') == 'SEALED_PASS':
        try:
            for artifact in sealed['assets']:
                path = (sealed_path.parent / artifact['path']).resolve()
                if (sealed_path.parent.resolve() not in path.parents
                        or path.stat().st_size != artifact['bytes']
                        or file_sha256(path) != artifact['sha256']):
                    raise ValueError('C++ seal artifact differs')
            receipts = [load_json(sealed_path.parent / item['path']) for item in sealed['assets']]
            verification = next(r for r in receipts if 'python_v2_reference_gate' in r)
            training = load_json(FULL / 'results' / (verification['training_label'] + '_training.json'))
            if (verification['status'] != 'PASS' or verification['python_v2_reference_gate'] != 'PASS'
                    or verification['cold_cache_python_cpp_gate'] != 'PASS'
                    or not verification['original_model_unchanged']
                    or sealed['model_sha256'] != training['model_sha256']):
                raise ValueError('C++ model or differential gate differs')
            native.update(status='PASS_SEALED_LOCAL_PUBLIC_WORKLOAD', queries=verification['queries'],
                paired_predictions=verification['paired_predictions'],
                group_cells=len(verification['figure8_public_group_cells']),
                scope='Historical v2 selector. Sealed receipt checked; native assets exhaustively verified at sealing. Canonical v3 requires its separate differential gate.')
        except (KeyError, ValueError, OSError, StopIteration) as error:
            native.update(status='EVIDENCE_INVALID', reason=str(error))
    stages['cpp_6spn_paper_proxy_v2'] = native
    cpp_current = dict(status='PENDING', evidence='output/full/cpp-v3/final_current_seal.json',
        scope='Canonical753x3, all15public Figure8 cells; complete physical native-call wall, shared host, not paper200/hardware')
    if (FULL / 'cpp-v3/final_current_seal.json').exists():
        try:
            from full_cpp_v3_audit import audit as audit_cpp
            audited = audit_cpp()
            cpp_current.update(status=audited['status'], queries=audited['queries'],
                paired_predictions=audited['paired_predictions'], group_cells=audited['figure8_cells'],
                successful_native_calls=audited['successful_native_calls'],
                upstream_omitted_successful_native_calls=audited['upstream_omitted_successful_native_calls'],
                physical_native_timer=audited['physical_native_timer'])
        except (KeyError, ValueError, OSError) as error:
            cpp_current.update(status='EVIDENCE_INVALID', reason=str(error))
    stages['cpp_canonical_v3'] = cpp_current
    dbest_audit_path = FULL / 'dbest_flights_audit/verification.json'
    dbest_stage = dict(status='PENDING', evidence=dbest_audit_path.relative_to(ROOT).as_posix())
    if dbest_audit_path.exists():
        try:
            from full_dbest_flights_audit import verify as verify_dbest
            audited = verify_dbest()
            dbest_stage.update(status='PASS_WITH_GAPS', population_rows=audited['population_rows'],
                unique_fit_rows=audited['unique_fit_rows'], native_calls=audited['verified_native_calls'],
                unsupported_queries=audited['unsupported_query_count'],
                scope='Original engine on own1B population;20K fit cap;4SQL classes and DE coverage gap. Not author configuration or full Figure13.')
        except (KeyError, ValueError, OSError) as error:
            dbest_stage.update(status='EVIDENCE_INVALID', reason=str(error))
    stages['dbest_1b_bounded_original_engine'] = dbest_stage
    for key, reason in [
        ('paper_exact_200_query_binding', 'Public files contain 683 grouped queries; original 200 membership not identified'),
        ('figure5_original_synthetic_database', 'Original generator, parameters and seeds not found in audited public sources'),
        ('all_original_comparison_implementations', 'Wavelets/IBJS/random/DBEst/XDB/VerdictDB original drivers not in released source'),
        ('figure7_exact_author_config', 'Both released-code and B*CBase proxy variants recorded; exact author 200-query set unavailable')]:
        stages[key] = dict(status='OPEN_SOURCE_GAP', reason=reason)
    formal = load_json(FULL / 'flights/model_formal_validation.json', {})
    observer = load_json(FULL / 'flights/root_formal_verification.json', {})
    formal_contents = dict(formal)
    formal_seal = formal_contents.pop('validation_sha256', None)
    formal_pass = (formal_seal is not None and formal_seal == binding_hash(formal_contents)
        and observer.get('status') == 'PASS' and observer.get('validation_sha256') == formal_seal
        and formal.get('population_rows') == formal.get('normalizer') == 1000000000
        and formal.get('actual_training_rows') == 9997912 and formal.get('query_errors') == 0)
    stages['flights_1b_rspn_aqp_and_ci'] = dict(
        status='FORMAL_COMPLETE_REPLAY_PENDING' if formal_pass else 'PENDING',
        evidence='output/full/flights/model_formal_validation.json; output/full/flights/root_formal_verification.json',
        actual_training_rows=formal.get('actual_training_rows'), truth_groups=formal.get('truth_groups'),
        missing_groups=formal.get('missing_model_groups'), extra_groups=formal.get('extra_model_groups'),
        ci_eligible_groups=formal.get('ci_eligible_groups'), ci_excluded_groups=formal.get('ci_excluded_groups'),
        scope='Own IDEBench population/seed; one-sample CI experiment, not repeated-sample calibration. Original baseline comparisons remain separate.')
    if formal_pass and (FULL/'flights-replay/final_seal.json').exists():
        try:
            from full_flights_replay_audit import verify as audit_flights_replay
            replayed = audit_flights_replay()
            receipt = load_json(ROOT/replayed['verification']['path'])
            if (replayed['status'] != 'PASS_READ_ONLY_FLIGHTS_REPLAY_WITH_CURRENT_PARSER_BINDING'
                    or receipt['configuration']['formal_receipt']['sha256'] != file_sha256(FULL/'flights/model_formal_validation.json')):
                raise ValueError('Flights replay/formal result binding differs')
            stages['flights_1b_rspn_aqp_and_ci'].update(status='PASS_SEALED_ORIGINAL_SCALE_LOCAL_EXPERIMENT',
                independent_reverse_point_ci_replay='PASS', successful_replay_calls=replayed['successful_prior_calls'],
                parser_binding_status=replayed['parser_binding_status'],
                parser_bound_during_original_inference=False,
                maximum_replay_relative_difference=replayed['maximum_relative_difference'])
        except (KeyError, ValueError, OSError) as error:
            stages['flights_1b_rspn_aqp_and_ci'].update(status='EVIDENCE_INVALID', reason=str(error))
    local_truth = load_json(FULL / 'results/grouped_truth_discrepancies.json', {})
    arrays = load_json(FULL / 'results/grouped_independent_truth_arrays.json', {})
    stages['independent_public_683_truths'] = dict(
        status=local_truth.get('status', 'PUBLIC_LABEL_DIFFERENCES_UNDER_SQL_REVIEW' if arrays.get('queries') == 683 else 'PENDING'),
        queries=arrays.get('queries', 0), published_matches=local_truth.get('published_matches'),
        independently_SQL_confirmed_differences=local_truth.get('independent_SQL_confirmed_differences'),
        evidence='output/full/results/grouped_truth_discrepancies.json',
        scope='Published CSVs remain unchanged; local exact counts are a separate input')
    stages['ssb_rspn_aqp'], stages['ssb_confidence_intervals'] = ssb_model_stages()
    for key in ['flights_original_baseline_comparisons', 'ssb_aqp_and_baselines',
                'dbest_wavelet_microbenchmarks']:
        stages[key] = dict(status='PENDING')
    output = dict(status='INCOMPLETE_FULL_PAPER', full_paper_complete=False,
                  updated_at_utc=datetime.now(timezone.utc).isoformat(),
                  original_verified_baseline_preserved=True,
                  inference_policy=PROTOCOL,
                  note='PASS applies only to each named receipt. V1 CSVs remain historical: original cache can mix physical RSPNs. Missing inputs and original-scale baselines remain open.',
                  stages=stages)
    atomic_json(FULL / 'completion_status.json', output)
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
