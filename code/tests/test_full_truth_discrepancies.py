from full_truth_discrepancies import classify


def test_agreeing_independent_engines_do_not_silently_accept_published_difference():
    assert classify(1104284888, 1104284894, 1104284894) == 'CONFIRMED_PUBLIC_INPUT_DIFFERENCE'
    assert classify(5, 5, 5) == 'PUBLISHED_MATCH'
    assert classify(5, 6, 5) == 'ARRAY_ENGINE_FAILURE'
