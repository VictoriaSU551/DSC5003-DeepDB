"""Run the sealed SSB paper entry with bounded Windows JSON sharing retries."""
from datetime import datetime, timezone
from pathlib import Path
import sys

from full_common import ROOT, FULL, atomic_json, file_sha256
from full_flights_run import retry_atomic_json

RUNNER_SHA256 = '7bbf4669455bdc0313883ffaa8d22b8d38eaaf6f55e8048c9107de141d71a4fc'


def main():
    import full_ssb_paper as paper
    import full_ssb_generate as sf1
    if file_sha256(ROOT / 'code/full_ssb_paper.py') != RUNNER_SHA256:
        raise ValueError('reviewed SSB runner source differs')
    scopes = [FULL / 'ssb', ROOT / 'data/ssb', FULL / 'results']
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    manifest_path = FULL / 'ssb/io_adapters' / (identifier + '.json')
    manifest = dict(status='RUNNING', args=sys.argv[1:], runner_sha256=RUNNER_SHA256,
                    adapter_sha256=file_sha256(__file__),
                    io_helper_sha256=file_sha256(ROOT / 'code/full_flights_run.py'),
                    adaptation='Bounded atomic JSON retries for WinError5/32 only',
                    scientific_binding_modified=False, retry_events=[])
    original_paper, original_sf1 = paper.atomic, sf1.atomic
    def resilient(writer, path, value):
        path = Path(path).resolve()
        scope = next((s for s in scopes if s.resolve() in path.parents), None)
        if scope is None:
            raise ValueError('SSB JSON write outside its project output scope')
        return retry_atomic_json(writer, path, value, scope,
                                 event_sink=manifest['retry_events'].append)
    resilient(atomic_json, manifest_path, manifest)
    paper.atomic = lambda path, value: resilient(original_paper, path, value)
    sf1.atomic = lambda path, value: resilient(original_sf1, path, value)
    try:
        result = paper.main()
        manifest.update(status='COMPLETED_INVOCATION', returncode=result)
        return result
    except BaseException as error:
        manifest.update(status='FAILED_INVOCATION', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        paper.atomic, sf1.atomic = original_paper, original_sf1
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        resilient(atomic_json, manifest_path, manifest)


if __name__ == '__main__':
    raise SystemExit(main())
