# DeepDB 最终交付说明

更新：2026-11-04。**这是有明确论文缺口的最终课程交付，全论文复现未完成。** 可公开材料下已完成的实验、组员贡献、原始失败和本地变体均分开记录，交付封版不关闭论文缺口。

## 结果与证据

- [31项主结果与图表](FULL_PAPER_RESULTS.md)来自2026-11-03的封存快照；[最终账本](final_delivery.json)另加入本次LOCAL Verdict SF500实际运行和最终模型保留边界。旧快照的PENDING不被静默改写。
- canonical38配置经过四hash seed，62,548次预测；753条查询各做三次C++，7,422次实际native调用，Python/native/CSV逐条一致。JOB-light代理中位q-error1.344960，但p95为4.313755、最大256.651971，尾部未恢复作者结果。
- 官方MSCN和一致样本重建MSCN各训练100轮，分别评估70/753条。公开683条分组查询中4–6表413条，不能标作作者200条；74项公开标签差异按独立PG真值另行评分。
- Flights实际遍历1B行，保留9,997,912行，12SQL/331组；新鲜逆序24调用一致；参考CI322组可用、9组排除。
- LOCAL SSB五个1M/table模型continuation及五个新10M/table cap模型均有完整验收和独立逆序。每种13次载入/26次调用，2,059点/4,118端点最大差0。10M cap事实表实际9,996,946行；参考CI1,253可用、806因样本少于10行排除。一次样本不是重复抽样CI校准。
- [Scalar、SRS/IBJS、DBEst、Verdict补充账本](fullpaper_additional_baselines.json)保留零预测、无穷大q-error、缺组、不支持项和条件均值分母；本地变体没有混作论文等预算排名。
- [guoao/breck1016贡献](guoao_experiments/report_zh.md)：14组JOB-light设置、980预测、70条不同SQL；13轮训练证据。两个标准库离线核验均通过，原文件、署名和提交保留；本次整合没有重训其模型。组员13个权重本体未提供，证据清单不等于本体。

## 新完成的LOCAL Verdict SF500

正式运行使用独立v13命名空间，五张表导入、一次注册、**38次原始物理调用**均完成，独立完整只读验收后导出六个公开文件。样本缩放门禁通过，项目PostgreSQL由所属控制器关闭。封存来源及SHA见[来源清单](fullpaper_verdict_ssb_local500_source_manifest.json)。

- 本地母体3,000,028,242行，事实样本9,996,946行；全量维表配合同一个已有事实样本。未导入完整3B事实表、没有重新抽样。
- [32行查询摘要](fullpaper_verdict_ssb_local500_query_summary.csv)由26行RAW和6行外部双SUM点适配构成；适配复用子调用，没有新增物理调用。原Q4复合SUM行为仍保存在RAW中。
- [RAW全部分组](fullpaper_verdict_ssb_local500_raw_groups.csv)与[适配分组](fullpaper_verdict_ssb_local500_adapter_groups.csv)保留缺组、额外组、原错误和非有限值。缺组在有定义的全真值均值中计100%相对误差；错误/非有限值/零真值导致均值不报告；有限匹配条件均值另列分母。
- [38次物理调用](fullpaper_verdict_ssb_local500_physical_calls.csv)与[英文范围说明](fullpaper_verdict_ssb_local500_RESULTS.md)记录原始SQL、可用的native返回与不可用项。记录原引擎错误0次、原生CI不可用行807项，不能只挑有限成功项报完整覆盖。
- Verdict按实际n/N注册并按N/n缩放；原DeepDB保留n/p归一化，两者分开。原生95%CI和DeepDB中央90%分开；外部差值没有协方差与联合CI。
- 正式整条命令耗时2471.924秒，独立完整验收和导出475.703秒，均包含来源遍历，不是纯训练/推断延迟。实际预算峰值4,120,975,810字节，固定资源上限未放宽。

v9外部排序触及1GiB暂存上限、v10完整往返顺序核对失败均未当作成功。独立1M行PG11.5四组诊断确认：预先提交建表时，不论单次或多次COPY都会发生物理回填重排；建表与COPY同一事务的两组保持完整原序字节一致。v11已实现新表同事务创建、一次有界流式COPY及严格物理顺序/完整字节门禁，并完成四张全量维表核对；事实表导入时，资源计数遇到正常轮换删除的WAL文件而失败。v12为自有资源目录计数增加最多三次完整重扫，另一次正式尝试在日期表和全量customer表核对后因Python进程命令行不可检查而停止；原失败快照未保存，后续扫描可读，故生命周期竞态只作为推测。v13仅对这种不可检查状态做有界完整进程快照重扫，已持久化的扫描回执含每轮证据；持续不可检查、已知冲突、格式错误和穷尽仍失败。所有失败均未计为成功，算法、严格导入门禁、SQL及资源上限未放宽。实现通过和SF2小试验没有替代本次SF500执行。

## 仍未复现的论文内容

1. [四项作者输入缺口](https://github.com/VictoriaSU551/DSC5003-DeepDB/blob/final-delivery-2026-11-04/docs/FINAL_PUBLIC_INPUT_GAPS.md)：200条泛化成员、Figure5合成配方、Wavelet执行/域/协议、Figure12原DBEst驱动与多维协议。没有用历史结果或替代微基准填为完成。
2. SSB作者行数匹配，但2,059项中1,713项customer连接真值不同；LOCAL结果仅对本地独立精确真值评分，作者母体门禁仍失败。
3. 原规模3B完整数据库、原表建样本、TABLESAMPLE/XDB及完整端到端比较没有执行；[容量说明](https://github.com/VictoriaSU551/DSC5003-DeepDB/blob/final-delivery-2026-11-04/docs/FULL_BASELINE_FEASIBILITY.md)给出载荷和数据库下界。
4. JOB-light尾部差异及其他比较方法配置、全覆盖和一致预算/计时仍未齐备。没有论文完成比例或全方法延迟排名。

## 源码、模型与本地精简

[公共仓库](https://github.com/VictoriaSU551/DSC5003-DeepDB)的main交付代码、SQL、测试、协议和共享结果；[PR3](https://github.com/VictoriaSU551/DSC5003-DeepDB/pull/3)保留整合记录。最终合并与不可变tag的实际SHA以本地PUBLICATION.json及GitHub为准，本文不提前声称合并或清理完成。

按用户要求，模型作为最终结果保留：**221个逻辑条目、220个去重权重文件，共2,128,498,224字节**，已逐文件核SHA。权重、数据、环境和数据库不上传GitHub。另保留49份小型支持/结果工件（2,478,232字节），含两个RDC矩阵、匹配的MSCN测试CSV/位图、重建模型的六份1000行样本和新衍生编码/标签极值元数据。新元数据明确区别于历史accepted工件；官方MSCN原始tuple样本未知，仅承诺已测70条匹配输入的复用边界。

本地精简目标是根README与results/（含最终模型）。最终保留/复制及清理状态必须以实际清单为准，不能仅根据本文判定已删除文件。移除原数据/HDF/环境/源快照后，原fullF与其CI/continuation/Verdict递归来源验收退役；保留文件SHA验收只证明结果包完整性。新实验可从GitHub恢复固定源码并重建环境和数据；恢复旧fullF必须恢复对应全部封印字节和运行目录，重新下载或生成不保证旧哈希身份。精简结果包没有宣称原驱动可直接运行。
