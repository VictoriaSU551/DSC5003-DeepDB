# 原DBEst：真实1B母体、<=20K拟合适配

只复用已完成的Flights1B同源样本/12条全流truth和已验证官方helper。
不修改`full_dbest.py`、200K输入/输出、私有源或现有环境。
F1.1/F1.2/F3.1只从全流状态取先于数值过滤的COUNT作为声明的训练N，SUM/AVG仅用于事后评价。
F4.1以**完整保留Bernoulli样本**的州数/p估计范围前N，另记其标准误，
不使用distance>2500的被评估COUNT填N。

实施计划：TDD验证上述元信息隔离、唯一确定抽样/完整样本计数、20K硬限；
流读最终9997912样本行，选择20K唯一保留行；真实官方拟合/原积分，逐组/逐查询原子封印；
独立解析矩核验、12类逐项状态、内存<=512MiB，最后对全部旧200K输出作SHA不变核对。
未完成前不据此声称原论文12类/原10M训练配置已经复现。

## 已完成的真实1B母体门禁

本次状态为`PASS_WITH_GAPS`，不是完整论文基线通过。
最终母体1,000,000,000行，保留样本**9,997,912行**，不是恰好10M；
582,074,363字节的样本SHA256：
`9d9c78d0e03b403472e34da73af9f3dccde070036c3ed02c649ce4ee880d6f45`。
`generation_result.json`、checkpoint、ground_truth的complete/母体/采样绑定以及12条SQL均核对。

一次流读全部保留样本56.784秒，`seed=74131`，均匀不放回选20,000个唯一**保留行ID**，
不按数值去重，不整读10M，不追加罕见组。选取文件及完整样本州目录有独立SHA；
之后可由此恢复，不再扫描已验证的582MB。真实官方引擎、LR+Gaussian配置与数值积分适配
全部复用封存`full_dbest.py` helper；仅在新子进程里改变其OUTPUT路由，原模块文件不改。
200K数值失败只作为已验证的积分适配依据复制并明确标`NOT a new 1B native result`，
没有把旧732.08的数值冒充新的1B实验。

本次76个真实模型/原聚合调用、429,156次原KDE求值，原积分时间合计73.264秒，
整次墙钟160.432秒，Windows进程峰值157,970,432字节（约150.65MiB），低于512MiB硬门禁。
所有实际积分与同模型解析Gaussian矩独立一致：AVG最大绝对差1.48e-12，SUM6.38e-6
（对应大母体缩放后的量纲；不是相对误差）。原COUNT仍保留int截断。
原200K模型/回执/输入/源与原`full_dbest.py`全部受前后SHA快照保护且未变。

| 查询 | 真实覆盖与同母体全流truth误差 |
|---|---|
| F1.1 AVG | 1模型；相对误差0.0738% |
| F1.2 AVG | 1模型；相对误差9.0816% |
| F3.1 SUM | 22年组均有估计；平均/最大相对误差25.6557%/60.3165% |
| F4.1 COUNT | 52组模型；DE在20K拟合中无行，明确null且漏1个真值组；现有非零真值组平均/最大误差68.0584%/762.6100% |

误差分母为有估计的非零真值组；**漏掉DE另行显式记录，不能把上表均值当成完整覆盖误差**。
零估计仍参与其非零真值组误差；额外组/缺失组单独保留。未用truth补模型或填零。
F2.1/F2.2/F2.3/F3.2/F3.3/F4.2/F5.1/F5.2仍为UNSUPPORTED，理由沿用200K协议，
不将有限适配边界写成原方法理论上不能支持这些查询。

F4.1全部范围前N估计合计999,791,200，与N=1B不同是Bernoulli波动的明确结果。
例如CA完整保留样本1,205,902行，p=.01，N_hat=120,590,200，元信息SE=109,263.122。
SE按`n_state*(1-p)/p^2`方差的平方根计算；这不是COUNT预测的完整置信区间，
也没有假设它与拟合子样本独立。F1/F3的N来源则为原全流COUNT，标estimated=false。

## 命令、恢复和证据

```powershell
.venv/Scripts/python.exe -B code/full_dbest_flights.py run
.venv/Scripts/python.exe -B code/full_dbest_flights.py verify
.venv/Scripts/python.exe -m pytest code/tests/test_full_dbest_flights.py -q
```

测试6 passed（3.15秒）；5项先因未实现失败，再通过。它们验证：改变评估SUM及F4过滤后的COUNT
不影响训练元信息、完整样本而非范围内州计数、固定抽样唯一性、行数错位拒绝和20K先于IO硬限。
真实1B集成测试此后核对已封存输出，不把复用冒充重训。

`data/dbest_flights/selection_seal.json`绑定唯一样本ID和仅20K行pickle；
`training_metadata.json`只有允许的COUNT元信息和N估计，无评估SUM/value。
`output/full/dbest_flights/query_00.json`至`query_11.json`是逐查询原子回执（原生预测不含评估答案），
models/integrals分别按原helper逐模型/积分保存。
事后评价集中在`verification.json`，全部受`verification_seal.json`保护，
另保留`first_success.json`和进程stdout/stderr/耗时日志。改变输入、helper、选取或结果字节拒绝复用。

该实验证明真实1B生成母体上的有界接入，而非1B行或10M点直接拟合；
DeepDB作者DBEst精确训练n、带宽/回归/归一化参数和Figure12微基准SQL仍无来源依据。
不能把本次低样本精度或延迟标作Figure12/13原配置复现。
