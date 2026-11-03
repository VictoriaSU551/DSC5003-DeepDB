"""Posthoc native Windows context above frozen LOCAL 1M model/replay verifiers.

The legacy default platform probe can launch cmd/ver. This explicitly identified
outer adapter independently checks native Windows and registry, then calls the
unchanged verifier with Python operations forbidden. It is not an OS sandbox.
"""
import argparse
import builtins
from contextlib import contextmanager
import importlib
import io
import json
import os
from pathlib import Path
import pickle
import socket
import subprocess
import sys
sys.dont_write_bytecode=True
from full_ssb_replay import read, digest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/full/ssb/local_readonly_audits'
SOURCE='output/full/results/ssb_local_sf500_source.json'
SOURCE_SHA='75fef537963dcbc183a720f2abc1b47b6972550822ba4591dec8f8336183e712'
PINS={
    'code/full_ssb_local_source.py':'699f85ec4d24c326a7b491cd4cbf9c5746a98e7947d5b79db60200d08c0e3ca3',
    'code/full_ssb_local_model.py':'0b736cb30e7f1e93c66d2ac632c9b8a0ac0023595440c46b8d9215962184bced',
    'code/full_ssb_local_model_run.py':'fd676fb41780ae96074a08f2478a7cef9820b7c55a65717b9b8e28ea9545dee3',
    'code/full_ssb_local_replay.py':'9c2211af6b6385944010e079eef2fbc1f1dae381ccd39590f4acef9479c98aac',
    'code/full_windows_fingerprint.py':'a9e9034efad01e258c521934aea43f0f405ff78c42caffb7841a73fd03d96784'}


@contextmanager
def no_operations(attempts):
    saved=[]
    def forbidden(*args,**kwargs):
        attempts.append('forbidden Python operation')
        raise RuntimeError('forbidden operation during LOCAL read-only audit')
    def patch(obj,name,replacement=forbidden):
        if hasattr(obj,name):
            saved.append((obj,name,getattr(obj,name)));setattr(obj,name,replacement)
    original_import=builtins.__import__
    def checked_import(name,*args,**kwargs):
        if name.split('.')[0] in ('sqlite3','psycopg2'):forbidden()
        return original_import(name,*args,**kwargs)
    def reader(original):
        def checked(file,mode='r',*args,**kwargs):
            if any(c in mode for c in 'wax+'):forbidden()
            return original(file,mode,*args,**kwargs)
        return checked
    original_os_open=os.open
    def checked_os_open(path,flags,*args,**kwargs):
        if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):forbidden()
        return original_os_open(path,flags,*args,**kwargs)
    try:
        for name in ('run','Popen','call','check_call','check_output'):patch(subprocess,name)
        for name in dir(os):
            if (name in ('system','popen','startfile','remove','unlink','rename','replace','mkdir','makedirs','rmdir')
                    or name.startswith(('spawn','exec'))):patch(os,name)
        for name in ('create_connection','socket'):patch(socket,name)
        for name in ('load','loads'):patch(pickle,name)
        patch(builtins,'open',reader(builtins.open));patch(io,'open',reader(io.open))
        patch(os,'open',checked_os_open);patch(builtins,'__import__',checked_import)
        yield
    finally:
        for obj,name,original in reversed(saved):setattr(obj,name,original)


def inventory(paths):
    return {str(p.resolve()):(p.stat().st_size,p.stat().st_mtime_ns)
            for p in sorted(set(map(Path,paths)),key=str)}


def descriptor_paths(value):
    if isinstance(value,dict):
        if set(('path','bytes','sha256'))<=set(value):
            path=(ROOT/value['path']).resolve()
            if ROOT.resolve() not in path.parents:
                # The sealed source includes precisely these two direct imports.
                # Reuse the unchanged whitelist and physical descriptor checker.
                from full_ssb_native_model import artifact_record
                if value!=artifact_record(path):
                    raise ValueError('External direct Windows import descriptor differs')
            yield path
        for child in value.values():yield from descriptor_paths(child)
    elif isinstance(value,list):
        for child in value:yield from descriptor_paths(child)


def audit(kind):
    result_path=ROOT/'output/full/results/ssb_local_sf500_model_aqp_ci.json'
    if kind not in ('formal','reverse') or not result_path.is_file():
        raise ValueError('Completed LOCAL 1M publication required')
    source=read(ROOT/SOURCE);report=read(result_path)
    if digest(ROOT/SOURCE)!=SOURCE_SHA or any(digest(ROOT/p)!=sha for p,sha in PINS.items()):
        raise ValueError('Frozen LOCAL providers or native Windows helper changed')
    model=importlib.import_module('full_ssb_local_model')
    # Imports precede the forbidden-operation interval; scientific calls do not.
    importlib.import_module('full_ssb_guard')
    for name in ('spn','sqlparse'):importlib.import_module(name)
    if kind=='formal': verifier=model.verify_local_formal
    else: verifier=importlib.import_module('full_ssb_local_replay').verify
    paths=set(descriptor_paths(source))|set(descriptor_paths(report))|{result_path,ROOT/SOURCE}
    run=Path(report['directory']).resolve()
    if (ROOT/'output/full/ssb/local_sf500_models/runs').resolve() not in run.parents:
        raise ValueError('LOCAL formal namespace differs')
    paths.update(p for p in run.rglob('*') if p.is_file())
    if kind=='reverse':
        home=ROOT/'output/full/ssb/local_sf500_replay'
        if not (home/'verification.json').is_file():raise ValueError('Completed reverse replay required')
        paths.update(p for p in home.rglob('*') if p.is_file())
    before=inventory(paths);attempts=[]
    from full_windows_fingerprint import verified_platform
    with no_operations(attempts):
        with verified_platform(source['dependencies']['platform'],'AMD64') as proof:
            accepted=verifier()
    if attempts or before!=inventory(paths):raise ValueError('Read-only operations or physical metadata changed')
    if (accepted['author_reproduction_complete'] is not False
            or accepted['full_paper_reproduction_complete'] is not False
            or accepted['author_different_groups']!=1713):raise ValueError('Author mismatch scope changed')
    return dict(status='PASS_POSTHOC_NATIVE_WINDOWS_LOCAL_READONLY_AUDIT',kind=kind,
        accepted_status=accepted['status'],scope='LOCAL_SSB_SF500',author_different_groups=1713,
        author_reproduction_complete=False,full_paper_reproduction_complete=False,
        current_posthoc_adapter=True,bare_legacy_default_is_process_free_claimed=False,
        native_platform=proof,audit_source_sha256=digest(__file__),frozen_sources=PINS,
        verified_files_metadata_unchanged=len(paths),forbidden_attempts=attempts,
        accepted_report_sha256=digest(result_path if kind=='formal' else home/'verification.json'),
        new_training_calls=0,new_inference_calls=0,new_processes_in_guard=0,
        limitations='Python operation interception and before/after size+mtime checks; not an OS-level access trace.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['formal','reverse']);parser.add_argument('--output',type=Path)
    args=parser.parse_args();path=args.output.resolve() if args.output else None
    if path is not None and (OUT.resolve() not in path.parents or path.exists()):
        raise ValueError('New output inside separate local_readonly_audits required')
    result=audit(args.kind);text=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if path is None:print(text,end='')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)


if __name__=='__main__':main()
