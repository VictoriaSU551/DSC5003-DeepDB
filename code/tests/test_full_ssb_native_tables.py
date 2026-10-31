import copy

import pytest

from full_ssb_native_tables import validate_formal_report


def fixture():
    return dict(stage='SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI',spn_count=5,
        full_paper_reproduction_complete=False,author_population_row_count_and_13_truths_match=True,
        author_full_row_byte_identity_proven=False,population_rows=3000028242,
        actual_sample_rows=10000001,point_query_errors=0,ci_query_errors=0,
        training_tables=[dict(table=t,actual_training_rows=2556 if t=='dwdate' else 1000000)
            for t in ['lineorder','dwdate','customer','part','supplier']])


def test_native_formal_report_is_distinct_from_failed_legacy_population():
    validate_formal_report(fixture(),10000001)


@pytest.mark.parametrize('change',['legacy','sample','population','training_subset','training_duplicate','budget','raw_identity','full_paper','query_error'])
def test_wrong_scope_or_model_cannot_become_a_derived_native_table(change):
    report=copy.deepcopy(fixture())
    if change=='legacy':report['stage']='SSB_SF500_SINGLE_1M_AQP_CI'
    if change=='sample':report['actual_sample_rows']-=1
    if change=='population':report['population_rows']+=92
    if change=='training_subset':report['training_tables'].pop()
    if change=='training_duplicate':report['training_tables'][-1]=report['training_tables'][0]
    if change=='budget':report['training_tables'][0]['actual_training_rows']=10000
    if change=='raw_identity':report['author_full_row_byte_identity_proven']=True
    if change=='full_paper':report['full_paper_reproduction_complete']=True
    if change=='query_error':report['ci_query_errors']=1
    with pytest.raises(ValueError):validate_formal_report(report,10000001)
