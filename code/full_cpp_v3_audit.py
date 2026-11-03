"""Read-only canonical native audit. Missing evidence fails; never starts inference."""
import json
from pathlib import Path
import full_cpp_v3 as runner


def require_snapshot_map(assets, directory, excluded):
    expected={path.relative_to(directory).as_posix() for path in Path(directory).rglob('*')
              if path.is_file() and path!=excluded}
    actual=[item['path'] for item in assets]
    if not actual or len(set(actual))!=len(actual) or set(actual)!=expected:
        raise ValueError('Final namespace artifact map is empty, duplicate or incomplete')


def audit_row(row, current_reference):
    runner.check_triplet(row['python_prediction'],row['cpp_prediction'],current_reference,row['generated_spn_calls'])
    runner.check_triplet(row['python_prediction'],row['cpp_prediction'],row['v3_csv_prediction'],row['generated_spn_calls'])
    if (set(row['native_call_map'])-{'spn%d'%i for i in range(6)}
            or row['upstream_omitted_calls']!=runner.validate_call_counters('cpp',row['native_call_map'],row['upstream_stats_calls'])):
        raise ValueError('Stored physical native identity/counter differs')


def audit():
    # Read this before importing any scientific runtime or considering a worker.
    final_path=runner.OUT/'final_current_seal.json'
    final=runner.read_json(final_path)
    runner.require_seal(final)
    if final.get('status')!='SEALED_CURRENT_CANONICAL_NATIVE_WITH_READ_ONLY_AUDIT':
        raise ValueError('Final current canonical native seal is missing/incorrect')
    require_snapshot_map(final['artifacts'],runner.OUT,final_path)
    runner.validate_assets(final['artifacts'],runner.OUT)
    runner.validate_assets(final['sources'],runner.ROOT)
    scientific=runner.read_json(runner.OUT/'final_seal.json')
    runner.require_seal(scientific)
    runner.validate_assets(scientific['artifacts'],runner.OUT)
    pointer=runner.read_json(runner.OUT/'latest.json')
    runner.require_seal(pointer)
    path=runner.ROOT/pointer['path']
    if runner.sha(path)!=pointer['sha256'] or runner.record(path)!=scientific['verification']:
        raise ValueError('Current scientific verification pointer differs')
    result=runner.read_json(path)
    runner.require_seal(result)
    runner.validate_assets(result['output_artifacts'],path.parent)
    # This actually reruns verify_current(label,753), current source/runtime,
    # all legacy hashes and canonical references, without invoking verify().
    config,workload,references,_=runner.inputs(3,True)
    if result['configuration']!=config or runner.digest(config)!=scientific['configuration_binding']:
        raise ValueError('Current scientific input binding differs')
    records=[json.loads(line) for line in (path.parent/'all_753_repeated.jsonl').read_text().splitlines()]
    runner.require_round_grid(records,workload,3)
    for row in records:audit_row(row,references[(row['group'],row['query_no'])])
    cells=runner.figure8_groups(records,3)
    if cells!=result['figure8_public_groups'] or sum(cell['unique_queries'] for cell in cells)!=413:
        raise ValueError('Stored Figure8 cells differ')
    totals=dict(successful_native_calls=sum(row['generated_spn_calls'] for row in records),
                upstream_stats_calls=sum(row['upstream_stats_calls'] for row in records),
                upstream_omitted_successful_native_calls=sum(row['upstream_omitted_calls'] for row in records),
                successful_native_wall_ns=sum(row['cpp_physical_native_ns'] for row in records))
    if any(result[key]!=value or scientific[key]!=value for key,value in totals.items()):
        raise ValueError('Stored aggregate native counts/wall differ')
    if (result['resource']['stopped_for_memory'] or result['resource']['compile_processes']
            or result['resource']['returncode'] or result['resource']['peak_tree_rss_bytes']>runner.LIMIT):
        raise ValueError('Owned process resource gate differs')
    return dict(status='PASS_READ_ONLY_CURRENT_CANONICAL_NATIVE_AUDIT',queries=753,paired_predictions=len(records),
        figure8_cells=len(cells),figure8_queries=413,actual_new_predictions=0,
        final_seal_sha256=runner.sha(final_path),verification_sha256=runner.sha(path),
        physical_native_timer='cpp_physical_native_ms',legacy_tree_unchanged=True,**totals)


if __name__=='__main__':
    print(json.dumps(audit(),sort_keys=True))
