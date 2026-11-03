"""Read-only acceptance of the recorded ROOT-relative 10M CI invocation."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = Path('code/full_ssb_local_ci_group_replay.py')
PROVIDER_SHA = '4b73cf6bed9bb001ec1bf289fadb6950bdd4f0c644e1837406eaef402b0a827c'
HELPER = Path('code/full_ssb_scoped_replay.py')
HELPER_SHA = 'f2514ac1e35cfea892096a7c9c338ab7c3aad6d905b4b35bfe6025f9ebca200c'


def verify():
    """Keep the complete frozen verifier; adapt only its known entry spelling."""
    if Path.cwd().resolve() != ROOT:
        raise ValueError('10M CI acceptance requires the project ROOT working directory')

    import full_ssb_local_ci_group_replay as provider
    import full_ssb_scoped_replay as helper

    for module, relative, expected_sha in ((provider, ENTRY, PROVIDER_SHA),
                                           (helper, HELPER, HELPER_SHA)):
        expected = ROOT/relative
        if (expected.resolve() != expected
                or Path(getattr(module, '__file__', '')).resolve() != expected):
            raise ValueError('10M CI acceptance provider/helper physical identity differs')
        if hashlib.sha256(expected.read_bytes()).hexdigest() != expected_sha:
            raise ValueError('10M CI acceptance frozen provider/helper source changed')

    replay = provider.engine()
    if Path(replay.ENTRY).resolve() != ROOT/ENTRY:
        raise ValueError('10M CI acceptance engine entry physical identity differs')
    # The successful worker receipt used this fixed relative argv[2]. Never
    # select an entry or any other command argument from the untrusted receipt.
    replay.ENTRY = ENTRY
    return replay.verify()
