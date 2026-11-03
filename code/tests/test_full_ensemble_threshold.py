from full_ensemble_threshold import thresholded_pairs


def test_paper_threshold_does_not_inherit_public_point15_pairs():
    values = {(0, 1): .31, (0, 2): .30, (1, 2): .164845129522991}
    assert thresholded_pairs(values, .3) == {(0, 1): .31, (0, 2): 0., (1, 2): 0.}
    assert thresholded_pairs(values, .15) == values
