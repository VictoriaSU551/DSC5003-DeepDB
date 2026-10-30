"""Export a small, explicitly incomplete collaboration snapshot; no data or models."""
import shutil
import os
from pathlib import Path

from full_common import ROOT, FULL, atomic_json, binding_hash, file_sha256, load_json


BUNDLES = {
    'cardinality': ('cardinality_tables_latest.json', [
        'table1.csv', 'studies.csv', 'groups.csv', 'temporal_population_fractions.csv',
        'inference_variant_changes.csv', 'table1_comparison.png', 'sample_size_study.png',
        'budget_study.png', 'generalization.png', 'cpp_latency.png', 'temporal_updates.png']),
    'flights': ('flights_tables_latest.json', [
        'query_summary.csv', 'all_groups.csv', 'flights_relative_error.png', 'flights_ci_half_width.png']),
    'flights_comparison': ('flights_comparisons_latest.json', [
        'query_comparison.csv', 'flights_partial_baselines.png']),
}


def record(path):
    path = Path(path).resolve()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                sha256=file_sha256(path))


def checked_bundle(pointer_path, filenames):
    if not filenames or len(filenames) != len(set(filenames)):
        raise ValueError('nonempty unique export whitelist required')
    if any(Path(name).name != name or Path(name).suffix not in {'.csv', '.png'} for name in filenames):
        raise ValueError('only explicit derived CSV or PNG filenames may be exported')
    pointer_path = Path(pointer_path)
    pointer = load_json(pointer_path)
    directory = (ROOT / pointer['path']).resolve()
    figures = (ROOT / 'output/full/figures').resolve()
    if figures not in directory.parents:
        raise ValueError('figure directory escapes the project output tree')
    manifest_path = directory / 'manifest.json'
    if file_sha256(manifest_path) != pointer['manifest_sha256']:
        raise ValueError('latest figure manifest differs')
    manifest = load_json(manifest_path)
    if manifest.get('full_paper_complete') is not False:
        raise ValueError('snapshot must retain the explicit incomplete scope')
    artifacts = manifest.get('artifacts', [])
    if not artifacts or len({a['path'] for a in artifacts}) != len(artifacts):
        raise ValueError('nonempty unique figure artifacts required')
    actual, physical = {}, set()
    for item in artifacts:
        path = (ROOT / item['path']).resolve()
        identity = os.path.normcase(str(path))
        if identity in physical:
            raise ValueError('duplicate physical artifact in sealed manifest')
        physical.add(identity)
        if path.parent != directory:
            raise ValueError('figure artifact escapes its sealed directory')
        if path.stat().st_size != item['bytes'] or file_sha256(path) != item['sha256']:
            raise ValueError('figure artifact differs: ' + item['path'])
        actual[path.name] = path
    if not set(filenames) <= set(actual):
        raise ValueError('whitelisted output is not in the sealed manifest')
    return [actual[name] for name in filenames], dict(pointer=record(pointer_path), manifest=record(manifest_path))


def main():
    selected, evidence = [], {}
    for prefix, (pointer, names) in BUNDLES.items():
        paths, sources = checked_bundle(FULL / 'results' / pointer, names)
        evidence[prefix] = sources
        selected.extend((prefix + '_' + path.name, path) for path in paths)
    status_path = FULL / 'completion_status.json'
    status = load_json(status_path)
    if status.get('full_paper_complete') is not False or status.get('status') != 'INCOMPLETE_FULL_PAPER':
        raise ValueError('current explicit coverage ledger required')
    # Publish only selected state fields; the local ledger can contain diagnostic machine paths.
    coverage = {name: {key: value for key, value in stage.items()
                      if key in {'status', 'scope', 'queries', 'generated_rows', 'requested_rows'}}
                for name, stage in status['stages'].items() if isinstance(stage, dict)}
    destination = ROOT / 'output/results'
    destination.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, source in selected:
        target = destination / ('fullpaper_' + name)
        if not target.exists() or file_sha256(target) != file_sha256(source):
            shutil.copyfile(str(source), str(target))
        outputs.append(dict(record(target), source=record(source)))
    index = destination / 'FULL_PAPER_RESULTS.md'
    lines = ['# 完整复现阶段：可公开的派生结果', '',
             '**整篇论文仍未完成。** 本页是已验证部分的协作快照。', '',
             '来源状态时间：' + status['updated_at_utc'], '',
             '作者Table1数值与本地重跑各有evidence标签；配置、样本和尾部误差有差异，不能互相替代。',
             '公开工作负载为683条，其中4--6表413条；作者200条具体成员未找到。',
             'Flights为本地生成的1B母体；DBEst仅4类SQL/20K拟合，八类不支持，未做等预算或延迟排名。',
             'CI仅一次样本，少于10行的组排除，不能解读为重复抽样覆盖率校准。', '',
             '只发布派生表图。原始数据、模型、运行环境、PDF和大输出保存在本地，不随仓库分发。', '',
             '## 表格和图', '']
    lines += ['- [' + item['path'].split('/')[-1] + '](' + item['path'].split('/')[-1] + ')' for item in outputs]
    lines += ['', '## 当前阶段状态', '', '| 阶段 | 状态 |', '| --- | --- |']
    lines += ['| ' + name + ' | ' + stage['status'] + ' |' for name, stage in coverage.items() if 'status' in stage]
    lines += ['', '完整协议、恢复门禁与组员分工见[运行指南](../../docs/FULL_RUNNING_GUIDE.md)。',
              '本快照的输入与工件SHA见[摘要](fullpaper_summary.json)。', '']
    content = '\n'.join(lines)
    if not index.exists() or index.read_text(encoding='utf-8') != content:
        with index.open('w', encoding='utf-8', newline='') as stream:
            stream.write(content)
    outputs.append(record(index))
    binding = dict(exporter=record(Path(__file__)), sources=evidence, coverage_source=record(status_path),
                   coverage=coverage, outputs=outputs)
    atomic_json(destination / 'fullpaper_summary.json', dict(
        status='VERIFIED_PARTIAL_COLLABORATION_SNAPSHOT', full_paper_complete=False,
        source_updated_at_utc=status['updated_at_utc'], binding_sha256=binding_hash(binding), **binding,
        scope='Derived tables/plots only. Author-reported values and local results remain labelled. '
              'No raw rows, model files, environments, PDF or credentials are included.'))
    print('PUBLIC_SUMMARY_READY', len(outputs), 'derived artifacts; full_paper_complete=False')


if __name__ == '__main__':
    main()
