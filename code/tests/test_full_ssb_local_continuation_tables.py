"""Pure continuation-consumer contracts; no parent verifier or scientific call."""
import copy
import csv
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


def target():
    try:
        return importlib.import_module('full_ssb_local_continuation_tables')
    except ModuleNotFoundError:
        pytest.fail('the separate continuation table consumer is not implemented')


def descriptor(path, sha='a'*64):
    return dict(path=path, bytes=1, sha256=sha)


def evidence(t):
    from test_full_ssb_local_tables import fixture
    from full_ssb_local_replay import QUERY_NAMES
    sqls=(t.ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines()
    counts=[1,1,1,100,100,143,150,600,24,4,35,100,800]
    queries=[]
    for i,(name,sql,count) in enumerate(zip(QUERY_NAMES,sqls,counts)):
        groups=[dict(key=[j],status='MATCHED',truth=1000.,prediction=900.,relative_error=.1,
            model_covers_truth=None,model_relative_half_width=None,model_interval=None,zero_truth=False,
            sample_moments=dict(count=0,filter_count=0,sum_integer=0,scale=1),
            reference_ci=dict(eligible=False,status='LESS_THAN_10_SAMPLES')) for j in range(count)]
        queries.append(dict(query_no=i,query_name=name,sql=sql,truth_groups=count,model_groups=count,
            missing_model_groups=0,extra_model_groups=0,groups=groups,point_error=None,ci_error=None,
            point_seconds=1.,ci_seconds=2.,nonfinite_original_intervals=[]))
    home='output/full/ssb/local_sf500_continuation/runs/'+'b'*20
    published=descriptor('output/full/results/ssb_local_sf500_canonical_aqp_ci.json')
    parent_result=descriptor('output/full/results/ssb_local_sf500_model_aqp_ci.json',t.PARENT_RESULT_SHA)
    mismatch=descriptor('output/full/results/ssb_native_v2.json',t.MISMATCH_SHA)
    forward=descriptor('output/full/ssb/local_sf500_canonical/runs/93ea10ffd9ae559ab77e/forward/verification.json')
    reverse=descriptor(home+'/reverse/verification.json')
    parent_home='output/full/ssb/local_sf500_models/runs/'+'c'*20
    parent=dict(status='PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH',scope='LOCAL_SSB_SF500',
        proof_method='DIRECT_FROZEN_PREVIOUS_VERIFY_LOCAL_FORMAL',report=dict(queries=copy.deepcopy(queries)),
        dependencies={'physical_source_closure':'fixture'},inputs={'native_moments':'fixture'},
        published_result=parent_result,model_path='output/full/ssb/local_sf500_models/ensemble.pkl',
        model_sha256='c'*64,sample_rows=9996946,population_rows=3000028242,
        queries=copy.deepcopy(queries),evaluation_binding={'original':'unchanged'},original_mismatch=mismatch,
        author_different_groups=1713,author_reproduction_complete=False,full_paper_reproduction_complete=False,
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False,
        **{k:descriptor(parent_home+'/'+name) for k,name in [('verification','verification.json'),
            ('verification_seal','verification_seal.json'),('plan','plan.json'),
            ('formal_receipt','formal/receipt.json'),('formal_lifecycle','formal/lifecycle.json')]})
    parent['artifacts']=[parent_result,mismatch]+[parent[k] for k in ('verification','verification_seal','plan','formal_receipt','formal_lifecycle')]
    parent['closure_sha256']=t.value_hash(parent['artifacts'])
    coverage=dict(truth_groups_total=2059,model_groups_total=2059,missing_model_groups_total=0,
        extra_model_groups_total=0,nonfinite_point_groups=0,nonfinite_original_ci_groups=0,
        missing_or_nonfinite_model_interval_groups=2059,zero_truth_groups=0,
        reference_ci_eligible_truth_groups=0,reference_ci_excluded_truth_groups=2059,
        reference_ci_status_counts_all_union={'LESS_THAN_10_SAMPLES':2059})
    r=fixture()
    r.update(status=t.REPORT_PASS,stage=t.configuration()['stage'],scope=t.SCOPE,execution_protocol=t.PROTOCOL,
        variant=t.EXECUTION_VARIANT,evaluation_variant=t.VARIANT,group_order_adapter_sha256=t.ADAPTER_SHA,
        directory=str(t.ROOT/home),parent_formal=parent_result,original_mismatch=mismatch,
        forward=forward,reverse=reverse,coverage=coverage,queries=queries,
        historical_reverse_accepted=False,historical_result_changed=False,adopted_forward=True,
        forward_reexecuted=False,preparation_executed=False,training_executed=False,moments_executed=False,
        phase_model_loads={'FORWARD':1,'REVERSE':13},phase_evaluator_calls={'FORWARD':26,'REVERSE':26})
    for row in r['training_tables']:row.update(full_join_estimate=3000028242,learning_seconds=1.)
    api=dict(status=t.API_PASS,scope=t.SCOPE,execution_protocol=t.PROTOCOL,variant=t.EXECUTION_VARIANT,
        evaluation_variant=t.VARIANT,group_order_adapter_sha256=t.ADAPTER_SHA,
        parent_snapshot=parent,report=r,published_result=published,parent_formal=parent_result,
        forward=forward,reverse=reverse,model_path=parent['model_path'],model_sha256=parent['model_sha256'],
        sample_rows=9996946,population_rows=3000028242,queries=queries,evaluation_binding={'canonical':'fixture'},
        original_mismatch=mismatch,author_different_groups=1713,author_reproduction_complete=False,
        full_paper_reproduction_complete=False,historical_reverse_accepted=False,
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False,
        **{k:descriptor(home+'/'+name) for k,name in [('verification','verification.json'),
            ('verification_seal','verification_seal.json'),('plan','plan.json'),
            ('formal_receipt','root_control/receipt.json'),('formal_lifecycle','root_control/lifecycle.json')]})
    api['artifacts']=parent['artifacts']+[published,forward,reverse]+[api[k] for k in
        ('verification','verification_seal','plan','formal_receipt','formal_lifecycle')]
    api['artifacts'] += [descriptor(p,sha) for p,sha in t.PINS.items() if p in t.PROVIDER_FILES]
    return api


def install(monkeypatch,t,api):
    calls=[]
    def verify():calls.append('one-public-continuation');return api
    monkeypatch.setattr(t,'check_sources',lambda:None)
    monkeypatch.setitem(sys.modules,'full_ssb_local_continuation',SimpleNamespace(
        __file__=str(t.ROOT/'code/full_ssb_local_continuation.py'),verify_canonical=verify))
    return calls


def test_acceptance_delegates_once_and_binds_full_proof_without_copying_it(monkeypatch):
    t=target();api=evidence(t);calls=install(monkeypatch,t,api)
    accepted=t.accepted();proof=accepted['continuation_validation']
    assert calls==['one-public-continuation']
    assert proof['parent_snapshot_sha256']==t.value_hash(api['parent_snapshot'])
    assert proof['artifacts_sha256']==t.value_hash(api['artifacts'])
    assert proof['adopted_forward'] is True and proof['forward_reexecuted'] is False
    assert accepted['coverage']==api['report']['coverage']
    assert accepted['source_snapshot']['published_result']==api['published_result']
    assert 'artifacts' not in proof and 'parent_snapshot' not in proof


@pytest.mark.parametrize('change',['oldstatus','oldscope','protocol','adapter','author','historical','N','n',
    'readonly','adoption','reexecuted','calls','loads','parent_proof','parent_summary','parent_closure',
    'empty_inventory','duplicate_inventory','parent_omitted','critical_omitted','source_omitted',
    'source_sha','published_path','reverse_path','forward_path','group_subset','query_subset','wrong_sql'])
def test_incomplete_or_old_evidence_is_rejected_before_output(monkeypatch,change):
    t=target();api=evidence(t);calls=install(monkeypatch,t,api)
    if change=='oldstatus':api['status']='PASS_READ_ONLY_LOCAL_SSB_SF500_CANONICAL_CI_WITH_AUTHOR_MISMATCH'
    elif change=='oldscope':api['scope']='LOCAL_SSB_SF500_CANONICAL_CI'
    elif change=='protocol':api['execution_protocol']='pretend_old_root_pass'
    elif change=='adapter':api['group_order_adapter_sha256']='0'*64
    elif change=='author':api['author_reproduction_complete']=True
    elif change=='historical':api['historical_reverse_accepted']=True
    elif change in ('N','n'):api['population_rows' if change=='N' else 'sample_rows']+=1
    elif change=='readonly':api['inference_executed']=True
    elif change=='adoption':api['report']['adopted_forward']=False
    elif change=='reexecuted':api['report']['forward_reexecuted']=True
    elif change=='calls':api['report']['phase_evaluator_calls']['REVERSE']=25
    elif change=='loads':api['report']['phase_model_loads']['REVERSE']=1
    elif change=='parent_proof':api['parent_snapshot']['proof_method']='SUMMARY_ONLY'
    elif change=='parent_summary':del api['parent_snapshot']['report']
    elif change=='parent_closure':api['parent_snapshot']['closure_sha256']='0'*64
    elif change=='empty_inventory':api['artifacts']=[]
    elif change=='duplicate_inventory':api['artifacts'].append(dict(api['artifacts'][0]))
    elif change=='parent_omitted':api['artifacts'].remove(api['parent_snapshot']['verification'])
    elif change=='critical_omitted':api['artifacts'].remove(api['reverse'])
    elif change=='source_omitted':api['artifacts']=[d for d in api['artifacts'] if d['path']!='code/full_ssb_group_order.py']
    elif change=='source_sha':next(d for d in api['artifacts'] if d['path']=='code/full_ssb_group_order.py')['sha256']='0'*64
    elif change=='published_path':api['published_result']=descriptor('output/full/results/old.json')
    elif change=='reverse_path':api['reverse']=descriptor('output/full/ssb/local_sf500_canonical/runs/'+'b'*20+'/reverse/verification.json')
    elif change=='forward_path':api['forward']=descriptor('output/full/ssb/local_sf500_continuation/runs/'+'b'*20+'/forward/verification.json')
    elif change=='group_subset':api['report']['queries'][12]['groups'].pop()
    elif change=='query_subset':api['report']['queries'].pop()
    elif change=='wrong_sql':api['report']['queries'][0]['sql']+=' '
    with pytest.raises((ValueError,KeyError)):t.accepted()
    assert calls==['one-public-continuation']


def test_frozen_sources_are_checked_before_public_provider(monkeypatch):
    t=target();calls=[]
    monkeypatch.setitem(sys.modules,'full_ssb_local_continuation',SimpleNamespace(verify_canonical=lambda:calls.append('forbidden')))
    monkeypatch.setattr(t,'PINS',dict(t.PINS,**{'code/full_ssb_group_order.py':'0'*64}))
    with pytest.raises(ValueError,match='source'):t.accepted()
    assert calls==[]


def test_shadow_provider_is_rejected_before_its_api(monkeypatch):
    t=target();api=evidence(t);calls=install(monkeypatch,t,api)
    sys.modules['full_ssb_local_continuation'].__file__=str(t.ROOT/'wrong.py')
    with pytest.raises(ValueError):t.accepted()
    assert calls==[]


def test_only_configuration_changes_math_and_visible_scope_are_frozen():
    t=target();c=t.configuration()
    assert c['cap']==1000000 and c['policy_applied'] is False
    assert c['training_rows']==dict(lineorder=1000000,dwdate=2556,customer=1000000,part=1000000,supplier=1000000)
    assert c['prefix']=='aqp_ssb_local_continuation_'
    assert c['pointer']=='ssb_local_continuation_tables_latest.json'
    assert 'adopt' in c['evaluation_note'].lower() and 'reverse' in c['evaluation_note'].lower()
    assert 'n/p' in c['normalizer_scope'] and 'not calibration' in c['ci_scope']


def test_synthetic_shared_build_retains_all_groups_and_only_five_derived_outputs(monkeypatch,tmp_path):
    t=target();api=evidence(t);calls=install(monkeypatch,t,api)
    import full_common as common
    import full_aqp_tables as aqp
    import full_ssb_local_tables as generic
    import full_ssb_tables as math
    original_root=t.ROOT;root=tmp_path/'fixture';full=root/'output/full'
    monkeypatch.setattr(t,'ROOT',root)
    monkeypatch.setattr(generic,'ROOT',root);monkeypatch.setattr(common,'FULL',full)
    monkeypatch.setattr(generic,'__file__',str(root/'code/full_ssb_local_tables.py'))
    monkeypatch.setattr(aqp,'ROOT',root);monkeypatch.setattr(math,'ROOT',root)
    sys.modules['full_ssb_local_continuation'].__file__=str(root/'code/full_ssb_local_continuation.py')
    api['report']['directory']=str(root/'output/full/ssb/local_sf500_continuation/runs'/('b'*20))
    path=root/api['published_result']['path'];path.parent.mkdir(parents=True)
    payload=json.dumps(api['report']).encode();path.write_bytes(payload)
    api['published_result'].update(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
    sql=root/'code/benchmarks/ssb/sql/aqp_queries.sql';sql.parent.mkdir(parents=True)
    sql.write_text((original_root/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text())
    for name in t.configuration()['helpers']+['code/full_ssb_tables.py','code/full_aqp_tables.py']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture helper')
    def draw(directory,*args):
        for name in ('ssb_relative_error.png','ssb_ci_half_width.png'):(directory/name).write_bytes(b'fixture PNG')
    monkeypatch.setattr(generic,'draw_local',draw)
    def forbidden(*a,**k):raise AssertionError('no process, DB, model or scientific API')
    import pickle,socket,sqlite3,subprocess
    for module,name in [(pickle,'load'),(socket,'create_connection'),(sqlite3,'connect'),(subprocess,'Popen')]:
        monkeypatch.setattr(module,name,forbidden)
    before=path.read_bytes();t.main()
    assert calls==['one-public-continuation'] and path.read_bytes()==before
    pointer=json.loads((full/'results'/t.configuration()['pointer']).read_text())
    directory=root/pointer['path'];manifest=json.loads((directory/'manifest.json').read_text())
    assert {d['path'].split('/')[-1] for d in manifest['artifacts']}==math.OUTPUT_NAMES
    assert manifest['group_truth_rows']==2059 and manifest['scope']==t.SCOPE
    assert manifest['full_paper_complete'] is False and manifest['author_different_groups']==1713
    assert manifest['paper_figure11_training_budget_reproduced'] is False
    with (directory/'all_groups.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==2059 and {r['ci_status'] for r in rows}=={'LESS_THAN_10_SAMPLES'}
    with (directory/'query_summary.csv').open(newline='') as stream:queries=list(csv.DictReader(stream))
    assert len(queries)==13 and sum(int(q['reference_ci_excluded']) for q in queries)==2059
    assert manifest['binding_details']['readonly_acceptance']['continuation_validation']['adopted_forward'] is True
    t.main();assert calls==['one-public-continuation']*2  # fresh acceptance even on exact reuse
    (directory/'training_tables.csv').write_text('tampered')
    with pytest.raises(ValueError,match='changed'):t.main()
    assert calls==['one-public-continuation']*3
