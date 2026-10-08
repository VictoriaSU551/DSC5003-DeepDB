"""The learner must import without starting worker processes at module scope."""
import importlib
import sys
from unittest.mock import patch


def test_import_does_not_spawn_workers():
    sys.modules.pop('rspn.learning.structure_learning', None)
    with patch('multiprocessing.Pool') as pool:
        importlib.import_module('rspn.learning.structure_learning')
        pool.assert_not_called()
