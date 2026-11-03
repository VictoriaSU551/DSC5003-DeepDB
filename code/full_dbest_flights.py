"""Original DBEst on the finalized 1B population, bounded to 20K retained rows."""
import argparse
from collections import Counter
import csv
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import time

import full_dbest as official

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/full/dbest_flights'
DATA=ROOT/'data/dbest_flights'
FLIGHTS_OUTPUT=ROOT/'output/full/flights/flights-1b'
SAMPLE=ROOT/'data/flights/generated/flights-1b/sample.csv'
SMALL_OUTPUT=ROOT/'output/full/dbest'
FIT_ROWS,SEED=20000,74131
MEMORY_LIMIT=512*1024*1024


def peak_bytes():
    if os.name!='nt':raise RuntimeError('This memory-gated receipt requires Windows process counters')
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in
            ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    current=ctypes.windll.kernel32.GetCurrentProcess;current.restype=wintypes.HANDLE
    read=ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not read(current(),ctypes.byref(counters),counters.cb):raise ctypes.WinError()
    if counters.PeakWorkingSetSize>MEMORY_LIMIT:raise MemoryError('DBEst 512MiB process peak budget exceeded')
    return counters.PeakWorkingSetSize


def stream_selection(path,total_rows,fit_rows,seed):
    official.require_fit_size(fit_rows)
    if total_rows<fit_rows:raise ValueError('Retained sample row count is smaller than fit size')
    row_ids=sorted(random.Random(seed).sample(range(total_rows),fit_rows));selected=set(row_ids)
    rows=[];states=Counter();seen=0
    with Path(path).open(newline='') as stream:
        for index,row in enumerate(csv.DictReader(stream)):
            states[row['DEST_STATE_ABR']]+=1
            if index in selected:rows.append(row)
            seen+=1
    if seen!=total_rows or len(rows)!=fit_rows:raise ValueError('Final retained sample row count mismatch')
    return {'row_ids':row_ids,'rows':rows,'state_counts':dict(sorted(states.items()))}


def training_metadata(truth,state_counts,probability):
    """Only declared pre-range COUNTs enter fitting; aggregate answers do not."""
    if not 0<probability<=1:raise ValueError('Invalid retained sample probability')
    counts={}
    for index in [0,1,5]:
        query=truth['queries'][index];groups={}
        for group in query['groups']:
            key=str(group['key'][0]) if group['key'] else 'all'
            groups[key]={'N':group['count'],'estimated':False,
                         'source':'Original full-stream prefilter/group COUNT, separately declared training metadata'}
        counts[query['query_name']]=groups
    counts['F4.1']={key:{'N':value/probability,'estimated':True,'retained_state_count':value,
                          'sample_probability':probability,'standard_error':math.sqrt(value*(1-probability))/probability,
                          'source':'All retained Bernoulli rows in state, BEFORE numeric distance filter; N_hat=n_state/p'}
                   for key,value in sorted(state_counts.items())}
    return {'population_rows':truth['population_rows'],'counts':counts,
            'F4_1_N_sum':sum(x['N'] for x in counts['F4.1'].values()),
            'F4_1_variance_note':'Plug-in Bernoulli HT count variance n_state*(1-p)/p^2; this is metadata uncertainty, not a query confidence interval',
            'evaluation_sum_and_value_fields_used_for_fitting':False}


def source_binding():
    result_path=FLIGHTS_OUTPUT/'generation_result.json';state_path=FLIGHTS_OUTPUT/'checkpoint.json'
    truth_path=FLIGHTS_OUTPUT/'ground_truth.json'
    result=json.loads(result_path.read_text());state=json.loads(state_path.read_text());truth=json.loads(truth_path.read_text())
    if result['status']!='PASS' or result['rows_generated']!=1000000000 or not truth['complete'] or truth['population_rows']!=1000000000:
        raise ValueError('Finalized 1B population and full-stream truth required')
    if state['rows_generated']!=result['rows_generated'] or state['sample_rows']!=result['sample_rows'] or state['binding']!=result['binding']:
        raise ValueError('Generation result/checkpoint binding mismatch')
    entry=result['files']['sample.csv']
    if state['files']['sample.csv']!=entry or SAMPLE.stat().st_size!=entry['offset']:
        raise ValueError('Final retained sample offset/seal mismatch')
    official.check_file(SAMPLE,entry['sha256'])
    support=official.query_support()
    if len(truth['queries'])!=12 or [(q['query_no'],q['query_name']) for q in truth['queries']]!=[(q['query_no'],q['name']) for q in support]:
        raise ValueError('Exactly aligned 12 full-stream queries required')
    normalize=lambda sql:''.join(sql.lower().split())
    if list(map(normalize,official.QUERIES.read_text().splitlines()))!=[normalize(q['sql']) for q in truth['queries']]:
        raise ValueError('Original query SQL mismatch')
    paths=[result_path,state_path,truth_path,official.QUERIES,Path(official.__file__),SMALL_OUTPUT/'environment.json',SMALL_OUTPUT/'small_gate_first_success.json']
    binding={'population_rows':1000000000,'retained_sample_rows':result['sample_rows'],'sample_sha256':entry['sha256'],
             'generation_binding':state['binding'],'sample_probability':state['binding_details']['config']['sample_rate'],
             'seed':SEED,'fit_rows':FIT_ROWS,'source_commit':official.SOURCE_COMMIT,
             'files_sha256':{str(p.relative_to(ROOT)):official.digest(p) for p in paths}}
    path=OUTPUT/'input_binding.json'
    if path.exists() and json.loads(path.read_text())!=binding:raise ValueError('1B DBEst input binding changed')
    if not path.exists():official.atomic(path,binding)
    return binding,truth


def protected_small_snapshot():
    paths=list(SMALL_OUTPUT.rglob('*'))+list(official.SOURCE.rglob('*.py'))
    paths+=[ROOT/'code/full_dbest.py',ROOT/'code/tests/test_full_dbest.py',ROOT/'docs/FULL_DBEST_PROTOCOL.md',
            official.GOLD_CSV,official.GOLD_DATABASE,official.GOLD_OUTPUT/'sqlite_exact_state.json',official.GOLD_OUTPUT/'golden_validation.json']
    return {str(path.relative_to(ROOT)):official.digest(path) for path in paths if path.is_file()}


def selected_data(binding):
    DATA.mkdir(parents=True,exist_ok=True)
    manifest=DATA/'selection_seal.json';path=DATA/'selected_rows.pkl'
    if manifest.exists():
        record=json.loads(manifest.read_text())
        if record['input_binding']!=binding:raise ValueError('Selection input binding changed')
        official.check_file(path,record['pickle_sha256'])
        with path.open('rb') as stream:data=pickle.load(stream)
    else:
        start=time.perf_counter();data=stream_selection(SAMPLE,binding['retained_sample_rows'],FIT_ROWS,SEED)
        temporary=path.with_suffix('.tmp')
        with temporary.open('wb') as stream:pickle.dump(data,stream,protocol=4)
        os.replace(str(temporary),str(path))
        official.atomic(manifest,{'input_binding':binding,'pickle_sha256':official.digest(path),
                                 'scan_seconds':time.perf_counter()-start,'unique_selected_rows':FIT_ROWS,
                                 'row_ids_sha256':hashlib.sha256(json.dumps(data['row_ids']).encode()).hexdigest()})
    if len(data['row_ids'])!=FIT_ROWS or len(set(data['row_ids']))!=FIT_ROWS or len(data['rows'])!=FIT_ROWS:
        raise ValueError('Selection unique-row contract failed')
    if sum(data['state_counts'].values())!=binding['retained_sample_rows']:raise ValueError('Full-sample state catalog row count failed')
    peak_bytes();return data


def cohorts_for(selected,metadata):
    cohorts={(query,key):{'population':group['N'],'xs':[],'ids':[]} for query,groups in metadata['counts'].items() for key,group in groups.items()}
    def add(query,key,index,value):
        item=cohorts[(query,key)];item['xs'].append(float(value));item['ids'].append(index)
    for index,row in zip(selected['row_ids'],selected['rows']):
        if row['ORIGIN']=='ATL':add('F1.1','all',index,row['DEP_DELAY'])
        if row['UNIQUE_CARRIER']=='TW':add('F1.2','all',index,row['DISTANCE'])
        if row['UNIQUE_CARRIER']=='9E':add('F3.1',row['YEAR_DATE'],index,row['DISTANCE'])
        add('F4.1',row['DEST_STATE_ABR'],index,row['DISTANCE'])
    return cohorts


def configure_official_helper():
    # Only this process's output routing changes. The already verified helper,
    # source bytes, environment and 200K data/output remain immutable on disk.
    official.OUTPUT=OUTPUT
    official.restore_source()
    evidence=json.loads((SMALL_OUTPUT/'numerical_failure_F1.2_all.json').read_text())
    evidence.update(evidence_scope='Previously verified 200K numerical compatibility failure; NOT a new 1B native result',
                    original_evidence_sha256=official.digest(SMALL_OUTPUT/'numerical_failure_F1.2_all.json'))
    target=OUTPUT/'numerical_failure_F1.2_all.json'
    if target.exists() and json.loads(target.read_text())!=evidence:raise ValueError('Adapter provenance evidence changed')
    if not target.exists():official.atomic(target,evidence)


def predict_query(spec,cohorts,metadata,binding):
    path=OUTPUT/('query_%02d.json'%spec['query_no']);seal=path.with_suffix('.seal.json')
    if path.exists() and seal.exists():
        entry=json.loads(seal.read_text())
        if entry['binding']!=binding:raise ValueError('Query input binding changed')
        official.check_file(path,entry['sha256'])
        result=json.loads(path.read_text());result['query_receipt_reused']=True
        return result
    result=dict(spec,training_configuration='Original CRegression LR + original Gaussian KDE bandwidth1 + previously validated quadrature points/limit adapter',
                predictions=[],unavailable_groups=[])
    if spec['status']=='SUPPORTED':
        aggregate={0:'avg',1:'avg',5:'sum',8:'count'}[spec['query_no']]
        for key,prior in sorted(metadata['counts'][spec['name']].items()):
            data=cohorts[(spec['name'],key)]
            if not data['xs']:
                result['unavailable_groups'].append({'group':key,'status':'UNSUPPORTED_INSUFFICIENT_SAMPLE','estimate':None,'fit_n':0,'population_metadata':prior})
                continue
            engine,model=official.cached_model(spec['name'],key,data,binding)
            lower=2500. if spec['query_no']==8 else min(data['xs'])-12.
            upper=max(max(data['xs'])+12.,lower+12.)
            actual=official.verified_integral(engine,data['xs'],lower,upper,(aggregate,),spec['name']+'_'+key)
            result['predictions'].append({'group':key,'aggregate':aggregate,'estimate':actual['values'][aggregate],
                                         'population_metadata':prior,'fit_n':len(data['xs']),'native':actual,
                                         'model_path':model['path'],'model_sha256':model['model_sha256'],'fit_seconds':model['fit_seconds']})
            peak_bytes()
        if result['unavailable_groups']:result['status']='SUPPORTED_WITH_COVERAGE_GAPS'
        result['all_native_integrals_verified']=all(p['native']['integral_verified'] for p in result['predictions'])
    official.atomic(path,result)
    official.atomic(seal,{'binding':binding,'sha256':official.digest(path)})
    return result


def evaluate_after_predictions(queries,truth):
    result=[]
    for query,reference in zip(queries,truth['queries']):
        output=dict(query)
        if query['status']=='UNSUPPORTED':result.append(output);continue
        exact={str(g['key'][0]) if g['key'] else 'all':g for g in reference['groups']}
        predictions=[]
        for prediction in query['predictions']:
            group=exact.get(prediction['group']);numerator=group['numerator'] if group else 0;denominator=group['denominator'] if group else 1
            value=numerator/denominator;estimate=prediction['estimate']
            predictions.append(dict(prediction,truth_numerator=numerator,truth_denominator=denominator,
                                    truth_group_present=group is not None,exact=value,absolute_error=abs(estimate-value),
                                    relative_error=abs(estimate/value-1) if value else None))
        keys={p['group'] for p in predictions};errors=[p['relative_error'] for p in predictions if p['relative_error'] is not None]
        output.update(predictions=predictions,missing_truth_groups=sorted(set(exact)-keys),extra_prediction_groups=sorted(keys-set(exact)),
                      mean_relative_error_over_present_nonzero_truth=math.fsum(errors)/len(errors) if errors else None,
                      max_relative_error_over_present_nonzero_truth=max(errors) if errors else None)
        result.append(output)
    return result


def worker():
    start=time.perf_counter();before=protected_small_snapshot();binding,truth=source_binding();configure_official_helper()
    selected=selected_data(binding)
    metadata=training_metadata(truth,selected['state_counts'],binding['sample_probability'])
    official.atomic(DATA/'training_metadata.json',metadata)
    cohorts=cohorts_for(selected,metadata)
    # Raw query receipts contain no evaluated SUM/AVG/filtered COUNT answers.
    queries=[predict_query(spec,cohorts,metadata,binding) for spec in official.query_support()]
    evaluated=evaluate_after_predictions(queries,truth)
    actual=[p['native'] for q in queries for p in q['predictions']]
    after=protected_small_snapshot()
    if after!=before:raise ValueError('Original 200K gate/source bytes changed')
    peak=peak_bytes()
    report={'status':'PASS_WITH_GAPS','stage':'ORIGINAL_DBEST_1B_POPULATION_BOUNDED_20K_FIT',
            'paper_scale_population_reached':True,'paper_DBEst_training_configuration_recovered':False,
            'population_rows':1000000000,'retained_sample_rows':binding['retained_sample_rows'],'unique_fit_rows':FIT_ROWS,
            'seed':SEED,'queries':evaluated,'training_metadata_path':str((DATA/'training_metadata.json').relative_to(ROOT)),
            'F4_1_population_metadata_estimated':True,'F4_1_N_sum':metadata['F4_1_N_sum'],
            'all_native_integrals_verified':all(x['integral_verified'] for x in actual),
            'native_method_calls_total_verified':sum(x['native_method_calls'] for x in actual),
            'native_method_calls_this_invocation':sum(p['native']['native_method_calls'] for q in queries for p in q['predictions'] if not q.get('query_receipt_reused') and not p['native'].get('verified_integral_reused')),
            'native_kde_evaluations_total_verified':sum(x['native_kde_evaluations'] for x in actual),
            'native_query_seconds_total_verified':sum(sum(x['seconds'].values()) for x in actual),
            'process_peak_working_set_bytes':peak,'process_peak_limit_bytes':MEMORY_LIMIT,'wall_seconds':time.perf_counter()-start,
            'source_commit':official.SOURCE_COMMIT,'helper_module_sha256':official.digest(official.__file__),
            'adapter_evidence_scope':'Validated original 200K compatibility evidence, copied with explicit provenance; no new 1B default-quadrature failure is claimed',
            'original_small_gate_bytes_unchanged':True,'protected_original_sha256':before,
            'input_binding':binding,'wrapper_sha256':official.digest(__file__)}
    path=OUTPUT/'verification.json';official.atomic(path,report)
    first=OUTPUT/'first_success.json'
    if not first.exists():official.atomic(first,report)
    protected=[path,DATA/'selection_seal.json',DATA/'selected_rows.pkl',DATA/'training_metadata.json']
    protected+=list((OUTPUT/'models').glob('*'))+list((OUTPUT/'integrals').glob('*.json'))+list(OUTPUT.glob('query_*.json'))
    official.atomic(OUTPUT/'verification_seal.json',{'files_sha256':{str(p.relative_to(ROOT)):official.digest(p) for p in protected if p.is_file()}})
    return report


def verify():
    binding,_=source_binding()
    report=json.loads((OUTPUT/'verification.json').read_text())
    if report['input_binding']!=binding or report['wrapper_sha256']!=official.digest(__file__):raise ValueError('Verified 1B wrapper/input changed')
    for name,sha in json.loads((OUTPUT/'verification_seal.json').read_text())['files_sha256'].items():official.check_file(ROOT/name,sha)
    if protected_small_snapshot()!=report['protected_original_sha256']:raise ValueError('Protected original bytes changed after gate')
    return report


def run():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if (OUTPUT/'verification.json').exists():return verify()
    result=official.run_command([official.PRIVATE_PYTHON,'-B',__file__,'worker'],OUTPUT/'process.json',timeout=900)
    if result.returncode:raise RuntimeError('Original DBEst 1B adapter failed: '+result.stderr[-4000:])
    return verify()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['run','worker','verify'])
    arguments=parser.parse_args();report={'run':run,'worker':worker,'verify':verify}[arguments.action]()
    print(json.dumps({k:report[k] for k in ['status','stage','unique_fit_rows','process_peak_working_set_bytes','wall_seconds']}))
