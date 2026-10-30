"""Isolated original Verdict SIGMOD18 build and existing-uniform-sample contract."""
import argparse
import base64
import ctypes
from ctypes import wintypes
import difflib
from fractions import Fraction
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/verdict'
OUT=ROOT/'output/full/verdict'
DOWNLOAD=ROOT/'data/downloads/verdict_runtime'
ARCHIVE=ROOT/'data/downloads/baselines/verdict18/b59209f626d278687ea0a801295b41064c7fecbb.zip'
SOURCE_SHA='72b068ce7dc501e065229b2b43eee19bd3777127e973db436256fd9770ae23c9'
GIB=1024**3


def digest(path,algorithm='sha256'):
    result=hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):result.update(block)
    return result.hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


def verify_original_source(path=ARCHIVE):
    if digest(path)!=SOURCE_SHA:raise ValueError('original source seal changed')
    return dict(path=Path(path).relative_to(ROOT).as_posix(),sha256=SOURCE_SHA,bytes=Path(path).stat().st_size)


def extract_safe(archive,destination,strip_first=False):
    destination=Path(destination).resolve()
    with zipfile.ZipFile(str(archive)) as source:
        plan=[]
        for item in source.infolist():
            relative=Path(item.filename)
            if relative.is_absolute() or '..' in relative.parts or '\\' in item.filename or ':' in item.filename:
                raise ValueError('unsafe archive member')
            if strip_first:relative=Path(*relative.parts[1:])
            target=(destination/relative).resolve()
            if target!=destination and destination not in target.parents:raise ValueError('unsafe archive target')
            plan.append((item,target))
        for item,target in plan:
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.open(item) as inp,target.open('wb') as out:shutil.copyfileobj(inp,out)


def sample_contract(sample_rows,population_rows):
    if type(sample_rows) is not int or type(population_rows) is not int or not 0<sample_rows<=population_rows:
        raise ValueError('exact positive sample/population row counts required')
    probability=Fraction(sample_rows,population_rows)
    return dict(execution_scope='EXISTING_UNIFORM_SAMPLE_ONLY',original_rows_materialized=0,
                sample_rows=sample_rows,population_rows=population_rows,
                probability_numerator=probability.numerator,probability_denominator=probability.denominator,
                query_truth_used_for_registration=False,
                information_budget=['schema','retained uniform sample','sample row count','population row count'],
                excluded_claims=['original-table sampling cost','full-table end-to-end latency','author snapshot','stratified sampling'])


def owned_disk_bytes():
    roots=[DATA,OUT,DOWNLOAD,ROOT/'.runtime/java',ROOT/'.runtime/maven']
    return sum(p.stat().st_size for r in roots if r.exists() for p in r.rglob('*') if p.is_file())


def fetch(url,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return
    temporary=path.with_suffix(path.suffix+'.part')
    # CPython3.8's bundled TLS failed on this host; Windows curl verified the
    # same official HTTPS endpoints with the system TLS stack.
    subprocess.run(['curl.exe','--silent','--show-error','--fail','--location','--retry','2',
                    '--max-time','300','--max-filesize',str(512*1024**2),'--output',str(temporary),url],
                   check=True,timeout=310)
    os.replace(str(temporary),str(path))
    if owned_disk_bytes()>8*GIB:raise ValueError('new Verdict disk budget exceeds8GiB')


def setup_runtime():
    entries=[dict(name='jdk8',base='https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u462-b08/',
                  file='OpenJDK8U-jdk_x64_windows_hotspot_8u462b08.zip',suffix='.sha256.txt',algorithm='sha256',
                  pinned='c6c2d8e6c2cbf0b4ddb707e6edb9a00d8a7b04e9ed6dda7e62d43dc4d83d342c',
                  directory=ROOT/'.runtime/java'),
             dict(name='maven',base='https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/',
                  checksum_base='https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/',
                  file='apache-maven-3.9.11-bin.zip',suffix='.sha512',algorithm='sha512',directory=ROOT/'.runtime/maven')]
    entries[1]['pinned']='03e2d65d4483a3396980629f260e25cac0d8b6f7f2791e4dc20bc83f9514db8d0f05b0479e699a5f34679250c49c8e52e961262ded468a20de0be254d8207076'
    records=[]
    for item in entries:
        path=DOWNLOAD/item['file'];checksum=DOWNLOAD/(item['file']+item['suffix'])
        checksum_base=item.get('checksum_base',item['base'])
        fetch(checksum_base+checksum.name,checksum)
        expected=checksum.read_text().split()[0].lower()
        if expected!=item['pinned']:raise ValueError('official checksum differs from fixed release pin')
        fetch(item['base']+path.name,path)
        if digest(path,item['algorithm'])!=expected:raise ValueError('official runtime checksum mismatch')
        directory=item['directory'];receipt=directory/(item['name']+'_verified.json')
        if not receipt.exists():
            extract_safe(path,directory)
            atomic_json(receipt,dict(url=item['base']+path.name,checksum_url=checksum_base+checksum.name,
                                    algorithm=item['algorithm'],expected=expected,sha256=digest(path),bytes=path.stat().st_size))
        records.append(json.loads(receipt.read_text()))
    atomic_json(OUT/'runtime_provenance.json',dict(status='OFFICIAL_CHECKSUMS_VERIFIED',assets=records))
    return records


def process_rss(pid):
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ['peak','working','p1','p2','p3','p4','page','peakpage']]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);api=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return 0
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    try:
        if not api.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):return 0
        return max(int(counters.working),int(counters.peak))
    finally:kernel.CloseHandle(handle)


def run_bounded(command,stem,timeout=1200,cwd=ROOT):
    OUT.mkdir(parents=True,exist_ok=True);started=time.monotonic();peak=0;reason=None
    if (OUT/(stem+'.stdout.log')).exists():
        attempt=OUT/'attempts'/(stem+'_'+digest(OUT/(stem+'.stdout.log'))[:12]);attempt.mkdir(parents=True,exist_ok=True)
        for suffix in ['.stdout.log','.stderr.log','.json']:
            old=OUT/(stem+suffix)
            if old.exists():shutil.copy2(str(old),str(attempt/old.name))
    next_disk_check=time.monotonic()+15
    with (OUT/(stem+'.stdout.log')).open('w',encoding='utf-8') as out,(OUT/(stem+'.stderr.log')).open('w',encoding='utf-8') as err:
        process=subprocess.Popen(list(map(str,command)),cwd=str(cwd),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        while process.poll() is None:
            peak=max(peak,process_rss(process.pid))
            if peak>GIB:reason='JAVA_RSS_EXCEEDS_1_GIB'
            elif time.monotonic()-started>timeout:reason='TIMEOUT'
            elif time.monotonic()>next_disk_check:
                if owned_disk_bytes()>8*GIB:reason='OWNED_DISK_EXCEEDS_8_GIB'
                next_disk_check=time.monotonic()+15
            if reason:process.terminate();break
            time.sleep(.1)
        peak=max(peak,process_rss(process.pid))
        code=process.wait()
    record=dict(status='PASS' if code==0 and reason is None else 'FAILED',exit_code=code,reason=reason,
                seconds=time.monotonic()-started,peak_rss_bytes=peak,owned_disk_bytes=owned_disk_bytes(),command=list(map(str,command)))
    atomic_json(OUT/(stem+'.json'),record);print(json.dumps(record),flush=True);return record


def prepare_build():
    verify_original_source();destination=DATA/'b'
    if not (destination/'pom.xml').exists():extract_safe(ARCHIVE,destination,strip_first=True)
    with zipfile.ZipFile(str(ARCHIVE)) as source:
        prefix=source.namelist()[0];records=[]
        for item in source.infolist():
            if item.is_dir():continue
            path=destination/item.filename[len(prefix):]
            expected=hashlib.sha256(source.read(item)).hexdigest()
            if digest(path)!=expected:raise ValueError('extracted original source byte changed: '+str(path))
            records.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=expected))
    atomic_json(OUT/'source_files.json',dict(archive_sha256=SOURCE_SHA,files=records))
    settings=DATA/'settings.xml'
    settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><mirrors><mirror><id>isolated-central-https</id><mirrorOf>*</mirrorOf><url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>')
    return destination,settings


def prepare_pg_build(destination):
    verify_original_source();destination=Path(destination)
    if not (destination/'pom.xml').exists():extract_safe(ARCHIVE,destination,strip_first=True)
    with zipfile.ZipFile(str(ARCHIVE)) as source:
        prefix=source.namelist()[0];member=prefix+'core/pom.xml'
        original=source.read(member).decode();removed=[]
        ns={'m':'http://maven.apache.org/POM/4.0.0'}
        def dependency(match):
            text=match.group(0);node=ET.fromstring(text)
            group=node.findtext('groupId')
            if not group.startswith('com.cloudera.'):return text
            if node.findtext('scope')!='test':raise ValueError('refuse removal of non-test dependency')
            removed.append(dict(group=group,artifact=node.findtext('artifactId'),version=node.findtext('version'),scope='test'))
            return ''
        patched=re.sub(r'<dependency>.*?</dependency>',dependency,original,flags=re.S)
        if len(removed)!=16:raise ValueError('unexpected original test dependency inventory')
        pom=destination/'core/pom.xml'
        if pom.read_bytes() not in [original.encode(),patched.encode()]:raise ValueError('working POM has an unrelated change')
        pom.write_bytes(patched.encode())
        for item in source.infolist():
            if not item.filename.endswith('.java'):continue
            if digest(destination/item.filename[len(prefix):])!=hashlib.sha256(source.read(item)).hexdigest():
                raise ValueError('original Java source changed')
    patch=''.join(difflib.unified_diff(original.splitlines(True),patched.splitlines(True),fromfile='original/core/pom.xml',tofile='postgres-build/core/pom.xml'))
    (destination/'postgres-test-dependencies.patch').write_text(patch)
    return dict(original_zip_sha256=SOURCE_SHA,original_pom_sha256=hashlib.sha256(original.encode()).hexdigest(),
                patched_pom_sha256=digest(pom),removed_test_dependencies=removed,java_sources_unchanged=True,
                adaptation='Remove16 unavailable Impala/Hive JDBC test-scope dependencies only; tests disabled; all Java and scientific algorithms unchanged')


def maven_command(goals,postgres_build=False):
    java=next((ROOT/'.runtime/java').glob('*/bin/java.exe'))
    maven=next((ROOT/'.runtime/maven').glob('apache-maven-*'))
    boot=next((maven/'boot').glob('plexus-classworlds-*.jar'))
    build,settings=prepare_build()
    if postgres_build:
        build=DATA/'p';record=prepare_pg_build(build);atomic_json(OUT/'postgres_build_patch.json',record)
    return [java,'-Xmx384m','-XX:MaxMetaspaceSize=192m','-XX:MaxDirectMemorySize=128m','-XX:ReservedCodeCacheSize=64m',
            '-Dmaven.home='+str(maven),'-Dmaven.multiModuleProjectDirectory='+str(build),
            '-Dclassworlds.conf='+str(maven/'bin/m2.conf'),'-cp',boot,'org.codehaus.plexus.classworlds.launcher.Launcher',
            '-B','-s',settings,'-Dmaven.repo.local='+str(DATA/'m2'),'-Dmaven.test.skip=true','-DskipTests',
            '-pl','core','-am']+goals


def runtime_jar():
    return next((DATA/'p/jars').glob('verdict-spark-lib-0.4.7*.jar'),DATA/'p/jars/NOT_BUILT.jar')


GATE_EXPRESSIONS=[
    'SELECT COUNT(*) FROM {table}','SELECT SUM(x) FROM {table}','SELECT AVG(x) FROM {table}',
    'SELECT grp, COUNT(*) FROM {table} GROUP BY grp',
    'SELECT grp, SUM(x) FROM {table} WHERE y>3 GROUP BY grp',
    'SELECT grp, AVG(x) FROM {table} WHERE x>=0 GROUP BY grp',
    'SELECT SUM(x*y) FROM {table} WHERE y<10','SELECT SUM(x)-SUM(y) FROM {table}',
    'SELECT COUNT(x) FROM {table} WHERE x>0','SELECT COUNT(*) FROM {table} WHERE x IS NULL',
    'SELECT SUM(x) FROM {table}','SELECT SUM(y) FROM {table}']


def compound_sum_adapter(left,right):
    return None if left is None or right is None else left-right


def run_gate():
    import psycopg2
    from psycopg2 import sql
    jar=runtime_jar()
    if not jar.exists():raise ValueError('original Java build is not ready')
    binding=dict(source_sha256=SOURCE_SHA,jar_sha256=digest(jar),driver_sha256=digest(__file__),
                 bridge_sha256=digest(ROOT/'code/full_verdict_gate.java'),population_rows=5000,ratio=.2,
                 error_bound_method='nobound',queries=GATE_EXPRESSIONS)
    receipt=OUT/'golden_gate.json'
    if receipt.exists():
        previous=json.loads(receipt.read_text())
        if previous.get('binding')==binding and previous.get('status')=='PASS_STANDARD_AND_REGISTERED_SAMPLE_EQUIVALENCE':
            for item in previous['artifacts']:
                if digest(ROOT/item['path'])!=item['sha256']:raise ValueError('golden gate artifact changed')
            return previous
    admin=psycopg2.connect(host='localhost',port=55432,user='postgres',dbname='postgres',connect_timeout=10,
                           options='-c statement_timeout=30000',application_name='deepdb_verdict_gate_admin')
    admin.autocommit=True
    try:
        with admin.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s',('deepdb_verdict',))
            if cursor.fetchone() is None:cursor.execute('CREATE DATABASE deepdb_verdict')
    finally:admin.close()
    connection=psycopg2.connect(host='localhost',port=55432,user='postgres',dbname='deepdb_verdict',connect_timeout=10,
                              options='-c statement_timeout=30000 -c work_mem=16384',application_name='deepdb_verdict_gate')
    connection.autocommit=True
    reuse=False
    with connection.cursor() as cursor:
        if receipt.exists():
            old=json.loads(receipt.read_text())
            retained=next((a for a in old.get('artifacts',[]) if a['path'].endswith('golden_retained_sample.csv')),None)
            if retained is not None and digest(ROOT/retained['path'])==retained['sha256']:
                stream=io.StringIO();cursor.copy_expert('COPY(SELECT * FROM public_verdict.vs_v_population_uf_0_2000 ORDER BY id) TO STDOUT WITH CSV HEADER',stream)
                if hashlib.sha256(stream.getvalue().encode()).hexdigest()!=retained['sha256']:
                    raise ValueError('already created official sample changed')
                reuse=True
        if not reuse:
            cursor.execute('DROP TABLE IF EXISTS public.v_population,public.v_imported')
            cursor.execute('CREATE TABLE public.v_population(id integer,grp text,x double precision,y double precision)')
            cursor.execute("INSERT INTO public.v_population SELECT i, CASE WHEN i%13=0 THEN NULL ELSE 'g'||(i%5)::text END, "
                           'CASE WHEN i%7=0 THEN NULL ELSE ((i%101)-50)::double precision/10 END, '
                           'CASE WHEN i%11=0 THEN NULL ELSE (i%17)::double precision END FROM generate_series(1,5000) AS i')
            cursor.execute('CREATE TABLE public.v_imported(LIKE public.v_population)')
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public_verdict' AND tablename ~ '^vt[0-9]+_[0-9]+$'")
        for (name,) in cursor.fetchall():cursor.execute(sql.SQL('DROP TABLE public_verdict.{}').format(sql.Identifier(name)))
    java=next((ROOT/'.runtime/java').glob('*/bin/java.exe'));javac=java.with_name('javac.exe')
    classes=DATA/'bridge_classes';classes.mkdir(parents=True,exist_ok=True)
    compiled=run_bounded([javac,'-J-Xmx256m','-encoding','UTF-8','-cp',jar,'-d',classes,ROOT/'code/full_verdict_gate.java'],
                         'bridge_compile',timeout=90)
    if compiled['exit_code']!=0:raise ValueError('bridge compilation failed; see isolated log')
    result_path=OUT/'golden_result.tsv'
    execution=run_bounded([java,'-Xmx384m','-XX:MaxMetaspaceSize=192m','-cp',str(classes)+os.pathsep+str(jar),
                           'full_verdict_gate',result_path]+(['reuse'] if reuse else []),'golden_java',timeout=180)
    if execution['exit_code']!=0:raise ValueError('original Java gate execution failed; see isolated log')
    values={'standard':{},'registered':{}};errors=[];sample=None;successes=set()
    for line in result_path.read_text().splitlines():
        fields=line.split('\t')
        if fields[0]=='SAMPLE':sample=fields[1:]
        elif fields[0]=='ERROR':errors.append(fields[1:])
        elif fields[0]=='OK':successes.add((fields[1],int(fields[2])))
        elif fields[0]=='ROW':
            row=[None if v=='N' else base64.b64decode(v[1:]).decode() for v in fields[3:]]
            values[fields[1]].setdefault(int(fields[2]),[]).append(row)
    if sample is None:raise ValueError('official CREATE SAMPLE did not return retained sample metadata')
    sample_name,import_name,n,N=sample;n,N=int(n),int(N)
    if not all(re.fullmatch(r'[a-z_0-9]+\.[a-z_0-9]+',name) for name in [sample_name,import_name]):
        raise ValueError('unexpected engine sample identifier')
    checks=[]
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM ((TABLE '+sample_name+' EXCEPT ALL TABLE '+import_name+') UNION ALL '
                       '(TABLE '+import_name+' EXCEPT ALL TABLE '+sample_name+')) AS differences')
        same=cursor.fetchone()[0]==0
        cursor.execute('SELECT COUNT(*) FROM public.v_imported');empty=cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*),MIN(verdict_vprob),MAX(verdict_vprob),MIN(verdict_vpart),MAX(verdict_vpart) FROM '+sample_name)
        sample_check=cursor.fetchone()
        if sample_check[0]!=n or not math.isclose(sample_check[1],n/N,rel_tol=1e-12) or sample_check[1]!=sample_check[2]:
            raise ValueError('official sample probability differs from actual n/N')
        sample_csv=OUT/'golden_retained_sample.csv'
        with sample_csv.open('w',newline='',encoding='utf-8') as stream:
            cursor.copy_expert('COPY(SELECT * FROM '+sample_name+' ORDER BY id) TO STDOUT WITH CSV HEADER',stream)
        for i,expression in enumerate(GATE_EXPRESSIONS):
            cursor.execute(expression.format(table=sample_name));raw=cursor.fetchall()
            factor=1 if 'AVG(' in expression else N/n
            reference={tuple(None if v is None else str(v) for v in row[:-1]):None if row[-1] is None else
                       float(round(float(row[-1])*factor)) if 'COUNT(' in expression else float(row[-1])*factor for row in raw}
            def result_map(path):
                return {tuple(row[:-1]):None if row[-1] is None else float(row[-1]) for row in values[path].get(i,[])}
            a,b=result_map('standard'),result_map('registered')
            def equal(left,right):
                return set(left)==set(right) and all((left[k] is None and right[k] is None) or
                    (left[k] is not None and right[k] is not None and math.isclose(left[k],right[k],rel_tol=1e-9,abs_tol=1e-8)) for k in left)
            checks.append(dict(query_no=i,sql=expression,two_path_match=equal(a,b),independent_sample_match=equal(b,reference),
                               standard=[dict(key=list(k),value=v) for k,v in sorted(a.items(),key=repr)],
                               registered=[dict(key=list(k),value=v) for k,v in sorted(b.items(),key=repr)],
                               independent_sample=[dict(key=list(k),value=v) for k,v in sorted(reference.items(),key=repr)]))
    connection.close()
    adapted={}
    for path in ['standard','registered']:
        left=values[path].get(10,[]);right=values[path].get(11,[])
        if len(left)==len(right)==1:
            l=left[0][-1];r=right[0][-1]
            adapted[path]=compound_sum_adapter(None if l is None else float(l),None if r is None else float(r))
    compound=checks[7];expected=compound['independent_sample'][0]['value']
    compound.update(raw_result_status='INCORRECT_RAW_UNSCALED_COMPOUND_SUM',adapted_values=adapted,
                    adapted_physical_engine_query_indices=[10,11],adapted_ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL',
                    adapted_independent_sample_match=len(adapted)==2 and all(math.isclose(v,expected,rel_tol=1e-9,abs_tol=1e-8) for v in adapted.values()))
    passed=(same and empty==0 and not errors and len(successes)==2*len(GATE_EXPRESSIONS)
            and all(values[path].get(i) for path in ['standard','registered'] for i in range(len(GATE_EXPRESSIONS)))
            and all(c['two_path_match'] and (c['independent_sample_match'] if c['query_no']!=7 else c['adapted_independent_sample_match']) for c in checks))
    artifacts=[jar,ROOT/'code/full_verdict_gate.java',classes/'full_verdict_gate.class',result_path,sample_csv]
    result=dict(status='PASS_STANDARD_AND_REGISTERED_SAMPLE_EQUIVALENCE' if passed else 'ORIGINAL_ENGINE_GATE_DIFFERENCES',
                binding=binding,original_rows=5000,imported_original_rows=empty,sample_rows=n,
                same_sample_membership=same,query_truth_used_for_registration=False,tested_queries=len(checks),
                successful_engine_queries=len(successes),reused_official_sample_without_resampling=reuse,
                count_rounding='Original round(sum(1/vprob)); independent positive-count reference applies round to exact weighted count',
                probability=n/N,partition_min=sample_check[3],partition_max=sample_check[4],
                queries=checks,engine_errors=errors,execution=execution,
                sample_only_contract=sample_contract(n,N),
                artifacts=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in artifacts])
    atomic_json(receipt,result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['runtime','build','compile','pg-build','gate','contract'])
    args=parser.parse_args()
    if args.action=='contract':print(json.dumps(sample_contract(9997912,1000000000),indent=2))
    elif args.action=='runtime':setup_runtime();print('OFFICIAL_RUNTIME_READY')
    elif args.action=='gate':print(json.dumps(run_gate(),indent=2))
    else:
        pg=args.action=='pg-build';goal='compile' if args.action=='compile' else 'package'
        result=run_bounded(maven_command([goal],pg),'maven_pg_package' if pg else 'maven_'+goal,cwd=DATA/('p' if pg else 'b'))
        raise SystemExit(result['exit_code'])


if __name__=='__main__':main()
