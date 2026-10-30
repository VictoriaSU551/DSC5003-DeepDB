"""A local result must never be presented as author-population reproduction."""
import copy
import pytest
from full_ssb_local_tables import validate_formal_report


def fixture():
    return dict(stage='LOCAL_SSB_SF500_SINGLE_1M_AQP_CI',scope='LOCAL_SSB_SF500',
        spn_count=5,full_paper_reproduction_complete=False,author_reproduction_complete=False,
        author_population_row_count_and_13_truths_match=False,
        author_different_groups=1713,author_full_row_byte_identity_proven=False,
        population_rows=3000028242,actual_sample_rows=9996946,
        point_query_errors=0,ci_query_errors=0,
        training_tables=[dict(table=t,actual_training_rows=2556 if t=='dwdate' else 1000000)
            for t in ['lineorder','dwdate','customer','part','supplier']])


def test_complete_local_report_keeps_failed_author_gate_visible():
    validate_formal_report(fixture(),9996946)


@pytest.mark.parametrize('change',['stage','scope','author','author_truths','different','sample',
    'population','training_subset','training_duplicate','budget','raw_identity','full_paper','query_error'])
def test_wrong_scope_or_incomplete_science_cannot_become_local_figure(change):
    report=copy.deepcopy(fixture())
    if change=='stage':report['stage']='SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI'
    if change=='scope':report['scope']='AUTHOR_SSB_SF500'
    if change=='author':report['author_reproduction_complete']=True
    if change=='author_truths':report['author_population_row_count_and_13_truths_match']=True
    if change=='different':report['author_different_groups']=0
    if change=='sample':report['actual_sample_rows']-=1
    if change=='population':report['population_rows']+=92
    if change=='training_subset':report['training_tables'].pop()
    if change=='training_duplicate':report['training_tables'][-1]=report['training_tables'][0]
    if change=='budget':report['training_tables'][0]['actual_training_rows']=10000
    if change=='raw_identity':report['author_full_row_byte_identity_proven']=True
    if change=='full_paper':report['full_paper_reproduction_complete']=True
    if change=='query_error':report['ci_query_errors']=1
    with pytest.raises(ValueError):validate_formal_report(report,9996946)
