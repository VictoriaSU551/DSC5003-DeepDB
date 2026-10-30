# AQP 原基线来源与可执行边界

> 本文保留来源调查时的静态边界。随后原DBEst小输入门禁及实际1B Flights上的20K拟合已执行，
> 当前实验结果见[FULL_DBEST_PROTOCOL.md](FULL_DBEST_PROTOCOL.md)、
> [FULL_DBEST_FLIGHTS.md](FULL_DBEST_FLIGHTS.md)和[独立审计](FULL_DBEST_FLIGHTS_AUDIT.md)。
> 原Verdict的实际已有Flights样本执行也已完成，见[FULL_VERDICT_PROTOCOL.md](FULL_VERDICT_PROTOCOL.md)；
> 原始错误、两SUM适配、95%CI与sample-only范围分别保留。
> 下文“尚未执行”描述调查当时，不代表这些后来已封存阶段仍未开始。

## 当前本机的 SSB 全表数据库空间界限

2026-10-31按固定公开schema和13条SSB SQL重新计算：lineorder含2个BIGINT和12个INTEGER，
数值载荷已有64字节/行。PostgreSQL11的INTEGER/BIGINT分别占4/8字节，见
[官方类型存储表](https://www.postgresql.org/docs/11/datatype-numeric.html)。
目标3,000,028,242行仅这些数值就需192,001,807,488字节；甚至只投影13条查询真正使用的
9个INTEGER，也需108,001,016,712字节。当前C盘空余101,268,606,976字节，已经不足，
且上述下界尚未计入heap行头、行指针、对齐、文本、维表、索引、WAL或临时空间。

修正后SF2实际保留全字段门禁的原始文本为1,196,848,919字节/11,997,996行；按相同每行字节外推
SF500约299.3GB。这只是原始文本外推，不是SF500实际dump或PostgreSQL空间实测。
原始证据和逐列计算保存在`output/full/results/ssb_full_database_resource_bound_20261031.json`。
因此当前机器无法直接建立原规模的普通PostgreSQL全表来运行TABLESAMPLE、原表建样本及完整join索引基线。
流式truth和保留样本仍可用于RSPN/CI及明确标注的sample-only方法；它们不提供原全表采样/建索引的端到端时间。
本结论针对公开schema和当前磁盘，不声称所有压缩或其他数据库实现都不可能。

## 以下为来源调查时的记录

本次只获取、封印和审计原作者来源，没有安装依赖、训练模型或运行任何基线。
论文作者历史CSV不是本地基线结果。正在运行的Flights/SSB生成器及协议绑定均未修改。
结论是：**原DBEst值得先做隔离的小输入接口验证；其余方法目前不能直接把已保留样本与truth当作原规模端到端基线。**

## 论文究竟比较了什么

DeepDB第6.2节使用Flights 1B、SSB SF500。Flights的VerdictDB事实样本为1%；
SSB的VerdictDB与Postgres TABLESAMPLE通过样本量校准到平均约2秒，
Wander Join显式时间预算2秒，仅用于含join的数据，并建立join及谓词二级索引。
DeepDB本身训练样本为Flights 10M、SSB 1M。
第12、13图的DBEst与wavelets另允许查询先验，不能与无先验配置混合。
出处为[原论文](https://www.vldb.org/pvldb/vol13/p992-hilprecht.pdf)第6.2节；
本地定位`output/full/paper/deepdb_raw.txt:1340`、`1661`。

论文中DBEst引用[24]和[25]是同一SIGMOD’19工作，正确作者论文DOI为
`10.1145/3299869.3324958`，见[Warwick作者存档](https://wrap.warwick.ac.uk/id/eprint/115961/)。
Wavelets[5]应区分VLDB’2000会议版与VLDB Journal 10(2–3):199–223的2001扩展版；
作者[正式条目](https://minosng.github.io/Abstracts/vldbj01-abs.html)提供这一区分。

## 已固定并完整校验的官方源码

完整ZIP只在`data/downloads/baselines/`，没有新增公开vendor副本。
每个ZIP的每个文件都与固定提交的官方递归Git tree核对Git blob SHA1及长度，
再封存归档SHA256、许可证原字节SHA256与审计证据文件。

| 方法/角色 | 原作者仓库与固定提交 | 官方分支/代码版本 | 原字节文件数 | ZIP字节 |
|---|---|---|---:|---:|
| 原DBEst主要候选 | [qingzma/DBEstPy](https://github.com/qingzma/DBEstPy/tree/2220a937b5eef358eb42a715da328915048b7250) `2220a937b5eef358eb42a715da328915048b7250` | v2.0分支；setup.py自报2.1 | 299 | 522,913 |
| 原DBEst命令行候选 | [qingzma/DBEstClient](https://github.com/qingzma/DBEstClient/tree/684cc9f5b84e751c7eeb7836e9d21c90638563b4) `684cc9f5b84e751c7eeb7836e9d21c90638563b4` | master，2019-12-10；自报1.2 | 27 | 24,141 |
| Verdict原SIGMOD方法 | [verdict-project/verdict](https://github.com/verdict-project/verdict/tree/b59209f626d278687ea0a801295b41064c7fecbb) `b59209f626d278687ea0a801295b41064c7fecbb` | sigmod18；pom 0.4.7 | 400 | 662,121 |
| Wander Join / XDB | [InitialDLab/XDB](https://github.com/InitialDLab/XDB/tree/8e9dc8c35b0792c01fe477232a0837a9eb70d32c) `8e9dc8c35b0792c01fe477232a0837a9eb70d32c` | sigmod16_stable，PG9.4.2分支 | 4,319 | 22,503,488 |
| DBEstClient的后续依赖候选 | [qingzma/qreg](https://github.com/qingzma/qreg/tree/50b5963f027beb747eac99080ae77ac11e7c6716) `50b5963f027beb747eac99080ae77ac11e7c6716` | master，2020；不是2019环境锁 | 52 | 267,178 |

共**5,097个Git blob**完整通过。当前来源目录约26.5MB；没有因源码取得进行大型安装。
归档SHA256及每个证据的原路径/固定URL都在`output/full/results/baseline_sources.json`，
证据用短文件名落地，避免Windows长路径；该JSON索引保留准确的源码行号对应关系。

DBEstPy、DBEstClient该固定版本的实际LICENSE正文均为BSD二条款形式，
即使setup分类器写MIT，也以[实际许可证文件](https://github.com/qingzma/DBEstPy/blob/2220a937b5eef358eb42a715da328915048b7250/LICENSE)为证据，不擅改标签。
Verdict保留Apache-2.0与3RDPARTY_LICENSE；QReg为Apache-2.0。
XDB保留COPYRIGHT与postgresql.COPYRIGHT：实际
[COPYRIGHT](https://github.com/InitialDLab/XDB/blob/8e9dc8c35b0792c01fe477232a0837a9eb70d32c/COPYRIGHT)
含用途不限的使用/修改/分发许可文字，而README另有non-commercial措辞；两者差异原样记录，
本项目仅作个人学术复现，没有重新发布XDB副本。

这些是**能合法取得并固定的官方实现候选**，没有证据证明其中某个提交就是DeepDB作者实际运行的未公开快照。

## DBEst：可以先推进小型接口验证，仍需明确输入协议

[原论文作者博士论文](https://wrap.warwick.ac.uk/id/eprint/162529/1/WRAP_Theses_Ma_2021.pdf)
第4.3节直接指向DBEstPy。该版本采用回归加KDE、数值积分，符合SIGMOD’19原方法，
不能用DBEst++的MDN/embedding实现替换原第12图积分行为。

直接可用的接口证据来自
[dbest/dbestclient.py](https://github.com/qingzma/DBEstPy/blob/2220a937b5eef358eb42a715da328915048b7250/dbest/dbestclient.py#L150)：
`add_pair_client(file, table_name, columnPair, num_of_points, ...)`在第165行读取给定CSV，
第185–187行把显式母体数量传给QueryEngine。
`init_groupby`第396–477行另要求`num_of_points_per_group`。
因此数学上可以使用有界均匀样本和正确母体倍率，不要求推理阶段保留整张原表；
但尚没有完成我们的Flights/SSB输入适配或任何本地预测。

需要解决的具体输入差异：

1. DeepDB实际上公开了**12条Flights、13条SSB预过滤/物化SQL**，不是DBEst实现。
   本次从固定原Git对象逐字节取得并封存：
   [Flights资源](https://github.com/DataManagementLab/deepdb-public/blob/655ada13a043a4226a239b0c0a65bcdefef87a02/baselines/aqp/resources/dbest_flights_aqp_queries.sql)、
   [SSB资源](https://github.com/DataManagementLab/deepdb-public/blob/655ada13a043a4226a239b0c0a65bcdefef87a02/baselines/aqp/resources/dbest_ssb_aqp_queries.sql)。
   Flights资源先按类别条件过滤；SSB资源先做FK join和类别过滤，再保留数值条件供模型处理。
   这些预先知道的条件必须写进模型输入绑定。
2. Flights保留的均匀样本可用相同类别过滤并投影；SSB保留完整维表，能够把抽中的事实行FK join到维表。
   这可产生“原母体的过滤子集样本”，但是每个子集/组的精确母体数量并不由全局p自动变成已知常数。
3. 原DBEst的GROUP BY API需要母体组数目。当前stream truth保存的是被评估查询的结果，
   不是任意预过滤后的完整分组大小表。不得默默把评估目标COUNT/SUM用作训练元信息。
   若使用已知先验组数、或用`n_group/p`估计组数，须分别声明来源、统计误差与信息预算。
4. CSV需按原API提供表头、逗号分隔、数值列及缺失值处理；SSB原pipe文件不能直接当默认CSV读。
   F5.1的`arr_delay*dep_delay`和F5.2的两个SUM之差也需要明确投影/组合路径。
5. 12/13查询的全流truth只用于同一生成母体的误差评价；不能把新seed的样本与作者历史truth交叉使用。

**旧CLI不等于现成样本入口。**
[2019 sampling.py:14–25](https://github.com/qingzma/DBEstClient/blob/684cc9f5b84e751c7eeb7836e9d21c90638563b4/dbestclient/io/sampling.py#L14)
只实现整数SIZE的reservoir扫描，概率输入明确未实现；
[executor.py:103–138](https://github.com/qingzma/DBEstClient/blob/684cc9f5b84e751c7eeb7836e9d21c90638563b4/dbestclient/executor/executor.py#L103)
从CSV计算母体/组数。如果把已保留的样本当原表，COUNT/SUM尺度就错了。
不能照抄新DBEst++文档里`SIZE 0.01`的样本输入语法到旧1.2版本。

还核验了[官方PyPI](https://pypi.org/project/dbestclient/3.0/)：当前发布元数据的latest为3.0（2021-03-17），
不是原1.2。实际下载原1.2 wheel并匹配PyPI SHA256后发现，它只有3,387字节，
包含`dbestclient/main.py`及dist-info，却没有`cli/prompt.py`或`executor/queryengine.py`。
这解释了为何不能把`pip install dbestclient==1.2`成功当作原执行器已取得；
需要使用本次封存的完整Git源码并独立验证加载路径。本次只检查wheel ZIP，没有安装或导入它。

还有两个**静态代码风险，尚未执行验证**：

- [QueryEngine:63–64](https://github.com/qingzma/DBEstPy/blob/2220a937b5eef358eb42a715da328915048b7250/dbest/query_engine.py#L63)
  对多列NumPy行数组使用Python min/max；多维输入可能在构造阶段失败。
- 同文件第83行删除`self.training_data`，多维SUM/COUNT分支第224、318行却继续读取它。
  第196、242、335行采用`scipy.integrate.nquad`。原第12图的1/2/3个数值过滤属性，
  必须先以小二维/三维差分测试查明原实现路径，不能因有nquad就报告原图可直接跑通。

积分容差也未被DeepDB公开锁定：DBEstPy该文件默认`epsabs=10, epsrel=0.1`，
全局nquad opts的limit为100，而dbestclient.py又定义另一组调用默认值。
未来需同时封存实际传入值和多维分支真正采用的opts，不能只记录谓词数量。

本机已有Python3.8.20、NumPy1.19.5、pandas1.0.3、SciPy1.4.1、sklearn0.22.2和matplotlib3.2.1；
缺xgboost、qregpy、pwlf、pyhs2。DBEstPy的requirements/setup没有完整版本锁且两处依赖集合不同。
推荐下一步仅在独立环境封存原代码，验证1K行一维COUNT/SUM/AVG及二维失败证据，
再审查最小兼容修复；本次没有安装或修复它们。
以10M行两个float64数值列为例，原始数组就需160MB，DataFrame/训练副本/模型另计；
每组、每列组合模型会增加内存。多维积分运行时只能实测并记录TIMEOUT，不能从第12图历史时间推算本机表现。

## VerdictDB：原方法和当前发布要分开

官方README明确把SIGMOD’18变分采样实现指向`sigmod18`分支。
该固定分支root pom为0.4.7，SQL为`CREATE ... SAMPLE`；
当前master `48533d410cbbc91dc2ce41506edde9e04004c6b8`的pom则为**0.5.10-SNAPSHOT**，使用scramble。
另外，本次[官方Maven元数据](https://repo.maven.apache.org/maven2/org/verdictdb/verdictdb-core/maven-metadata.xml)
的最新正式发布为**0.5.8**，不能把master快照称为最新正式release。

旧版实际语法可由
[grammar](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/antlr4/edu/umich/verdict/parser/VerdictSQL.g4#L64)
和[SampleParam:121](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/datatypes/SampleParam.java#L121)核对：

```sql
create 1% uniform sample of flights;
create 1% stratified sample of flights on origin;
```

这是未来接入原表时的示例，未执行；默认自动策略还可建立uniform/universe/stratified样本。
[CreateSampleQuery:45、67–76、119–157](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/query/CreateSampleQuery.java#L45)
的默认样本量依据约2GB启发式，并不是固定1%。
因此论文Flights的有效1%应显式控制，不能用当前源码默认值冒充原论文配置。
当前[SCRAMBLE文档](https://docs.verdictdb.org/reference/scrambling/)又规定RATIO默认1.0、方法UNIFORM/HASH，
它与旧分层样本策略也不能混写。

原分支有PostgreSQL适配器，但标准创建入口仍读取原表：
[DbmsPostgreSQL:110–119](https://github.com/verdict-project/verdict/blob/b59209f626d278687ea0a801295b41064c7fecbb/core/src/main/java/edu/umich/verdict/dbms/DbmsPostgreSQL.java#L110)
查询原表COUNT并生成概率列；分层路径需要组大小和原表join。
仅有我们保留的普通CSV样本和13/12个truth结果，不等于已有Verdict sample表、概率列、分区和catalog元数据。

可研究官方`Meta.insertSampleInfo`等元数据接口，导入预先抽好的uniform样本并显式注册真实倍率；
这可能允许独立测量已有样本上的查询，但需要新适配、概率/分区验证及信息预算，**尚未实现或证实可运行**。
它也不能还原论文所报告的原表建样本成本、完整分层样本或原规模端到端延迟。
把样本作为一张小“原表”再CREATE SAMPLE，只会得到该小表的答案。

官方构建路线是固定源码后`mvn package`；旧pom目标Java1.7并有HTTP依赖仓库，
本机PATH没有java/javac/mvn，未验证依赖解析和PG11.5兼容性。
本次没有下载JAR依赖或搭建Java环境。对于SSB，在当前不保留全量事实母体的设计下应先暂缓原规模Verdict标准建样本流程。

## Wander Join / XDB：完整索引母体是硬输入

[作者项目页](https://initialdlab.github.io/XDB/)明确把
[SIGMOD’16方法](https://www.cse.ust.hk/~yike/sigmod16.pdf)连接到XDB。
这是修改PostgreSQL 9.4.2的完整源码，不能安装成现有PG11.5扩展。
正式实验须新建独立cluster，不能复用或覆盖当前`deepdb_job`。

官方操作形态：先按原INSTALL构建专用数据库，导入完整关系，建立join/谓词索引，再执行：

```sql
SELECT ONLINE sum(lo_revenue)
FROM lineorder, dwdate
WHERE lo_orderdate=d_datekey
WITHTIME 2000 CONFIDENCE 95 REPORTINTERVAL 2000;
```

该示例仅演示原语法/毫秒单位，未宣称已覆盖SSB13条SQL。
原[README](https://github.com/InitialDLab/XDB/blob/8e9dc8c35b0792c01fe477232a0837a9eb70d32c/README.md)
还提供`SCAN table_or_index`预热；Wander Join有随机I/O，是否预热显著影响结果。
官方示例query3/7/10使用60–240秒，复现DeepDB须明确改为2000ms，并另计完整SQL墙钟时间。

还有确定的模式门槛：
[planonline.c:820、1534–1554](https://github.com/InitialDLab/XDB/blob/8e9dc8c35b0792c01fe477232a0837a9eb70d32c/src/backend/optimizer/plan/planonline.c#L1534)
要求primary index，找不到时报错。我们的原SSB schema没有声明lineorder主键；
应先核验生成键的唯一性并明确主键/行标识协议，不能仅因事实文件存在就认为XDB可执行。
官方另有`no_pkey_requirement`分支，但本任务未核验其功能或把它替代SIGMOD’16固定版本。

完整母体与索引不能用10M事实样本替代。即使额外乘抽样倍率，得到的也是两阶段抽样的新配置，
不是原规模随机游走的I/O、拒绝率或2秒精度。
按本项目标准SSB schema，仅12个int4加2个int8数值列就有**64字节/事实行**，
3,000,028,242行对应**192,001,807,488字节**，尚未包括其他列、行/页头、维表或任何索引。
这已超过审计时约133GB空闲空间，也远超10GB流式预算。
原CSV按SF2原字节量线性估计约291GB；不能误把当前几GB样本存储成本写成原规模数据库成本。

当前portable GCC/make/sh存在，缺Perl/Flex/Bison；固定Git树确实有gram.y/scan.l而没有生成的gram.c/scan.c。
PG9.4[官方构建要求](https://www.postgresql.org/docs/9.4/install-requirements.html)
要求Git树构建配备Flex/Bison，Windows也需要Perl。
因而仅有我们已装的MinGW不能视为工具链已齐备。本次没有编译XDB、安装额外工具或导入数据库。

## Wavelets：原论文可得，原执行器未定位

已经核对[VLDB会议原文](https://www.vldb.org/conf/2000/P111.pdf)、
[作者期刊条目](https://minosng.github.io/Abstracts/vldbj01-abs.html)、
[Microsoft Research作者发布页](https://www.microsoft.com/en-us/research/publication/approximate-query-processing-using-wavelets-3/)
和DeepDB固定tree。上述范围只发现论文及历史结果，没有定位到可固定、许可清楚的原执行器。
这是一项有范围的缺口，不声称全球不存在源码。

所需的是非标准多维Haar关系摘要、规范化系数截断，以及直接在系数上执行select/join/aggregate的关系代数。
普通PyWavelets变换函数不能直接代替。还需恢复类别域编码、数值离散网格、系数预算、
每表或每查询摘要构造策略和join语义。第13图使用先验列组合建立逐查询最小维摘要；
第12图改变维数，不能拿一个低维通用DWT结果替代。
原方法可通过ROLAP/chunk方式构造而无需稠密展开整个笛卡尔域，但完整源码缺失时，
其实际内存/临时空间与耗时不能可信量化；若从我们的均匀样本构造，还须声明抽样误差与倍率。
下一步可以继续寻找作者原实现；若新实现，必须明确标为独立实现并先验证关系代数，不能称原代码重跑。

## 已运行的来源审计命令与下一步

```powershell
.venv/Scripts/python.exe code/full_baseline_sources.py self-test
.venv/Scripts/python.exe code/full_baseline_sources.py fetch
.venv/Scripts/python.exe code/full_baseline_sources.py audit
```

self-test最初因缺少验证实现而失败，加入实现后3个真实归档检查通过：正常原字节、篡改内容拒绝、路径穿越拒绝。
fetch取得并校验5个固定源码ZIP、两个当前官方快照的指定文件、PyPI/Maven官方发布元数据及DeepDB的25条预过滤SQL。
audit离线重算每个Git blob和封印；结果状态为`SOURCE_AUDIT_ONLY_NO_BASELINE_EXECUTED`。
动态发布元数据只代表此次取证快照，不承诺将来latest不变。

建议先推进**原DBEst的一维小输入隔离验证**，随后审核多维失败与最小兼容路径；
Verdict的已有样本导入应作为单独适配研究，不能抢先写论文结果；
XDB在缺完整索引母体/磁盘/构建工具时暂缓原规模执行；wavelets继续保留实现缺口。
本次没有改原实验代码、当前SSB入口、任何已有协议绑定，也没有commit/push。
