"""Recovery has to prove all committed physical bytes before discarding a tail."""
import hashlib
import importlib
import json
from pathlib import Path

import pytest


def fixture(tmp_path):
    root=tmp_path/'run';chunk=root/'chunks/00000000';chunk.mkdir(parents=True)
    data=b'1|original\n2|original\n';sample=root/'sample.csv';sample.write_bytes(data)
    (chunk/'stats.json').write_text(json.dumps({'rows':6,'sample_rows':2,'unmatched_foreign_keys':0}))
    (chunk/'aggregates.tsv').write_text('0\t100\n3\t1992\tMFGR#1\t200\n')
    (chunk/'seeds_after.tsv').write_text('0\t0\t1\t0\t1\n')
    files={p.relative_to(root).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in chunk.iterdir()}
    binding={'sample_seed':20261030,'source_id':'fixed','cutoff':123}
    record={'shard':0,'first_order':1,'orders':2,'rows':6,'sample_rows':2,'sample_bytes':len(data),
            'sample_sha256':hashlib.sha256(data).hexdigest(),'files':files}
    state={'schema':'ssb_native_v2_checkpoint_v1','binding':binding,'next_shard':1,'committed_shards':[record],
           'rows':6,'sample_rows':2,'sample_bytes':len(data),'sample_sha256':hashlib.sha256(data).hexdigest(),
           'aggregates':[{'query_no':0,'group':[],'value':100},{'query_no':3,'group':['1992','MFGR#1'],'value':200}]}
    return root,sample,binding,state


def test_committed_prefix_is_preserved_and_only_uncommitted_tail_truncated(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_stream');root,sample,binding,state=fixture(tmp_path)
    expected=sample.read_bytes();sample.write_bytes(expected+b'UNCOMMITTED partial tail')
    module.validate_restore(sample,state,binding,root,[(1,2),(3,2)],truncate=True)
    assert sample.read_bytes()==expected


@pytest.mark.parametrize('field,value',[('source_id','changed'),('sample_seed',99),('cutoff',124)])
def test_changed_source_seed_or_probability_refuses_recovery_without_truncation(tmp_path,field,value):
    module=importlib.import_module('full_ssb_native_v2_stream');root,sample,binding,state=fixture(tmp_path)
    sample.write_bytes(sample.read_bytes()+b'tail');before=sample.read_bytes();binding=dict(binding,**{field:value})
    with pytest.raises(ValueError,match='binding'):module.validate_restore(sample,state,binding,root,[(1,2)],truncate=True)
    assert sample.read_bytes()==before


def test_corrupt_committed_aggregate_is_refused_before_sample_tail_truncation(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_stream');root,sample,binding,state=fixture(tmp_path)
    (root/'chunks/00000000/aggregates.tsv').write_text('0\t101\n');before=sample.read_bytes()+b'tail';sample.write_bytes(before)
    with pytest.raises(ValueError,match='artifact'):module.validate_restore(sample,state,binding,root,[(1,2)],truncate=True)
    assert sample.read_bytes()==before


def test_checkpoint_cannot_truncate_in_middle_of_a_committed_line(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_stream');root,sample,binding,state=fixture(tmp_path)
    state['sample_bytes']-=1;state['committed_shards'][0]['sample_bytes']-=1
    state['sample_sha256']=state['committed_shards'][0]['sample_sha256']=hashlib.sha256(sample.read_bytes()[:-1]).hexdigest()
    with pytest.raises(ValueError,match='line'):module.validate_restore(sample,state,binding,root,[(1,2)],truncate=True)


def test_empty_artifact_map_or_noncontiguous_shards_refuses_recovery(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_stream');root,sample,binding,state=fixture(tmp_path)
    state['committed_shards'][0]['files']={}
    with pytest.raises(ValueError,match='inventory'):module.validate_restore(sample,state,binding,root,[(1,2)],truncate=True)


def test_actual_native_restart_matches_uninterrupted_sample_and_integer_truth(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_stream')
    native=importlib.import_module('full_ssb_native_v2');gate=native.callback_tiny_gate()
    dimensions=native.OUTPUT/('callback_tiny_'+native.object_sha(gate['binding'])[:16])/'dimensions'
    plan=module.stream_plan('0.001',1500,4,dimensions,20261030,1<<63)
    whole=module.stream(plan,tmp_path/'whole')
    interrupted=module.stream(plan,tmp_path/'resumed',stop_after=2)
    assert interrupted['status']=='PAUSED_FOR_TEST'
    sample=tmp_path/'resumed/lineorder_sampled.csv';sample.write_bytes(sample.read_bytes()+b'uncommitted-tail')
    resumed=module.stream(plan,tmp_path/'resumed',resume=True)
    assert whole['checkpoint']['aggregates']==resumed['checkpoint']['aggregates']
    assert (tmp_path/'whole/lineorder_sampled.csv').read_bytes()==sample.read_bytes()
    assert resumed['checkpoint']['rows']==6005
    assert resumed['resumed_shards']==2


def test_wrong_resume_plan_cannot_taint_an_existing_complete_namespace(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_native_v2_stream');home=tmp_path/'complete';home.mkdir()
    original={'status':'STREAM_COMPLETE','plan_sha256':'original'}
    module.native.atomic(home/'lifecycle.json',original)
    monkeypatch.setattr(module,'check_plan',lambda plan:plan['binding'])
    with pytest.raises(ValueError,match='lifecycle'):module.stream({'binding':{'wrong':True}},home,resume=True)
    assert json.loads((home/'lifecycle.json').read_text())==original


def test_os_execution_lock_refuses_a_second_controller(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_stream')
    with module.namespace_lock(tmp_path):
        with pytest.raises(ValueError,match='active execution lock'):
            with module.namespace_lock(tmp_path):raise AssertionError('Second controller obtained lock')


def test_cleanup_failure_keeps_committed_science_and_reports_the_residual(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_native_v2_stream');path=tmp_path/'sample.csv';path.write_bytes(b'committed\n')
    def refuse(*args,**kwargs):raise PermissionError('Temporary AV sharing refusal')
    monkeypatch.setattr(Path,'unlink',refuse)
    failure=module.cleanup_committed_sample(path,3)
    assert failure['shard']==3 and 'PermissionError' in failure['error']
    assert path.read_bytes()==b'committed\n'
