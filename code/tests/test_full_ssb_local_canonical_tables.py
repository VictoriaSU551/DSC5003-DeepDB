"""Derived views must bind the accepted new variant and disclose its scope."""
import copy
import sys
from types import SimpleNamespace
import pytest

import full_ssb_local_canonical_tables as target
from full_ssb_local_tables import validate_formal_report,scope_text
from test_full_ssb_local_tables import fixture


def report():
    r=fixture();c=target.configuration()
    r.update(stage=c['stage'],scope=c['scope'],evaluation_variant=target.VARIANT,group_order_adapter_sha256=target.ADAPTER_SHA)
    return r


@pytest.mark.parametrize('field,value',[('evaluation_variant','OLD_GROUP_SET_ORDER'),('group_order_adapter_sha256','0'*64)])
def test_legacy_or_changed_adapter_cannot_render_canonical_figures(field,value):
    r=report();validate_formal_report(r,9996946,target.configuration())
    r[field]=value
    with pytest.raises(ValueError):validate_formal_report(r,9996946,target.configuration())


def test_scopes_are_explicit_before_output_and_never_inferred_from_missing_fields():
    c=target.configuration()
    assert 'canonical' in scope_text({},c,'ci_scope').lower()
    assert 'n/p' in scope_text({},c,'normalizer_scope')
    with pytest.raises(ValueError):scope_text({}, {}, 'ci_scope')
    with pytest.raises(ValueError):scope_text({}, {'ci_scope':''}, 'ci_scope')


def api():
    d=lambda name:dict(path=name,bytes=1,sha256='a'*64)
    return dict(status=target.API_PASS,scope=target.SCOPE,evaluation_variant=target.VARIANT,group_order_adapter_sha256=target.ADAPTER_SHA,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        historical_reverse_accepted=False,sample_rows=9996946,population_rows=3000028242,
        published_result=d('output/full/results/ssb_local_sf500_canonical_aqp_ci.json'),artifacts=[d('physical.json')],
        report=dict(coverage={'groups':2059}),**{k:d(k+'.json') for k in ('verification','verification_seal','plan','formal_receipt','formal_lifecycle','forward','reverse')})


@pytest.mark.parametrize('mutation',[None,'old_status','scope','historical','author','variant'])
def test_table_acceptance_calls_only_canonical_public_api_once(monkeypatch,mutation):
    r=api();calls=[]
    if mutation=='old_status':r['status']='PASS_LOCAL_SSB_SF500_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH'
    if mutation=='scope':r['scope']='LOCAL_SSB_SF500'
    if mutation=='historical':r['historical_reverse_accepted']=True
    if mutation=='author':r['author_reproduction_complete']=True
    if mutation=='variant':r['evaluation_variant']='old'
    def verify():calls.append('canonical-current-proof');return r
    monkeypatch.setitem(sys.modules,'full_ssb_local_canonical',SimpleNamespace(verify_canonical=verify))
    if mutation is None:
        checked=target.accepted()
        assert checked['source_snapshot']['published_result']==r['published_result']
        assert checked['source_snapshot']['sample_rows']==9996946
        assert checked['canonical_validation']['artifacts_sha256']==target.value_hash(r['artifacts'])
    else:
        with pytest.raises(ValueError):target.accepted()
    assert calls==['canonical-current-proof']


def test_future_10m_tables_use_new_group_replay_and_explicit_variant():
    from full_ssb_local_ci_tables import configuration
    c=configuration()
    assert c['evaluation_variant']==target.VARIANT
    assert 'code/full_ssb_local_ci_group_replay.py' in c['helpers']
    assert 'code/full_ssb_group_order.py' in c['helpers']
