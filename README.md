# DeepDB 论文复现 · DSC5003

论文：Benjamin Hilprecht 等，**DeepDB: Learn from Data, not from Queries!**，VLDB 2020。
[论文](https://arxiv.org/abs/1909.00607) · [作者代码](https://github.com/DataManagementLab/deepdb-public)

**2026-10-30：正在继续完整复现，尚未完成整篇论文。** 原目录及第一阶段结果保留。
新阶段已独立核对全部70条JOB-light真值，完成10M原schema预算模型、100K存储模型、
单表退化模型、完整样本量/预算扫描和5个正式时间切分更新实验。
Flights已实际遍历1B母体，使用9,997,912行样本完成12SQL、331组AQP与CI；
C++已对753条公开查询逐条差分。SSB SF500、MSCN100轮及原对照方法仍有在执行/待完成内容。
公开683条真值还发现74条与本地完整数据的精确COUNT不同，正在逐条独立SQL核验，原文件保留。
不能据此宣布完整复现。

本地最新覆盖状态为 `output/full/completion_status.json`，可运行
`.venv/Scripts/python.exe code/full_status.py` 重建。方法、差异和完成条件见
[完整复现协议](docs/FULL_REPRODUCTION_PROTOCOL.md)、[执行记录](docs/FULL_REPRODUCTION_PLAN.md)、
[推理修正](docs/FULL_INFERENCE_CORRECTIONS.md)、[参数口径](docs/FULL_PARAMETER_STUDIES.md)。
当前阶段说明见[复现状态与证据](docs/FULL_REPRODUCTION_STATUS.md)，正式Flights入口见
[运行说明](docs/FULL_FLIGHTS_MODEL_RUN.md)。
后续基数结果以 `output/full/evaluation_v2/` 为准；旧CSV保留历史证据，部分旧推理缓存具有顺序依赖。

以下为保留的2026-10-08第一阶段运行说明。

本项目先复现作者提供的 **JOB-light 双表关系基础模型**：下载完整 IMDb 快照中的六张表，
预处理数据，每个关系抽取 1,000,000 个连接样本训练一个 RSPN，共训练五个模型，
评估原始的 70 条 SQL 查询，再从保存的模型重新计算所有预测。
训练不使用查询真值。

这是论文复现的第一阶段。基础模型与论文优化的 RDC ensemble 配置不同，
不能据此宣称已经复现论文的全部性能、对比实验、增量更新、SSB 或 Flights 实验。

2026-10-08 本机验证：五个模型训练完成，70 条查询全部评估，重新载入模型后 70 条预测一致，
4 项回归检查通过。q-error 中位数 **1.500**，95 分位数 **6.901**，平均查询耗时 **7.03 ms**。
完整记录见 [本次结果](output/results/RESULTS.md)。

## 文件布局

```text
Deep DB/
  code/                 作者算法、查询集和本地复现脚本
    tests/              需要保留的回归检查，不是临时调试脚本
  data/
    imdb/               六张完整原始 CSV（不上传 GitHub）
    manifest.json       来源、文件大小与 SHA256
  output/
    models/             训练完成的模型（不上传 GitHub）
    results/            查询结果、数值复核和数据审计
    logs/               本地正式运行日志
  docs/                 源码来源与兼容性修改记录
  .venv/                独立 Python 环境（不上传 GitHub）
  .runtime/             本地 Python 3.8（不上传 GitHub）
```

原始 PDF 留在本地。下载压缩包、构建缓存、调试产物和核验后不再使用的 HDF 不进入仓库。

## 在 Windows 上运行

在项目根目录打开 PowerShell。需要 Git、curl 和 uv；uv 可通过 `python -m pip install uv` 安装。
本项目使用 Python 3.8.20，以尽量保持论文时代的依赖行为。

```powershell
# 创建独立环境；已存在且可用时无需重复安装
powershell -ExecutionPolicy Bypass -File setup.ps1

# 下载、校验 SHA256 / gzip CRC、只提取六张所需表
.venv/Scripts/python.exe code/download_data.py

# 检查兼容性修改
.venv/Scripts/python.exe -m pytest

# 完整原始数据预处理、五个模型训练、70 条查询评估及模型重载复核
.venv/Scripts/python.exe code/reproduce.py all

# 直接从原始 CSV 审计行数并重算前三条查询的真值
.venv/Scripts/python.exe code/audit_data.py
```

原始数据约 2.81 GB（十进制字节）；下载包约 1.26 GB。预处理阶段还需要额外磁盘空间。
数据已存在且哈希一致时下载脚本会跳过下载；模型已存在时 `all` 会直接评估。
不要覆盖已验证实验的模型：更改代码、数据或参数后请使用独立实验目录或先备份旧结果。

只重新评估，无需 HDF：

```powershell
.venv/Scripts/python.exe code/reproduce.py evaluate
.venv/Scripts/python.exe code/verify_results.py
```

若模型不存在而只想单独执行一步，可使用 `prepare`、`train`、`evaluate`。
`--samples` 可指定每个模型的样本量；不同样本量的模型和结果文件分开命名。
固定 NumPy/Python 随机种子及 Python 哈希种子，限制数值库线程；跨系统结果仍可能有浮点差异。

Linux 可创建 Python 3.8 venv，安装 `requirements.txt`，再执行
`pip install --no-deps spflow==0.0.40`。随后使用相同 Python 脚本。
当前实测平台为 Windows；尚未实测 Linux。

## 结果与验证边界

- `output/results/job_light_1000000.csv`：70 条查询逐条估计、官方真值及耗时。
- `output/results/verification_1000000.json`：q-error 分位数、模型结构检查、70 条预测重算是否一致。
- `output/results/data_audit.json`：六张表实际行数；前三条查询由原始 CSV 独立计算，与官方真值核对。
- `output/results/run_1000000.json`：参数、阶段命令、时长、模型 SHA256。

q-error 定义为 `max(估计值/真值, 真值/估计值)`，越接近 1 越好。
第一阶段使用官方提供的70条真值，只独立重算前三条。
2026-10-30的新阶段已用项目内PostgreSQL11.5独立核对全部70条，详见完整复现记录。
耗时来自本机 Python 推理，不能直接与论文的硬件或 C++ 优化推理耗时比较。

完整复现阶段在 `reproduction/full-paper` 分支持续进行，
全部新数据/输出分别位于 `data/` 和 `output/full/`，不会覆盖第一阶段模型。
公开泛化文件实际含683条查询；它们与论文200条的精确对应仍是来源缺口。

## 来源、环境与协作

作者版本固定为 `655ada13a043a4226a239b0c0a65bcdefef87a02`。
保留作者 MIT 许可证，修改详见 `docs/UPSTREAM.md` 和 `docs/compatibility.patch`。
`requirements.txt` 是运行所需的依赖；`requirements-lock.txt` 记录本次实际环境。
SPFlow 的完整历史依赖包含本实验不用的可选组件，因此按作者建议单独以 `--no-deps` 安装。

组员按 [CONTRIBUTING.md](CONTRIBUTING.md) 使用分支和 Pull Request 协作。
请勿提交原始数据、账户凭据、虚拟环境、模型大文件或私人文档。
