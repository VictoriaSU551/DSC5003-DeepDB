"""Header-aware, sealed Flights RSPN model and independent sample confidence intervals."""
import argparse
from contextlib import contextmanager
import csv
import inspect
from decimal import Decimal
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import pickle
import random
import re
import sqlite3
import time

import numpy as np
import pandas as pd
from scipy.stats import norm

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, algorithm_seal

COLUMNS = ('YEAR_DATE','UNIQUE_CARRIER','ORIGIN','ORIGIN_STATE_ABR','DEST','DEST_STATE_ABR',
           'DEP_DELAY','TAXI_OUT','TAXI_IN','ARR_DELAY','AIR_TIME','DISTANCE')
NUMERIC = ('dep_delay','taxi_out','taxi_in','arr_delay','air_time','distance')
SQL_PATH = ROOT / 'code/benchmarks/flights/sql/aqp_queries.sql'
QUERY_NAMES = ('F1.1','F1.2','F2.1','F2.2','F2.3','F3.1','F3.2','F3.3','F4.1','F4.2','F5.1','F5.2')


def seal_record(path, root=ROOT):
    path, root = Path(path).resolve(), Path(root).resolve()
    return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=file_sha256(path))


def verify_artifacts(records, root=ROOT):
    root = Path(root).resolve()
    for record in records:
        path = (root / record['path']).resolve()
        if root not in path.parents or not path.is_file() or path.stat().st_size != record['bytes'] or file_sha256(path) != record['sha256']:
            raise ValueError('sealed artifact changed: ' + record['path'])


def validate_header(path):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        header = next(csv.reader(stream), [])
    if tuple(header) != COLUMNS:
        raise ValueError('Flights sample header must be exactly the12 uppercase columns')


def read_sample_header(path):
    validate_header(path)
    frame = pd.read_csv(path, header=0)
    if tuple(frame.columns) != COLUMNS:
        raise ValueError('Flights sample header differs after parsing')
    frame.columns = [c.lower() for c in COLUMNS]
    for column in ('year_date',) + NUMERIC:
        frame[column] = pd.to_numeric(frame[column], errors='raise')
    return frame


def load_generated_input(source, paper=False):
    source = Path(source)
    if source.is_absolute() or '..' in source.parts:
        raise ValueError('source must name a Flights generated run')
    output = FULL / 'flights' / source
    data = ROOT / 'data/flights/generated' / source
    report = json.loads((output / 'generation_result.json').read_text())
    truth = json.loads((output / 'ground_truth.json').read_text())
    checkpoint = json.loads((output / 'checkpoint.json').read_text())
    seal = checkpoint.pop('checkpoint_sha256', None)
    if seal != binding_hash(checkpoint) or checkpoint['binding'] != binding_hash(checkpoint['binding_details']):
        raise ValueError('generation checkpoint seal mismatch')
    population = int(report['rows_generated'])
    if (report['status'] != 'PASS' or not truth['complete'] or population != truth['population_rows'] or
            population != checkpoint['rows_generated'] or population != checkpoint['binding_details']['config']['rows'] or
            report['binding'] != checkpoint['binding']):
        raise ValueError('generation or exact truth incomplete/inconsistent')
    if paper and (population != 1000000000 or not report['paper_scale_reached']):
        raise ValueError('formal Flights model requires completed1B (1000000000) population')
    queries = SQL_PATH.read_text().splitlines()
    if len(queries) != 12 or len(truth['queries']) != 12:
        raise ValueError('Flights requires exactly12 SQL queries/truth groups')
    for i, (sql, item) in enumerate(zip(queries, truth['queries'])):
        if item['query_no'] != i or item['query_name'] != QUERY_NAMES[i] or re.sub(r'\s+','',sql) != re.sub(r'\s+','',item['sql']):
            raise ValueError('Flights truth SQL alignment differs')
    if file_sha256(SQL_PATH) != checkpoint['binding_details']['input_seal']['query_sha256']:
        raise ValueError('generation SQL source changed')
    sample_path = data / 'sample.csv'
    expected = checkpoint['files']['sample.csv']
    if report['files']['sample.csv'] != expected or sample_path.stat().st_size != expected['offset'] or file_sha256(sample_path) != expected['sha256']:
        raise ValueError('sealed sample bytes changed')
    validate_header(sample_path)
    with sample_path.open(newline='', encoding='utf-8') as stream:
        reader = csv.reader(stream); next(reader)
        actual = sum(1 for row in reader if len(row) == 12)
    if actual != report['sample_rows'] or actual != checkpoint['sample_rows']:
        raise ValueError('actual sample row count differs')
    return dict(source=source.as_posix(), population_rows=population, sample_rows=actual,
                paper_scale_reached=population == 1000000000, sample_path=sample_path.relative_to(ROOT).as_posix(),
                sample_sha256=expected['sha256'], generation_binding=checkpoint['binding'],
                generation_checkpoint_sha256=seal, truth=truth,
                truth_path=(output / 'ground_truth.json').relative_to(ROOT).as_posix(),
                truth_sha256=file_sha256(output / 'ground_truth.json'))


def canonical_key(key):
    result = []
    for value in key:
        if isinstance(value, np.generic): value = value.item()
        if isinstance(value, float) and not math.isfinite(value): value = None
        if isinstance(value, float) and value.is_integer(): value = int(value)
        result.append(value)
    return tuple(result)


def compare_groups(truths, predictions, intervals):
    truth_map = {canonical_key(r['key']):r for r in truths}
    keys = set(truth_map) | set(predictions)
    rows = []
    for key in sorted(keys, key=repr):
        item = truth_map.get(key)
        truth = float(Fraction(int(item['numerator']), int(item['denominator']))) if item is not None else None
        prediction = predictions.get(key)
        status = ('EXTRA_MODEL_GROUP' if item is None else
                  'MISSING_MODEL_GROUP' if key not in predictions else 'MATCHED')
        zero = truth == 0 if truth is not None else False
        error = abs(truth - prediction) if truth is not None and prediction is not None else None
        interval = intervals.get(key)
        rows.append(dict(key=list(key), status=status, truth=truth, prediction=prediction,
                         zero_truth=zero, absolute_error=error,
                         relative_error=error / abs(truth) if error is not None and not zero else None,
                         model_interval=interval,
                         model_covers_truth=(interval[0] <= truth <= interval[1]) if interval is not None and truth is not None else None,
                         model_relative_half_width=((interval[1]-interval[0])/2/abs(prediction))
                         if interval is not None and prediction not in (None,0) else None))
    return rows


def query_spec(sql):
    found = re.fullmatch(r'\s*SELECT\s+(.+?)\s+FROM\s+flights\s*(.*?)\s*;?\s*',sql,re.I)
    if not found: raise ValueError('unsupported Flights SQL')
    select, tail = found.groups(); tail = tail.rstrip(';').strip()
    group = None
    grouped = re.search(r'\s*GROUP\s+BY\s+([a-z_]+)\s*$',tail,re.I)
    if grouped:
        group = grouped.group(1).lower(); tail = tail[:grouped.start()].strip()
        selected_group, select = select.split(',',1)
        if selected_group.strip().lower() != group: raise ValueError('group projection differs')
    where = tail[5:].strip() if tail.upper().startswith('WHERE') else ''
    if tail and not where: raise ValueError('unsupported SQL tail')
    difference = re.fullmatch(r'SUM\((\w+)\)\s*-\s*SUM\((\w+)\)',select.strip(),re.I)
    components = []
    if difference:
        components = [v.lower() for v in difference.groups()]
        expression = 'COALESCE({},0)-COALESCE({},0)'.format(*components)
        kind, scale = 'DIFF',10
    else:
        aggregate = re.fullmatch(r'(AVG|SUM|COUNT)\(([^)]+)\)',select.strip(),re.I)
        if not aggregate: raise ValueError('unsupported aggregate')
        kind, expression = aggregate.groups(); kind=kind.upper(); expression=expression.lower().strip()
        if kind == 'COUNT':
            if expression != '*': raise ValueError('only COUNT(*) supported')
            expression,scale = '1',1
        else:
            parts=expression.split('*')
            if not all(part.strip() in NUMERIC for part in parts): raise ValueError('unsupported numeric expression')
            scale=10**len(parts)
    def scaled(match):
        value=Decimal(match.group(3))*10
        if value != value.to_integral_value(): raise ValueError('threshold not exact tenths')
        return match.group(1)+match.group(2)+str(int(value))
    where=re.sub(r'\b('+'|'.join(NUMERIC)+r')\s*(>=|<=|<>|!=|=|>|<)\s*(-?\d+(?:\.\d+)?)',scaled,where,flags=re.I)
    return dict(kind=kind,expression=expression,scale=scale,where=where,group=group,components=components)


class IntegerMoments:
    def __init__(self): self.count,self.total,self.square = 0,0,0
    def step(self,value):
        if value is None: return
        if not isinstance(value,int): raise ValueError('SQLite expression lost integer precision')
        self.count+=1; self.total+=value; self.square+=value*value
    def finalize(self): return json.dumps([self.count,self.total,self.square])


def sample_moments(path, sqls, database=':memory:'):
    validate_header(path)
    connection=sqlite3.connect(str(database))
    try:
        connection.execute('DROP TABLE IF EXISTS flights')
        ddl=','.join(c.lower()+(' INTEGER' if c.lower() in NUMERIC+('year_date',) else ' TEXT') for c in COLUMNS)
        connection.execute('CREATE TABLE flights('+ddl+')')
        connection.create_aggregate('exact_moments',1,IntegerMoments)
        with Path(path).open(newline='',encoding='utf-8') as stream:
            reader=csv.reader(stream); next(reader); pending=[]
            for row in reader:
                values=[]
                for name,value in zip(COLUMNS,row):
                    if value == '': value=None
                    elif name.lower() in NUMERIC+('year_date',):
                        scaled=Decimal(value)*(10 if name.lower() in NUMERIC else 1)
                        if scaled != scaled.to_integral_value(): raise ValueError('non-exact tenths sample value')
                        value=int(scaled)
                    values.append(value)
                if len(values)!=12: raise ValueError('sample field count differs')
                pending.append(values)
                if len(pending)>=10000:
                    connection.executemany('INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',pending); pending=[]
            if pending: connection.executemany('INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',pending)
        connection.commit()
        result=[]
        for sql in sqls:
            spec=query_spec(sql); group=spec['group']
            columns=([group] if group else [])+['exact_moments('+spec['expression']+')','COUNT(*)']
            columns+=['COUNT('+c+')' for c in spec['components']]
            statement='SELECT '+','.join(columns)+' FROM flights'
            if spec['where']: statement+=' WHERE '+spec['where']
            if group: statement+=' GROUP BY '+group
            groups=[]
            for values in connection.execute(statement):
                key=canonical_key(values[:1]) if group else ()
                rest=values[1:] if group else values
                count,total,square=json.loads(rest[0]) if rest[0] is not None else (0,0,0)
                groups.append(dict(key=list(key),count=count,sum_integer=total,square_sum_integer=square,
                                   filter_count=rest[1],component_non_null_counts=list(rest[2:]),scale=spec['scale']))
            result.append(dict(sql=sql,kind=spec['kind'],groups=groups))
        return result
    finally: connection.close()


def reference_ci(moment,kind,population,sample_size):
    count=int(moment['count']); filtered=int(moment['filter_count']); z=float(norm.ppf(.95))
    result=dict(eligible=False,status='EXCLUDED_SAMPLE_COUNT_LT_10',interval=None,z=z,
                sample_count=count,sample_filter_count=filtered)
    if min(count,filtered)<10: return result
    if any(v==0 for v in moment.get('component_non_null_counts',[])):
        result['status']='ALL_NULL_SUM_COMPONENT'; return result
    total=int(moment['sum_integer']); squares=int(moment['square_sum_integer']); scale=int(moment['scale'])
    mean=Fraction(total,count*scale)
    sample_variance=(Fraction(squares,1)-Fraction(total*total,count))/(count-1)/(scale*scale)
    if sample_variance<0: raise ValueError('negative exact sample variance')
    variance_avg=sample_variance/count
    p=Fraction(count,sample_size); expected_count=population*p
    variance_count=population*population*p*(1-p)/sample_size
    if kind=='AVG': point,variance=mean,variance_avg
    elif kind=='COUNT': point,variance=expected_count,variance_count
    elif kind in ('SUM','DIFF'):
        point=expected_count*mean
        variance=(variance_count+expected_count*expected_count)*variance_avg+variance_count*mean*mean
    else: raise ValueError('unsupported CI aggregate')
    point=float(point); se=math.sqrt(float(variance)); half=z*se
    result.update(eligible=True,status='ELIGIBLE',point=point,standard_error=se,
                  interval=[point-half,point+half],relative_half_width=half/abs(point) if point else None,
                  sample_variance=float(sample_variance),assumption='independent count and conditional mean; central normal90pct')
    return result


@contextmanager
def stage_lock(directory):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    with (directory/'run.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def atomic_pickle(path,value):
    path=Path(path); temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('wb') as stream:
        pickle.dump(value,stream,pickle.HIGHEST_PROTOCOL); stream.flush(); os.fsync(stream.fileno())
    os.replace(str(temp),str(path))


def stage_code_seal(stage):
    names={'prepare':['prepare_input','read_sample_header','validate_header','schema_for_input'],
           'model':['train_model','schema_for_input'],
           'evaluation':['evaluate_model','sample_moments','IntegerMoments','query_spec','reference_ci','compare_groups','legacy_comparison','canonical_key']}
    relevant={name:inspect.getsource(globals()[name]) for name in names[stage]}
    relevant['seal_logic']=inspect.getsource(stage_code_seal)
    relevant['common']=file_sha256(ROOT/'code/full_common.py')
    relevant['algorithm']=algorithm_seal()
    relevant['header']=COLUMNS; relevant['numeric_columns']=NUMERIC
    relevant['protocol']='flights_header_fd_rspn_rdc03_min1pct_actual_n_v1'
    import platform,scipy
    relevant['runtime']=[platform.python_version(),np.__version__,pd.__version__,scipy.__version__]
    return binding_hash(relevant)


def schema_for_input(path,population):
    from schemas.flights.schema import gen_flights_10M_schema
    schema=gen_flights_10M_schema(str(path))
    table=schema.table_dictionary['flights']
    table.csv_file_location=str(path); table.table_size=int(population)
    # The file is the actual sample. Population normalization is supplied to AQPSPN.
    table.sample_rate=1.0
    return schema


def prepare_input(source,max_rows=10000000,seed=1):
    import data_preparation.prepare_single_tables as original
    if not 100<=max_rows<=10000000: raise ValueError('training cap must be between100 and10M')
    core={k:source[k] for k in ('source','population_rows','sample_rows','sample_path','sample_sha256',
                               'generation_binding','generation_checkpoint_sha256','truth_path','truth_sha256','paper_scale_reached')}
    binding=dict(input=core,max_rows=max_rows,seed=seed,code=stage_code_seal('prepare'))
    directory=FULL/'flights'/('prepared_'+binding_hash(binding))
    with stage_lock(directory):
        path=directory/'prepared.json'
        if path.exists():
            result=json.loads(path.read_text())
            if result['binding']!=binding_hash(binding): raise ValueError('prepared binding differs')
            verify_artifacts(result['artifacts'])
            return result
        source_path=ROOT/source['sample_path']
        if file_sha256(source_path)!=source['sample_sha256']: raise ValueError('source sample changed before preparation')
        frame=read_sample_header(source_path)
        if len(frame)!=source['sample_rows']: raise ValueError('sample actual rows differ during preparation')
        training_path=source_path
        if len(frame)>max_rows:
            frame=frame.sample(n=max_rows,random_state=seed)
            training_path=directory/'training_sample.csv'
            export=frame.copy(); export.columns=COLUMNS
            export.to_csv(str(training_path)+'.tmp',index=False)
            os.replace(str(training_path)+'.tmp',str(training_path))
        schema=schema_for_input(training_path,source['population_rows'])
        table=schema.table_dictionary['flights']
        original_reader=original.read_table_csv
        def reader(table_obj,csv_seperator=','):
            if table_obj is not table: raise ValueError('unexpected table in header adapter')
            current=frame.copy()
            current.columns=['flights.'+c for c in current.columns]
            return current
        temporary=directory/'flights.hdf.tmp'; hdf=directory/'flights.hdf'
        started=time.perf_counter()
        original.read_table_csv=reader
        try:
            metadata=original.prepare_single_table(schema,'flights',str(temporary),max_table_data=10000001)
        finally: original.read_table_csv=original_reader
        os.replace(str(temporary),str(hdf)); metadata['hdf_path']=str(hdf)
        prepared=pd.read_hdf(str(hdf))
        if list(prepared.columns)!=metadata['relevant_attributes_full']:
            raise ValueError('prepared columns and metadata differ')
        if not all('flights.'+c in prepared.columns for c in NUMERIC):
            raise ValueError('numeric Flights columns were lost during preparation')
        values=prepared.values.astype(np.float64)
        if not np.isfinite(values).all(): raise ValueError('prepared NULL sentinels must be finite')
        values_path=directory/'values.npy'
        with (directory/'values.npy.tmp').open('wb') as stream:
            np.save(stream,values,allow_pickle=False); stream.flush(); os.fsync(stream.fileno())
        os.replace(str(directory/'values.npy.tmp'),str(values_path))
        meta_path=directory/'metadata.pkl'; atomic_pickle(meta_path,{'flights':metadata})
        result=dict(status='PASS',binding=binding_hash(binding),binding_details=binding,source=core,
                    actual_training_rows=len(prepared),requested_training_rows=max_rows,
                    training_sample_path=training_path.relative_to(ROOT).as_posix(),
                    training_sample_sha256=file_sha256(training_path),columns=list(prepared.columns),
                    values_path=values_path.relative_to(ROOT).as_posix(),metadata_path=meta_path.relative_to(ROOT).as_posix(),
                    preparation_seconds=time.perf_counter()-started,
                    artifacts=[seal_record(p) for p in [hdf,values_path,meta_path,training_path]])
        atomic_json(path,result)
        return result


def train_model(prepared,formal_memory_approved=False,seed=1):
    from aqp_spn.aqp_spn import AQPSPN
    from ensemble_compilation.spn_ensemble import SPNEnsemble
    from spn.structure.StatisticalTypes import MetaType
    from rspn.algorithms.validity.validity import is_valid
    verify_artifacts(prepared['artifacts'])
    population=prepared['source']['population_rows']
    if population==1000000000 and not formal_memory_approved:
        raise ValueError('formal1B training awaits explicit parent memory release')
    binding=dict(prepared_binding=prepared['binding'],prepared_artifacts=prepared['artifacts'],
                 seed=seed,rdc_threshold=.3,min_cluster_fraction=.01,normalizer=population,
                 actual_training_rows=prepared['actual_training_rows'],code=stage_code_seal('model'))
    directory=FULL/'flights'/('model_'+binding_hash(binding))
    with stage_lock(directory):
        receipt=directory/'model.json'
        if receipt.exists():
            result=json.loads(receipt.read_text())
            if result['binding']!=binding_hash(binding): raise ValueError('model binding differs')
            verify_artifacts(result['artifacts']); return result
        np.random.seed(seed); random.seed(seed)
        with (ROOT/prepared['metadata_path']).open('rb') as stream: metadata=pickle.load(stream)
        frame=np.load(str(ROOT/prepared['values_path']),mmap_mode='r')
        columns=prepared['columns']; md=metadata['flights']
        types=[MetaType.DISCRETE if md['categorical_columns_dict'].get(c) is not None else MetaType.REAL for c in columns]
        schema=schema_for_input(ROOT/prepared['training_sample_path'],population)
        model=AQPSPN(types,md['null_values_column'],int(population),schema,[],
                     full_sample_size=len(frame),table_set={'flights'},column_names=columns,table_meta_data=metadata)
        started=time.perf_counter()
        model.learn(np.asarray(frame),rdc_threshold=.3,min_instances_slice=.01*len(frame))
        elapsed=time.perf_counter()-started
        valid,reason=is_valid(model.mspn,check_ids=True,check_cluster_centers=True)
        if not valid: raise ValueError(reason)
        if model.full_join_size!=population or model.full_sample_size!=len(frame): raise ValueError('model population/sample accounting differs')
        target=directory/'ensemble.pkl'; atomic_pickle(target,SPNEnsemble(schema,[model]))
        result=dict(status='PASS',binding=binding_hash(binding),binding_details=binding,
                    paper_scale_reached=prepared['source']['paper_scale_reached'],population_rows=population,
                    actual_training_rows=len(frame),requested_training_rows=prepared['requested_training_rows'],
                    learning_seconds=elapsed,model_path=target.relative_to(ROOT).as_posix(),
                    prepared=prepared,artifacts=[seal_record(target)])
        atomic_json(receipt,result); return result


def legacy_comparison(moment,kind,population,sample_size,reference):
    if not reference['eligible']: return dict(status='NOT_ELIGIBLE')
    from evaluation.confidence_interval_evaluation import evaluate_stds
    from ensemble_compilation.graph_representation import AggregationType
    count=moment['count']; total=moment['sum_integer']/moment['scale']
    if kind=='COUNT': value=count; aggregate=AggregationType.COUNT
    elif kind=='AVG': value=total/count; aggregate=AggregationType.AVG
    else: value=total; aggregate=AggregationType.SUM
    if value==0: return dict(status='LEGACY_RELATIVE_ERROR_UNDEFINED_AT_ZERO')
    _,half,_,_,_=evaluate_stds(reference['point'],reference['interval'],count,sample_size,
                              math.sqrt(reference['sample_variance']),value,aggregate,population/sample_size)
    expected=reference['z']*reference['standard_error']
    return dict(status='COMPARED_NOT_USED_AS_TRUTH',released_reference_half_width=float(half),
                corrected_reference_half_width=expected,ratio=float(half)/expected if expected else None,
                sum_units_note='Released SUM combines count variance with probability mean; corrected reference uses count mean and variance consistently'
                if kind in ('SUM','DIFF') else None)


def evaluate_model(trained,source):
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.utils import parse_query
    from full_factor_cache import model_aware_factor_cache
    verify_artifacts(trained['artifacts'])
    prepared=trained['prepared']; verify_artifacts(prepared['artifacts'])
    if prepared['source']['generation_binding']!=source['generation_binding'] or prepared['source']['truth_sha256']!=source['truth_sha256']:
        raise ValueError('model and population truth binding differ')
    sqls=SQL_PATH.read_text().splitlines()
    binding=dict(model_binding=trained['binding'],model_artifacts=trained['artifacts'],
                 sample_sha256=prepared['training_sample_sha256'],population=source['population_rows'],
                 actual_training_rows=prepared['actual_training_rows'],truth_sha256=source['truth_sha256'],
                 sql_sha256=file_sha256(SQL_PATH),code=stage_code_seal('evaluation'),
                 cache_adapter=file_sha256(ROOT/'code/full_factor_cache.py'),
                 parser=file_sha256(ROOT/'code/evaluation/utils.py'),
                 legacy_ci=file_sha256(ROOT/'code/evaluation/confidence_interval_evaluation.py'),
                 ci_protocol='same_actual_sample_exact_integer_moments_independent_count_mean_center90_v1')
    directory=(ROOT/trained['model_path']).parent
    result_path=FULL/'results'/('flights_model_'+binding_hash(binding)+'_evaluation.json')
    with stage_lock(directory):
        if result_path.exists():
            result=json.loads(result_path.read_text())
            if result['binding']!=binding_hash(binding): raise ValueError('evaluation binding differs')
            verify_artifacts(result['artifacts']); return result
        moment_path=(ROOT/prepared['values_path']).parent/('moments_'+binding_hash(binding)[:16]+'.json')
        if moment_path.exists():
            moment_result=json.loads(moment_path.read_text())
            if moment_result['binding']!=binding_hash(binding): raise ValueError('sample moment binding differs')
            moments=moment_result['queries']
        else:
            # Keep the bundled SQLite Win32 VFS path below MAX_PATH.
            database=FULL/'flights'/('prepared_moments_'+binding_hash(binding)[:16]+'.sqlite')
            moments=sample_moments(ROOT/prepared['training_sample_path'],sqls,database)
            atomic_json(moment_path,dict(binding=binding_hash(binding),queries=moments,
                                        arithmetic='Python exact integer totals/squares, rational unbiased variance',
                                        source_sha256=prepared['training_sample_sha256']))
        ensemble=read_ensemble(str(ROOT/trained['model_path']),build_reverse_dict=True)
        queries=[]; errors=0
        with model_aware_factor_cache():
            for i,sql in enumerate(sqls):
                query=parse_query(sql,ensemble.schema_graph)
                ensemble.cached_expecation_vals={}
                started=time.perf_counter(); failure=None
                try:
                    raw_intervals,predicted=ensemble.evaluate_query(query,confidence_intervals=True,
                                                        confidence_sample_size=prepared['actual_training_rows'])
                except Exception as error:
                    failure=type(error).__name__+': '+str(error); errors+=1
                    ensemble.cached_expecation_vals={}
                    try: _,predicted=ensemble.evaluate_query(query,confidence_intervals=False)
                    except Exception as point_error:
                        failure+='; point: '+type(point_error).__name__+': '+str(point_error); predicted=[]
                    raw_intervals=None
                elapsed=time.perf_counter()-started
                predictions={}; intervals={}; nonfinite=[]
                def scalar(value):
                    value=float(np.asarray(value).reshape(-1)[0])
                    return value if math.isfinite(value) else None
                if query.group_bys:
                    for j,item in enumerate(predicted):
                        key=canonical_key(item[:-1]); predictions[key]=scalar(item[-1])
                        if raw_intervals is not None:
                            pair=[scalar(v) for v in raw_intervals[j]]
                            if None in pair: nonfinite.append(dict(key=list(key),raw=repr(raw_intervals[j])))
                            else: intervals[key]=pair
                elif not isinstance(predicted,list) or predicted:
                    predictions[()]=scalar(predicted)
                    if raw_intervals is not None:
                        pair=[scalar(v) for v in raw_intervals]
                        if None in pair: nonfinite.append(dict(key=[],raw=repr(raw_intervals)))
                        else: intervals[()]=pair
                truth=source['truth']['queries'][i]
                rows=compare_groups(truth['groups'],predictions,intervals)
                moment_map={canonical_key(g['key']):g for g in moments[i]['groups']}
                for item in rows:
                    moment=moment_map.get(canonical_key(item['key']),dict(count=0,filter_count=0,sum_integer=0,square_sum_integer=0,scale=1))
                    reference=reference_ci(moment,moments[i]['kind'],source['population_rows'],prepared['actual_training_rows'])
                    if reference['eligible']:
                        reference['covers_population_truth']=(reference['interval'][0]<=item['truth']<=reference['interval'][1]) if item['truth'] is not None else None
                    item['sample_moments']=moment
                    item['reference_ci']=reference
                    item['released_ci_comparison']=legacy_comparison(moment,moments[i]['kind'],source['population_rows'],prepared['actual_training_rows'],reference)
                    item['model_value_status']='FINITE' if item['prediction'] is not None else 'UNAVAILABLE_OR_NONFINITE'
                true_rows=[r for r in rows if r['truth'] is not None]
                eligible=[r for r in true_rows if r['reference_ci']['eligible']]
                relative=[r['relative_error'] for r in true_rows if r['relative_error'] is not None]
                penalized=[r['relative_error'] if r['relative_error'] is not None else 1. for r in true_rows if not r['zero_truth']]
                queries.append(dict(query_no=i,query_name=QUERY_NAMES[i],sql=sql,latency_ms=elapsed*1000,
                                    query_error=failure,nonfinite_original_intervals=nonfinite,
                                    truth_groups=len(truth['groups']),model_groups=len(predictions),
                                    missing_model_groups=sum(r['status']=='MISSING_MODEL_GROUP' for r in rows),
                                    extra_model_groups=sum(r['status']=='EXTRA_MODEL_GROUP' for r in rows),
                                    zero_truth_groups=sum(r['zero_truth'] for r in rows),
                                    mean_relative_error_matched_nonzero=float(np.mean(relative)) if relative else None,
                                    coverage_penalized_mean_relative_error=float(np.mean(penalized)) if penalized else None,
                                    missing_group_penalty_policy='unit relative error penalty; no invented model aggregate',
                                    ci_eligible_truth_groups=len(eligible),ci_excluded_groups=len(true_rows)-len(eligible),
                                    model_ci_coverage_all_eligible=sum(r['model_covers_truth'] is True for r in eligible)/len(eligible) if eligible else None,
                                    reference_ci_coverage=sum(r['reference_ci']['covers_population_truth'] is True for r in eligible)/len(eligible) if eligible else None,
                                    f5_2_warning='Correlated SUM terms violate independent-estimate approximation' if i==11 else None,
                                    groups=rows))
        result=dict(status='PASS' if errors==0 else 'MODEL_QUERY_ERRORS_RECORDED',
                    stage='PAPER_SCALE_FLIGHTS_LOCAL_RSPN_AQP_CI' if source['paper_scale_reached'] else 'SMALL_SCALE_FLIGHTS_MODEL_GOLDEN_ONLY',
                    paper_scale_reached=source['paper_scale_reached'],population_rows=source['population_rows'],
                    actual_training_rows=prepared['actual_training_rows'],requested_training_rows=prepared['requested_training_rows'],
                    binding=binding_hash(binding),binding_details=binding,query_errors=errors,
                    source_truth_path=source['truth_path'],source_generation_binding=source['generation_binding'],
                    prepared_path=prepared['values_path'],model_path=trained['model_path'],learning_seconds=trained['learning_seconds'],
                    confidence_level=.90,z=float(norm.ppf(.95)),relative_ci_definition='half width / abs(point); undefined at zero',
                    reference_variance='independent count*conditional AVG product; unbiased conditional sample variance; no finite population correction',
                    original_ci_preserved=True,queries=queries,
                    artifacts=[seal_record(moment_path)]+trained['artifacts'],
                    result_path=result_path.relative_to(ROOT).as_posix())
        atomic_json(result_path,result); return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['audit','prepare','train','evaluate','all'])
    parser.add_argument('--source',default='golden-200k/continuous')
    parser.add_argument('--paper',action='store_true')
    parser.add_argument('--formal-memory-approved',action='store_true')
    parser.add_argument('--max-rows',type=int,default=10000000)
    parser.add_argument('--seed',type=int,default=1)
    args=parser.parse_args(argv)
    source=load_generated_input(args.source,paper=args.paper)
    if args.action=='audit':
        print(json.dumps({k:v for k,v in source.items() if k!='truth'})); return
    if source['population_rows']==1000000000 and not args.formal_memory_approved:
        raise ValueError('formal preparation/training awaits parent memory release')
    prepared=prepare_input(source,args.max_rows,args.seed)
    if args.action=='prepare': result=prepared
    else:
        trained=train_model(prepared,args.formal_memory_approved,args.seed)
        result=trained if args.action=='train' else evaluate_model(trained,source)
    print(json.dumps({k:result.get(k) for k in ['status','stage','paper_scale_reached','population_rows',
                      'actual_training_rows','requested_training_rows','query_errors','model_path','result_path']},ensure_ascii=False))


if __name__=='__main__': main()
