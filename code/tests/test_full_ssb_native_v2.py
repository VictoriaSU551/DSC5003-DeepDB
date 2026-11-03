"""Corrected generator gates never reinterpret the original failed population."""
import hashlib
import importlib
import io
from pathlib import Path
import tarfile

import pytest

ROOT=Path(__file__).resolve().parents[2]


def test_priority_patch_requires_exact_source_and_changes_only_two_ssbm_arrays():
    module=importlib.import_module('full_ssb_native_v2')
    original=(ROOT/'code/vendor/ssb_dbgen/dsstypes.h').read_bytes()
    corrected=module.compatibility_header(original)
    needle=b'char            opriority[MAXAGG_LEN + 1];'
    assert corrected==original.replace(needle,b'char            opriority[16];',2)
    assert (ROOT/'code/vendor/ssb_dbgen/dsstypes.h').read_bytes()==original
    assert hashlib.sha256(original).hexdigest()=='ecc57e3e2854e21c339e6ee94d2a2fdce307ce2c7472cd87c9ad7a4ec644d4bd'


def test_priority_patch_rejects_even_one_changed_original_byte():
    module=importlib.import_module('full_ssb_native_v2')
    original=(ROOT/'code/vendor/ssb_dbgen/dsstypes.h').read_bytes()
    with pytest.raises(ValueError,match='source'):
        module.compatibility_header(original+b'\n')


def test_exact_shared_date_prefix_explains_all_92_extra_rows():
    module=importlib.import_module('full_ssb_native_v2')
    assert module.date_prefix_delta(750000000,2556)=={'head_rows':10161,'tail_rows':10253,'difference':92}


@pytest.mark.parametrize('name',['../escape','/absolute','usr/../../escape','C:/escape'])
def test_package_extraction_rejects_paths_outside_local_runtime(tmp_path,name):
    module=importlib.import_module('full_ssb_native_v2')
    with pytest.raises(ValueError,match='path'):
        module.package_target(tmp_path,name)
    assert not list(tmp_path.iterdir())


def test_cygwin_usr_bin_and_usr_lib_are_local_default_aliases(tmp_path):
    module=importlib.import_module('full_ssb_native_v2')
    assert module.package_target(tmp_path,'usr/bin/gcc.exe')==tmp_path/'bin/gcc.exe'
    assert module.package_target(tmp_path,'usr/lib/libc.a')==tmp_path/'lib/libc.a'
    assert module.package_target(tmp_path,'usr/include/stdio.h')==tmp_path/'usr/include/stdio.h'


def test_native_corrected_header_preserves_quantity_after_full_priority_copy():
    module=importlib.import_module('full_ssb_native_v2')
    result=module.compatibility_build()
    assert result['layout']['sizeof_long']==4
    assert result['layout']['priority_capacity']==16
    assert result['layout']['quantity_after_copy']==37


def test_native_corrected_stock_tiny_keeps_quantity_rng_bounds():
    module=importlib.import_module('full_ssb_native_v2')
    result=module.corrected_tiny_stock()
    assert result['rows']==6005
    assert result['zero_quantities']==0
    assert result['min_quantity']==1 and result['max_quantity']==50
    assert result['all_integer_price_formulas_match'] is True


def test_compatibility_printer_changes_only_legacy_priority_serialization():
    module=importlib.import_module('full_ssb_native_v2');original=(ROOT/'code/vendor/ssb_dbgen/print.c').read_bytes()
    corrected=module.compatibility_printer(original)
    assert corrected==original.replace(b'PR_STR(fp_l, o->lineorders[i].opriority, O_OPRIO_LEN);',
        b'fprintf(fp_l, "%.*s%c", MAXAGG_LEN+1, o->lineorders[i].opriority, SEPARATOR);',1)
    with pytest.raises(ValueError,match='source'):module.compatibility_printer(original+b'\n')


def test_rng_usage_guard_preserves_unifint_call_and_does_not_reassign_invalid_stream():
    module=importlib.import_module('full_ssb_native_v2');original=(ROOT/'code/vendor/ssb_dbgen/rnd.c').read_bytes()
    corrected=module.compatibility_rng_usage(original)
    assert corrected==original.replace(b'Seed[stream].usage += 1;',
        b'if (stream >= 0 && stream <= MAX_STREAM) Seed[stream].usage += 1;',1)
    with pytest.raises(ValueError,match='source'):module.compatibility_rng_usage(original+b'\n')


def test_llp64_range_conversion_happens_before_integer_overflow_without_touching_seed_update():
    module=importlib.import_module('full_ssb_native_v2');original=(ROOT/'code/vendor/ssb_dbgen/rnd.c').read_bytes()
    corrected=module.compatibility_rng_range(original)
    assert corrected==original.replace(b'dRange = DOUBLE_CAST (nHigh - nLow + 1);',
        b'dRange = DOUBLE_CAST(nHigh) - DOUBLE_CAST(nLow) + 1.0;',1)
    with pytest.raises(ValueError,match='source'):module.compatibility_rng_range(original+b'\n')


def test_safe_stock_printer_preserves_observed_lp64_legacy_priority_text():
    module=importlib.import_module('full_ssb_native_v2');result=module.corrected_tiny_stock()
    values={r.split('|')[6] for r in (Path(result['directory'])/'lineorder.tbl').read_text().splitlines()}
    assert '4-NOT SPECI' in values and '4-NOT SPECIFIED' not in values


def test_cygwin_dependency_closure_rejects_missing_package_and_pins_transitive_set():
    module=importlib.import_module('full_ssb_native_v2')
    metadata={'gcc':{'depends2':'runtime ( >= 1 ), headers','install':'gcc.tar 7 abc'},
              'runtime':{'depends2':'_windows ( >= 6.3 )','install':'runtime.tar 4 def'},
              'headers':{'install':'headers.tar 2 ghi'}}
    assert set(module.package_closure(metadata,['gcc']))=={'gcc','runtime','headers'}
    metadata.pop('runtime')
    with pytest.raises(ValueError,match='Missing'):module.package_closure(metadata,['gcc'])


def test_tar_stream_copies_regular_bytes_without_running_postinstall(tmp_path):
    module=importlib.import_module('full_ssb_native_v2');stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name,data in [('usr/bin/probe.exe',b'fixed-binary'),('etc/postinstall/evil.sh',b'must not run'),
                          ('usr/share/man/man1/:.1.gz',b'Unix documentation name is deliberately skipped')]:
            info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
    stream.seek(0);result=module.extract_tar_stream(stream,tmp_path)
    assert (tmp_path/'bin/probe.exe').read_bytes()==b'fixed-binary'
    assert not (tmp_path/'etc').exists()
    assert result['regular_files']==1 and result['bytes']==12


def test_official_project_local_lp64_oracle_preserves_original_header_quantity():
    module=importlib.import_module('full_ssb_native_v2')
    result=module.setup_cygwin()
    assert result['layout']['sizeof_long']==8 and result['layout']['sizeof_void_pointer']==8
    assert result['layout']['priority_capacity']==11
    assert result['layout']['quantity_after_copy']==37


def test_actual_lp64_stock_matches_corrected_windows_all_tiny_fact_fields_and_dimensions():
    module=importlib.import_module('full_ssb_native_v2')
    result=module.lp64_tiny_gate()
    assert result['lineorder_all17_fields_equal'] is True
    assert result['unprimed_rows']==6005
    assert set(result['dimension_equal'])=={'customer','supplier','part','date'}
    assert all(result['dimension_equal'].values())


def test_cygwin_argument_converts_stored_windows_path_strings_without_losing_spaces():
    module=importlib.import_module('full_ssb_native_v2')
    assert module.cygwin_argument('C:\\owned project\\probe.exe')=='/cygdrive/c/owned project/probe.exe'


def test_cygwin_shell_does_not_append_windows_carriage_return_to_last_argument(tmp_path):
    module=importlib.import_module('full_ssb_native_v2');toolchain=module.setup_cygwin()
    result=module.cygwin_run([Path(toolchain['directory'])/'bin/bash.exe','--noprofile','--norc',
                             '-c','printf %s "$1"','_','sentinel'],tmp_path,tmp_path/'process.json',toolchain)
    assert result.stdout=='sentinel'


def test_direct_callback_tiny_matches_all17_fields_and_13_independent_sql_sums():
    module=importlib.import_module('full_ssb_native_v2');result=module.callback_tiny_gate()
    assert result['rows']==6005
    assert result['all17_fields_equal'] is True
    assert result['independent_sql_queries']==13
    assert result['all13_exact_integer_aggregates_equal'] is True


def test_high_order_skip_matches_lp64_modular_reference_in_all_fields_and_effective_seeds():
    module=importlib.import_module('full_ssb_native_v2');result=module.high_order_gate()
    assert result['order_starts']==[1,306000001,613000001,749999937]
    assert result['all17_fields_equal'] and result['all_effective_seeds_equal']
    assert result['unused_differences_classified'] is True


def test_official_toolchain_lock_is_fixed_and_does_not_need_rolling_setup_metadata():
    module=importlib.import_module('full_ssb_native_v2');lock=module.toolchain_lock()
    assert len(lock['packages'])==26
    assert lock['packages']['gcc-core']['version']=='14.4.0-1'
    assert sum(int(p['install'].split()[1]) for p in lock['packages'].values())==66164325


@pytest.mark.parametrize('state',['RUNNING','TAINTED'])
def test_strict_receipt_never_reuses_nonpass_lifecycle(tmp_path,state):
    module=importlib.import_module('full_ssb_native_v2');(tmp_path/'native.exe').write_bytes(b'fixed')
    module.atomic(tmp_path/'receipt.json',{'status':'PASS','binding':{},'files_sha256':{'native.exe':module.digest(tmp_path/'native.exe')}})
    module.atomic(tmp_path/'receipt_seal.json',{'sha256':module.digest(tmp_path/'receipt.json')})
    module.atomic(tmp_path/'lifecycle.json',{'status':state,'receipt_sha256':module.digest(tmp_path/'receipt.json')})
    with pytest.raises(ValueError,match='lifecycle'):module.strict_receipt(tmp_path,{}, {'native.exe'})


def test_strict_receipt_refuses_empty_missing_extra_inventory_even_if_resealed(tmp_path):
    module=importlib.import_module('full_ssb_native_v2');(tmp_path/'native.exe').write_bytes(b'fixed')
    for files in [{},{'other.exe':'fake'},{'native.exe':module.digest(tmp_path/'native.exe'),'extra':'fake'}]:
        module.atomic(tmp_path/'receipt.json',{'status':'PASS','binding':{},'files_sha256':files})
        module.atomic(tmp_path/'receipt_seal.json',{'sha256':module.digest(tmp_path/'receipt.json')})
        module.atomic(tmp_path/'lifecycle.json',{'status':'PASS','receipt_sha256':module.digest(tmp_path/'receipt.json')})
        with pytest.raises(ValueError,match='inventory'):module.strict_receipt(tmp_path,{}, {'native.exe'})


@pytest.mark.parametrize('scale',[1,2])
def test_corrected_scale_full_stock_callback_and_sqlite_gate(scale):
    module=importlib.import_module('full_ssb_native_v2');result=module.verified_sf1_gate() if scale==1 else module.corrected_scale_gate(scale)
    assert result['scale']==scale and result['rows']>scale*5900000
    assert result['all17_fields_equal'] and result['all_dimensions_equal']
    assert result['all13_exact_integer_aggregates_equal']


def test_native_integer_sampling_refuses_equal_cutoff_and_handles_zero_and_all():
    module=importlib.import_module('full_ssb_native_v2');result=module.native_sampling_gate()
    assert result['boundary_cases']==8 and result['all_cases_match_python_integer_oracle']


def test_high_index_actual_callback_view_and_formatter_match_lp64_all17_fields():
    module=importlib.import_module('full_ssb_native_v2');result=module.high_callback_gate()
    assert result['actual_callback_formatter_all17_fields_equal']
    assert result['maximum_observed_orderkey']>2**31


def test_atomic_checkpoint_retries_only_bounded_windows_share_conflicts(tmp_path,monkeypatch):
    module=importlib.import_module('full_ssb_native_v2');replace=module.os.replace;calls=[]
    def transient(source,target):
        calls.append(1)
        if len(calls)<3:
            error=PermissionError('Read-close sharing window');error.winerror=32;raise error
        return replace(source,target)
    monkeypatch.setattr(module.os,'replace',transient);monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    module.atomic(tmp_path/'checkpoint.json',{'verified':True})
    assert len(calls)==3 and (tmp_path/'checkpoint.json').is_file()
