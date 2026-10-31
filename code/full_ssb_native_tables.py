"""Render native SF500 tables only after a real, accepted reverse replay."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_formal_report(report, sample_rows):
    if (report['stage'] != 'SSB_NATIVE_V2_SF500_SINGLE_1M_AQP_CI'
            or report['spn_count'] != 5 or report['population_rows'] != 3000028242
            or report['actual_sample_rows'] != sample_rows
            or report['full_paper_reproduction_complete'] is not False
            or report['author_population_row_count_and_13_truths_match'] is not True
            or report['author_full_row_byte_identity_proven'] is not False
            or report['point_query_errors'] != 0 or report['ci_query_errors'] != 0):
        raise ValueError('complete native SF500 scope and successful formal model required')
    tables = report['training_tables']
    expected = {'lineorder':1000000, 'dwdate':2556, 'customer':1000000,
                'part':1000000, 'supplier':1000000}
    if (len(tables) != 5 or len({t['table'] for t in tables}) != 5
            or {t['table']:t['actual_training_rows'] for t in tables} != expected):
        raise ValueError('complete five-model original training budget required')


def main():
    from full_common import FULL, atomic_json, binding_hash, file_sha256, load_json
    from full_aqp_tables import artifact, csv_table
    from full_ssb_native_replay import verify, validate_query_identities, QUERY_NAMES
    from full_ssb_tables import summarize, draw, require_existing_figures, OUTPUT_NAMES
    accepted = verify()  # No fallback execution; missing evidence must fail.
    source = accepted['source_snapshot']['published_result']
    path = ROOT/source['path']
    if path.resolve() != (FULL/'results/ssb_native_v2_model_aqp_ci.json').resolve():
        raise ValueError('new native model result path required')
    payload = path.read_bytes()
    if len(payload) != source['bytes'] or hashlib.sha256(payload).hexdigest() != source['sha256']:
        raise ValueError('native model result changed since strict replay acceptance')
    report = json.loads(payload)
    actual_n = accepted['source_snapshot']['sample_rows']
    validate_formal_report(report, actual_n)
    validate_query_identities(report['queries'], (ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines(), QUERY_NAMES)
    helpers = [Path(__file__), ROOT/'code/full_ssb_native_replay.py',
        ROOT/'code/full_ssb_native_model.py', ROOT/'code/full_ssb_tables.py', ROOT/'code/full_aqp_tables.py']
    binding = dict(readonly_acceptance=accepted, sources=[source]+[artifact(p) for p in helpers],
                   full_paper_complete=False)
    directory = FULL/'figures'/('aqp_ssb_native_v2_'+binding_hash(binding)[:16])
    manifest_path = directory/'manifest.json'
    pointer = FULL/'results/ssb_native_v2_tables_latest.json'
    def publish_pointer():
        atomic_json(pointer, dict(path=directory.relative_to(ROOT).as_posix(),
            manifest_sha256=file_sha256(manifest_path), full_paper_complete=False))
    if manifest_path.exists():
        require_existing_figures(load_json(manifest_path), directory, binding)
        publish_pointer()
        print('REUSED_SEALED_NATIVE_SSB_TABLES', directory.relative_to(ROOT))
        return
    queries, groups = [], []
    for query in report['queries']:
        rows, summary = summarize(query, report['population_rows'], actual_n)
        queries.append(summary); groups.extend(rows)
    directory.mkdir(parents=True, exist_ok=False)
    csv_table(directory/'query_summary.csv', queries)
    csv_table(directory/'all_groups.csv', groups)
    csv_table(directory/'training_tables.csv', [{key:t[key] for key in
        ('table', 'actual_training_rows', 'full_join_estimate', 'learning_seconds')}
        for t in report['training_tables']])
    draw(directory, queries, groups, actual_n)
    outputs = [directory/name for name in sorted(OUTPUT_NAMES)]
    # Bind the existing scientific files; this entry only computes derived views.
    for entry in binding['sources']:
        if file_sha256(ROOT/entry['path']) != entry['sha256']:
            raise ValueError('native derived source changed during rendering')
    atomic_json(manifest_path, dict(status='PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES',
        binding=binding_hash(binding), binding_details=binding,
        artifacts=[artifact(p) for p in outputs], full_paper_complete=False,
        group_truth_rows=sum(q['truth_groups'] for q in queries),
        training_rows_per_table={t['table']:t['actual_training_rows'] for t in report['training_tables']},
        confidence_fact_sample_rows=actual_n, normalizer_scope=report['normalizer_scope'],
        ci_scope=report['ci_scope'], author_full_row_byte_identity_proven=False,
        missing_group_policy='Missing truth groups incur100pct error; invalid predictions suppress the '
            'query mean. Extras, zero truths, missing/nonfinite intervals and CI exclusions remain explicit.'))
    publish_pointer()
    print('NATIVE_SSB_TABLES_READY', directory.relative_to(ROOT))


if __name__ == '__main__':
    main()
