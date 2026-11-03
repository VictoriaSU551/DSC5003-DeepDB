"""Durable publication and complete dependency guards for frozen SSB routines.

Core seals are provisional. Only this layer's PASS namespace may be consumed.
RUNNING leftovers and all exceptions permanently taint that namespace; recovery
requires an independently reviewed new namespace, never restoring raw files and
automatically accepting the old core seal.
"""
from contextlib import contextmanager
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import pickle
import platform

import numpy as np
import pandas as pd
import full_ssb_model as core

ADOPTED_TINY_DEPENDENCIES_SHA256='9bc2cfeed87f68563038436e480aa769f258712d0cb45d7ce7d140a0756f54de'
TINY_MODEL_SHA256='cfadb3ecb8100544ae91d0f14d03d559982ff48489d7de590eb9e051943b56f6'


def value_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def dependencies():
    import spn,sqlparse
    sources=[]
    for folder in ('aqp_spn','rspn','ensemble_creation','ensemble_compilation','data_preparation','schemas'):
        sources.extend((core.ROOT/'code'/folder).rglob('*.py'))
    sources.extend(core.ROOT/'code'/name for name in ('evaluation/utils.py','full_ssb_model.py','full_common.py',
                                                       'full_factor_cache.py','full_flights_model.py'))
    versions={'python':platform.python_version()}
    for name in ('numpy','pandas','scipy','scikit-learn','joblib','tables','spflow','sqlparse','networkx'):
        versions[name]=importlib.metadata.version(name)
    def package_files(module):
        root=Path(module.__file__).resolve().parent
        return {p.relative_to(root).as_posix():core.digest(p) for p in sorted(root.rglob('*.py'))}
    return {'sources':{p.relative_to(core.ROOT).as_posix():core.digest(p) for p in sorted(set(sources))},
            'spflow_sources':package_files(spn),'sqlparse_sources':package_files(sqlparse),'versions':versions,
            'sql_sha256':core.digest(core.SQL_PATH)}


def reject_tainted(home):
    home=Path(home);path=home/'lifecycle.json'
    if path.exists():
        state=json.loads(path.read_text())
        if state.get('status') not in ('PASS',):
            state.update(status='TAINTED',reason='Previous exception or interrupted RUNNING namespace; automatic recovery forbidden')
            core.atomic_json(path,state)
            raise ValueError('TAINTED namespace cannot automatically resume: '+str(home))


def transaction(home,kind,binding,producer,validator):
    home=Path(home);home.mkdir(parents=True,exist_ok=True);reject_tainted(home)
    state_path=home/'lifecycle.json';receipt_path=home/'receipt.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        if state.get('binding')!=binding:raise ValueError('Namespace dependency binding changed; use a new namespace')
        try:
            if not receipt_path.exists() or core.digest(receipt_path)!=state['receipt_sha256']:
                raise ValueError('Outer PASS receipt checksum changed')
            receipt=json.loads(receipt_path.read_text())
            if receipt.get('status')!='PASS' or receipt.get('binding')!=binding:raise ValueError('Outer PASS receipt binding changed')
            validator(receipt['result'])
            return receipt['result']
        except BaseException as error:
            core.atomic_json(state_path,{'status':'TAINTED','kind':kind,'binding':binding,'reason':repr(error)})
            raise
    core.atomic_json(state_path,{'status':'RUNNING','kind':kind,'binding':binding})
    try:
        result=producer();validator(result)
        core.atomic_json(receipt_path,{'status':'PASS','kind':kind,'binding':binding,'result':result})
        core.atomic_json(state_path,{'status':'PASS','kind':kind,'binding':binding,'receipt_sha256':core.digest(receipt_path)})
        return result
    except BaseException as error:
        core.atomic_json(state_path,{'status':'TAINTED','kind':kind,'binding':binding,'reason':repr(error)})
        raise


def home_for(directory,kind):
    directory=Path(directory)
    return directory.parent/('.'+directory.name+'_'+kind+'_guard_'+core.digest(__file__)[:16])


def replay_integer_mean(table,column,work,chunk_rows,rows):
    """Use the same contiguous int64 Series and pandas float64 reduction order."""
    path=Path(work)/(column.replace('.','_')+'_large_int64.bin')
    with path.open('wb') as stream:
        for frame in core.raw_chunks(table,chunk_rows,[column.split('.',1)[1]]):
            values=pd.to_numeric(frame[column],errors='raise')
            if values.dtype.kind not in 'iu' or values.isna().any():raise ValueError('Large integer replay dtype changed')
            stream.write(values.astype('int64').values.tobytes())
    values=np.memmap(str(path),mode='r',dtype='int64',shape=(rows,))
    return float(pd.Series(values,copy=False).mean())


@contextmanager
def large_integer_profile_route():
    """One explicit source replacement; the on-disk golden function is untouched.

    Safe integers retain its exact old path. Only its former rejection branch is
    routed through original pandas Series.mean over a bounded on-disk replay.
    The external guard binds this adapter plus the unchanged core source.
    """
    original=core.profile_table;source=inspect.getsource(original)
    needle="if state['max_abs']*rows>=2**53:raise ValueError('Integer reduction outside proven exact range')\n                state['mean']=state['int_sum']/state['nonnull']"
    replacement="if state['max_abs']*rows>=2**53:\n                    state['mean']=replay_integer_mean(table,column,work,chunk_rows,rows)\n                else:\n                    state['mean']=state['int_sum']/state['nonnull']"
    if source.count(needle)!=1:raise ValueError('Frozen integer rejection branch changed; adapter cannot be applied')
    namespace=dict(core.__dict__,replay_integer_mean=replay_integer_mean)
    exec(compile(source.replace(needle,replacement),'<SSB integer mean replay adapter>','exec'),namespace)
    core.profile_table=namespace['profile_table']
    try:yield
    finally:core.profile_table=original


def prepared_result(schema,directory):
    return {'status':'PASS','core_input_artifacts':core.model_input_artifacts(schema,directory),
            'core_seal_sha256':core.digest(Path(directory)/'seal.json')}


def require_prepared_pass(schema,directory):
    home=home_for(directory,'prepared');reject_tainted(home)
    state_path=home/'lifecycle.json';receipt_path=home/'receipt.json'
    if not state_path.exists() or not receipt_path.exists():raise ValueError('Prepared core seal requires outer PREPARED PASS')
    state=json.loads(state_path.read_text());receipt=json.loads(receipt_path.read_text())
    if (state.get('status')!='PASS' or state.get('receipt_sha256')!=core.digest(receipt_path) or
        receipt.get('status')!='PASS' or receipt.get('binding')!=state.get('binding')):
        raise ValueError('Prepared outer PASS receipt changed')
    if receipt['binding']['dependencies']!=dependencies() or receipt['binding']['guard_source_sha256']!=core.digest(__file__):
        raise ValueError('Prepared outer complete dependencies changed')
    if prepared_result(schema,directory)!=receipt['result']:raise ValueError('Prepared outer physical artifacts changed')
    return receipt['result']


def guarded_prepare(schema,directory,chunk_rows=100000,adopt_verified_tiny=False):
    directory=Path(directory);home=home_for(directory,'prepared');reject_tainted(home)
    binding={'dependencies':dependencies(),'guard_source_sha256':core.digest(__file__),
             'preparation':core.preparation_binding(schema,chunk_rows),'integer_reduction':'original pandas int64 Series.mean replay for unsafe2**53 only'}
    if adopt_verified_tiny:authorize_tiny_adoption(directory)
    if (directory/'seal.json').exists() and not (home/'lifecycle.json').exists() and not adopt_verified_tiny:
        raise ValueError('Existing core preparation seal without outer PREPARED PASS cannot be consumed')
    def produce():
        if not adopt_verified_tiny:
            with large_integer_profile_route():core.prepare_bounded(schema,directory,chunk_rows)
        return prepared_result(schema,directory)
    def validate(result):
        if binding['dependencies']!=dependencies() or prepared_result(schema,directory)!=result:
            raise ValueError('Final prepared input/artifact verification failed')
    transaction(home,'PREPARED',binding,produce,validate)
    require_prepared_pass(schema,directory)
    with (directory/'meta_data.pkl').open('rb') as stream:return pickle.load(stream)


def guarded_train(schema,prepared,cap,directory):
    directory=Path(directory);home=home_for(directory,'model');reject_tainted(home)
    require_prepared_pass(schema,prepared)
    binding={'prepared_directory':str(prepared),'prepared_outer_receipt_sha256':core.digest(home_for(prepared,'prepared')/'receipt.json'),
             'dependencies':dependencies(),'guard_source_sha256':core.digest(__file__),
             'model_stage':core.model_stage_binding(prepared,cap,1)}
    if (directory/'model.json').exists() and not (home/'lifecycle.json').exists():
        raise ValueError('Existing unguarded model namespace requires separately verified tiny adoption')
    def produce():return core.guarded_train_single_models(schema,prepared,cap,directory)
    def validate(model):
        require_prepared_pass(schema,prepared)
        if binding['dependencies']!=dependencies():raise ValueError('Model complete dependencies changed during execution')
        verify_core_model(model)
    return transaction(home,'MODEL',binding,produce,validate)


def verify_core_model(model):
    directory=Path(model['model_path']).parent;record=json.loads((directory/'model_guard.json').read_text())
    expected=set(model['files_sha256'])|{'model.json','input_guard.json'}
    expected.update(Path(name).stem+'.json' for name in model['files_sha256'] if name!=Path(model['model_path']).name)
    if (not expected or set(record['model_files_sha256'])!=expected or
        record['binding']['model_stage']!=model['binding']):raise ValueError('Model core receipt inventory/binding changed')
    for name,sha in record['model_files_sha256'].items():
        target=(directory/name).resolve()
        if target.parent!=directory.resolve() or not target.is_file() or core.digest(target)!=sha:
            raise ValueError('Model core artifact checksum changed: '+name)
    if (json.loads((directory/'model.json').read_text())!=model or
        json.loads((directory/'input_guard.json').read_text())['binding']!=record['binding']):
        raise ValueError('Model core receipt content changed')


def require_model_pass(model):
    directory=Path(model['model_path']).parent;home=home_for(directory,'model');reject_tainted(home)
    state_path=home/'lifecycle.json';receipt_path=home/'receipt.json'
    if not state_path.exists() or not receipt_path.exists():raise ValueError('Model requires outer MODEL PASS')
    state=json.loads(state_path.read_text());receipt=json.loads(receipt_path.read_text())
    if (state.get('status')!='PASS' or state.get('receipt_sha256')!=core.digest(receipt_path) or
        receipt.get('status')!='PASS' or receipt['binding']!=state['binding'] or receipt['result']!=model or
        receipt['binding']['dependencies']!=dependencies() or receipt['binding']['guard_source_sha256']!=core.digest(__file__)):
        raise ValueError('Model outer dependency/receipt mismatch')
    for name,sha in model['files_sha256'].items():
        if core.digest(directory/name)!=sha:raise ValueError('Model outer physical checksum changed')
    verify_core_model(model)
    return receipt


def query_bundle(directory,global_binding,sqls=None,names=None):
    directory=Path(directory);sqls=sqls or core.SQL_PATH.read_text().splitlines();names=names or core.QUERY_NAMES
    required={'query_%02d'%index+suffix for index in range(len(sqls)) for suffix in ('.json','.seal.json')}
    if {p.name for p in directory.glob('query_*.json')}!=required:raise ValueError('Query identity set missing/extra')
    result=[];seen=set()
    for index,(sql,name) in enumerate(zip(sqls,names)):
        path=directory/('query_%02d.json'%index);seal_path=path.with_suffix('.seal.json')
        query=json.loads(path.read_text());seal=json.loads(seal_path.read_text())
        if (query.get('query_no')!=index or query.get('query_name')!=name or query.get('sql')!=sql or
            index in seen or seal.get('binding')!=global_binding or seal.get('sha256')!=core.digest(path)):
            raise ValueError('Query identity/index/exactSQL/physical seal mismatch: '+str(index))
        seen.add(index);result.append({'query_no':index,'query_name':name,'exact_sql':sql,'global_binding':global_binding,
                                      'result_sha256':core.digest(path),'core_seal_sha256':core.digest(seal_path)})
    if len(result)!=len(sqls) or len(seen)!=len(sqls):raise ValueError('Query identities incomplete/duplicated')
    return result


def guarded_evaluate(model,truth,moments,directory):
    home=home_for(directory,'evaluation');reject_tainted(home)
    if not (home/'lifecycle.json').exists() and any(Path(directory).rglob('query_*.json')):
        raise ValueError('Existing unguarded query cache cannot be adopted; tiny requires explicit audited adoption')
    require_model_pass(model)
    binding={'dependencies':dependencies(),'guard_source_sha256':core.digest(__file__),'model_sha256':core.digest(model['model_path']),
             'truth_sha256':truth['checkpoint_sha256'],'moments_sha256':value_hash(core.normalized_moments(moments)),
             'model_outer_receipt_sha256':core.digest(home_for(Path(model['model_path']).parent,'model')/'receipt.json')}
    def produce():
        result=core.evaluate_ssb(model,truth,moments,directory)
        result['identities']=query_bundle(result['directory'],result['binding'])
        return result
    def validate(result):
        require_model_pass(model)
        if binding['dependencies']!=dependencies():raise ValueError('Complete inference/parser dependencies changed')
        if result['identities']!=query_bundle(result['directory'],result['binding']):raise ValueError('Query identity receipts changed')
        if [(q['query_no'],q['query_name'],q['sql']) for q in result['queries']]!=[(i,n,s) for i,(n,s) in enumerate(zip(core.QUERY_NAMES,core.SQL_PATH.read_text().splitlines()))]:
            raise ValueError('Evaluation summary query identity set changed')
    return transaction(home,'EVALUATION',binding,produce,validate)


def authorize_tiny_adoption(prepared):
    if value_hash(dependencies())!=ADOPTED_TINY_DEPENDENCIES_SHA256:
        raise ValueError('Verified tiny adoption dependency pin changed; independent review required, never retrain automatically')
    gate=json.loads((core.OUTPUT/'sf2_preparation_gate_latest.json').read_text())
    small=json.loads((core.OUTPUT/'sf2_small_model_gate_latest.json').read_text())
    if (Path(gate['bounded_directory']).resolve()!=Path(prepared).resolve() or gate['status']!='PASS' or
        not gate['comparison']['metadata_exact'] or not gate['comparison']['all_frame_values_and_dtypes_exact'] or
        small['sample_cap']!=10000 or not small['checkpointed_matches_original_naive_fit_and_structure_exact'] or
        core.digest(small['model_path'])!=TINY_MODEL_SHA256):
        raise ValueError('Existing independently verified tiny adoption proof does not match')
    return small


def seal_small_gate():
    """Post-hoc adoption of correct tiny bytes/identities; no train or inference."""
    schema,_,prepared=core.sf2_preparation_reuse();small=authorize_tiny_adoption(prepared)
    chunk=json.loads((prepared/'binding.json').read_text())['chunk_rows']
    guarded_prepare(schema,prepared,chunk,adopt_verified_tiny=True)
    model_dir=Path(small['model_path']).parent;model=json.loads((model_dir/'model.json').read_text())
    original=json.loads((Path(small['directory'])/'original/reference.json').read_text())
    if (len(model['training_tables'])!=5 or len(original['observations'])!=5 or
        core.digest(original['model_path'])!=original['sha256']):raise ValueError('Original tiny reference changed')
    for expected,actual in zip(original['observations'],model['training_tables']):
        if any(expected[key]!=actual[key] for key in ('table','actual_training_rows','sample_matrix_sha256','structure_sha256')):
            raise ValueError('Original naive tiny model adoption proof failed')
    binding={'prepared_directory':str(prepared),'prepared_outer_receipt_sha256':core.digest(home_for(prepared,'prepared')/'receipt.json'),
             'dependencies':dependencies(),'guard_source_sha256':core.digest(__file__),
             'model_stage':core.model_stage_binding(prepared,10000,1)}
    def validate_model(saved):
        require_prepared_pass(schema,prepared)
        if saved!=model or core.digest(saved['model_path'])!=TINY_MODEL_SHA256:raise ValueError('Tiny model bytes changed')
        verify_core_model(saved)
    transaction(home_for(model_dir,'model'),'MODEL',binding,lambda:model,validate_model)
    require_model_pass(model)
    eval_dir=Path(small['directory'])/'adopted_evaluation'
    native_dir=core.OUTPUT/'sf2_sample_moments_native';moment_seal=json.loads((native_dir/'seal.json').read_text())
    moment_binding=core.moment_source_binding(schema);moment_binding['sample_rows']=39712
    if (moment_seal['binding']!=moment_binding or core.digest(native_dir/'moments.json')!=moment_seal['sha256'] or
        core.digest(native_dir/'moments.tsv')!=moment_seal['tsv_sha256']):raise ValueError('Tiny exact moments changed')
    moments=json.loads((native_dir/'moments.json').read_text())['queries']
    truth=core.population_truth_groups(core.ROOT/'output/full/ssb/paper/sf2_gate_v2/checkpoint.json')
    eval_binding={'dependencies':dependencies(),'guard_source_sha256':core.digest(__file__),'model_sha256':TINY_MODEL_SHA256,
                  'truth_sha256':truth['checkpoint_sha256'],'moments_sha256':value_hash(core.normalized_moments(moments)),
                  'model_outer_receipt_sha256':core.digest(home_for(model_dir,'model')/'receipt.json')}
    def adopt_evaluation():
        return {'queries':small['queries'],'binding':small['evaluation_binding'],'directory':small['evaluation_directory'],
                'identities':query_bundle(small['evaluation_directory'],small['evaluation_binding'])}
    def validate_evaluation(result):
        if result['identities']!=query_bundle(result['directory'],result['binding']):raise ValueError('Tiny query identity changed')
        if len(result['queries'])!=13:raise ValueError('Tiny query summaries incomplete')
        for identity,summary in zip(result['identities'],result['queries']):
            raw=json.loads((Path(result['directory'])/('query_%02d.json'%identity['query_no'])).read_text())
            if raw!=summary:raise ValueError('Tiny query summary/raw receipt mismatch')
    transaction(home_for(eval_dir,'evaluation'),'EVALUATION',eval_binding,adopt_evaluation,validate_evaluation)
    receipts=[home_for(prepared,'prepared')/'receipt.json',home_for(model_dir,'model')/'receipt.json',
              home_for(eval_dir,'evaluation')/'receipt.json']
    report={'status':'PASS_CURRENT_COMPLETE_DEPENDENCIES','model_sha256':TINY_MODEL_SHA256,'no_preparation_training_or_inference_repeated':True,
            'dependencies_sha256':value_hash(dependencies()),'guard_source_sha256':core.digest(__file__),
            'outer_receipts_sha256':{str(p):core.digest(p) for p in receipts},'query_identities':13}
    path=core.OUTPUT/'sf2_outer_guard_verification.json';core.atomic_json(path,report)
    core.atomic_json(path.with_suffix('.seal.json'),{'sha256':core.digest(path),'guard_source_sha256':core.digest(__file__)})
    return report


def verify_small_gate():
    """Successful verification is read-only; never prepare, learn or infer."""
    path=core.OUTPUT/'sf2_outer_guard_verification.json';seal=json.loads(path.with_suffix('.seal.json').read_text())
    report=json.loads(path.read_text())
    if (seal.get('sha256')!=core.digest(path) or seal.get('guard_source_sha256')!=core.digest(__file__) or
        report.get('guard_source_sha256')!=core.digest(__file__) or report.get('dependencies_sha256')!=value_hash(dependencies()) or
        report.get('status')!='PASS_CURRENT_COMPLETE_DEPENDENCIES' or report.get('query_identities')!=13):
        raise ValueError('Tiny outer final source/dependency/self seal changed')
    schema,_,prepared=core.sf2_preparation_reuse();small=authorize_tiny_adoption(prepared)
    require_prepared_pass(schema,prepared)
    model=json.loads((Path(small['model_path']).parent/'model.json').read_text());require_model_pass(model)
    required=[home_for(prepared,'prepared')/'receipt.json',home_for(Path(small['model_path']).parent,'model')/'receipt.json',
              home_for(Path(small['directory'])/'adopted_evaluation','evaluation')/'receipt.json']
    if set(report['outer_receipts_sha256'])!={str(p) for p in required}:raise ValueError('Tiny exact outer stage receipt set changed')
    for receipt in required:
        reject_tainted(receipt.parent)
        state=json.loads((receipt.parent/'lifecycle.json').read_text())
        if (report['outer_receipts_sha256'][str(receipt)]!=core.digest(receipt) or state.get('status')!='PASS' or
            state.get('receipt_sha256')!=core.digest(receipt)):raise ValueError('Tiny outer stage receipt/lifecycle changed')
    evaluation=json.loads(required[-1].read_text())['result']
    if evaluation['identities']!=query_bundle(evaluation['directory'],evaluation['binding']):raise ValueError('Tiny exact13 identities changed')
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['seal-small','verify-small'])
    arguments=parser.parse_args();result=seal_small_gate() if arguments.action=='seal-small' else verify_small_gate()
    print(json.dumps({key:result[key] for key in ('status','model_sha256','dependencies_sha256','query_identities')}))
