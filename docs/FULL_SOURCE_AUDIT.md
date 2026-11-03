# DeepDB 公开来源与输入清点

核查日期：2026-10-30。固定算法上游：
[`DataManagementLab/deepdb-public@655ada13a043a4226a239b0c0a65bcdefef87a02`](https://github.com/DataManagementLab/deepdb-public/tree/655ada13a043a4226a239b0c0a65bcdefef87a02)。
论文依据为原目录的《DeepDB: Learn from Data, not from Queries!》，对应
[VLDB 正式版本](https://www.vldb.org/pvldb/vol13/p992-hilprecht.pdf)。
本任务仅清点源码和输入，不训练、不运行估计器，也不把历史预测记为本地重跑。

## 可重复执行

从项目根目录运行：

```powershell
.venv/Scripts/python.exe -m pytest code/tests/test_full_inventory.py -q
.venv/Scripts/python.exe code/full_inventory.py
```

清单写到 `output/full/results/source_inventory.json`。程序不联网、不连接数据库、不加载模型。
SQL/CSV 对齐、行数、组内表数/谓词数、query_no 或非负整数真值校验失败会抛错并返回失败；
已有成功清单不会被一次失败运行替换。应同时核对本次命令退出码、清单生成时间和文件摘要。
清单包含每对输入 SHA256、审计源码/测试/文档/协议摘要、上游 baselines 树 SHA 和文件列表摘要。
外部下载可用性是下文所记日期的来源核查，离线程序不会重新验证网络状态。

## SQL 与真值实数

官方 evaluator 在 `code/evaluation/cardinality_evaluation.py:81-89` 按行读取查询。
本清点逐个非空行匹配 CSV 的 query 字段，忽略关键词大小写、空白及最后一个分号，
保留引号内字面值及标识符内容；不按分号切分，不改变真值，也不删除零真值。
CSV 支持 query/sql/query_string 与 cardinality_true/true_cardinality/cardinality 列名；
本版本实际 23 对文件使用 query、cardinality_true、query_no。

| `code/benchmarks/job-light/sql/` 文件 | 查询数 |
|---|---:|
| `job_light_queries.sql` | 70 |
| `synthetic_queries.sql` | 5000 |
| `scale_queries.sql` | 500 |

[`scale_sql`](https://github.com/DataManagementLab/deepdb-public/tree/655ada13a043a4226a239b0c0a65bcdefef87a02/benchmarks/job-light/scale_sql)
中 `{表数}_{谓词数}_SPN.sql` 的实数如下，每个文件都有逐条对齐的同名 truth CSV：

| 表数 | 1 谓词 | 2 谓词 | 3 谓词 | 4 谓词 | 5 谓词 | 合计 |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 97 | 73 | 49 | 37 | 14 | 270 |
| 4 | 70 | 69 | 56 | 43 | 22 | 260 |
| 5 | 13 | 23 | 17 | 21 | 10 | 84 |
| 6 | 12 | 23 | 13 | 11 | 10 | 69 |
| 合计 | | | | | | **683** |

Figure 6/8 所讨论的 4--6 表部分合计 **413** 条。`5_5_SPN.sql:9` 缺末尾分号，
但该文件确有 10 条单行查询；按分号切分会少算。组别的表数及非连接谓词数也按 SQL 内容检查。
此计数器仅处理这些平坦 SELECT 查询的合取条件，不是通用 SQL 语义分析器。

论文 6.1 节说使用 200 条随机查询；公开 683 条文件没有找到原 200 条的选择规则或 ID。
500 条 scale 与 5000 条 synthetic 文件同样不能证明就是这 200 条。
因此记录 `NOT_IDENTIFIED_IN_PUBLIC_FILES`；全公开集评估或新抽样 200 条都须另标协议。

## 基线源码与历史结果边界

本地 Git 对象仍有完整上游树，Windows 下无需检出不合法文件名。
使用 `git ls-tree -r -z --name-only <commit> -- baselines`，以 NUL 分隔读取真实文件名，
避免普通 Git 输出给带引号文件名添加转义后造成 `.csv` 统计错误。
全部文件数、扩展名分布、源码扩展名集合及命中路径在 JSON 中留档。
实数分布：CSV 567、pickle 602、PNG 1、SQL 2、无扩展名 600，总计1772。

固定树的 baselines 共 **1772 个文件**。没有 Python、C/C++、shell、PowerShell、R、Java、
Scala、Julia 或 notebook 实现文件；只有两个 DBEst SQL 资源、历史 CSV/pickle/无扩展名结果与概览图片。
这个结论针对固定树和明确检查的源码类型，不是对所有私有或未公开实现的断言。

- `baselines/cardinality_estimation/results/mcsn/`：21 个历史 CSV；JOB-light 一组与 20 个表数/谓词数组。
- `.../selectivity_oracle/imdb_light.csv`：70 条作者历史预测；没有相应公开驱动。
- `.../wavelets/`：5 个历史 CSV；没有相应公开 Wavelets 实现。
- `.../deepDB/`：包含 budget、samples、gen_code 和 updates 历史结果；不属于本轮执行。
- `code/ensemble_compilation/physical_db.py:94-109` 计算真实 COUNT，不是 PostgreSQL 优化器估计器。
- `code/evaluation/cardinality_evaluation.py:138-146` 的 MSCN/IBJS 对比数字是硬编码旧参考值，
  不能计作本地基线，也不能直接拿来替代本篇 Table 1。

额外来源调查读取了搜索返回的 24 个非空同名 fork 默认分支树，包含
[`b-hilprecht/deepdb-public`](https://github.com/b-hilprecht/deepdb-public)、
[`SEICS/deepdb-public`](https://github.com/SEICS/deepdb-public) 和
[`LumingSun/deepdb-public`](https://github.com/LumingSun/deepdb-public)。
作者镜像 master 仍等于固定提交；所查 fork 未补出 Fig.5 生成器或缺失基线。
新增文件主要是包装脚本、模型、推理代码。组织内 wavelet/IBJS 查询也只发现历史结果或旧引用。
这是有范围的搜索记录，不声称穷尽所有网络位置。

## 预算与实验配置差异

论文第 6 节默认预算 **B=0.5**；固定上游 README 第 62 行使用 **5**；
固定上游 `maqp.py:51` 参数类型是 int。`ensemble_creation/rdc_based.py:158-160`
把数值预算直接乘以单表列数平方和，没有除以 10。
无法据此证明 5 与 0.5 等价。JSON 同时记录上游与当前工作副本的参数声明；
即使本轮修复浮点 CLI，两个配置及其选择出的模型仍须分别留档。

Table 1 的标准模型默认 10M 样本，存储优化模型为 100K/RSPN 的基础 ensemble；
此前已验证的 1M 关系基础模型不能直接视作这两个条目的复现。
论文以训练时间解释预算，公开选择器使用列数平方成本近似，亦需保留差异。

## MSCN 原始材料

官方仓库为 [`andreaskipf/learnedcardinalities`](https://github.com/andreaskipf/learnedcardinalities)，
固定到 [`50073283eacdea300d1dcd815c720f64e3d2d400`](https://github.com/andreaskipf/learnedcardinalities/tree/50073283eacdea300d1dcd815c720f64e3d2d400)。
2026-10-30 对固定提交的 raw URL 发 HEAD 请求，下列四项均 HTTP 200：

| 路径 | 字节 |
|---|---:|
| `data/train.csv` | 10131572 |
| `data/train.bitmaps` | 27459500 |
| `workloads/job-light.csv` | 11478 |
| `workloads/job-light.bitmaps` | 32030 |

本轮未下载训练 CSV/bitmap；没有独立数过 train.csv 行数。
[官方 README](https://github.com/andreaskipf/learnedcardinalities/blob/50073283eacdea300d1dcd815c720f64e3d2d400/README.md)
要求 Python 3.7、PyTorch 1.0，论文复现命令是 `--queries 100000 --epochs 100 job-light`。
[mscn/data.py](https://github.com/andreaskipf/learnedcardinalities/blob/50073283eacdea300d1dcd815c720f64e3d2d400/mscn/data.py)
读取 # 分隔查询 CSV 与 bitmap；前 90% 训练、随后 10% 验证。
[train.py](https://github.com/andreaskipf/learnedcardinalities/blob/50073283eacdea300d1dcd815c720f64e3d2d400/train.py)
使用 1000 个 materialized samples、Adam lr=0.001，默认 batch=1024、hidden=256；--cuda 才启用 GPU。

小文件实际比对结果：job-light.csv 是 70 条且真值与本地逐行全相同；官方 job-light.sql、
synthetic.sql 与本地对应文件规范换行后相同。官方 scale.sql 与本地 scale_queries.sql
的 500 行有 **499 行不同**，不能混用 bitmap。
未找到 DeepDB 683 条泛化集对应的 MSCN bitmap、原始 materialized sample 行和生成器。
现成输入可用于官方 JOB-light 重跑；扩展泛化实验须先恢复或另行定义一致输入协议。
官方训练程序默认没有保存恢复 checkpoint，长期训练前还需独立包装保存状态。

## C++ 路径与未验证风险

- `code/maqp.py:179-181` 与 `rspn/code_generation/generate_code.py:180-203` 提供生成入口。
  生成器会分配 SPN id，并在第 199-200 行 save 回输入模型；先复制到新输出目录并封存 hash。
- `rspn/code_generation/templates/identity_leave.cpp:43` 使用
  `uniqueVals{node_id}[rightIdx{node_id}-{node_id}]`，存在减去节点 ID 导致负索引/越界的静态疑点。
  第 38 行的左边界判断也应覆盖超出数据域的输入。需用数值边界和全查询 Python/C++ 差分测试验证；
  不能把编译成功视为推理正确。
- `rspn/algorithms/expectations.py:38-59` 的 generated_spn_calls/total_time 只统计可走生成代码的调用；
  不适用条件仍可能回退 Python。须核对调用次数。
- `evaluation/cardinality_evaluation.py:125-131` 的 latency_ms 与 latency_generated_code 均为毫秒；
  Fig.8 使用微秒，绘图时乘 1000，并分别记录预热、重复测量和总路径。

工具链只读检查：PATH 无 cl/g++/clang++/cmake/ninja；vswhere 列出 VS2022 Community，
但 isComplete/isLaunchable=false，VC/Tools/MSVC 不存在，-find cl.exe 无结果。
仅 -requires 返回注册路径不能证明工具链实际存在。Python.h、python38.lib 已在项目 .runtime 内；
Python 为 3.8.20 x64，扩展后缀 .cp38-win_amd64.pyd；当时 venv 没有 pybind11/setuptools/torch。
这些是核查时点状态，后续安装需要再次检查。
官方可用路线参见 [pybind11 Windows](https://pybind11.readthedocs.io/en/stable/basics.html#windows)
和 [构建系统](https://pybind11.readthedocs.io/en/stable/compiling.html)；尚未在本机验证编译。

## 各实验仍需补齐的输入

| 项目 | 输入或缺口 |
|---|---|
| Table 1 | 本地 70 条逐条预测；各原始基线实现、存储预算与运行配置 |
| Fig.5 | IMDb 模式合成数据库生成器、种子、均匀/Zipf(2/3/4)与20--100%相关属性定义；原70条非零真值及各方法 |
| Fig.6 | 413条公开4--6表输入可用；原200条映射与MSCN对应bitmap未定位 |
| Fig.7 | 1K--10M样本、正文预算0--3含0.5、相同查询集及训练时间；不得用作者历史计时代替 |
| Fig.8 | C++编译、边界差分和全查询一致性、生成代码覆盖与独立计时 |
| Fig.12 | DBEst 1/2/3个数值过滤属性延迟与Wavelets维数实验驱动；原版本/参数及Flights数据 |

Fig.5 的合成数据与 synthetic_queries.sql 是两件不同的输入。
Fig.12 只有历史 `baselines/aqp/results/dbest/.../times.csv` 与
`baselines/aqp/results/wavelets/curse_of_dim/*.csv` 等产物。
现今 [DBEstClient](https://github.com/qingzma/DBEstClient) 已说明 DBEst++ 的后续工作，
不能未经版本核对就当作原文旧基线。复原图形可用历史产物，但必须标明“作者历史结果重建”。

## 本任务验证记录

先创建 9 个行为测试；实现缺失时测试命令实测返回 9 failed、退出码1。
实现后针对同一组输入重新执行，核验缺分号查询不丢失、同长错位真值被拒绝、
字符串字面值大小写不被误归一化、零真值保留、坏query_no/负真值/行数不符拒绝、
带引号Git路径正确分类，以及组别表数/谓词数由内容校验。
首次相对路径执行暴露 Python 3.8 的相对 __file__ 与绝对路径封存不匹配；
新增第10项真实输入回归测试，先实测失败，再通过解析绝对路径修复。
最终测试与生成清单的命令结果以当前任务回报为准；未提交、推送或运行资源密集实验。
