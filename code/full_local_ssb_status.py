"""Separate LOCAL SF500 evidence; never upgrades author-population coverage."""
from full_common import FULL, file_sha256, load_json

CANONICAL_VARIANT='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
GROUP_ADAPTER_SHA='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'


def model_stages():
    evidence = 'output/full/results/ssb_local_sf500_model_aqp_ci.json; output/full/ssb/local_sf500_replay/verification.json'
    model = dict(status='PENDING', evidence=evidence,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,author_different_groups=1713,
        scope='LOCAL SSB SF500: five single-table RSPNs,1M/table cap; original n/p normalizer; local exact truths.1713 author truth groups still differ.')
    ci = dict(status='PENDING', evidence=evidence,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,author_different_groups=1713,
        model_training_cap_per_table=1000000,paper_figure11_training_budget_reproduced=False,
        scope='LOCAL SSB1M/table model; Figure11 uses10M training, still separate pending. Author mismatch retained. Central90 reference from retained fact sample; count<10 excluded; one sample, not repeated-sample calibration.')
    path = FULL/'results/ssb_local_sf500_model_aqp_ci.json'
    if not path.exists():
        return model, ci
    if load_json(path).get('status') != 'PASS_LOCAL_SSB_SF500_MODEL_AQP_CI':
        model['status'] = ci['status'] = 'FORMAL_QUERY_ERRORS_RECORDED'
        return model, ci
    model['status'] = ci['status'] = 'FORMAL_COMPLETE_REPLAY_PENDING'
    if not (FULL/'ssb/local_sf500_replay/verification.json').exists():
        attempt=FULL/'ssb/local_sf500_replay/last_run.json'
        if attempt.exists() and load_json(attempt).get('status')=='TAINTED':
            for stage in (model,ci):
                stage.update(status='FORMAL_COMPLETE_REPLAY_FAILURE_RECORDED',reason=load_json(attempt).get('error','TAINTED historical reverse attempt'))
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
        ci.update(status='PASS_REPLAY_WITH_CI_GAPS' if ci_gaps else 'PASS_LOCAL_1M_MODEL_CI_WITH_EXCLUSIONS',
            confidence_fact_sample_rows=source['sample_rows'], coverage=coverage,
            eligible_truth_groups=coverage['reference_ci_eligible_truth_groups'],
            excluded_truth_groups=coverage['reference_ci_excluded_truth_groups'])
        if not ci['eligible_truth_groups']:
            ci['status'] = 'NO_ELIGIBLE_REFERENCE_INTERVALS'
    except (KeyError, ValueError, OSError) as error:
        model.update(status='EVIDENCE_INVALID', reason=str(error))
        ci.update(status='EVIDENCE_INVALID', reason=str(error))
    return model, ci


def canonical_stages():
    """One fresh CONT verification projects both stages; old failures stay historical.

    An accepted old forward plus a new continuation reverse does not certify the
    old TAINTED ROOT transaction. No execution or legacy-verifier fallback exists.
    """
    import hashlib
    import json
    import os
    from pathlib import Path
    import re
    from full_common import ROOT
    scope='LOCAL_SSB_SF500_CANONICAL_CONTINUATION'
    protocol='ADOPT_ACCEPTED_FORWARD_FRESH_REVERSE_WITH_CONSUMED_CLOSURE_V1'
    descriptor_fields=('published_result','verification','verification_seal','plan','formal_receipt','formal_lifecycle')
    readonly=('database_connected','training_executed','inference_executed','files_modified')
    pins={'code/full_ssb_local_continuation.py':'7a1bf30793e0484482bda3548c9d65dc3c3732af286287e62a2a054fd5e15563',
        'code/full_ssb_local_continuation_run.py':'763c9c46ce34fa0b4b0e59fbeea4f43d081945b8d6e20b91dde0b91eb937c7a0',
        'code/full_ssb_group_order.py':GROUP_ADAPTER_SHA}
    def require(valid,message):
        if not valid:raise ValueError(message)
    def inventory(rows):
        require(type(rows) is list and bool(rows),'nonempty complete continuation artifact inventory required')
        physical=set()
        for d in rows:
            require(type(d) is dict and isinstance(d.get('path'),str) and bool(d['path'])
                and type(d.get('bytes')) is int and d['bytes']>=0 and isinstance(d.get('sha256'),str)
                and re.fullmatch('[0-9a-f]{64}',d['sha256']) is not None,'complete artifact descriptor required')
            key=os.path.normcase(str((ROOT/d['path']).resolve()))
            require(key not in physical,'duplicate physical continuation artifact');physical.add(key)
        return {d['path']:d for d in rows}
    common=dict(status='PENDING',author_reproduction_complete=False,full_paper_reproduction_complete=False,
        author_different_groups=1713,evaluation_variant=CANONICAL_VARIANT,group_order_adapter_sha256=GROUP_ADAPTER_SHA,
        historical_reverse_accepted=False,model_training_cap_per_table=1000000,
        paper_figure11_training_budget_policy_applied=False,
        evidence='output/full/results/ssb_local_sf500_canonical_aqp_ci.json',
        scope=scope,execution_protocol=protocol,
        scope_note='LOCAL1M/table continuation adopts the accepted old forward and verifies a fresh reverse. Old ROOT/reverse failures remain historical;1713 author differences remain.')
    model,ci=dict(common),dict(common)
    path=FULL/'results/ssb_local_sf500_canonical_aqp_ci.json'
    if not path.exists():return model,ci
    try:
        from full_ssb_local_continuation import verify_canonical
        accepted=verify_canonical()  # One fresh complete provider call for both projections.
        r=accepted['report'];parent=accepted['parent_snapshot']
        if (accepted['status']!='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_WITH_AUTHOR_MISMATCH'
                or accepted['scope']!=scope or accepted['execution_protocol']!=protocol
                or accepted['variant']!='CANONICAL_PAIRED_DECODED_GROUP_ORDER'
                or accepted['evaluation_variant']!=CANONICAL_VARIANT or accepted['group_order_adapter_sha256']!=GROUP_ADAPTER_SHA
                or accepted['author_reproduction_complete'] is not False or accepted['full_paper_reproduction_complete'] is not False
                or type(accepted['author_different_groups']) is not int or accepted['author_different_groups']!=1713
                or accepted['historical_reverse_accepted'] is not False
                or not all(accepted[k] is False for k in readonly)
                or type(accepted['population_rows']) is not int or accepted['population_rows']!=3000028242
                or type(accepted['sample_rows']) is not int or accepted['sample_rows']!=9996946
                or accepted['published_result']!=dict(path='output/full/results/ssb_local_sf500_canonical_aqp_ci.json',
                    bytes=path.stat().st_size,sha256=file_sha256(path))):
            raise ValueError('Separate continuation publication, read-only protocol and retained author mismatch required')
        require(r['status']=='PASS_LOCAL_SSB_SF500_CANONICAL_CONTINUATION_AQP_CI'
            and r['stage']=='LOCAL_SSB_SF500_CANONICAL_CONTINUATION_1M_AQP_CI'
            and all(r[k]==accepted[k] for k in ('scope','execution_protocol','variant','evaluation_variant','group_order_adapter_sha256'))
            and r['adopted_forward'] is True and r['forward_reexecuted'] is False
            and r['historical_reverse_accepted'] is False and r['author_different_groups']==1713
            and r['author_reproduction_complete'] is False and r['full_paper_reproduction_complete'] is False,
            'accepted adopted-forward/fresh-reverse report required')
        for field,expected in (('phase_model_loads',dict(FORWARD=1,REVERSE=13)),('phase_evaluator_calls',dict(FORWARD=26,REVERSE=26))):
            require(r[field]==expected and all(type(v) is int for v in r[field].values()),'exact phase load/call accounting required')
        require(parent['proof_method']=='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL'
            and parent['status']=='PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH' and parent['scope']=='LOCAL_SSB_SF500'
            and type(parent['report']) is dict and len(parent['report']['queries'])==13
            and type(parent['dependencies']) is dict and bool(parent['dependencies'])
            and len(parent['queries'])==13 and 'evaluation_binding' in parent
            and parent['population_rows']==3000028242 and parent['sample_rows']==9996946 and parent['author_different_groups']==1713
            and parent['author_reproduction_complete'] is False and parent['full_paper_reproduction_complete'] is False
            and all(parent[k] is False for k in readonly),'complete original formal proof required')
        records=inventory(accepted['artifacts']);original=inventory(parent['artifacts'])
        require(parent['closure_sha256']==hashlib.sha256(json.dumps(parent['artifacts'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            and all(records.get(p)==d for p,d in original.items()),'complete original parent artifact subset required')
        for obj in (accepted,parent):
            require(all(obj[k] in accepted['artifacts'] and obj[k]['bytes']>0 for k in descriptor_fields),
                'complete publication/parent descriptors required')
        require(all(p in records and records[p]['sha256']==sha for p,sha in pins.items()),'complete current continuation source closure required')
        require(accepted['parent_formal']==r['parent_formal']==parent['published_result']
            and parent['published_result']['path']=='output/full/results/ssb_local_sf500_model_aqp_ci.json'
            and parent['published_result']['sha256']=='da358d52a0005bb28cd606c8e539099bdf242b72d4f6e663db6c0a3f84e15c82'
            and accepted['original_mismatch']==r['original_mismatch']==parent['original_mismatch']
            and parent['original_mismatch']['path']=='output/full/results/ssb_native_v2.json'
            and parent['original_mismatch']['sha256']=='740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e'
            and parent['original_mismatch'] in accepted['artifacts']
            and accepted['model_path']==parent['model_path'] and accepted['model_sha256']==parent['model_sha256'],
            'original model and author-mismatch lineage required')
        home=Path(r['directory']).resolve();runid=home.name
        relative='output/full/ssb/local_sf500_continuation/runs/'+runid
        require(re.fullmatch('[0-9a-f]{20}',runid) is not None
            and home==(FULL/'ssb/local_sf500_continuation/runs'/runid).resolve()
            and accepted['verification']['path']==relative+'/verification.json'
            and accepted['verification_seal']['path']==relative+'/verification_seal.json'
            and accepted['reverse']==r['reverse'] and accepted['reverse']['path']==relative+'/reverse/verification.json'
            and accepted['forward']==r['forward'] and accepted['forward']['path']=='output/full/ssb/local_sf500_canonical/runs/93ea10ffd9ae559ab77e/forward/verification.json'
            and all(accepted[k] in accepted['artifacts'] for k in ('forward','reverse')),
            'accepted old forward and distinct continuation reverse paths required')
        c=r['coverage']
        require(type(r['queries']) is list and len(r['queries'])==13 and accepted['queries']==r['queries']
            and [q['query_no'] for q in r['queries']]==list(range(13))
            and sum(q['truth_groups'] for q in r['queries'])==c['truth_groups_total']==2059
            and c['reference_ci_eligible_truth_groups']+c['reference_ci_excluded_truth_groups']==2059,
            'complete thirteen-query/2059-truth coverage required')
        for stage in (model,ci):
            stage.update(adopted_forward=True,forward_reexecuted=False,forward=accepted['forward'],reverse=accepted['reverse'],
                phase_model_loads=r['phase_model_loads'],phase_evaluator_calls=r['phase_evaluator_calls'])
        model_gaps=any(c[k] for k in ('missing_model_groups_total','extra_model_groups_total','nonfinite_point_groups'))
        ci_gaps=model_gaps or any(c[k] for k in ('nonfinite_original_ci_groups','missing_or_nonfinite_model_interval_groups'))
        model.update(status='PASS_REPLAY_WITH_GROUP_GAPS' if model_gaps else 'PASS_LOCAL_CONTINUATION_1M_AQP_WITH_AUTHOR_MISMATCH',
            population_rows=accepted['population_rows'],actual_fact_sample_rows=accepted['sample_rows'],queries=13,coverage=c)
        ci.update(status='PASS_REPLAY_WITH_CI_GAPS' if ci_gaps else 'PASS_LOCAL_CONTINUATION_1M_CI_WITH_EXCLUSIONS',
            confidence_fact_sample_rows=accepted['sample_rows'],queries=13,coverage=c,
            eligible_truth_groups=c['reference_ci_eligible_truth_groups'],excluded_truth_groups=c['reference_ci_excluded_truth_groups'])
        if not ci['eligible_truth_groups']:ci['status']='NO_ELIGIBLE_REFERENCE_INTERVALS'
    except (KeyError,ValueError,OSError,TypeError) as error:
        for stage in (model,ci):stage.update(status='EVIDENCE_INVALID',reason=str(error))
    return model,ci


def ci10m_stage():
    result=dict(status='PENDING',author_reproduction_complete=False,full_paper_reproduction_complete=False,
        author_different_groups=1713,model_training_cap_per_table=10000000,
        paper_figure11_training_budget_policy_applied=False,exact10000000_fact_training_rows_claimed=False,
        evaluation_variant=CANONICAL_VARIANT,group_order_adapter_sha256=GROUP_ADAPTER_SHA,
        evidence='output/full/results/ssb_local_sf500_ci10m.json; output/full/ssb/local_sf500_ci10m_group_replay/verification.json',
        scope='Separate LOCAL Figure11 training-cap policy,10M/table; fact actually9996946. Reuses accepted prepared inputs and native moments, trains five new models; one sample and author1713 mismatch remain.')
    path=FULL/'results/ssb_local_sf500_ci10m.json'
    if not path.exists():return result
    if load_json(path).get('status')!='PASS_LOCAL_SSB_SF500_10M_CI_WITH_AUTHOR_MISMATCH':
        result['status']='FORMAL_QUERY_ERRORS_RECORDED';return result
    result['status']='FORMAL_COMPLETE_REPLAY_PENDING'
    if not (FULL/'ssb/local_sf500_ci10m_group_replay/verification.json').exists():return result
    try:
        from full_ssb_local_ci_group_replay import verify
        accepted=verify();source=accepted['source_snapshot']
        if (accepted['status']!='PASS_LOCAL_SSB_10M_CI_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH'
                or accepted['scope']!='LOCAL_SSB_10M_CI' or accepted['author_reproduction_complete'] is not False
                or accepted['full_paper_reproduction_complete'] is not False or accepted['author_different_groups']!=1713
                or accepted['training_cap_per_table']!=10000000
                or accepted['evaluation_variant']!=CANONICAL_VARIANT or accepted['group_order_adapter_sha256']!=GROUP_ADAPTER_SHA
                or accepted['paper_figure11_training_budget_policy_applied'] is not True
                or accepted['exact10000000_fact_training_rows_claimed'] is not False
                or accepted['actual_training_rows_per_table']!=dict(lineorder=9996946,dwdate=2556,customer=10000000,part=1800000,supplier=1000000)
                or source['published_result']['sha256']!=file_sha256(path)):
            raise ValueError('Separate accepted 10M CI replay/budget/source required')
        c=accepted['coverage'];gaps=any(c[k] for k in ('missing_model_groups_total','extra_model_groups_total',
            'nonfinite_point_groups','nonfinite_original_ci_groups','missing_or_nonfinite_model_interval_groups'))
        result.update(status='PASS_REPLAY_WITH_CI_GAPS' if gaps else 'PASS_LOCAL_10M_CAP_CI_WITH_EXCLUSIONS',
            paper_figure11_training_budget_policy_applied=True,confidence_fact_sample_rows=source['sample_rows'],
            actual_training_rows_per_table=accepted['actual_training_rows_per_table'],coverage=c,
            eligible_truth_groups=c['reference_ci_eligible_truth_groups'],excluded_truth_groups=c['reference_ci_excluded_truth_groups'])
        if not result['eligible_truth_groups']:result['status']='NO_ELIGIBLE_REFERENCE_INTERVALS'
    except (KeyError,ValueError,OSError) as error:result.update(status='EVIDENCE_INVALID',reason=str(error))
    return result
