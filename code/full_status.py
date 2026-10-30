"""Derive an honest full-paper coverage ledger from verified stage receipts."""
import json
from pathlib import Path

from full_common import ROOT, FULL, atomic_json, file_sha256, load_json


def main():
    stages = {}
    inventory = load_json(FULL / 'results/source_inventory.json', {})
    stages['paper_and_public_input_audit'] = dict(status=inventory.get('status', 'PENDING'),
        evidence='docs/FULL_REPRODUCTION_PROTOCOL.md; output/full/results/source_inventory.json')
    pg = load_json(FULL / 'results/postgres_job_light_verification.json', {})
    stages['independent_70_truths_and_postgres_11_5'] = dict(
        status='PASS' if pg.get('all_official_truths_independently_matched') and pg.get('queries') == 70 else 'PENDING',
        evidence='output/full/results/postgres_job_light_verification.json')
    for label in ['rdc_n100000_b0p0', 'public_scale_rdc_n100000_b0p0',
                  'public_scale_rdc_n10000000_b0p5', 'public_scale_rdc_n10000000_b5p0']:
        path = FULL / 'results' / (label + '_evaluation.json')
        result = load_json(path, {})
        stages[label] = dict(status=result.get('status', 'PENDING'), queries=result.get('queries', 0),
                              evidence=path.relative_to(ROOT).as_posix())
    cpp = load_json(FULL / 'results/cpp_verification.json', {})
    stages['cpp_existing_model_correctness'] = dict(status=cpp.get('status', 'PENDING'),
        scope='Existing 1M model correctness and repeated JOB-light timing; not full Figure 8',
        evidence='output/full/results/cpp_verification.json')
    aqp = load_json(FULL / 'results/aqp_sources.json', {})
    stages['flights_source_5m'] = dict(status=aqp.get('status', 'PENDING'),
                                    scope='Source inputs only; not generated 1B')
    golden = load_json(FULL / 'flights/golden-200k/golden_validation.json', {})
    stages['flights_streaming_golden_200k'] = dict(status=golden.get('status', 'PENDING'),
                                               scope='Adapter correctness at 200K, not full-size experiment')
    for key, reason in [
        ('paper_exact_200_query_binding', 'Public files contain 683 grouped queries; original 200 membership not identified'),
        ('figure5_original_synthetic_database', 'Original generator, parameters and seeds not found in audited public sources'),
        ('all_original_comparison_implementations', 'Wavelets/IBJS/random/DBEst/XDB/VerdictDB original drivers not in released source'),
        ('figure7_budget_semantics', 'Paper relative time budget and public column-cost numeric factor differ')]:
        stages[key] = dict(status='OPEN_SOURCE_GAP', reason=reason)
    for key in ['mscn_100_epochs', 'sample_size_sweep', 'budget_sweep', 'temporal_updates',
                'cpp_generalization_figure8', 'flights_1b_generated', 'ssb_sf500_generated',
                'flights_aqp_and_baselines', 'ssb_aqp_and_baselines', 'confidence_intervals',
                'dbest_wavelet_microbenchmarks']:
        stages[key] = dict(status='PENDING')
    output = dict(status='INCOMPLETE_FULL_PAPER', full_paper_complete=False,
                  original_verified_baseline_preserved=True,
                  note='PASS applies only to each named receipt. Missing inputs, original-scale baselines and pending experiments remain open.',
                  stages=stages)
    atomic_json(FULL / 'completion_status.json', output)
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
