"""Derived tables for the separately accepted canonical1M SSB evaluation."""
from full_ssb_local_tables import main as build
from full_ssb_replay import value_hash

SCOPE='LOCAL_SSB_SF500_CANONICAL_CI'
API_PASS='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH'
VARIANT='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
ADAPTER_SHA='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'


def accepted():
    from full_ssb_local_canonical import verify_canonical
    checked=verify_canonical()
    if (checked['status']!=API_PASS or checked['scope']!=SCOPE or checked['evaluation_variant']!=VARIANT
            or checked['group_order_adapter_sha256']!=ADAPTER_SHA or checked['historical_reverse_accepted'] is not False
            or checked['author_reproduction_complete'] is not False or checked['full_paper_reproduction_complete'] is not False
            or checked['author_different_groups']!=1713 or checked['sample_rows']!=9996946 or checked['population_rows']!=3000028242):
        raise ValueError('complete accepted canonical evaluation with retained author mismatch required')
    # The provider has just physically checked its entire closure. Bind its
    # descriptors and full artifact-list digest without copying large raw lists
    # into each derived figure manifest.
    compact={k:checked[k] for k in ('verification','verification_seal','published_result','plan',
        'formal_receipt','formal_lifecycle','forward','reverse')}
    compact['artifacts_sha256']=value_hash(checked['artifacts'])
    return dict(status=checked['status'],scope=SCOPE,evaluation_variant=VARIANT,
        group_order_adapter_sha256=ADAPTER_SHA,canonical_validation=compact,
        source_snapshot=dict(published_result=checked['published_result'],sample_rows=checked['sample_rows'],population_rows=checked['population_rows']),
        coverage=checked['report']['coverage'],author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False)


def configuration():
    return dict(stage='LOCAL_SSB_SF500_CANONICAL_1M_AQP_CI',scope=SCOPE,
        cap=1000000,training_rows=dict(lineorder=1000000,dwdate=2556,customer=1000000,part=1000000,supplier=1000000),
        verify=accepted,result='ssb_local_sf500_canonical_aqp_ci.json',prefix='aqp_ssb_local_canonical_',
        pointer='ssb_local_canonical_tables_latest.json',policy_applied=False,
        evaluation_variant=VARIANT,group_order_adapter_sha256=ADAPTER_SHA,
        normalizer_scope='Model retains original n/p fact normalizer and full dimensions; independent reference uses exact N3000028242.',
        ci_scope='Canonical paired GROUP BY prototype; original RSPN CI and central90 Bernoulli reference from retained fact sample joined to full dimensions; count<10 excluded; one realization, not calibration.',
        evaluation_note='Canonical paired GROUP BY prototype; the five saved1M models are unchanged.',
        helpers=['code/full_ssb_local_canonical_tables.py','code/full_ssb_local_canonical.py',
            'code/full_ssb_local_canonical_run.py','code/full_ssb_group_order.py'])


if __name__=='__main__':build(configuration())
