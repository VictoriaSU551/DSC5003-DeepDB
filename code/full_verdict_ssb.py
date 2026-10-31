"""Original Verdict SSB candidate: pure planning/decoding, no science executor.

This module deliberately has no database, JVM, subprocess or SQLite entry point.
Pure gates do not establish support of any SSB query in the original engine.
"""
import argparse
import base64
import hashlib
import json
import math
import re
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = 'code/benchmarks/ssb/sql/aqp_queries.sql'
SCHEMA_PATH = 'code/benchmarks/ssb/setup-sql/schema.sql'
SQL_SHA256 = '37bf231b917f5c5995decb576566596acfc37722ed08e554252e68e91f839e32'
SCHEMA_SHA256 = '250abfbb28d74a8ded09110be6b16c2b472d6541691621b88e7a562ddb5a85dd'
VERDICT_COMMIT = 'b59209f626d278687ea0a801295b41064c7fecbb'
JAR_SHA256 = '05dd0ec816c2c11ec143ff1aa3084a296a5156ec9fc11923b0068bdc3625b0a1'
QUERY_IDS = ('Q1.1', 'Q1.2', 'Q1.3', 'Q2.1', 'Q2.2', 'Q2.3', 'Q3.1', 'Q3.2', 'Q3.3', 'Q3.4', 'Q4.1', 'Q4.2', 'Q4.3')
GROUP_WIDTHS = (0, 0, 0, 2, 2, 2, 3, 3, 3, 3, 2, 3, 3)
MODES = ('nobound', 'subsampling')
PROFIT = re.compile(r'sum\(lo_revenue\)\s*-\s*sum\(lo_supplycost\)', re.IGNORECASE)
DENOMINATOR = 2**64
SF2_BENCHMARK = 'output/full/ssb/native_v2/benchmark_sf2_315fee3c562d6361'
SF2_GOLDEN = 'output/full/ssb/native_v2/corrected_sf2_f31b7c6e2194db66'
SF2_BENCHMARK_SHA = 'b0c904816a21d38edfb83db1969bd796146670d5108aa0b32f4560a1921b25a7'
SF2_GOLDEN_SHA = 'f9c30ce9d9a017ba8eeabffc7878a2a1e865056ab6ba8d2e19a079d6a7879146'
SF2_SAMPLE_SHA = '2ccbfc5d5c32f3c6bb792b292fbed38f33af4e05df0c7fbe306c0eaee325bc5a'
DIMENSIONS = {'customer': (8, 60000), 'supplier': (7, 4000), 'part': (9, 400000), 'date': (17, 2556)}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def load_queries(root=ROOT):
    path = Path(root) / SQL_PATH
    if digest(path) != SQL_SHA256:
        raise ValueError('SSB SQL hash mismatch')
    queries = [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(queries) != 13 or len(set(queries)) != 13 or any(not q.endswith(';') for q in queries):
        raise ValueError('Expected 13 unique original complete SSB SQL statements')
    return queries


def call_plan(queries):
    # Identity is the whole ordered original workload, not only query count.
    if list(queries) != load_queries():
        raise ValueError('Original ordered SSB query identity mismatch')
    calls = []
    for mode in MODES:
        for query_no, sql in enumerate(queries):
            expressions = [('RAW', sql)]
            if query_no >= 10:
                if len(PROFIT.findall(sql)) != 1:
                    raise ValueError('Profit SQL projection mismatch')
                expressions += [('SUM_REVENUE', PROFIT.sub('sum(lo_revenue)', sql)),
                                ('SUM_SUPPLYCOST', PROFIT.sub('sum(lo_supplycost)', sql))]
            for role, text in expressions:
                calls.append(dict(call_id='{}.{}.{}'.format(QUERY_IDS[query_no], role.lower(), mode),
                                  query_no=query_no, query_id=QUERY_IDS[query_no],
                                  group_width=GROUP_WIDTHS[query_no], role=role, mode=mode,
                                  sql=text, sql_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()))
    return calls


def rational(value):
    return dict(numerator=value.numerator, denominator=value.denominator)


def scaling_contract(n, N, cutoff):
    if any(type(x) is not int for x in (n, N, cutoff)) or not 0 < n <= N or not 0 < cutoff <= DENOMINATOR:
        raise ValueError('Invalid n/N or generator integer cutoff')
    p = Fraction(cutoff, DENOMINATOR)
    return dict(sample_rows=n, population_rows=N,
                verdict_probability=rational(Fraction(n, N)),
                verdict_weight=rational(Fraction(N, n)),
                generator_probability=rational(p),
                deepdb_normalizer=rational(Fraction(n, 1) / p),
                query_truth_used_for_registration=False)


def scaled_sample_sum(value, n, N):
    if type(value) is not int:
        raise ValueError('Independent sample SUM must remain an integer')
    scaling_contract(n, N, 1)
    return Fraction(value * N, n)


def decode_token(value):
    if value == 'N':
        return None
    if not value.startswith('V'):
        raise ValueError('Invalid original-engine cell prefix')
    try:
        return base64.b64decode(value[1:], validate=True).decode('utf-8')
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid original-engine base64 cell') from error


def numeric(value):
    if value is None:
        return None, 'NULL'
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None, 'NONNUMERIC'
    return number if math.isfinite(number) else None, 'FINITE' if math.isfinite(number) else 'NONFINITE'


def decoded_row(cells, width, mode):
    expected = width + (2 if mode == 'subsampling' else 1)
    if len(cells) != expected:
        raise ValueError('Original engine row arity mismatch')
    point, point_status = numeric(cells[width])
    interval = None
    half = None
    if mode == 'subsampling':
        half, half_status = numeric(cells[width + 1])
        if half_status != 'FINITE':
            ci_status = half_status
        elif half < 0:
            ci_status = 'NEGATIVE_HALFWIDTH'
        elif point_status != 'FINITE':
            ci_status = point_status + '_POINT'
        elif not all(math.isfinite(x) for x in (point - half, point + half)):
            ci_status = 'NONFINITE_INTERVAL'
        else:
            ci_status, interval = 'FINITE', [point - half, point + half]
    else:
        ci_status = 'NOT_REQUESTED'
    return dict(key=cells[:width], point=point, point_status=point_status,
                interval95=interval, halfwidth95=half, ci_status=ci_status, raw_cells=cells)


def parse_engine(text, calls):
    """Decode a complete single namespace; refuse duplicates/truncation/unknown IDs.

    ERROR plus TIME is completed evidence of failure, never a successful point.
    Rows produced before an error remain raw diagnostics.
    """
    expected = {c['call_id']: c for c in calls}
    if len(expected) != len(calls) or not calls or any(c['mode'] not in MODES for c in calls):
        raise ValueError('Invalid/duplicate expected call identities')
    results = {qid: dict(call=c, labels=None, rows=[], error=None, elapsed_ns=None)
               for qid, c in expected.items()}
    group_sets = {qid: set() for qid in expected}
    for line in text.splitlines():
        fields = line.split('\t')
        if len(fields) < 2 or fields[0] not in ('META', 'ROW', 'ERROR', 'TIME') or fields[1] not in expected:
            raise ValueError('Unknown original engine record or call identity')
        kind, qid = fields[:2]
        result, c = results[qid], expected[qid]
        if result['elapsed_ns'] is not None:
            raise ValueError('Duplicate completion or records after TIME')
        if kind == 'TIME':
            if len(fields) != 3 or not fields[2].isdigit() or (result['labels'] is None and result['error'] is None):
                raise ValueError('Invalid or unaccounted completion')
            result['elapsed_ns'] = int(fields[2])
        elif kind == 'ERROR':
            if len(fields) != 3 or result['error'] is not None:
                raise ValueError('Duplicate/malformed engine error')
            result['error'] = decode_token(fields[2])
            if result['error'] is None:
                raise ValueError('NULL error record')
        elif kind == 'META':
            if result['labels'] is not None or result['error'] is not None:
                raise ValueError('Duplicate/out-of-order engine metadata')
            result['labels'] = [decode_token(v) for v in fields[2:]]
            count = c['group_width'] + (2 if c['mode'] == 'subsampling' else 1)
            if len(result['labels']) != count:
                raise ValueError('Engine metadata arity mismatch')
        else:
            if result['labels'] is None or result['error'] is not None:
                raise ValueError('ROW without META or after ERROR')
            row = decoded_row([decode_token(v) for v in fields[2:]], c['group_width'], c['mode'])
            key = tuple(row['key'])
            if key in group_sets[qid]:
                raise ValueError('Duplicate engine group key')
            group_sets[qid].add(key)
            result['rows'].append(row)
    for result in results.values():
        if result['elapsed_ns'] is None:
            raise ValueError('Missing original-engine TIME completion')
        result['status'] = 'ENGINE_ERROR' if result['error'] is not None else 'RETURNED'
        result['usable_for_point_comparison'] = result['error'] is None
    return results


def subtract_groups(left, right):
    def index(rows):
        out = {}
        for row in rows:
            key = tuple(row['key'])
            if key in out:
                raise ValueError('duplicate child group key')
            out[key] = row
        return out
    a, b = index(left), index(right)
    result = []
    for key in sorted(set(a) | set(b), key=lambda x: json.dumps(x)):
        value = None
        if key not in a:
            status = 'MISSING_LEFT'
        elif key not in b:
            status = 'MISSING_RIGHT'
        else:
            x, sx = numeric(a[key]['point'])
            y, sy = numeric(b[key]['point'])
            if sx != 'FINITE' or sy != 'FINITE':
                status = 'INVALID_CHILD_POINT'
            elif not math.isfinite(x - y):
                status = 'NONFINITE_DIFFERENCE'
            else:
                status, value = 'MATCHED', x - y
        result.append(dict(key=list(key), point=value, status=status,
                           method='TWO_ORIGINAL_SUM_POINT_ADAPTER', interval95=None,
                           ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL'))
    return result


def profit_adapter(raw, left, right):
    """Consumption boundary: failed child rows remain diagnostics, never points."""
    identities = call_plan(load_queries())
    qno, mode = raw['call']['query_no'], raw['call']['mode']
    if qno not in (10, 11, 12) or mode not in MODES:
        raise ValueError('Not an original SSB profit query')
    expected = [c for c in identities if c['query_no'] == qno and c['mode'] == mode]
    for result, c in zip((raw, left, right), expected):
        if result['call'] != c:
            raise ValueError('Profit adapter query/SQL/role identity mismatch')
        if result['status'] not in ('ENGINE_ERROR', 'RETURNED') or result['usable_for_point_comparison'] != (result['status'] == 'RETURNED'):
            raise ValueError('Inconsistent original child completion state')
    children_ok = all(r['usable_for_point_comparison'] and r['error'] is None for r in (left, right))
    return dict(status='POINT_ADAPTER_RETURNED' if children_ok else 'ENGINE_ERROR',
                query_no=qno, mode=mode, raw_compound=raw, children=[left, right],
                groups=subtract_groups(left['rows'], right['rows']) if children_ok else [],
                ci_status='UNSUPPORTED_NO_COVARIANCE_MODEL')


def normalize_pipe_records(source, target, width, terminal_pipe=False):
    """Bounded raw pipe → COPY CSV; preserve every field and duplicate row.

    Empty strings and literal backslash-N are quoted so COPY NULL '\\N' cannot
    reinterpret either value. Do not strip whitespace or parse original strings.
    """
    if type(width) is not int or width < 1:
        raise ValueError('Invalid raw row width')
    count = 0
    for line in source:
        if not line.endswith('\n') or '\x00' in line:
            raise ValueError('Incomplete or NUL-containing raw row')
        raw = line[:-1]
        if raw.endswith('\r'):
            raw = raw[:-1]
        if terminal_pipe:
            if not raw.endswith('|'):
                raise ValueError('Missing raw terminal pipe')
            raw = raw[:-1]
        fields = raw.split('|')
        if len(fields) != width or any('\r' in f or '\n' in f for f in fields):
            raise ValueError('Raw row field count/line ending mismatch')
        def quote(value):
            if value in ('', '\\N') or any(ch in value for ch in '|"\r\n'):
                return '"' + value.replace('"', '""') + '"'
            return value
        target.write('|'.join(quote(field) for field in fields) + '\n')
        count += 1
    return count


def canonical_truth(rows):
    values = {}
    for row in rows:
        qno, group, value = row['query_no'], row['group'], row['value']
        if type(qno) is not int or not 0 <= qno < 13 or type(value) is not int:
            raise ValueError('Invalid exact integer truth row')
        if not isinstance(group, list) or len(group) != GROUP_WIDTHS[qno] or any(type(x) is not str for x in group):
            raise ValueError('Truth group width/type mismatch')
        key = (qno, tuple(group))
        if key in values:
            raise ValueError('Duplicate canonical truth group')
        values[key] = value
    if {key[0] for key in values} != set(range(13)):
        raise ValueError('Incomplete 13-query population truth')
    return values


def validate_sample_lineage(benchmark, golden, checkpoint, truth):
    """Pure relation validation after caller has independently pinned receipts.

    This checks existing full-population evidence only; it computes no sample SQL.
    """
    if benchmark['status'] != 'PASS' or golden['status'] != 'PASS':
        raise ValueError('Unaccepted source receipts')
    if not all(golden[k] is True for k in ('all17_fields_equal', 'all_dimensions_equal', 'all13_exact_integer_aggregates_equal')) or benchmark['all13_integer_aggregates_equal'] is not True:
        raise ValueError('Missing original source golden proof')
    plan = benchmark['binding']['plan']
    binding = plan['binding']
    if str(binding['scale']) != '2' or checkpoint['binding'] != binding:
        raise ValueError('Sample plan/checkpoint binding mismatch')
    if binding['native_build_binding'] != golden['binding']['callback_binding']:
        raise ValueError('Sample/golden native callback source mismatch')
    if binding['effective_probability_numerator'] != binding['actual_cutoff'] or binding['effective_probability_denominator'] != DENOMINATOR:
        raise ValueError('Sample integer probability mismatch')
    n, N = benchmark['sample_rows'], benchmark['rows']
    scaling = scaling_contract(n, N, binding['actual_cutoff'])
    if checkpoint['complete'] is not True or checkpoint['next_shard'] != binding['shards'] or len(checkpoint['committed_shards']) != binding['shards']:
        raise ValueError('Incomplete committed source stream')
    if N != golden['rows'] or N != checkpoint['rows'] or n != checkpoint['sample_rows']:
        raise ValueError('Source population/sample count mismatch')
    descriptor = benchmark['sample_descriptor']
    if any(descriptor[a] != checkpoint[b] for a, b in [('bytes', 'sample_bytes'), ('sha256', 'sample_sha256'), ('rows', 'sample_rows')]):
        raise ValueError('Source sample descriptor mismatch')
    rows = samples = sample_bytes = 0
    next_order = 1
    ranges = []
    for index, shard in enumerate(checkpoint['committed_shards']):
        if shard['shard'] != index or shard['first_order'] != next_order or shard['orders'] < 1:
            raise ValueError('Noncontiguous/duplicate committed source shard')
        if any(type(shard[k]) is not int or shard[k] < 0 for k in ('rows', 'sample_rows', 'sample_bytes')) or shard['sample_rows'] > shard['rows']:
            raise ValueError('Invalid committed source counts')
        ranges.append([next_order, shard['orders']])
        next_order += shard['orders']
        rows += shard['rows']; samples += shard['sample_rows']; sample_bytes += shard['sample_bytes']
    if ranges != plan['ranges'] or next_order != binding['total_orders'] + 1 or (rows, samples, sample_bytes) != (N, n, descriptor['bytes']):
        raise ValueError('Committed source totals/ranges mismatch')
    exact = canonical_truth(truth)
    if canonical_truth(checkpoint['aggregates']) != exact or len(exact) != golden['truth_groups']:
        raise ValueError('Sample source full-population truth mismatch')
    return dict(scaling, truth_group_count=len(exact), sample_sql_computed=False, engine_calls_executed=0)


def file_descriptor(path):
    path = Path(path)
    return dict(path=str(path.resolve()), bytes=path.stat().st_size, sha256=digest(path))


def verify_benchmark_file_set(home, files):
    required = {'stream/' + name for name in ('checkpoint.json', 'execution.lock', 'lifecycle.json', 'lineorder_sampled.csv', 'native.stderr.log', 'plan.json')}
    required |= {'stream/chunks/{:08d}/{}'.format(i, name) for i in range(16)
                 for name in ('aggregates.tsv', 'seeds_after.tsv', 'stats.json')}
    if set(files) != required:
        raise ValueError('Benchmark required file set mismatch')
    result = {}
    for name in sorted(required):
        descriptor = file_descriptor(Path(home) / name)
        if descriptor['sha256'] != files[name]:
            raise ValueError('Benchmark physical artifact hash mismatch: ' + name)
        result[name] = descriptor
    return result


def verify_raw_rows(path, width, terminal_pipe):
    """Read-only field/count gate; no aggregate computation or retained copy."""
    count = 0
    with Path(path).open('rb') as source:
        for line in source:
            if not line.endswith(b'\n') or b'\x00' in line:
                raise ValueError('Incomplete physical raw row')
            raw = line[:-1]
            if raw.endswith(b'\r'):
                raw = raw[:-1]
            if terminal_pipe:
                if not raw.endswith(b'|'):
                    raise ValueError('Missing dimension terminal pipe')
                raw = raw[:-1]
            if len(raw.split(b'|')) != width or b'\r' in raw:
                raise ValueError('Physical raw field count mismatch')
            raw.decode('utf-8')
            count += 1
    return count


def inspect_sf2(root=ROOT):
    """Read only the fixed, completed SF2 namespace; never inspect SF500."""
    root = Path(root).resolve()
    bench, gold = root / SF2_BENCHMARK, root / SF2_GOLDEN
    artifacts = {}
    def read_pinned(path, expected):
        descriptor = file_descriptor(path)
        if descriptor['sha256'] != expected:
            raise ValueError('Pinned SF2 receipt/hash mismatch: ' + str(path))
        artifacts[str(path.relative_to(root))] = descriptor
        return json.loads(path.read_text(encoding='utf-8'))
    receipts = []
    for home, sha in ((bench, SF2_BENCHMARK_SHA), (gold, SF2_GOLDEN_SHA)):
        receipt = read_pinned(home / 'receipt.json', sha)
        for name, field in (('receipt_seal.json', 'sha256'), ('lifecycle.json', 'receipt_sha256')):
            path = home / name
            body = json.loads(path.read_text(encoding='utf-8'))
            if body[field] != sha or (name == 'lifecycle.json' and body['status'] != 'PASS'):
                raise ValueError('Unaccepted pinned SF2 receipt lifecycle')
            artifacts[str(path.relative_to(root))] = file_descriptor(path)
        receipts.append(receipt)
    benchmark, golden = receipts
    if benchmark['binding']['golden_receipt_sha256'] != SF2_GOLDEN_SHA:
        raise ValueError('Benchmark does not reference pinned SF2 golden')
    for name, descriptor in verify_benchmark_file_set(bench, benchmark['files_sha256']).items():
        artifacts[str((bench / name).relative_to(root))] = descriptor
    cp = json.loads((bench / 'stream/checkpoint.json').read_text(encoding='utf-8'))
    truth_path = gold / 'independent_truth.json'
    truth = read_pinned(truth_path, golden['files_sha256']['independent_truth.json'])
    relation = validate_sample_lineage(benchmark, golden, cp, truth)
    if (relation['population_rows'], relation['sample_rows'], relation['truth_group_count']) != (11997996, 39587, 1798):
        raise ValueError('Pinned SF2 population shape mismatch')
    source_binding = benchmark['binding']['plan']['binding']
    if json.loads((bench / 'stream/plan.json').read_text(encoding='utf-8')) != benchmark['binding']['plan']:
        raise ValueError('Physical SF2 stream plan mismatch')
    sample = bench / 'stream/lineorder_sampled.csv'
    desc = benchmark['sample_descriptor']
    if Path(desc['path']).resolve() != sample.resolve() or desc['sha256'] != SF2_SAMPLE_SHA or desc['bytes'] != sample.stat().st_size or verify_raw_rows(sample, 17, False) != 39587:
        raise ValueError('Physical SF2 sample descriptor/rows mismatch')
    dimensions = {}
    if set(source_binding['dimensions']) != set(DIMENSIONS):
        raise ValueError('Full four-dimension source set mismatch')
    for name, (width, rows) in DIMENSIONS.items():
        path = gold / 'dimensions' / (name + '.tbl')
        expected = source_binding['dimensions'][name]
        descriptor = file_descriptor(path)
        if descriptor != {k: expected[k] for k in ('path', 'bytes', 'sha256')} or descriptor['sha256'] != golden['files_sha256']['dimensions/' + name + '.tbl'] or expected['rows'] != rows or verify_raw_rows(path, width, True) != rows:
            raise ValueError('Full SF2 dimension binding/count mismatch: ' + name)
        descriptor['rows'] = rows
        dimensions[name] = descriptor
        artifacts[str(path.relative_to(root))] = descriptor
    # Retain original raw source IDs and exact fixed wrapper hashes as provenance.
    # This is not a rebuild or a re-execution of generator golden gates.
    for name, sha in source_binding['sources_sha256'].items():
        path = root / name
        if path.resolve().is_file() and root not in path.resolve().parents:
            raise ValueError('Source path outside project')
        descriptor = file_descriptor(path)
        if descriptor['sha256'] != sha:
            raise ValueError('SF2 native source/runtime hash mismatch: ' + name)
        artifacts[name] = descriptor
    return dict(schema='verdict_ssb_sf2_input_audit_v1', status='PASS_READ_ONLY_SOURCE_LINK_ONLY',
                native_source_id=source_binding['source_id'], scaling=relation,
                dimensions=dimensions, artifacts=artifacts,
                benchmark_receipt_sha256=SF2_BENCHMARK_SHA, golden_receipt_sha256=SF2_GOLDEN_SHA,
                sample_sha256=SF2_SAMPLE_SHA, engine_calls_executed=0,
                sample_sql_computed=False, formal_allowed=False)


def candidate_plan(root=ROOT):
    root = Path(root)
    if digest(root / SCHEMA_PATH) != SCHEMA_SHA256:
        raise ValueError('SSB schema hash mismatch')
    return dict(schema='verdict_ssb_candidate_v1', stage='CANDIDATE_PURE_ONLY',
                verdict_commit=VERDICT_COMMIT, jar_sha256=JAR_SHA256,
                sql_sha256=SQL_SHA256, schema_sha256=SCHEMA_SHA256,
                database='deepdb_verdict_ssb', protected_databases=['deepdb_job', 'deepdb_verdict'],
                dimension_policy='FULL_UNSAMPLED_NO_VPART',
                original_fact_policy='EMPTY_SCHEMA_ONLY',
                fact_registration_probability='ACTUAL_RETAINED_n/N',
                native_ci_probability=0.95, native_partition_count=100,
                population_rows=3000028242, calls=call_plan(load_queries(root)),
                engine_calls_executed=0, formal_allowed=False,
                required_before_formal=['ROOT_SOURCE_MODEL_REPLAY_ACCEPTANCE', 'SF2_ORIGINAL_ENGINE_GATE',
                                        'PROTECTED_DB_RESOURCE_REVIEW', 'MEASURED_PG_ALLOWANCE'],
                required_before_science=['ROOT_GO', 'NATIVE_FINAL_ACCEPTED', 'MEASURED_PG_ALLOWANCE'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'inspect-sf2'])
    parser.add_argument('--output', type=Path, help='New candidate JSON only; existing files are refused')
    args = parser.parse_args(argv)
    result = candidate_plan() if args.command == 'plan' else inspect_sf2()
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.output:
        allowed = (ROOT / 'output/full/verdict_ssb').resolve()
        if allowed not in args.output.resolve().parents:
            raise ValueError('Candidate output must be inside output/full/verdict_ssb')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as target:
            target.write(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
