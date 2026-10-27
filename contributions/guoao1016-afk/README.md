# Guo Ao: local DeepDB experiments and count audit

个人阶段成果 / AI-assisted experimental contribution, 2026-10-09–2026-10-27.

本目录只新增个人成果，不替换仓库原有代码、结果、README 或配置。核心 DeepDB/RSPN 算法沿用作者实现，初始复现流程建立在组员已有仓库之上。本次贡献是本机实验、传统数据库对照、核验和分析材料；代码执行与起草有 AI 辅助。

## 内容与小组分工

| 路径 | 内容 | 对应工作 |
|---|---|---|
| `results/seed_runs/` | 三种样本量 × 三个全局训练种子，共九组 70-query 结果及保存的重载核验 | 扩展实验 |
| `results/seed_summary.json` | 九组指标及均值/范围 | 扩展实验汇总 |
| `results/postgresql/` | PostgreSQL 70 条估计、原始计划、630 条配对比较 | 对照与核验 |
| `results/truth_audit/` | 70 条独立计数、每次执行记录、重试设置和等价计数交叉验证 | 正确性核验 |
| `results/query_cases.json` | 查询 ID 14、34、64 的具体案例 | 结果分析 |
| `reports/zh/`, `reports/en/` | 综合实验说明、PostgreSQL 专项报告、真值核验报告 | 报告素材 |
| `figures/zh/`, `figures/en/` | 每种语言八张图 | 报告与展示 |
| `code_snapshot/` | 本阶段新增程序的归档副本 | 实验工具与核验方法 |
| `patches/seed_support.patch` | 两个已有文件的可审阅差异，未应用 | 后续代码整合参考 |

## 主要结果与边界

- 三个种子下，10K→100K 样本的中位误差均改善；100K→1M 时两个种子的中位误差略增，但三个种子的 P95 均降低。
- PostgreSQL 16.15 / default_statistics_target=100：median q-error **8.6874**，P95 **842.7846**。
- 原种子 1 / 1M DeepDB：median **1.4997**，P95 **6.9010**；66/70 条误差小于 PostgreSQL。其他两个 1M 种子分别在 65 和 64 条上更准。
- 全部 70 条真值已独立计算并匹配：**69 条原始 SQL 直接成功；ID 59 使用等价精确分组 SQL**，不是 70 条原始 SQL 均直接成功。等价方法在 ID 0、14、34、57 的原始 SQL 实算结果上交叉验证通过。
- 内部固定随机种子 17 保留，只改变 Python/NumPy 全局训练种子。只有一个数据集、一套查询和三个种子，无显著性检验。
- 真值计算在相同导入数据上进行，并非外部团队或不同 SQL 引擎的独立审计。计数执行时间、PostgreSQL 规划时间与 DeepDB 估计时间不能直接当作查询执行加速比。
- RDC 优化模型、独立核心算法重实现、最终课程报告及视频不属于本目录已经完成的声明。

## 阅读顺序

1. [中文综合说明](reports/zh/03_实验解释.txt) / [English experimental notes](reports/en/03_experiment_report.txt)
2. [PostgreSQL 中文报告](reports/zh/09_PostgreSQL对照报告.txt) / [English comparison](reports/en/09_postgresql_baseline_report.txt)
3. [真值核验中文报告](reports/zh/10_全量真值核验报告.txt) / [English true-count audit](reports/en/10_full_ground_truth_audit_report.txt)
4. 重点图：`figures/*/05_*`（种子误差）、`07_*`（数据库对照）、`08_*`（逐条对照）、`11_*`（最终成功计数耗时）。编号中的 03/09/10 是报告，不是缺图。

报告中的图号对应 `figures/zh` 或 `figures/en`；历史目录名称不表示需要复制大文件。

## 不运行数据库也能检查

从仓库根目录执行，只需 Python 3.8+ 标准库：

```powershell
python contributions/guoao1016-afk/verify_contribution.py
```

该程序重新匹配九组 SQL/真值，计算误差分位数，核对 PostgreSQL 比较、70 条计数及四条等价交叉验证，并检查发布文件指纹。它不重训模型，也不声称在缺少模型文件时重新完成模型重载验证；包内保留的是本机已经通过的记录。

等价计数变换的三个单元测试（需要 pytest）：

```powershell
python -m pytest contributions/guoao1016-afk/code_snapshot/tests -q
```

## 代码归档与后续整合

`code_snapshot` 是实验时脚本的归档，仍依赖原本 `team project/{DeepDB,tools,学习记录}` 目录布局及本地 PostgreSQL，不能直接当成仓库根目录里的新运行入口。重跑前请阅读 [来源和复现说明](docs/SCOPE_AND_REPRODUCTION.md)。
已有 `code/maqp.py` 和 `code/verify_results.py` 的修改只以补丁提供；本提交不应用补丁。组长审阅后如需整合，应在单独分支核对 `git apply --check`，不要盲目覆盖后来代码。

## 来源与可公开内容

作者代码：[DataManagementLab/deepdb-public](https://github.com/DataManagementLab/deepdb-public)，固定提交 `655ada13a043a4226a239b0c0a65bcdefef87a02`；组员仓库基准 `ac2485496157092bcdbe85f61e18db216168566e`。遵守仓库与作者许可证。

不包含原始数据、模型、虚拟环境、数据库程序/数据目录、凭据或私人课程文件。本机绝对路径在公开副本中替换为 `<LOCAL_PROJECT>` 等占位符；原始运行记录中的 source/model SHA256 仍指历史本机原件。`MANIFEST.csv` 校验本次公开副本，并保留来源原件指纹，二者不要混淆。

**English scope:** This add-only directory archives AI-assisted local experiments, a PostgreSQL estimate baseline and a full count audit. It builds on author algorithms and the teammate pipeline. There are nine verified seed/sample settings, one workload of 70 distinct queries, and 630 model–database pairings. Count audit: 69 direct original SQL successes plus one exact equivalent grouped calculation (ID 59), cross-checked on four executed cases. No full-paper reproduction, independently implemented RSPN, optimized RDC, statistical-significance or execution-speedup claim is made. Source snapshots are archival, while the offline verifier and three exact-count unit tests can run from this directory. Absolute local paths are normalized in public copies.
