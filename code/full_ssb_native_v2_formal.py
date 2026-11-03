"""Review-gated corrected SSB generation and strictly read-only final audit.

No function in this module turns the historical MISMATCH into PASS. Final PASS
means the new population matches the author row count and all13 query truths;
the author did not publish a complete raw snapshot SHA.
"""
import argparse
import ctypes
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import sys
import time
from itertools import zip_longest
import subprocess

import full_ssb_native_v2 as native
import full_ssb_native_v2_stream as controller

ROOT=native.ROOT
OUTPUT=native.OUTPUT
FINAL=ROOT/'output/full/results/ssb_native_v2.json'
AUTHOR=ROOT/'code/benchmarks/ssb/ground_truth_500GB.pkl'
QUERIES=ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql'
AUTHOR_SHA='14ff6ea9cf4d8b8e0b0f05066e8854cbb5f4e186715f67bf5d528f27722f0d1c'
AUTHOR_ROWS=3000028242
REQUESTED_NUMERATOR=3333
REQUESTED_DENOMINATOR=1000000
FORMAL_CUTOFF=(REQUESTED_NUMERATOR*(1<<64))//REQUESTED_DENOMINATOR
GIB=1024**3


def read_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    def invalid(value):raise ValueError('Nonfinite JSON constant: '+value)
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=invalid)


def author_groups():
    if native.digest(AUTHOR)!=AUTHOR_SHA:raise ValueError('Pinned author truth changed')
    with AUTHOR.open('rb') as stream:raw=pickle.load(stream)
    if set(raw)!=set(range(13)):raise ValueError('Author query identity set changed')
    return {(q,tuple(str(v) for v in row[:-1])):row[-1] for q,rows in raw.items() for row in rows}


def author_check(rows,records):
    if type(rows) is not int:raise ValueError('Population rows must be integer')
    expected=author_groups();actual={}
    for record in records:
        if set(record)!={'query_no','group','value'} or type(record['query_no']) is not int or record['query_no'] not in range(13):raise ValueError('Invalid canonical truth query identity')
        q=record['query_no']
        if not isinstance(record['group'],list) or len(record['group'])!=controller.ARITIES[q] or any(type(v) is not str for v in record['group']):raise ValueError('Invalid canonical truth group')
        if type(record['value']) is not int:raise ValueError('Truth must remain exact integers')
        key=(q,tuple(record['group']))
        if key in actual:raise ValueError('Duplicate canonical truth group')
        actual[key]=record['value']
    missing=sorted(set(expected)-set(actual));extra=sorted(set(actual)-set(expected))
    different=[{'query_no':key[0],'group':list(key[1]),'actual':actual[key],'author':expected[key]} for key in sorted(set(actual)&set(expected)) if actual[key]!=expected[key]]
    return {'match':rows==AUTHOR_ROWS and not(missing or extra or different),'author_rows':AUTHOR_ROWS,'actual_rows':rows,
            'row_difference':rows-AUTHOR_ROWS,'author_groups':len(expected),'actual_groups':len(actual),
            'missing':[{'query_no':q,'group':list(group)} for q,group in missing],
            'extra':[{'query_no':q,'group':list(group)} for q,group in extra],'different_values':different}


def resources():
    class Status(ctypes.Structure):
        _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in
          ['ullTotalPhys','ullAvailPhys','ullTotalPageFile','ullAvailPageFile','ullTotalVirtual','ullAvailVirtual','ullAvailExtendedVirtual']]
    memory=Status();memory.dwLength=ctypes.sizeof(memory)
    if os.name!='nt' or not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):raise ValueError('Windows RAM probe failed')
    result={'available_ram_bytes':int(memory.ullAvailPhys),'free_disk_bytes':shutil.disk_usage(ROOT).free,
            'required_ram_bytes':4*GIB,'required_free_disk_bytes':8*GIB,'combined_ssb_budget_bytes':16*GIB}
    if result['available_ram_bytes']<4*GIB or result['free_disk_bytes']<8*GIB:raise ValueError('Formal RAM/disk resource gate failed: '+repr(result))
    return result


def ssb_bytes():
    return sum(p.stat().st_size for root in [ROOT/'data/ssb',ROOT/'output/full/ssb'] for p in root.rglob('*') if p.is_file())


def descriptor(path,rows=False):return native.file_description(path,rows)


def validate_descriptor(description):
    path=Path(description['path'])
    if not path.is_file() or path.stat().st_size!=description['bytes'] or native.digest(path)!=description['sha256']:
        raise ValueError('Physical artifact changed: '+str(path))
    if 'rows' in description:
        with path.open('rb') as stream:rows=sum(block.count(b'\n') for block in iter(lambda:stream.read(4*1024**2),b''))
        if rows!=description['rows']:raise ValueError('Physical row count differs: '+str(path))


def manifest_paths(plan,home,sample):
    """Independent exact inventory, never inferred from a receipt's file map."""
    home=Path(home);sample=Path(sample);b=plan['binding']
    result={'plan':home/'plan.json','checkpoint':home/'checkpoint.json','raw_sample':sample,
            'queries':QUERIES,'author_truth':AUTHOR,'native_executable':Path(b['native_executable']['path']),
            'native_build_receipt':Path(b['native_build_receipt']['path']),
            'resource_probe':home.parent/'resources.json','review_plan':OUTPUT/'formal_review_plan.json','review_plan_seal':OUTPUT/'formal_review_plan_seal.json',
            'readiness':OUTPUT/'readiness/readiness.json','readiness_seal':OUTPUT/'readiness/readiness_seal.json'}
    result.update({'dimension_proof/'+name:home.parent/'dimensions'/name for name in ['receipt.json','receipt_seal.json','lifecycle.json','external_artifacts.json','temporary_manifest.json','temporary_manifest_seal.json','old_dimension_comparison.json','lp64/process.json','lp64/process.sh','lp64/dimension_seeds.tsv']})
    result.update({'dimension/'+table:Path(b['dimensions'][table]['path']) for table in ['customer','supplier','part','date']})
    result.update({'source/'+p.relative_to(ROOT).as_posix():p for p in controller.source_paths()})
    result.update({'platform_runtime/'+name:Path(d['path']) for name,d in b['native_runtime']['direct_import_files'].items()})
    for index in range(len(plan['ranges'])):
        result.update({'chunk/'+str(index)+'/'+name:home/'chunks'/str(index).zfill(8)/name for name in ['stats.json','aggregates.tsv','seeds_after.tsv']})
    return result


def publish_final(plan,home,sample,review_plan,dimension_receipt):
    home=Path(home);sample=Path(sample);controller.check_plan(plan)
    state=read_json(home/'checkpoint.json');life=read_json(home/'lifecycle.json')
    if not state['complete'] or life['status']!='STREAM_COMPLETE' or state['next_shard']!=4000 or len(state['committed_shards'])!=4000:raise ValueError('Formal stream is not complete4000 shards')
    controller.validate_restore(sample,state,plan['binding'],home,plan['ranges'],False)
    comparison=author_check(state['rows'],state['aggregates']);passed=comparison['match']
    if FINAL.exists() or FINAL.with_name(FINAL.stem+'_seal.json').exists():raise ValueError('Final output already exists; preserve and verify it')
    cutoff=plan['binding']['actual_cutoff'];n=state['sample_rows'];artifacts=manifest_paths(plan,home,sample)
    result={'schema':'ssb_native_v2_final_v1','status':'PASS_AUTHOR_TRUTHS' if passed else 'MISMATCH','complete':passed,
            'paper_population_row_count_and_13_truths_match':passed,'raw_snapshot_identity_claimed':False,
            'source_id':plan['binding']['source_id'],'population_rows':state['rows'],'N':state['rows'],'sample_rows':n,
            'sampling':{'sample_seed':plan['binding']['sample_seed'],'actual_cutoff':cutoff,'probability_numerator':cutoff,
                        'probability_denominator':1<<64,'requested_numerator':REQUESTED_NUMERATOR,'requested_denominator':REQUESTED_DENOMINATOR,
                        'effective_probability':float(Fraction(cutoff,1<<64)),
                        'normalizer_numerator':n*(1<<64),'normalizer_denominator':cutoff,'normalizer_n_over_p':float(Fraction(n*(1<<64),cutoff))},
            'canonical_truth':state['aggregates'],'author_comparison':comparison,'plan':descriptor(home/'plan.json'),
            'checkpoint':descriptor(home/'checkpoint.json'),'raw_sample':descriptor(sample,True),
            'dimensions':plan['binding']['dimensions'],'review_plan':descriptor(review_plan),'dimension_receipt':descriptor(dimension_receipt),
            'artifacts':{name:descriptor(path) for name,path in artifacts.items()},'peak_native_working_set_bytes':life['peak_native_working_set_bytes'],
            'stream_seconds':life['seconds'],'combined_ssb_bytes':ssb_bytes(),
            'cleanup_failures':state.get('cleanup_failures',[]),
            'retained_committed_chunk_samples':[str(home/'chunks'/str(i).zfill(8)/'sample.csv') for i in range(4000) if (home/'chunks'/str(i).zfill(8)/'sample.csv').exists()],
            'cleanup_scope':'Residual temporary samples are never consumed; scientific dependency is only the verified committed raw sample prefix. Residuals count toward the disk budget.'}
    native.atomic(FINAL,result);native.atomic(FINAL.with_name(FINAL.stem+'_seal.json'),{'sha256':native.digest(FINAL)})
    if not passed:raise ValueError('Corrected final author comparison MISMATCH; preserved, no model may start')
    return _verify_final(FINAL,False)


def require_final_guard(home,report,review_sha):
    life=read_json(Path(home)/'lifecycle.json')
    if life.get('status')!='FINAL_PASS' or life.get('final_report_sha256')!=native.digest(report) or life.get('review_plan_sha256')!=review_sha:
        raise ValueError('Final namespace has no matching FINAL_PASS guard; RUNNING/TAINTED is never consumed')


def verify_final(path=FINAL):
    return _verify_final(path,True)


def _verify_final(path=FINAL,final_guard=True):
    """Strictly read-only: absent/partial/mismatched evidence fails immediately."""
    path=Path(path);report=read_json(path);seal=read_json(path.with_name(path.stem+'_seal.json'))
    if seal!={'sha256':native.digest(path)}:raise ValueError('Final self seal differs')
    if report.get('schema')!='ssb_native_v2_final_v1' or report.get('status')!='PASS_AUTHOR_TRUTHS' or report.get('complete') is not True or report.get('paper_population_row_count_and_13_truths_match') is not True:
        raise ValueError('Final native author gate is not PASS')
    validate_descriptor(report['plan']);plan=read_json(report['plan']['path']);controller.check_plan(plan)
    home=Path(report['plan']['path']).parent
    if final_guard:require_final_guard(home.parent,path,plan['binding']['formal_review_plan_sha256'])
    if plan['binding']['scale']!='500' or plan['binding']['total_orders']!=750000000 or plan['binding']['shards']!=4000:raise ValueError('Final plan is not formal SF500')
    if plan['binding']['actual_cutoff']!=FORMAL_CUTOFF or plan['binding']['sample_seed']!=20261030:raise ValueError('Final sample policy differs from the reviewed target')
    expected=manifest_paths(plan,Path(report['plan']['path']).parent,report['raw_sample']['path'])
    if set(report.get('artifacts',{}))!=set(expected):raise ValueError('Final required artifact inventory differs')
    for name,p in expected.items():
        if report['artifacts'][name]['path']!=str(p):raise ValueError('Final artifact identity/path differs: '+name)
        validate_descriptor(report['artifacts'][name])
    for key in ['checkpoint','raw_sample','review_plan','dimension_receipt']:validate_descriptor(report[key])
    for table in ['customer','supplier','part','date']:validate_descriptor(report['dimensions'][table])
    verify_review_plan(plan['binding']['formal_review_plan_sha256'],report['review_plan']['path']);verify_dimensions(home.parent/'dimensions',plan['binding']['formal_review_plan_sha256'])
    state=read_json(report['checkpoint']['path']);home=Path(report['plan']['path']).parent;life=read_json(home/'lifecycle.json')
    if not state['complete'] or state['next_shard']!=4000 or len(state['committed_shards'])!=4000 or life['status']!='STREAM_COMPLETE':raise ValueError('Final4000-shard lifecycle is incomplete')
    controller.validate_restore(report['raw_sample']['path'],state,plan['binding'],home,plan['ranges'],False)
    comparison=author_check(state['rows'],state['aggregates'])
    if not comparison['match'] or comparison!=report['author_comparison'] or state['aggregates']!=report['canonical_truth'] or report['N']!=AUTHOR_ROWS or report['population_rows']!=AUTHOR_ROWS:raise ValueError('Final exact author comparison differs')
    if report['source_id']!=plan['binding']['source_id'] or report['sample_rows']!=state['sample_rows'] or report['raw_sample']['rows']!=state['sample_rows']:raise ValueError('Final source/sample accounting differs')
    if report['cleanup_failures']!=state.get('cleanup_failures',[]) or report.get('raw_snapshot_identity_claimed') is not False:raise ValueError('Final cleanup/raw identity declaration differs')
    cutoff=plan['binding']['actual_cutoff'];sampling=report['sampling']
    expected_sampling={'sample_seed':plan['binding']['sample_seed'],'actual_cutoff':cutoff,'probability_numerator':cutoff,'probability_denominator':1<<64,
      'requested_numerator':REQUESTED_NUMERATOR,'requested_denominator':REQUESTED_DENOMINATOR,'normalizer_numerator':state['sample_rows']*(1<<64),'normalizer_denominator':cutoff,
      'effective_probability':float(Fraction(cutoff,1<<64)),
      'normalizer_n_over_p':float(Fraction(state['sample_rows']*(1<<64),cutoff))}
    if sampling!=expected_sampling or report['dimensions']!=plan['binding']['dimensions']:raise ValueError('Final sampling/dimension metadata differs')
    return {'status':'PASS_AUTHOR_TRUTHS','N':AUTHOR_ROWS,'sample_rows':state['sample_rows'],'source_id':report['source_id'],
            'truth_groups':len(state['aggregates']),'queries':13,'report_sha256':native.digest(path),'report':str(path),
            'normalizer_n_over_p':sampling['normalizer_n_over_p'],'paper_raw_snapshot_sha_public':False,
            'final_guard':descriptor(home.parent/'lifecycle.json') if final_guard else None,
            'review_plan':report['review_plan']}


def recovery_gate():
    """Real new native process restart, plus an independent integer hash oracle."""
    tiny=native.callback_tiny_gate();tiny_home=OUTPUT/('callback_tiny_'+native.object_sha(tiny['binding'])[:16])
    plan=controller.stream_plan('0.001',1500,4,tiny_home/'dimensions',20261030,1<<63)
    binding={'plan':plan,'gate_version':1};home=OUTPUT/('recovery_'+native.object_sha(binding)[:16])
    relative={'plan.json','checkpoint.json','execution.lock','native.stderr.log','lifecycle.json','lineorder_sampled.csv'}|{'chunks/'+str(i).zfill(8)+'/'+name for i in range(4) for name in ['stats.json','aggregates.tsv','seeds_after.tsv']}
    required={run+'/'+name for run in ['whole','resumed'] for name in relative}|{'independent_sampling_oracle.json'}
    if (home/'receipt.json').exists():return native.strict_receipt(home,binding,required)
    home.mkdir(exist_ok=False);native.atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        whole=controller.stream(plan,home/'whole')
        paused=controller.stream(plan,home/'resumed',stop_after=2)
        before=paused['checkpoint']['committed_shards'][:];sample=home/'resumed/lineorder_sampled.csv'
        with sample.open('ab') as out:out.write(b'UNCOMMITTED_TAIL_NO_NEWLINE');out.flush();os.fsync(out.fileno())
        resumed=controller.stream(plan,home/'resumed',resume=True)
        if before!=resumed['checkpoint']['committed_shards'][:2]:raise ValueError('Committed shards were changed during restart')
        expected=[];mask=(1<<64)-1
        def mix(x):
            x=(x+0x9e3779b97f4a7c15)&mask;x=((x^(x>>30))*0xbf58476d1ce4e5b9)&mask;x=((x^(x>>27))*0x94d049bb133111eb)&mask;return x^(x>>31)
        for row in native.normalized_facts(tiny_home/'chunk/sample.csv'):
            fields=row.split(b'|');h=mix(20261030^mix(int(fields[0]))^mix(int(fields[1])+0xd1b54a32d192ed03))
            if h<1<<63:expected.append(row+b'\n')
        expected_raw=b''.join(expected)
        if expected_raw!=sample.read_bytes() or expected_raw!=(home/'whole/lineorder_sampled.csv').read_bytes():raise ValueError('Real sampler differs from independent integer oracle or restart')
        golden=native.aggregate_map(tiny_home/'chunk/aggregates.tsv')
        if resumed['checkpoint']['aggregates']!=controller.canonical(golden) or whole['checkpoint']['aggregates']!=controller.canonical(golden):raise ValueError('Restart lost exact query aggregates')
        native.atomic(home/'independent_sampling_oracle.json',{'rows':len(expected),'sha256':hashlib.sha256(expected_raw).hexdigest(),'cutoff':1<<63,
           'expected_integer_probability_denominator':1<<64,'complete_input_rows':6005})
        return native.publish_receipt(home,{'status':'PASS','binding':binding,'rows':6005,'sample_rows':len(expected),'committed_shards_preserved':2,
            'resumed_shards_executed':2,'uninterrupted_shards_executed':4,'all13_integer_aggregates_equal':True,
            'independent_integer_sampling_oracle_equal':True,'uncommitted_tail_truncated_only_after_validation':True},required)
    except BaseException as error:
        native.atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise


def benchmark_sf2():
    sf2=native.corrected_scale_gate(2);sf2_home=OUTPUT/('corrected_sf2_'+native.object_sha(sf2['binding'])[:16])
    cutoff=FORMAL_CUTOFF
    plan=controller.stream_plan('2',3000000,16,sf2_home/'dimensions',20261030,cutoff)
    binding={'plan':plan,'golden_receipt_sha256':native.digest(sf2_home/'receipt.json')};home=OUTPUT/('benchmark_sf2_'+native.object_sha(binding)[:16])
    relative={'plan.json','checkpoint.json','execution.lock','native.stderr.log','lifecycle.json','lineorder_sampled.csv'}|{'chunks/'+str(i).zfill(8)+'/'+name for i in range(16) for name in ['stats.json','aggregates.tsv','seeds_after.tsv']}
    required={'stream/'+name for name in relative}
    if (home/'receipt.json').exists():return native.strict_receipt(home,binding,required)
    home.mkdir(exist_ok=False);native.atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        result=controller.stream(plan,home/'stream')
        expected=read_json(sf2_home/'independent_truth.json')
        if result['checkpoint']['aggregates']!=expected or result['checkpoint']['rows']!=sf2['rows']:raise ValueError('Formal sampler benchmark changed population/truth')
        seconds=result['seconds'];estimate=seconds*250
        return native.publish_receipt(home,{'status':'PASS','binding':binding,'rows':sf2['rows'],'sample_rows':result['checkpoint']['sample_rows'],
            'seconds':seconds,'peak_native_working_set_bytes':result['peak_native_working_set_bytes'],
            'estimated_sf500_stream_seconds_linear':estimate,'estimated_sf500_plus_dimension_seconds_range':[estimate*.7,estimate*2+600],
            'estimate_limit':'Linear SF2 native stream extrapolation; separate SF500 dimension generation/load and platform contention remain uncertain',
            'all13_integer_aggregates_equal':True,'sample_descriptor':descriptor(home/'stream/lineorder_sampled.csv',True)},required)
    except BaseException as error:
        native.atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise


def gate_files(kind):
    if kind=='lp64_tiny':
        return {'compat_a/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','lineorder.tbl','process.json']}|{'lp64_a/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','lineorder.tbl','process.json','process.sh']}|{'lp64_l/'+name for name in ['lineorder.tbl','process.json','process.sh']}
    if kind=='callback_tiny':return {'dimensions/'+table+'.tbl' for table in ['customer','supplier','part','date']}|{'chunk/'+name for name in ['sample.csv','stats.json','aggregates.tsv','seeds_after.tsv']}|{'process.json','independent.sqlite'}
    if kind=='high_order':return {engine+'_'+str(first)+'/'+name for engine in ['llp64','lp64'] for first in [1,306000001,613000001,749999937] for name in ['lineorder.tbl','seeds_after.tsv','process.json']+(['process.sh'] if engine=='lp64' else [])}
    if kind=='high_callback':return {'probe.exe','compile.json'}|{str(first)+'/'+name for first in [1,306000001,613000001,749999937] for name in ['lineorder.tbl','seeds_after.tsv','process.json']}
    if kind in ['sf1','sf2']:
        return {'lp64_dimensions/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json','process.sh']}|{'dimensions/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json']}|{'stock/process.json','stock/process.sh','independent_truth.json','temporary_artifacts.json','callback_process.json'}|{'chunks/'+str(i).zfill(4)+'/'+name for i in range(8 if kind=='sf1' else 16) for name in ['aggregates.tsv','stats.json','seeds_after.tsv']}
    if kind=='sampling':return {'probe.cpp','probe.exe','compile.json'}
    if kind in ['recovery','benchmark']:
        count=4 if kind=='recovery' else 16
        files={'plan.json','checkpoint.json','execution.lock','native.stderr.log','lifecycle.json','lineorder_sampled.csv'}|{'chunks/'+str(i).zfill(8)+'/'+name for i in range(count) for name in ['stats.json','aggregates.tsv','seeds_after.tsv']}
        return {run+'/'+name for run in (['whole','resumed'] if kind=='recovery' else ['stream']) for name in files}|({'independent_sampling_oracle.json'} if kind=='recovery' else set())
    raise ValueError('Unrecognized gate kind')


def check_gate(kind,description):
    validate_descriptor(description);home=Path(description['path']).parent;record=read_json(description['path']);required=gate_files(kind)
    if (home/'lifecycle.json').exists():return native.strict_receipt(home,record['binding'],required)
    # The only provisional gate is explicitly frozen and adopted outside its
    # original directory; read-only verification must not create an adoption.
    pin=native.LEGACY_RECEIPTS.get(home.name)
    if not pin or pin!=description['sha256'] or set(record.get('files_sha256',{}))!=required:raise ValueError('Unrecognized provisional gate/inventory')
    native.strict_receipt(OUTPUT/'adoptions'/home.name,{'legacy_receipt_sha256':pin,'binding':record['binding']},{'artifacts.json'})
    if read_json(OUTPUT/'adoptions'/home.name/'artifacts.json')!=record['files_sha256']:raise ValueError('Legacy adoption differs')
    physical={p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}-{'receipt.json','receipt_seal.json'}
    if physical!=required:raise ValueError('Legacy gate physical inventory changed')
    for name,sha in record['files_sha256'].items():
        if native.digest(home/name)!=sha:raise ValueError('Legacy gate artifact changed')
    return record


def freeze_gates():
    """Execution command: may finish bounded gates; never starts SF500."""
    sources={p.relative_to(ROOT).as_posix():native.digest(p) for p in controller.source_paths()}
    records={'lp64_tiny':native.lp64_tiny_gate(),'callback_tiny':native.callback_tiny_gate(),
             'high_order':native.high_order_gate(),'high_callback':native.high_callback_gate(),'sf1':native.verified_sf1_gate(),'sf2':native.corrected_scale_gate(2),
             'sampling':native.native_sampling_gate(),'recovery':recovery_gate(),'benchmark':benchmark_sf2()}
    prefixes={'lp64_tiny':'lp64_tiny_','callback_tiny':'callback_tiny_','high_order':'high_order_','high_callback':'high_callback_','sf2':'corrected_sf2_',
              'sampling':'integer_sampling_','recovery':'recovery_','benchmark':'benchmark_sf2_'}
    gates={kind:descriptor((OUTPUT/'corrected_sf1_6c34ba3b7ba3246b' if kind=='sf1' else OUTPUT/(prefixes[kind]+native.object_sha(record['binding'])[:16]))/'receipt.json') for kind,record in records.items()}
    for kind,description in gates.items():check_gate(kind,description)
    if sources!={p.relative_to(ROOT).as_posix():native.digest(p) for p in controller.source_paths()}:raise ValueError('Source changed during gate sealing')
    tests={p.relative_to(ROOT).as_posix():native.digest(p) for p in [ROOT/'code/tests/test_full_ssb_native_v2.py',ROOT/'code/tests/test_full_ssb_native_v2_stream.py',ROOT/'code/tests/test_full_ssb_native_v2_formal.py']}
    ready={'schema':'ssb_native_v2_readiness_v1','status':'READY_FOR_INDEPENDENT_REVIEW','sources_sha256':sources,'tests_sha256':tests,'gates':gates,
           'sf1_sampling_scope':'SF1 used p=1 before integer-sampler output-only refinement; SF2 uses the final exact-cutoff build. Both retain-all gates cover every fact field and13 SQL sums.',
           'estimated_sf500_stream_seconds_linear':records['benchmark']['estimated_sf500_stream_seconds_linear'],
           'estimated_sf500_plus_dimension_seconds_range':records['benchmark']['estimated_sf500_plus_dimension_seconds_range']}
    home=OUTPUT/'readiness';home.mkdir(parents=True,exist_ok=True)
    if (home/'readiness.json').exists():
        if read_json(home/'readiness.json')!=ready:raise ValueError('Readiness already frozen; use a new explicit version instead of overwriting')
    else:native.atomic(home/'readiness.json',ready);native.atomic(home/'readiness_seal.json',{'sha256':native.digest(home/'readiness.json')})
    review={'schema':'ssb_native_v2_review_plan_v1','status':'REQUIRES_PARENT_REVIEW','readiness':descriptor(home/'readiness.json'),
            'target':{'scale':500,'orders':750000000,'shards':4000,'sample_seed':20261030,'sample_target':10000000,
                      'requested_probability_numerator':REQUESTED_NUMERATOR,'requested_probability_denominator':REQUESTED_DENOMINATOR,
                      'actual_cutoff':FORMAL_CUTOFF,'effective_probability_denominator':1<<64,'author_rows':AUTHOR_ROWS,'author_truth_groups':2059},
            'resources':{'minimum_available_ram_bytes':4*GIB,'minimum_free_disk_bytes':8*GIB,'combined_ssb_budget_bytes':16*GIB,
                         'reason':'Preserve failed4.20GiB, corrected dims/sample, bounded gate temporaries and later HDF. Previous10GiB failed plan stays unchanged.'},
            'data_directory':str(ROOT/'data/ssb/sf500_native_v2'),'output_directory':str(OUTPUT/'formal500'),
            'final_report':str(FINAL),'author_raw_sha_published':False}
    path=OUTPUT/'formal_review_plan.json'
    if path.exists():
        if read_json(path)!=review:raise ValueError('Review plan already frozen; explicit new version required')
    else:native.atomic(path,review);native.atomic(OUTPUT/'formal_review_plan_seal.json',{'sha256':native.digest(path)})
    return {'status':'READY_FOR_INDEPENDENT_REVIEW','review_plan':str(path),'review_plan_sha256':native.digest(path),'readiness_sha256':native.digest(home/'readiness.json')}


def verify_readiness(path=OUTPUT/'readiness/readiness.json'):
    """Read-only; this never invokes gate/build/generation functions."""
    path=Path(path);record=read_json(path)
    if read_json(path.with_name('readiness_seal.json'))!={'sha256':native.digest(path)} or record.get('schema')!='ssb_native_v2_readiness_v1' or record.get('status')!='READY_FOR_INDEPENDENT_REVIEW':raise ValueError('Readiness self seal/status changed')
    expected={p.relative_to(ROOT).as_posix():native.digest(p) for p in controller.source_paths()}
    if record['sources_sha256']!=expected:raise ValueError('Readiness exact source/runtime inventory changed')
    tests={str(Path('code/tests')/name).replace('\\','/'):native.digest(ROOT/'code/tests'/name) for name in ['test_full_ssb_native_v2.py','test_full_ssb_native_v2_stream.py','test_full_ssb_native_v2_formal.py']}
    if record['tests_sha256']!=tests:raise ValueError('Readiness test sources changed')
    if set(record['gates'])!={'lp64_tiny','callback_tiny','high_order','high_callback','sf1','sf2','sampling','recovery','benchmark'}:raise ValueError('Readiness exact gate inventory changed')
    gates={kind:check_gate(kind,value) for kind,value in record['gates'].items()}
    if gates['sf1']['rows']!=6001215 or gates['callback_tiny']['rows']!=6005 or gates['sf2']['scale']!=2:raise ValueError('Gate population scope changed')
    if gates['sf2']['binding']['callback_binding']!=gates['benchmark']['binding']['plan']['binding']['native_build_binding']:raise ValueError('SF2 golden is not the benchmark native build')
    controller.check_plan(gates['benchmark']['binding']['plan']);controller.check_plan(gates['recovery']['binding']['plan'])
    return {'status':'READY_FOR_INDEPENDENT_REVIEW','readiness_sha256':native.digest(path),'gates':9,'estimated_sf500_stream_seconds_linear':record['estimated_sf500_stream_seconds_linear']}


def budget_gate():
    value=ssb_bytes()
    if value>16*GIB:raise ValueError('Combined SSB16GiB budget exceeded; preserve evidence and stop: '+str(value))
    if shutil.disk_usage(ROOT).free<GIB:raise ValueError('Less than1GiB free during the bounded stream')
    return value


def verify_review_plan(expected_sha,path=OUTPUT/'formal_review_plan.json'):
    path=Path(path)
    if native.digest(path)!=expected_sha or read_json(path.with_name('formal_review_plan_seal.json'))!={'sha256':expected_sha}:raise ValueError('Review plan is not the explicitly approved digest')
    plan=read_json(path)
    if plan.get('schema')!='ssb_native_v2_review_plan_v1' or plan['target']!={'scale':500,'orders':750000000,'shards':4000,'sample_seed':20261030,'sample_target':10000000,
       'requested_probability_numerator':REQUESTED_NUMERATOR,'requested_probability_denominator':REQUESTED_DENOMINATOR,'actual_cutoff':FORMAL_CUTOFF,
       'effective_probability_denominator':1<<64,'author_rows':AUTHOR_ROWS,'author_truth_groups':2059}:raise ValueError('Reviewed scientific target differs')
    if (plan['data_directory'],plan['output_directory'],plan['final_report'])!=(str(ROOT/'data/ssb/sf500_native_v2'),str(OUTPUT/'formal500'),str(FINAL)):raise ValueError('Reviewed paths differ')
    validate_descriptor(plan['readiness']);verify_readiness(plan['readiness']['path']);return plan


def training_processes():
    script="Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'full_mscn(_rebuilt)?\\.py|full_training(_guard)?\\.py|full_ssb_model\\.py.*formal-all' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result=subprocess.check_output(['powershell','-NoProfile','-Command',script],text=True).strip()
    return json.loads(result) if result else []


DIM_FILES={'lp64/dimension_seeds.tsv','lp64/process.json','lp64/process.sh','temporary_manifest.json','temporary_manifest_seal.json','external_artifacts.json','old_dimension_comparison.json'}


def verify_dimensions(home,review_sha):
    home=Path(home);record=read_json(home/'receipt.json')
    if record['binding']['review_plan_sha256']!=review_sha:raise ValueError('Dimension review binding differs')
    residual={name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl'] if (home/'lp64'/name).exists()}
    if {Path(item['path']).name for item in record['cleanup_failures']}!=residual:raise ValueError('Dimension cleanup residual accounting differs')
    native.strict_receipt(home,record['binding'],DIM_FILES|{'lp64/'+name for name in residual})
    temporary=read_json(home/'temporary_manifest.json')
    if read_json(home/'temporary_manifest_seal.json')!={'sha256':native.digest(home/'temporary_manifest.json')}:raise ValueError('Dimension temporary evidence seal differs')
    for name in residual:validate_descriptor(temporary['lp64_full_dimension_temporaries'][name])
    descriptions=read_json(home/'external_artifacts.json')
    if set(descriptions)!={'customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json'}:raise ValueError('Dimension external inventory differs')
    for description in descriptions.values():validate_descriptor(description)
    expected={'customer.tbl':15000000,'supplier.tbl':1000000,'part.tbl':1800000,'date.tbl':2556}
    if {name:descriptions[name]['rows'] for name in expected}!=expected:raise ValueError('Dimension scale/row counts differ')
    return record


def prepare_dimensions(data_directory,home,review_sha):
    """Corrected stock constructors, all LP64 fields and effective Seed traces."""
    home=Path(home);data=Path(data_directory);directory=data/'dimensions'
    if (home/'receipt.json').exists():return verify_dimensions(home,review_sha)
    home.mkdir(exist_ok=False);native.atomic(home/'lifecycle.json',{'status':'RUNNING','review_plan_sha256':review_sha})
    started=time.perf_counter()
    try:
        data.mkdir(exist_ok=False);directory.mkdir();reference=home/'lp64';reference.mkdir()
        windows=native.dimension_build();lp64=native.dimension_build(True);toolchain=native.setup_cygwin()
        binding={'review_plan_sha256':review_sha,'windows_dimension_binding':windows['binding'],'lp64_dimension_binding':lp64['binding']}
        native.command([windows['executable'],'500',native.VENDOR/'dists.dss'],directory,directory/'process.json')
        native.cygwin_run([lp64['executable'],'500',native.VENDOR/'dists.dss'],reference,reference/'process.json',toolchain)
        comparison={};temporary={};old_comparison={}
        for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv']:
            left=hashlib.sha256();right=hashlib.sha256();rows=0
            with (directory/name).open('rb') as a,(reference/name).open('rb') as b:
                for x,y in zip_longest(a,b):
                    if x is None or y is None or x.rstrip(b'\r\n')!=y.rstrip(b'\r\n'):raise ValueError('SF500 LP64 dimension field/Seed trajectory differs: '+name+' row'+str(rows))
                    left.update(x.rstrip(b'\r\n')+b'\n');right.update(y.rstrip(b'\r\n')+b'\n');rows+=1
            comparison[name]={'rows':rows,'normalized_sha256':left.hexdigest(),'lp64_normalized_sha256':right.hexdigest(),'all_fields_equal':True}
            if name.endswith('.tbl'):
                temporary[name]=descriptor(reference/name,True)
                old=ROOT/'data/ssb/sf500_paper/dimensions'/name;changed_address=0;old_rows=0
                with (directory/name).open('rb') as a,old.open('rb') as b:
                    for x,y in zip_longest(a,b):
                        if x is None or y is None:raise ValueError('Old/new dimension row counts differ')
                        xf=x.rstrip(b'\r\n').rstrip(b'|').split(b'|');yf=y.rstrip(b'\r\n').rstrip(b'|').split(b'|')
                        if name in ['customer.tbl','supplier.tbl']:
                            changed_address+=xf[2]!=yf[2];xf=xf[:2]+xf[3:];yf=yf[:2]+yf[3:]
                        if xf!=yf:raise ValueError('Unexpected old/new non-address dimension difference: '+name+' row'+str(old_rows))
                        old_rows+=1
                old_comparison[name]={'old':descriptor(old,True),'rows':old_rows,'changed_addresses':changed_address,'other_fields_equal':True}
        external={name:descriptor(directory/name,name.endswith('.tbl')) for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json']}
        native.atomic(home/'external_artifacts.json',external);native.atomic(home/'old_dimension_comparison.json',old_comparison)
        native.atomic(home/'temporary_manifest.json',{'lp64_full_dimension_temporaries':temporary,'comparison':comparison,
           'disposition':'Remove only these new temporary full LP64 .tbl files after this sealed byte/field evidence; preserve failed old dimensions.'})
        native.atomic(home/'temporary_manifest_seal.json',{'sha256':native.digest(home/'temporary_manifest.json')})
        cleanup=[]
        for name in temporary:
            try:(reference/name).unlink()
            except OSError as error:cleanup.append({'path':str(reference/name),'error':repr(error),'disposition':'Retained; no alternate deletion mechanism'})
        # Retained failed cleanup is a non-scientific space item, explicitly
        # included in the receipt rather than making valid dimensions TAINTED.
        required=DIM_FILES|{'lp64/'+Path(item['path']).name for item in cleanup}
        budget_gate()
        result=native.publish_receipt(home,{'status':'PASS','binding':binding,'all_four_dimensions_all_fields_equal_lp64':True,
              'all48_valid_seed_trajectories_equal':True,'comparison':comparison,'seconds':time.perf_counter()-started,'cleanup_failures':cleanup},required)
        return result
    except BaseException as error:
        native.atomic(home/'lifecycle.json',{'status':'TAINTED','review_plan_sha256':review_sha,'error':repr(error)});raise


def run_formal(review_sha,memory_approved=False,resume=False):
    if not memory_approved:raise ValueError('Formal resource acknowledgement flag is required; root has authorized it subject to real probes')
    review=verify_review_plan(review_sha);probes=resources();busy=training_processes()
    if busy:raise ValueError('Other model training has not ended: '+repr(busy))
    budget_gate();global_home=OUTPUT/'formal_execution_lock';global_home.mkdir(exist_ok=True)
    with controller.namespace_lock(global_home):
        home=Path(review['output_directory']);data=Path(review['data_directory'])
        if not resume:
            home.mkdir(exist_ok=False);native.atomic(home/'lifecycle.json',{'status':'RUNNING','review_plan_sha256':review_sha})
            native.atomic(home/'resources.json',dict(probes,training_processes=busy,combined_ssb_bytes_before=ssb_bytes()))
        else:
            life=read_json(home/'lifecycle.json')
            if life['review_plan_sha256']!=review_sha or life['status'] not in ['RUNNING','FINAL_PASS']:raise ValueError('Formal namespace is TAINTED or belongs to another reviewed plan')
            if FINAL.exists():return verify_final()
        try:
            prepare_dimensions(data,home/'dimensions',review_sha);verify_dimensions(home/'dimensions',review_sha)
            stream_home=home/'stream'
            if (stream_home/'plan.json').exists():plan=read_json(stream_home/'plan.json')
            else:
                plan=controller.stream_plan('500',750000000,4000,data/'dimensions',20261030,review['target']['actual_cutoff'])
                plan['binding']['formal_review_plan_sha256']=review_sha;plan['binding'].pop('source_id')
                plan['binding']['source_id']=native.object_sha(plan['binding'])
            if plan['binding'].get('formal_review_plan_sha256')!=review_sha:raise ValueError('Materialized stream plan belongs to another review')
            result=controller.stream(plan,stream_home,resume=resume and stream_home.exists(),data_directory=data,budget_check=budget_gate)
            if result['status']!='STREAM_COMPLETE_NOT_AUTHOR_VERIFIED':raise ValueError('Formal stream did not complete')
            verified=publish_final(plan,stream_home,data/'lineorder_sampled.csv',OUTPUT/'formal_review_plan.json',home/'dimensions/receipt.json')
            native.atomic(home/'lifecycle.json',{'status':'FINAL_PASS','review_plan_sha256':review_sha,'final_report_sha256':native.digest(FINAL)})
            return verify_final()
        except BaseException as error:
            native.atomic(home/'lifecycle.json',{'status':'TAINTED','review_plan_sha256':review_sha,'error':repr(error)});raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('freeze-gates');sub.add_parser('verify-readiness');sub.add_parser('verify-final')
    run=sub.add_parser('run');run.add_argument('--review-plan-sha256',required=True);run.add_argument('--formal-memory-approved',action='store_true');run.add_argument('--resume',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='freeze-gates':result=freeze_gates()
    elif args.command=='verify-readiness':result=verify_readiness()
    elif args.command=='verify-final':result=verify_final()
    else:result=run_formal(args.review_plan_sha256,args.formal_memory_approved,args.resume)
    print(json.dumps(result,indent=2,allow_nan=False));return 0


if __name__=='__main__':raise SystemExit(main())
