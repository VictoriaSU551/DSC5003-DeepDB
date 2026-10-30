# SSB bounded preparation / single-table model protocol

SSB生成器、SF1/SF2回执和原算法模块保持只读。本阶段先在既有SF2输入上验证
bounded preparation与`prepare_single_tables.prepare_all_tables`逐项等价，不能生成新的SF1/SF2母体，
不能在SF500流生成尚运行/根任务未释放资源时训练正式SF500模型。

## 计划

1. TDD：含跨块高基数文本、FD、有序类别、数值NULL、FK NULL、缺少child PK的合成输入，
   先与原routine比较metadata及所有HDF行列/NULL tuple，保留失败后修复证据。
2. 分块探测全局类型、首次出现顺序、FD、>10000类别；全局整数统计精确合并，
   非整数全局均值按原行序memmap交给相同Pandas mean。
3. 对维表PK使用有证明的连续key或小型稀疏key索引，流式累积FK count与有效child PK匹配标记；
   完全保留原`count*1/sample_rate`及`0→1`倍数公式。
4. 使用全局字典/NULL哨兵逐块编码并写原格式HDF，同时写NULL tuple；
   全局倍数均值使用原行序memmap，相同Pandas reduction，避免改成近似分块均值。
5. 读取已封存SF2的39712事实样本及4维表，逐字节核验输入SHA后做原routine金标准。
6. preparation通过后再封存1M每表、ensemble_single、rdc0.3、post_sampling10训练入口，
   先小规模模型与13SQL/CI独立整数矩门禁；正式500执行等待根任务释放资源。

## 已完成的 preparation 门禁

`code/full_ssb_model.py sf2-gate` 只读复用已封存SF2，不调用生成器。
原routine与bounded输出均保存在`output/full/ssb/models/`独立目录；原routine产物按源/输入封印复用，
不因未来新增训练入口而重算。bounded准备只绑定自身依赖函数的AST及MAX_DISTINCT/依赖版本，
测试已证明无关训练函数新增不使准备结果失效。

实际门禁PASS：5张HDF共39712 lineorder、2556 dwdate、60000 customer、400000 part、4000 supplier；
另外3张NULL tuple HDF。全部metadata（仅目录前缀不同）、列/行/索引顺序、dtype、数值、
类别字典/首次出现顺序、FD反向字典、NULL哨兵、倍数/全局均值均严格相等，
比较使用`pd.testing.assert_frame_equal(check_exact=True,check_dtype=True)`。
输入与原routine SHA前后不变。

首轮实测：原routine4.665秒、bounded9.628秒、整门禁15.376秒，Windows进程峰值工作集
324,964,352字节。原参考目录73,343,547字节、bounded目录86,710,923字节。
后续代码增加明确的<20M存储行/384MiB FK数组硬门禁，原参考没有重算；
当前结果见`sf2_preparation_gate_latest.json`及按准备算法SHA命名的独立回执，旧回执保留。

`pytest code/tests/test_full_ssb_model.py -q`：4 passed（18.88秒）。
TDD实际先发现并修复了NULL tuple索引名（原需`parent.id`，主HDF为None）、
含NULL的类别编码dtype（原int64，误设float64）及JSON将FD tuple变list后的恢复绑定差异。
合成门禁跨73行小块处理10005个唯一文本，覆盖>10000剔除、全NULL列、数值NULL、类别NULL、
先出现顺序、FD、FK NULL及child PK NULL，输出与原routine逐项一致；
完成结果可复用，输入变更明确拒绝。

当前实现限制：只证明单PK维表为连续1..N或<=10000的有序稀疏域；
整数归约要求绝对值×行数<2^53，存储行数严格<20M，不触发原随机HDF截断分支；
这些条件均满足本SF2输入及预期SF500 schema。正式执行仍须按最终输入重新验证。
完成的表和FK计数有SHA检查点；表内未提交HDF不自动冒充完成，需另开输出目录处理。
这些是原核心检查点；正式入口的外层namespace规则见下，异常或残留RUNNING后不自动恢复该目录。

SF2使用实际抽样概率0.003333，因此元数据长度仍严格保留原routine的`n/p`估算，
不偷换为精确母体事实数；正式SF500应绑定最终流式回执中的实际抽样概率。
准备目录还未对SF500执行。下述模型/13SQL/CI是SF2、10K cap实际门禁，不是论文正式1M训练。

## 已实际执行的五模型及13SQL门禁

固定seed=1，完全复用上述prepared HDF，不重新生成SF1/SF2，不重新执行SF2准备。
训练调用原`JoinDataPreparator.generate_n_samples`、`AQPSPN.learn`和`SPNEnsemble`，
参数与原README SSB入口一致：single、rdc_threshold=0.3、post_sampling_factor=10、
min_instances_slice=0.01×实际训练行数、max_table_data=20M、无bloom、无incremental。
本门禁cap=10K，正式入口cap=1M；dwdate小于cap时使用实际2556行。
仅在进程内将原RDC的n_jobs限制为1，退出context恢复；没有修改原算法文件或RDC公式。

实际分别调用未修改的`create_naive_all_split_ensemble`与独立逐表检查点循环，
五表的训练矩阵SHA256及完整mspn pickle SHA256逐一严格相同。检查点包括Python和NumPy RNG状态，
原核心可从完成表恢复随机状态；正式外层遇异常/中断则保留检查点供独立审查，拒绝自动恢复同一namespace。
每个checkpoint和最终模型均按物理SHA验证。

| 表 | 实际训练行数 | 独立循环真实learning秒 |
| --- | ---: | ---: |
| lineorder | 10000 | 5.8456800 |
| dwdate | 2556 | 5.3308463 |
| customer | 10000 | 0.3020806 |
| part | 10000 | 8.4900215 |
| supplier | 4000 | 5.3056825 |

原naive入口27.2930476秒；独立循环learning合计25.2743109秒。
最初整轮62.4623538秒在训练全部保存后因truth JSON使用数字query id而非S1.1名称失败，
`small_model_before_truth_layout.json`保留原异常。修复truth reader后复用全部模型，没有重训。
初次训练峰值RAM未捕获；后续23.1825909秒/137,089,024字节峰值只对应读取模型、
依赖审计和评估，不作为完整训练性能。

使用原SQL parser及ensemble.evaluate_query，对每条SQL分别实际执行point和原confidence_intervals=True，
max_variants=5、merge_indicator_exp=False、无overlapping，confidence_sample_size=39712实际保留事实行数。
13 point与13 CI均0异常；原模型CI的非有限区间和warnings保留，不能失败时删组或填0。
每条查询使用新factor cache并带SPN identity，采用独立`full_factor_cache.py`适配，原文件不改。

| 查询 | 模型组数 | 母体truth组数 | 缺少组 | 额外组 | 独立参考CI可用组 |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1.1 | 1 | 1 | 0 | 0 | 1 |
| S1.2 | 1 | 1 | 0 | 0 | 1 |
| S1.3 | 1 | 1 | 0 | 0 | 0 |
| S2.1 | 280 | 280 | 0 | 0 | 0 |
| S2.2 | 56 | 56 | 0 | 0 | 0 |
| S2.3 | 7 | 7 | 0 | 0 | 0 |
| S3.1 | 150 | 150 | 0 | 0 | 87 |
| S3.2 | 600 | 600 | 0 | 0 | 0 |
| S3.3 | 24 | 24 | 0 | 0 | 0 |
| S3.4 | 16 | 2 | 0 | 14 | 0 |
| S4.1 | 35 | 35 | 0 | 0 | 34 |
| S4.2 | 100 | 100 | 0 | 0 | 0 |
| S4.3 | 800 | 527 | 0 | 273 | 0 |

全部母体truth组有估计，但小模型存在287个额外组；保留这些误差，不将门禁称为论文精度复现。
S4.*两SUM差的原模型CI含独立性假设，回执明确标记；没有将其修改为实测正确区间。

## 同事实样本的独立整型矩与CI

自写原生消费者只读取既有sample和四张完整维表，不生成/重抽事实行。
compact维表保留查询所需uint16类别码，date用2556项map，不为199x日期key分配巨大数组。
维表PK必须唯一、customer/supplier/part必须1..N连续；inner join仅要求该条SQL真正使用的维表。
重复事实行逐行计数；NULL FK按join条件排除，SUM跳过NULL；两SUM差用行级COALESCE差构造协方差，
同时独立保存两组件非NULL计数，任何组件全NULL时参考CI排除。
S1.*的乘积单位为原SQL的extendedprice×discount整数，未擅自除100；S4.*为原收入减成本单位。

COUNT、SUM、SUMSQ用有符号128位原生整数；硬门禁样本<=20M、单贡献绝对值<=1e12，
因此平方和最大2e31小于2^127。Python/SQLite的自定义aggregate使用任意精度整数。
小输入独立SQLite执行相同13SQL的WHERE/JOIN/GROUP BY，不复用原生聚合逻辑。
SF2完整39712事实样本的13类所有组矩与SQLite严格相等；原生扫描实测0.6007814秒。
另外7行合成数据包含物理重复事实、NULL数值/FK、>2^63平方和；13条仍严格相等。
差值组5行sum=4、sumsq=132、组件非NULL数3/3，标量组6个filter行但仅5个非NULL贡献。
首次真实编译因portable GCC找不到as失败，原回执保留；仅为子进程PATH加入同目录bin后成功，
不安装全局编译器、不更改系统环境。

独立CI复用已验证的`full_flights_model.reference_ci`，输入为上述精确整数矩，
保留条件均值样本方差、母体count估算及其乘积方差，central90%，无FPC。
不足10个贡献/合格行、全NULL组件明确排除；每组保留样本count/filter_count、平方和、方差单位、
母体truth是否落入独立区间及released-reference比较。它是参考抽样CI，不是对原模型CI作真值背书。
本reference使用同一Bernoulli事实样本join完整维表；原`confidence_queries.sql`使用
TABLESAMPLE SYSTEM(16.667)。两者抽样设计不同，不能冒称逐字复现作者CI实验。

## 物理依赖、恢复与正式入口

`model_input_artifacts`逐一复算所有raw SHA、prepared binding、metadata、全部主HDF与unmatched HDF的SHA，
并验证metadata中每个HDF路径都位于目录内、都在seal清单中、磁盘HDF集合完全相同。
不能只根据metadata或seal文件自身的SHA判断可恢复。`input_guard.json`在训练前绑定实际依赖，
`model_guard.json`在训练后再核对依赖并封印全部模型/checkpoint/receipt文件。
绑定Python可执行文件与版本、平台、NumPy/Pandas/SciPy/sklearn/joblib/PyTables版本、
SPFlow RDC来源SHA和原DeepDB算法seal；查询还绑定模型及guard、13SQL、完整流truth checkpoint、
精确矩、factor cache适配与CI公式来源。每query原子结果、独立seal和按binding分目录恢复。
新增guard采用已验证的原naive矩阵/节点完全相同证据封存旧10K模型，未改模型字节。
部分表的未提交HDF依然明确停止，不能假装它是已完成的表。

正式执行顺序：

```powershell
.venv/Scripts/python.exe -B code/full_ssb_model.py formal-plan
.venv/Scripts/python.exe -B code/full_ssb_model.py formal-gate
# 仅根任务确认生成最终PASS及释放资源后执行：
.venv/Scripts/python.exe -B code/full_ssb_model.py formal-all --formal-memory-approved
```

formal-plan只写计划、审计已经完成的小门禁，不读取正在增长的SF500 sample。
formal-gate为只读门禁，生成未完成时exit2，不进行准备、训练或抽样。
formal-all由独立子进程限制BLAS/RDC线程，持OS lock防止两个正式模型任务重叠。
正式门禁要求：生成结果complete/PASS、恰好3,000,028,242事实行、4000连续已提交分片、
最终sample字节/SHA/行数与两份回执一致，实际seed/probability/source与生成计划相同；
重新独立比较流聚合的13条全部作者整数组，并核对作者truth/SQL来源SHA；四维表实际SHA/大小/行数一致。
SHA计算与实际物理记录数在同一有界二进制扫描中独立完成，正确计入没有末尾换行的最后一行，
不把JSON声明的sample_rows/维表rows当作实数；四维表数还须等于15M/1M/1.8M/2556。
任何一项失败都不能开始模型阶段。

正式sample预计约10M行，使用最终actual sample_rows，不强写10M；维表customer15M、supplier1M、part1.8M、date2556。
bounded preparation chunk=100K。每表最多1M训练，原routine的fact normalizer仍为n/p估计，
不在训练中偷偷替换为已知母体3B；母体精确truth仅供评估/独立reference。
只为小门禁运行SQLite，正式10M的精确矩使用已对SQLite验证过的流式原生消费者。
准备/训练/评估产物均写`output/full/ssb/models/sf500_<binding>/`，正式摘要才写
`output/full/results/ssb_model_aqp_ci.json`；不会覆写生成器`ssb_paper.json`或任何历史1M结果。

计划预算：额外准备/模型4.5GiB（主HDF约2.3GB、unmatched<=0.9GB、count/mean约0.5GB及索引/模型余量），
总SSB仍需<=10GiB；启动前至少6GiB空闲磁盘、4GiB available RAM并显式要求根任务释放资源。
准备峰值估计<=1.5GiB，原numeric HDF及post_sampling训练峰值暂按4GiB规划，native维表约110MiB。
训练仍保留原`pd.read_hdf`及post_sampling行为，未声称完全流式训练；正式耗时/内存尚未实测。
已实测的10K/39712行时间不能线性保证1M/10M表现。

## 验证与证据

`pytest code/tests/test_full_ssb_model.py -q -k "not sealed_sf2_actual_original_preparation_golden"`：
10 passed、1 deselected（53.25秒）。被排除的旧SF2 preparation test此前已通过，遵照不重复已完成工作的要求不再运行。
本轮先运行4个新增guard/正式gate测试得到4 failed，再实现后4 passed；
实际破坏unmatched HDF末尾但保持metadata/seal不动时必须被拒绝，
未完成生成、author mismatch、未释放内存均在样本读取/训练前拒绝。
随后新增final physical-row/hash测试先1 failed、1 passed，再实现有界计数器；
最终相关7测试通过（12.17秒），包括计划seal被篡改时在memory/data访问前拒绝。
这些更新没有改变准备AST、原训练循环或10K模型。

## 独立review后的强制外层发布屏障

正式入口现仅通过`full_ssb_guard.py`的PREPARED、MODEL、EVALUATION与整个FORMAL事务。
每个namespace先持久写RUNNING，最终raw/HDF/模型/依赖/查询身份全部复核后才写外层PASS receipt；
任何异常写TAINTED。残留RUNNING也转TAINTED，恢复原raw或发现原核心已写seal/model.json都不能自动洗白。
原核心seal是临时内部产物，单独存在不得消费；整个FORMAL最终PASS前不发布正式verification或results摘要。
guard状态与receipt位于工件目录旁的独立目录，名字绑定guard源码SHA，不进入原模型文件清单。
变化的guard代码/依赖使用独立namespace，旧TAINTED证据保留；没有自动copy/resume已污染目录的逻辑。

新完整依赖包含原六个算法目录所有Python源、`evaluation/utils.py`、full_factor_cache、CI公式、
完整SPFlow Python包源及完整sqlparse Python包源；同时绑定Python及numpy/pandas/scipy/sklearn/
joblib/tables/spflow/sqlparse/networkx包版本。不能只封RDC单文件或parser包版本。
每个query现在还必须匹配filename对应index、query_name、逐字SQL、全局binding及物理result/seal SHA；
完整集合必须恰好13、无额外/重复/缺少。复制query00整对JSON/seal到query01会明确失败。
外层receipt封存13个逐条身份，不只记录共同的global binding。

已正确的tiny准备/五模型/13query采用后验审计封印，完整依赖摘要硬pin为
`9bc2cfeed87f68563038436e480aa769f258712d0cb45d7ce7d140a0756f54de`。
采用必须核对先前原routine metadata/HDF exact和原naive训练矩阵/节点exact证据、模型物理SHA与13正确身份。
测试把全部prepare/train/evaluate入口替换为报错函数，采用仍通过；不重新准备、训练或推断。
后续依赖变化不能自动重新采用，必须独立审查。

SF500 orderkey的max×sample_rows约3e16，原有2^53整数保护会拒绝，不能简单放宽后保留Python精确除法。
实际读取本环境pandas1.0.3 `nanops.nanmean`：整数输入明确设dtype_sum=np.float64，
而非int64精确求和后Python除法。实际三值oracle `[2**53,1,0]`：
原pandas mean为3002399751580330.5，Python精确整数sum/3为3002399751580331.0。
独立适配只替换原profile拒绝分支：原行序int64写有界memmap，再调用相同`pd.Series(...).mean()`；
<=2^53的旧路径保持。动态替换要求原拒绝分支源文本恰好匹配一次，否则停止；原磁盘函数和准备AST不改。
三行大整数表的metadata及HDF已与实际原prepare_all_tables严格相同，未生成大表。
正式约10M的orderkey replay额外磁盘约80MB，包含在既定4.5GiB准备/模型预算内。

新外层测试`pytest code/tests/test_full_ssb_guard.py -q`：6项先失败，再实现后6通过；
加禁止重算的tiny采用回归后7 passed（28.39秒）。当前guard证据见
`sf2_outer_guard_verification.json`及其seal、三阶段外层lifecycle/receipt。
随后review补充两条边界：没有outer state时已有旧query cache也必须拒绝，
`require_model_pass`还要核验全部core非pickle receipt、精确清单及其内容，而不只核模型pkl。
两项新回归先失败（包括真实DID NOT RAISE），修复后全9 passed（25.65秒）。
reviewer只读轻测又分别确认两项通过，未重跑原SF2生成/训练/13推断。
大整数来源及真实float结果另存`large_integer_reduction_probe.json`。

最终成功只读复核入口：

```powershell
.venv/Scripts/python.exe -B code/full_ssb_guard.py verify-small
```

返回`PASS_CURRENT_COMPLETE_DEPENDENCIES`、13身份、原模型SHA及完整依赖摘要。
此入口成功时不写任何文件，不调用prepare/train/evaluate；新版`formal-plan`先验证这些外层receipt后再封正式计划。

主要证据：`sf2_small_model_gate_latest.json`、对应目录`small_model_gate.seal.json`、
`checkpointed/model_guard.json`、按binding命名的evaluation目录13对query/seal、
`sf2_sample_moments_native/seal.json`、`sf2_moments_reference.sqlite.seal.json`、
`formal_plan.json`及其seal、`formal_generation_gate.json`，全部位于`output/full/ssb/models/`。
准备AST维持`20046e789fafdc04cd4ccba958ef8d4b4a3902ac1b10ece120072a3890372df0`；
10K ensemble SHA维持`cfadb3ecb8100544ae91d0f14d03d559982ff48489d7de590eb9e051943b56f6`。
