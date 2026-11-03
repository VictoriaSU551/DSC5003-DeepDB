"""The new population cannot inherit PASS from the historical failed run."""
import importlib
from pathlib import Path
import pickle

import pytest

ROOT=Path(__file__).resolve().parents[2]


def truths():
    with (ROOT/'code/benchmarks/ssb/ground_truth_500GB.pkl').open('rb') as stream:raw=pickle.load(stream)
    return [{'query_no':q,'group':[str(v) for v in row[:-1]],'value':row[-1]} for q,rows in sorted(raw.items()) for row in rows]


def test_author_gate_requires_exact_population_rows_and_all_2059_integer_groups():
    module=importlib.import_module('full_ssb_native_v2_formal');groups=truths()
    assert module.author_check(3000028242,groups)['match']
    result=module.author_check(3000028334,groups)
    assert not result['match'] and result['row_difference']==92
    groups[0]['value']+=1
    assert not module.author_check(3000028242,groups)['match']


@pytest.mark.parametrize('defect',['duplicate','missing','float'])
def test_author_gate_refuses_duplicate_missing_or_float_truth(defect):
    module=importlib.import_module('full_ssb_native_v2_formal');groups=truths()
    if defect=='duplicate':groups.append(dict(groups[0]))
    if defect=='missing':groups.pop()
    if defect=='float':groups[0]['value']=float(groups[0]['value'])
    if defect=='missing':assert not module.author_check(3000028242,groups)['match']
    else:
        with pytest.raises(ValueError):module.author_check(3000028242,groups)


def test_final_readonly_verify_does_not_create_evidence_or_run_a_generator(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_native_v2_formal')
    def forbidden(*args,**kwargs):raise AssertionError('Read-only verifier attempted execution')
    monkeypatch.setattr(module.native,'callback_build',forbidden)
    with pytest.raises((ValueError,FileNotFoundError)):module.verify_final(tmp_path/'missing.json')
    assert list(tmp_path.iterdir())==[]


def test_final_guard_refuses_tainted_namespace_even_when_report_sha_matches(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_formal');report=tmp_path/'report.json';report.write_text('{}')
    module.native.atomic(tmp_path/'lifecycle.json',{'status':'TAINTED','final_report_sha256':module.native.digest(report),'review_plan_sha256':'fixed'})
    with pytest.raises(ValueError,match='FINAL_PASS'):module.require_final_guard(tmp_path,report,'fixed')


def test_unconsumed_cleanup_residual_is_not_a_scientific_dependency(tmp_path):
    module=importlib.import_module('full_ssb_native_v2_formal');home=tmp_path/'stream';chunk=home/'chunks/00000000';chunk.mkdir(parents=True)
    residual=chunk/'sample.csv';residual.write_bytes(b'committed elsewhere; not consumed\n')
    b={'native_executable':{'path':'native.exe'},'native_build_receipt':{'path':'build.json'},
       'dimensions':{table:{'path':table+'.tbl'} for table in ['customer','supplier','part','date']},
       'native_runtime':{'direct_import_files':{}}}
    result=module.manifest_paths({'binding':b,'ranges':[[1,2]]},home,tmp_path/'actual_sample.csv')
    assert residual not in result.values()
