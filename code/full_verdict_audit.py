"""Strictly read-only fixed-scope Verdict audit: files and historical evidence only.

This module has no database client, subprocess, network, repair or write operation.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import base64
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = 'output/full/verdict/'
NAMES = ('F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2')
N, SAMPLE_N = 1000000000, 9997912
SOURCE = 'data/downloads/baselines/verdict18/b59209f626d278687ea0a801295b41064c7fecbb.zip'
JDK = 'data/downloads/verdict_runtime/OpenJDK8U-jdk_x64_windows_hotspot_8u462b08.zip'
MAVEN = 'data/downloads/verdict_runtime/apache-maven-3.9.11-bin.zip'
PG = 'data/downloads/postgresql-11.5-1-windows-x64-binaries.zip'
SQL = 'code/benchmarks/flights/sql/aqp_queries.sql'
TRUTH = 'output/full/flights/flights-1b/ground_truth.json'
SAMPLE = 'data/flights/generated/flights-1b/sample.csv'
JAR = 'data/verdict/p/jars/verdict-spark-lib-0.4.7.jar'
FIXED_HASHES = {
 SOURCE:'72b068ce7dc501e065229b2b43eee19bd3777127e973db436256fd9770ae23c9',
 JDK:'c6c2d8e6c2cbf0b4ddb707e6edb9a00d8a7b04e9ed6dda7e62d43dc4d83d342c',
 MAVEN:'0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb',
 PG:'89ec61731231b88b748ae0f923ec02568ede2c008c79f901666ea67de6565f4c',
 SQL:'5400031e656041bbe2d374d40a68b6817196c7ca777100dbfeaf666efa70c823',
 TRUTH:'f1cd8591539f8fb04bc0c6582a7cab9d660beecdc2843bcc27dbbcda43e34cb2',
 SAMPLE:'9d9c78d0e03b403472e34da73af9f3dccde070036c3ed02c649ce4ee880d6f45',
 JAR:'05dd0ec816c2c11ec143ff1aa3084a296a5156ec9fc11923b0068bdc3625b0a1',
 'data/verdict/bridge_classes/full_verdict_gate.class':'422dd71d115db0e187835992e46b7492e164460cf941860c356bf7a0db9386fb',
 'data/verdict/bridge_classes/full_verdict_flights.class':'5ac16a3931319d72bcf0dbcf5140426880c1f54911a36f462df61721c15b478c',
 'code/full_verdict_gate.java':'d1b522250b51683be5651613d92c398fc3c18ed99a09cf23939430c188dddbf4',
 'code/full_verdict_flights.java':'9aef09aef73b8453f036fd70862a654b187aecf503b7626ba74b56c4db161b3a',
 OUT+'golden_retained_sample.csv':'788409d8ccfd22070d5d3f71975c457f77db6f9ed8fad956a4061c0037c05dcd'}
GATE_SQL = (
 'SELECT COUNT(*) FROM {table}','SELECT SUM(x) FROM {table}','SELECT AVG(x) FROM {table}',
 'SELECT grp, COUNT(*) FROM {table} GROUP BY grp',
 'SELECT grp, SUM(x) FROM {table} WHERE y>3 GROUP BY grp',
 'SELECT grp, AVG(x) FROM {table} WHERE x>=0 GROUP BY grp',
 'SELECT SUM(x*y) FROM {table} WHERE y<10','SELECT SUM(x)-SUM(y) FROM {table}',
 'SELECT COUNT(x) FROM {table} WHERE x>0','SELECT COUNT(*) FROM {table} WHERE x IS NULL',
 'SELECT SUM(x) FROM {table}','SELECT SUM(y) FROM {table}')
REQUIRED_OUTPUT = '''bridge_compile.json bridge_compile.stderr.log bridge_compile.stdout.log
flights_bridge_compile.json flights_bridge_compile.stderr.log flights_bridge_compile.stdout.log
flights_engine_sql.tsv flights_evaluation_derivation.log flights_evaluation.json flights_import.json
flights_nobound.json flights_nobound.stderr.log flights_nobound.stdout.log flights_nobound.tsv
flights_post_run_snapshot.json flights_post_run_snapshot.log flights_prepare.log
flights_register.json flights_register.stderr.log flights_register.stdout.log flights_registration.json
flights_run.log flights_subsampling.json flights_subsampling.stderr.log flights_subsampling.stdout.log
flights_subsampling.tsv focused_tests.log golden_cli.log golden_gate.json golden_java.json
 golden_java.stderr.log golden_java.stdout.log golden_result.tsv golden_retained_sample.csv
historical_build_dependency_resolution.json maven_compile.json maven_compile.stderr.log maven_compile.stdout.log
maven_package.json maven_package.stderr.log maven_package.stdout.log maven_pg_package.json
maven_pg_package.stderr.log maven_pg_package.stdout.log postgres_build_patch.json runtime_dependency_provenance.json
runtime_provenance.json source_files.json cleanup.json verification.json historical_attempts.json'''.split()
ATTEMPT_STEMS = ('bridge_compile_e3b0c44298fc','golden_java_0b5bee8fac1e','golden_java_9847669cbc0d',
                 'golden_java_c2b4ed39f0f8','golden_java_e846c19e2ad6')


def require(condition, message):
    if not condition: raise ValueError(message)


def bhash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''): result.update(block)
    return result.hexdigest()


def load(root, path): return json.loads((root/path).read_text())


def safe_file(root, name):
    require(isinstance(name,str) and name and '\\' not in name, 'noncanonical artifact path')
    part=PurePosixPath(name)
    require(not part.is_absolute() and ':' not in name and all(x not in ('','..','.') for x in name.split('/')), 'unsafe artifact path')
    result=(root/name).resolve()
    require(root in result.parents and result.is_file(), 'artifact missing/outside root: '+name)
    return result


def verify_manifest(path,root=ROOT):
    root=Path(root).resolve();body=json.loads(Path(path).read_text());seal=body.pop('seal_sha256',None)
    require(seal==bhash(body), 'Verdict manifest seal changed')
    require(body.get('status')=='SEALED_EXISTING_SAMPLE_ONLY_VERDICT', 'Verdict manifest status differs')
    records=body.get('artifacts');require(isinstance(records,list) and bool(records), 'empty artifact list')
    seen=set()
    for item in records:
        artifact=safe_file(root,item['path']);identity=str(artifact).casefold()
        require(identity not in seen, 'duplicate artifact path');seen.add(identity)
        require(type(item.get('bytes')) is int and item['bytes']>=0 and re.fullmatch('[a-f0-9]{64}',item.get('sha256','')) is not None,
                'invalid artifact record')
        require(artifact.stat().st_size==item['bytes'] and digest(artifact)==item['sha256'], 'sealed artifact changed: '+item['path'])
    return dict(status='PASS_CURRENT_FILES_AND_HISTORICAL_EVIDENCE_ONLY',verified_artifacts=len(records),
        manifest_sha256=digest(path),database_connected=False,engine_sql_executed=False,files_modified=False,
        scope='Current files/JAR/source plus sealed historical DB/runtime evidence. No claim of current DB row-content identity.',
        result_path=body.get('result_path'),sample_only=True)


def archive_pairs(root,archive,directory,selection=None,strip=False):
    with zipfile.ZipFile(str(root/archive)) as original:
        entries=[i for i in original.infolist() if not i.is_dir() and (selection is None or selection(i.filename))]
        prefix=original.namelist()[0] if strip else ''
        for item in entries:
            relative=item.filename[len(prefix):]
            require(relative and '..' not in PurePosixPath(relative).parts, 'unsafe archived runtime/source path')
            yield directory+'/'+relative, hashlib.sha256(original.read(item)).hexdigest()


def required_artifacts(root=ROOT):
    """Derive the full immutable closure, never infer completeness from the seal's list."""
    root=Path(root)
    names=set(FIXED_HASHES)
    names.update(OUT+n for n in REQUIRED_OUTPUT)
    names.update(('code/full_verdict.py','code/full_verdict_flights.py','code/full_verdict_audit.py',
        'code/full_verdict_seal.py','code/full_common.py','code/tests/test_full_verdict.py',
        'code/tests/test_full_verdict_flights.py','code/tests/test_full_verdict_audit.py',
        'docs/FULL_VERDICT_PROTOCOL.md','data/verdict/settings.xml','data/verdict/p/postgres-test-dependencies.patch',
        'data/downloads/baselines/verdict18/seal.json','data/postgresql/runtime_manifest.json',
        JDK+'.sha256.txt',MAVEN+'.sha512','output/full/flights/flights-1b/generation_result.json',
        'output/full/flights/flights-1b/checkpoint.json'))
    for archive,directory,selection,strip in (
        (SOURCE,'data/verdict/b',None,True),(SOURCE,'data/verdict/p',None,True),
        (JDK,'.runtime/java',None,False),(MAVEN,'.runtime/maven',None,False),
        (PG,'.runtime/postgresql-11.5',lambda n:n.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/')),False)):
        names.update(p for p,_ in archive_pairs(root,archive,directory,selection,strip))
    attempts=load(root,OUT+'historical_attempts.json')
    require(attempts.get('status')=='SEALED_FAILED_ATTEMPTS_RETAINED' and attempts.get('artifacts'), 'failed raw attempts evidence incomplete')
    expected={OUT+'attempts/'+stem+'/'+stem.rsplit('_',1)[0]+suffix for stem in ATTEMPT_STEMS for suffix in ('.json','.stderr.log','.stdout.log')}
    require(len(attempts['artifacts'])==15 and {a['path'] for a in attempts['artifacts']}==expected, 'failed raw attempts subset/duplicates')
    for item in attempts['artifacts']:
        path=safe_file(root,item['path'])
        require(path.stat().st_size==item['bytes'] and digest(path)==item['sha256'], 'failed raw attempt record changed')
    names.update(expected)
    return names


def check_archives(root):
    counts={}
    for archive,directory,selection,strip in (
        (SOURCE,'data/verdict/b',None,True),(SOURCE,'data/verdict/p',None,True),
        (JDK,'.runtime/java',None,False),(MAVEN,'.runtime/maven',None,False),
        (PG,'.runtime/postgresql-11.5',lambda n:n.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/')),False)):
        count=0
        for path,expected in archive_pairs(root,archive,directory,selection,strip):
            if path=='data/verdict/p/core/pom.xml': expected='40d11f90b85de88de18457f70b2f374587a4560a1bae68f61c0d6ce6135f97e5'
            require(digest(safe_file(root,path))==expected, 'archive byte mismatch: '+path);count+=1
        counts[directory]=count
    require(counts['data/verdict/b']==400 and counts['data/verdict/p']==400 and counts['.runtime/java']==446
            and counts['.runtime/maven']==96 and counts['.runtime/postgresql-11.5']==1436, 'source/runtime closure count differs')
    patch=load(root,OUT+'postgres_build_patch.json')
    require(len(patch['removed_test_dependencies'])==16 and all(x['scope']=='test' and x['group'].startswith('com.cloudera.') for x in patch['removed_test_dependencies'])
            and patch['java_sources_unchanged'] is True, 'unexpected scientific build patch')
    return counts


def decode(value):
    if value=='N': return None
    require(value.startswith('V'), 'invalid original engine cell')
    return base64.b64decode(value[1:],validate=True).decode('utf-8')


def read_physical_calls(path,expected_ids):
    """Reject subset, duplicate, unknown, failed, empty or incomplete checkpoints."""
    expected_ids=set(expected_ids);require(bool(expected_ids), 'empty expected calls')
    result={}
    for line in Path(path).read_text().splitlines():
        fields=line.split('\t');require(len(fields)>=3,'malformed physical call')
        kind,qid=fields[:2];require(qid in expected_ids,'unexpected physical call '+qid)
        if kind=='META':
            require(qid not in result,'duplicate physical META')
            result[qid]=dict(rows=[],columns=[decode(v) for v in fields[2:]],error=None)
            require(bool(result[qid]['columns']), 'empty physical columns')
        else:
            require(qid in result and not result[qid].get('complete'), 'physical record after completion / missing META')
            item=result[qid]
            if kind=='ROW':
                row=[decode(v) for v in fields[2:]];require(len(row)==len(item['columns']),'physical row width differs');item['rows'].append(row)
            elif kind=='TIME':
                require(len(fields)==3 and fields[2].isdigit() and int(fields[2])>0,'invalid physical elapsed time')
                require(bool(item['rows']), 'empty physical result')
                item.update(engine_wall_ms=int(fields[2])/1e6,complete=True)
            else: raise ValueError('failed or unknown original physical call: '+kind)
    require(set(result)==expected_ids and all(x.get('complete') for x in result.values()), 'missing/incomplete physical calls')
    return result


def numeric_key(row,grouped):
    value=row[1 if grouped else 0]
    key=tuple(int(x) if x is not None and re.fullmatch(r'-?\d+',x) else x for x in (row[:1] if grouped else []))
    return key,None if value is None else float(value)


def predictions(rows,grouped):
    result={}
    for row in rows:
        key,value=numeric_key(row,grouped);require(key not in result, 'duplicate physical group')
        require(value is None or math.isfinite(value), 'nonfinite physical prediction');result[key]=value
    return result


def near(a,b):
    return a is None and b is None or a is not None and b is not None and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-10)


def compare_group_records(records,truth,pred):
    require(isinstance(records,list) and len(records)==len(set(truth)|set(pred)), 'outer group coverage differs')
    seen=set()
    for row in records:
        key=tuple(row['key']);require(key not in seen and key in set(truth)|set(pred), 'duplicate/extra group record');seen.add(key)
        actual=truth.get(key);value=pred.get(key)
        status='EXTRA_MODEL_GROUP' if key not in truth else 'MISSING_MODEL_GROUP' if key not in pred else 'MATCHED'
        ae=abs(value-actual) if value is not None and actual is not None else None
        rel=ae/abs(actual) if ae is not None and actual!=0 else None
        require(row['status']==status and near(row['truth'],actual) and near(row['prediction'],value) and row['zero_truth']==(actual==0)
                and near(row['absolute_error'],ae) and near(row['relative_error'],rel) and row['engine_error'] is None,
                'group arithmetic/status differs')
    return len(set(truth)-set(pred)),len(set(pred)-set(truth))


def expected_plans(sqls):
    plans={name+'.raw':sql for name,sql in zip(NAMES,sqls)}
    sql=sqls[-1];match=re.search(r'SUM\((\w+)\)\s*-\s*SUM\((\w+)\)',sql,re.I)
    require(match is not None,'compound SUM plan missing')
    for i,column in enumerate(match.groups()): plans['F5.2.adapter'+str(i)]=sql[:match.start()]+'SUM('+column+')'+sql[match.end():]
    return plans


def validate_evaluation(evaluation,truth,sqls,point,ci):
    require(len(sqls)==12 and [q.get('query_name') for q in evaluation.get('queries',[])]==list(NAMES), 'fixed12 evaluation queries required')
    require(truth['complete'] is True and truth['population_rows']==N and len(truth['queries'])==12,'truth incomplete')
    require(evaluation['status']=='COMPLETED_SAMPLE_ONLY_ORIGINAL_ENGINE_WITH_EXPLICIT_RAW_COMPOUND_LIMITATION'
            and evaluation['actual_sample_rows']==SAMPLE_N and evaluation['population_prior']==N
            and evaluation['query_truth_used_for_registration'] is False,'evaluation scope differs')
    require(evaluation['sql_sha256']==FIXED_HASHES[SQL] and evaluation['truth_sha256']==FIXED_HASHES[TRUTH], 'evaluation input binding differs')
    plans=expected_plans(sqls);require(set(point)==set(ci)==set(plans),'fixed14 point/CI calls required')
    coverage=[];truth_count=0
    for index,(name,sql,q,t) in enumerate(zip(NAMES,sqls,evaluation['queries'],truth['queries'])):
        require(t['query_no']==index and t['query_name']==name and re.sub(r'\s+','',t['sql'])==re.sub(r'\s+','',sql)
                and q['sql']==sql,'query index/name/SQL alignment differs')
        grouped='GROUP BY' in sql.upper();true={}
        for g in t['groups']:
            k=tuple(g['key']);require(k not in true and len(k)==int(grouped),'duplicate/malformed truth group')
            require(type(g['numerator']) is int and type(g['denominator']) is int and g['denominator']>0,'invalid exact truth')
            true[k]=float(Fraction(g['numerator'],g['denominator']))
        require(bool(true),'empty truth query');truth_count+=len(true)
        raw=point[name+'.raw'];native=ci[name+'.raw']
        require(q['raw']==raw and q['native_ci']==native and q['native_ci_confidence']==.95,'result differs from historical physical cells')
        pred=predictions(raw['rows'],grouped);missing,extra=compare_group_records(q['groups'],true,pred)
        require((q['missing'],q['extra'])==(missing,extra),'group missing/extra receipt differs')
        cint={};details={};position=2 if grouped else 1
        require(set(predictions(native['rows'],grouped))==set(pred),'native CI group set differs from point groups')
        for row in native['rows']:
            k,value=numeric_key(row,grouped)
            if len(row)>position and row[position] is not None:
                half=float(row[position]);details[k]=dict(point=value,error_bound=half)
                if value is not None and math.isfinite(half) and half>=0:cint[k]=[value-half,value+half]
        for row in q['groups']:
            k=tuple(row['key']);bounds=cint.get(k)
            status=('UNSUPPORTED_RAW_COMPOUND_SUM' if name=='F5.2' else 'AVAILABLE_ORIGINAL_NATIVE95' if bounds else 'UNAVAILABLE_NULL_ABSENT_OR_INVALID_BOUND')
            covers=bounds[0]<=true[k]<=bounds[1] if bounds and k in true else None
            require(row['native_95pct_interval']==bounds and row['native_ci_original_values']==details.get(k)
                    and row['native_ci_status']==status and row['native_ci_covers_truth']==covers,'native CI record differs')
        adapted=q['adapted']
        if name=='F5.2':
            require(q['raw_status']=='INCORRECT_RAW_UNSCALED_COMPOUND_SUM' and isinstance(adapted,dict),'raw compound limitation hidden')
            left,right=point[name+'.adapter0'],point[name+'.adapter1'];lm=predictions(left['rows'],grouped);rm=predictions(right['rows'],grouped)
            amap={k:None if lm[k] is None or rm[k] is None else lm[k]-rm[k] for k in set(lm)&set(rm)}
            am,ax=compare_group_records(adapted['groups'],true,amap)
            require(adapted['status']=='ADAPTED_TWO_ORIGINAL_TOP_LEVEL_SUMS' and adapted['physical_sql_calls']==2
                and adapted['ci_status']=='UNSUPPORTED_NO_COVARIANCE_MODEL' and adapted['children']==dict(left=left,right=right)
                and adapted['native_ci_children']==dict(left=ci[name+'.adapter0'],right=ci[name+'.adapter1'])
                and adapted['engine_wall_ms']==left['engine_wall_ms']+right['engine_wall_ms']
                and (adapted['missing'],adapted['extra'])==(am,ax),'adapter provenance/call/CI differs')
            require(any(not near(pred[k],amap[k]) for k in set(pred)&set(amap)), 'raw compound error no longer visible')
        else: require(adapted is None and q['raw_status']=='EXECUTED_RAW_ORIGINAL','unexpected adapter/error')
        coverage.append(dict(query_name=name,raw_status=q['raw_status'],truth_groups=len(true),raw_predicted_groups=len(pred),
            missing=missing,extra=extra,raw_error=raw['error'],native_ci_error=native['error'],
            native_ci_groups_with_interval=len(cint),adapted_status=adapted['status'] if adapted else None,
            adapted_missing=adapted['missing'] if adapted else None,adapted_extra=adapted['extra'] if adapted else None))
    require(truth_count==331, 'fixed331 unique truth groups required')
    require(sum(q['raw_predicted_groups'] for q in coverage)==329 and sum(q['missing'] for q in coverage)==2
            and sum(q['extra'] for q in coverage)==0,'historical raw group coverage differs')
    return coverage


def validate_gate(root):
    gate=load(root,OUT+'golden_gate.json')
    require(gate['status']=='PASS_STANDARD_AND_REGISTERED_SAMPLE_EQUIVALENCE' and gate['original_rows']==5000
        and gate['imported_original_rows']==0 and gate['sample_rows']==1050 and gate['probability']==1050/5000
        and gate['same_sample_membership'] is True and gate['query_truth_used_for_registration'] is False
        and gate['tested_queries']==12 and gate['successful_engine_queries']==24 and gate['engine_errors']==[]
        and gate['partition_min']==0 and gate['partition_max']==99,'golden sample/empty-original/nN contract differs')
    require(gate['binding']['queries']==list(GATE_SQL) and gate['binding']['driver_sha256']==digest(root/'code/full_verdict.py')
            and gate['binding']['bridge_sha256']==FIXED_HASHES['code/full_verdict_gate.java']
            and gate['binding']['jar_sha256']==FIXED_HASHES[JAR] and gate['binding']['source_sha256']==FIXED_HASHES[SOURCE], 'golden source binding differs')
    expected={(p,i) for p in ('standard','registered') for i in range(12)};rows={x:[] for x in expected};done=set();sample=[]
    for line in (root/(OUT+'golden_result.tsv')).read_text().splitlines():
        f=line.split('\t')
        if f[0]=='SAMPLE': sample.append(f[1:]);continue
        require(f[0] in ('ROW','OK') and len(f)>=3,'failed golden physical call')
        key=(f[1],int(f[2]));require(key in expected and key not in done,'unexpected/duplicate golden physical call')
        if f[0]=='ROW':rows[key].append([decode(v) for v in f[3:]])
        else:require(len(f)==3 and bool(rows[key]),'empty golden physical call');done.add(key)
    require(done==expected and sample==[['public_verdict.vs_v_population_uf_0_2000','public_verdict.vs_v_imported_uf_0_2000','1050','5000']], 'golden24 completeness differs')
    with (root/(OUT+'golden_retained_sample.csv')).open(newline='') as stream:sample_rows=list(csv.DictReader(stream))
    require(len(sample_rows)==1050 and len({r['id'] for r in sample_rows})==1050 and all(float(r['verdict_vprob'])==.21 for r in sample_rows),'golden retained sample differs')
    require([q['query_no'] for q in gate['queries']]==list(range(12)),'golden query subset/duplicates')
    for i,q in enumerate(gate['queries']):
        require(q['sql']==GATE_SQL[i] and q['two_path_match'] is True,'golden query SQL/two-path differs')
        grouped=i in (3,4,5);references={}
        for row in sample_rows:
            x=None if row['x']=='' else float(row['x']);y=None if row['y']=='' else float(row['y'])
            if i==4 and (y is None or not y>3) or i==5 and (x is None or not x>=0) or i==6 and (y is None or not y<10) or i==8 and (x is None or not x>0) or i==9 and x is not None:continue
            key=(row['grp'] or None,) if grouped else ()
            values=references.setdefault(key,[])
            val=1 if i in (0,3,8,9) else y if i==11 else None if i==6 and (x is None or y is None) else x*y if i==6 else x
            if val is not None:values.append(val)
        if i==7:
            references={():sum(float(r['x']) for r in sample_rows if r['x'])-sum(float(r['y']) for r in sample_rows if r['y'])}
        else:references={k:(sum(v)/len(v) if i in (2,5) else round(sum(v)/.21) if i in (0,3,8,9) else sum(v)/.21) for k,v in references.items()}
        if i==7:references={k:v/.21 for k,v in references.items()}
        actual=[]
        for path in ('standard','registered'):
            pred=predictions(rows[(path,i)],grouped);actual.append(pred)
            stored={tuple(r['key']):r['value'] for r in q[path]}
            require(pred==stored and set(pred)==set(references),'golden nonempty full-group coverage differs')
            if i!=7:require(all(math.isclose(pred[k],references[k],rel_tol=1e-9,abs_tol=1e-8) for k in references),'golden independent arithmetic differs')
        require(actual[0]==actual[1],'golden physical paths differ')
        require(q['independent_sample_match']==(i!=7), 'golden raw error flag differs')
        stored={tuple(r['key']):r['value'] for r in q['independent_sample']}
        require(set(stored)==set(references) and all(math.isclose(stored[k],references[k],rel_tol=1e-9,abs_tol=1e-8) for k in references),'golden reference record differs')
        if i==7:
            require(q['raw_result_status']=='INCORRECT_RAW_UNSCALED_COMPOUND_SUM' and q['adapted_physical_engine_query_indices']==[10,11]
                and q['adapted_ci_status']=='UNSUPPORTED_NO_COVARIANCE_MODEL' and q['adapted_independent_sample_match'] is True,'golden compound adapter omitted')
            for path in ('standard','registered'):
                value=float(rows[(path,10)][0][0])-float(rows[(path,11)][0][0])
                require(near(q['adapted_values'][path],value) and math.isclose(value,references[()],rel_tol=1e-9,abs_tol=1e-8),'golden adapted arithmetic differs')
            require(not math.isclose(actual[0][()],references[()],rel_tol=1e-9,abs_tol=1e-8),'golden raw compound error is not preserved')
    return 24


def validate_receipts(root):
    imported=load(root,OUT+'flights_import.json');registration=load(root,OUT+'flights_registration.json');snapshot=load(root,OUT+'flights_post_run_snapshot.json')
    source=imported['source'];require(imported['status']=='PASS_EXISTING_UNIFORM_SAMPLE_IMPORTED' and source['sample_sha256']==FIXED_HASHES[SAMPLE]
        and source['sample_bytes']==582074363 and source['sample_rows']==SAMPLE_N and source['population_rows']==N
        and source['query_truth_used_for_registration'] is False and imported['actual_sample_rows']==SAMPLE_N
        and imported['original_rows']==0 and imported['population_prior']==N and imported['probability']==SAMPLE_N/N
        and imported['binding_sha256']==bhash(imported['binding']) and imported['protected_job_before']==imported['protected_job_after']
        and imported['budget_peak_bytes']<=8*1024**3 and imported['statement_timeout_ms']==120000,'formal import contract differs')
    driver=(root/'code/full_verdict_flights.py').read_text(encoding='utf-8-sig')
    function=next(n for n in ast.parse(driver).body if isinstance(n,ast.FunctionDef) and n.name=='import_sample')
    function_bytes=''.join(driver.splitlines(True)[function.lineno-1:function.end_lineno]).encode()
    require(imported['binding']['import_function']==hashlib.sha256(function_bytes).hexdigest(),'actual import function binding differs')
    require(registration['status']=='PASS_ORIGINAL_METADATA_REGISTERED' and registration['exit_code']==0
        and registration['actual_sample_rows']==SAMPLE_N and registration['population_prior']==N
        and registration['import_binding']==imported['binding_sha256'] and registration['query_truth_used_for_registration'] is False,'registration differs')
    require(snapshot['status']=='PASS_POST_RUN_READ_ONLY_RR_ACCOUNTING_SNAPSHOT' and snapshot['transaction_begin'][2:]==['on','repeatable read']
        and snapshot['original_rows']==0 and snapshot['sample_count_probability_partition_range']==[SAMPLE_N,SAMPLE_N/N,SAMPLE_N/N,0,99]
        and snapshot['partition_histogram']==imported['partition_histogram']
        and [p for p,_ in snapshot['partition_histogram']]==list(range(100))
        and sum(n for _,n in snapshot['partition_histogram'])==SAMPLE_N
        and snapshot['sample_relation_identity_and_insert_update_delete_stats'][2:]==[SAMPLE_N,0,0]
        and snapshot['native_size_metadata']==[['public_verdict','vs_flights_uf_0_0100',SAMPLE_N,N]]
        and snapshot['native_name_metadata']==[['public','flights','public_verdict','vs_flights_uf_0_0100','uniform',.01,'']]
        and snapshot['protected_job_identity']==imported['protected_job_after'],'historical snapshot differs')
    checkpoint=load(root,'output/full/flights/flights-1b/checkpoint.json');seal=checkpoint.pop('checkpoint_sha256')
    report=load(root,'output/full/flights/flights-1b/generation_result.json')
    require(seal==bhash(checkpoint) and checkpoint['binding']==bhash(checkpoint['binding_details'])
        and seal==source['generation_checkpoint_sha256'] and checkpoint['binding']==source['generation_binding']
        and checkpoint['rows_generated']==report['rows_generated']==N and checkpoint['sample_rows']==report['sample_rows']==SAMPLE_N
        and report['status']=='PASS' and report['paper_scale_reached'] is True
        and checkpoint['files']['sample.csv']==report['files']['sample.csv']==dict(offset=582074363,sha256=FIXED_HASHES[SAMPLE]),'Flights source generation binding differs')
    for name in ('golden_java','flights_nobound','flights_subsampling','flights_register'):
        record=load(root,OUT+name+'.json')
        require(record['status']=='PASS' and record['exit_code']==0 and 0<record['peak_rss_bytes']<=1024**3,'Java resource/exit receipt differs')
    return dict(point=14,native_ci=14,golden=24)


def verify(manifest_path=None,root=ROOT):
    root=Path(root).resolve();manifest_path=Path(manifest_path) if manifest_path is not None else root/(OUT+'final_seal.json')
    checked=verify_manifest(manifest_path,root);seal=json.loads(manifest_path.read_text())
    require(seal.get('result_path')==OUT+'flights_evaluation.json', 'fixed evaluation artifact required')
    records={r['path']:r for r in seal['artifacts']}
    for path,expected in FIXED_HASHES.items():require(path in records and records[path]['sha256']==expected,'fixed archive/input/runtime hash differs: '+path)
    required=required_artifacts(root);require(set(records)==required,'mandatory artifact closure missing/extra: '+str(sorted(required^set(records))[:8]))
    archive_counts=check_archives(root)
    sqls=(root/SQL).read_text().splitlines();require(len(sqls)==12,'fixed SQL query count differs')
    plans=expected_plans(sqls);actual={}
    for line in (root/(OUT+'flights_engine_sql.tsv')).read_text().splitlines():
        f=line.split('\t');require(len(f)==2 and f[0] not in actual,'duplicate/malformed physical SQL plan')
        actual[f[0]]=base64.b64decode(f[1],validate=True).decode()
    require(actual==plans,'fixed14 original physical SQL plans differ')
    point=read_physical_calls(root/(OUT+'flights_nobound.tsv'),plans);ci=read_physical_calls(root/(OUT+'flights_subsampling.tsv'),plans)
    coverage=validate_evaluation(load(root,OUT+'flights_evaluation.json'),load(root,TRUTH),sqls,point,ci)
    gate_calls=validate_gate(root);calls=validate_receipts(root)
    require(gate_calls==calls['golden'] and seal.get('historical_physical_calls')==calls,'physical call receipt differs')
    verification=load(root,OUT+'verification.json')
    require(verification['status']=='PASS_INDEPENDENT_FIXED_SCOPE_EXTERNAL_AUDIT'
            and verification['group_coverage']==coverage and verification['historical_physical_calls']==calls
            and verification['archive_file_counts']==archive_counts and verification['database_connected'] is False
            and verification['engine_sql_executed'] is False,'verification receipt incomplete/differs')
    return dict(status='PASS_READ_ONLY_ORIGINAL_VERDICT_SAMPLE_ONLY_WITH_GAPS',evaluation_artifact=records[OUT+'flights_evaluation.json'],
        verification=records[OUT+'verification.json'],final_seal=dict(path=manifest_path.relative_to(root).as_posix(),bytes=manifest_path.stat().st_size,sha256=digest(manifest_path)),
        verified_artifacts=checked['verified_artifacts'],database_connected=False,engine_sql_executed=False,files_modified=False,
        evidence_scope=checked['scope'],actual_sample_rows=SAMPLE_N,population_prior=N,
        historical_physical_calls=calls,group_coverage=coverage,native_ci_confidence=.95,
        compound_adapter_ci='UNSUPPORTED_NO_COVARIANCE_MODEL',full_paper_complete=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',default=str(ROOT/(OUT+'final_seal.json')))
    args=parser.parse_args();print(json.dumps(verify(args.manifest),indent=2))


if __name__=='__main__':main()
