"""Separate LOCAL SF500 evidence; never upgrades author-population coverage."""
from full_common import FULL, file_sha256, load_json


def model_stages():
    evidence = 'output/full/results/ssb_local_sf500_model_aqp_ci.json; output/full/ssb/local_sf500_replay/verification.json'
    model = dict(status='PENDING', evidence=evidence,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,author_different_groups=1713,
        scope='LOCAL SSB SF500: five single-table RSPNs,1M/table cap; original n/p normalizer; local exact truths.1713 author truth groups still differ.')
    ci = dict(status='PENDING', evidence=evidence,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,author_different_groups=1713,
        scope='LOCAL SSB; author mismatch retained. Central90 reference from retained fact sample; count<10 excluded; one sample, not repeated-sample calibration.')
    path = FULL/'results/ssb_local_sf500_model_aqp_ci.json'
    if not path.exists():
        return model, ci
    if load_json(path).get('status') != 'PASS_LOCAL_SSB_SF500_MODEL_AQP_CI':
        model['status'] = ci['status'] = 'FORMAL_QUERY_ERRORS_RECORDED'
        return model, ci
    model['status'] = ci['status'] = 'FORMAL_COMPLETE_REPLAY_PENDING'
    if not (FULL/'ssb/local_sf500_replay/verification.json').exists():
        return model, ci
    try:
        from full_ssb_local_replay import verify
        accepted = verify()
        source = accepted['source_snapshot']
        if (accepted['status'] != 'PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH'
                or accepted['scope'] != 'LOCAL_SSB_SF500'
                or accepted['author_reproduction_complete'] is not False
                or accepted['full_paper_reproduction_complete'] is not False
                or accepted['author_different_groups'] != 1713
                or source['published_result']['sha256'] != file_sha256(path)):
            raise ValueError('LOCAL formal report/reverse replay identity or author mismatch differs')
        coverage = accepted['coverage']
        model_gaps = any(coverage[k] for k in ('missing_model_groups_total',
            'extra_model_groups_total', 'nonfinite_point_groups'))
        ci_gaps = model_gaps or any(coverage[k] for k in ('nonfinite_original_ci_groups',
            'missing_or_nonfinite_model_interval_groups'))
        model.update(status='PASS_REPLAY_WITH_GROUP_GAPS' if model_gaps else 'PASS_VERIFIED_LOCAL_SF500_AQP_WITH_AUTHOR_MISMATCH',
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
