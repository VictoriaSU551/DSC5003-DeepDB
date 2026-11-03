from fractions import Fraction
import importlib.util
from pathlib import Path
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[2]


def module():
    path=ROOT/'code/full_verdict.py'
    assert path.exists(), 'Isolated Verdict setup/contract implementation is missing'
    spec=importlib.util.spec_from_file_location('full_verdict',str(path))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def test_original_archive_matches_parent_seal_and_rejects_modified_source(tmp_path):
    m=module();record=m.verify_original_source()
    assert record['sha256']=='72b068ce7dc501e065229b2b43eee19bd3777127e973db436256fd9770ae23c9'
    changed=tmp_path/'changed.zip';changed.write_bytes(b'not the sealed original source')
    with pytest.raises(ValueError,match='source seal'):
        m.verify_original_source(changed)


def test_zip_extraction_refuses_traversal_before_writing(tmp_path):
    m=module();archive=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(str(archive),'w') as z:z.writestr('../escape.txt','bad')
    with pytest.raises(ValueError,match='unsafe'):
        m.extract_safe(archive,tmp_path/'destination')
    assert not (tmp_path/'escape.txt').exists()


def test_sample_only_contract_has_exact_scale_and_excludes_truth_information():
    m=module();contract=m.sample_contract(9997912,1000000000)
    assert Fraction(contract['probability_numerator'],contract['probability_denominator'])==Fraction(9997912,1000000000)
    assert contract['execution_scope']=='EXISTING_UNIFORM_SAMPLE_ONLY'
    assert contract['original_rows_materialized']==0
    assert contract['query_truth_used_for_registration'] is False
    for n,N in [(0,100),(-1,100),(101,100),(1,0),(True,100)]:
        with pytest.raises(ValueError):m.sample_contract(n,N)


def test_real_java_standard_sample_and_registered_sample_share_exact_membership():
    m=module()
    assert hasattr(m,'run_gate'), 'Real original-engine two-path PostgreSQL gate is missing'
    if not m.runtime_jar().exists():pytest.skip('Original Verdict Java runtime has not been built')
    result=m.run_gate()
    assert result['status']=='PASS_STANDARD_AND_REGISTERED_SAMPLE_EQUIVALENCE'
    assert result['original_rows']==5000
    assert result['imported_original_rows']==0
    assert result['same_sample_membership'] is True
    assert result['query_truth_used_for_registration'] is False
    assert result['tested_queries']>=8
    assert result['successful_engine_queries']==24
    assert result['queries'][7]['raw_result_status']=='INCORRECT_RAW_UNSCALED_COMPOUND_SUM'
    assert result['queries'][7]['adapted_independent_sample_match'] is True


def test_postgres_build_patch_removes_only_unavailable_test_dependencies(tmp_path):
    m=module()
    assert hasattr(m,'prepare_pg_build'), 'Audited PostgreSQL build-only dependency patch is missing'
    record=m.prepare_pg_build(tmp_path/'pg-build')
    assert len(record['removed_test_dependencies'])==16
    assert record['java_sources_unchanged'] is True
    assert record['original_zip_sha256']==m.SOURCE_SHA
    assert all(d['scope']=='test' for d in record['removed_test_dependencies'])


def test_compound_sum_adapter_preserves_null_and_uses_only_original_outputs():
    m=module()
    assert hasattr(m,'compound_sum_adapter'), 'External arithmetic-only compound SUM adapter is missing'
    assert m.compound_sum_adapter(100.,35.)==65.
    assert m.compound_sum_adapter(None,35.) is None
    assert m.compound_sum_adapter(100.,None) is None
