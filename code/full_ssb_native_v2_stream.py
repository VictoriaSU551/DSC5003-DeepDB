"""Independent corrected SSB stream controller; historical evidence is read-only.

This module never relaxes the frozen original author gate. Its own final receipt
requires the author's row count and all13 integer SQL result sets.
"""
import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
import subprocess
import sys
import time
import uuid
import re
import platform

import full_ssb_native_v2 as native

ROOT=native.ROOT
ARITIES=[0,0,0,2,2,2,3,3,3,3,2,3,3]


def canonical(groups):
    return [{'query_no':q,'group':list(group),'value':value} for (q,group),value in sorted(groups.items())]


def parse_aggregates(path):
    result={}
    for line in Path(path).read_text().splitlines():
        fields=line.split('\t');q=int(fields[0])
        if q not in range(13) or len(fields)!=ARITIES[q]+2:raise ValueError('Invalid aggregate query/group identity')
        key=(q,tuple(fields[1:-1]));value=int(fields[-1])
        if key in result:raise ValueError('Duplicate aggregate query/group')
        result[key]=value
    return result


def validate_restore(sample,state,binding,directory,ranges,truncate=False):
    """Prove all committed files and each sample segment before any truncation."""
    sample=Path(sample);directory=Path(directory)
    if state.get('schema')!='ssb_native_v2_checkpoint_v1' or state.get('binding')!=binding:raise ValueError('Checkpoint binding changed')
    records=state['committed_shards'];count=len(records)
    if count>len(ranges) or state['next_shard']!=count or [r['shard'] for r in records]!=list(range(count)):
        raise ValueError('Checkpoint shards are not contiguous')
    merged={};rows=kept=size=0
    for index,record in enumerate(records):
        if (record['first_order'],record['orders'])!=tuple(ranges[index]):raise ValueError('Checkpoint order range changed')
        expected={'chunks/'+str(index).zfill(8)+'/'+name for name in ['stats.json','aggregates.tsv','seeds_after.tsv']}
        if set(record['files'])!=expected:raise ValueError('Checkpoint required artifact inventory changed')
        for name,description in record['files'].items():
            path=directory/name
            if not path.is_file() or path.stat().st_size!=description['bytes'] or native.digest(path)!=description['sha256']:
                raise ValueError('Committed artifact changed: '+name)
        stats=json.loads((directory/('chunks/'+str(index).zfill(8)+'/stats.json')).read_text())
        if stats['rows']!=record['rows'] or stats['sample_rows']!=record['sample_rows'] or stats['unmatched_foreign_keys']!=0:
            raise ValueError('Committed row accounting changed')
        if any(type(record[k]) is not int or record[k]<0 for k in ['rows','sample_rows','sample_bytes']) or record['sample_rows']>record['rows']:
            raise ValueError('Invalid committed row accounting')
        for key,value in parse_aggregates(directory/('chunks/'+str(index).zfill(8)+'/aggregates.tsv')).items():merged[key]=merged.get(key,0)+value
        rows+=record['rows'];kept+=record['sample_rows'];size+=record['sample_bytes']
    if canonical(merged)!=state['aggregates'] or (rows,kept,size)!=(state['rows'],state['sample_rows'],state['sample_bytes']):
        raise ValueError('Checkpoint cumulative accounting changed')
    if not sample.is_file() or sample.stat().st_size<size:raise ValueError('Sample is shorter than its committed prefix')
    whole=hashlib.sha256()
    with sample.open('rb') as stream:
        for record in records:
            remaining=record['sample_bytes'];part=hashlib.sha256();lines=0;last=b''
            while remaining:
                block=stream.read(min(4*1024**2,remaining))
                if not block:raise ValueError('Incomplete sample prefix')
                whole.update(block);part.update(block);remaining-=len(block);lines+=block.count(b'\n');last=block[-1:]
            if record['sample_bytes'] and last!=b'\n':raise ValueError('Committed sample offset is not a complete line boundary')
            if part.hexdigest()!=record['sample_sha256'] or lines!=record['sample_rows']:raise ValueError('Committed sample segment hash/rows changed')
    if whole.hexdigest()!=state['sample_sha256']:raise ValueError('Committed sample prefix hash changed')
    if sample.stat().st_size!=size:
        if not truncate:raise ValueError('Uncommitted sample tail exists')
        with sample.open('r+b') as stream:stream.truncate(size);stream.flush();os.fsync(stream.fileno())
    return {'rows':rows,'sample_rows':kept,'sample_bytes':size,'aggregates':canonical(merged),'hasher':whole}


def stream_plan(scale,total_orders,shards,dimensions,seed,cutoff):
    if type(total_orders) is not int or total_orders<1 or total_orders>750000000:raise ValueError('Invalid total orders')
    if type(shards) is not int or shards<1 or shards>min(10000,total_orders):raise ValueError('Invalid shard count')
    if type(cutoff) is not int or cutoff<0 or cutoff>1<<64:raise ValueError('Invalid integer cutoff')
    if type(seed) is not int or seed<0 or seed>=(1<<64):raise ValueError('Invalid sample seed')
    build=native.callback_build();dimensions=Path(dimensions).resolve()
    source_map={p.relative_to(ROOT).as_posix():native.digest(p) for p in source_paths()}
    dims={table:native.file_description(dimensions/(table+'.tbl'),True) for table in ['customer','supplier','part','date']}
    size,extra=divmod(total_orders,shards);ranges=[(i*size+1,size+(extra if i==shards-1 else 0)) for i in range(shards)]
    binding={'scale':str(scale),'total_orders':total_orders,'shards':shards,'sample_seed':seed,'actual_cutoff':cutoff,
             'effective_probability_numerator':cutoff,'effective_probability_denominator':1<<64,'sources_sha256':source_map,
             'dimensions':dims,'native_executable':native.file_description(build['executable']),
             'native_build_binding':build['binding'],'native_build_receipt':native.file_description(Path(build['directory'])/'receipt.json'),'python_version':sys.version,
             'native_runtime':native_runtime(build['executable'])}
    binding['source_id']=native.object_sha(binding)
    return {'schema':'ssb_native_v2_stream_plan_v1','binding':binding,'ranges':[list(pair) for pair in ranges]}


def source_paths():
    own=ROOT/'code/vendor/ssb_native_v2'
    paths=[ROOT/'code/full_ssb_native_v2.py',Path(__file__),ROOT/'code/full_ssb_native_v2_formal.py',native.VENDOR/'SOURCES.json',
           native.GCC,native.GCC.with_name('g++.exe'),native.GCC.with_name('objdump.exe'),Path(sys.executable),Path(getattr(sys,'_base_executable',sys.executable))]
    paths+=[own/name for name in ['native_api.h','native_driver.c','native_callback.cpp','native_sampling.h','native_dimensions.c','native_field_probe.cpp','cygwin.lock.json']]
    paths+=[native.VENDOR/name for name in json.loads((native.VENDOR/'SOURCES.json').read_text())['files_sha256']]
    return sorted(set(p.resolve() for p in paths))


def native_runtime(executable):
    output=subprocess.check_output([str(native.GCC.with_name('objdump.exe')),'-p',str(executable)],text=True)
    names=re.findall(r'DLL Name:\s+(\S+)',output)
    if sorted(name.lower() for name in names)!=['kernel32.dll','msvcrt.dll']:raise ValueError('Unreviewed native runtime DLL dependency')
    system=Path(os.environ['SystemRoot'])/'System32'
    return {'platform':platform.platform(),'machine':platform.machine(),'direct_imports':names,
            'import_audit_output_sha256':hashlib.sha256(output.encode()).hexdigest(),
            'direct_import_files':{name:native.file_description(system/name) for name in names},
            'scope':'PE direct imports; MinGW libgcc/libstdc++ statically linked. Windows transitive OS DLLs are platform dependencies, not bundled.'}


def check_plan(plan,physical=True):
    if plan.get('schema')!='ssb_native_v2_stream_plan_v1':raise ValueError('Unknown stream plan schema')
    binding=plan['binding'];copy=dict(binding);source_id=copy.pop('source_id')
    if source_id!=native.object_sha(copy):raise ValueError('Plan source identity changed')
    total,shards=binding['total_orders'],binding['shards'];size,extra=divmod(total,shards)
    if plan['ranges']!=[[i*size+1,size+(extra if i==shards-1 else 0)] for i in range(shards)]:raise ValueError('Plan order ranges changed')
    if set(binding['sources_sha256'])!={p.relative_to(ROOT).as_posix() for p in source_paths()}:raise ValueError('Required source/runtime inventory changed')
    if sorted(name.lower() for name in binding['native_runtime']['direct_import_files'])!=['kernel32.dll','msvcrt.dll']:raise ValueError('Required direct native runtime inventory changed')
    if physical:
        for name,sha in binding['sources_sha256'].items():
            if native.digest(ROOT/name)!=sha:raise ValueError('Bound source/runtime changed: '+name)
        for description in list(binding['dimensions'].values())+[binding['native_executable']]+list(binding['native_runtime']['direct_import_files'].values()):
            path=Path(description['path'])
            if path.stat().st_size!=description['bytes'] or native.digest(path)!=description['sha256']:raise ValueError('Bound physical input changed: '+str(path))
        receipt=binding['native_build_receipt']
        if native.digest(receipt['path'])!=receipt['sha256']:raise ValueError('Native build receipt changed')
        required={Path(name).stem+'.o' for name in native.SOURCES+['native_driver.c']}|{'compile_'+Path(name).stem+'.json' for name in native.SOURCES+['native_driver.c']}|{'native.exe','link.json'}
        native.strict_receipt(Path(receipt['path']).parent,binding['native_build_binding'],required)
    return binding


def cleanup_committed_sample(path,index):
    try:Path(path).unlink();return None
    except OSError as error:return {'shard':index,'path':str(path),'error':repr(error),'disposition':'Retained, not used; committed prefix already fsynced and checkpointed'}


def process_peak_bytes(process):
    if os.name!='nt':return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    result=Counters();result.cb=ctypes.sizeof(result)
    function=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    function.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];function.restype=wintypes.BOOL
    if not function(wintypes.HANDLE(int(process._handle)),ctypes.byref(result),result.cb):raise ctypes.WinError(ctypes.get_last_error())
    return int(result.PeakWorkingSetSize)


@contextmanager
def namespace_lock(home):
    """The OS lock is released on process death; an existing file is not a lock."""
    path=Path(home)/'execution.lock'
    stream=path.open('a+b')
    if stream.tell()==0:stream.write(b'0');stream.flush()
    stream.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:raise ValueError('Namespace already has an active execution lock') from error
        else:
            import fcntl
            try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:raise ValueError('Namespace already has an active execution lock') from error
        yield
    finally:
        # Closing the descriptor releases only this descriptor's lock.
        stream.close()


def stream(plan,directory,resume=False,stop_after=None,data_directory=None,budget_check=None):
    binding=check_plan(plan);home=Path(directory).resolve();sample_home=Path(data_directory).resolve() if data_directory else home
    if not resume:
        home.parent.mkdir(parents=True,exist_ok=True)
        try:home.mkdir(exist_ok=False)
        except FileExistsError as error:raise ValueError('New stream namespace already exists; it is never adopted implicitly') from error
    elif not home.is_dir():raise ValueError('Resume namespace does not exist')
    with namespace_lock(home):
        return _stream_locked(plan,home,sample_home,resume,stop_after,budget_check)


def _stream_locked(plan,home,sample_home,resume,stop_after,budget_check):
    binding=plan['binding'];sample=sample_home/'lineorder_sampled.csv';process=None;log=None;started=time.perf_counter()
    started_run=not resume
    try:
        if resume:
            life=json.loads((home/'lifecycle.json').read_text())
            if life['status'] not in ['RUNNING','PAUSED_FOR_TEST','STREAM_COMPLETE'] or life['plan_sha256']!=native.object_sha(plan):
                raise ValueError('Namespace lifecycle/plan refuses recovery (TAINTED is permanent)')
            if json.loads((home/'plan.json').read_text())!=plan:raise ValueError('Saved plan changed')
            started_run=True
            state=json.loads((home/'checkpoint.json').read_text())
            checked=validate_restore(sample,state,binding,home,plan['ranges'],truncate=True);hasher=checked['hasher']
        else:
            sample_home.mkdir(parents=True,exist_ok=True)
            with sample.open('xb') as out:out.flush();os.fsync(out.fileno())
            native.atomic(home/'plan.json',plan)
            state={'schema':'ssb_native_v2_checkpoint_v1','binding':binding,'next_shard':0,'committed_shards':[],
                   'rows':0,'sample_rows':0,'sample_bytes':0,'sample_sha256':hashlib.sha256(b'').hexdigest(),'aggregates':[],'complete':False}
            native.atomic(home/'checkpoint.json',state);hasher=hashlib.sha256()
        resumed=state['next_shard'];peak=0
        if resumed==len(plan['ranges']):
            if not state['complete']:raise ValueError('Full checkpoint is not complete')
            return {'status':'STREAM_COMPLETE_NOT_AUTHOR_VERIFIED','checkpoint':state,'resumed_shards':resumed}
        native.atomic(home/'lifecycle.json',{'status':'RUNNING','plan_sha256':native.object_sha(plan),'pid':os.getpid(),'sample':str(sample)})
        log=(home/'native.stderr.log').open('ab')
        dimensions=Path(binding['dimensions']['date']['path']).parent
        process=subprocess.Popen([binding['native_executable']['path'],binding['scale'],str(native.VENDOR/'dists.dss'),str(dimensions)],
            cwd=str(home),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
        if process.stdout.readline().strip()!='READY':raise ValueError('Native stream initialization failed')
        peak=process_peak_bytes(process) or 0
        merged={(r['query_no'],tuple(r['group'])):r['value'] for r in state['aggregates']}
        for index in range(resumed,len(plan['ranges'])):
            if budget_check is not None and index%128==0:budget_check()
            first,count=plan['ranges'][index];target=home/'chunks'/str(index).zfill(8)
            if target.exists():
                quarantine=home/'uncommitted'/('shard_'+str(index)+'_'+uuid.uuid4().hex);quarantine.parent.mkdir(exist_ok=True)
                target.rename(quarantine) # only the uncommitted bounded shard, retained as evidence
            target.mkdir(parents=True)
            instruction='ALL' if binding['actual_cutoff']==1<<64 else 'C'+str(binding['actual_cutoff'])
            tick=time.perf_counter();process.stdin.write(str(first)+'\t'+str(count)+'\t'+str(target)+'\t'+str(binding['sample_seed'])+'\t'+instruction+'\n');process.stdin.flush()
            if process.stdout.readline().strip()!='OK':raise ValueError('Native chunk failed: '+str(index))
            peak=max(peak,process_peak_bytes(process) or 0)
            stats=json.loads((target/'stats.json').read_text())
            if stats.get('total_orders')!=binding['total_orders'] or stats['unmatched_foreign_keys']!=0:raise ValueError('Native order/key accounting failed')
            part=native.file_description(target/'sample.csv',True)
            if part['rows']!=stats['sample_rows'] or stats['sample_rows']>stats['rows']:raise ValueError('Native sample row accounting failed')
            for key,value in parse_aggregates(target/'aggregates.tsv').items():merged[key]=merged.get(key,0)+value
            with sample.open('ab') as out,(target/'sample.csv').open('rb') as incoming:
                for block in iter(lambda:incoming.read(4*1024**2),b''):out.write(block);hasher.update(block)
                out.flush();os.fsync(out.fileno())
            files={p.relative_to(home).as_posix():{'bytes':p.stat().st_size,'sha256':native.digest(p)} for p in [target/'stats.json',target/'aggregates.tsv',target/'seeds_after.tsv']}
            record={'shard':index,'first_order':first,'orders':count,'rows':stats['rows'],'sample_rows':stats['sample_rows'],
                    'sample_bytes':part['bytes'],'sample_sha256':part['sha256'],'files':files,'seconds':time.perf_counter()-tick}
            state['committed_shards'].append(record);state['next_shard']=index+1;state['rows']+=stats['rows'];state['sample_rows']+=stats['sample_rows'];state['sample_bytes']+=part['bytes']
            state['sample_sha256']=hasher.hexdigest();state['aggregates']=canonical(merged)
            native.atomic(home/'checkpoint.json',state)
            cleanup_failure=cleanup_committed_sample(target/'sample.csv',index)
            if cleanup_failure:state.setdefault('cleanup_failures',[]).append(cleanup_failure)
            if stop_after is not None and index+1>=stop_after:
                if float(binding['scale'])>2:raise ValueError('Test-only pause forbidden for formal scale')
                native.atomic(home/'lifecycle.json',{'status':'PAUSED_FOR_TEST','plan_sha256':native.object_sha(plan),'sample':str(sample)})
                return {'status':'PAUSED_FOR_TEST','checkpoint':state,'resumed_shards':resumed}
        process.stdin.write('QUIT\n');process.stdin.flush();process.communicate()
        if process.returncode:raise ValueError('Native stream exit failure')
        check_plan(plan);validate_restore(sample,state,binding,home,plan['ranges'],truncate=False)
        if budget_check is not None:budget_check()
        state['complete']=True;native.atomic(home/'checkpoint.json',state)
        native.atomic(home/'lifecycle.json',{'status':'STREAM_COMPLETE','plan_sha256':native.object_sha(plan),'sample':str(sample),'seconds':time.perf_counter()-started,'peak_native_working_set_bytes':peak})
        return {'status':'STREAM_COMPLETE_NOT_AUTHOR_VERIFIED','checkpoint':state,'resumed_shards':resumed,'seconds':time.perf_counter()-started,'peak_native_working_set_bytes':peak}
    except BaseException as error:
        if started_run:native.atomic(home/'lifecycle.json',{'status':'TAINTED','plan_sha256':native.object_sha(plan),'error':repr(error),'sample':str(sample)})
        raise
    finally:
        if process is not None and process.poll() is None:process.kill();process.communicate()
        if log is not None:log.close()
