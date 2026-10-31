"""Array bit preservation, runtime seals, actual C++ boundaries, and RSS guard."""
import hashlib
import importlib
import struct
import sys

import pytest


def implementation():
    try:
        return importlib.import_module('full_cpp_scale')
    except ModuleNotFoundError as exc:
        if exc.name != 'full_cpp_scale':
            raise
        pytest.fail('External-array C++ adapter is not implemented')


def test_external_arrays_preserve_every_double_and_float_bit(tmp_path):
    module = implementation()
    source = '''double scalar=0.2;
    double nodeIntermediateResult[4] = {0};
    vector<double> uniqueVals1{0.1, -0.0, 1e-200, 1.0000000000000002, 9007199254740992.0};
    vector<double> probSum1{0., .1, 1.};
    double probsNode3[] = {0.1, 0.2, 0.7};
    vector<float> uniqueVals9{0.1, 1.0000000596046448};
    vector<double>::iterator leftBoundIdx1;
    '''
    destination = tmp_path / 'arrays.bin'
    rewritten, record = module.externalize_arrays(source, destination)
    assert len(record['arrays']) == 4
    assert 'double scalar=0.2' in rewritten
    assert 'double nodeIntermediateResult[4] = {0}' in rewritten
    assert 'static const vector<double> uniqueVals1' in rewritten
    assert 'vector<double>::const_iterator leftBoundIdx1' in rewritten
    expected = [struct.pack('<5d', .1, -0., 1e-200, 1.0000000000000002, 9007199254740992.),
                struct.pack('<3d', 0., .1, 1.), struct.pack('<3d', .1, .2, .7),
                struct.pack('<2f', .1, 1.0000000596046448)]
    raw = destination.read_bytes()
    assert raw == b''.join(expected)
    for item, payload in zip(record['arrays'], expected):
        assert raw[item['offset']:item['offset'] + item['bytes']] == payload
        assert item['sha256'] == hashlib.sha256(payload).hexdigest()


def test_expressions_are_not_silently_evaluated_as_array_values(tmp_path):
    module = implementation()
    destination = tmp_path / 'arrays.bin'
    destination.write_bytes(b'existing verified blob')
    with pytest.raises(ValueError, match='literal'):
        module.externalize_arrays('vector<double> uniqueVals1{1.0, (2.0+1)};', destination)
    assert destination.read_bytes() == b'existing verified blob'


def test_asset_seal_rejects_same_length_binary_tamper(tmp_path):
    module = implementation()
    path = tmp_path / 'arrays.bin'
    path.write_bytes(struct.pack('<2d', .1, .9))
    record = [{'path': path.name, 'sha256': module.file_hash(path), 'bytes': path.stat().st_size}]
    module.validate_assets(record, tmp_path)
    modified = bytearray(path.read_bytes())
    modified[0] ^= 1
    path.write_bytes(modified)
    with pytest.raises(ValueError, match='hash|SHA'):
        module.validate_assets(record, tmp_path)


def test_actual_compiled_external_arrays_cover_null_open_closed_and_domain_edges():
    module = implementation()
    report = module.boundary_differential(module.OUT / 'boundary_tdd')
    assert report['status'] == 'PASS', report
    assert len(report['cases']) == 12
    assert report['external_array_count'] == 2
    assert report['binary_tamper_runtime_rejected'] is True
    assert report['compile_peak_tree_rss_bytes'] > 0


def test_resource_guard_stops_only_its_owned_process(tmp_path):
    module = implementation()
    report = module.run_limited(
        [sys.executable, '-B', '-c', 'import time; payload=bytearray(8*1024*1024); time.sleep(3)'],
        tmp_path, 'memory_guard', memory_limit=1024 * 1024)
    assert report['stopped_for_memory'] is True
    assert report['returncode'] != 0
    assert report['peak_tree_rss_bytes'] > 1024 * 1024
    assert report['scope'] == 'Owned subprocess and observed descendants only'


def test_public_workload_alignment_and_figure8_dimensions():
    module = implementation()
    workload = module.load_workload()
    assert len(workload['queries']) == 753
    assert workload['job_light_queries'] == 70
    assert workload['grouped_queries'] == 683
    assert len({(q['tables'], q['predicates']) for q in workload['queries']
                if q['group'] != 'job_light' and q['tables'] in (4, 5, 6)}) == 15


def range_adapter():
    try:
        return importlib.import_module('full_cpp_range_adapter')
    except ModuleNotFoundError as exc:
        if exc.name != 'full_cpp_range_adapter':
            raise
        pytest.fail('Ordered numeric inversion adapter is not implemented')


def test_inversion_flags_map_to_ordered_feature_columns():
    adapter = range_adapter()
    assert adapter.inverse_feature_indices([6, 5, 4], [False, False, True]) == [4]
    assert adapter.inverse_feature_indices([5, 4], [False, True]) == [4]
    assert adapter.inverse_feature_indices([6, 4], [True, True]) == [6, 4]
    assert adapter.inverse_feature_indices([], []) == []
    with pytest.raises(ValueError, match='length'):
        adapter.inverse_feature_indices([6], [])


def test_runtime_adapter_fixes_real_converter_without_mutating_flags_or_source(monkeypatch):
    adapter = range_adapter()
    import rspn.rspn as rspn_module
    import rspn.algorithms.expectations as expectation_module
    from spn.structure.StatisticalTypes import MetaType
    flags = [False, False, True]
    original_converter = expectation_module.convert_range
    original_file_hash = implementation().file_hash(expectation_module.convert_range.__code__.co_filename)
    def convert_at_expectation_boundary(spn, ordered_scope, inverted, conditions, **kwargs):
        return expectation_module.convert_range(
            [True] * 7, [i in ordered_scope for i in range(7)],
            [MetaType.REAL] * 7, conditions, inverted)
    monkeypatch.setattr(rspn_module, 'expectation', convert_at_expectation_boundary)
    # Reproduce the original wrong parameter: column 4 should be inverted.
    assert original_converter([True] * 7, [i in [6, 5, 4] for i in range(7)],
                              [MetaType.REAL] * 7, [None] * 7, flags)[1][2 + 4 * 8] is False
    with adapter.mapped_numeric_inversion() as audit:
        applicable, parameters = rspn_module.expectation(None, [6, 5, 4], flags, [None] * 7)
        assert applicable is True
        assert [parameters[2 + i * 8] for i in range(7)] == [False, False, False, False, True, False, False]
        assert audit['converted_calls'] == 1
        assert audit['inverted_calls'] == 1
    assert flags == [False, False, True]
    assert expectation_module.convert_range is original_converter
    assert implementation().file_hash(original_converter.__code__.co_filename) == original_file_hash


def test_runtime_adapter_restores_both_entry_points_after_failure():
    adapter = range_adapter()
    import rspn.rspn as rspn_module
    import rspn.algorithms.expectations as expectation_module
    original_expectation, original_converter = rspn_module.expectation, expectation_module.convert_range
    with pytest.raises(RuntimeError, match='interrupted'):
        with adapter.mapped_numeric_inversion():
            assert rspn_module.expectation is not original_expectation
            assert expectation_module.convert_range is not original_converter
            raise RuntimeError('interrupted')
    assert rspn_module.expectation is original_expectation
    assert expectation_module.convert_range is original_converter


def test_training_label_selects_receipt_without_allowing_path_traversal():
    module = implementation()
    label = 'paper_proxy_public_scale_rdc_n10000000_b0p5'
    assert module.training_receipt_path(label) == module.ROOT / 'output/full/results' / (label + '_training.json')
    with pytest.raises(ValueError, match='label'):
        module.training_receipt_path('../outside')


def test_model_build_paths_keep_the_sealed_five_spn_run_separate():
    module = implementation()
    old = {'training_label': 'old', 'model_sha256': 'a' * 64}
    new = {'training_label': 'new', 'model_sha256': 'b' * 64}
    assert module.model_build_directory(old) != module.model_build_directory(new)
    assert 'b' * 16 in module.model_build_directory(new).name
    assert module.model_build_directory(old).name != 'public_scale_10m_double_d01024d1a4a5'


def test_v2_reference_is_bound_to_model_csv_query_and_helper_hashes(tmp_path, monkeypatch):
    import csv
    import json
    module = implementation()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    label, model_hash = 'paper_proxy_test', 'b' * 64
    summary_path = tmp_path / 'output/full/results' / (label + '_evaluation_v2.json')
    summary_path.parent.mkdir(parents=True)
    source = tmp_path / 'output/full/evaluation_v2' / label / 'job_light.csv'
    source.parent.mkdir(parents=True)
    sql = 'select count(*) from title t;'
    with source.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['query_no', 'query', 'cardinality_true', 'cardinality_predict'])
        writer.writeheader()
        writer.writerow(dict(query_no=0, query=sql, cardinality_true=3, cardinality_predict=4.25))
    helpers = {}
    for name in ['full_factor_cache.py', 'full_evaluation_v2.py']:
        path = tmp_path / 'code' / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('# frozen helper')
        helpers[name] = module.file_hash(path)
    summary = {'status': 'PASS', 'protocol': 'model_identity_factor_hash_and_cold_query_cache_v2',
               'model_sha256': model_hash, 'queries': 1,
               'groups': {'job_light': {'csv_sha256': module.file_hash(source), 'helpers': helpers}}}
    summary_path.write_text(json.dumps(summary))
    workload = {'queries': [{'group': 'job_light', 'query_no': 0, 'sql': sql, 'cardinality_true': 3}]}
    reference = module.load_v2_references(label, workload, model_hash)
    assert reference['rows']['job_light'][0]['cardinality_predict'] == '4.25'
    with pytest.raises(ValueError, match='model'):
        module.load_v2_references(label, workload, 'c' * 64)
    source.write_text(source.read_text().replace('4.25', '5.25'))
    with pytest.raises(ValueError, match='hash|SHA'):
        module.load_v2_references(label, workload, model_hash)
