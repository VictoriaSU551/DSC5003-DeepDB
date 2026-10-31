# 完整阶段的运行入口

所有命令从项目根目录的 PowerShell 执行。已有检查点时先查看状态，不要重建环境、
重新下载同一数据或重训已验证模型。数据和模型不随公开仓库分发。

## 协作与环境

公开仓库的完整阶段在 `reproduction/full-paper` 分支。组员可克隆这个分支，
在自己的功能分支提交 PR；不要把大数据、模型、环境、PDF或私人文件加入 Git。
阶段协作入口为[草稿PR #3](https://github.com/VictoriaSU551/DSC5003-DeepDB/pull/3)，
原`main`仍保留第一阶段；完整阶段尚未合并。PR明确列出已验证范围和未完成缺口。

新机器先运行 `setup.ps1` 建主环境。官方和重建 MSCN 使用独立的
`setup-mscn.ps1`：10个Windows/Python3.8 wheel的URL、大小和SHA256固定在
`docs/manifests/mscn-windows-py38-wheels.json`。已有匹配环境仅检查版本，不安装或修改包。
该锁来自本次本地兼容环境，不是作者的原Python3.7/PyTorch1.0环境。
2026-10-31已在本机的干净源码副本新建主环境、验证算法导入/HDF读写，并新建MSCN环境、
重新取得官方100K/70配套输入，27项MSCN语义检查通过；没有重训正式模型。
主安装器随后增加`--no-bin --no-registry`，其私有Python安装已在空目录另验，
MSCN新安装使用了这两个开关。Python文件留在项目`.runtime`，不新增全局命令或注册表登记。
测试过的uv版本为0.9.11；这是当前Windows主机的安装验证，不是另一台机器或全新操作系统的验证。
本地核验记录在`output/full/bootstrap_verification/`，2.87GB逻辑大小的临时副本和CLI归档已移出项目。

```powershell
# MSCN源码和100K/70配套位图；存在的文件只核验，不覆盖
.venv/Scripts/python.exe code/full_mscn_sources.py

# 仅新机器安装；已有正确环境直接返回
powershell -ExecutionPolicy Bypass -File setup-mscn.ps1
```

`full_mscn_sources.py --offline` 可只核验本地固定归档和所有解出的原字节。
主数据下载入口仍为 `code/download_data.py`；其余来源与数据生成见相应协议。

## 接续与验收

```powershell
.venv/Scripts/python.exe code/full_status.py

# 基线按组提交；逆序重放按完整模型提交，在四个新进程中验证
.venv/Scripts/python.exe code/full_evaluation_v3_run.py --all
.venv/Scripts/python.exe code/full_canonical_acceptance.py

# 严格只读native验收；缺少既有最终工件时失败，不补跑推断或编译
.venv/Scripts/python.exe code/full_cpp_v3_audit.py

# 验收通过后，只读现有预测生成表图和local真值指标
.venv/Scripts/python.exe code/full_paper_tables.py
.venv/Scripts/python.exe code/full_local_truth_eval_v3.py

# Flights正式AQP/CI结果与部分DBEst对照的只读表图
.venv/Scripts/python.exe code/full_flights_replay_audit.py verify
.venv/Scripts/python.exe code/full_aqp_tables.py
.venv/Scripts/python.exe code/full_aqp_comparisons.py

# Verdict原引擎在既有Flights样本上的只读验收与派生表图
.venv/Scripts/python.exe code/full_verdict_audit.py
.venv/Scripts/python.exe code/full_verdict_tables.py

# 作者母体门禁仍失败；以下严格作者入口会拒绝，不能用LOCAL成功替代
.venv/Scripts/python.exe -B code/full_ssb_native_replay.py verify
.venv/Scripts/python.exe -B code/full_ssb_native_tables.py

# 新continuation事务已通过；旧replay/canonical ROOT失败状态保留
# 以下两种只读入口按需要择一，每个入口都包含一次完整父证据核验
.venv/Scripts/python.exe -B code/full_ssb_local_continuation_run.py verify
.venv/Scripts/python.exe -B code/full_ssb_local_continuation_tables.py

# 独立10M/table训练政策的结果与逆序重放均完成后；不能接受1M模型代替
.venv/Scripts/python.exe -B code/full_ssb_local_ci_group_replay.py verify
.venv/Scripts/python.exe -B code/full_ssb_local_ci_tables.py

# Scalar本地变体实际收集与完整封存后；不连接PG、不重新收集计数
.venv/Scripts/python.exe -B code/full_scalar_oracle_audit.py --directory <已封存的独立run目录>
.venv/Scripts/python.exe -B code/full_scalar_oracle_tables.py --directory <同一run目录>

# 两种采样均已通过；只读验收和派生，不连接PG或补跑采样
.venv/Scripts/python.exe -B code/full_job_sampling_tables.py --srs-run output/full/sampling/job70/runs/bfdbb8efeab95c9c1ba9 --ibjs-run output/full/sampling/job70_ibjs/runs/da6334a896570c01d792

# 仅导出显式白名单派生CSV/PNG，作为可提交的协作快照
.venv/Scripts/python.exe code/full_public_summary.py
```

`--all` 读取本阶段已有v2实验配置清单；新训练配置也可把其明确label作为位置参数传给v3入口。
v1/v2、原模型和原published真值均保留为历史证据。只有完整v3依赖、seed0基线和seed1/2/3
逆序重放通过后，当前状态才报告该配置通过。论文200条成员缺失不能被683条本地工作负载替代。

新训练/恢复先用 `full_prepared_seal.py` 和 `full_training_guard.py`；不要直接把旧
`full_training.py` 的metadata级检查点当作完整HDF来源证明。详见
[依赖与恢复审计](FULL_DEPENDENCY_AUDIT.md)。原组件种子由binding派生，metadata包含本地路径；
新机器重建metadata后不保证产生同一训练样本或逐位相同模型。每次结果保留实际种子与输入摘要，
不得把本机结果摘要当作另一台机器已经重跑的结果。
已封存的CRLF源及新CI重放绑定源在`.gitattributes`明确设为`-text`，其余Python为LF；
不要运行全目录换行格式化，否则会改变运行凭据绑定的原始字节。

## 分实验协议

| 内容 | 入口与边界 |
|---|---|
| 论文精读、图表覆盖条件 | [FULL_REPRODUCTION_PROTOCOL.md](FULL_REPRODUCTION_PROTOCOL.md) |
| 参数、预算和两个schema | [FULL_PARAMETER_STUDIES.md](FULL_PARAMETER_STUDIES.md) |
| 当前C++差分、物理调用计时与只读验收 | [FULL_CPP_V3.md](FULL_CPP_V3.md)、[FULL_CPP_V3_AUDIT.md](FULL_CPP_V3_AUDIT.md) |
| 官方MSCN与最终只读复核 | [FULL_MSCN_PROTOCOL.md](FULL_MSCN_PROTOCOL.md)、[FULL_MSCN_VERIFY.md](FULL_MSCN_VERIFY.md) |
| 重建一致位图MSCN | [FULL_MSCN_REBUILT.md](FULL_MSCN_REBUILT.md) |
| Flights原规模模型/AQP/CI | [FULL_FLIGHTS_MODEL_RUN.md](FULL_FLIGHTS_MODEL_RUN.md) |
| Flights独立逆序重放与当前parser绑定 | [FULL_FLIGHTS_REPLAY.md](FULL_FLIGHTS_REPLAY.md)、[FULL_FLIGHTS_REPLAY_AUDIT.md](FULL_FLIGHTS_REPLAY_AUDIT.md) |
| 原DBEst实际1B母体上的20K拟合与审计 | [FULL_DBEST_FLIGHTS.md](FULL_DBEST_FLIGHTS.md)、[FULL_DBEST_FLIGHTS_AUDIT.md](FULL_DBEST_FLIGHTS_AUDIT.md) |
| 原Verdict已有样本执行、原错误和独立适配 | [FULL_VERDICT_PROTOCOL.md](FULL_VERDICT_PROTOCOL.md) |
| SSB SF500与准备/训练门禁 | [FULL_SSB_MODEL_PROTOCOL.md](FULL_SSB_MODEL_PROTOCOL.md) |
| SSB新鲜进程逆序point/CI重放及只读验收 | [FULL_SSB_REPLAY.md](FULL_SSB_REPLAY.md) |
| 修正SSB原生生成器、完整字段差分与恢复 | [FULL_SSB_NATIVE_V2.md](FULL_SSB_NATIVE_V2.md) |
| 修正SSB模型桥与独立逆序验收 | [FULL_SSB_NATIVE_MODEL.md](FULL_SSB_NATIVE_MODEL.md)、[FULL_SSB_NATIVE_REPLAY.md](FULL_SSB_NATIVE_REPLAY.md) |
| LOCAL1M独立模型/作者差异保留 | [FULL_SSB_LOCAL_REPLAY.md](FULL_SSB_LOCAL_REPLAY.md) |
| 新canonical1M评估事务与历史失败分界 | [FULL_SSB_LOCAL_CANONICAL_PROTOCOL.md](FULL_SSB_LOCAL_CANONICAL_PROTOCOL.md)、[FULL_SSB_GROUP_ORDER_DIAGNOSTIC.md](FULL_SSB_GROUP_ORDER_DIAGNOSTIC.md) |
| LOCAL10M/table训练政策及独立重放/只读外层 | [FULL_SSB_LOCAL_CI_PROTOCOL.md](FULL_SSB_LOCAL_CI_PROTOCOL.md)、[FULL_SSB_LOCAL_CI_REPLAY.md](FULL_SSB_LOCAL_CI_REPLAY.md) |
| 新DBEst单维兼容查询路由与两次运行入口修复 | [FULL_DBEST_FLIGHTS_ROUTES.md](FULL_DBEST_FLIGHTS_ROUTES.md) |
| 独立JOB-light每表1000行WOR采样与全部终态保留 | [FULL_JOB_SAMPLING_PROTOCOL.md](FULL_JOB_SAMPLING_PROTOCOL.md) |
| 独立Scalar oracle与作者Perfect Selectivities分界 | [FULL_SCALAR_ORACLE_PROTOCOL.md](FULL_SCALAR_ORACLE_PROTOCOL.md) |
| LOCAL Verdict的canonical父证据与预算 | [FULL_VERDICT_LOCAL_SSB_IMPLEMENTATION.md](FULL_VERDICT_LOCAL_SSB_IMPLEMENTATION.md) |
| 原Verdict SSB SF2实际38调用与缺口 | [FULL_VERDICT_SSB_SF2_AUDIT.md](FULL_VERDICT_SSB_SF2_AUDIT.md) |

正式长任务只运行一个控制器。SSB全4000片、3,000,028,242事实行与13项作者整数聚合
必须先通过，才允许正式训练；不得用正在增长的样本启动另一份正式运行。
2026-10-31首次完整遍历实际为3,000,028,334行、9,993,609样本，作者聚合2059项不同；
原监督器已正确停止，作者母体正式门禁仍关闭。不得直接重启监督器、改写MISMATCH或把该样本标作作者母体。
新原生路径已通过SF1/SF2完整字段差分、独立SQLite聚合和实际重启门禁，SF500在新命名空间完成。
新SF500行数已一致，前6条查询346项真值完全匹配，但7条customer连接查询1713项不同，仍为MISMATCH/TAINTED。
因此三个作者母体模型执行闩锁保持关闭，没有生成严格作者模型计划或开始训练；不得改写失败状态来绕过门禁。
另行封存的LOCAL决定与完整21766项来源审计允许本地生成母体实验。当前五个1M/table模型和13条
查询已经实际执行，无查询错误，三阶段封存通过；旧独立重放9c因S4.3置信区间差异失败并保留TAINTED。
GROUP BY配对排序新变体的全部13条查询通过双hash/正逆序诊断，点与区间一致；
旧canonical评估失败；后续10M和LOCAL Verdict使用下述已经通过的continuation父契约。
2026-10-31首次canonical监督事务因Windows Job名称前缀不兼容，在任何模型调用前失败；旧计划和TAINTED保留。
v2只修正两个名称字符串，正逆两个方向的真实base→venv进程门禁均通过，门禁不调用模型或数据库。
第二次事务正向26次调用及2059组验收通过；逆向在科学调用前因存储监控过期停止，旧ROOT保持TAINTED。
新continuation协议仅复用已验收的正向结果，在新命名空间执行逆向；两项源码固定为
`151b29aac633aa85902578ccb115de749a31be74d8f525b1e62d5d99257dd6d1`及
`e3135eea0469eb00df42ea8c27370d6af445356bb4c136f2c71ee2e11ebf41be`。
首个接续事务在完整来源核对后因RAM不足5GiB停于0worker/0模型调用，旧f263命名空间保持TAINTED。
v2用显式`--attempt-id`将新尝试绑定到独立计划和目录，目录认领前先检查5GiB，worker前也保留原门禁。
v2的`ram_retry_02`已经整体通过，新计划位于`output/full/ssb/local_sf500_continuation/plans/87392d7dedf465279272/plan.json`。
它复用正向26次调用并新增逆向13次模型载入/26次调用，2059个点及4118个区间端点完全一致。
运行前后完整来源核验、独立子进程控制和最终发布均为PASS；原1M模型、旧正向结果及历史失败状态保持不变。
结果为`output/full/results/ssb_local_sf500_canonical_aqp_ci.json`，SHA为`f37833fdc2b249e22632f5fa3e0ea98499c748487a43fcd42b0d692768fbeac8`。
3张派生表及2张图已通过独立只读验收和图像检查，来源为`output/full/figures/aqp_ssb_local_continuation_82803cb6f9608f78/`。
公开副本和哈希来源记录见`output/results/fullpaper_ssb_local_continuation_*`。
10M/table训练入口的实际小黄金等价验证已经整体通过，结果为`output/full/results/ssb_local_ci10m_cap_golden.json`，
SHA为`469fe011130f4b55e3f4e6603a622cd8286f65b0f35f2e10f0d02ef450b46ff1`。
五表矩阵、结构、NumPy/Python随机状态一致；恢复只补拟合三个组件，前两个组件的四个checkpoint文件字节不变。
这只是既有SF2/10K夹具的算法等价证据。正式10M训练正在生成候选计划，不能把小黄金记作正式CI模型。
CI v7及LOCAL Verdict v6仅更新两个source pins，科学、黄金及资源策略不变，
不代表实际黄金、训练或数据库执行已通过。旧canonical runner及旧计划保持历史失败状态。
详见[FULL_SSB_LOCAL_CONTINUATION.md](FULL_SSB_LOCAL_CONTINUATION.md)。
本轮CI的独立逆序入口是`full_ssb_local_ci_group_replay.py`，当前固定SHA为
`4b73cf6bed9bb001ec1bf289fadb6950bdd4f0c644e1837406eaef402b0a827c`；
CI协议中v3段落的旧`97243fa7...`为其预热修正前的历史候选。新的worker先导入会设置NumPy种子的
原推断模块，再由冻结通用重放器设置声明的74031种子；不会逐query重新播种。
详见[FULL_SSB_GROUP_ORDER_DIAGNOSTIC.md](FULL_SSB_GROUP_ORDER_DIAGNOSTIC.md)。10M/table政策实验
代码已审查，但真实黄金和正式训练尚未执行。它们不能提升作者母体失败状态。
其采样使用发布schema的精确概率0.003333，再按64位整数cutoff实施；实际样本数和n/p归一化均保留。
`full_ssb_native_v2_formal.py verify-final`仅是固定生成器的数值/物理输入门禁；模型桥还须独立绑定
stream lifecycle/stderr、时间/峰值和外层FINAL_PASS后才接纳，不把作者13条真值相同称为全部原始行字节相同。
旧监督器和`full_ssb_replay.py`的旧路径保持冻结，不对失败母体执行训练。
修正SSB原顺序正式推断后，由唯一控制器显式执行一次`full_ssb_native_replay.py replay`；
日常验收只用`verify`。重放PASS只证明行为一致，缺组、非有限区间和CI排除仍单列，
不能把模型调用零异常当作所有分组及区间覆盖完整。
Flights日常验收使用新的只读parser外层。它记录当前sqlparse0.3.1及完整22个Python源文件，
不重跑已接受的24次推断，也不能证明最初推断时的parser原字节。
有源码、原始输入或资源缺口的项目保持未完成，不能把作者报告数值复制成此次结果。
完整测试目录包含原生编译、实际生成器和数据库接入门禁。日常验收运行上述只读audit，
代码改动只运行对应的纯/合成测试；不要为了检查状态重跑整个pytest目录。
确需门禁时先核对现有封印并复用已验证产物，临时目录使用项目内较短的`output/tmp/`子目录。
Verdict的当前验收只核文件/JAR/源码及历史数据库记录，不连接或重跑数据库，也不证明当前数据库逐行未变。
它保留F5.2原始错误、单独的两SUM适配和缺组；原生95%区间不能混作DeepDB中央90%区间。
Windows深路径运行Verdict的建树测试时，临时目录应使用较短的`--basetemp output/tmp/v`，避免MAX_PATH；
只读日常验收使用上述audit入口，不需要重跑golden或正式SQL。
DBEst新路由的200K门禁实际完成101次原生聚合调用、103次拟合尝试，SUM/AVG独立数值验证通过，
无拟合或数值验证错误；79个空样本和2个预算不支持项仍为覆盖缺口。后续1B母体测试不重跑旧4类76次调用。
1B母体V4已实际通过：204个组件、101次拟合尝试、99次原生调用，103个空样本和2个预算不支持项；
独立派生结果在`output/full/figures/dbest_routes_e647e45a22ca151fd40c/`，导出执行零次科学调用。
第7条PHX/year2005使用显式拟合配置变体：目标SQL与本地精确真值匹配，可单列该变体的误差；
发布资源的拟合预筛仅PHX，与新配置不同，不能据此称作者配置已恢复。两个SUM的差不提供联合CI。
Scalar V4已实际完成50项计数和70条预测，独立只读派生验收通过。正式目录为
`output/full/scalar_oracle/runs/8e345a77946b8294c724/`，派生结果为
`output/full/figures/scalar_oracle_c0f8f6a31e91b8b68058/`。它只用单表精确计数和
预先声明的uniform-title-key公式估计多表结果，不是作者未公开的Perfect Selectivities组合器。
派生表单独采用`EVALUATION_ONLY_FLOOR1`，保留原始Fraction/零预测；不与既有DeepDB的零值无穷大
计分政策静默共榜。只读派生命令不会缺失时补跑计数。
JOB-light SRS和IBJS均已实际完成70条及严格验收。SRS每表独立WOR 1000行、
每条查询30秒预算、原始零值和超时null均保留；合法首次SQL前超时也占一个终态，不能补采或丢弃。
SRS70条均为原始零估计；IBJS n1000/b100K有13条零估计、57条正估计，无未完成项。
零对应无穷大q-error，完整70条IBJS中位1.458495、p90/p95/最大值无穷大；条件有限57条指标另列。
独立汇总位于`output/full/figures/sampling_b23bd4bd6edb87315fe8/`。两种方法所有相关表的schema及
两个全量query-column COPY哈希逐一相同。作者原n/预算/回退配置未识别，不称作者Table1原结果已恢复。

按用户要求，最终清理将只保留必要源数据、最终处理数据、代码和结果。当前自动审批以
`blocked by policy`拒绝了缓存和草稿的删除，已完成盘点而未执行删除；草稿现已补齐为正式采样汇总代码及测试，
缓存和失败产物仍待清理。
详见`output/full/results/cleanup_plan_current.json`；失败父目录中的已验收正向结果须单独保留。
历史完整审计依赖仍在；将来退役这些依赖时，原fullF及依赖它的continuation/CI/Verdict验收也必须明确退役。

## 组员可直接接手的内容

- 对照论文逐图读 `output/results/fullpaper_*` 派生表/图，分析中位数接近但尾部未恢复的原因；
  不挑选最有利配置替换默认结果，也不把public413当作者200。
- 审查未公开输入清单：原Figure5生成参数/种子、作者200条成员、Wavelet实现和Figure12查询。
  获得原始证据后再建独立配置；本仓库的历史作者数字不能当本次实验。
- 在各自功能分支补原基线接入、结果解释与课程报告/PPT，通过PR合入。数据和模型使用独立下载/生成入口，
  不随Git提交；已完成并验证的实验直接消费封存结果。
- SSB作者母体门禁仍关闭；跨平台字段修复与原规模新遍历已经完成，剩余customer相关真值来源继续审查。
  组员不要重启任一失败控制器，也不要通过改真值或执行闩锁启动训练。
