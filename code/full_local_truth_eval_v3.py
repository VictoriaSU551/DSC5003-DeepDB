"""Postprocess four-hash-seed verified v3 predictions against separate local truths.

No training or inference. Keeps the published truth metrics and earlier v2
postprocessing snapshots intact. Reuses the exact-integer alignment helper.
"""
import csv
from pathlib import Path

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json
from full_evaluation import numeric_summary, workload_files
from full_evaluation_v3 import PROTOCOL
from full_local_truth_eval import align_and_score, read_csv, source_record
from full_status import verified_current_evaluation


def main():
    truth_report_path = FULL / 'results/grouped_truth_discrepancies.json'
    verified = load_json(truth_report_path)
    if (verified is None or verified['status'] != 'PASS_LOCAL_COUNTS_WITH_PUBLISHED_INPUT_DIFFERENCES'
            or verified['queries'] != 683 or not verified['original_published_inputs_unchanged']):
        raise ValueError('independent SQL discrepancy audit is not complete')
    local_path = ROOT / verified['local_truth_path']
    if file_sha256(local_path) != verified['local_truth_sha256']: raise ValueError('local truth CSV changed')
    truth_by_group = {}
    for row in read_csv(local_path): truth_by_group.setdefault(row['group'], []).append(row)
    sources = {r['path']:r for r in map(source_record, [truth_report_path, local_path, Path(__file__), ROOT / 'code/full_local_truth_eval.py', ROOT / 'code/full_evaluation.py', ROOT / 'code/full_canonical_acceptance.py', FULL / 'results/canonical_inference_verification.json'])}
    models, details = {}, []
    for path in sorted((FULL / 'results').glob('*_evaluation_v3.json')):
        evaluation = load_json(path)
        if evaluation.get('queries') != 753 or evaluation.get('protocol') != PROTOCOL: continue
        label = evaluation['label']
        if verified_current_evaluation(label, 753)['status'] != 'PASS_LOCAL_VARIANT':
            raise ValueError('canonical v3 prediction source is not sealed: ' + label)
        sources[path.relative_to(ROOT).as_posix()] = source_record(path)
        source_label = evaluation.get('reused_from_label', label)
        summaries, pooled = {}, []
        for group, _, _ in workload_files()[1:]:
            csv_path = FULL / 'evaluation_v3' / source_label / (group + '.csv')
            scored = align_and_score(read_csv(csv_path), truth_by_group[group])
            summaries[group] = dict(queries=len(scored),
                local=numeric_summary([r['local_q_error'] for r in scored]),
                published=numeric_summary([r['published_q_error'] for r in scored]))
            sources[csv_path.relative_to(ROOT).as_posix()] = source_record(csv_path)
            for row in scored:
                item = dict(label=label, group=group, **row); details.append(item); pooled.append(item)
        models[label] = dict(groups=summaries, model_sha256=evaluation['model_sha256'],
            prediction_summary_sha256=file_sha256(path),
            public_3to6=dict(queries=len(pooled),local=numeric_summary([r['local_q_error'] for r in pooled]),
                published=numeric_summary([r['published_q_error'] for r in pooled])))
        larger = [r for r in pooled if int(r['group'][0]) >= 4]
        models[label]['public_4to6'] = dict(queries=len(larger),local=numeric_summary([r['local_q_error'] for r in larger]),
            published=numeric_summary([r['published_q_error'] for r in larger]))
    binding = dict(sources=sorted(sources.values(),key=lambda r:r['path']),
                   source_grouped_queries=683, independent_SQL_confirmed_differences=verified['independent_SQL_confirmed_differences'])
    directory = FULL / 'local_truth_metrics_v3' / binding_hash(binding)[:16]
    previous = load_json(directory / 'manifest.json')
    if previous is not None:
        if any(file_sha256(ROOT / item['path']) != item['sha256'] for item in previous['artifacts']):
            raise ValueError('previous local metrics artifact changed')
        print('REUSED_LOCAL_TRUTH_METRICS',directory.relative_to(ROOT)); return
    directory.mkdir(parents=True,exist_ok=True)
    atomic_json(directory / 'metrics.json',models)
    with (directory / 'all_predictions_scored.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,list(details[0]));writer.writeheader();writer.writerows(details)
    atomic_json(directory / 'manifest.json',dict(status='PASS_LOCAL_TRUTH_POSTPROCESSING',
        binding=binding_hash(binding),binding_details=binding,
        artifacts=[source_record(p) for p in sorted(directory.iterdir()) if p.is_file()],
        full_paper_complete=False,models=len(models),predictions=len(details),
        note='Exactly the preserved predictions, no retraining or inference. Both local and original published metrics remain inspectable.'))
    atomic_json(FULL / 'results/local_truth_metrics_v3_latest.json',dict(path=directory.relative_to(ROOT).as_posix(),
        manifest_sha256=file_sha256(directory / 'manifest.json'),full_paper_complete=False))
    print('LOCAL_TRUTH_METRICS_READY',len(models),len(details),directory.relative_to(ROOT))


if __name__ == '__main__': main()
