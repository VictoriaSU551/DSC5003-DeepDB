"""Derive an honest full-paper coverage ledger from verified stage receipts."""
import json
from datetime import datetime, timezone
import os
from pathlib import Path

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import workload_files
from full_evaluation_v2 import helper_seal, PROTOCOL


def progress_json(path, default=None):
    """Read an atomic Windows checkpoint without denying its writer a rename."""
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
    with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
        return json.load(stream)


def verified_evaluation(label, queries):
    path = FULL / 'results' / (label + '_evaluation_v2.json')
    result = load_json(path)
    stage = dict(status='PENDING', evidence=path.relative_to(ROOT).as_posix())
    if result is None:
        return stage
    training = load_json(FULL / 'results' / (label + '_training.json'))
    try:
        if (result.get('status') != 'PASS' or result.get('protocol') != PROTOCOL
                or result.get('queries') != queries or training is None
                or result.get('model_sha256') != training.get('model_sha256')
                or file_sha256(ROOT / training['model_path']) != training['model_sha256']):
            raise ValueError('evaluation or model seal mismatch')
        source = result.get('reused_from_label', label)
        expected_helpers = helper_seal()
        for group, query_path, truth_path in workload_files(queries != 70):
            record = result['groups'][group]
            csv = FULL / 'evaluation_v2' / source / (group + '.csv')
            if (record['helpers'] != expected_helpers or record['query_sha256'] != file_sha256(query_path)
                    or record['truth_sha256'] != file_sha256(truth_path)
                    or file_sha256(csv) != record['csv_sha256']):
                raise ValueError('prediction, workload or evaluator seal mismatch')
        stage.update(status='PASS_LOCAL_VARIANT', queries=queries,
                     job_light_qerror=result['groups']['job_light']['q_error'],
                     independently_replayed=load_json(FULL / 'results' / (label + '_replay_v2.json'), {}).get('status') == 'PASS')
    except (KeyError, ValueError, OSError) as error:
        stage.update(status='EVIDENCE_INVALID', reason=str(error))
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
        stages[label] = verified_evaluation(label, count)
    stages['sample_size_sweep_public_profile'] = {str(n): verified_evaluation(
        'public_scale_rdc_n%d_b%s' % (n, '0p5' if n == 10000000 else '0p0'), 753)
        for n in [1000, 10000, 100000, 1000000, 10000000]}
    stages['budget_sweep_public_paper_cost_proxy'] = {str(b): verified_evaluation(
        'paper_proxy_public_scale_rdc_n10000000_b%s' % str(b).replace('.', 'p'), 753)
        for b in [0., .5, 1., 2., 3.]}
    stages['temporal_10m_joblight'] = {str(c): verified_evaluation(
        'temporal_joblight_rdc_n10000000_b0p0_year%d' % c, 70) for c in [2019, 2011, 2009, 2004, 1991]}
    stages['literal_point3_ensemble_threshold'] = {profile: {str(b): verified_evaluation(
        'threshold03_%s_rdc_n10000000_b%s' % (profile, str(b).replace('.', 'p')), 70 if profile == 'joblight' else 753)
        for b in [0., .5, 1., 2., 3.]} for profile in ['joblight', 'public_scale']}
    stages['all_relationships_joblight'] = {str(n): verified_evaluation(
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
    stages['ssb_sf500_generated'] = dict(
        status='PASS_AUTHOR_POPULATION' if ssb_result.get('status') == 'PASS' else 'PARTIAL_CHECKPOINT',
        generated_rows=ssb.get('rows', 0), requested_rows=3000028242,
        sample_rows=ssb.get('sample_rows', 0), committed_shards=len(ssb.get('committed_shards', [])),
        scope='Requires all author integer aggregates and exact fact row count at completion')
    mscn_dir = FULL / 'mscn/table1_job_light_seed1'
    mscn = progress_json(mscn_dir / 'checkpoints/latest.json', {})
    mscn_eval = load_json(mscn_dir / 'evaluation.json', {})
    stages['mscn_100_epochs'] = dict(
        status='PASS_LOCAL_TABLE1_RERUN' if mscn_eval.get('status') == 'TABLE1_LOCAL_RERUN_COMPLETE'
                     and mscn_eval.get('completed_epochs') == mscn.get('completed_epochs') == 100 else 'PARTIAL_CHECKPOINT',
        committed_epochs=mscn.get('completed_epochs', 0), target_epochs=100,
        scope='Official matched 100K input bitmaps; public 683 generalization bitmaps not recovered')
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
                scope='Sealed receipt checked; native assets were exhaustively verified at sealing, not rehashed by the live progress reader')
        except (KeyError, ValueError, OSError, StopIteration) as error:
            native.update(status='EVIDENCE_INVALID', reason=str(error))
    stages['cpp_6spn_paper_proxy_v2'] = native
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
        status='PASS_SEALED_ORIGINAL_SCALE_LOCAL_EXPERIMENT' if formal_pass else 'PENDING',
        evidence='output/full/flights/model_formal_validation.json; output/full/flights/root_formal_verification.json',
        actual_training_rows=formal.get('actual_training_rows'), truth_groups=formal.get('truth_groups'),
        missing_groups=formal.get('missing_model_groups'), extra_groups=formal.get('extra_model_groups'),
        ci_eligible_groups=formal.get('ci_eligible_groups'), ci_excluded_groups=formal.get('ci_excluded_groups'),
        scope='Own IDEBench population/seed; one-sample CI experiment, not repeated-sample calibration. Original baseline comparisons remain separate.')
    local_truth = load_json(FULL / 'results/grouped_truth_discrepancies.json', {})
    arrays = load_json(FULL / 'results/grouped_independent_truth_arrays.json', {})
    stages['independent_public_683_truths'] = dict(
        status=local_truth.get('status', 'PUBLIC_LABEL_DIFFERENCES_UNDER_SQL_REVIEW' if arrays.get('queries') == 683 else 'PENDING'),
        queries=arrays.get('queries', 0), published_matches=local_truth.get('published_matches'),
        independently_SQL_confirmed_differences=local_truth.get('independent_SQL_confirmed_differences'),
        evidence='output/full/results/grouped_truth_discrepancies.json',
        scope='Published CSVs remain unchanged; local exact counts are a separate input')
    for key in ['flights_original_baseline_comparisons', 'ssb_aqp_and_baselines', 'ssb_confidence_intervals',
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
