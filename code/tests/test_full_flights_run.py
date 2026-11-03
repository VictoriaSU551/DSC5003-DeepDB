from pathlib import Path

import pytest

from full_flights_run import retry_atomic_json


def denied(code=5):
    error = PermissionError(13, 'simulated Windows sharing conflict')
    error.winerror = code
    return error


def test_atomic_checkpoint_retries_transient_windows_access_denied(tmp_path):
    calls, delays, events = [], [], []
    def writer(path, value):
        calls.append((path, value))
        if len(calls) < 3:
            raise denied()
    retry_atomic_json(writer, tmp_path / 'checkpoint.json', {'cursor': 1756}, tmp_path,
                      sleep=delays.append, event_sink=events.append)
    assert len(calls) == 3 and calls[0] == calls[-1]
    assert len(delays) == len(events) == 2


def test_retry_never_replaces_paths_outside_the_scoped_output(tmp_path):
    with pytest.raises(ValueError, match='scope'):
        retry_atomic_json(lambda *a: None, tmp_path.parent / 'outside.json', {}, tmp_path)


def test_nonsharing_error_is_not_retried(tmp_path):
    calls = []
    def writer(*args):
        calls.append(1)
        raise denied(87)
    with pytest.raises(PermissionError):
        retry_atomic_json(writer, tmp_path / 'checkpoint.json', {}, tmp_path)
    assert len(calls) == 1


def test_retry_is_bounded_and_propagates_a_persistent_denial(tmp_path):
    calls = []
    def writer(*args):
        calls.append(1)
        raise denied()
    with pytest.raises(PermissionError):
        retry_atomic_json(writer, tmp_path / 'checkpoint.json', {}, tmp_path,
                          max_attempts=3, sleep=lambda _: None)
    assert len(calls) == 3


def test_entrypoint_preserves_generator_zero_argument_cli_and_restores_patch(tmp_path, monkeypatch):
    import sys
    import full_flights_run as wrapper
    import full_flights_generate as generator
    source = tmp_path / 'code/full_flights_generate.py'
    source.parent.mkdir()
    source.write_text('sealed test source')
    monkeypatch.setattr(wrapper, 'ROOT', tmp_path)
    monkeypatch.setattr(wrapper, 'FULL', tmp_path / 'output/full')
    monkeypatch.setattr(wrapper, 'GENERATOR_SHA256', wrapper.file_sha256(source))
    argv_before, function_before = sys.argv, generator.atomic_json
    def main_without_arguments():
        assert sys.argv == [str(source), 'generate', '--max-batches', '1']
        return 0
    monkeypatch.setattr(generator, 'main', main_without_arguments)
    assert wrapper.main(['generate', '--max-batches', '1']) == 0
    assert sys.argv is argv_before and generator.atomic_json is function_before
