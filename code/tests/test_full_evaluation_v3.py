import pytest

from full_common import binding_hash
from full_evaluation_v3 import require_sealed, seal


def test_sealed_group_rejects_same_length_wrong_group_and_modified_value():
    expected = dict(group='5_2_SPN', queries=23, binding='inputs')
    receipt = seal(dict(expected, status='PASS', csv_sha256='original'))
    require_sealed(receipt, expected)
    with pytest.raises(ValueError, match='identity'):
        require_sealed(seal(dict(receipt, group='6_2_SPN')), expected)
    with pytest.raises(ValueError, match='seal'):
        require_sealed(dict(receipt, csv_sha256='changed'), expected)
