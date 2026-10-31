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
    'flights_verdict': ('verdict_tables_latest.json', [
        'query_summary.csv', 'all_groups.csv', 'flights_verdict_comparison.png']),
    'ssb': ('ssb_tables_latest.json', ['query_summary.csv', 'all_groups.csv', 'training_tables.csv',
                                    'ssb_relative_error.png', 'ssb_ci_half_width.png']),
    'ssb_local_sf500': ('ssb_local_sf500_tables_latest.json', ['query_summary.csv', 'all_groups.csv',
        'training_tables.csv', 'ssb_relative_error.png', 'ssb_ci_half_width.png']),
    'ssb_local_canonical': ('ssb_local_canonical_tables_latest.json', ['query_summary.csv','all_groups.csv',
        'training_tables.csv','ssb_relative_error.png','ssb_ci_half_width.png']),
    'ssb_local_ci10m': ('ssb_local_ci10m_tables_latest.json', ['query_summary.csv','all_groups.csv',
        'training_tables.csv','ssb_relative_error.png','ssb_ci_half_width.png']),
    'ssb_native_v2': ('ssb_native_v2_tables_latest.json', ['query_summary.csv', 'all_groups.csv',
        'training_tables.csv', 'ssb_relative_error.png', 'ssb_ci_half_width.png']),
}
OPTIONAL_BUNDLES = {'ssb','ssb_native_v2','ssb_local_sf500','ssb_local_canonical','ssb_local_ci10m','flights_verdict'}


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
    local_scopes={'ssb_local_sf500_tables_latest.json':'LOCAL_SSB_SF500',
                  'ssb_local_canonical_tables_latest.json':'LOCAL_SSB_SF500_CANONICAL_CI',
                  'ssb_local_ci10m_tables_latest.json':'LOCAL_SSB_10M_CI'}
    if pointer_path.name in local_scopes:
        if (manifest.get('status') != 'PASS_VERIFIED_LOCAL_SSB_DERIVED_TABLES'
                or pointer.get('full_paper_complete') is not False):
            raise ValueError('successful LOCAL manifest and explicitly incomplete pointer required')
        for evidence in (pointer,manifest):
            if (evidence.get('scope') != local_scopes[pointer_path.name]
                    or evidence.get('author_reproduction_complete') is not False
                    or type(evidence.get('author_different_groups')) is not int
                    or evidence['author_different_groups'] != 1713):
                raise ValueError('LOCAL SSB bundle must retain author mismatch and incomplete scope')
        if pointer_path.name in ('ssb_local_canonical_tables_latest.json','ssb_local_ci10m_tables_latest.json'):
            details=manifest.get('binding_details',{});accepted=details.get('readonly_acceptance',{})
            variant='CANONICAL_DECODED_GROUP_PROTOTYPE_V1'
            if (accepted.get('evaluation_variant')!=variant
                    or accepted.get('group_order_adapter_sha256')!='48220a0474a838c8dc9a7cf3fef0e8a84459a05e3fa8e15405307acae430ae5c'
                    or details.get('presentation',{}).get('evaluation_variant')!=variant):
                raise ValueError('canonical group variant must agree in scientific acceptance and derived presentation')
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


def coverage_rows(stages, prefix=''):
    rows = {}
    for name, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        label = prefix + str(name)
        if 'status' in stage:
            rows[label] = {key:value for key,value in stage.items()
                if key in {'status', 'scope', 'queries', 'generated_rows','requested_rows','author_different_groups',
                    'author_reproduction_complete','full_paper_reproduction_complete','evaluation_variant',
                    'model_training_cap_per_table','historical_reverse_accepted'}}
        else:
            rows.update(coverage_rows(stage, label+'/'))
    return rows


def main():
    selected, evidence = [], {}
    for prefix, (pointer, names) in BUNDLES.items():
        if prefix in OPTIONAL_BUNDLES and not (FULL/'results'/pointer).exists():
            continue  # Optional experiment has no accepted derived bundle yet.
        paths, sources = checked_bundle(FULL / 'results' / pointer, names)
        evidence[prefix] = sources
        selected.extend((prefix + '_' + path.name, path) for path in paths)
    status_path = FULL / 'completion_status.json'
    status = load_json(status_path)
    if status.get('full_paper_complete') is not False or status.get('status') != 'INCOMPLETE_FULL_PAPER':
        raise ValueError('current explicit coverage ledger required')
    # Publish only selected state fields; the local ledger can contain diagnostic machine paths.
    coverage = coverage_rows(status['stages'])
    if any(stage['status'] == 'EVIDENCE_INVALID' for stage in coverage.values()):
        raise ValueError('invalid current evidence must be resolved before publishing a new snapshot')
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
             'CI仅一次样本，少于10行的组排除，不能解读为重复抽样覆盖率校准。', '']
    if 'flights_verdict' in evidence:
        lines += ['Verdict仅执行已物化的同一样本：原F5.2错误和两个原SUM的外部差分适配分别列出；',
                  '原生95%区间与DeepDB中央90%不同，不做覆盖率或耗时排名。', '']
    if 'ssb_local_sf500' in evidence:
        lines += ['SSB本地SF500母体为3,000,028,242行，9,996,946行实际样本；作者2059项真值中1713项不同。',
                  '本地模型/CI以同一生成母体的整数精确真值评分，严格作者复现仍未通过；不替代论文结果。',
                  '该SSB模型训练上限1M/table；置信区间参数使用实际约10M参考样本，Figure11的10M训练政策另列独立实验。', '']
    if 'ssb_local_canonical' in evidence:
        lines += ['SSB canonical1M使用原五个已保存模型，仅规范配对分组顺序；新鲜双hash正逆序另行验收。',
                  '历史逆序区间失败记录保留。作者2059项真值中1713项不同，本地母体结果不能替代作者结果。',
                  '该变体训练上限1M/table，独立参考使用实际9,996,946行样本；仍未完成Figure11的10M训练政策。','']
    if 'ssb_local_ci10m' in evidence:
        lines += ['SSB另训练五个10M/table上限模型，事实表实际9,996,946行；复用同一已封存预处理与独立样本统计。',
                  '使用canonical配对分组顺序并经过独立逆序核验。这是Figure11训练上限政策的本地实验，',
                  '作者1713项真值差异仍保留，不声称恰好10M事实行或作者母体完全复现。','']
    if 'ssb_native_v2' in evidence:
        lines += ['SSB修正母体须匹配作者行数及13条SQL的2059项真值；这不证明作者全部原始行字节相同。',
                  '原失败母体另保留MISMATCH，五个单表模型受1M/table预算限制，CI仍只有一次样本。', '']
    lines += ['只发布派生表图。原始数据、模型、运行环境、PDF和大输出保存在本地，不随仓库分发。', '',
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
