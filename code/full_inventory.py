"""Read-only source/input audit; writes only the requested JSON receipt.

This module does not connect to databases, download data, import a trained
model, or train an estimator. A passing input audit is not a paper reproduction.
"""
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = '655ada13a043a4226a239b0c0a65bcdefef87a02'
MSCN_REF = '50073283eacdea300d1dcd815c720f64e3d2d400'
SOURCE_EXTENSIONS = {'.py', '.pyx', '.ipynb', '.c', '.cc', '.cpp', '.cxx', '.h',
                     '.hpp', '.sh', '.ps1', '.bat', '.cmd', '.r', '.java', '.scala', '.jl'}
SQL_TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|>=|<=|<>|!=|"
                       r'[A-Za-z_]\w*|\d+(?:\.\d+)?|[^\s]')
GROUP_COUNTS = {3: [97, 73, 49, 37, 14], 4: [70, 69, 56, 43, 22],
                5: [13, 23, 17, 21, 10], 6: [12, 23, 13, 11, 10]}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sql_tokens(query):
    """Ignore formatting/keyword case, retaining quoted values and identifiers."""
    tokens = SQL_TOKEN.findall(query.strip())
    if tokens and tokens[-1] == ';':
        tokens.pop()
    return tuple(token if token.startswith(("'", '"')) else token.casefold()
                 for token in tokens)


def query_dimensions(query):
    """Count tables and non-join conjuncts in the supplied flat JOB-light SQL."""
    tokens = sql_tokens(query)
    try:
        start = tokens.index('from') + 1
    except ValueError:
        raise ValueError('Query has no FROM clause')
    end = tokens.index('where') if 'where' in tokens else len(tokens)
    tables = 1 + tokens[start:end].count(',')
    conditions = []
    current = []
    for token in tokens[end + 1:]:
        if token == 'and':
            conditions.append(current)
            current = []
        else:
            current.append(token)
    if current:
        conditions.append(current)
    # All public group joins have the form alias.column = alias.column.
    def is_join(condition):
        return (len(condition) == 7 and condition[1] == '.' and
                condition[3] == '=' and condition[5] == '.' and
                all(re.fullmatch(r'[a-z_]\w*', condition[i]) for i in (0, 2, 4, 6)))
    return tables, sum(not is_join(condition) for condition in conditions)


def inspect_query_pair(sql_path, truth_path, expected_dimensions=None):
    sql_path, truth_path = Path(sql_path), Path(truth_path)
    physical_lines = sql_path.read_text(encoding='utf-8-sig').splitlines()
    queries = [(line_no, query.strip()) for line_no, query in enumerate(physical_lines, 1)
               if query.strip()]
    with truth_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        rows = list(reader)
    query_column = next((name for name in ('query', 'sql', 'query_string') if name in fields), None)
    cardinality_column = next((name for name in ('cardinality_true', 'true_cardinality', 'cardinality')
                               if name in fields), None)
    if query_column is None or cardinality_column is None:
        raise ValueError('Missing query or cardinality CSV column: {}'.format(truth_path))
    if len(queries) != len(rows):
        raise ValueError('SQL/truth row count mismatch: {} != {} ({})'.format(
            len(queries), len(rows), sql_path))
    dimensions = Counter()
    zero_truth = 0
    for index, ((line_no, query), row) in enumerate(zip(queries, rows)):
        if sql_tokens(query) != sql_tokens(row.get(query_column) or ''):
            raise ValueError('SQL mismatch at line {} (CSV record {}): {}'.format(
                line_no, index + 1, sql_path))
        if 'query_no' in fields and row['query_no'] != str(index):
            raise ValueError('query_no mismatch at line {}: {}'.format(line_no, truth_path))
        try:
            value = Decimal(row[cardinality_column])
        except (InvalidOperation, TypeError):
            raise ValueError('Invalid cardinality at line {}: {}'.format(line_no, truth_path))
        if not value.is_finite() or value < 0 or value != value.to_integral_value():
            raise ValueError('Invalid cardinality at line {}: {}'.format(line_no, truth_path))
        zero_truth += value == 0
        actual_dimensions = query_dimensions(query)
        dimensions['{}-{}'.format(*actual_dimensions)] += 1
        if expected_dimensions is not None and actual_dimensions != tuple(expected_dimensions):
            raise ValueError('Query dimensions mismatch at line {}: {} != {}'.format(
                line_no, actual_dimensions, expected_dimensions))
    return {'sql_path': str(sql_path), 'truth_path': str(truth_path),
            'sql_sha256': sha256(sql_path), 'truth_sha256': sha256(truth_path),
            'queries': len(queries), 'truth_rows': len(rows),
            'physical_lines': len(physical_lines),
            'blank_lines': len(physical_lines) - len(queries),
            'missing_terminal_semicolon_lines': [n for n, q in queries if not q.endswith(';')],
            'truth_columns': {'query': query_column, 'cardinality': cardinality_column,
                              'query_no': 'query_no' if 'query_no' in fields else None},
            'query_alignment': 'PASS', 'zero_truth_queries': zero_truth,
            'table_predicate_counts': dict(sorted(dimensions.items()))}


def classify_baseline_paths(paths):
    paths = sorted(paths)
    extensions = Counter(PurePosixPath(path).suffix.lower() or '[none]' for path in paths)
    implementations = [path for path in paths if PurePosixPath(path).suffix.lower() in SOURCE_EXTENSIONS]
    return {'files': len(paths), 'extension_counts': dict(sorted(extensions.items())),
            'implementation_source_extensions_checked': sorted(SOURCE_EXTENSIONS),
            'implementation_source_paths': implementations,
            'sql_resource_paths': [path for path in paths if PurePosixPath(path).suffix.lower() == '.sql'],
            'paths_outside_results': [path for path in paths if '/results/' not in path],
            'conclusion': ('IMPLEMENTATION_SOURCES_PRESENT' if implementations else
                           'NO_IMPLEMENTATION_SOURCE_FILES_IN_PINNED_BASELINES_TREE'),
            'historical_results_are_local_reruns': False}


def git_bytes(root, *arguments):
    return subprocess.check_output(['git', '-C', str(root)] + list(arguments))


def build_inventory(root=ROOT):
    root = Path(root).resolve()
    benchmark = root / 'code/benchmarks/job-light'
    reports = {}
    for label, expected in [('job_light', 70), ('synthetic', 5000), ('scale', 500)]:
        report = inspect_query_pair(benchmark / 'sql' / (label + '_queries.sql'),
                                    benchmark / 'sql' / (label + '_true_cardinalities.csv'))
        if report['queries'] != expected:
            raise ValueError('Pinned workload count changed: {} != {}'.format(report['queries'], expected))
        reports[label] = report
    groups = []
    for tables, expected_counts in sorted(GROUP_COUNTS.items()):
        for predicates, expected in enumerate(expected_counts, 1):
            stem = '{}_{}_SPN'.format(tables, predicates)
            report = inspect_query_pair(benchmark / 'scale_sql' / (stem + '.sql'),
                                        benchmark / 'scale_sql' / (stem + '.csv'),
                                        expected_dimensions=(tables, predicates))
            if report['queries'] != expected:
                raise ValueError('Pinned group count changed: {}'.format(stem))
            report.update(tables=tables, predicates=predicates)
            groups.append(report)
    # -z is essential: regular ls-tree display quotes Windows-invalid filenames.
    raw_paths = git_bytes(root, 'ls-tree', '-r', '-z', '--name-only', UPSTREAM, '--', 'baselines')
    paths = [item.decode('utf-8') for item in raw_paths.split(b'\0') if item]
    baselines = classify_baseline_paths(paths)
    baselines.update(upstream_commit=UPSTREAM,
                     tree_sha=git_bytes(root, 'rev-parse', UPSTREAM + ':baselines').decode().strip(),
                     path_listing_sha256=hashlib.sha256(raw_paths).hexdigest(),
                     enumeration='git ls-tree -r -z --name-only <commit> -- baselines')
    upstream_cli = git_bytes(root, 'show', UPSTREAM + ':maqp.py').decode('utf-8')
    upstream_readme = git_bytes(root, 'show', UPSTREAM + ':README.md').decode('utf-8')
    working_cli = (root / 'code/maqp.py').read_text(encoding='utf-8')
    files_to_seal = [Path(__file__).resolve(), root / 'code/tests/test_full_inventory.py',
                     root / 'docs/FULL_SOURCE_AUDIT.md', root / 'docs/FULL_REPRODUCTION_PROTOCOL.md']
    inventory = {
        'status': 'INPUT_AUDIT_PASS_WITH_GAPS',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Local source and SQL/truth alignment audit only; no estimator evaluation or training',
        'full_paper_reproduction_complete': False,
        'upstream_commit': UPSTREAM,
        'workloads': reports, 'generalization_groups': groups,
        'summary': {'job_light_queries': reports['job_light']['queries'],
                    'synthetic_queries': reports['synthetic']['queries'],
                    'scale_queries': reports['scale']['queries'],
                    'generalization_groups': len(groups),
                    'generalization_queries_3_to_6_tables': sum(x['queries'] for x in groups),
                    'figure_6_8_queries_4_to_6_tables': sum(x['queries'] for x in groups if x['tables'] >= 4),
                    'all_sql_truth_pairs_aligned': True},
        'paper_200_queries': {
            'status': 'NOT_IDENTIFIED_IN_PUBLIC_FILES', 'paper_claimed_count': 200,
            'public_group_query_count': sum(x['queries'] for x in groups),
            'selection_rule_or_query_ids': None,
            'restriction': 'Do not label all public queries or a newly sampled subset as the original 200.'},
        'upstream_baselines': baselines,
        'budget_difference': {
            'paper_section_6_budget': 0.5, 'upstream_readme_budget': 5,
            'upstream_cli_declaration': next(x.strip() for x in upstream_cli.splitlines()
                                             if "add_argument('--ensemble_budget_factor'" in x),
            'working_cli_declaration': next(x.strip() for x in working_cli.splitlines()
                                            if "add_argument('--ensemble_budget_factor'" in x),
            'upstream_readme_evidence': next(x.strip() for x in upstream_readme.splitlines()
                                             if '--ensemble_budget_factor 5' in x),
            'mapping_status': 'NO_VERIFIED_EQUIVALENCE_BETWEEN_PAPER_0_5_AND_README_5',
            'source': 'ensemble_creation/rdc_based.py:158-160 multiplies the numeric budget directly'},
        'external_mscn_source_audit': {
            'repository': 'https://github.com/andreaskipf/learnedcardinalities',
            'commit': MSCN_REF, 'verified_on': '2026-10-30',
            'verification': 'HEAD_HTTP_200_IN_SOURCE_AUDIT; not rechecked by this offline inventory',
            'training_data_downloaded_in_audit': False,
            'available_paths_and_bytes': {'data/train.csv': 10131572, 'data/train.bitmaps': 27459500,
                                         'workloads/job-light.csv': 11478,
                                         'workloads/job-light.bitmaps': 32030},
            'official_configuration': {'queries': 100000, 'epochs': 100, 'python': '3.7', 'pytorch': '1.0'},
            'training_csv_rows_independently_counted': False,
            'job_light_rows_checked': 70, 'job_light_truth_matches_local': True,
            'generalization_bitmaps_683_queries': 'NOT_LOCATED',
            'public_scale_sql_vs_local_scale_sql_different_rows': 499},
        'unresolved_requirements': [
            {'item': 'Figure 5 synthetic IMDb database generator and original parameters/seeds',
             'status': 'NOT_LOCATED_IN_AUDITED_PUBLIC_SOURCES'},
            {'item': 'Original 200-query selection or exact identifiers', 'status': 'NOT_IDENTIFIED'},
            {'item': 'Original Wavelets/IBJS/random-sampling/Perfect-Selectivities experiment drivers',
             'status': 'NOT_LOCATED_IN_PINNED_TREE_OR_AUDITED_FORKS'},
            {'item': 'MSCN inputs for DeepDB 683-query generalization workload', 'status': 'BITMAPS_NOT_LOCATED'},
            {'item': 'C++ numeric leaf boundary correctness',
             'status': 'REQUIRES_DIFFERENTIAL_TEST',
             'source': 'code/rspn/code_generation/templates/identity_leave.cpp:38-44'},
            {'item': 'C++ generation rewrites the model with assigned IDs',
             'status': 'COPY_AND_SEAL_MODEL_BEFORE_CODE_GENERATION',
             'source': 'code/rspn/code_generation/generate_code.py:184-200'},
            {'item': 'Original baseline and large AQP experiments rerun locally', 'status': 'NOT_ESTABLISHED_BY_THIS_AUDIT'}],
        'audit_file_seals': {path.relative_to(root).as_posix(): sha256(path) for path in files_to_seal},
    }
    for report in list(reports.values()) + groups:
        for key in ('sql_path', 'truth_path'):
            report[key] = Path(report[key]).relative_to(root).as_posix()
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/full/results/source_inventory.json')
    args = parser.parse_args()
    result = build_inventory()
    target = args.output.resolve()
    allowed = (ROOT / 'output/full/results').resolve()
    if allowed not in target.parents:
        parser.error('Inventory output must stay inside output/full/results')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(target))
    print(json.dumps({'status': result['status'], 'summary': result['summary'],
                      'output': str(target)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
