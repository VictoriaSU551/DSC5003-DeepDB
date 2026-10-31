"""Independent corrected SSB generator; original failed SF500 evidence is frozen."""
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import shutil
import sqlite3
import subprocess
import tarfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/full/ssb/native_v2'
VENDOR=ROOT/'code/vendor/ssb_dbgen'
HEADER_SHA256='ecc57e3e2854e21c339e6ee94d2a2fdce307ce2c7472cd87c9ad7a4ec644d4bd'
GCC=ROOT/'.runtime/w64devkit/bin/gcc.exe'
SOURCES=['build.c','driver.c','bm_utils.c','rnd.c','print.c','load_stub.c','bcd2.c','speed_seed.c','text.c','permute.c']
LAYOUT_SOURCE=r'''#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "dss.h"
#include "dsstypes.h"
int main(void){lineorder_t row;memset(&row,0,sizeof(row));row.quantity=37;strcpy(row.opriority,"4-NOT SPECIFIED");row.ship_priority=0;printf("{\"sizeof_long\":%llu,\"sizeof_void_pointer\":%llu,\"sizeof_lineorder\":%llu,\"priority_offset\":%llu,\"priority_capacity\":%llu,\"ship_priority_offset\":%llu,\"quantity_offset\":%llu,\"quantity_after_copy\":%ld}\n",(unsigned long long)sizeof(long),(unsigned long long)sizeof(void*),(unsigned long long)sizeof(row),(unsigned long long)offsetof(lineorder_t,opriority),(unsigned long long)sizeof(row.opriority),(unsigned long long)offsetof(lineorder_t,ship_priority),(unsigned long long)offsetof(lineorder_t,quantity),row.quantity);return 0;}
'''


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def object_sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    # Read-only share7 monitoring reduces, but does not eliminate, Windows'
    # short read/close replace window. Retry only Win5/32, with a finite bound.
    for attempt in range(21):
        try:os.replace(str(temporary),str(path));break
        except OSError as error:
            if getattr(error,'winerror',None) not in [5,32] or attempt==20:raise
            time.sleep(.05)


LEGACY_RECEIPTS={
    'lp64_8ea76c9f3df61974':'8114b2f1c4a0244ea672629b427a220a1c10d4c2ec815bcac852e746b6ce2983',
    'stock_sf0p001_62c9f982a25e12b3':'9bc45f18e13c329d00eb44e32b8147ee6594b1790376dc15414ba79577f25491',
    'lp64_tiny_aa4dd1e18732e21a':'3396fc02ff4f712f464246e40400d3bd03291d7bc037a8e9edc4a196696c490a',
    'callback_tiny_303215af1aa09f5f':'ef6f59e35f1d65de9a185148fe92b6bd968b5a38f831d5f74e334b8c02a034b0',
    'high_order_0a1fefce2ec71577':'a3c28170219e75011d2491bef61568f2a0bb7c7f6040cd477d8cd680db4cf787'}


def strict_receipt(home,binding,required):
    home=Path(home);required=set(required);receipt=home/'receipt.json'
    record=json.loads(receipt.read_text());life=json.loads((home/'lifecycle.json').read_text())
    if life.get('status')!='PASS' or life.get('receipt_sha256')!=digest(receipt):raise ValueError('Receipt lifecycle is not sealed PASS')
    if record.get('status')!='PASS' or record.get('binding')!=binding or json.loads((home/'receipt_seal.json').read_text())['sha256']!=digest(receipt):raise ValueError('Receipt binding/seal changed')
    if not required or set(record.get('files_sha256',{}))!=required:raise ValueError('Receipt required inventory differs')
    physical={p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}-{'receipt.json','receipt_seal.json','lifecycle.json'}
    if physical!=required:raise ValueError('Receipt physical inventory differs')
    for name in sorted(required):
        if digest(home/name)!=record['files_sha256'][name]:raise ValueError('Receipt artifact changed: '+name)
    return record


def checked_receipt(home,binding,required):
    """Only explicitly pinned pre-transaction WIP evidence can be adopted once."""
    home=Path(home);receipt=home/'receipt.json'
    if (home/'lifecycle.json').exists():return strict_receipt(home,binding,required)
    pin=LEGACY_RECEIPTS.get(home.name)
    if pin is None or digest(receipt)!=pin:raise ValueError('Unrecognized provisional legacy receipt; cannot adopt')
    record=json.loads(receipt.read_text())
    if record['status']!='PASS' or json.loads((home/'receipt_seal.json').read_text())['sha256']!=pin:raise ValueError('Legacy receipt seal changed')
    actual_binding=record.get('binding',record.get('build_binding'))
    if actual_binding!=binding:raise ValueError('Legacy receipt binding changed')
    physical={p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}-{'receipt.json','receipt_seal.json'}
    if not required or physical!=set(required):raise ValueError('Legacy required physical inventory differs')
    if 'files_sha256' in record and set(record['files_sha256'])!=set(required):raise ValueError('Legacy required inventory differs')
    hashes={name:digest(home/name) for name in sorted(required)}
    if 'files_sha256' in record and hashes!=record['files_sha256']:raise ValueError('Legacy artifact changed')
    if 'executable_sha256' in record and hashes.get('dbgen.exe')!=record['executable_sha256']:raise ValueError('Legacy executable changed')
    if 'raw_sha256' in record and hashes.get('lineorder.tbl')!=record['raw_sha256']:raise ValueError('Legacy raw changed')
    adopted=OUTPUT/'adoptions'/home.name
    if (adopted/'receipt.json').exists():
        outer=strict_receipt(adopted,{'legacy_receipt_sha256':pin,'binding':binding},{'artifacts.json'})
        if json.loads((adopted/'artifacts.json').read_text())!=hashes:raise ValueError('Adopted artifact snapshot changed')
    else:
        adopted.parent.mkdir(parents=True,exist_ok=True);adopted.mkdir(exist_ok=False)
        atomic(adopted/'lifecycle.json',{'status':'RUNNING'})
        atomic(adopted/'artifacts.json',hashes)
        publish_receipt(adopted,{'status':'PASS','binding':{'legacy_receipt_sha256':pin,'binding':binding},'legacy_directory':str(home)}, {'artifacts.json'})
    return record


def publish_receipt(home,record,required):
    home=Path(home);record=dict(record);record['files_sha256']={name:digest(home/name) for name in sorted(required)}
    atomic(home/'receipt.json',record);atomic(home/'receipt_seal.json',{'sha256':digest(home/'receipt.json')})
    atomic(home/'lifecycle.json',{'status':'PASS','receipt_sha256':digest(home/'receipt.json')})
    return strict_receipt(home,record['binding'],required)


def toolchain_lock():
    path=ROOT/'code/vendor/ssb_native_v2/cygwin.lock.json'
    if digest(path)!='335fba5f9eb8c2ad6c465f96bd55401811898c9d1a27ce730d9e24c350f65383':raise ValueError('Fixed official Cygwin lock changed')
    return json.loads(path.read_text())


def command(arguments,directory,log,environment=None):
    environment=environment or dict(os.environ,PATH=str(GCC.parent)+os.pathsep+os.environ.get('PATH',''))
    started=time.perf_counter();result=subprocess.run([str(a) for a in arguments],cwd=str(directory),env=environment,
                                                       capture_output=True,text=True,errors='replace')
    atomic(log,{'arguments':[str(a) for a in arguments],'returncode':result.returncode,'stdout':result.stdout,
                'stderr':result.stderr,'seconds':time.perf_counter()-started})
    if result.returncode:raise RuntimeError('Native v2 command failed: '+str(log))
    return result


def compatibility_header(original):
    """Two SSBM priority buffers only; reject every unrecognized original byte."""
    if hashlib.sha256(original).hexdigest()!=HEADER_SHA256:
        raise ValueError('Pinned original header source changed')
    needle=b'char            opriority[MAXAGG_LEN + 1];'
    if original.count(needle)!=3:raise ValueError('Pinned source priority contexts changed')
    # The first two occur in SSBM lineorder_t/order_t. The third is TPCH order_t.
    return original.replace(needle,b'char            opriority[16];',2)


def compatibility_printer(original):
    if hashlib.sha256(original).hexdigest()!='4e0b599dfd59d32a06d317e31a60e1cf36899c870ddccd39845b59f97e44dc1a':
        raise ValueError('Pinned original printer source changed')
    needle=b'PR_STR(fp_l, o->lineorders[i].opriority, O_OPRIO_LEN);'
    if original.count(needle)!=1:raise ValueError('Pinned source priority serialization context changed')
    return original.replace(needle,b'fprintf(fp_l, "%.*s%c", MAXAGG_LEN+1, o->lineorders[i].opriority, SEPARATOR);',1)


def compatibility_rng_usage(original):
    if hashlib.sha256(original).hexdigest()!='7b1fcf7ae693631fcc66b70f389490b18d1c3f5dc6b7ad38e3f89bea7355ba83':
        raise ValueError('Pinned original RNG bookkeeping source changed')
    needle=b'Seed[stream].usage += 1;'
    if original.count(needle)!=1:raise ValueError('Pinned source usage-counter context changed')
    return original.replace(needle,b'if (stream >= 0 && stream <= MAX_STREAM) Seed[stream].usage += 1;',1)


def compatibility_rng_range(original):
    if hashlib.sha256(original).hexdigest()!='7b1fcf7ae693631fcc66b70f389490b18d1c3f5dc6b7ad38e3f89bea7355ba83':
        raise ValueError('Pinned original RNG range source changed')
    needle=b'dRange = DOUBLE_CAST (nHigh - nLow + 1);'
    if original.count(needle)!=1:raise ValueError('Pinned source range-conversion context changed')
    return original.replace(needle,b'dRange = DOUBLE_CAST(nHigh) - DOUBLE_CAST(nLow) + 1.0;',1)


def date_prefix_delta(orders,prefix):
    """Count only two short nonoverlapping tails, never all750M orders."""
    if orders<0 or prefix<0:raise ValueError('RNG count must be nonnegative')
    modulus,multiplier,initial=2147483647,16807,1434868289
    head=initial;tail=initial*pow(multiplier,orders,modulus)%modulus;head_rows=tail_rows=0
    for _ in range(prefix):
        head=head*multiplier%modulus;tail=tail*multiplier%modulus
        head_rows+=1+int(float(head)/modulus*7.)
        tail_rows+=1+int(float(tail)/modulus*7.)
    return {'head_rows':head_rows,'tail_rows':tail_rows,'difference':tail_rows-head_rows}


def package_target(directory,name):
    """Map Cygwin's built-in usr/bin and usr/lib aliases without system mounts."""
    name=str(name).replace('\\','/')
    path=PurePosixPath(name)
    if not name or name.startswith('/') or ':' in name or '..' in path.parts:
        raise ValueError('Unsafe package path: '+name)
    parts=path.parts
    if len(parts)>=2 and parts[:2] in (('usr','bin'),('usr','lib')):parts=parts[1:]
    directory=Path(directory).resolve();target=directory.joinpath(*parts)
    if directory!=target and directory not in target.resolve().parents:raise ValueError('Package path escaped runtime')
    return target


def compatibility_build():
    pins=json.loads((VENDOR/'SOURCES.json').read_text())['files_sha256']
    for name,sha in pins.items():
        if digest(VENDOR/name)!=sha:raise ValueError('Original source changed: '+name)
    corrected=compatibility_header((VENDOR/'dsstypes.h').read_bytes())
    printer=compatibility_printer((VENDOR/'print.c').read_bytes())
    original_rng=(VENDOR/'rnd.c').read_bytes();usage_guard=compatibility_rng_usage(original_rng)
    range_conversion=compatibility_rng_range(original_rng)
    usage=range_conversion.replace(b'Seed[stream].usage += 1;',b'if (stream >= 0 && stream <= MAX_STREAM) Seed[stream].usage += 1;',1)
    flags=['-O2','-std=gnu89','-fcommon','-Wno-implicit-function-declaration','-Wno-int-conversion',
           '-Wno-incompatible-pointer-types','-DWIN32','-DSSBM','-DDB2','-static-libgcc']
    binding={'original_sources':pins,'corrected_header_sha256':hashlib.sha256(corrected).hexdigest(),
             'corrected_printer_sha256':hashlib.sha256(printer).hexdigest(),'serialization_policy':'LP64 legacy priority first11 bytes; safe16-byte storage',
             'corrected_rng_source_sha256':hashlib.sha256(usage).hexdigest(),
             'rng_usage_guard_only_sha256':hashlib.sha256(usage_guard).hexdigest(),
             'rng_range_conversion_only_sha256':hashlib.sha256(range_conversion).hexdigest(),
             'invalid_rng_policy':'Original UnifInt invalid-to0 value stream; suppress invalid usage write only',
             'range_policy':'Convert bounds to double before subtraction+1; preserve LP64 address mapping and every Seed value/usage',
             'compiler_sha256':digest(GCC),'flags':flags,'layout_source_sha256':hashlib.sha256(LAYOUT_SOURCE.encode()).hexdigest()}
    home=OUTPUT/'build'/('compat_'+object_sha(binding)[:16]);receipt=home/'receipt.json'
    required={'sources/'+name for name in pins}|{'dbgen.exe','layout_probe.exe','layout_probe.c','compile_stock.json','compile_layout.json'}
    if receipt.exists():
        return strict_receipt(home,binding,required)
    home.parent.mkdir(parents=True,exist_ok=True)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete native build namespace preserved') from error
    atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        copied=home/'sources';copied.mkdir()
        for name in pins:(copied/name).write_bytes(corrected if name=='dsstypes.h' else printer if name=='print.c' else usage if name=='rnd.c' else (VENDOR/name).read_bytes())
        (home/'layout_probe.c').write_text(LAYOUT_SOURCE,encoding='utf-8')
        command([GCC]+flags+[copied/name for name in SOURCES]+['-o',home/'dbgen.exe','-lm'],home,home/'compile_stock.json')
        command([GCC]+flags+['-I',copied,home/'layout_probe.c','-o',home/'layout_probe.exe'],home,home/'compile_layout.json')
        layout=json.loads(subprocess.check_output([str(home/'layout_probe.exe')],text=True))
        if layout['priority_capacity']!=16 or layout['quantity_after_copy']!=37:raise ValueError('Native priority copy still corrupts quantity')
        record={'status':'PASS','binding':binding,'directory':str(home),'executable':str(home/'dbgen.exe'),'layout':layout,
                'files_sha256':{name:digest(home/name) for name in sorted(required)}}
        atomic(receipt,record);atomic(home/'receipt_seal.json',{'sha256':digest(receipt)})
        atomic(home/'lifecycle.json',{'status':'PASS','receipt_sha256':digest(receipt)});return record
    except BaseException as error:
        atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise


def corrected_tiny_stock():
    build=compatibility_build();home=OUTPUT/('stock_sf0p001_'+object_sha(build['binding'])[:16]);receipt=home/'receipt.json'
    if receipt.exists():
        return checked_receipt(home,build['binding'],{'process.json','lineorder.tbl'})
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete tiny stock namespace preserved') from error
    command([build['executable'],'-s','0.001','-T','l','-f','-b',VENDOR/'dists.dss'],home,home/'process.json')
    rows=[line.split('|') for line in (home/'lineorder.tbl').read_text().splitlines()]
    quantities=[int(row[8]) for row in rows]
    record={'status':'PASS','build_binding':build['binding'],'directory':str(home),'rows':len(rows),
            'raw_sha256':digest(home/'lineorder.tbl'),'zero_quantities':quantities.count(0),'min_quantity':min(quantities),
            'max_quantity':max(quantities),'all_integer_price_formulas_match':all(int(r[9])==
            (90000+(int(r[3])//10)%20001+(int(r[3])%1000)*100)*int(r[8]) for r in rows)}
    if record['zero_quantities'] or not record['all_integer_price_formulas_match']:raise ValueError('Corrected stock numeric constraint failed')
    atomic(receipt,record);atomic(home/'receipt_seal.json',{'sha256':digest(receipt)});return record


def package_closure(metadata,roots):
    selected={};pending=list(roots)
    while pending:
        name=pending.pop()
        if name=='_windows' or name in selected:continue
        if name not in metadata or 'install' not in metadata[name]:raise ValueError('Missing official Cygwin package: '+name)
        selected[name]=metadata[name]
        dependencies=re.sub(r'\([^)]*\)','',metadata[name].get('depends2',''))
        pending.extend(piece.strip() for piece in dependencies.split(',') if piece.strip())
    return selected


def extract_tar_stream(stream,directory):
    count=size=0;links=[]
    with tarfile.open(fileobj=stream,mode='r|') as archive:
        for member in archive:
            if member.name.startswith(('usr/share/','etc/')) and '..' not in PurePosixPath(member.name).parts:continue
            target=package_target(directory,member.name)
            if member.issym() or member.islnk():
                name=member.linkname
                linked=posixpath.normpath(name.lstrip('/') if name.startswith('/') or member.islnk() else posixpath.join(posixpath.dirname(member.name),name))
                link_target=package_target(directory,linked)
                links.append({'path':str(target),'target':str(link_target)});continue
            if not member.isfile():continue
            size+=member.size
            if size>1024**3:raise ValueError('Single official package exceeds1GiB extraction limit')
            target.parent.mkdir(parents=True,exist_ok=True)
            data=archive.extractfile(member).read()
            if len(data)!=member.size:raise ValueError('Incomplete package regular file')
            if target.exists() and target.read_bytes()!=data:raise ValueError('Conflicting official package regular file: '+str(target))
            if not target.exists():target.write_bytes(data)
            count+=1
    return {'regular_files':count,'bytes':size,'links':links}


def setup_cygwin():
    """Extract fixed official packages locally; never run setup/postinstall/mount."""
    lock=toolchain_lock();base=lock['mirror']
    downloads=ROOT/'data/downloads/ssb_native_v2';downloads.mkdir(parents=True,exist_ok=True)
    expected=lock['metadata_sha256'];packages=lock['packages']
    compressed=sum(int(entry['install'].split()[1]) for entry in packages.values())
    if compressed>128*1024**2:raise ValueError('Official LP64 package closure exceeds128MiB download budget')
    binding={'metadata_sha256':expected,'mirror':base,'packages':packages,'extraction_policy':1}
    home=ROOT/'.runtime'/('cygwin_lp64_'+object_sha(binding)[:16]);evidence=OUTPUT/'cygwin'/object_sha(binding)[:16]
    evidence.mkdir(parents=True,exist_ok=True);receipt=evidence/'receipt.json'
    if receipt.exists():
        record=json.loads(receipt.read_text())
        if record['binding']!=binding or json.loads((evidence/'receipt_seal.json').read_text())['sha256']!=digest(receipt):
            raise ValueError('Official LP64 toolchain receipt changed')
        if {p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}!=set(record['runtime_files_sha256']):
            raise ValueError('Exact official LP64 runtime inventory changed')
        for name,sha in record['runtime_files_sha256'].items():
            if digest(home/name)!=sha:raise ValueError('Official LP64 runtime file changed: '+name)
        if digest(evidence/'layout_probe.exe')!=record['probe_sha256']:raise ValueError('LP64 probe changed')
        return record
    atomic(evidence/'lifecycle.json',{'status':'SETUP_RUNNING','binding':binding})
    links=[];total_extracted=0;package_results={}
    try:
        for name,entry in sorted(packages.items()):
            relative,size,sha=entry['install'].split();size=int(size);archive=downloads/Path(relative).name
            if not archive.exists():
                temporary=archive.with_suffix(archive.suffix+'.download.tmp');count=0;checksum=hashlib.sha512()
                with urllib.request.urlopen(base+relative,timeout=60) as remote,temporary.open('wb') as target:
                    while True:
                        block=remote.read(1024**2)
                        if not block:break
                        count+=len(block)
                        if count>size:raise ValueError('Official package exceeds declared length')
                        target.write(block);checksum.update(block)
                if count!=size or checksum.hexdigest()!=sha:raise ValueError('Official package download checksum differs: '+name)
                os.replace(str(temporary),str(archive))
            if archive.stat().st_size!=size or hashlib.sha512(archive.read_bytes()).hexdigest()!=sha:
                raise ValueError('Pinned official package changed: '+name)
            # bsdtar converts zstd/xz archives to a standard uncompressed tar
            # stream. Python validates all paths and writes regular files only.
            convert=subprocess.Popen(['tar','-c','-f','-','@'+str(archive)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                result=extract_tar_stream(convert.stdout,home)
                # tarfile's streaming reader stops at end-of-archive records;
                # drain bsdtar's remaining block padding before closing its pipe.
                while convert.stdout.read(1024**2):pass
            finally:convert.stdout.close()
            error=convert.stderr.read().decode(errors='replace');code=convert.wait()
            if code:raise ValueError('Official package tar conversion failed: '+error)
            total_extracted+=result['bytes'];links+=result.pop('links');package_results[name]=result
            if total_extracted>768*1024**2:raise ValueError('LP64 extracted runtime exceeds768MiB budget')
        # Materialize package aliases by copying already verified local regular
        # files. Never create a symlink, registry entry, mount, or external file.
        unresolved=links
        for _ in range(8):
            remaining=[]
            for link in unresolved:
                target,path=Path(link['target']),Path(link['path'])
                if target.is_file():
                    if path.exists() and digest(path)!=digest(target):raise ValueError('Conflicting local package alias')
                    if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(str(target),str(path))
                else:remaining.append(link)
            if len(remaining)==len(unresolved):break
            unresolved=remaining
        gcc=home/'bin/gcc.exe'
        if not gcc.exists():
            candidates=list((home/'bin').glob('x86_64-pc-cygwin-gcc*.exe'))
            if len(candidates)!=1:raise ValueError('Official LP64 GCC alias cannot be established')
            shutil.copyfile(str(candidates[0]),str(gcc))
        environment=dict(os.environ,PATH=str(home/'bin')+os.pathsep+os.environ.get('PATH',''),LC_ALL='C',TZ='UTC')
        version=command([gcc,'--version'],evidence,evidence/'gcc_version.json',environment)
        source=evidence/'layout_probe.c';source.write_text(LAYOUT_SOURCE,encoding='utf-8')
        arguments=[gcc,'-O2','-std=gnu89','-fcommon','-DLINUX','-DSSBM','-DDB2','-DSUPPORT_64BITS',
                   '-DDSS_HUGE=long','-DHUGE_COUNT=1','-DHUGE_FORMAT="%ld"','-I',VENDOR,source,'-o',evidence/'layout_probe.exe']
        response=evidence/'compile_layout.args'
        def posix_argument(value):
            text=Path(value).as_posix() if isinstance(value,Path) else str(value)
            if len(text)>2 and text[1:3]==':/':text='/cygdrive/'+text[0].lower()+text[2:]
            return shlex.quote(text)
        response.write_text('\n'.join(posix_argument(a) for a in arguments[1:]),encoding='utf-8')
        command([gcc,'@'+response.name],evidence,evidence/'compile_layout.json',environment)
        result=command([evidence/'layout_probe.exe'],evidence,evidence/'run_layout.json',environment);layout=json.loads(result.stdout)
        if layout['sizeof_long']!=8 or layout['quantity_after_copy']!=37:raise ValueError('Actual LP64 original-header oracle failed')
        files={p.relative_to(home).as_posix():digest(p) for p in home.rglob('*') if p.is_file()}
        record={'status':'PASS','binding':binding,'directory':str(home),'compiler':str(gcc),'compiler_version':version.stdout,
                'layout':layout,'probe_sha256':digest(evidence/'layout_probe.exe'),'compressed_bytes':compressed,
                'regular_bytes':total_extracted,'package_results':package_results,'unmaterialized_directory_aliases':unresolved,
                'runtime_files_sha256':files,'scope':'Official project-local LP64 reference; no installer, postinstall, registry or mount action'}
        atomic(receipt,record);atomic(evidence/'receipt_seal.json',{'sha256':digest(receipt)})
        atomic(evidence/'lifecycle.json',{'status':'PASS','receipt_sha256':digest(receipt)});return record
    except BaseException as error:
        atomic(evidence/'lifecycle.json',{'status':'SETUP_FAILED','binding':binding,'error':repr(error)});raise


def cygwin_argument(value):
    text=Path(value).as_posix() if isinstance(value,Path) else str(value)
    if re.match(r'^[a-zA-Z]:[\\/]',text):text=text.replace('\\','/')
    if len(text)>2 and text[1:3]==':/':return '/cygdrive/'+text[0].lower()+text[2:]
    return text


def cygwin_environment(toolchain):
    (Path(toolchain['directory'])/'tmp').mkdir(exist_ok=True)
    result=dict(os.environ,PATH=str(Path(toolchain['directory'])/'bin')+os.pathsep+os.environ.get('PATH',''),LC_ALL='C',TZ='UTC')
    result.pop('BASH_ENV',None);result.pop('ENV',None);return result


def cygwin_compile(arguments,directory,log,toolchain):
    response=Path(log).with_suffix('.args');response.write_text('\n'.join(shlex.quote(cygwin_argument(a)) for a in arguments[1:]),encoding='utf-8')
    return command([arguments[0],'@'+response.name],directory,log,cygwin_environment(toolchain))


def cygwin_run(arguments,directory,log,toolchain):
    script=Path(log).with_suffix('.sh');script.write_bytes(('exec '+' '.join(shlex.quote(cygwin_argument(a)) for a in arguments)+'\n').encode())
    return command([Path(toolchain['directory'])/'bin/bash.exe','--noprofile','--norc',script.name],directory,log,cygwin_environment(toolchain))


def lp64_build():
    toolchain=setup_cygwin();pins=json.loads((VENDOR/'SOURCES.json').read_text())['files_sha256']
    for name,sha in pins.items():
        if digest(VENDOR/name)!=sha:raise ValueError('LP64 original source changed: '+name)
    flags=['-O2','-std=gnu89','-fcommon','-Wno-implicit-function-declaration','-Wno-int-conversion',
           '-Wno-incompatible-pointer-types','-DLINUX','-DSSBM','-DDB2','-DSUPPORT_64BITS',
           '-DDSS_HUGE=long','-DHUGE_COUNT=1','-DHUGE_FORMAT="%ld"','-DO_LARGEFILE=0']
    patches={'dsstypes.h':compatibility_header((VENDOR/'dsstypes.h').read_bytes()),
             'print.c':compatibility_printer((VENDOR/'print.c').read_bytes()),
             'rnd.c':compatibility_rng_usage((VENDOR/'rnd.c').read_bytes())}
    binding={'original_sources':pins,'compatibility_differences_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in patches.items()},
             'reference_policy':'LP64 reference with explicit priority and invalid-usage memory-safety compatibility guards',
             'toolchain_binding':toolchain['binding'],'compiler_sha256':digest(toolchain['compiler']),'flags':flags}
    home=OUTPUT/'build'/('lp64_'+object_sha(binding)[:16]);receipt=home/'receipt.json'
    if receipt.exists():
        result=json.loads(receipt.read_text())
        if (result['binding']!=binding or digest(home/'dbgen.exe')!=result['executable_sha256'] or
            json.loads((home/'receipt_seal.json').read_text())['sha256']!=digest(receipt)):raise ValueError('LP64 original stock build changed')
        for name in pins:
            if (home/'sources'/name).read_bytes()!=patches.get(name,(VENDOR/name).read_bytes()):raise ValueError('LP64 copied source changed: '+name)
        return checked_receipt(home,binding,{'sources/'+name for name in pins}|{'dbgen.exe','compile_stock.json','compile_stock.args'})
    home.parent.mkdir(parents=True,exist_ok=True)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete LP64 build namespace preserved') from error
    copied=home/'sources';copied.mkdir()
    for name in pins:(copied/name).write_bytes(patches.get(name,(VENDOR/name).read_bytes()))
    cygwin_compile([toolchain['compiler']]+flags+[copied/name for name in SOURCES]+['-o',home/'dbgen.exe','-lm'],home,home/'compile_stock.json',toolchain)
    for name,sha in pins.items():
        if digest(VENDOR/name)!=sha:raise ValueError('LP64 original source changed during compilation: '+name)
    result={'status':'PASS','binding':binding,'directory':str(home),'executable':str(home/'dbgen.exe'),
            'executable_sha256':digest(home/'dbgen.exe'),'toolchain_directory':toolchain['directory']}
    atomic(receipt,result);atomic(home/'receipt_seal.json',{'sha256':digest(receipt)});return result


def lp64_tiny_gate():
    lp64=lp64_build();compat=compatibility_build();toolchain=setup_cygwin();tiny=corrected_tiny_stock()
    binding={'lp64_build':lp64['binding'],'compat_build':compat['binding'],'scale':'0.001',
             'fact_sequence':'stock -T l unprimed','io_adapter_version':3}
    home=OUTPUT/('lp64_tiny_'+object_sha(binding)[:16]);receipt=home/'receipt.json'
    required={'compat_a/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','lineorder.tbl','process.json']}|{'lp64_a/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','lineorder.tbl','process.json','process.sh']}|{'lp64_l/'+name for name in ['lineorder.tbl','process.json','process.sh']}
    if receipt.exists():
        return checked_receipt(home,binding,required)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete LP64 tiny namespace preserved') from error
    atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    for mode in ['l','a']:
        directory=home/('lp64_'+mode);directory.mkdir()
        cygwin_run([lp64['executable'],'-s','0.001','-T',mode,'-f','-b',VENDOR/'dists.dss'],directory,directory/'process.json',toolchain)
    corrected_all=home/'compat_a';corrected_all.mkdir()
    command([compat['executable'],'-s','0.001','-T','a','-f','-b',VENDOR/'dists.dss'],corrected_all,corrected_all/'process.json')
    def normalized(path):return Path(path).read_bytes().replace(b'\r\n',b'\n')
    left=normalized(home/'lp64_l/lineorder.tbl');right=normalized(Path(tiny['directory'])/'lineorder.tbl')
    dimensions={name:normalized(home/('lp64_a/'+name+'.tbl'))==normalized(corrected_all/(name+'.tbl')) for name in ['customer','supplier','part','date']}
    if left!=right or not all(dimensions.values()):raise ValueError('Actual LP64 stock differs from corrected Windows fields/dimensions')
    result={'status':'PASS','binding':binding,'lineorder_all17_fields_equal':True,'unprimed_rows':left.count(b'\n'),
            'normalized_fact_sha256':hashlib.sha256(left).hexdigest(),'dimension_equal':dimensions,
            'line_ending_normalization_only':True,'files_sha256':{p.relative_to(home).as_posix():digest(p) for p in home.rglob('*') if p.is_file()}}
    return publish_receipt(home,result,required)


def callback_build(reference=False,stock_printer=False):
    """Serial C object compilation; original main is renamed in its object only."""
    stock=lp64_build() if reference else compatibility_build()
    toolchain=setup_cygwin() if reference else None
    sources=Path(stock['directory'])/'sources';own=ROOT/'code/vendor/ssb_native_v2'
    compiler=Path(toolchain['compiler']) if reference else GCC
    flags=stock['binding']['flags'][:]
    printer=reference or stock_printer
    binding={'stock_binding':stock['binding'],'reference':reference,'stock_printer':printer,
             'native_sources_sha256':{name:digest(own/name) for name in ['native_api.h','native_driver.c']+([] if printer else ['native_callback.cpp','native_sampling.h'])},
             'reference_seed_policy':'independent per-stream modular stride' if reference else 'original sd_order + sd_line nonnegative skip',
             'compiler_sha256':digest(compiler)}
    if not printer:binding['linker_sha256']=digest(GCC.with_name('g++.exe'))
    home=OUTPUT/'build'/(('reference_callback_' if reference else 'callback_')+object_sha(binding)[:16]);receipt=home/'receipt.json'
    required={Path(name).stem+'.o' for name in SOURCES+['native_driver.c']}|{'compile_'+Path(name).stem+'.json' for name in SOURCES+['native_driver.c']}|{'native.exe','link.json'}
    if reference:required|={'compile_'+Path(name).stem+'.args' for name in SOURCES+['native_driver.c']}|{'link.args'}
    if receipt.exists():
        return strict_receipt(home,binding,required)
    home.parent.mkdir(parents=True,exist_ok=True)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete callback namespace preserved') from error
    atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        objects=[]
        for name in SOURCES+['native_driver.c']:
            source=own/name if name=='native_driver.c' else sources/name
            target=home/(Path(name).stem+'.o');args=[compiler]+flags+['-I',sources,'-I',own]
            if name=='driver.c':args+=['-Dmain=ssb_original_main']
            if name=='native_driver.c' and printer:args+=['-DV2_STOCK_PRINTER_REFERENCE']
            if name=='native_driver.c' and reference:args+=['-DV2_DIRECT_SEED_REFERENCE']
            args+=['-c',source,'-o',target]
            if reference:cygwin_compile(args,home,home/('compile_'+Path(name).stem+'.json'),toolchain)
            else:command(args,home,home/('compile_'+Path(name).stem+'.json'))
            objects.append(target)
        executable=home/'native.exe'
        args=([compiler]+objects if printer else [GCC.with_name('g++.exe'),'-O2','-std=c++17','-static-libgcc','-static-libstdc++',own/'native_callback.cpp']+objects)+['-o',executable,'-lm']
        if reference:cygwin_compile(args,home,home/'link.json',toolchain)
        else:command(args,home,home/'link.json')
        if any(digest(own/name)!=sha for name,sha in binding['native_sources_sha256'].items()):raise ValueError('Native source changed during build')
        result={'status':'PASS','binding':binding,'directory':str(home),'executable':str(executable)}
        return publish_receipt(home,result,required)
    except BaseException as error:
        atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise


def normalized_facts(path):
    """Stock terminal separator and CRLF are serialization, not a field."""
    with Path(path).open('rb') as stream:
        for row in stream:
            yield row.rstrip(b'\r\n').removesuffix(b'|') if hasattr(bytes,'removesuffix') else row.rstrip(b'\r\n').rstrip(b'|')


def aggregate_map(path):
    groups={}
    for line in Path(path).read_text().splitlines():
        fields=line.split('\t');key=(int(fields[0]),tuple(fields[1:-1]))
        if key in groups:raise ValueError('Duplicate aggregate key')
        groups[key]=int(fields[-1])
    return groups


def sqlite_truth(dimensions,facts,database):
    """Independent SQL engine over all retained bounded golden rows."""
    connection=sqlite3.connect(str(database))
    try:
        connection.executescript((ROOT/'code/benchmarks/ssb/setup-sql/schema.sql').read_text())
        for table in ['customer','supplier','part','date','lineorder']:
            path=Path(facts) if table=='lineorder' else Path(dimensions)/(table+'.tbl')
            sql_table='dwdate' if table=='date' else table
            count=len(connection.execute('PRAGMA table_info('+sql_table+')').fetchall())
            statement='INSERT INTO '+sql_table+' VALUES ('+','.join('?'*count)+')';batch=[]
            for row in normalized_facts(path):
                fields=row.decode().split('|')
                if len(fields)!=count:raise ValueError('Independent SQLite field count mismatch')
                batch.append(fields)
                if len(batch)>=10000:connection.executemany(statement,batch);batch=[]
            if batch:connection.executemany(statement,batch)
            connection.commit()
        queries=[line.strip() for line in (ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines() if line.strip()]
        if len(queries)!=13:raise ValueError('Expected exactly13 independent SQL statements')
        groups={}
        for index,sql in enumerate(queries):
            for row in connection.execute(sql):
                if row[-1] is None:continue
                if not isinstance(row[-1],int):raise ValueError('Independent SQLite aggregate is not integer')
                groups[(index,tuple(str(v) for v in row[:-1]))]=row[-1]
        return groups
    finally:connection.close()


def callback_tiny_gate():
    prior=lp64_tiny_gate();build=callback_build()
    binding={'lp64_tiny_receipt_sha256':digest(OUTPUT/('lp64_tiny_'+object_sha(prior['binding'])[:16])/'receipt.json'),
             'callback_binding':build['binding'],'full_date_fixture_sha256':digest(ROOT/'data/ssb/sf1_gold/date.tbl'),
             'schema_sha256':digest(ROOT/'code/benchmarks/ssb/setup-sql/schema.sql'),'queries_sha256':digest(ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql')}
    home=OUTPUT/('callback_tiny_'+object_sha(binding)[:16]);receipt=home/'receipt.json'
    required={'dimensions/'+table+'.tbl' for table in ['customer','supplier','part','date']}|{'chunk/'+name for name in ['sample.csv','stats.json','aggregates.tsv','seeds_after.tsv']}|{'process.json','independent.sqlite'}
    if receipt.exists():
        return checked_receipt(home,binding,required)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete callback tiny namespace preserved') from error
    atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    dimensions=home/'dimensions';dimensions.mkdir();chunk=home/'chunk';chunk.mkdir()
    prior_home=OUTPUT/('lp64_tiny_'+object_sha(prior['binding'])[:16])
    for table in ['customer','supplier','part']:shutil.copyfile(str(prior_home/'compat_a'/(table+'.tbl')),str(dimensions/(table+'.tbl')))
    shutil.copyfile(str(ROOT/'data/ssb/sf1_gold/date.tbl'),str(dimensions/'date.tbl'))
    started=time.perf_counter()
    process=subprocess.run([build['executable'],'0.001',str(VENDOR/'dists.dss'),str(dimensions)],
        input='1\t1500\t'+str(chunk)+'\t2020\t1\nQUIT\n',capture_output=True,text=True,cwd=str(home))
    atomic(home/'process.json',{'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr,'seconds':time.perf_counter()-started})
    if process.returncode or process.stdout.splitlines()!=['READY','OK']:raise ValueError('Native tiny callback failed: '+str(home/'process.json'))
    left=list(normalized_facts(chunk/'sample.csv'));right=list(normalized_facts(prior_home/'lp64_l/lineorder.tbl'))
    if left!=right:raise ValueError('Callback differs from actual LP64 stock fact fields')
    truth=sqlite_truth(dimensions,chunk/'sample.csv',home/'independent.sqlite')
    if truth!=aggregate_map(chunk/'aggregates.tsv'):raise ValueError('Callback differs from independent13 SQLite sums')
    result={'status':'PASS','binding':binding,'rows':len(left),'all17_fields_equal':True,
            'independent_sql_queries':13,'all13_exact_integer_aggregates_equal':True,'truth_groups':len(truth),
            'seconds':time.perf_counter()-started,'scope':'Fractional stock facts; standard full date fixture; no previous golden regeneration',
            'files_sha256':{p.relative_to(home).as_posix():digest(p) for p in home.rglob('*') if p.is_file()}}
    return publish_receipt(home,result,required)


def high_order_gate():
    """Stock skip on LLP64 versus independent 64-bit per-stream modular oracle."""
    left=callback_build(stock_printer=True);right=callback_build(reference=True);toolchain=setup_cygwin()
    starts=[1,306000001,613000001,749999937]
    binding={'llp64_binding':left['binding'],'lp64_binding':right['binding'],'scale':'500','orders_per_probe':64,'starts':starts}
    home=OUTPUT/('high_order_'+object_sha(binding)[:16]);receipt=home/'receipt.json'
    required={engine+'_'+str(first)+'/'+name for engine in ['llp64','lp64'] for first in starts for name in ['lineorder.tbl','seeds_after.tsv','process.json']+(['process.sh'] if engine=='lp64' else [])}
    if receipt.exists():
        return checked_receipt(home,binding,required)
    try:home.mkdir(exist_ok=False)
    except FileExistsError as error:raise ValueError('Prior incomplete high-order namespace preserved') from error
    atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    # build.c mk_order under SSBM reads exactly these streams; all other LINE/
    # ORDER streams are row_stop padding only. Both complete trajectories and
    # differing unused states are retained, never silently equated.
    effective={11,13,14,15,16,18,19,20,22,38,40,43};probes=[]
    for first in starts:
        paths=[]
        for label,build in [('llp64',left),('lp64',right)]:
            directory=home/(label+'_'+str(first));directory.mkdir();paths.append(directory)
            args=[build['executable'],'500',VENDOR/'dists.dss',str(first),'64']
            if label=='lp64':cygwin_run(args,directory,directory/'process.json',toolchain)
            else:command(args,directory,directory/'process.json')
        facts=[list(normalized_facts(path/'lineorder.tbl')) for path in paths]
        states=[{int(f[0]):tuple(int(v) for v in f[1:]) for f in (line.split('\t') for line in (path/'seeds_after.tsv').read_text().splitlines())} for path in paths]
        differences=[i for i in range(48) if states[0][i]!=states[1][i]]
        if facts[0]!=facts[1] or any(i in effective for i in differences):raise ValueError('High-index LP64 effective seed or raw field differs')
        if set(differences)-{12,25,39}:raise ValueError('Unclassified high-index seed mismatch: '+repr(differences))
        probes.append({'first_order':first,'rows':len(facts[0]),'raw_normalized_sha256':hashlib.sha256(b'\n'.join(facts[0])+b'\n').hexdigest(),
                       'unused_seed_differences':differences,'effective_streams':sorted(effective)})
    result={'status':'PASS','binding':binding,'order_starts':starts,'all17_fields_equal':True,'all_effective_seeds_equal':True,
            'unused_differences_classified':True,'probes':probes,
            'unused_policy':'12/25 unused SSBM comment padding may overflow LLP64 skip;39 HVAR unused and not skipped by sd_line. No RNG change.',
            'files_sha256':{p.relative_to(home).as_posix():digest(p) for p in home.rglob('*') if p.is_file()}}
    return publish_receipt(home,result,required)


def dimension_build(reference=False):
    stock=callback_build(reference=reference,stock_printer=True);home_stock=Path(stock['directory'])
    source=ROOT/'code/vendor/ssb_native_v2/native_dimensions.c';toolchain=setup_cygwin() if reference else None
    compiler=Path(toolchain['compiler']) if reference else GCC
    flags=stock['binding']['stock_binding']['flags'];original=lp64_build() if reference else compatibility_build()
    binding={'stock_object_binding':stock['binding'],'dimension_adapter_sha256':digest(source),'compiler_sha256':digest(compiler)}
    home=OUTPUT/'build'/('dimensions_'+object_sha(binding)[:16]);required={'native_dimensions.o','native.exe','compile.json','link.json'}
    if reference:required|={'compile.args','link.args'}
    if (home/'receipt.json').exists():return strict_receipt(home,binding,required)
    home.parent.mkdir(parents=True,exist_ok=True);home.mkdir(exist_ok=False);atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        compile_args=[compiler]+flags+['-I',Path(original['directory'])/'sources','-c',source,'-o',home/'native_dimensions.o']
        link_args=[compiler]+[home_stock/(Path(name).stem+'.o') for name in SOURCES]+[home/'native_dimensions.o','-o',home/'native.exe','-lm']
        for args,name in [(compile_args,'compile'),(link_args,'link')]:
            if reference:cygwin_compile(args,home,home/(name+'.json'),toolchain)
            else:command(args,home,home/(name+'.json'))
        return publish_receipt(home,{'status':'PASS','binding':binding,'directory':str(home),'executable':str(home/'native.exe')},required)
    except BaseException as error:
        atomic(home/'lifecycle.json',{'status':'TAINTED','error':repr(error),'binding':binding});raise


def file_description(path,rows=False):
    path=Path(path);result={'path':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}
    if rows:
        with path.open('rb') as stream:result['rows']=sum(block.count(b'\n') for block in iter(lambda:stream.read(4*1024**2),b''))
    return result


def corrected_scale_gate(scale):
    """Fresh corrected SF1/SF2 science. No old SF1 or SF2 input is regenerated."""
    if type(scale) is not int or scale not in [1,2]:raise ValueError('Only bounded scales1/2 are allowed')
    build=callback_build();lp64=lp64_build();win_dim=dimension_build();lp_dim=dimension_build(True);toolchain=setup_cygwin()
    binding={'scale':scale,'callback_binding':build['binding'],'lp64_stock_binding':lp64['binding'],
             'windows_dimension_binding':win_dim['binding'],'lp64_dimension_binding':lp_dim['binding'],
             'chunk_orders':187500,'schema_sha256':digest(ROOT/'code/benchmarks/ssb/setup-sql/schema.sql'),
             'queries_sha256':digest(ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql'),'adapter_version':1}
    home=OUTPUT/('corrected_sf'+str(scale)+'_'+object_sha(binding)[:16]);receipt=home/'receipt.json'
    chunk_count=scale*8
    required={'lp64_dimensions/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json','process.sh']}|{'dimensions/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json']}|{'stock/process.json','stock/process.sh','independent_truth.json','temporary_artifacts.json','callback_process.json'}|{'chunks/'+str(i).zfill(4)+'/'+name for i in range(chunk_count) for name in ['aggregates.tsv','stats.json','seeds_after.tsv']}
    if receipt.exists():return strict_receipt(home,binding,required)
    home.parent.mkdir(parents=True,exist_ok=True);home.mkdir(exist_ok=False);atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    started=time.perf_counter();process=None
    try:
        for directory,dim in [('dimensions',win_dim),('lp64_dimensions',lp_dim)]:
            target=home/directory;target.mkdir()
            if directory=='dimensions':command([dim['executable'],str(scale),VENDOR/'dists.dss'],target,target/'process.json')
            else:cygwin_run([dim['executable'],str(scale),VENDOR/'dists.dss'],target,target/'process.json',toolchain)
        dimension_comparison={}
        for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv']:
            a=(home/'dimensions'/name).read_bytes().replace(b'\r\n',b'\n');b=(home/'lp64_dimensions'/name).read_bytes().replace(b'\r\n',b'\n')
            dimension_comparison[name]=a==b
        if not all(dimension_comparison.values()):raise ValueError('Corrected full dimension or valid Seed trajectory differs from LP64')
        stock=home/'stock';stock.mkdir()
        cygwin_run([lp64['executable'],'-s',str(scale),'-T','l','-f','-b',VENDOR/'dists.dss'],stock,stock/'process.json',toolchain)
        temporary={'stock':file_description(stock/'lineorder.tbl',True)}
        truth=sqlite_truth(home/'dimensions',stock/'lineorder.tbl',home/'independent.sqlite')
        atomic(home/'independent_truth.json',[{'query_no':q,'group':list(group),'value':value} for (q,group),value in sorted(truth.items())])
        temporary['sqlite']=file_description(home/'independent.sqlite')
        process=subprocess.Popen([build['executable'],str(scale),str(VENDOR/'dists.dss'),str(home/'dimensions')],cwd=str(home),
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if process.stdout.readline().strip()!='READY':raise ValueError('Callback did not initialize')
        native_started=time.perf_counter();merged={};rows=0;sample_sha=hashlib.sha256();stock_rows=iter(normalized_facts(stock/'lineorder.tbl'));chunks=[]
        for index in range(chunk_count):
            target=home/'chunks'/str(index).zfill(4);target.mkdir(parents=True)
            process.stdin.write(str(index*187500+1)+'\t187500\t'+str(target)+'\t20261030\t1\n');process.stdin.flush()
            if process.stdout.readline().strip()!='OK':raise ValueError('Callback chunk failed')
            chunk_rows=0
            for row in normalized_facts(target/'sample.csv'):
                if row!=next(stock_rows,None):raise ValueError('Corrected callback differs from original LP64 all17 fields at row '+str(rows))
                sample_sha.update(row+b'\n');rows+=1;chunk_rows+=1
            stats=json.loads((target/'stats.json').read_text())
            if stats['rows']!=chunk_rows or stats['sample_rows']!=chunk_rows:raise ValueError('Retain-all chunk row accounting differs')
            for key,value in aggregate_map(target/'aggregates.tsv').items():merged[key]=merged.get(key,0)+value
            chunks.append({'shard':index,'sample':file_description(target/'sample.csv',True)})
            (target/'sample.csv').unlink() # bounded new temporary oracle, never failed old data
        native_seconds=time.perf_counter()-native_started
        if next(stock_rows,None) is not None:raise ValueError('Callback omitted final stock facts')
        process.stdin.write('QUIT\n');process.stdin.flush();stdout,stderr=process.communicate();code=process.returncode
        atomic(home/'callback_process.json',{'returncode':code,'stdout':stdout,'stderr':stderr,'seconds':native_seconds,'all_rows_formatted_for_oracle':True})
        if code or merged!=truth:raise ValueError('Corrected callback differs from independent13 exact integer SQL aggregates')
        temporary['chunks']=chunks;temporary['disposition']='Only these newly generated full fact/SQLite temporaries removed after independent comparisons; original failed data unchanged'
        atomic(home/'temporary_artifacts.json',temporary)
        (stock/'lineorder.tbl').unlink();(home/'independent.sqlite').unlink()
        result={'status':'PASS','binding':binding,'scale':scale,'rows':rows,'all17_fields_equal':True,'all_dimensions_equal':True,
                'all13_exact_integer_aggregates_equal':True,'truth_groups':len(truth),'dimension_comparison':dimension_comparison,
                'normalized_facts_sha256':sample_sha.hexdigest(),'seconds':time.perf_counter()-started,
                'retain_all_callback_seconds_including_python_byte_gate':native_seconds,'lp64_stock_seconds':json.loads((stock/'process.json').read_text())['seconds']}
        return publish_receipt(home,result,required)
    except BaseException as error:
        if process is not None and process.poll() is None:process.kill();process.communicate()
        atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise


def verified_sf1_gate():
    """Read-only original corrected SF1 all-row gate, before integer sampling.

    SF1 used p=1, for which both predicates retain every row. The SF2 gate uses
    the final integer sampler and its complete final build binding. This function
    never reinterprets the older failed Windows generator's SF1 artifacts.
    """
    home=OUTPUT/'corrected_sf1_6c34ba3b7ba3246b';receipt=home/'receipt.json'
    if digest(receipt)!='b8f7aa67a942b16e0372a3c0d32203c3ba87d50b831bd9b8e4170e0bb3c52544':raise ValueError('Preserved corrected SF1 receipt changed')
    record=json.loads(receipt.read_text())
    required={'lp64_dimensions/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json','process.sh']}|{'dimensions/'+name for name in ['customer.tbl','supplier.tbl','part.tbl','date.tbl','dimension_seeds.tsv','process.json']}|{'stock/process.json','stock/process.sh','independent_truth.json','temporary_artifacts.json','callback_process.json'}|{'chunks/'+str(i).zfill(4)+'/'+name for i in range(8) for name in ['aggregates.tsv','stats.json','seeds_after.tsv']}
    return strict_receipt(home,record['binding'],required)


def high_callback_gate():
    stock=high_order_gate();native=callback_build();own=ROOT/'code/vendor/ssb_native_v2'
    binding={'high_stock_binding':stock['binding'],'actual_callback_binding':native['binding'],'harness_sha256':digest(own/'native_field_probe.cpp')}
    home=OUTPUT/('high_callback_'+object_sha(binding)[:16]);required={'probe.exe','compile.json'}|{str(first)+'/'+name for first in [1,306000001,613000001,749999937] for name in ['lineorder.tbl','seeds_after.tsv','process.json']}
    if (home/'receipt.json').exists():return strict_receipt(home,binding,required)
    home.mkdir(exist_ok=False);atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        objects=[Path(native['directory'])/(Path(name).stem+'.o') for name in SOURCES+['native_driver.c']]
        command([GCC.with_name('g++.exe'),'-O2','-std=c++17','-static-libgcc','-static-libstdc++',own/'native_field_probe.cpp']+objects+['-o',home/'probe.exe','-lm'],home,home/'compile.json')
        previous=OUTPUT/('high_order_'+object_sha(stock['binding'])[:16]);maximum=0;probes=[]
        for first in [1,306000001,613000001,749999937]:
            target=home/str(first);target.mkdir();command([home/'probe.exe','500',VENDOR/'dists.dss',str(first),'64'],target,target/'process.json')
            actual=list(normalized_facts(target/'lineorder.tbl'));expected=list(normalized_facts(previous/('lp64_'+str(first))/'lineorder.tbl'))
            if actual!=expected:raise ValueError('Actual high callback view/formatter differs from LP64 stock')
            maximum=max(maximum,max(int(row.split(b'|',1)[0]) for row in actual));probes.append({'first_order':first,'rows':len(actual)})
        return publish_receipt(home,{'status':'PASS','binding':binding,'actual_callback_formatter_all17_fields_equal':True,
           'maximum_observed_orderkey':maximum,'probes':probes,'scope':'Exact production C view and emit_sample formatter; no dimensions/aggregates used in this separate high-key audit harness'},required)
    except BaseException as error:
        atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise


def native_sampling_gate():
    own=ROOT/'code/vendor/ssb_native_v2'
    source=r'''#include "native_sampling.h"
#include <cstdio>
int main(){const char *p[]={"C0","C1","C1","C100","C100","C18446744073709551615","C18446744073709551615","ALL"};
uint64_t h[]={0,0,1,99,100,UINT64_MAX-1,UINT64_MAX,UINT64_MAX};
for(int i=0;i<8;++i)std::printf("%d\n",ssb_parse_selection(p[i]).keep(h[i])?1:0);
try{ssb_parse_selection("0.5");return 3;}catch(const std::exception &){}
try{ssb_parse_selection("C18446744073709551616");return 4;}catch(const std::exception &){}
for(uint64_t i=1;i<=7;++i)std::printf("%llu\n",(unsigned long long)ssb_mix(UINT64_C(20261030)^ssb_mix(1)^ssb_mix(i+UINT64_C(0xd1b54a32d192ed03))));
return 0;}
'''
    binding={'sampling_header_sha256':digest(own/'native_sampling.h'),'compiler_sha256':digest(GCC.with_name('g++.exe')),
             'probe_sha256':hashlib.sha256(source.encode()).hexdigest()}
    home=OUTPUT/('integer_sampling_'+object_sha(binding)[:16]);required={'probe.cpp','probe.exe','compile.json'}
    if (home/'receipt.json').exists():return strict_receipt(home,binding,required)
    home.mkdir(exist_ok=False);atomic(home/'lifecycle.json',{'status':'RUNNING','binding':binding})
    try:
        (home/'probe.cpp').write_bytes(source.encode())
        command([GCC.with_name('g++.exe'),'-O2','-std=c++17','-static-libgcc','-static-libstdc++','-I',own,home/'probe.cpp','-o',home/'probe.exe'],home,home/'compile.json')
        values=[int(x) for x in subprocess.check_output([str(home/'probe.exe')],text=True).splitlines()]
        mask=(1<<64)-1
        def mix(x):
            x=(x+0x9e3779b97f4a7c15)&mask;x=((x^(x>>30))*0xbf58476d1ce4e5b9)&mask;x=((x^(x>>27))*0x94d049bb133111eb)&mask;return x^(x>>31)
        expected=[0,1,0,1,0,1,0,1]+[mix(20261030^mix(1)^mix(i+0xd1b54a32d192ed03)) for i in range(1,8)]
        if values!=expected:raise ValueError('Native exact cutoff or hash differs from independent integer oracle')
        return publish_receipt(home,{'status':'PASS','binding':binding,'boundary_cases':8,'all_cases_match_python_integer_oracle':True,
                                     'native_output':values,'python_integer_output':expected,'floating_and_out_of_range_inputs_rejected':True},required)
    except BaseException as error:
        atomic(home/'lifecycle.json',{'status':'TAINTED','binding':binding,'error':repr(error)});raise
