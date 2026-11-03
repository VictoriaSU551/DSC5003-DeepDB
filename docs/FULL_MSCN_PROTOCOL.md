# MSCN 本地基线与恢复协议

本协议只覆盖 Table 1 的官方 JOB-light 70 条 MSCN 重跑。输入通过校验和环境就绪不代表
训练已完成；以 `output/full/mscn/<run>/checkpoints/latest.json` 的已完成 epoch 和本地预测为证据。

## 固定来源与输入

来源为 [andreaskipf/learnedcardinalities](https://github.com/andreaskipf/learnedcardinalities/tree/50073283eacdea300d1dcd815c720f64e3d2d400)，
提交 `50073283eacdea300d1dcd815c720f64e3d2d400`。
完整 ZIP 留于 `data/downloads/mscn-50073283eacdea300d1dcd815c720f64e3d2d400.zip`，
SHA256 为 `8cd760049c496e5cf30aba7bd8e89051738e9931745bceb9198e5554acbdfe4e`。
原始源码和 MIT 许可证放在 `code/vendor/mscn/`，数据与 workload 原件放在 `data/mscn/`。
ZIP 中每个文件在审计时逐字节核对，不修改 vendor 源码。

- 原始 `data/train.csv`：100000 条；配套 `data/train.bitmaps`。
- 原始 `workloads/job-light.csv`：70 条；配套 `workloads/job-light.bitmaps`。
- 每个 bitmap 记录先存 little-endian uint32 表数量，随后按 CSV 表顺序保存每表 125 字节。
  每字节按 NumPy 默认的高位在前展开，恰好1000个 materialized samples。
- 每行表数、bitmap边界、完整结尾均校验；70条重构SQL和整数真值逐条对齐本地JOB真值文件。
  位图只含位，没有 sample-row ID，因此不能仅靠结构检验发现同表数查询位图交换；
  固定官方 ZIP 的内容摘要封印承担配对来源验证。
- `column_min_max_vals.csv` 与整份训练数据共同决定编码字典和标签归一化，沿用官方实现。

`output/full/results/mscn_sources.json` 包含每个来源文件的字节数、SHA256、行数和配对结果。
审计源码不导入 PyTorch，不展开100K训练位图，也不启动训练。

## 配置与已记录适配

官方 README 指定 Python3.7/PyTorch1.0。本地隔离环境 `.venv-mscn` 使用 Python3.8.20、
PyTorch1.13.1+cpu、NumPy1.24.4。它是已注明的运行时兼容适配，不能声称原始二进制环境一致。
不修改原 `.venv`、SPFlow依赖或全局安装。下载 wheel 的来源和SHA256保存在
`.venv-mscn/wheels/manifest.json`，环境精确版本写入每个运行的绑定。

默认100000条查询中前90000条训练、随后10000条验证；不洗牌。
100epochs、Adam学习率0.001、batch1024、hidden256、1000位样本、CPU执行。
模型采用原始 `mscn/model.py:SetConv`，特征函数和 q-error 损失使用原始 `mscn/util.py` 与 `train.py`。
标签归一化使用整份100K训练输入的log最小值/最大值，保留官方行为。

包装器的变更：按需展开每条bitmap并构造同样的补零张量，避免官方loader一次持有多份稠密样本；
轻量真实输入测试与官方loader逐张量比较，覆盖bit顺序、掩码和补零。
训练使用固定seed1，原实现没有固定随机种子，因此不能承诺恢复作者的具体随机权重。
PyTorch固定CPU线程数（默认4），不增加DataLoader子进程。推理以 `no_grad()` 执行。
官方逐样本 q-error 损失原样使用，训练次序、默认批量和优化器配置保持一致。

## 运行与断点

从 Deep DB 根目录执行；`--epochs` 是目标累计epoch，不是本次追加数：

```powershell
.venv/Scripts/python.exe code/full_mscn.py audit
.venv-mscn/Scripts/python.exe -m pytest code/tests/test_full_mscn.py -q
.venv-mscn/Scripts/python.exe code/full_mscn.py train --epochs 1
.venv-mscn/Scripts/python.exe code/full_mscn.py train --epochs 100
.venv-mscn/Scripts/python.exe code/full_mscn.py evaluate
```

单epoch命令完成后再以100作为目标，会从epoch2继续。默认运行名为 `table1_job_light_seed1`。
缩小 `--queries`、hidden、batch 等配置必须使用其他 `--run`，输出标为兼容验证，不能计作Table1完成。
训练运行由系统文件锁排他保护；进程退出时操作系统自动释放锁，避免不必要的手动解锁。

每个完整epoch结束后保存模型、Adam状态、Python/NumPy/Torch随机状态和累计历史到独立`.pt`，
先原子替换checkpoint文件，再原子提交含SHA256的`latest.json`。
未提交的中断文件不能覆盖上一个已提交epoch。恢复前校验数据、vendor源码、包装器、
本协议、精确依赖版本与训练配置；任何改变、损坏或缺失均拒绝复用，不自动从epoch0重跑。
已完成epoch不会重做，未完成epoch从其开头重跑。目标epoch小于已完成数也会拒绝。
只从本地已封印checkpoint载入pickle，不载入外来checkpoint。

`evaluate`对70条配套输入推理，保留每条query_no、SQL、真值、估计、q-error和延迟。
小于100epochs的输出状态明确为`PARTIAL_TRAINING`；完整Table1状态还要求100K训练与默认参数。
模型参数字节、完整checkpoint大小与推理延迟分别报告；checkpoint包括Adam等状态，不能冒充模型空间。
不把作者报告值或历史baseline结果写成此次本地输出。

## 683 条泛化集

DeepDB公开683条泛化查询（其中413条为4--6表）缺与之配套的原MSCN位图和materialized sample行。
官方MSCN scale.sql 与DeepDB的500条scale查询有499行不同，故现成scale位图禁止混用；
JOB-light位图也不能供泛化集使用。当前泛化状态为
`BLOCKED_MISSING_MATCHED_BITMAPS_AND_SAMPLE_ROWS`。

若后续选择重建：固定本地IMDb表版本/哈希，为每个表使用有明确定义的稳定抽样算法和seed选取
1000行（表小于1000行时另行明确有放回策略），持久化sample的主键、完整值、顺序和摘要；
从同一组sample对100K训练查询、JOB70及683泛化查询逐表计算本表谓词的通过位，
按每条查询CSV表顺序编码，保存每一查询SQL/真值/bitmap的联合摘要。
重新训练并评估，记录这是新定义的一致样本重建协议，而不是官方原bitmap或原200条泛化实验。
需先独立验证严格/非严格边界、无谓词、空结果、NULL及所有表别名的位图语义。
