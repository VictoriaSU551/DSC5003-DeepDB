"""Configurable required-set validation capsule, without copying a model driver."""
import sys
sys.dont_write_bytecode=True
import ast
import hashlib
from pathlib import Path
import full_ssb_local_model as frozen

PIN='0b736cb30e7f1e93c66d2ac632c9b8a0ac0023595440c46b8d9215962184bced'
require=frozen.require
REPLACEMENTS={
    "prepared=run/'prepared';":"prepared=Path(r['prepared_directory']);",
    "(2556 if t=='dwdate' else 1000000)":"expected_training_rows[t]",
    "moments=run/'sample_moments_native';":"moments=Path(r['moments_directory']);",
    "helper=root/OUTPUT/'runtime/native'":"helper=Path(r['moments_helper_directory'])",
    "checkpoint=run/'core_truth_checkpoint.json';":"checkpoint=Path(r['truth_projection_path']);",
}


def configured_source():
    path=Path(frozen.__file__);require(frozen.digest(path)==PIN,'frozen required-set validation source changed')
    raw=path.read_text(encoding='utf-8');nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='stage_artifacts']
    require(len(nodes)==1,'exact frozen stage validation function required');original=ast.get_source_segment(raw,nodes[0])+'\n';configured=original
    for before,after in REPLACEMENTS.items():
        require(configured.count(before)==1,'required-set configuration mapping changed');configured=configured.replace(before,after)
    return original,configured


def binding(configuration):
    a,b=configured_source()
    return dict(frozen_validation_module_sha256=PIN,source_sha256=hashlib.sha256(a.encode()).hexdigest(),configured_source_sha256=hashlib.sha256(b.encode()).hexdigest(),
        adapter_sha256=frozen.digest(__file__),configuration=configuration,source_mappings=REPLACEMENTS)


def validate_scope(report,configuration):
    require(all(report.get(k)==configuration[k] for k in ('evaluation_variant','group_order_adapter_sha256')),'canonical evaluation variant/adapter differs')
    require(report.get('scope')==configuration['scope'] and report.get('status') in configuration['statuses']
        and report.get('author_different_groups')==1713 and report.get('author_reproduction_complete') is False
        and report.get('full_paper_reproduction_complete') is False and report.get('author_population_row_count_and_13_truths_match') is False
        and report.get('author_full_row_byte_identity_proven') is False,'distinct local CI scope and all author-false boundaries required')
    old=report['original_mismatch'];inputs=report['inputs']
    require(old['path']==frozen.source.NATIVE_REPORT and old['sha256']==frozen.source.NATIVE_REPORT_SHA
        and inputs['status']==frozen.source.STATUS and inputs['scope']==frozen.source.SCOPE and inputs['different_author_groups']==1713,'local source/mismatch lineage differs')


def validate(report,configuration,root=frozen.ROOT):
    require(set(configuration)=={'scope','output','parameters','expected_rows','statuses','evaluation_variant','group_order_adapter_sha256'}
        and set(configuration['expected_rows'])==set(frozen.base.TABLES),'complete validation configuration required')
    namespace=dict(vars(frozen));namespace.update(OUTPUT=configuration['output'],MODEL=configuration['parameters'],expected_training_rows=configuration['expected_rows'],
        validate_scope=lambda r:validate_scope(r,configuration))
    exec(compile(configured_source()[1],'<sealed-configurable-local-stage-validation>','exec'),namespace)
    return namespace['stage_artifacts'](report,root)
