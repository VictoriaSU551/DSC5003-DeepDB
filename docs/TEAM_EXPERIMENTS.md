# JOB-light 组员实验汇总与同步核验

2026-11-03 整理。来源为 guoao 的贡献分支，Git 提交作者署名 `breck1016`：

- [`58313be`](https://github.com/VictoriaSU551/DSC5003-DeepDB/commit/58313be)：实验表格、图及中英文分析。
- [`0ad9c15`](https://github.com/VictoriaSU551/DSC5003-DeepDB/commit/0ad9c15b7ab1498ee41d69e20329d81437ef1477)：逐轮配置、日志和交付证据。

两提交基于仓库原基础版本 `ac2485496157092bcdbe85f61e18db216168566e`。这次保留原提交和整个交付包，增加主线入口、详细索引及独立同步记录，不修改组员预测、图表、源码快照或原始证据清单。扩展复现分支的其他实验单独保留。

## 1. 已交付的实验范围

| 内容 | 完成情况 | 证据入口 |
|---|---|---|
| 关系基础模型 | 3个请求样本预算 × 3个全局种子，9轮训练；每轮5个RSPN | [指标](../output/results/guoao_experiments/metrics.csv)、[逐轮记录](../output/results/guoao_experiments/evidence/run_records.json) |
| RDC模型 | 100K种子1、1M种子1/2/3，4轮训练；每轮7个RSPN；RDC选择推断 | 同上及[设置](../output/results/guoao_experiments/settings.json) |
| PostgreSQL估计 | PostgreSQL16.15，70条查询 | [预测](../output/results/guoao_experiments/predictions.csv)、[协议](../output/results/guoao_experiments/evidence/protocol_audit.json) |
| 数据库真值 | 69条原始SQL及ID59精确等价分组计数，70/70匹配官方值 | [真值表](../output/results/guoao_experiments/truth_audit.csv)、[核验证据](../output/results/guoao_experiments/evidence/verification_records.json) |
| 展示与分析 | 8类图，每类中英2版；共16张图，2份图文报告 | [中文报告](../output/results/guoao_experiments/report_zh.md)、[English report](../output/results/guoao_experiments/report_en.md) |
| 模型及运行取证 | 13个模型的清单和指纹、37段选定日志、9个源码快照成员 | [交付说明](../output/results/guoao_experiments/DELIVERY_MAP.md)、[来源清单](../output/results/guoao_experiments/evidence/source_manifest.json) |

上述始终是同一套70条不同查询：13组模型评估加1组数据库估计，合计14组设置、980个保存预测。不是980条不同查询，也不是16组图表实验。13个模型本体合计119,308,280字节，未上传GitHub。

## 2. 数据、参数与可比性

数据是作者README链接的CWI IMDb/JOB快照中的六张完整表。压缩包SHA256为 `25f9d893c54f903366e0c263f88db0d429dbc2b159d4987ebc1e203242a7e988`；表文件信息见[数据清单](../output/results/guoao_experiments/evidence/data_manifest.json)。作者算法版本为 `655ada13a043a4226a239b0c0a65bcdefef87a02`，组员记录环境为Windows x64、Python3.8.20。

- 关系模型请求每个RSPN使用10K、100K或1M样本，学习RDC阈值0.3；`post_sampling_factor` 为 `10 10 5 1 1`。
- RDC预算系数5、最多3个连接，预采样与搜索样本各10K，候选集合10K，学习/选择阈值0.3/0.15，`max_variants=1`。公开的是 `rdc_spn_selection` 推断结果。
- 全局训练种子1/2/3；评估种子1、`PYTHONHASHSEED=1`。RDC三轮固定同一份种子1预采样，保留作者内部固定种子，不能称全部随机源相互独立。
- 5个与7个RSPN的总训练预算不同，同号种子不保证同一批训练行。关系流程的连接规模来自元数据估算，RDC作者入口使用数据库精确内连接计数。由此观察到的是两条完整配置流程的差异，不能视作只改变RDC的严格消融。
- PostgreSQL统计目标100，建主键及连接键索引后ANALYZE，无扩展统计，关闭并行估计/JIT。估计读取COUNT顶层Aggregate下方输入节点的Plan Rows，不是Aggregate固定的1行。
- 组员PostgreSQL16.15与扩展复现分支的其他数据库配置分别报告；不能把不同版本、采样、工作负载和时钟口径拼为统一性能排名。

## 3. 全部14组指标

q-error为 `max(prediction/truth, truth/prediction)`，分位数线性插值。此交付包中所有真值与预测为正数，无零值裁剪问题；精确保存值以CSV为准。

| 设置 | 每RSPN请求样本 | 种子 | RSPN数 | 中位q-error | P95 | 最大值 |
|---|---:|---:|---:|---:|---:|---:|
| relationship_10000_s1 | 10000 | 1 | 5 | 1.970142 | 49.733917 | 2600.613714 |
| relationship_100000_s1 | 100000 | 1 | 5 | 1.542241 | 16.778418 | 190.794165 |
| relationship_1000000_s1 | 1000000 | 1 | 5 | 1.499699 | 6.901042 | 63.164469 |
| relationship_10000_s2 | 10000 | 2 | 5 | 1.878850 | 32.626848 | 344.835271 |
| relationship_100000_s2 | 100000 | 2 | 5 | 1.576105 | 7.830888 | 33.197425 |
| relationship_1000000_s2 | 1000000 | 2 | 5 | 1.687380 | 6.346785 | 33.000000 |
| relationship_10000_s3 | 10000 | 3 | 5 | 1.890432 | 151.667741 | 3024.500721 |
| relationship_100000_s3 | 100000 | 3 | 5 | 1.551395 | 7.475244 | 33.000000 |
| relationship_1000000_s3 | 1000000 | 3 | 5 | 1.626079 | 6.118604 | 33.000000 |
| rdc_100000_s1 | 100000 | 1 | 7 | 1.422098 | 42.698773 | 2386.642837 |
| rdc_1000000_s1 | 1000000 | 1 | 7 | 1.384653 | 6.962957 | 191.965978 |
| rdc_1000000_s2 | 1000000 | 2 | 7 | 1.432222 | 3.823158 | 223.753806 |
| rdc_1000000_s3 | 1000000 | 3 | 7 | 1.444588 | 8.699903 | 664.005561 |
| postgresql | — | — | — | 8.687412 | 842.784563 | 3606.405405 |

百万预算下，RDC相对关系基础模型的逐查询胜/负数为42/28、44/26、42/28，无平局。三轮中位误差都降低，P95只有种子2改善，最大误差三轮都更高。种子1的基础模型相对PostgreSQL有66条查询误差较低。训练时长来自历史运行，不用于受控速度比较；估计准确度改善不证明SQL执行提速。

ID14、16、34的逐查询案例见[原报告](../output/results/guoao_experiments/report_zh.md)。ID16真值为33，RDC种子1/百万预算仍约192倍误差，保留该尾部失败。案例是查看结果后的探索性分析，不是独立泛化测试。

## 4. 图表阅读顺序

| 图表主题 | 对应问题 | 中文图 |
|---|---|---|
| 01 样本预算 | 种子1增加请求样本量如何改变误差？ | [查看](../output/results/guoao_experiments/figures/zh/01_sample_size.png) |
| 02 基础模型种子 | 样本预算结论是否在3个种子下稳定？ | [查看](../output/results/guoao_experiments/figures/zh/02_seed_sensitivity.png) |
| 03 PostgreSQL汇总 | 不同流程的误差分布如何？ | [查看](../output/results/guoao_experiments/figures/zh/03_postgresql_summary.png) |
| 04 PostgreSQL逐查询 | 哪些查询改善、哪些退化？ | [查看](../output/results/guoao_experiments/figures/zh/04_postgresql_per_query.png) |
| 05 真值核验 | 最终成功计数尝试记录；不含重试、不是性能排名 | [查看](../output/results/guoao_experiments/figures/zh/05_truth_audit.png) |
| 06 RDC样本预算 | 固定种子1时100K与1M的差异 | [查看](../output/results/guoao_experiments/figures/zh/06_rdc_sample_size.png) |
| 07 具体失败/改善案例 | ID14、16、34的探索性分析 | [查看](../output/results/guoao_experiments/figures/zh/07_rdc_cases.png) |
| 08 RDC三种子 | 中位数改善与尾部风险是否重复出现？ | [查看](../output/results/guoao_experiments/figures/zh/08_rdc_seed_stability.png) |

对应英文图使用同目录的 `figures/en/`，完整解释见[英文报告](../output/results/guoao_experiments/report_en.md)。

## 5. 本次同步实际核验了什么

在仓库根目录执行：

```powershell
python -B output/results/guoao_experiments/verify_results.py --repo-root .
python -B output/results/guoao_experiments/verify_evidence.py
```

两条检查均通过。第一条从CSV重算14组指标、核对70个查询哈希和官方真值，并重算三种子胜负数；第二条检查35个公开文件、37段选定日志、源码ZIP CRC/成员指纹及13个模型清单与指标的对应。另核对了全部36个交付文件与原贡献提交逐字节一致，检查了源码包路径及常见高置信凭据模式。后者是限定模式检查，不表示覆盖所有隐私风险。

同步核验记录在[guoao_integration_audit.json](../output/results/guoao_integration_audit.json)。原来源清单未重写；旧记录中的历史单种子核验、部分真值核验及失败日志保持原含义，不补写成新实验。

这次没有重新训练13个模型、重新加载组员模型或重新执行70条数据库查询。模型本体不在包中，当前机器不能仅凭清单重新验其内部结构或加载重放。原始计数的数据库执行证据来自组员交付；本次独立检查的是保存数值、官方查询对齐和包内部完整性。

## 6. 复训与组员交接

基础流程可按[主README](../README.md)重跑。恢复组员完整实验还需要交接13个匹配指纹的模型、原数据/HDF、相容环境及PostgreSQL16.15的数据库设置。ZIP中的9个成员提供历史驱动/适配来源和许可证，不能冒充已经接入统一命令的一键复训工具。

`${PROJECT_ROOT}`、`${TEAM_ROOT}`是原记录中的脱敏占位符，需要按实际目录恢复；不要将历史命令中的占位符直接当成可执行路径。恢复时用新运行目录，并验证SQL、样本预算、推断策略、种子、预采样及连接规模来源，避免覆盖原结果。

建议小组最终报告使用本文件的范围表、三种子尾部结论及原图文报告；模型交付与实验扩展按[CONTRIBUTING](../CONTRIBUTING.md)记录。DeepDB不是Zero-Shot Cost Models，不能把三种样本量当成三种输入表示，也不能用这一单数据库结果声称完成跨数据库、few-shot或留一数据库实验。两篇项目继续分开。

## 7. 当前仍未完成的范围

本批贡献不能单独补齐论文全部表格、作者200条查询成员、Figure5原合成生成参数、SSB/Flights的作者对齐及全部对比方法。完整论文复现继续在[扩展分支](https://github.com/VictoriaSU551/DSC5003-DeepDB/tree/reproduction/full-paper)记录各阶段的独立证据；其已完成与未完成范围以该分支文档为准。
