"""Draft, fail-closed I/O bridge for a future author-truth-matching native SSB.

No formal execution is enabled until the native contract and a new bridge version
are reviewed. Pure validation/draft planning never imports the model stack.
"""
import sys
sys.dont_write_bytecode=True
import argparse
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import pickletools
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUTPUT_REL='output/full/ssb/native_v2_models'
RESULT_REL='output/full/results/ssb_native_v2_model_aqp_ci.json'
GEN_RESULT_REL='output/full/results/ssb_native_v2.json'
SQL_REL='code/benchmarks/ssb/sql/aqp_queries.sql'
TRUTH_REL='code/benchmarks/ssb/ground_truth_500GB.pkl'
SQL_SHA='37bf231b917f5c5995decb576566596acfc37722ed08e554252e68e91f839e32'
TRUTH_SHA='14ff6ea9cf4d8b8e0b0f05066e8854cbb5f4e186715f67bf5d528f27722f0d1c'
SOURCE_PINS_SHA='c2d5be39dabd3903dfa0a010ce09e0590b275f59a5bf654dd18c3840001d5816'
N=3000028242
GIB=1024**3
FINAL_RECEIPT_INTERFACE_FROZEN=False
GENERATOR_CLOSURE_INTERFACE_FROZEN=False
FORMAL_PUBLICATION_REVIEW_COMPLETE=False
NATIVE_API_SOURCE_PINS={  # frozen candidate; these pins do not open execution
 'code/full_ssb_native_v2.py':'9dc407892acaa14042cf4c9645b455747efbbba46d63fb8385946ee30a60eaeb',
 'code/full_ssb_native_v2_stream.py':'ddcd3b3d387b8b6a28324ceb89b39f1b0911db8f4130ccf5dbd4567424e422b1',
 'code/full_ssb_native_v2_formal.py':'52de0f43faf554a761f8dacca3cee5e9d919113402743aacf1a211ddcd882b40'}
NATIVE_READINESS_SHA='0bc498c29664ef4f44692ef08e61d4fe4734d73b904be0a8a581a74ba9ac00e1'
NATIVE_REVIEW_PLAN_SHA='da3d91cfcc02e8d0934b9925c2a77c88c7adac834eb043f2bb1c2a138cc0dd34'
FORMAL_CUTOFF=3333*(1<<64)//1000000
MINGW_TREE_PIN='91ee6db0baa926fe4ae966c790504b29e43097988bdf6a989c58593ba1c7c081'
CYGWIN_TREE_PIN='72898942c4a6d9b37ebe230ba7c092604ba95bac2f7f862cf983d96dc933dce5'
CYGWIN_LOCK_PIN='335fba5f9eb8c2ad6c465f96bd55401811898c9d1a27ce730d9e24c350f65383'
MINGW_ARCHIVE_PIN='cea23fc56a5e61457492113a8377c8ab0c42ed82303fcc454ccd1963a46f8ce1'
FROZEN={
 'code/full_ssb_model.py':'5b6d31a15884cf09ba29c19d3c49db2c5a79d82a5fba40e4aa1d7e714f23aa27',
 'code/full_ssb_guard.py':'fc19133d00216ceac72198eed747107d81e82f224804c69440290931a201f842',
 'code/full_ssb_replay.py':'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab'}
DIMENSIONS={'customer':(15000000,8),'supplier':(1000000,7),'part':(1800000,9),'date':(2556,17)}
GROUP_WIDTHS=(0,0,0,2,2,2,3,3,3,3,2,3,3)
QUERY_NAMES=('S1.1','S1.2','S1.3','S2.1','S2.2','S2.3','S3.1','S3.2','S3.3','S3.4','S4.1','S4.2','S4.3')
TABLES=('lineorder','dwdate','customer','part','supplier')
MODEL=dict(samples_per_spn=1000000,ensemble_strategy='single',rdc_threshold=.3,
           min_slice_fraction=.01,seed=1,post_sampling_factor=10,rdc_jobs=1)


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(path):
    def pairs(items):
        out={}
        for key,value in items:
            require(key not in out,'duplicate JSON key');out[key]=value
        return out
    def invalid(value):raise ValueError('nonfinite JSON value: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


@contextmanager
def controller_lock(path):
    """Kernel lock: exactly one producer; crashes release the OS lock, not state."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    stream=path.open('a+b');acquired=False
    try:
        if stream.seek(0,2)==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:raise ValueError('another formal controller owns this lock') from error
        acquired=True
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()


def formal_transaction(home,binding,producer,validator,lock_path=None,kind='FORMAL'):
    """Durable whole-FORMAL publication, independent of child stage receipts."""
    home=Path(home);home.mkdir(parents=True,exist_ok=True)
    with controller_lock(lock_path or home/'controller.lock'):
        state_path=home/'lifecycle.json';receipt_path=home/'receipt.json'
        if state_path.exists():
            state=read(state_path)
            require(state.get('binding')==binding,'formal namespace binding changed; new namespace required')
            if state.get('status')!='PASS':
                atomic(state_path,dict(status='TAINTED',kind=kind,binding=binding,reason='previous RUNNING/TAINTED formal namespace'))
                raise ValueError('TAINTED formal namespace cannot automatically resume')
            try:
                require(receipt_path.is_file() and digest(receipt_path)==state.get('receipt_sha256'),'formal PASS receipt missing/changed')
                receipt=read(receipt_path)
                require(receipt.get('status')=='PASS' and receipt.get('kind')==kind and receipt.get('binding')==binding,'formal PASS receipt binding changed')
                validator(receipt['result']);return receipt['result']
            except BaseException as error:
                atomic(state_path,dict(status='TAINTED',kind=kind,binding=binding,reason=repr(error)));raise
        require(not receipt_path.exists(),'orphan formal receipt cannot be adopted')
        atomic(state_path,dict(status='RUNNING',kind=kind,binding=binding))
        try:
            result=producer();validator(result)
            atomic(receipt_path,dict(status='PASS',kind=kind,binding=binding,result=result))
            atomic(state_path,dict(status='PASS',kind=kind,binding=binding,receipt_sha256=digest(receipt_path)))
            return result
        except BaseException as error:
            atomic(state_path,dict(status='TAINTED',kind=kind,binding=binding,reason=repr(error)));raise


def relative_path(name):
    require(isinstance(name,str) and bool(name) and '\\' not in name and ':' not in name,'noncanonical artifact path')
    require(not PurePosixPath(name).is_absolute() and all(p not in ('','..','.') for p in name.split('/')),'unsafe artifact path')
    return name


def descriptor(entry):
    relative_path(entry['path'])
    require(type(entry['bytes']) is int and entry['bytes']>0 and re.fullmatch('[a-f0-9]{64}',entry['sha256']) is not None,'invalid artifact descriptor')
    if 'rows' in entry:
        require(type(entry['rows']) is int and entry['rows']>0 and type(entry.get('fields')) is int and entry['fields']>0,'invalid physical rows/fields')
    return entry


def verify_artifact(entry,root=ROOT):
    descriptor(entry);root=Path(root).resolve();path=(root/entry['path']).resolve()
    require(root in path.parents and path.is_file(),'artifact missing/outside project: '+entry['path'])
    require(path.stat().st_size==entry['bytes'],'artifact byte count changed: '+entry['path'])
    if 'rows' not in entry:
        require(digest(path)==entry['sha256'],'artifact hash changed: '+entry['path']);return dict(entry)
    h=hashlib.sha256();rows=0
    with path.open('rb') as stream:
        for raw in stream:
            h.update(raw);row=raw.rstrip(b'\r\n');require(bool(row),'blank raw SSB record')
            fields=row.count(b'|')+1
            if row.endswith(b'|') and fields==entry['fields']+1:fields-=1
            require(fields==entry['fields'],'physical raw field count changed: '+entry['path']);rows+=1
    require(rows==entry['rows'] and h.hexdigest()==entry['sha256'],'artifact hash/physical row count changed: '+entry['path'])
    return dict(entry)


def truth_map(records):
    require(isinstance(records,list) and len(records)==2059,'all2059 integer truth groups required')
    result={}
    for row in records:
        q=row['query_no'];group=row['group'];value=row['value']
        require(type(q) is int and 0<=q<13 and isinstance(group,list) and len(group)==GROUP_WIDTHS[q], 'truth query/group shape changed')
        require(all(isinstance(x,str) and not any(c in x for c in '\t\n\r\0') for x in group) and type(value) is int,'truth must use canonical strings/exact integers')
        key=(q,tuple(group));require(key not in result,'duplicate integer truth group');result[key]=value
    require({q for q,_ in result}==set(range(13)),'all13 truth identities required')
    return result


def native_descriptor(entry,root=ROOT,fields=None):
    """Normalize the actual native v1 absolute descriptor without changing data."""
    root=Path(root).resolve();path=Path(entry['path'])
    require(path.is_absolute(),'native v1 artifact path must be absolute')
    path=path.resolve();require(root in path.parents,'native project artifact outside project')
    result=dict(path=path.relative_to(root).as_posix(),bytes=entry['bytes'],sha256=entry['sha256'])
    if fields is not None:result.update(rows=entry['rows'],fields=fields)
    descriptor(result);return result


def validate_contract(body,author_groups,checkpoint=None,plan=None,root=ROOT):
    """Actual native v1 metadata; never a physical-source acceptance shortcut."""
    require(body.get('schema')=='ssb_native_v2_final_v1' and body.get('status')=='PASS_AUTHOR_TRUTHS'
            and body.get('complete') is True and body.get('paper_population_row_count_and_13_truths_match') is True,
            'complete final native generation PASS with all author truths required')
    require({'N','population_rows','canonical_truth','raw_sample','dimensions','plan','checkpoint','artifacts','sampling','source_id','sample_rows'}<=set(body),'actual native v1 receipt fields required; obsolete draft aliases refused')
    require(type(body['N']) is int and body['N']==N and type(body['population_rows']) is int and body['population_rows']==N,'author population row count required')
    require(re.fullmatch('[a-f0-9]{64}',body['source_id']) is not None,'native v1 source identity must be64hex')
    require(type(body['sample_rows']) is int and 1000000<=body['sample_rows']<20000000,'sample outside proven formal preparation domain')
    require(truth_map(body['canonical_truth'])==truth_map(author_groups),'all2059 author integer truth values must match')
    sample=native_descriptor(body['raw_sample'],root,17)
    require(sample['path']=='data/ssb/sf500_native_v2/lineorder_sampled.csv' and sample['rows']==body['sample_rows'],'new native fact sample path/count required')
    require(set(body['dimensions'])==set(DIMENSIONS),'complete four dimensions required')
    for name,(rows,width) in DIMENSIONS.items():
        entry=native_descriptor(body['dimensions'][name],root,width)
        require(entry['rows']==rows,'native dimension physical row receipt differs')
    artifacts=body['artifacts'];require(isinstance(artifacts,dict) and {'plan','checkpoint','raw_sample','queries','author_truth'}<=set(artifacts),'actual flat native artifact map required')
    for role in ('plan','checkpoint'):
        require(native_descriptor(body[role],root)['path'].startswith('output/full/ssb/native_v2/') and body[role]==artifacts[role],'native physical plan/checkpoint descriptor differs')
    require(native_descriptor(artifacts['queries'],root)['path']==SQL_REL and native_descriptor(artifacts['author_truth'],root)['path']==TRUTH_REL,'fixed native SQL/author truth artifact paths required')
    sampling=body['sampling'];cutoff=sampling['actual_cutoff']
    require(type(cutoff) is int and 0<cutoff<=2**64 and type(sampling['sample_seed']) is int and sampling['sample_seed']>=0,'actual64bit sample cutoff/seed required')
    require(all(type(sampling.get(k)) is int for k in ('probability_numerator','probability_denominator','normalizer_numerator',
            'normalizer_denominator','requested_numerator','requested_denominator')),'sampling fractions/normalizer must remain exact integers')
    probability=Fraction(cutoff,2**64);normalizer=Fraction(body['sample_rows']*2**64,cutoff)
    require(cutoff==FORMAL_CUTOFF and sampling.get('requested_numerator')==3333 and sampling.get('requested_denominator')==1000000,
            'formal schema sampling must request exact0.003333, then apply integer cutoff')
    require(type(sampling['probability_numerator']) is int and sampling['probability_numerator']==cutoff
            and type(sampling['probability_denominator']) is int and sampling['probability_denominator']==2**64,
            'effective sampling probability must equal exact cutoff/2**64')
    require(sampling['normalizer_numerator']==body['sample_rows']*2**64 and sampling['normalizer_denominator']==cutoff
            and sampling['normalizer_n_over_p']==float(normalizer),'actual retained n/p receipt differs')
    require(sampling.get('effective_probability')==float(probability),'native descriptive effective probability missing/differs')
    require(isinstance(checkpoint,dict) and isinstance(plan,dict),'physical native checkpoint and plan bodies required')
    require(plan.get('schema')=='ssb_native_v2_stream_plan_v1' and checkpoint.get('schema')=='ssb_native_v2_checkpoint_v1','actual native stream/checkpoint schemas required')
    binding=plan['binding'];copy=dict(binding);source_id=copy.pop('source_id')
    require(source_id==body['source_id']==value_hash(copy) and checkpoint['binding']==binding,'actual native source/binding identity differs')
    require(binding['scale']=='500' and binding['shards']==4000 and binding['total_orders']==750000000
            and binding['actual_cutoff']==cutoff and binding['sample_seed']==sampling['sample_seed'] and binding['dimensions']==body['dimensions'], 'actual formal native plan settings differ')
    committed=checkpoint['committed_shards']
    require(checkpoint['complete'] is True and type(checkpoint['next_shard']) is int and checkpoint['next_shard']==4000
            and len(committed)==4000 and len(plan['ranges'])==4000 and all(type(s['shard']) is int for s in committed)
            and [s['shard'] for s in committed]==list(range(4000)),'complete actual0based4000-shard checkpoint required')
    next_order=1
    for shard,expected in zip(committed,plan['ranges']):
        require(type(shard['first_order']) is int and shard['first_order']==next_order and type(shard['orders']) is int and shard['orders']>0
                and [shard['first_order'],shard['orders']]==expected,'checkpoint order range gap/overlap')
        next_order+=shard['orders']
    require(next_order==750000001 and type(checkpoint['rows']) is int and checkpoint['rows']==N
            and type(checkpoint['sample_rows']) is int and checkpoint['sample_rows']==body['sample_rows']
            and checkpoint['sample_sha256']==sample['sha256'] and checkpoint['sample_bytes']==sample['bytes']
            and checkpoint['aggregates']==body['canonical_truth'], 'checkpoint source/sample/final truth binding differs')
    return dict(population_rows=N,sample_rows=body['sample_rows'],truth_groups=2059,source_id=body['source_id'],
        probability=dict(numerator=probability.numerator,denominator=probability.denominator),fact_normalizer=dict(numerator=normalizer.numerator,denominator=normalizer.denominator),
        scope='Author row count and13 SQL truth values match; no claim of all original row bytes matching author')


def load_author_groups(root=ROOT):
    import pickle
    root=Path(root);require(digest(root/TRUTH_REL)==TRUTH_SHA,'pinned author pickle changed before load')
    with (root/TRUTH_REL).open('rb') as stream:truth=pickle.load(stream)
    require(set(truth)==set(range(13)),'author query set changed')
    records=[dict(query_no=q,group=[str(x) for x in row[:-1]],value=row[-1]) for q,rows in truth.items() for row in rows]
    truth_map(records);return records


def verify_generation(receipt_path=None,expected_receipt_sha256=None,root=ROOT):
    """Full physical source gate. Caller must supply root-reviewed final receipt SHA."""
    root=Path(root).resolve();receipt_path=Path(receipt_path or root/GEN_RESULT_REL)
    require(receipt_path.is_file(),'final native source receipt missing; generation/interface is not complete')
    require(re.fullmatch('[a-f0-9]{64}',expected_receipt_sha256 or '') is not None,'root-reviewed final receipt SHA required')
    require(receipt_path.resolve()==(root/GEN_RESULT_REL).resolve() and digest(receipt_path)==expected_receipt_sha256,'final native receipt path/hash differs')
    body=read(receipt_path)
    # Reject status/rows before touching any potentially growing raw artifact.
    require(body.get('status')=='PASS_AUTHOR_TRUTHS' and body.get('complete') is True
            and body.get('N')==N and body.get('paper_population_row_count_and_13_truths_match') is True,'complete final author generation PASS required before raw input access')
    require(GENERATOR_CLOSURE_INTERFACE_FROZEN,'native source/runtime closure interface is not frozen')
    require(set(NATIVE_API_SOURCE_PINS)=={'code/full_ssb_native_v2.py','code/full_ssb_native_v2_stream.py','code/full_ssb_native_v2_formal.py'},'reviewed exact native readonly API source pins missing')
    for path,sha in NATIVE_API_SOURCE_PINS.items():require(digest(root/path)==sha,'reviewed native final verifier source changed')
    require(digest(root/'output/full/ssb/native_v2/readiness/readiness.json')==NATIVE_READINESS_SHA,'frozen native readiness changed')
    require(digest(root/'output/full/ssb/native_v2/formal_review_plan.json')==NATIVE_REVIEW_PLAN_SHA,'frozen native review plan changed')
    require(root==ROOT,'real native API requires the project root')
    import full_ssb_native_v2_formal as native_final
    # Only the owner's reviewed read-only verifier may be called; never any
    # constructor/build/adoption/stream entry. It also requires FINAL_PASS.
    checked=native_final.verify_final(receipt_path)
    require(checked['status']=='PASS_AUTHOR_TRUTHS' and checked['report_sha256']==expected_receipt_sha256,'native owner final gate differs')
    checkpoint=read(body['checkpoint']['path']);plan=read(body['plan']['path'])
    require(plan['binding']['formal_review_plan_sha256']==NATIVE_REVIEW_PLAN_SHA,'native source belongs to another review plan')
    result=validate_contract(body,load_author_groups(root),checkpoint,plan,root);physical=[]
    for role,entry in body['artifacts'].items():
        if role.startswith('platform_runtime/'):
            item=artifact_record(entry['path'],root)
            require(item.get('external_scope')=='windows_direct_native_import' and item['sha256']==entry['sha256'] and item['bytes']==entry['bytes'],'native direct Windows import descriptor differs')
        else:
            item=native_descriptor(entry,root)
        physical.append(item)
    require(digest(root/SQL_REL)==SQL_SHA and digest(root/TRUTH_REL)==TRUTH_SHA,'pinned author SQL/truth changed')
    physical.append(verify_artifact(native_descriptor(body['raw_sample'],root,17),root))
    for name,(_,width) in DIMENSIONS.items():physical.append(verify_artifact(native_descriptor(body['dimensions'][name],root,width),root))
    # These are required independent final guards/receipts, not mere contents of
    # the source report's flat artifact list. Native owner freezes exact paths.
    for key in ('review_plan','dimension_receipt'):physical.append(verify_artifact(native_descriptor(body[key],root),root))
    physical.extend(native_final_boundary(body,checked,plan,root))
    physical.append(artifact_record(receipt_path.with_name(receipt_path.stem+'_seal.json'),root))
    require(digest(receipt_path)==expected_receipt_sha256,'final native source changed during verification')
    result.update(receipt_path=GEN_RESULT_REL,receipt_sha256=expected_receipt_sha256,
                  canonical_truth_sha256=value_hash(body['canonical_truth']),physical_artifacts=physical)
    return result


def native_final_boundary(body,checked,plan,root=ROOT):
    """Seal consumed stream/final guards absent from the frozen native flat map."""
    root=Path(root);home=Path(body['plan']['path']).parent
    final_path=home.parent/'lifecycle.json';final=read(final_path);stream=read(home/'lifecycle.json')
    require(checked['review_plan']==body['review_plan'],'native checked review-plan descriptor differs')
    expected=artifact_record(final_path,root)
    require(native_descriptor(checked['final_guard'],root)==expected,'native outer final guard descriptor differs')
    require(final.get('status')=='FINAL_PASS' and final.get('final_report_sha256')==checked['report_sha256']
            and final.get('review_plan_sha256')==plan['binding']['formal_review_plan_sha256'],'native outer FINAL_PASS/report/review binding differs')
    seconds=stream.get('seconds');peak=stream.get('peak_native_working_set_bytes')
    require(stream.get('status')=='STREAM_COMPLETE' and stream.get('plan_sha256')==value_hash(plan),'native stream lifecycle/plan differs')
    require(type(seconds) in (int,float) and math.isfinite(seconds) and seconds>=0 and type(peak) is int and peak>=0
            and seconds==body['stream_seconds'] and peak==body['peak_native_working_set_bytes'],'native stream timing/peak binding differs')
    return [expected,artifact_record(home/'lifecycle.json',root),artifact_record(home/'native.stderr.log',root)]


def frozen_sources(root=ROOT):
    root=Path(root)
    for path,sha in FROZEN.items():require(digest(root/path)==sha,'frozen model/guard/replay source changed')
    return dict(FROZEN)


def base_python_files(base_prefix,prefix,base_executable,root=ROOT):
    root=Path(root).resolve();base_prefix=Path(base_prefix).resolve();prefix=Path(prefix).resolve()
    require(root in base_prefix.parents and root in prefix.parents,'actual base/venv Python must remain project-local')
    paths={Path(base_executable).resolve(),prefix/'pyvenv.cfg'}
    paths.update(p for p in base_prefix.rglob('*') if p.is_file() and p.suffix.lower() in ('.exe','.dll','.pyd'))
    result={}
    for path in sorted(paths):
        require(root in path.parents and path.is_file(),'actual base Python runtime file missing/outside project')
        result[path.relative_to(root).as_posix()]=digest(path)
    require(any(p.endswith('python38.dll') for p in result) if os.name=='nt' else bool(result),'actual Python base native closure missing')
    return result


def verify_runtime_tree(directory,inventory_sha256,file_count,root=ROOT):
    """Independent fixed inventory pin defeats a re-sealed subset receipt."""
    directory=Path(directory).resolve();root=Path(root).resolve()
    require(root in directory.parents and directory.is_dir(),'project-contained runtime tree required')
    inventory={};records=[]
    for path in sorted(directory.rglob('*')):
        if not path.is_file():continue
        require(root in path.resolve().parents,'runtime alias escaped project')
        sha=digest(path);inventory[path.relative_to(directory).as_posix()]=sha
        records.append(dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=sha))
    require(len(inventory)==file_count and value_hash(inventory)==inventory_sha256,'fixed complete runtime inventory changed/subset')
    return records


def generator_runtime_closure(root=ROOT):
    """Read/hash only; project toolchain inventory plus official package provenance.

    The reviewed extracted-inventory pins supplement the native final receipt.
    They do not claim to seal all transitive Windows operating-system libraries.
    """
    root=Path(root).resolve();lock_path=root/'code/vendor/ssb_native_v2/cygwin.lock.json'
    require(digest(lock_path)==CYGWIN_LOCK_PIN,'fixed official Cygwin package lock changed')
    archive=root/'data/downloads/w64devkit-x64-2.0.0.exe'
    require(digest(archive)==MINGW_ARCHIVE_PIN,'fixed MinGW archive changed')
    records=[artifact_record(archive,root),artifact_record(lock_path,root)]
    records.extend(verify_runtime_tree(root/'.runtime/w64devkit',MINGW_TREE_PIN,5906,root))
    lock=read(lock_path);binding={name:lock[name] for name in ('metadata_sha256','mirror','packages','extraction_policy')}
    identity=value_hash(binding)[:16];evidence=root/'output/full/ssb/native_v2/cygwin'/identity
    receipt=read(evidence/'receipt.json');seal=read(evidence/'receipt_seal.json');life=read(evidence/'lifecycle.json')
    require(receipt['status']==life['status']=='PASS' and receipt['binding']==binding
            and seal['sha256']==life['receipt_sha256']==digest(evidence/'receipt.json')
            and len(receipt['runtime_files_sha256'])==3136 and value_hash(receipt['runtime_files_sha256'])==CYGWIN_TREE_PIN,
            'fixed complete Cygwin source/package/runtime receipt differs')
    require(Path(receipt['directory']).resolve()==(root/'.runtime'/('cygwin_lp64_'+identity)).resolve(),'actual Cygwin runtime root differs')
    records.extend(verify_runtime_tree(receipt['directory'],CYGWIN_TREE_PIN,3136,root))
    for name in ('receipt.json','receipt_seal.json','lifecycle.json','layout_probe.exe'):records.append(artifact_record(evidence/name,root))
    require(digest(evidence/'layout_probe.exe')==receipt['probe_sha256'],'actual LP64 layout oracle executable changed')
    for package in lock['packages'].values():
        relative,size,sha512=package['install'].split();path=root/'data/downloads/ssb_native_v2'/Path(relative).name
        require(path.stat().st_size==int(size),'official Cygwin package bytes changed')
        sha=hashlib.sha512()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(4*1024**2),b''):sha.update(block)
        require(sha.hexdigest()==sha512,'official Cygwin package checksum changed');records.append(artifact_record(path,root))
    return dict(mingw_inventory_sha256=MINGW_TREE_PIN,cygwin_inventory_sha256=CYGWIN_TREE_PIN,
                artifacts=records,scope='Project toolchains plus direct native Windows imports only; not the full transitive operating system')


def dependency_snapshot():
    """Future worker binding: all frozen sources,22 parser files and physical runtime."""
    import full_ssb_guard as guard
    import platform,importlib
    complete=guard.dependencies()
    require(len(complete['sqlparse_sources'])==22,'reviewed22-file parser closure changed')
    package_root=(ROOT/'.venv/Lib/site-packages').resolve();libraries={};module_roots={}
    require(Path(sys.prefix).resolve()==(ROOT/'.venv').resolve(),'actual loaded Python must be the original isolated .venv')
    for name in ('numpy','pandas','scipy','sklearn','joblib','tables','spn','sqlparse','networkx'):
        path=Path(importlib.import_module(name).__file__).resolve()
        require(package_root in path.parents,'actual loaded model package root differs: '+name)
        module_roots[name]=dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path))
    for path in sorted(package_root.rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.dll','.pyd'):libraries[path.relative_to(ROOT).as_posix()]=digest(path)
    require(bool(libraries),'physical model runtime library closure missing')
    return dict(frozen_sources=frozen_sources(),complete=complete,python_executable=dict(path=str(Path(sys.executable).resolve()),sha256=digest(sys.executable)),
                python_base_native_files=base_python_files(sys.base_prefix,sys.prefix,getattr(sys,'_base_executable',sys.executable)),
                actual_module_roots=module_roots,physical_native_libraries=libraries,generator_runtime=generator_runtime_closure(),
                operational_launcher=artifact_record(ROOT/'code/full_ssb_native_model_run.py'),
                python_base_executable=artifact_record(getattr(sys,'_base_executable',sys.executable)),
                platform=platform.platform(),bridge_sha256=digest(__file__))


@contextmanager
def isolated_output(core,directory,root=ROOT):
    require(os.environ.get('DEEPDB_SSB_NATIVE_MODEL_WORKER')=='1','I/O routing requires a fresh dedicated worker')
    base=(Path(root)/OUTPUT_REL).resolve();directory=Path(directory).resolve()
    require(base==directory or base in directory.parents,'new model I/O namespace required')
    original=core.OUTPUT;core.OUTPUT=directory
    try:yield
    finally:core.OUTPUT=original


def check_resources(free_disk_bytes,available_memory_bytes,existing_ssb_bytes,additional_bytes=5*GIB):
    require(free_disk_bytes>=8*GIB,'at least8GiB free disk required')
    require(available_memory_bytes>=4*GIB,'at least4GiB available RAM required')
    require(existing_ssb_bytes>=0 and additional_bytes>=0 and existing_ssb_bytes+additional_bytes<=16*GIB,'projected total SSB storage exceeds16GiB')
    return dict(free_disk_bytes=free_disk_bytes,available_memory_bytes=available_memory_bytes,
                existing_ssb_bytes=existing_ssb_bytes,additional_reserve_bytes=additional_bytes,total_budget_bytes=16*GIB)


def draft_plan():
    return dict(schema='ssb_native_v2_model_plan_draft_v1',status='DRAFT_BLOCKED_PENDING_NATIVE_V2_FINAL_RECEIPT_AND_ROOT_REVIEW',
        executable=False,formal_training_started=False,final_receipt_interface_frozen=FINAL_RECEIPT_INTERFACE_FROZEN,
        generator_closure_interface_frozen=GENERATOR_CLOSURE_INTERFACE_FROZEN,formal_publication_review_complete=FORMAL_PUBLICATION_REVIEW_COMPLETE,
        source_receipt=GEN_RESULT_REL,source_receipt_sha256=None,expected_population_rows=N,required_exact_truth_groups=2059,
        source_contract='ssb_native_v2_final_v1; frozen generator candidate, final population not yet accepted',model=dict(MODEL),
        sampling=dict(requested_numerator=3333,requested_denominator=1000000,actual_cutoff=FORMAL_CUTOFF,probability_denominator=2**64),
        native_candidate=dict(sources=NATIVE_API_SOURCE_PINS,readiness_sha256=NATIVE_READINESS_SHA,review_plan_sha256=NATIVE_REVIEW_PLAN_SHA),
        normalizer='actual retained n / exact effective cutoff probability; never replace learned length with exact N',
        namespaces=dict(output=OUTPUT_REL,result=RESULT_REL),frozen_sources=frozen_sources(),bridge_sha256=digest(__file__),
        resources=dict(total_ssb_budget_bytes=16*GIB,minimum_free_disk_bytes=8*GIB,minimum_available_memory_bytes=4*GIB,additional_reserve_bytes=5*GIB),
        future_routines=['guarded_prepare','guarded_train','guarded_evaluate','sample_moments_native','population_truth_groups'],
        unexecuted=['final native source acceptance','SF500 HDF preparation','SF5001M training','13 model/CI evaluation','independent reverse replay'],
        scope='Prior faulty SF2 gates show algorithm equivalence only; no native data fidelity or author full-row byte identity claim')


def make_schema(body):
    from schemas.ssb.schema import gen_500gb_ssb_schema
    schema=gen_500gb_ssb_schema(str(ROOT/'data/ssb/sf500_native_v2/dimensions/{}.tbl'))
    probability=float(Fraction(body['sampling']['actual_cutoff'],2**64))
    for table in schema.tables:
        source='date' if table.table_name=='dwdate' else table.table_name
        entry=body['raw_sample'] if source=='lineorder' else body['dimensions'][source]
        table.csv_file_location=entry['path'];table.table_size=N if source=='lineorder' else entry['rows']
        table.sample_rate=probability if source=='lineorder' else 1
    return schema


def core_truth_projection(body):
    aggregates={str(q):{} for q in range(13)}
    for row in body['canonical_truth']:aggregates[str(row['query_no'])]['\t'.join(row['group'])]=row['value']
    return dict(rows=N,sample_rows=body['sample_rows'],aggregates=aggregates,
                source_receipt_sha256=body['receipt_sha256'],adapter='canonical integer truth; no arithmetic/rounding')


def artifact_record(path,root=ROOT):
    root=Path(root).resolve();path=Path(path).resolve()
    if root not in path.parents:
        allowed={Path('C:/Windows/System32')/name for name in ('KERNEL32.dll','msvcrt.dll')}
        require(path in {p.resolve() for p in allowed} and path.is_file(),'external artifact is not an allowed direct Windows import')
        return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path),external_scope='windows_direct_native_import')
    require(path.is_file(),'required publication artifact missing: '+str(path))
    return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=digest(path))


def stage_home(directory,kind):
    directory=Path(directory)
    return directory.parent/('.'+directory.name+'_'+kind+'_guard_'+FROZEN['code/full_ssb_guard.py'][:16])


def required_stage_artifacts(report,root=ROOT,author_groups=None):
    """Derive exact stage files from frozen formats; no rglob-as-proof or unpickle.

    Metadata pickle strings are inspected with pickletools only. Models and
    metadata are never deserialized or executed by this read-only inventory.
    """
    root=Path(root).resolve();directory=Path(report['directory']).resolve();files={}
    require(root in directory.parents,'model run outside project')
    def add(path,expected=None):
        item=artifact_record(path,root)
        require(expected is None or item['sha256']==expected,'stage artifact hash changed: '+item['path'])
        files[item['path']]=item;return item
    def outer(path,kind):
        home=stage_home(path,kind.lower());state_path=home/'lifecycle.json';receipt_path=home/'receipt.json'
        add(state_path);receipt_item=add(receipt_path);state=read(state_path);receipt=read(receipt_path)
        require(state.get('status')=='PASS' and state.get('receipt_sha256')==receipt_item['sha256']
                and receipt.get('status')=='PASS' and receipt.get('kind')==kind and state.get('binding')==receipt.get('binding'), 'outer '+kind+' PASS lifecycle/receipt incomplete')
        require(receipt['binding']['dependencies']==report['plan']['dependencies']['complete']
                and receipt['binding']['guard_source_sha256']==FROZEN['code/full_ssb_guard.py'], 'outer '+kind+' source/parser/runtime binding changed')
        return receipt
    prepared=directory/'prepared';pouter=outer(prepared,'PREPARED');partifact=pouter['result']['core_input_artifacts']
    pseal=read(prepared/'seal.json');add(prepared/'seal.json',pouter['result']['core_seal_sha256'])
    recorded=partifact['prepared_files_sha256']
    require(recorded==pseal['files_sha256'] and {'meta_data.pkl','binding.json'}<=set(recorded),'prepared receipt/file inventory differs')
    for name,sha in recorded.items():
        require(Path(name).name==name,'nonlocal prepared file');add(prepared/name,sha)
    require(set(partifact['raw_files'])==set(TABLES),'prepared exact raw table set differs')
    raw_by_name={Path(e['path']).name:e for e in report['inputs']['physical_artifacts']}
    for table in TABLES:
        name='lineorder_sampled.csv' if table=='lineorder' else 'date.tbl' if table=='dwdate' else table+'.tbl'
        require(name in raw_by_name and partifact['raw_files'][table]['sha256']==raw_by_name[name]['sha256']
                and Path(partifact['raw_files'][table]['path']).resolve()==(root/raw_by_name[name]['path']).resolve(),'prepared raw physical binding differs')
    # Static pickle scan binds even unmatched HDF references omitted from a
    # maliciously re-sealed JSON inventory. It does not execute pickle opcodes.
    referenced=set()
    for opcode,arg,_ in pickletools.genops((prepared/'meta_data.pkl').read_bytes()):
        if opcode.name in ('UNICODE','BINUNICODE','SHORT_BINUNICODE','BINUNICODE8') and isinstance(arg,str) and arg.endswith('.hdf'):
            path=Path(arg)
            if path.is_absolute():
                require(path.resolve().parent==prepared.resolve(),'metadata HDF path escapes prepared namespace');referenced.add(path.name)
    mains={t+'.hdf' for t in TABLES}
    require(mains<=referenced and referenced=={p.name for p in prepared.glob('*.hdf')}
            and set(recorded)==referenced|{'meta_data.pkl','binding.json'}, 'main/unmatched HDF required inventory incomplete/extra')
    model=report['model'];model_dir=directory/'model';mouter=outer(model_dir,'MODEL')
    require(mouter['result']==model and read(model_dir/'model.json')==model,'outer/model report differs')
    require(set(model['files_sha256'])=={t+'.pkl' for t in TABLES}|{'ensemble_single.pkl'},'exact6 model/checkpoint pickle set required')
    require(model['binding']['samples_per_spn']==1000000 and model['binding']['seed']==1
            and model['binding']['ensemble_strategy']=='single' and model['binding']['rdc_threshold']==.3,'formal fixed model settings differ')
    require(Path(report['model_path']).resolve()==Path(model['model_path']).resolve()==(model_dir/'ensemble_single.pkl').resolve()
            and model['spn_count']==report['spn_count']==5 and model['training_tables']==report['training_tables'],'formal model/path/count summary differs')
    rows={r['table']:r for r in model['training_tables']}
    require(set(rows)==set(TABLES) and all(r['actual_training_rows']==(2556 if t=='dwdate' else 1000000) for t,r in rows.items()),'exact1M/table and actual date row counts required')
    p=report['inputs']['probability'];probability=float(Fraction(p['numerator'],p['denominator']))
    require(math.isclose(rows['lineorder']['full_join_estimate'],report['actual_sample_rows']*1/probability,rel_tol=2e-15),'model fact normalizer must equal actual n/p')
    mguard=read(model_dir/'model_guard.json');add(model_dir/'model_guard.json')
    required={t+'.pkl' for t in TABLES}|{t+'.json' for t in TABLES}|{'ensemble_single.pkl','model.json','input_guard.json'}
    require(set(mguard['model_files_sha256'])==required and mguard['binding']['model_stage']==model['binding'],'model guard required inventory differs')
    for name,sha in mguard['model_files_sha256'].items():add(model_dir/name,sha)
    require({p.name for p in model_dir.glob('*.pkl')}==set(model['files_sha256']),'model physical pickle set missing/extra')
    require(read(model_dir/'input_guard.json')['binding']==mguard['binding'] and mguard['binding']['inputs']==partifact,'model input/HDF guard binding differs')
    for name,sha in model['files_sha256'].items():require(files[(model_dir/name).relative_to(root).as_posix()]['sha256']==sha,'model checkpoint digest differs')
    require(report['model_sha256']==model['files_sha256']['ensemble_single.pkl'],'published model checksum differs')
    require(mouter['binding']['prepared_outer_receipt_sha256']==digest(stage_home(prepared,'prepared')/'receipt.json'),'model prepared outer receipt link differs')
    for table in TABLES:
        row=read(model_dir/(table+'.json'))
        require(row['binding']==model['binding'] and row['sha256']==model['files_sha256'][table+'.pkl']
                and row['training'] in model['training_tables'],'per-table checkpoint/RNG receipt differs')
    moments=directory/'sample_moments_native';moment=read(moments/'moments.json');mseal=read(moments/'seal.json')
    add(moments/'moments.json',mseal['sha256']);add(moments/'moments.tsv',mseal['tsv_sha256']);add(moments/'seal.json');add(moments/'process.json')
    require(moment['status']=='PASS' and moment['sample_rows']==report['actual_sample_rows'] and mseal['binding']['sample_rows']==report['actual_sample_rows']
            and read(moments/'process.json')['returncode']==0,'actual retained sample moment binding differs')
    sqls=(root/SQL_REL).read_text().splitlines()
    require(len(sqls)==13 and len(moment['queries'])==13 and [q['sql'] for q in moment['queries']]==sqls,'moment SQL identity set differs')
    helper=root/OUTPUT_REL/'runtime/native';stem='ci_'+moment['build']['binding']['source_sha256'][:16]
    add(helper/(stem+'.cpp'),moment['build']['binding']['source_sha256']);add(helper/(stem+'.exe'),moment['build']['executable_sha256'])
    add(helper/(stem+'.json'));add(helper/(stem+'_build.json'))
    require(read(helper/(stem+'.json'))==moment['build'] and read(helper/(stem+'_build.json'))['returncode']==0,'native CI helper runtime/build link differs')
    checkpoint=directory/'core_truth_checkpoint.json';add(checkpoint)
    require(read(checkpoint)['source_receipt_sha256']==report['source_receipt_sha256'],'truth projection native source link differs')
    evaluation=report['evaluation'];eouter=outer(directory/'evaluation','EVALUATION')
    require(eouter['result']==evaluation and evaluation['queries']==report['queries'] and evaluation['binding']==report['evaluation_binding'],'evaluation report/outer receipt differs')
    evaluation_dir=Path(report['evaluation_directory']).resolve()
    require(evaluation_dir.parent==(directory/'evaluation').resolve(),'evaluation output namespace differs')
    require({p.name for p in evaluation_dir.glob('query_*.json')}=={'query_%02d'%i+suffix for i in range(13) for suffix in ('.json','.seal.json')}, 'exact26 query identity files required')
    require(len(evaluation['identities'])==13 and len(report['queries'])==13,'all13 evaluation identities required')
    author=truth_map(author_groups if author_groups is not None else load_author_groups(root))
    for i,(name,sql,q,identity) in enumerate(zip(QUERY_NAMES,sqls,report['queries'],evaluation['identities'])):
        path=evaluation_dir/('query_%02d.json'%i);item=add(path);seal_path=path.with_suffix('.seal.json');seal_item=add(seal_path);seal=read(seal_path)
        require((q['query_no'],q['query_name'],q['sql'])==(i,name,sql) and read(path)==q
                and seal['binding']==report['evaluation_binding'] and seal['sha256']==item['sha256'],'query original index/name/exactSQL/physical binding differs')
        require(identity==dict(query_no=i,query_name=name,exact_sql=sql,global_binding=report['evaluation_binding'],
                              result_sha256=item['sha256'],core_seal_sha256=seal_item['sha256']),'query identity receipt differs')
        keys=[tuple(g['key']) for g in q['groups']];require(len(keys)==len(set(keys)),'duplicate published model union group')
        group_fields={'key','status','truth','prediction','zero_truth','absolute_error','relative_error','model_interval',
                      'model_covers_truth','model_relative_half_width','sample_moments','reference_ci','released_ci_comparison'}
        require(all(group_fields<=set(g) for g in q['groups']) and isinstance(q['nonfinite_original_intervals'],list),'original point/CI/reference group states incomplete')
        require(all(g['status'] in ('MATCHED','MISSING_MODEL_GROUP','EXTRA_MODEL_GROUP') for g in q['groups']),'unknown model union group state')
        expected={k:v for (index,k),v in author.items() if index==i}
        observed={tuple(str(x) for x in g['key']):g for g in q['groups'] if g['status']!='EXTRA_MODEL_GROUP'}
        require(set(observed)==set(expected) and all(observed[k]['truth']==float(v) for k,v in expected.items()),'complete2059 actual author group/value identity required')
        require(q['missing_model_groups']==sum(g['status']=='MISSING_MODEL_GROUP' for g in q['groups'])
                and q['extra_model_groups']==sum(g['status']=='EXTRA_MODEL_GROUP' for g in q['groups'])
                and q['truth_groups']==sum(g['status']!='EXTRA_MODEL_GROUP' for g in q['groups'])
                and q['model_groups']==sum(g['status']!='MISSING_MODEL_GROUP' for g in q['groups']),'published group coverage receipt differs')
    require(sum(q['truth_groups'] for q in report['queries'])==2059
            and report['point_query_errors']==sum(bool(q['point_error']) for q in report['queries'])
            and report['ci_query_errors']==sum(bool(q['ci_error']) for q in report['queries']),'published truth/error totals differ')
    require(report['evaluation_binding']['confidence_sample_size']==report['actual_sample_rows']
            and report['evaluation_binding']['truth_checkpoint_sha256']==digest(checkpoint),'evaluation fact sample/truth checkpoint differs')
    return list(files.values())


def formal_binding(report):
    return dict(plan_binding_sha256=report['plan_binding_sha256'],source_receipt_sha256=report['source_receipt_sha256'],
                dependencies_sha256=value_hash(report['plan']['dependencies']),bridge_sha256=report['adapter_source_sha256'])


def required_publication_artifacts(report,root=ROOT):
    root=Path(root).resolve();records={r['path']:r for r in required_stage_artifacts(report,root)}
    def add(path,expected=None):
        r=artifact_record(path,root);require(expected is None or r['sha256']==expected,'publication dependency changed: '+r['path']);records[r['path']]=r
    for item in report['inputs']['physical_artifacts']:add(root/item['path'],item['sha256'])
    generation_path=root/GEN_RESULT_REL;generation_seal=generation_path.with_name(generation_path.stem+'_seal.json')
    add(generation_path,report['source_receipt_sha256']);add(generation_seal)
    require(read(generation_seal)['sha256']==report['source_receipt_sha256'],'native final receipt/seal link differs')
    plan_path=root/report['plan_path'];add(plan_path,report['plan_file_sha256']);add(plan_path.with_suffix('.seal.json'))
    require(read(plan_path)==report['plan'] and value_hash(report['plan'])==report['plan_binding_sha256']
            and read(plan_path.with_suffix('.seal.json'))['sha256']==report['plan_file_sha256'],'formal plan identity/seal differs')
    dependencies=report['plan']['dependencies'];complete=dependencies['complete']
    for path,sha in complete['sources'].items():add(root/path,sha)
    for package,field in (('spn','spflow_sources'),('sqlparse','sqlparse_sources')):
        for path,sha in complete[field].items():add(root/'.venv/Lib/site-packages'/package/path,sha)
    require(len(complete['sqlparse_sources'])==22,'exact22 parser sources required')
    for path,sha in dependencies['physical_native_libraries'].items():add(root/path,sha)
    require(dependencies.get('python_base_native_files') and dependencies.get('actual_module_roots'),'actual base Python/module-root closure required')
    for path,sha in dependencies['python_base_native_files'].items():add(root/path,sha)
    base=dependencies['python_base_executable'];require(dependencies['python_base_native_files'].get(base['path'])==base['sha256'],'actual base executable role missing from native closure')
    add(root/base['path'],base['sha256'])
    for entry in dependencies['actual_module_roots'].values():add(root/entry['path'],entry['sha256'])
    launcher=dependencies['operational_launcher'];require(launcher['path']=='code/full_ssb_native_model_run.py','fixed operational launcher path required')
    add(root/launcher['path'],launcher['sha256'])
    for entry in dependencies.get('generator_runtime',{}).get('artifacts',[]):add(root/entry['path'],entry['sha256'])
    add(dependencies['python_executable']['path'],dependencies['python_executable']['sha256'])
    for path,sha in dependencies['frozen_sources'].items():add(root/path,sha)
    add(root/'code/full_ssb_native_model.py',report['adapter_source_sha256'])
    directory=Path(report['directory']);control=directory/'formal_control';receipt=read(control/'receipt.json');state=read(control/'lifecycle.json')
    add(control/'receipt.json');add(control/'lifecycle.json')
    require(receipt['status']=='PASS' and receipt['kind']=='FORMAL' and state['status']=='PASS'
            and state['receipt_sha256']==digest(control/'receipt.json') and state['binding']==receipt['binding']==formal_binding(report)
            and receipt['result']==report,'whole FORMAL PASS receipt/lifecycle required')
    add(directory/'verification.json');add(root/RESULT_REL)
    require(read(directory/'verification.json')==read(root/RESULT_REL)==report,'published/verification/formal result differs')
    return [records[p] for p in sorted(records)]


def publication_binding(report,root=ROOT):
    return dict(formal_receipt_sha256=digest(Path(report['directory'])/'formal_control/receipt.json'),
                report_sha256=value_hash(report),plan_binding_sha256=report['plan_binding_sha256'])


def verify_publication(report,root=ROOT,require_publication_pass=True):
    """Read-only complete publication layer; caller separately validates source."""
    records=required_publication_artifacts(report,root)
    seal=read(Path(report['directory'])/'verification_seal.json')
    require(seal.get('status')=='PASS_BRIDGE_PUBLICATION' and seal.get('artifacts')==records
            and seal['dependencies_sha256']==value_hash(report['plan']['dependencies'])
            and seal['source_receipt_sha256']==report['source_receipt_sha256'],'formal required artifact list missing/extra/changed')
    if require_publication_pass:
        directory=Path(report['directory']);home=directory/'publication_control';state=read(home/'lifecycle.json');receipt=read(home/'receipt.json')
        require(state['status']=='PASS' and receipt['status']=='PASS' and receipt['kind']=='PUBLICATION'
                and state['receipt_sha256']==digest(home/'receipt.json') and state['binding']==receipt['binding']==publication_binding(report,root)
                and receipt['result']==publication_result(report,root),'complete PUBLICATION PASS and final seal link required')
        records=records+[artifact_record(home/'receipt.json',root),artifact_record(home/'lifecycle.json',root),
                         artifact_record(directory/'verification_seal.json',root)]
    return records


def verify_formal_publication(root=ROOT):
    """Strict read-only API for root's future native replay; never repairs/runs."""
    root=Path(root).resolve();published=root/RESULT_REL
    require(published.is_file(),'completed formal native model publication missing')
    report=read(published);directory=Path(report['directory']).resolve();plan=report['plan']
    require(report['stage']=='SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI' and report['status'] in ('PASS','MODEL_QUERY_ERRORS_RECORDED')
            and report['population_rows']==N and report['source_receipt_sha256']==plan['source_receipt_sha256'],'completed native formal report identity differs')
    require(directory==(root/OUTPUT_REL/'runs'/report['plan_binding_sha256'][:20]).resolve(),'formal run namespace differs')
    require(plan.get('status')=='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN' and plan.get('executable') is True and plan.get('model')==MODEL,'root-reviewed formal model plan required')
    require(FINAL_RECEIPT_INTERFACE_FROZEN and GENERATOR_CLOSURE_INTERFACE_FROZEN and FORMAL_PUBLICATION_REVIEW_COMPLETE,'formal source/runtime/publication interfaces remain unreviewed')
    inputs=verify_generation(expected_receipt_sha256=plan['source_receipt_sha256'],root=root)
    require(report['inputs']==inputs and report['actual_sample_rows']==inputs['sample_rows'],'actual native source snapshot differs')
    require(root==ROOT and plan['dependencies']==dependency_snapshot(),'current model/parser/runtime dependency snapshot differs')
    require(report['adapter_source_sha256']==digest(__file__),'bridge/context source changed')
    records=verify_publication(report,root);seal_path=directory/'verification_seal.json'
    error_status=bool(report['point_query_errors'] or report['ci_query_errors'])
    return dict(status='PASS_READ_ONLY_SSB_NATIVE_V2_FORMAL_MODEL_WITH_ERRORS' if error_status else 'PASS_READ_ONLY_SSB_NATIVE_V2_FORMAL_MODEL',
        report=report,verification=artifact_record(directory/'verification.json',root),verification_seal=artifact_record(seal_path,root),
        published_result=artifact_record(published,root),plan=artifact_record(root/report['plan_path'],root),
        formal_receipt=artifact_record(directory/'formal_control/receipt.json',root),formal_lifecycle=artifact_record(directory/'formal_control/lifecycle.json',root),
        artifacts=records,dependencies=plan['dependencies'],model_path=report['model_path'],model_sha256=report['model_sha256'],
        sample_rows=inputs['sample_rows'],population_rows=N,queries=report['queries'],evaluation_binding=report['evaluation_binding'],
        database_connected=False,training_executed=False,inference_executed=False,files_modified=False)


def verify_formal(root=ROOT):
    """Public read-only API: complete science plus successful owned supervisor."""
    result=verify_formal_publication(root)
    import full_ssb_native_model_run as runner
    require(runner.read_reviewed_plan(Path(root)/result['report']['plan_path'],result['report']['plan_file_sha256'],root)==result['report']['plan'],
            'public formal acceptance requires the complete reviewed operational/model plan')
    result['artifacts']=result['artifacts']+runner.verify_supervisor(result['report'],root)
    require(len(result['artifacts'])==len({r['path'] for r in result['artifacts']}),'duplicate formal/supervisor artifact path')
    return result


def execute_formal(plan,memory_approved=False):
    """Future orchestration; unreachable in this draft release, including via CLI."""
    require(FINAL_RECEIPT_INTERFACE_FROZEN,'native final receipt interface is not frozen; formal execution disabled')
    require(GENERATOR_CLOSURE_INTERFACE_FROZEN and FORMAL_PUBLICATION_REVIEW_COMPLETE,'source/runtime closure and formal control/publication review incomplete')
    require(memory_approved,'root memory release required')
    require(os.environ.get('DEEPDB_SSB_NATIVE_MODEL_WORKER')=='1','formal execution requires a new fresh worker')
    import full_ssb_native_model_run as runner
    runner.verify_owned_job_membership(os.environ.get('DEEPDB_SSB_NATIVE_MODEL_JOB'))
    require(all(os.environ.get(name)=='1' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')),'original model worker thread limits must all equal1')
    require(plan.get('status')=='ROOT_REVIEWED_NATIVE_V2_MODEL_PLAN' and plan.get('executable') is True and plan.get('model')==MODEL,'reviewed executable plan required')
    require(plan['dependencies']==dependency_snapshot(),'complete bridge/model/parser/runtime dependencies changed')
    plan_binding_sha256=value_hash(plan)
    plan_path=ROOT/OUTPUT_REL/'plans'/plan_binding_sha256[:20]/'plan.json'
    require(read(plan_path)==plan and read(plan_path.with_suffix('.seal.json')).get('sha256')==digest(plan_path),'reviewed physical model plan/seal required')
    inputs=verify_generation(expected_receipt_sha256=plan['source_receipt_sha256'])
    import full_ssb_guard as guard
    core=guard.core
    existing=sum(p.stat().st_size for folder in ('data/ssb','output/full/ssb') for p in (ROOT/folder).rglob('*') if p.is_file())
    resources=check_resources(shutil.disk_usage(str(ROOT)).free,core.available_memory_bytes(),existing)
    directory=ROOT/OUTPUT_REL/'runs'/plan_binding_sha256[:20];directory.mkdir(parents=True,exist_ok=True)
    binding=dict(plan_binding_sha256=plan_binding_sha256,source_receipt_sha256=inputs['receipt_sha256'],
                 dependencies_sha256=value_hash(plan['dependencies']),bridge_sha256=digest(__file__))
    def produce():return execute_stages(plan,inputs,directory,resources,plan_path)
    def validate(report):
        require(formal_binding(report)==binding,'whole formal binding differs')
        require(verify_generation(expected_receipt_sha256=plan['source_receipt_sha256'])==inputs,'native physical inputs changed before FORMAL publication')
        require(plan['dependencies']==dependency_snapshot(),'complete dependencies changed before FORMAL publication')
        required_stage_artifacts(report)
    with controller_lock(ROOT/OUTPUT_REL/'controller.lock'):
        report=formal_transaction(directory/'formal_control',binding,produce,validate)
        publish_formal(report)
    return report


def publish_formal(report,root=ROOT):
    """Independent durable PUBLICATION; failures also taint whole-FORMAL."""
    root=Path(root);directory=Path(report['directory']);receipt=read(directory/'formal_control/receipt.json');state=read(directory/'formal_control/lifecycle.json')
    require(receipt['result']==report and receipt['status']==state['status']=='PASS'
            and state['receipt_sha256']==digest(directory/'formal_control/receipt.json'),'whole FORMAL PASS required before result publication')
    def validate(result):
        verify_publication(report,root,require_publication_pass=False)
        require(result==publication_result(report,root),'publication physical results changed')
    try:
        return formal_transaction(directory/'publication_control',publication_binding(report,root),
            lambda:write_publication(report,root),validate,kind='PUBLICATION')
    except BaseException as error:
        atomic(directory/'formal_control/lifecycle.json',dict(status='TAINTED',kind='FORMAL',binding=formal_binding(report),reason='publication failed: '+repr(error)))
        raise


def publication_result(report,root=ROOT):
    directory=Path(report['directory'])
    return dict(verification_seal_sha256=digest(directory/'verification_seal.json'),
                verification_sha256=digest(directory/'verification.json'),published_result_sha256=digest(Path(root)/RESULT_REL))


def write_publication(report,root=ROOT):
    root=Path(root);directory=Path(report['directory'])
    atomic(directory/'verification.json',report);atomic(root/RESULT_REL,report)
    artifacts=required_publication_artifacts(report,root)
    atomic(directory/'verification_seal.json',dict(status='PASS_BRIDGE_PUBLICATION',artifacts=artifacts,
        dependencies_sha256=value_hash(report['plan']['dependencies']),source_receipt_sha256=report['source_receipt_sha256']))
    return publication_result(report,root)


def execute_stages(plan,inputs,directory,resources,plan_path):
    """Called only under both whole-FORMAL kernel lock and durable transaction."""
    require(FINAL_RECEIPT_INTERFACE_FROZEN and GENERATOR_CLOSURE_INTERFACE_FROZEN and FORMAL_PUBLICATION_REVIEW_COMPLETE,'formal scientific stages remain closed')
    import full_ssb_guard as guard
    core=guard.core;plan_binding_sha256=value_hash(plan)
    body=read(ROOT/GEN_RESULT_REL);body['receipt_sha256']=inputs['receipt_sha256'];schema=make_schema(body)
    checkpoint=directory/'core_truth_checkpoint.json';projection=core_truth_projection(body)
    if checkpoint.exists():require(read(checkpoint)==projection,'core truth I/O projection changed')
    else:atomic(checkpoint,projection)
    # Route only helper compilation I/O; original source/constants stay fixed.
    with isolated_output(core,ROOT/OUTPUT_REL/'runtime'):
        metadata=guard.guarded_prepare(schema,directory/'prepared',chunk_rows=100000)
        probability=float(Fraction(body['sampling']['actual_cutoff'],2**64))
        expected_length=body['sample_rows']*1/probability
        require(math.isclose(metadata['lineorder']['length'],expected_length,rel_tol=2e-15),'learned preparation length must remain original n/p')
        moments=core.sample_moments_native(schema,inputs['sample_rows'],directory/'sample_moments_native')
        model=guard.guarded_train(schema,directory/'prepared',1000000,directory/'model')
        require(model['spn_count']==5 and model['binding']['seed']==1 and model['binding']['rdc_threshold']==.3,'formal single-table model settings changed')
        trained={r['table']:r for r in model['training_tables']}
        require(set(trained)=={'lineorder','dwdate','customer','supplier','part'} and all(r['actual_training_rows']==(2556 if name=='dwdate' else 1000000) for name,r in trained.items()),'actual per-table training row counts differ')
        require(math.isclose(trained['lineorder']['full_join_estimate'],expected_length,rel_tol=2e-15),'trained fact normalizer was replaced by exact N')
        truth=core.population_truth_groups(checkpoint)
        evaluated=guard.guarded_evaluate(model,truth,moments['queries'],directory/'evaluation')
    require(verify_generation(expected_receipt_sha256=plan['source_receipt_sha256'])==inputs,'native physical inputs changed during model stages')
    require(plan['dependencies']==dependency_snapshot(),'model/parser/runtime changed during model stages')
    guard.require_prepared_pass(schema,directory/'prepared');guard.require_model_pass(model)
    guard.query_bundle(evaluated['directory'],evaluated['binding'])
    require(len(evaluated['queries'])==13 and sum(q['truth_groups'] for q in evaluated['queries'])==2059,'complete model evaluation truth identity set required')
    report=dict(status='PASS' if not evaluated['point_query_errors'] and not evaluated['ci_query_errors'] else 'MODEL_QUERY_ERRORS_RECORDED',
        stage='SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI',full_paper_reproduction_complete=False,
        author_population_row_count_and_13_truths_match=True,author_full_row_byte_identity_proven=False,
        directory=str(directory),inputs=inputs,plan=plan,plan_path=plan_path.relative_to(ROOT).as_posix(),
        plan_binding_sha256=plan_binding_sha256,plan_file_sha256=digest(plan_path),resources_at_start=resources,
        population_rows=N,actual_sample_rows=inputs['sample_rows'],fact_normalizer=inputs['fact_normalizer'],
        source_receipt=GEN_RESULT_REL,source_receipt_sha256=inputs['receipt_sha256'],
        prepared_directory=str(directory/'prepared'),model_directory=str(directory/'model'),
        model_path=model['model_path'],model_sha256=digest(model['model_path']),spn_count=model['spn_count'],
        training_tables=model['training_tables'],evaluation_directory=evaluated['directory'],
        evaluation_binding=evaluated['binding'],queries=evaluated['queries'],
        point_query_errors=evaluated['point_query_errors'],ci_query_errors=evaluated['ci_query_errors'],
        model=model,evaluation=evaluated,
        ci_scope='Original central90 and same actual retained sample; correlated SUM differences retain original warnings',
        normalizer_scope='Original row-order/int64/pandas mean and actual retained n/p preserved',
        adapter_source_sha256=digest(__file__),core_truth_projection_sha256=digest(checkpoint))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','validate-source'])
    parser.add_argument('--receipt-sha256',help='Explicit root-reviewed frozen final native receipt hash; never inferred')
    args=parser.parse_args()
    if args.action=='plan':result=draft_plan()
    else:result=verify_generation(expected_receipt_sha256=args.receipt_sha256)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
