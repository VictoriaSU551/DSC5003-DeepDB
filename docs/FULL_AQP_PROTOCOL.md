# DeepDB AQP 输入、论文配置与尚未完成的实验

本文件从属于 `FULL_REPRODUCTION_PROTOCOL.md` 和 `FULL_REPRODUCTION_PLAN.md`。
本阶段只取得并验证 IDEBench 生成器的输入样本和原版源码，**没有生成 Flights 1B、训练模型、
执行 SSB SF500 或重跑任何 AQP 对照方法**。下载原始样本不是 Figure 9--13 的完整复现。
旧 JOB-light 结果不属于本文件的完成范围，也不覆盖。

## 1. 固定来源和可重复验证

- 官方仓库：<https://github.com/IDEBench/IDEBench-public>
- 固定提交：`67339d9b81d0bcbb7b41ce6dc2e55918cf1c498f`。
- 下载地址：<https://raw.githubusercontent.com/IDEBench/IDEBench-public/67339d9b81d0bcbb7b41ce6dc2e55918cf1c498f/data/flights.zip>
- Git tree 中的归档 blob SHA1：`e8073ce07ea81db6df3e83c281c12beab2c416db`；长度为
  **78,000,681 bytes**。这是 Git 的 `blob <size>\0<content>` 对象摘要，不是普通文件 SHA1。
- ZIP 中共有 47 项。本阶段先检验全部文件的 CRC，再只提取以下两个文件；其他条目不落地。

| ZIP 条目 | 解压字节数 | ZIP CRC32 |
|---|---:|---|
| `flights/sample.csv` | 327,292,943 | `971900ce` |
| `flights/sample.json` | 2,835 | `8946b66a` |

归档保留在 `data/downloads/`；提取文件保留在 `data/flights/`。实际 SHA256、CSV 实际数据行数、
列序、逐年行数和最早/最晚年份写入 `output/full/results/aqp_sources.json`。
SHA256 由完整下载后的文件实算；不从 HTTP ETag 或 Git blob SHA1 推造。
执行日志位于 `output/full/logs/aqp_download.log`。

2026-10-30完整下载及再次离线校验的实测结果：**5,000,000条数据行，12列，1995--2016年**。
全部47个ZIP条目的文件CRC检验完成；真实文件摘要如下：

| 文件 | 实算SHA256 |
|---|---|
| 原始ZIP | `01af4eb1f36c607d37ad7c7f4662a3f43aa7053d6a5571d7df2edf2d274e644b` |
| sample.csv | `869aa27e19a89f99a06204292d9bfc584cfd0eea0debed9e3eb69f3e1820c936` |
| sample.json | `8f686f9c854f52ab61a0def0ae9a94cab4c4b7fc39466c4b9ce934acba84efdf` |

固定 `datagen.py`、`LICENSE` 和上游 `README.md` 原样存放在 `code/vendor/idebench/`，
每个文件的固定 blob SHA1 和实算 SHA256 记录于同目录 `SOURCES.json`。生成器是单文件程序，
没有需额外取得的本地 Python 支持模块；它依赖 NumPy、Pandas、SciPy，并读取上述 descriptor。
本阶段不安装依赖、不修改项目环境、不执行该生成器。

在项目根目录运行：

```powershell
& .\.venv\Scripts\python.exe -B .\code\full_aqp_data.py
& .\.venv\Scripts\python.exe -B .\code\full_aqp_data.py --verify-only
```

第二条命令不访问网络，重新验证归档固定 blob/长度、全部 ZIP CRC、提取文件 SHA256、列序和实际行数。
只有每个提取文件与刚从固定归档解压计算的 SHA256 相同，才视为有效缓存；文件被篡改时失败，
不会悄悄覆盖或继续记为有效。原版源码被篡改同样失败。
成功回执的 `stage=AQP_SOURCE_INPUTS_VERIFIED_ONLY`，不代表 1B 生成或论文实验完成。
失败会写 `status=FAIL`，不得仅凭旧成功摘要判断数据当前有效。

## 2. Flights 数据和扩展算法

论文 6.2 节要求 Flights **1,000,000,000 行母体**，DeepDB 使用 **10M** 训练样本，
12 条查询对应 F1.1--F5.2。查询涵盖 AVG、COUNT、SUM、乘积、两个 SUM 的差以及 GROUP BY，
原始 SQL 为 `code/benchmarks/flights/sql/aqp_queries.sql`。

论文参考文献 [1] 指向 <https://www.kaggle.com/usdot/flight-delays>，该页面现为
“2015 Flight Delays and Cancellations”。但 IDEBench 提供的输入以及作者 1B 真值的年份分组
覆盖 **1995--2016**；F3.3 还查询 `year_date=2005`，F1.2 查询 `unique_carrier='TW'`。
因此不能直接以 2015 单年 Kaggle 数据替换作者基准。

固定生成器源：
<https://github.com/IDEBench/IDEBench-public/blob/67339d9b81d0bcbb7b41ce6dc2e55918cf1c498f/datagen.py>。
上游使用说明：<https://github.com/IDEBench/IDEBench-public/wiki/1.-Setup>。

| 代码位置 | 实际行为 |
|---|---|
| `datagen.py:25--33` | 默认种子41001，批大小100000，最多读取5M输入行；目标行数由`--size`决定 |
| `107--110` | 默认将每个 quantitative 列减去该列最小值；延误数值会发生平移 |
| `136--148` | 数值标准化，计算协方差及 Cholesky 分解 |
| `170--193` | 每批种子为初始种子加批号；相关正态→正态CDF→经验逆CDF→反标准化 |
| `199--218` | 分类列按各自边际分布独立生成；机场所属州通过机场映射恢复；数值保留1位小数 |
| `227--235` | 经验逆CDF使用1000个直方图桶及线性插值 |

后续若生成1B，可显式固定 `--size 1000000000 --random-seed 41001 --batchsize 100000`，
但这只是公开程序的默认配置：论文/DeepDB README 没有证实作者实际使用的生成种子和批大小。
改变批大小会改变随机数序列和输出，不能只记录种子。

DeepDB README 218--241 行使用 `.01` Bernoulli 抽样生成 `dataset_sampled.csv`；
其 `awk 'BEGIN {srand()}'` 没有指定固定抽样种子。Python 的 `maqp.py` 把 NumPy 和 random
种子固定为1，不等同于固定前面的 shell 抽样。
`schemas/flights/schema.py:4--8` 将母体设为1B、抽样率设为.01。
上游没有发布作者的最终训练 CSV 或训练模型；IDEBench `sample.csv` 是生成器输入，
不是作者从1B母体抽得的10M模型训练集。

## 3. SSB SF500 与可行的流式执行路线

论文要求 SF500，不是小规模 SSB。作者 `schemas/ssb/schema.py:82--152` 的母体规模为：

| 表 | 作者声明的行数 | 数据准备 |
|---|---:|---|
| lineorder | 3,000,028,242 | Bernoulli .003333，约10M原始样本，再用于1M/10M模型 |
| customer | 15,000,000 | 完整维表用于连接真值，模型按配置抽样 |
| part | 1,800,000 | 同上 |
| supplier | 1,000,000 | 同上 |
| dwdate | 2,556 | 完整维表，CSV文件名为`date.csv` |

原作者分发路径 `https://www.cs.umb.edu/~poneil/dbgen.zip` 在本环境发生证书链校验错误，
未绕过 TLS 校验。可取得的原版衍生源码包括：

- <https://github.com/electrum/ssb-dbgen/tree/219403ad7d1dd32ae1f97b5553abf92129fccd7f>
- <https://github.com/vadimtk/ssb-dbgen/tree/0741e06d4c3e811bcec233378a39db2fc0be5d79>
- <https://github.com/eyalroz/ssb-dbgen/tree/ae1e254aa4d603d8ef1f44078e5abed011634b23>

这些来源不能直接标为“已确认的DeepDB作者生成器版本”。它们的 `driver.c` 通过log2决定part行数，
`dss.h:L_PKEY_MAX` 却使用自然对数决定事实表part外键上界；这个历史特点应固定并审计，
不为所谓修正而静默改变。`rnd.h` 定义独立固定随机流；`bm_utils.c:set_state` 和 `-C/-S`
支持分片跳种子，`tbl_open` 有FIFO分支。Windows上的流式输出仍需单独实现和验证。

原始文本空间暂按 **300--400GB** 预算，非本机实测。依据是
[Apache Doris 原始报告](https://doris.apache.org/blog/ssb/)中SF100约600M事实行、约60GB，
再外推SF500并考虑更长键值。`tbl`转`csv`保留两份、数据库、索引和临时文件会进一步增大空间。
项目当前空闲磁盘不能直接容纳这些全量共存文件。

可在保持原规模母体的条件下减少落盘量，以下步骤**尚未实施**：

1. 固定生成器版本、全部编译参数、分片数、随机流及抽样种子。先生成四张完整维表。
2. 在小规模上比较整表与分片输出，验证跳种子不重不漏，并用SQL独立核验全部13条聚合。
3. 完整遍历SF500全部事实记录；每行按维表键映射执行13条查询的过滤和整数SUM/GROUP BY，
   维护少量聚合状态，同时用独立随机流保留10M样本，再选嵌套1M。
4. Windows可用经过验证的输出适配，或只保留一个有界分片；处理完并原子封存状态再删除该分片。
   不把尚未验证的Unix FIFO命令当作Windows已跑通证据。
5. 完成后检查实际总行数、键匹配、分片覆盖和全部13条真值。按分组键比较作者真值，不能依赖行顺序。
   输出、样本和检查点实算SHA256；若生成器版本导致差异，记录并另存，不能冒称精确恢复作者母体。

全部事实行实际生成和参与真值计算，区别于仅生成1M/10M小母体。但该路线只能先完成
DeepDB训练与原规模真值，**不能得到VerdictDB、WanderJoin/XDB、Postgres TABLESAMPLE的原规模延迟**；
后三者仍需相应原规模数据库和存储预算。

## 4. 论文、README和上游历史记录的差异

DeepDB固定上游为 `655ada13a043a4226a239b0c0a65bcdefef87a02`。
本地README的AQP部分在143--281行。不能以文档路径存在代替配置经过核验。

| 项目 | 论文6.2 | README | 发布的历史证据 |
|---|---|---|---|
| Flights准确率 | 1B母体、10M训练 | single10M、RDC=.3、post_sampling_factor10 | stats记录9,999,751个训练样本，符合Bernoulli样本量随机性 |
| SSB准确率 | SF500、1M训练 | single1M | stats列出single10M以及四个relationship10M模型；不能证明Figure10最终使用哪个 |
| SSB CI | 10M参考样本、模型在该实验也用10M | 注释写10M，模型路径却仍是single1M | CI历史CSV存在，模型文件未发布 |
| CI低样本处理 | 排除count<10 | 无过滤参数 | evaluator只跳过count<=1；绘图需要补足论文过滤 |
| 对照采样预算 | Flights VerdictDB默认1%；SSB及TABLESAMPLE调到平均2秒；WanderJoin限制2秒 | 未提供基线执行入口 | 有不同采样率的历史CSV，不能仅据文件名认定最终图中选哪组 |

历史stats原始地址：

- <https://raw.githubusercontent.com/DataManagementLab/deepdb-public/655ada13a043a4226a239b0c0a65bcdefef87a02/baselines/aqp/results/deepDB/flights1B_ensemble_stats.csv>
- <https://raw.githubusercontent.com/DataManagementLab/deepdb-public/655ada13a043a4226a239b0c0a65bcdefef87a02/baselines/aqp/results/deepDB/ssb500GB_ensemble_stats.csv>

SSB四个relationship模型的学习耗时合计约989.5秒，接近论文17分钟；这只是配置线索，
不能据此断言论文训练配置。准确率1M与CI10M应分别记录，必要时增加历史配置核验，
而不是把README单个模型的成功运行直接计为两种论文配置均完成。

## 5. 发布真值的实际完整性与CI修复需求

已对上游pickle只读解包清点：

| 文件（位于`code/benchmarks/`） | 查询键 | 总结果分组/行 |
|---|---:|---:|
| `flights/ground_truth_1B.pkl` | 12/12 | 331 |
| `ssb/ground_truth_500GB.pkl` | 13/13 | 2,059 |
| `flights/confidence_intervals/confidence_interval_10M.pkl` | 12/12 | 329 |
| `ssb/confidence_intervals/confidence_interval_10M.pkl` | 13/13 | 1,763 |
| `flights/ground_truth_10M.pkl` | 仅4/12 | 不完整，不用于完整12查询评价 |

发布真值能作为作者参考；新生成数据必须另算独立真值并比较，不能默认生成种子相同。
CI真值每组有aggregate、stddev、count，不是全量母体真值的置信界。

需在后续CI实施阶段处理，当前下载阶段没有修改这些代码：

1. `ssb/sql/confidence_queries.sql` 全部使用`TABLESAMPLE SYSTEM(16.667)`，与SF500约3B→10M
   的约`.333333%`不符。发布CI第一条count198773，而对应全量count59575490，比例接近1/300。
   不能照搬该SQL重新生成后仍声称取得10M参考。应直接在明确的10M事实样本及完整维表上计算。
2. CI参考应绑定实际训练样本、样本量和descriptor。Flights放大100，SSB放大300；
   样本率舍入或样本量随机性须留档。README的CI函数使用两个不同参数传递样本数，需保持一致。
3. `evaluation/confidence_interval_evaluation.py:83--85`只跳过count<=1；论文排除count<10。
   发布SSB CI中S3.4和S4.3所有组均少于10，解释Figure11不画这两项。
   历史SSB输出仍包含194条count2--9的记录，绘图必须按论文继续过滤。
4. `ensemble_compilation/spn_ensemble.py`的`build_confidence_interval`和CI evaluator均用
   `norm.ppf(.95)`，对应**中心90%双侧区间**，不能标为95%双侧区间。
5. 相对CI长度用单侧半宽除预测值；与论文一致记录，不误写为全区间宽度。
   F5.2是两个相关SUM的差，论文明确其独立性假设不成立、区间可能偏宽，不能当作一般校准保证。

## 6. Figure9--13仍需的实际执行证据

| 图 | 必需工作与输入 | 当前真实缺口 |
|---|---|---|
| 9 | Flights1B、10M训练、12查询逐组真值；DeepDB/VerdictDB/TABLESAMPLE误差和延迟 | 1B尚未生成；无模型、本地测量及原规模基线数据库 |
| 10 | SSB SF500、1M训练、13查询；DeepDB/VerdictDB/XDB/TABLESAMPLE | SF500及原规模数据库尚未生成，配置冲突待核验 |
| 11 | 两数据集10M模型及对应参考样本；样本stddev/count、论文过滤 | 模型、参考样本绑定与上述CI修复未完成 |
| 12左 | DBEst在1/2/3个数值过滤属性上的延迟 | 缺本地运行器；上游仅有SSB pair 1d/2d/3d历史结果 |
| 12右 | Flights wavelet维度变化的误差，与DeepDB比较 | 缺wavelet实现/运行器；历史CSV含维度2--12、30K系数、1M样本等参数 |
| 13 | Flights12查询：每查询优化wavelet、DBEst、知晓工作负载的分层样本、DeepDB | 缺本地基线训练/推理、先验信息绑定、误差核验 |

已查询上游完整Git tree：`baselines/aqp/`具有发布结果CSV/PKL和两份DBEst抽样SQL资源，
没有这些基线的训练/测量入口或绘图脚本。Windows此前排除了含非法文件名的`baselines`目录，
但即使取得这些CSV，也只能称“作者历史结果重建”，不能称“本地重跑”。
现有`maqp.py`可执行DeepDB的HDF、single/relationship模型、AQP/CI，及通过Postgres计算真值。
运行器缺失、原规模数据库存储不足和作者最终训练样本未发布均保留为未完成条件。

## 7. 本阶段验证

`code/tests/test_full_aqp_data.py`使用实际构造的ZIP测试路径穿越、必需文件缺失、选中/未选中成员CRC损坏、
提取缓存篡改、Git blob不符、列序不符以及有效缓存幂等复用。测试先观察实现缺失而失败，再实现并通过。
在`code`目录运行：

```powershell
& ..\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/test_full_aqp_data.py -q
```

下载器和`--verify-only`必须实测，文件统计以成功回执为准。本阶段成功不勾选整个AQP实验完成。

后续独立阶段已完成200K原版/流式/恢复金标准，详见`FULL_FLIGHTS_STREAMING.md`。
该阶段实际运行了原作者小规模生成器，但仍没有启动1B正式生成；本文件上述下载回执保留为输入获取阶段证据。
