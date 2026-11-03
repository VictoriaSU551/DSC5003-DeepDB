# SSB 有界分片、精确聚合与抽样

本阶段只验证完整SF1金标准及可恢复输出消费，不启动SF500。
SF1通过不是原规模论文实验完成；未来SF500仍须核对**3,000,028,242条事实行**及
作者发布的13条查询全部结果分组，才能讨论作者母体是否被恢复。

## 来源与许可证记录

首先尝试 `https://www.cs.umb.edu/~poneil/dbgen.zip`。正常TLS验证报
`CERTIFICATE_VERIFY_FAILED: self signed certificate in certificate chain`，未关闭验证。
错误原文保存在 `output/full/ssb/author_source_probe.json`。
因此使用指定镜像：

<https://github.com/electrum/ssb-dbgen/tree/219403ad7d1dd32ae1f97b5553abf92129fccd7f>

固定归档保留在 `data/downloads/`；34个原文件按原字节放在 `code/vendor/ssb_dbgen/`，
归档和逐文件摘要见 `SOURCES.json`。未证明这是DeepDB作者的精确生成器版本。
镜像固定树没有LICENSE/COPYING；程序报告TPC 1994--2000版权。
保留原README、TPCH_README和全部源码头，不臆定MIT授权；见 `LICENSE_NOTICE.md`。

原源码没有任何补丁。`full_consumer.cpp`是新增的独立输出消费器，
只读取已经产生的文本分片；不调用、替换或推进其随机流。
`full_chunk_driver.c`是独立恢复适配入口，调用原版日期生成和skip-ahead函数，
再调用原版gen_tbl生成指定连续订单段；严格字节比对通过后才接纳该适配。
`dss.h:L_PKEY_MAX`的自然log与`driver.c`生成part表时的log2差异原样保留。
SF500下二者对应的事实外键上限和part维表规模不同，不能静默“修正”。

## 便携编译

复用项目 `.runtime/w64devkit` GCC14.2，不安装全局组件。
原C源码一次一个编译进程，采用SSBM/DB2及WIN32的既有分支；
WIN32配置启用原有64位DSS_HUGE和打印格式，避免SF500订单键的32位溢出。
适配入口直接指定一段订单，始终只运行一个原生成器进程，不触发自动多进程。
实际参数、警告和退出码在 `output/full/ssb/build/compile_original.json`。
旧C代码的gets与整数/指针转换编译警告保留，不通过改随机算法消除。

原生成器和新增C++17消费器都有SHA256构建绑定；每次重用检查原始34文件、
消费器源码、编译器和两个可执行文件。任一原文件被修改即拒绝构建。

## 执行路径

```powershell
.venv/Scripts/python.exe -m pytest code/tests/test_full_ssb_generate.py -q
.venv/Scripts/python.exe code/full_ssb_generate.py build
.venv/Scripts/python.exe code/full_ssb_generate.py sf1 --shards 8
.venv/Scripts/python.exe code/full_ssb_generate.py plan
```

数据只在 `data/ssb/`，日志、分片回执、检查点在 `output/full/ssb/`，
总体回执为 `output/full/results/ssb_sources.json`。
不连接PostgreSQL，不接触deepdb_job的六张表及其导入/真值回执。

SF1先用未经修改的原生成器`-s 1 -T a`产生完整金标准，保留四维表与完整lineorder。
将全部数据导入独立SQLite，执行仓库的原13条SQL，整数SUM与分组键原样保留，
禁止用浮点数保存大整数聚合。
SQLite仅用于SF1独立核验，不作为SF500全量数据库方案。

初始实测发现，原版`-T l -C/-S`与`-T a`的第1条事实就不同：
DATE=4与ORDER=4共享编号，完整生成日期时会推进ORDER随机流；
而原sd_line的共享种子跳过也没有涵盖O_CKEY/O_PRIO等所有订单流。
失败的首条差异及摘要保存在 `upstream_chunk_mismatch.json`，回归测试先失败再修。
DOS编译分支另有-C解析被禁用的问题；未为此修改原driver.c。

因此实际分片采用新增适配入口：先调用原版`-T d`复现完整日期前缀，
再用原sd_order和sd_line分别跳过完整订单段，调用原gen_tbl产生目标段。
既不换随机算法/种子，也不改事实构造、分布或行边界补齐规则。
这项恢复适配必须与原版完整-T a的**全部SF1事实字节**严格相同，才算通过。
默认8片，每次只保留一个有界临时分片。
每片与SF1完整原文件对应字节区间进行SHA256比较；最后要求完整字节长度和实际行数均被覆盖。
这验证了本适配在固定版本、本编译设置下不重不漏且顺序相同，
不把存在缺陷的原版-C/-S直接记为已验证。
未来不同SF和分片数仍须记录配置，不能仅凭SF1成功断言作者SF500版本相同。

常驻C++消费器只加载一次维表，逐条检查所有主外键，执行13项原查询对应的
整数过滤、SUM/GROUP BY。处理每片后输出聚合TSV、样本和实际行数；
Python只合并少量整数分组状态，不逐行承担未来3B事实的查询计算。

## 独立抽样与恢复

抽样用SplitMix64风格的无状态hash：固定sampling_seed与(orderkey,linenumber)决定是否保留，
不会消耗生成器随机数。概率固定为`.003333`，未来3,000,028,242行预期约9,999,094行；
这是约10M的Bernoulli样本，不声称恰为10M或恢复作者未指定的awk抽样种子。
样本写17列、无末尾管道、LF换行的`lineorder_sampled.csv`，不丢弃任何母体行的聚合贡献。

每片事务顺序：原分片生成/比对→原生聚合与抽样→样本追加并fsync→整数聚合状态更新→
原子检查点替换→删除该已封存临时分片。
检查点绑定源文件/二进制/维表/查询/scale/分片数/抽样种子与概率及runner摘要。
恢复先拒绝绑定变化，校验已提交sample前缀摘要，按已提交字节偏移截去额外尾部，
再核对各已提交分片保留产物；不得重新生成这些分片。
若恰在检查点提交后、原分片删除前中断，恢复会核对该剩余原分片的摘要后仅清理它，
不会重放已提交片；未提交分片不按已完成片清理。

SF1验证故意在已提交前缀后写入未提交尾部，然后恢复；要求恢复后的样本与
完整金标准一次连续消费的样本SHA完全相同，且已提交分片回执保持不变。
13项分片合并结果与连续原生结果都须和独立SQLite的13项整数分组结果完全一致。

## SF500门禁与资源边界

`require_generation_gate`当前只允许SF1；`plan`纯输出配置，不执行生成。
未来候选可用约4000片，使单片约75万事实行、约100MB文本；
只留四维表、约10M样本、聚合/检查点与一个临时分片，目标新增磁盘低于10GB。
行宽和维表空间必须在放行前用本版本实测预算，不依靠本次估计保证空间。

原版生成器的随机流种子固定在rnd.h，`-S`是分片编号而非随机种子。
必须保留分片数、SF、编译标志、rnd.h与dists.dss摘要。
未来放行还需要将SF1金标准绑定逻辑扩展为原规模维表生成/原规模完成门禁，
并逐分组对比作者 `ground_truth_500GB.pkl`；目前不把该工作记为已完成。
即使将来生成器完整遍历3B行，仍不能由本方案获得VerdictDB/XDB/TABLESAMPLE的
原规模数据库延迟，它们另需完整存储和实现。

## 验证记录

测试先运行，缺少实现时7项失败；随后补充提交后删除前中断及真正分片字节回归，
相应测试均先观察失败，再实施修复。
覆盖已提交偏移后的尾部截断、输入/种子变化先拒绝、短文件/前缀损坏先拒绝、
超过2^53的整数聚合精确保留、SF500门禁拒绝、提交后的剩余原分片清理与损坏拒绝、
实际生成的1/64段与原完整文件对应字节相同。
实际SF1全量校验结果与各项检查，以 `ssb_sources.json` 和独立SQL回执为准。
没有commit/push，没有启动SF500生成或模型训练。

### 本次实测

`SF1_STREAMING_VALIDATED_ONLY`回执为PASS。完整原版SF1事实表实际**6,001,171行**；
四维表为customer30,000、part200,000、supplier2,000、date2,556行。
SQLite原13条SQL共得到1584个结果分组，全部与连续C++及8片合并整数结果精确一致。
8片覆盖完整原始文件的每个字节，事实行数合计一致，最大单片72,349,291字节。

固定seed=20261030、p=.003333抽得**19,731行**SF1样本；
在第2片后追加未提交尾部再恢复，最终样本与完整文件连续消费的SHA256相同，
已提交分片被保留。恢复、前缀、源文件、所有分片产物及独立SQLite数据库摘要再核验通过。
本任务数据/源码/SSB输出合计约**1.059GB**，未触及10GB预算。

任务测试10项实测通过。全项目测试先因另一并行任务尚缺
`full_paper_budget`模块而收集失败；其模块完成后重新执行，
结果为90通过、2项因缺少torch跳过、1条既有pandas合并警告。
昂贵的完整SF1生成和SQLite真值保留并按输入摘要复用，没有因分片适配调试重复计算。
