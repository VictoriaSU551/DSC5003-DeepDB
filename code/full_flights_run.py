"""Run the frozen Flights generator with bounded Windows checkpoint I/O retry.

This changes only retries of atomic JSON writes after WinError5/32. The pinned
statistical generator, sample, aggregates and scientific checkpoint binding are
unchanged. Each invocation records this separate I/O adapter's source seal.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from full_common import ROOT, FULL, atomic_json, file_sha256

GENERATOR_SHA256 = '4aeb0f556f5b7e9f31d4785968b2519467a6e1646aeec7ac0ca5fcf9e4d961c4'


def retry_atomic_json(writer, path, value, scope, max_attempts=12,
                      sleep=time.sleep, event_sink=None):
    path, scope = Path(path).resolve(), Path(scope).resolve()
    if scope not in path.parents or path.suffix != '.json':
        raise ValueError('atomic retry path outside its JSON output scope')
    for attempt in range(max_attempts):
        try:
            return writer(path, value)
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32) or attempt + 1 == max_attempts:
                raise
            delay = min(.05 * 2 ** attempt, 1.)
            if event_sink:
                event_sink(dict(attempt=attempt + 1, delay_seconds=delay,
                                winerror=error.winerror, path=path.relative_to(scope).as_posix()))
            sleep(delay)


def main(argv=None):
    import full_flights_generate as generator
    source = ROOT / 'code/full_flights_generate.py'
    if file_sha256(source) != GENERATOR_SHA256:
        raise ValueError('frozen generator source differs; review I/O adapter compatibility')
    scope = FULL / 'flights'
    scope.mkdir(parents=True, exist_ok=True)
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    manifest_path = scope / 'io_adapters' / (identifier + '.json')
    manifest = dict(status='RUNNING', started_at_utc=identifier,
                    adapter_sha256=file_sha256(__file__), generator_sha256=GENERATOR_SHA256,
                    args=list(sys.argv[1:] if argv is None else argv),
                    adaptation='Bounded retry of atomic JSON writes on WinError5/32 only',
                    scientific_binding_modified=False, retry_events=[])
    retry_atomic_json(atomic_json, manifest_path, manifest, scope)
    original = generator.atomic_json
    original_argv = sys.argv
    sys.argv = [str(source)] + manifest['args']
    generator.atomic_json = lambda path, value: retry_atomic_json(
        original, path, value, scope, event_sink=manifest['retry_events'].append)
    try:
        result = generator.main()
        manifest['status'] = 'COMPLETED_INVOCATION'
        return result
    except BaseException as error:
        manifest.update(status='FAILED_INVOCATION', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        generator.atomic_json = original
        sys.argv = original_argv
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        retry_atomic_json(atomic_json, manifest_path, manifest, scope)


if __name__ == '__main__':
    raise SystemExit(main())
