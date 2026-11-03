from full_prepare import schema_for_profile


def test_public_scale_profile_retains_required_person_predicate():
    original = schema_for_profile('joblight')
    extended = schema_for_profile('public-scale')
    assert 'person_id' in original.table_dictionary['cast_info'].irrelevant_attributes
    assert 'person_id' not in extended.table_dictionary['cast_info'].irrelevant_attributes
    assert 'person_id' in extended.table_dictionary['cast_info'].no_compression
