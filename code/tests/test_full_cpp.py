"""Generated numerical results must agree with the Python estimator."""
import importlib
import importlib.util
from pathlib import Path

import pytest


def cpp_module():
    assert importlib.util.find_spec('full_cpp') is not None, 'C++ verification runner is missing'
    return importlib.import_module('full_cpp')


def test_generated_open_upper_boundary_matches_python():
    module = cpp_module()
    report = module.boundary_differential(module.CPP / 'regression_open_upper',
                                          cases=[(-float('inf'), 3.0, True, False)])
    assert report['cases'][0]['python'] == pytest.approx(0.2)
    assert report['cases'][0]['cpp'] == pytest.approx(0.2, rel=1e-6)
    assert report['status'] == 'PASS'


def test_generated_numeric_boundary_matrix_matches_python():
    module = cpp_module()
    report = module.boundary_differential(module.CPP / 'regression_boundary_matrix')
    assert len(report['cases']) == 12
    assert report['status'] == 'PASS', report


def test_differential_rejects_mismatch_and_no_cpp_calls():
    check = cpp_module().check_prediction_pairs
    assert check([10.0], [10.000001], [1])['status'] == 'PASS'
    assert check([10.0], [11.0], [1])['status'] == 'FAIL'
    assert check([10.0], [10.0], [0])['status'] == 'FAIL'
    assert check([10.0], [float('nan')], [1])['status'] == 'FAIL'


def test_model_copy_keeps_original_bytes(tmp_path):
    module = cpp_module()
    source = tmp_path / 'original.pkl'
    source.write_bytes(b'original fitted model')
    copied = tmp_path / 'new' / 'model_with_ids.pkl'
    seal = module.copy_model(source, copied)
    copied.write_bytes(b'generated model with assigned ids')
    assert source.read_bytes() == b'original fitted model'
    assert seal['source_sha256'] == module.file_hash(source)
    with pytest.raises(ValueError, match='different'):
        module.copy_model(source, source)
