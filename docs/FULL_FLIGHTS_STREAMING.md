# Flights 批次流式生成：200K金标准与恢复证据

2026-10-30完成的是 **200,000行的小规模等价性金标准**，不是论文1B实验。
固定原作者生成器实际产生的CSV、连续流式输出、中断后恢复输出三者逐行12列一致，且文件SHA256相同。
全部12条查询的296个结果分组，与独立SQLite精确整数SQL状态完全一致。
**未启动1B正式生成、模型训练或论文对照方法。**

入口：`code/full_flights_generate.py`。沿用`FULL_REPRODUCTION_PROTOCOL.md`、
`FULL_REPRODUCTION_PLAN.md`和`FULL_AQP_PROTOCOL.md`的原规模定义及完成边界。
所有新文件只写`output/full/flights/`和`data/flights/generated/`。
没有修改vendor源码、其他核心模块或Python环境；没有访问PostgreSQL现有表或imports目录。

## 1. 固定算法及唯一适配

原始文件为`code/vendor/idebench/datagen.py`：

- 上游commit：`67339d9b81d0bcbb7b41ce6dc2e55918cf1c498f`。
- 原始SHA256：`e7527f37f062eafc501062aaac4b164d1413127ef45129bd7ed9db699cebd8e9`。
- 原始输入CSV SHA256：`869aa27e19a89f99a06204292d9bfc584cfd0eea0debed9e3eb69f3e1820c936`。
- descriptor SHA256：`8f686f9c854f52ab61a0def0ae9a94cab4c4b7fc39466c4b9ce934acba84efdf`。

适配器在内存解析固定源码的AST，拒绝不符合预期的代码结构；不修改磁盘上的原文件：

1. 仅去掉模块末尾自动执行的`DataGen()`，以便受控实例化同一个类。
2. 将唯一的`range(num_batches)`改为`range(_resume_batch_start,num_batches)`，跳过已经封存的批次。
3. 包装`process_batch`以标识当前批号；原方法体完整执行。临时拦截其指定输出路径上的
   `DataFrame.to_csv`，将原始结果帧送入采样、精确聚合和批次提交。
4. 输出拦截拒绝意外目标、额外参数或列序；结束后恢复`sys.argv`和Pandas方法。

减最小值、标准化、协方差、Cholesky、正态CDF、1000桶经验逆CDF、分类边际抽样、
函数依赖恢复、保留一位小数，均直接执行原作者方法体，没有重新实现或替换统计生成算法。
每批仍由作者代码执行`np.random.seed(generation_seed + batch_number)`。
每个运行目录的`source_adapter.json`记录原始SHA256、适配说明和适配后AST摘要。

本次环境：Python3.8.20、NumPy1.19.5、Pandas1.0.3、SciPy1.4.1。
这些版本、输入摘要、查询摘要、适配器自身摘要和完整配置均进入检查点binding。

## 2. 200K金标准的实际配置和命令

输入使用全部5M原始行进行原算法分布准备；输出200K，两个100K批次。
生成种子41001，采样种子81001，独立Bernoulli概率.01。
保持默认数值最小值平移，未使用缩小的输入样本改变分布。

本次先直接执行未修改的原文件，退出码0，日志为
`output/full/flights/golden-200k/original.log`：

```powershell
& .\.venv\Scripts\python.exe -B .\code\vendor\idebench\datagen.py `
  --sample-file data/flights/sample.csv `
  --sample-descriptor data/flights/sample.json `
  --size 200000 --batchsize 100000 --random-seed 41001 --num-samples 5000000 `
  --output-file data/flights/generated/golden-200k/original.csv
```

随后明确指定这份已实际生成的CSV，避免重复执行原作者生成：

```powershell
& .\.venv\Scripts\python.exe -B .\code\full_flights_generate.py golden `
  --rows 200000 --batch-size 100000 --seed 41001 --sampling-seed 81001 `
  --sample-rate 0.01 --run-name golden-200k `
  --reference-csv data/flights/generated/golden-200k/original.csv
```

若在全新运行目录重做金标准，可省略`--reference-csv`，程序会以独立子进程实际执行固定原版，
保存命令和日志，再进行同样比较。已有但未封存的原版CSV不会被静默视为可信缓存；
显式指定的参考也必须通过与固定配置流式输出的全部行/列比较。

实际主回执：`output/full/flights/golden-200k/golden_validation.json`，
`status=PASS`、`stage=SMALL_SCALE_GOLDEN_ONLY`、`paper_scale_reached=false`。

| 结果 | 实测 |
|---|---|
| 原版CSV数据行数 | 200,000 |
| 列数与逐行内容 | 12列，全部一致 |
| 原版/连续/恢复CSV字节数 | 均为11,643,759 |
| 三份CSV的SHA256 | `c9df154be75aebc047ce7c11c5efc55c2e81e13b85e5b2a5fc26f219d312992d` |
| 连续/恢复Bernoulli样本 | 均为1,993行、116,180 bytes |
| 两份样本的SHA256 | `5a59fd5538a0946cea74accca732f274c2e3e9927c247f32ee14f61d450a7390` |
| 连续实际执行批号 | `[0,1]` |
| 中断前实际执行批号 | `[0]` |
| 恢复实际执行批号 | `[1]`，未重算批次0 |
| 恢复丢弃的未提交尾部 | sample.csv与population.csv各31 bytes |
| 最终next_batch | 2 |

原版CSV、连续CSV、恢复CSV保留在`data/flights/generated/golden-200k/`及其两个子目录。
检查点、结果、适配记录、SQLite文件和SQL状态在对应`output/full/flights/golden-200k/`。
另外对已完成运行做缓存检查：将统计生成入口替换为必然报错的运行时guard后，再调用恢复接口，
仍返回PASS且执行批号为`[]`；两个数据文件mtime不变。证据为`completed_cache_check.json`，
确认适配器源码摘要与检查点一致，未重复准备分布或生成已封存批次。

## 3. 独立SQL真值与精确算术

生产流式路径对每批的原结果帧应用固定12条SQL的谓词和分组，独立维护整数sum/count。
所有生成数值在CSV中均为一位小数，因此按整数十分位表示；两个数值的乘积按百分位表示。
NumPy每批使用int64加法，并做溢出上界检查；跨批使用Python整数累加，不把加权bincount浮点和
当作精确SUM。AVG保留精确的分子/分母，展示用十进制值不是唯一真值依据。

金标准另从**原作者实际CSV**出发，用标准库CSV和Decimal逐值读取，再载入独立SQLite。
SQL中的数值列存成十分位整数，阈值2500/1000/1500相应表示为25000/10000/15000；
SUM的分母为10，`arr_delay*dep_delay`的分母为100，AVG的分母为10乘行数。
这种固定点表示保持原12条SQL的数学意义，避免SQLite REAL累加舍入掩盖错误。
参考路径不调用流式NumPy分组函数，两个实现的分组键、整数和及count要求逐项完全相等，未使用误差容忍。

| 查询 | 独立SQL结果分组数 |
|---|---:|
| F1.1 | 1 |
| F1.2 | 1 |
| F2.1 | 26 |
| F2.2 | 23 |
| F2.3 | 17 |
| F3.1 | 22 |
| F3.2 | 41 |
| F3.3 | 23 |
| F4.1 | 50 |
| F4.2 | 22 |
| F5.1 | 22 |
| F5.2 | 48 |

合计296个分组，连续和恢复两种运行均与SQLite全部相等。
`sqlite_exact_state.json`保留独立SQL文本和状态；每个子运行的`ground_truth.json`保留
原SQL、整数分子/分母及完成标志。母体尚未完整生成时`complete=false`，不能提前当成全量真值。

## 4. 原子批次、尾部截断和恢复边界

每批按以下顺序处理：原作者生成→精确聚合→独立采样→追加输出并flush/fsync→
原子替换`checkpoint.json`。检查点同时保存下一批号、实际生成/样本行数、12查询状态、
每个输出的已提交字节偏移和SHA256，以及检查点本身的内容摘要。

恢复先核对完整binding和所有已提交文件前缀，再截断比封存偏移更长的尾部。
已提交前缀更短、hash不符、检查点损坏或输入/生成种子/采样种子/代码/环境变化都会失败。
输入binding不符时先失败，不先截断文件。OS文件锁阻止同一运行同时有两个写入进程；
进程退出会释放锁，旧锁文件不需要人为删除。

金标准先在提交批次0后有控制地停止，再在两个CSV各追加31字节模拟未提交写入，
然后恢复批次1；不是声称做了操作系统断电试验。恢复日志只显示批次1的生成。
真正中途写入未封存的批次会重新生成；已经完成且封存的批次不会重算。
恢复仍需重新准备原输入分布，这部分固定5M的均值/协方差等准备工作尚未另做序列化缓存。

采样使用局部`RandomState(sampling_seed + batch_number)`，不消耗原作者全局`np.random`状态；
采样比例约1%，不是保证样本恰好10M。批量大小、种子和输入上限均不能在同一检查点上改变。

## 5. 后续1B路线已具备的接口及尚未完成项

CLI默认200K；只有显式`--rows 1000000000`才请求1B。下面是**尚未执行**的后续命令：

```powershell
& .\.venv\Scripts\python.exe -B .\code\full_flights_generate.py generate `
  --rows 1000000000 --batch-size 100000 --seed 41001 --sampling-seed 81001 `
  --sample-rate 0.01 --input-limit 5000000 --run-name flights-1b
```

此配置不保留1B全量CSV，只保留约10M Bernoulli样本、全部12查询精确聚合和检查点。
原分布准备仍持有5M输入及原作者工作数组，并非总内存只依赖批大小。
按本次生成行宽外推，10M样本CSV约0.58GB；这是估算，不是已生成的1B样本实测值。
`--retain-population`限制最多1M行，防止调试选项将1B全量文本意外落盘。
`--max-batches N`允许每次只执行N个新批次；再次运行同一配置即从封存下一批继续。

尚未完成：

- 1B所有10,000批次的实际生成、最终行数/分组覆盖/摘要核验及作者1B真值对照。
- 原作者实际生成种子/批大小和原训练抽样种子的确证；公开默认值不等于已知作者参数。
- 从实际生成样本训练10M模型和CI参考绑定，及Figure9/11/13本地误差与延迟实验。
- VerdictDB、TABLESAMPLE、DBEst、wavelet、分层抽样的原规模本地对照；
  全母体流式真值不会自动提供这些方法所需的全量数据库或测量入口。
- 跨Python/NumPy/SciPy/Pandas版本、不同种子或不同批大小的单独金标准。

## 6. 测试

先运行9项测试，观察实现缺失导致全部失败；实现后9项通过。覆盖两个输出的未提交尾部截断、
生成/采样种子及输入binding改变拒绝、已提交前缀篡改、短文件、检查点损坏、已完成批次禁止重放、
全局NumPy状态不受采样影响，以及12查询与独立SQLite SQL完全一致。

在`code`目录：

```powershell
& ..\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/test_full_flights_generate.py -q
```

200K金标准是适配器正确性证据；本文件及回执均不将其计为1B复现完成。
本次完整项目测试还得到`52 passed, 1 warning`；warning来自原有
`test_preparation.py::test_sampled_hdfs_handle_named_indices`的整数/浮点合并提示。
