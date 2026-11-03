"""Project only accepted native SSB evidence into the full-paper coverage ledger."""
from full_common import FULL, file_sha256, load_json


def generation_stage(progress_reader=load_json):
    home = FULL/'ssb/native_v2/formal500'
    state = progress_reader(home/'stream/checkpoint.json', {})
    life = progress_reader(home/'lifecycle.json', {})
    stage = dict(status='PARTIAL_CHECKPOINT' if life or state else 'PENDING',
        generated_rows=state.get('rows', 0), sample_rows=state.get('sample_rows', 0),
        committed_shards=state.get('next_shard', 0), requested_rows=3000028242,
        evidence='output/full/results/ssb_native_v2.json',
        author_full_row_byte_identity_proven=False,
        scope='Corrected native population: author row count and13 exact SQL truths; raw author byte identity unavailable. Historical MISMATCH remains separate.')
    if life.get('status') == 'TAINTED':
        stage['status'] = 'TAINTED_NATIVE_GENERATION'
    path = FULL/'results/ssb_native_v2.json'
    if not path.exists():
        return stage
    body = load_json(path)
    if body.get('status') == 'MISMATCH':
        stage['status'] = 'FAILED_AUTHOR_POPULATION_GATE'
        return stage
    try:
        from full_ssb_native_model import verify_generation
        accepted = verify_generation(expected_receipt_sha256=file_sha256(path))
        stage.update(status='PASS_AUTHOR_ROWS_AND_13_TRUTHS_WITH_PHYSICAL_CLOSURE',
            generated_rows=accepted['population_rows'], sample_rows=accepted['sample_rows'],
            truth_groups=accepted['truth_groups'], queries=13, committed_shards=4000)
    except (KeyError, ValueError, OSError) as error:
        stage.update(status='EVIDENCE_INVALID', reason=str(error))
    return stage


def model_stages():
    evidence = 'output/full/results/ssb_native_v2_model_aqp_ci.json; output/full/ssb/native_v2_replay/verification.json'
    model = dict(status='PENDING', evidence=evidence,
        scope='Corrected native SF500: five single-table RSPNs,1M/table cap; original n/p normalizer; exact author13 truths, no full raw byte identity claim.')
    ci = dict(status='PENDING', evidence=evidence,
        scope='Central90 reference from retained fact sample; count<10 excluded; one sample, not repeated-sample calibration.')
    path = FULL/'results/ssb_native_v2_model_aqp_ci.json'
    if not path.exists():
        return model, ci
    if load_json(path).get('status') != 'PASS':
        model['status'] = ci['status'] = 'FORMAL_QUERY_ERRORS_RECORDED'
        return model, ci
    model['status'] = ci['status'] = 'FORMAL_COMPLETE_REPLAY_PENDING'
    if not (FULL/'ssb/native_v2_replay/verification.json').exists():
        return model, ci
    try:
        from full_ssb_native_replay import verify
        accepted = verify()
        source = accepted['source_snapshot']
        if (accepted['status'] != 'PASS_NATIVE_V2_INDEPENDENT_REVERSE_REPLAY'
                or source['published_result']['sha256'] != file_sha256(path)):
            raise ValueError('native formal report/reverse replay identity differs')
        coverage = accepted['coverage']
        model_gaps = any(coverage[k] for k in ('missing_model_groups_total',
            'extra_model_groups_total', 'nonfinite_point_groups'))
        ci_gaps = model_gaps or any(coverage[k] for k in ('nonfinite_original_ci_groups',
            'missing_or_nonfinite_model_interval_groups'))
        model.update(status='PASS_REPLAY_WITH_GROUP_GAPS' if model_gaps else 'PASS_VERIFIED_NATIVE_SF500_AQP',
            population_rows=source['population_rows'], actual_fact_sample_rows=source['sample_rows'],
            queries=13, coverage=coverage)
        ci.update(status='PASS_REPLAY_WITH_CI_GAPS' if ci_gaps else 'PASS_LOCAL_CI_WITH_EXCLUSIONS',
            confidence_fact_sample_rows=source['sample_rows'], coverage=coverage,
            eligible_truth_groups=coverage['reference_ci_eligible_truth_groups'],
            excluded_truth_groups=coverage['reference_ci_excluded_truth_groups'])
        if not ci['eligible_truth_groups']:
            ci['status'] = 'NO_ELIGIBLE_REFERENCE_INTERVALS'
    except (KeyError, ValueError, OSError) as error:
        model.update(status='EVIDENCE_INVALID', reason=str(error))
        ci.update(status='EVIDENCE_INVALID', reason=str(error))
    return model, ci
