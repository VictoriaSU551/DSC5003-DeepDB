"""Strict offline verification for the independent scalar-oracle local variant."""
import argparse
from fractions import Fraction
import math
from pathlib import Path
import sys

import full_scalar_oracle as core
import full_scalar_oracle_run as run
from full_scalar_oracle import require, object_hash


def seconds(value):
    require(type(value) in (int,float) and math.isfinite(value) and value>=0,'Finite nonnegative wall time required')


def validate_receipt(contract,r,root=core.ROOT):
    require(object_hash(r['scope'])==object_hash(core.SCOPE),'Exact local-only method scope required')
    core.validate_counts(contract,r['scalar_counts'],r['population'],r['assumptions'])
    require(r['new_model_calls']==0 and type(r['new_model_calls']) is int and r['server_started_or_stopped'] is False,
            'Scalar counts only; no server lifecycle or model calls')
    require(type(r['client_pid']) is int and r['client_pid']>0,'Actual client PID required')
    seconds(r['seconds'])
    require(r['seconds']<=run.POLICY['max_total_seconds'],'Declared total collection window exceeded')
    require(r['source_boundary']=='HISTORIC_IMPORT_LINEAGE_PLUS_CURRENT_QUERY_COLUMN_SNAPSHOT_NOT_FULL_CSV_IDENTITY',
            'Current projection snapshot is not original CSV full-value proof')
    expected=run.requests(contract)
    require(len(r['operations'])==len(expected),'Complete six aggregations plus five foreign-key checks required')
    for wanted,op in zip(expected,r['operations']):
        require(object_hash(op['request'])==object_hash(wanted),'Exact single-table request and role required')
        seconds(op['seconds'])
        a=r['assumptions'][wanted['table']]
        if wanted['kind']=='scalar_aggregate':values=[a['rows'],a['distinct_ids'],a['null_ids']]+[r['scalar_counts'][k] for k in wanted['predicate_ids']]
        else:values=[a['null_movie_ids'],a['orphan_movie_ids']]
        require(object_hash(values)==object_hash(op['returned_counts']),'SQL results and scalar/assumption payload disagree')
    require(set(r['before'])==set(r['after'])==set(contract['tables'])
            and object_hash(r['before'])==object_hash(r['after']),'Complete unchanged six-table query-column snapshot required')
    for table,snapshot in r['before'].items():
        run.validate_schema(contract,table,snapshot['schema'])
        require(snapshot['projection']==run.projection(contract,table),'Exact query-column projection required')
        b=snapshot['binary_copy'];core.integer(b['bytes'],'binary snapshot bytes')
        require(set(b)=={'bytes','sha256'} and 0<b['bytes']<=run.POLICY['max_snapshot_bytes_per_table']
                and type(b['sha256']) is str and len(b['sha256'])==64 and all(c in '0123456789abcdef' for c in b['sha256']),
                'Nonempty bounded binary COPY digest required')
    identity=r['database_identity']
    require(identity['database']=='deepdb_job' and identity['server_version_num']=='110005'
            and identity['address']=='127.0.0.1' and type(identity['port']) is int and identity['port']==55432
            and Path(identity['data_directory']).resolve()==(Path(root)/'data/postgresql/cluster').resolve()
            and type(identity['backend_pid']) is int and identity['backend_pid']>0
            and identity['read_only']=='on' and identity['isolation']=='repeatable read'
            and type(identity['postmaster_start']) is str and bool(identity['postmaster_start'])
            and Path(identity['image']).resolve()==(Path(root)/'.runtime/postgresql-11.5/pgsql/bin/postgres.exe').resolve(),
            'Wrong database, server runtime, or read-only transaction identity')
    require(type(r['resources']) is list and len(r['resources'])>=12
            and r.get('resource_monitor_errors')==[] and r.get('resource_monitor_stopped') is True,
            'Startup/11 operation resource receipts and a clean stopped monitor required')
    for i,sample in enumerate(r['resources']):run.validate_resources(sample,startup=i==0)


def verify_predictions(contract,receipt,predictions):
    require(type(predictions) is list and len(predictions)==70,'All 70 predictions required')
    for query,row in zip(contract['queries'],predictions):
        require(set(row)=={'query_no','sql','estimate'} and type(row['query_no']) is int
                and row['query_no']==query['query_no'] and row['sql']==query['sql'],'Exact query identity required')
        # Independent exact rational recomputation; no call to producer estimator.
        selected={p['table']:receipt['scalar_counts'][p['id']] for p in query['predicates']}
        numerator=selected['title']
        for table in query['tables']:
            if table!='title':numerator*=selected[table]
        expected=Fraction(numerator,receipt['population']['title']**(len(query['tables'])-1))
        require(row['estimate']=={'numerator':str(expected.numerator),'denominator':str(expected.denominator)},
                'Prediction differs from declared scalar-only uniform title-key formula')


def qerror(prediction,truth,floor=1):
    """Evaluation only: floor both operands at 1 without changing predictions."""
    core.integer(truth,'evaluation truth')
    require(type(floor) is int and floor==1 and isinstance(prediction,Fraction) and prediction>=0,
            'Declared evaluation floor=1 and nonnegative Fraction required')
    p=max(Fraction(floor),prediction);t=max(Fraction(floor),Fraction(truth))
    return float(max(p/t,t/p))


def verify(directory=None,root=core.ROOT):
    root=Path(root).resolve();base=(root/run.BASE/'runs').resolve()
    if directory is None:
        choices=list(base.glob('*/final_seal.json'));require(len(choices)==1,'Exactly one run or an explicit directory is required')
        directory=choices[0].parent
    directory=Path(directory).resolve()
    require(directory.parent==base and directory.is_dir(),'Result directory must be an independent scalar-oracle run')
    require({p.name for p in directory.iterdir()}==set(run.FILES)|{'final_seal.json'}
            and all(p.is_file() for p in directory.iterdir()),'Exact nonempty result artifact set required')
    before={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in directory.iterdir()}
    seal=run.read(directory/'final_seal.json');body={k:v for k,v in seal.items() if k!='self_sha256'}
    require(set(seal)=={'schema','binding','files','self_sha256'} and seal['schema']=='scalar-oracle-final-v1'
            and seal['self_sha256']==object_hash(body) and set(seal['files'])==set(run.FILES),'Incomplete or invalid final seal')
    physical=set()
    for name in run.FILES:
        expected=run.artifact(directory/name,root);resolved=str((directory/name).resolve()).lower()
        require(resolved not in physical and object_hash(seal['files'][name])==object_hash(expected),'Artifact path, bytes, hash or physical uniqueness changed')
        physical.add(resolved)
    plan=run.read(directory/'plan.json');run.validate_plan(plan,root)
    require(directory.name==plan['binding'][:20] and seal['binding']==plan['binding'],'Namespace/plan binding mismatch')
    approval=run.read(directory/'approval.json')
    # The original approved plan path is independently revalidated, not a new
    # receipt manufactured from this copied plan inside the finished run.
    original=root/approval['plan_file']['path'];run.validate_approval(approval,plan,original,root)
    require(object_hash(run.read(original))==object_hash(plan),'Approved original plan content changed')
    life=run.read(directory/'lifecycle.json');verification=run.read(directory/'verification.json')
    require(life==dict(status='PASS',binding=plan['binding'],verification_sha256=run.digest(directory/'verification.json')),
            'Failed or incomplete lifecycle cannot be accepted')
    expected_verification=dict(status='PASS_LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY_COUNTS',binding=plan['binding'],scope=core.SCOPE,
        scalar_predicates=50,queries=70,counts=run.artifact(directory/'counts.json',root),predictions=run.artifact(directory/'predictions.json',root),source_boundary=plan['source_boundary'])
    require(object_hash(verification)==object_hash(expected_verification),'Incomplete or incorrectly scoped verification receipt')
    receipt=run.read(directory/'counts.json');validate_receipt(plan['contract'],receipt,root)
    predicted=run.read(directory/'predictions.json')
    require(set(predicted)=={'scope','binding','queries'} and object_hash(predicted['scope'])==object_hash(core.SCOPE)
            and predicted['binding']==plan['binding'],'Prediction envelope changed')
    verify_predictions(plan['contract'],receipt,predicted['queries'])
    after={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in directory.iterdir()}
    require(before==after,'Artifacts changed during read-only verification')
    return dict(status='PASS_READ_ONLY_LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY',scope=core.SCOPE,
                binding=plan['binding'],queries=70,scalar_predicates=50,new_model_calls=0,new_database_calls=0,
                source_boundary=plan['source_boundary'],artifacts=[run.artifact(p,root) for p in sorted(directory.iterdir())],
                prediction_artifact=run.artifact(directory/'predictions.json',root),final_seal=run.artifact(directory/'final_seal.json',root),
                qerror_policy='EVALUATION_ONLY_FLOOR_BOTH_OPERANDS_AT_1_RAW_ZERO_ESTIMATES_PRESERVED',evaluation_truth_used=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory');args=parser.parse_args()
    result=verify(args.directory);print({k:v for k,v in result.items() if k!='artifacts'})
