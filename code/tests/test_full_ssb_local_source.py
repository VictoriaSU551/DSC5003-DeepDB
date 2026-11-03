"""Local metadata and fail-closed tests; no physical native-source audit."""
import copy
from fractions import Fraction
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_ssb_local_source.py'
    assert path.exists(),'independent local source gate missing'
    spec=importlib.util.spec_from_file_location('ssb_local_source_test',str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def decision(m):
    return dict(schema='root_local_ssb_scope_decision_v1',status='ROOT_LOCAL_SCOPE_DECISION',scope=m.SCOPE,
        local_model_experiment_in_scope=True,source_audit_allowed_after_code_review=True,
        model_execution_authorized_by_this_record=False,model_execution_requires_separate_reviewed_plan_and_memory_release=True,
        generator_reexecution_authorized=False,author_gate_pass_authorized=False,strict_author_latches_must_remain_false=True,full_paper_complete=False,
        original_report={'path':m.NATIVE_REPORT,'sha256':m.NATIVE_REPORT_SHA,'bytes':4790908},
        author_gap_diagnostic={'path':m.DIAGNOSTIC,'sha256':m.DIAGNOSTIC_SHA,'bytes':3686},
        population_rows=m.N,actual_sample_rows=m.SAMPLE_ROWS,local_truth_groups=2059,matching_author_groups=346,different_author_groups=1713)


def metadata(m):
    author=m.base.load_author_groups(ROOT);truth=copy.deepcopy(author)
    for record in truth:
        if record['query_no']>=6:record['value']+=1
    desc=lambda path:dict(path=str(ROOT/path),bytes=123,sha256='a'*64)
    dims={name:dict(desc('data/ssb/sf500_native_v2/dimensions/'+name+'.tbl'),rows=rows) for name,(rows,_) in m.base.DIMENSIONS.items()}
    binding=dict(scale='500',total_orders=750000000,shards=4000,sample_seed=20261030,actual_cutoff=m.CUTOFF,dimensions=dims,
        formal_review_plan_sha256=m.base.NATIVE_REVIEW_PLAN_SHA)
    binding['source_id']=m.base.value_hash(binding)
    plan=dict(schema='ssb_native_v2_stream_plan_v1',binding=binding,ranges=[[i*187500+1,187500] for i in range(4000)])
    sample=dict(desc('data/ssb/sf500_native_v2/lineorder_sampled.csv'),rows=m.SAMPLE_ROWS)
    state=dict(schema='ssb_native_v2_checkpoint_v1',binding=binding,complete=True,next_shard=4000,
        committed_shards=[dict(shard=i,first_order=i*187500+1,orders=187500) for i in range(4000)],rows=m.N,sample_rows=m.SAMPLE_ROWS,
        sample_bytes=sample['bytes'],sample_sha256=sample['sha256'],aggregates=truth)
    b=dict(schema='ssb_native_v2_final_v1',status='MISMATCH',complete=False,paper_population_row_count_and_13_truths_match=False,
        raw_snapshot_identity_claimed=False,N=m.N,population_rows=m.N,sample_rows=m.SAMPLE_ROWS,source_id=binding['source_id'],canonical_truth=truth,
        raw_sample=sample,dimensions=dims,plan=desc('output/full/ssb/native_v2/formal500/stream/plan.json'),
        checkpoint=desc('output/full/ssb/native_v2/formal500/stream/checkpoint.json'),
        sampling=dict(sample_seed=20261030,actual_cutoff=m.CUTOFF,probability_numerator=m.CUTOFF,probability_denominator=2**64,
            requested_numerator=3333,requested_denominator=1000000,effective_probability=float(Fraction(m.CUTOFF,2**64)),
            normalizer_numerator=m.SAMPLE_ROWS*2**64,normalizer_denominator=m.CUTOFF,normalizer_n_over_p=float(Fraction(m.SAMPLE_ROWS*2**64,m.CUTOFF))))
    b['author_comparison']=m.compare_author(truth,author)
    return b,state,plan,author


def test_exact_local_metadata_preserves_complete_author_mismatch():
    m=module();m.validate_decision(decision(m));b,state,plan,author=metadata(m)
    result=m.validate_metadata(b,state,plan,author)
    assert result['scope']==m.SCOPE and result['different_author_groups']==1713 and result['matching_author_groups']==346
    assert result['fact_normalizer']!=dict(numerator=m.N,denominator=1)
    assert result['author_truth_match'] is False


@pytest.mark.parametrize('field',['scope','model_execution_authorized_by_this_record','author_gate_pass_authorized','generator_reexecution_authorized','different_author_groups'])
def test_root_local_decision_cannot_authorize_science_or_launder_author_gate(field):
    m=module();d=decision(m);d[field]=True if type(d[field]) is bool else 'wrong'
    with pytest.raises(ValueError):m.validate_decision(d)


@pytest.mark.parametrize('damage',['author_pass','complete','N','sample','missing_truth','float_truth','changed_gap','unfinished','missing_shard','range_gap','normalizer','probability'])
def test_local_metadata_rejects_scope_or_source_laundering(damage):
    m=module();b,state,plan,author=metadata(m)
    if damage=='author_pass':b['status']='PASS_AUTHOR_TRUTHS'
    elif damage=='complete':b['complete']=True
    elif damage=='N':b['population_rows']+=1
    elif damage=='sample':b['sample_rows']+=1
    elif damage=='missing_truth':b['canonical_truth'].pop()
    elif damage=='float_truth':b['canonical_truth'][0]['value']=float(b['canonical_truth'][0]['value'])
    elif damage=='changed_gap':b['canonical_truth'][-1]['value']=author[-1]['value']
    elif damage=='unfinished':state['complete']=False
    elif damage=='missing_shard':state['committed_shards'].pop()
    elif damage=='range_gap':state['committed_shards'][1]['first_order']+=1
    elif damage=='normalizer':b['sampling']['normalizer_n_over_p']=m.N
    else:b['sampling']['actual_cutoff']+=1
    with pytest.raises(ValueError):m.validate_metadata(b,state,plan,author)


def test_default_local_source_verify_missing_fails_without_creating_output(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='missing'):m.verify_local_source(root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_physical_source_audit_requires_explicit_matching_code_review_before_access(tmp_path):
    m=module()
    with pytest.raises(ValueError,match='review|decision'):m.audit_local_source('0'*64,'0'*64,root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def synthetic_source_publication(m,root):
    report={'schema':'ssb_local_sf500_source_v1','status':m.STATUS,'scope':m.SCOPE,'synthetic_only':True,'local_sources':{p:'a'*64 for p in m.LOCAL_FILES}}
    binding=dict(scope=m.SCOPE,decision_sha256=m.DECISION_SHA,native_report_sha256=m.NATIVE_REPORT_SHA,local_codes_sha256=m.value_hash(report['local_sources']))
    home=root/m.OUTPUT/'audits'/m.value_hash(binding)[:20]
    m.base.formal_transaction(home,binding,lambda:report,lambda r:None,kind='LOCAL_SOURCE_AUDIT')
    return report,home


def test_source_publication_complete_and_readonly_without_repair(tmp_path,monkeypatch):
    m=module();report,home=synthetic_source_publication(m,tmp_path)
    m.publish_source(report,home,tmp_path)
    monkeypatch.setattr(m,'collect_physical_source',lambda root:report)
    before={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}
    assert m.verify_local_source(tmp_path)['status']==m.STATUS
    assert before=={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('failure',['writer','running'])
def test_source_publication_failure_taints_source_audit_and_never_reseals(tmp_path,monkeypatch,failure):
    m=module();report,home=synthetic_source_publication(m,tmp_path)
    if failure=='writer':
        def fail(*args):raise ValueError('synthetic source publication failure')
        monkeypatch.setattr(m,'write_source_publication',fail)
    else:m.atomic(home/'publication_control/lifecycle.json',dict(status='RUNNING',binding=m.source_publication_binding(report,home)))
    with pytest.raises(ValueError):m.publish_source(report,home,tmp_path)
    assert m.read(home/'lifecycle.json')['status']=='TAINTED'
    assert m.read(home/'publication_control/lifecycle.json')['status']=='TAINTED'
    with pytest.raises(ValueError):m.publish_source(report,home,tmp_path)


def test_source_audit_cannot_reseal_a_different_controller_binding(tmp_path,monkeypatch):
    m=module();report,home=synthetic_source_publication(m,tmp_path)
    receipt=m.read(home/'receipt.json');life=m.read(home/'lifecycle.json');receipt['binding']['decision_sha256']='f'*64
    life['binding']=receipt['binding'];m.atomic(home/'receipt.json',receipt);life['receipt_sha256']=m.digest(home/'receipt.json');m.atomic(home/'lifecycle.json',life)
    m.publish_source(report,home,tmp_path);monkeypatch.setattr(m,'collect_physical_source',lambda root:report)
    with pytest.raises(ValueError,match='binding|namespace'):m.verify_local_source(tmp_path)
