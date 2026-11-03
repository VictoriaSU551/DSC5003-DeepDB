# 原 DBEst：封存 200K 输入的小门禁

已实际运行原官方 DBEstPy 的 `CRegression.fit`、Gaussian KDE 和
`QueryEngine.approximate_{count,sum,avg}_from_to`。这是接口、倍率和数值门禁，
不是 Figure12/13 完整基线复现，也不是 1B 规模性能测试。

## 固定来源、环境和输入

官方源为 [DBEstPy@2220a937b5eef358eb42a715da328915048b7250](https://github.com/qingzma/DBEstPy/tree/2220a937b5eef358eb42a715da328915048b7250)。
ZIP SHA256 为 `532902dce2c0f598c71583bfb31085037eea9fac71c588393812a63de899e2bf`，
此前已逐 Git blob 核验，见 `output/full/results/baseline_sources.json`。
ZIP 留在 `data/downloads/baselines/dbpy/`；原字节只恢复到忽略的 `data/dbest/source/`。
没有改原源码或新增公开 vendor 副本。[实际 LICENSE](https://github.com/qingzma/DBEstPy/blob/2220a937b5eef358eb42a715da328915048b7250/LICENSE)
为 BSD 二条款形式。原方法论文见[作者 SIGMOD'19 存档](https://wrap.warwick.ac.uk/id/eprint/115961/)，
DOI `10.1145/3299869.3324958`。这是官方可执行候选，没有证据证明是 DeepDB 作者精确快照。

初次在既有环境只读导入失败：`ModuleNotFoundError: xgboost`，保留为
`output/full/dbest/import_before_environment.json`。随后只创建 `.venv-dbest`，不改主环境。
固定 CPython3.8、numpy1.19.5、scipy1.4.1、pandas1.0.3、scikit-learn0.22.2.post1、
matplotlib3.2.1、xgboost1.0.2；全部精确版本、官方 PyPI wheel SHA256 见 `environment.json`。
这是兼容环境锁，不是未公开的论文原环境锁。

只读复用 `data/flights/generated/golden-200k/original.csv`，200,000 行、12 列，SHA256
`c9df154be75aebc047ce7c11c5efc55c2e81e13b85e5b2a5fc26f219d312992d`；没有重新生成输入。
原12SQL、既有 `golden_validation.json`、`reference.sqlite`、`sqlite_exact_state.json`
全部绑定 SHA。SQLite 使用 `mode=ro`；再执行的12条精确SQL逐组等于封存整数状态。
生成器模块仅 AST 读取字面量，不导入、更不修改。

## 模型、抽样和信息预算

固定 `seed=74031`，从200K一次均匀不放回选20,000个唯一行ID，所有路由共用这些ID。
不为罕见组追加样本；每个模型硬上限20K，实际最大2,419行。
使用原 `qreg.py:980–985` 提供的 `base_models=['LR']`，原默认 Gaussian KDE、bandwidth=1，
保留原数值单位。聚合列同时作一维密度特征，LR 确实由原 `CRegression.fit` 拟合。
这避开可能出现二次代价的模型配置；不是手写回归/KDE，也不是 Figure13 作者已披露的超参数。

[原 QueryEngine 构造器](https://github.com/qingzma/DBEstPy/blob/2220a937b5eef358eb42a715da328915048b7250/dbest/query_engine.py#L47)
支持显式母体 N，不给时默认用训练 n。`dbestclient.py:185–187` 也传入 N；
GROUP BY API 的第424、477行另要求组大小。
本任务对原 CSV 单次扫描，只数类别预过滤/组成员，**先于数值范围过滤**计算 N，
写入 `data/dbest/group_counts.json`；不把目标 COUNT/SUM 用于训练。
例如 F4.1 用完整州 N，而不是 distance>2500 的答案。真值只在估计后用于误差评价。
纯类别 COUNT 的答案等于所提供的精确组大小，所以本门禁排除 F2.* 的这类信息泄漏。

## 真实失败、最小适配和独立数值核验

先写测试并观察缺失实现失败，再实现。真实宽范围积分又暴露原实现的错误：

| 同一个 F1.2 原模型 | AVG |
|---|---:|
| 原未适配 scipy.quad | 696.4512003724882 |
| 独立 Gaussian 解析矩 + 实际拟合 LR 系数 | 732.0846689895470 |
| 只增加积分分段点/预算后的原方法 | 732.0846689895473 |

原积分达到50个 subdivisions 并发收敛警告；回归测试先真实失败、再通过。
原失败留在 `numerical_failure_F1.2_all.json` 和 `small_process_before_quad.json`。
新环境的入口也会先运行未适配路径、封存真实失败，然后才启用适配。
包装仅临时替换进程内 `dbest.query_engine.integrate`，继续调用原 scipy.quad，
增加4×bandwidth间距的分段点和 limit；超过10,000分段拒绝。用后恢复。
官方方法、KDE、回归、SciPy算法及源码字节不改；解析积分只作 oracle，绝不返回成预测。

8行探针真实得到：默认 n=8 → COUNT/SUM/AVG=8/32/4；显式 N=80 → 80/320/4；
N=800 → 800/3200/4。SUM相对解析差0，AVG最大绝对差8.88e-16。
原COUNT末尾有 `int(result)`，因此允许约1的截断差，不静默改这一行为。
所有方法次数和 `kde.score_samples` 求值次数留证。

严格边界仍有明确限制。SQLite 用整数十分位区分 `>` 与 `>=`；200K的distance=2500
没有点质量，两种真值均2,713。另一个探针包含x=0原子，N=80时严格/闭边界真值40/50，
连续KDE对两种边界均估44，说明没有离散原子质量语义。数值等值查询仍未支持。
真实二维输入也在原 `QueryEngine.__init__:63` 的 `min(ndarray)` 产生
`ValueError: ... truth value of an array ... ambiguous`，已记 `probe.json`，没有修多维路径冒称通过。

## 实际估计及原12类支持边界

以下全部来自本次真实估计与同母体SQLite，不使用作者历史CSV：

| 原查询 | 拟合与结果 |
|---|---|
| F1.1 | ATL，n=1,132/N=11,254；AVG 1207.186042 vs 1206.652666，误差0.0442% |
| F1.2 | TW，n=287/N=2,742；AVG 732.084669 vs 732.206419，误差0.0166% |
| F3.1 | 9E按年22个SUM模型，各n=6–14；所有真值组有估计，平均/最大相对误差16.54%/49.50% |
| F4.1 | 按州DISTANCE>2500 COUNT，51模型，各n=8–2,419；50个真值组有估计，平均/最大误差50.70%/200%；另一个VI零估计组 |
| F2.1/F2.2/F2.3 | UNSUPPORTED：纯类别COUNT会与精确先验组数重合，不作为独立模型估计 |
| F3.2 | UNSUPPORTED：罕见HPN预过滤、第二个分组SUM路由和样本覆盖未验证 |
| F3.3 | UNSUPPORTED：公开预过滤只选PHX，year=2005仍是未验证数值等值路径 |
| F4.2 | UNSUPPORTED：两个数值过滤维度，原二维构造器已真实失败 |
| F5.1 | UNSUPPORTED：乘积聚合投影未路由 |
| F5.2 | UNSUPPORTED：两个SUM组合未路由 |

F4.1完整域中的DE、TT母体分别3、4行，样本均0；各标
`UNSUPPORTED_INSUFFICIENT_SAMPLE`、`estimate=null`，不补样、不填0。
它们恰好都不在范围查询的非空真值组里；不能据此声称完整类别覆盖。
评价保留零估计、额外组和缺失组，而非只挑有利输出。
上述UNSUPPORTED是本包装器的验证边界，不是原方法理论能力的断言。

还调用了CA州 `500<distance<=1500` 的三个原聚合：COUNT 11250 vs 精确10969，
SUM 9670215.860565 vs 9423971.2，AVG 859.562497 vs 精确整数比 `94239712/109690`。
同一已拟合模型的解析差：COUNT0.160284（原int截断）、SUM3.73e-9、AVG9.09e-13。
抽样近似误差与数值错误分开报告。

首个成功门禁 `small_gate_first_success.json`：75原模型、78原聚合调用、423,024次KDE求值，
原生查询合计169.897秒，历史实际拟合合计3.784秒，该成功调用墙钟202.429秒。
失败和环境安装耗时不包含在此；这些不是原规模速度。
后续使用绑定SHA的逐组原子回执恢复；`native_method_calls_this_invocation` 和
`verified_integrals_reused` 区分当次新调用与复用，不能把缓存称重跑。

## 命令、封印和1B计划

项目根目录执行：

```powershell
.venv/Scripts/python.exe code/full_dbest.py setup
.venv/Scripts/python.exe code/full_dbest.py probe
.venv/Scripts/python.exe code/full_dbest.py small
.venv/Scripts/python.exe -m pytest code/tests/test_full_dbest.py -q
.venv/Scripts/python.exe code/full_dbest.py plan
```

本次13 tests passed：9项无依赖契约，4项真实集成测试；没有独立环境/封存输入时相关项显式skip。
其中截掉第12项真值的测试先观察到未拒绝，再修为显式核对12项及其query编号/名称，避免zip截断误报。
`output/full/dbest/` 中的 source/input binding、models、integrals、small_gate/seal、probe
分别封印源/输入、模型N/n与行ID、原积分/解析差分、完整估计与缺口、探针。
绑定字节变更拒绝复用；超时终止该命令的Windows子进程树。BLAS/OMP固定单线程。
完整成功门禁和原失败都保留，不覆盖旧实验或任何原输入。

`one_billion_plan.json` 只生成计划：待1B样本/全流truth最终完成并按同一seed/config/SHA封印后，
流式扫描约10M保留样本，再固定选最多20K唯一行。不整读10M，不直接训练10M点KDE。
N=1B可知，但F4.1需要数值过滤**之前**的州数；已有过滤后的目标COUNT不能当先验。
没有独立精确计数目录时，只能用完整保留样本的n_group/p估算N，另外报告抽样误差，
不能声称精确母体组数已恢复。F1/F3分母若作为训练元信息也须明确声明。

当前独立环境369.8MB、下载/私有源/行ID约100.5MB；读到过122.7MB进程峰值计数快照，
不是整项工作的完整峰值测量。后续<=20K门禁预算：单进程512MiB RAM、最多100MB新增子集/模型，
复用约600MB输入CSV，扫描10分钟、拟合/查询15分钟。它们是保守预算，不是1B实测，
不能外推10M KDE复杂度。本任务没有开始1B训练。

[DeepDB 6.2节和Figure12/13](https://www.vldb.org/pvldb/vol13/p992-hilprecht.pdf)
给出Flights1B、原12查询类及已知工作负载条件，Figure12左图改变1/2/3个数值过滤属性。
DeepDB的Flights训练样本10M不证明DBEst也使用10M。固定公开资源只有12条
[DBEst类别预过滤SQL](https://github.com/DataManagementLab/deepdb-public/blob/655ada13a043a4226a239b0c0a65bcdefef87a02/baselines/aqp/resources/dbest_flights_aqp_queries.sql)。
Figure12精确微基准SQL、每模型实际训练n、带宽、回归配置、归一化和积分参数仍未定位。
没有把这些缺口、剩余8类、多维路径或原规模性能记为完成。
