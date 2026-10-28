# 交付内容与分工对应 / Delivery and contribution map

这份材料对应 DeepDB 在 IMDb / JOB-light 上的实验。分工参考图中的 Zero-Shot Cost Models 属于另一篇论文；留一数据库、三种输入表示和 few-shot 尚未开展，不能用三种样本量代替。

| 分工 | 已有工作 | 本目录证据 | 尚未覆盖 |
|---|---|---|---|
| A 数据与协议 | 六表来源、文件指纹、预处理检查、固定实验参数、训练输入检查 | evidence/data_manifest.json、protocol_audit.json、settings.json | 留一数据库实验；独立调参验证集 |
| B 模型与训练 | 9轮基础模型、4轮RDC、多种子、逐阶段记录、完成模型和逐条预测 | run_records.json、model_inventory.json、压缩日志、predictions.csv | 三种输入表示；训练内部checkpoint；模型本体未上传GitHub |
| C 基线与扩展 | PostgreSQL对照、样本量及种子实验、RDC流程对比 | metrics.csv、两份图文报告 | few-shot；独立复杂查询泛化实验 |
| D 核验与分析 | 70条真值核验、指标重算、失败案例和图表、限制说明 | truth_audit.csv、verification_records.json、图表和核验工具 | 小组最终报告/PPT/视频；全部论文表格对齐 |

因此，这份贡献主要覆盖 **B的训练与记录、D的实验核验与分析，并承担A和C的部分工作**，不能称为整张分工表已完成。

## 文件怎么用

- 数据指纹和预处理范围：`evidence/data_manifest.json`、`evidence/protocol_audit.json`。
- 逐轮配置、历史命令、阶段耗时、返回状态：`evidence/run_records.json`。`${PROJECT_ROOT}`代表DeepDB仓库，`${TEAM_ROOT}`代表外层项目目录。
- 13轮训练以及对应评估日志：`evidence/logs/training.log.gz`、`evaluation.log.gz`；数据库导入与真值核验过程及失败记录：`database.log.gz`。解压后按每段标题查找run_id。这些是选定原日志的完整文本，未删行；本机路径、用户名和凭据作占位替换。
- 每轮核验与真值交叉检查：`evidence/verification_records.json`。历史“单种子”或“仅前三条真值”的记录保留当时含义，最终覆盖以本目录汇总和最新真值核验为准。
- 模型指纹与大小：`evidence/model_inventory.json`。13个模型本体保留在本机，合计119.31 MB；GitHub清单不能加载模型，若验收需要模型应另外交付。
- 驱动与适配源码快照：`evidence/source_snapshots.zip`，包含作者许可证与来源说明。它是历史代码取证；恢复相同训练还需要原始数据、HDF、环境、数据库和目录设置，并非解压即能完整复训。
- 原始记录指纹、日志段索引及公开文件指纹：`evidence/source_manifest.json`。

训练阶段使用同一个数据库的数据，评估阶段使用查询和答案；这符合数据驱动估计的实验设定。已检查保存的训练参数和训练分支没有读取查询/答案路径，但这是限定范围的静态检查，不是跨数据库或独立调参测试，也不能概括为“任何泄漏都已排除”。

## English

This contribution concerns DeepDB on one IMDb/JOB-light database. The reference assignment table describes another paper, Zero-Shot Cost Models. Three sample budgets are not three input representations; leave-one-database-out and few-shot experiments were not conducted.

The contribution primarily covers **B: training and run records, D: verification and experimental analysis, plus parts of A and C**. It includes nine baseline and four RDC training runs, PostgreSQL estimates, all 70 truth checks, configurations, per-query predictions and bilingual figures. It does not complete every requirement in the reference table.

The evidence directory contains dataset hashes, preprocessing scope, a limited training-input audit, historical run and verification records, and complete text from the selected training/evaluation/database logs compressed with gzip. Machine-specific paths, usernames and secrets are replaced by placeholders; lines and outcomes are retained. Historical snapshots are not rewritten as new experiments. Full historical retry archives are retained locally; selected database logs include failure records.

Thirteen exact trained model binaries remain local (119.31 MB total); their hashes and locations are listed, and the binaries require a separate handoff when requested. Source snapshots include driver scripts and provenance but require the original data/HDF/runtime/database setup for retraining. They are evidence, not a turnkey end-to-end package. Stage-level resume is supported; no within-training checkpointing or continuous per-run peak-memory profile is claimed. No query-held-out tuning/validation split was used, and no zero-shot, few-shot or cross-database results are claimed.

Run `python output/results/guoao_experiments/verify_results.py --repo-root .` for numerical checks, and `python output/results/guoao_experiments/verify_evidence.py` for package integrity checks.
