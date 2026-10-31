"""The controller cannot turn a partial generator receipt into a model run."""
import importlib
import pytest


def ready():
    result={'status':'PASS','complete':True,'rows':3000028242,'sample_rows':10000000,
            'row_count_matches_author':True,'author_truth_comparison':{'match':True}}
    checkpoint={'rows':3000028242,'sample_rows':10000000,'next_shard':4001,
                'committed_shards':[{'shard':x} for x in range(1,4001)]}
    return result,checkpoint


def test_partial_generation_waits_even_if_row_count_reached():
    module=importlib.import_module('full_ssb_supervisor');result,checkpoint=ready()
    result['status']='CHECKPOINTED';result['complete']=False
    assert module.generation_decision(result,checkpoint)=='WAIT_GENERATION'


@pytest.mark.parametrize('mutation',['truth','rows','shards','sample'])
def test_false_completion_cannot_launch(mutation):
    module=importlib.import_module('full_ssb_supervisor');result,checkpoint=ready()
    if mutation=='truth':result['author_truth_comparison']['match']=False
    elif mutation=='rows':checkpoint['rows']-=1
    elif mutation=='shards':checkpoint['committed_shards'].pop()
    else:checkpoint['sample_rows']-=1
    with pytest.raises(ValueError):module.generation_decision(result,checkpoint)


def test_ready_generation_still_requires_memory_disk_and_mscn_completion():
    module=importlib.import_module('full_ssb_supervisor');result,checkpoint=ready()
    assert module.generation_decision(result,checkpoint)=='GENERATION_CANDIDATE_COMPLETE'
    assert not module.resources_ready(4*1024**3-1,6*1024**3,True,False)
    assert not module.resources_ready(4*1024**3,6*1024**3-1,True,False)
    assert not module.resources_ready(4*1024**3,6*1024**3,False,False)
    assert not module.resources_ready(4*1024**3,6*1024**3,True,True)
    assert module.resources_ready(4*1024**3,6*1024**3,True,False)


def test_polling_below_sixty_seconds_is_rejected_before_io():
    module=importlib.import_module('full_ssb_supervisor')
    with pytest.raises(ValueError,match='60'):module.run(interval=59)


def test_checkpoint_handle_is_closed_before_parser_and_writer_can_replace(tmp_path,monkeypatch):
    import json,os
    module=importlib.import_module('full_ssb_supervisor')
    source=tmp_path/'checkpoint.json';source.write_text('{"rows":1}')
    replacement=tmp_path/'next.json';replacement.write_text('{"rows":2}')
    original=json.loads
    def replacing_during_parser(text):
        os.replace(str(replacement),str(source))
        return original(text)
    monkeypatch.setattr(module.json,'loads',replacing_during_parser)
    assert module.read_shared(source)=={'rows':1}
    assert original(source.read_text())=={'rows':2}
