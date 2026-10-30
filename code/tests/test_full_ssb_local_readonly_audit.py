"""A posthoc verifier must fail closed before an operation or artifact write."""
import builtins
import io
import os
from pathlib import Path
import subprocess
import pytest
import full_ssb_local_readonly_audit as audit


@pytest.mark.parametrize('operation',['process','os_launch','write','os_write','database_import'])
def test_operation_guard_blocks_side_effects_and_restores_objects(tmp_path,operation):
    file=tmp_path/'existing';file.write_bytes(b'original')
    saved=(builtins.open,io.open,os.open,subprocess.Popen,subprocess.check_output)
    attempts=[]
    with pytest.raises(RuntimeError,match='forbidden'):
        with audit.no_operations(attempts):
            assert file.read_bytes()==b'original'
            if operation=='process':subprocess.check_output(['cmd','/c','ver'])
            if operation=='os_launch':os.system('ver')
            if operation=='write':file.write_text('overwritten')
            if operation=='os_write':os.open(str(file),os.O_WRONLY)
            if operation=='database_import':__import__('sqlite3')
    assert len(attempts)==1
    assert (builtins.open,io.open,os.open,subprocess.Popen,subprocess.check_output)==saved
    assert file.read_bytes()==b'original'


def test_inventory_rejects_missing_inputs_and_detects_metadata_changes(tmp_path):
    file=tmp_path/'one';file.write_bytes(b'x')
    before=audit.inventory([file])
    file.write_bytes(b'changed')
    assert before!=audit.inventory([file])
    with pytest.raises(FileNotFoundError):audit.inventory([tmp_path/'missing'])


def test_only_two_actual_sealed_direct_windows_imports_may_be_external():
    from full_ssb_native_model import artifact_record
    native=Path('C:/Windows/System32/kernel32.dll')
    record=artifact_record(native)
    assert list(audit.descriptor_paths([record]))==[native.resolve()]
    with pytest.raises(ValueError):
        list(audit.descriptor_paths(dict(path='C:/Windows/System32/user32.dll',
            bytes=1,sha256='0'*64,external_scope='windows_direct_native_import')))
    record['sha256']='0'*64
    with pytest.raises(ValueError):list(audit.descriptor_paths(record))
