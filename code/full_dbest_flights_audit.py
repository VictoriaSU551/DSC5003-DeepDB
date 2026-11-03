"""Independent, read-only audit of the frozen original-DBEst Flights1B run.

This layer never imports the engine/helper or runs fitting/integration. Its pins
identify the reviewed completed run; replacing a scientific result requires a
new versioned audit namespace, not regenerating these pins automatically.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import pickle
import random
import re
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/full/dbest_flights_audit'
PREFIX='output/full/dbest_flights'
SOURCE_MANIFEST_SHA256='2c0d86b156fa1da40a68180ae9a9fb54a7e79992fd5c027333bc76117e6c84c1'
CANONICAL_MANIFEST_SHA256='841bdc9866326bccbdef382d48a9344b1d4b24fa5c57fc3af517c2ccfefc0b73'
COMPLETE_INVENTORY_SHA256='f0b369776c4a8d95e4973964f11a357427980805755bc1cf4bdb46ed07304edc'
SOURCE_REPORT_SHA256='de73e1110d7299e8fdd092e0ab2e0502b8502da783a0e35602889b2e56159b30'
FROZEN_WRAPPER_SHA256='2c690c33c8b875a9794addaf2143f2b6e1d8f0e2da145cef9a5da4ee13e54073'
SAMPLE_SHA256='9d9c78d0e03b403472e34da73af9f3dccde070036c3ed02c649ce4ee880d6f45'
SOURCE_COMMIT='2220a937b5eef358eb42a715da328915048b7250'
QUERY_NAMES=('F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2')
STATES='AK AL AR AZ CA CO CT FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA PR RI SC SD TN TT TX UT VA VI VT WA WI WV WY'.split()
STEMS=tuple(['F1.1_all','F1.2_all']+['F3.1_'+str(year) for year in range(1995,2017)]+['F4.1_'+state for state in STATES])


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def strict_json(text):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    def invalid(value):raise ValueError('Nonfinite JSON number: '+value)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=invalid)


def read_json(path):return strict_json(Path(path).read_text(encoding='utf-8'))


def canonical_path(name):
    if not isinstance(name,str):raise ValueError('Artifact path must be text')
    name=name.replace('\\','/');path=PurePosixPath(name)
    if not name or path.is_absolute() or ':' in name or any(x in ('','..','.') for x in name.split('/')):
        raise ValueError('Unsafe artifact path')
    return path.as_posix()


def normalize_manifest(mapping):
    if not isinstance(mapping,dict):raise ValueError('Artifact manifest must be a mapping')
    result={}
    for name,value in mapping.items():
        name=canonical_path(name)
        if name in result:raise ValueError('Duplicate normalized artifact path: '+name)
        if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('Invalid SHA256')
        result[name]=value
    return result


def manifest_digest(mapping):
    normalized=normalize_manifest(mapping)
    return hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def required_artifacts():
    result={PREFIX+'/verification.json','data/dbest_flights/selection_seal.json',
            'data/dbest_flights/selected_rows.pkl','data/dbest_flights/training_metadata.json'}
    for index in range(12):
        result.update(PREFIX+'/query_%02d'%index+suffix for suffix in ('.json','.seal.json'))
    for stem in STEMS:
        result.update({PREFIX+'/models/'+stem+'.pkl',PREFIX+'/models/'+stem+'.json',PREFIX+'/integrals/'+stem+'.json'})
    if len(STEMS)!=76 or len(result)!=256:raise ValueError('Internal required artifact inventory is incomplete')
    return result


def validate_manifest(mapping,required,expected_digest):
    normalized=normalize_manifest(mapping)
    if not required or not normalized or set(normalized)!=set(required):
        raise ValueError('Exact nonempty artifact set required; missing='+repr(sorted(set(required)-set(normalized)))+
                         '; extra='+repr(sorted(set(normalized)-set(required))))
    if manifest_digest(normalized)!=expected_digest:raise ValueError('Pinned complete manifest digest changed')
    return normalized


def verify_files(root,mapping):
    root=Path(root).resolve()
    for name,expected in normalize_manifest(mapping).items():
        path=(root/name).resolve()
        if root not in path.parents or not path.is_file() or sha256(path)!=expected:
            raise ValueError('Artifact checksum/missing file: '+name)


def assert_frozen_wrapper(root=ROOT):
    path=Path(root)/'code/full_dbest_flights.py'
    if not path.is_file() or sha256(path)!=FROZEN_WRAPPER_SHA256:
        raise ValueError('Frozen wrapper changed: reject partial recovery/cache reuse; use a new wrapper-version namespace')
    return FROZEN_WRAPPER_SHA256


def validate_report(report):
    expected={'status':'PASS_WITH_GAPS','stage':'ORIGINAL_DBEST_1B_POPULATION_BOUNDED_20K_FIT',
              'population_rows':1000000000,'retained_sample_rows':9997912,'unique_fit_rows':20000,'seed':74131,
              'native_method_calls_total_verified':76,'native_kde_evaluations_total_verified':429156,
              'paper_scale_population_reached':True,'paper_DBEst_training_configuration_recovered':False,
              'all_native_integrals_verified':True,'original_small_gate_bytes_unchanged':True,
              'source_commit':SOURCE_COMMIT,'wrapper_sha256':FROZEN_WRAPPER_SHA256}
    for key,value in expected.items():
        if report.get(key)!=value:raise ValueError('Frozen scientific report contract changed: '+key)
    if not 0<report['process_peak_working_set_bytes']<=512*1024**2:raise ValueError('Memory budget contract changed')
    queries=report['queries']
    if len(queries)!=12 or [(q['query_no'],q['name']) for q in queries]!=list(enumerate(QUERY_NAMES)):
        raise ValueError('Exactly12 aligned queries required')
    native=[];stems=[]
    for index,query in enumerate(queries):
        supported=index in (0,1,5,8)
        if not supported:
            if query['status']!='UNSUPPORTED' or query['predictions']:raise ValueError('Unsupported query was promoted')
            continue
        if query['status']!=('SUPPORTED_WITH_COVERAGE_GAPS' if index==8 else 'SUPPORTED'):
            raise ValueError('Supported query coverage contract changed')
        if len(query['predictions'])!={0:1,1:1,5:22,8:52}[index]:raise ValueError('Native model group count changed')
        if index==8 and [(g['group'],g['status'],g['estimate']) for g in query['unavailable_groups']]!=[('DE','UNSUPPORTED_INSUFFICIENT_SAMPLE',None)]:
            raise ValueError('Missing DE sample coverage was concealed')
        groups=set()
        for prediction in query['predictions']:
            if prediction['group'] in groups:raise ValueError('Duplicate native prediction group')
            groups.add(prediction['group']);stem=query['name']+'_'+prediction['group'];stems.append(stem)
            if canonical_path(prediction['model_path'])!=PREFIX+'/models/'+stem+'.pkl':raise ValueError('Native model path mismatch')
            item=prediction['native'];native.append(item)
            if item['native_method_calls']!=1 or item['integral_verified'] is not True:raise ValueError('Native integral evidence missing')
            if not 0<prediction['fit_n']<=20000 or not math.isfinite(prediction['estimate']):raise ValueError('Invalid fit size/estimate')
    if set(stems)!=set(STEMS) or len(stems)!=76:raise ValueError('Exact76 native model set changed')
    if sum(x['native_method_calls'] for x in native)!=76 or sum(x['native_kde_evaluations'] for x in native)!=429156:
        raise ValueError('Native invocation counters disagree')


def selection_and_query_contract(root,report):
    binding=report['input_binding'];selection=read_json(root/'data/dbest_flights/selection_seal.json')
    metadata=read_json(root/'data/dbest_flights/training_metadata.json')
    if selection['input_binding']!=binding or read_json(root/(PREFIX+'/input_binding.json'))!=binding:
        raise ValueError('Selection/input binding differs from completed report')
    if binding['sample_sha256']!=SAMPLE_SHA256 or binding['fit_rows']!=20000 or binding['population_rows']!=1000000000:
        raise ValueError('1B retained sample input contract changed')
    with (root/'data/dbest_flights/selected_rows.pkl').open('rb') as stream:selected=pickle.load(stream)
    ids=selected['row_ids'];rows=selected['rows']
    expected_ids=sorted(random.Random(74131).sample(range(9997912),20000))
    if ids!=expected_ids or len(rows)!=20000 or selection['unique_selected_rows']!=20000:
        raise ValueError('Uniform unique20K retained-row selection contract changed')
    if hashlib.sha256(json.dumps(ids).encode()).hexdigest()!=selection['row_ids_sha256']:
        raise ValueError('Selected row-id checksum changed')
    if sum(selected['state_counts'].values())!=9997912:raise ValueError('All-sample state count catalog incomplete')
    truth=read_json(root/'output/full/flights/flights-1b/ground_truth.json')
    if truth['population_rows']!=1000000000 or truth['complete'] is not True or len(truth['queries'])!=12:
        raise ValueError('Full-stream1B truth is incomplete')
    for index in (0,1,5):
        expected={str(g['key'][0]) if g['key'] else 'all':g['count'] for g in truth['queries'][index]['groups']}
        actual=metadata['counts'][QUERY_NAMES[index]]
        if {key:value['N'] for key,value in actual.items()}!=expected or any(v['estimated'] for v in actual.values()):
            raise ValueError('Declared pre-range population COUNT metadata changed')
    for state,count in selected['state_counts'].items():
        group=metadata['counts']['F4.1'][state]
        if (group['retained_state_count']!=count or group['N']!=count/.01 or not group['estimated'] or
            group['sample_probability']!=.01 or group['standard_error']!=math.sqrt(count*.99)/.01):
            raise ValueError('F4 population metadata is not the unfiltered sample count/rate')
    if metadata['evaluation_sum_and_value_fields_used_for_fitting'] is not False:raise ValueError('Training answer leakage flag changed')
    for query in report['queries']:
        index=query['query_no'];raw=read_json(root/(PREFIX+'/query_%02d.json'%index));seal=read_json(root/(PREFIX+'/query_%02d.seal.json'%index))
        if seal['binding']!=binding or seal['sha256']!=sha256(root/(PREFIX+'/query_%02d.json'%index)):
            raise ValueError('Query physical seal/binding mismatch')
        if raw['name']!=query['name'] or raw['status']!=query['status'] or len(raw['predictions'])!=len(query['predictions']):
            raise ValueError('Raw/evaluated query alignment changed')
        for prediction,evaluated in zip(raw['predictions'],query['predictions']):
            if any(evaluated.get(key)!=value for key,value in prediction.items()):raise ValueError('Evaluated query changed original prediction')
            stem=query['name']+'_'+prediction['group']
            model=read_json(root/(PREFIX+'/models/'+stem+'.json'));integral=read_json(root/(PREFIX+'/integrals/'+stem+'.json'))
            if integral['actual']!=prediction['native']:raise ValueError('Native integral/raw receipt mismatch')
            if (model['configuration']['inputs']!=binding or model['fit_rows']!=prediction['fit_n'] or
                model['population_rows']!=prediction['population_metadata']['N'] or
                model['model_sha256']!=prediction['model_sha256']):raise ValueError('Model metadata/prediction mismatch')
            if prediction['population_metadata']!=metadata['counts'][query['name']][prediction['group']]:
                raise ValueError('Model population metadata mismatch')
    return {'unique_fit_rows':len(ids),'retained_sample_rows':sum(selected['state_counts'].values()),'state_catalog_size':len(selected['state_counts'])}


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temp),str(path))


def audit(write=True):
    started=time.perf_counter();root=ROOT
    assert_frozen_wrapper(root)
    manifest_path=root/(PREFIX+'/verification_seal.json');report_path=root/(PREFIX+'/verification.json')
    if sha256(manifest_path)!=SOURCE_MANIFEST_SHA256 or sha256(report_path)!=SOURCE_REPORT_SHA256:
        raise ValueError('Reviewed source manifest/report self pin changed')
    manifest=validate_manifest(read_json(manifest_path)['files_sha256'],required_artifacts(),CANONICAL_MANIFEST_SHA256)
    verify_files(root,manifest)
    report=read_json(report_path);validate_report(report)
    # Scientific subdirectories cannot hide extra or duplicated model/integral files.
    for subdir in ('models','integrals'):
        actual={p.relative_to(root).as_posix() for p in (root/PREFIX/subdir).iterdir() if p.is_file()}
        required={p for p in manifest if p.startswith(PREFIX+'/'+subdir+'/')}
        if actual!=required:raise ValueError('Scientific directory artifact inventory changed: '+subdir)
    catalog=selection_and_query_contract(root,report)
    artifacts=dict(manifest)
    def merge(mapping):
        for name,value in normalize_manifest(mapping).items():
            if name in artifacts and artifacts[name]!=value:raise ValueError('Contradictory source artifact checksum')
            artifacts[name]=value
    merge(report['input_binding']['files_sha256']);merge(report['protected_original_sha256'])
    merge({PREFIX+'/verification_seal.json':SOURCE_MANIFEST_SHA256,'code/full_dbest_flights.py':FROZEN_WRAPPER_SHA256,
           'data/flights/generated/flights-1b/sample.csv':SAMPLE_SHA256})
    verify_files(root,artifacts)
    if manifest_digest(artifacts)!=COMPLETE_INVENTORY_SHA256:raise ValueError('Pinned complete611 dependency inventory changed')
    if sha256(manifest_path)!=SOURCE_MANIFEST_SHA256 or sha256(report_path)!=SOURCE_REPORT_SHA256:
        raise ValueError('Original source changed during independent audit')
    result={'status':'PASS_WITH_GAPS','stage':'INDEPENDENT_FROZEN_DBEST_1B_FINAL_ARTIFACT_AUDIT',
            'population_rows':1000000000,'retained_sample_rows':9997912,'unique_fit_rows':20000,
            'verified_native_calls':76,'unsupported_query_count':8,'native_models':76,'source_manifest_items':len(manifest),
            'source_manifest_sha256':SOURCE_MANIFEST_SHA256,'canonical_source_manifest_sha256':CANONICAL_MANIFEST_SHA256,
            'source_report_sha256':SOURCE_REPORT_SHA256,'frozen_wrapper_sha256':FROZEN_WRAPPER_SHA256,
            'selection_contract':catalog,'files_sha256':artifacts,'complete_inventory_sha256':manifest_digest(artifacts),
            'original_files_unchanged':True,'audit_only_no_fit_or_integration':True,
            'paper_DBEst_training_configuration_recovered':False,'coverage_gap':'F4.1 DE has no selected fit row; eight original query classes remain unsupported',
            'audit_source_sha256':sha256(__file__),'wall_seconds':time.perf_counter()-started}
    if write:
        path=OUT/'verification.json';seal=OUT/'verification_seal.json'
        atomic_json(path,result);atomic_json(seal,{'report_sha256':sha256(path),'audit_source_sha256':sha256(__file__),
                    'source_manifest_sha256':SOURCE_MANIFEST_SHA256,'complete_inventory_sha256':result['complete_inventory_sha256'],
                    'required_source_artifacts':sorted(required_artifacts())})
    return result


def verify():
    path=OUT/'verification.json';seal=read_json(OUT/'verification_seal.json')
    if seal.get('report_sha256')!=sha256(path) or seal.get('audit_source_sha256')!=sha256(__file__):
        raise ValueError('Independent audit self seal changed')
    if seal.get('required_source_artifacts')!=sorted(required_artifacts()) or seal.get('source_manifest_sha256')!=SOURCE_MANIFEST_SHA256:
        raise ValueError('Independent audit exact required inventory changed')
    prior=read_json(path);current=audit(write=False)
    for key in ('complete_inventory_sha256','files_sha256','population_rows','unique_fit_rows','verified_native_calls'):
        if prior.get(key)!=current[key]:raise ValueError('Independent audit physical/content mismatch: '+key)
    if seal.get('complete_inventory_sha256')!=current['complete_inventory_sha256']:raise ValueError('Independent complete manifest self seal changed')
    return current


def recovery_gate(root=ROOT):
    """Mandatory preflight for a future partial recovery; never start computation."""
    assert_frozen_wrapper(root)  # Must run before even opening a cache manifest.
    path=Path(root)/(PREFIX+'/verification_seal.json')
    if not path.exists() or sha256(path)!=SOURCE_MANIFEST_SHA256:
        raise ValueError('Only the frozen reviewed namespace can be considered; a new run needs a wrapper-version namespace')
    manifest=validate_manifest(read_json(path)['files_sha256'],required_artifacts(),CANONICAL_MANIFEST_SHA256)
    present={name:value for name,value in manifest.items() if (Path(root)/name).is_file()}
    verify_files(root,present)
    return {'status':'FROZEN_WRAPPER_RECOVERY_GATE_PASS','wrapper_sha256':FROZEN_WRAPPER_SHA256,
            'complete':len(present)==len(manifest),'present_artifacts':len(present),'required_artifacts':256,
            'missing_artifacts':sorted(set(manifest)-set(present)),
            'scope':'Read-only preflight only; modified wrappers must use a new versioned namespace. No recovery executed.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['audit','verify','recovery-gate'])
    args=parser.parse_args();report={'audit':audit,'verify':verify,'recovery-gate':recovery_gate}[args.action]()
    print(json.dumps({key:report[key] for key in ['status','stage','population_rows','unique_fit_rows','verified_native_calls','source_manifest_items','complete_inventory_sha256'] if key in report}))
