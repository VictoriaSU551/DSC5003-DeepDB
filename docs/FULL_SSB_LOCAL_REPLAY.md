# 本地 SSB SF500 模型的独立重放和派生结果

本协议只适用于 `LOCAL_SSB_SF500`。当前生成母体为3,000,028,242行，实际保留9,996,946行；
与作者2059项整数聚合真值比较，346项相同、1713项不同。原始 `MISMATCH`、
原生成监督器的 `TAINTED` 和严格作者模型的三个关闭闩锁继续保留。
本地模型、重放和表图通过均不能升级为作者数据复现或整篇论文完成。

## 接纳边界

`code/full_ssb_local_replay.py` 只接纳本地模型的严格只读接口
`PASS_READ_ONLY_LOCAL_SSB_SF500_MODEL_WITH_AUTHOR_MISMATCH`。
接口必须保留本地范围、1713项差异、作者和整篇复现未完成标记，以及原失败报告的固定路径和SHA。
缺少源文件、模型、HDF、依赖、模型监督器或任何正式产物时应失败，不能补跑或修复。

新鲜子进程采用 `PYTHONHASHSEED=173`，Python/NumPy种子74031，四个数值线程上限均为1。
按13条原始SQL的逆序执行，每条重新读取保存模型，分别实际执行point和CI路径：
共13次模型加载、26次原评估调用。比较原始组身份、预测、区间、非有限区间模式，
相对容差1e-9、绝对容差1e-5。缺组、额外组、零真值和CI排除不从覆盖范围中删除。

模型执行期间禁止Python层原始/准备文件读取器和数值数据加载器访问输入。
这不是操作系统文件访问跟踪。模型执行前后完整物理输入、模型和依赖快照必须相同。
每条查询保存结果及封印，正式目录固定为26个查询工件加3个验收工件；
任何历史命名空间不能自动重跑或洗去失败状态。

父进程启动凭据绑定完整重放binding、结果SHA、目录、报告的worker PID、精确命令、
显式种子/线程环境、有限非负耗时和stdout/stderr物理文件。
报告的worker PID不是对Windows venv启动器PID的操作系统观测声明。
旧模型的成功启动凭据不能接纳新模型的worker结果。

## 执行和读取

模型正式验收完成并释放资源后，唯一控制器显式执行：

```powershell
.venv/Scripts/python.exe -B code/full_ssb_local_replay.py replay
```

日常验收只读取，不启动进程、加载模型、推断或写文件：

```powershell
.venv/Scripts/python.exe -B code/full_ssb_local_replay.py verify
```

已接纳重放的派生结果由 `code/full_ssb_local_tables.py` 生成。
复用已验证的聚合误差/样本矩计算；两幅PNG及全部三个CSV均标注本地范围与作者差异。
表图只落在 `output/full/figures/aqp_ssb_local_sf500_<hash>/`，
最新指针为 `output/full/results/ssb_local_sf500_tables_latest.json`。
完整五个工件及binding必须通过缓存核验才能复用。
公开导出仅接纳成功manifest、不完整标记和明确的本地范围，名单只包含派生CSV/PNG。

中央90%CI仍只来自一次实际样本；参考样本组数少于10时排除。
模型沿用原n/p，均匀样本参考使用精确N；不同样本预算、Bernoulli与SYSTEM抽样差异、
S4差分项可能违反独立性等限制仍须保留，不做重复抽样校准或公平耗时排名声明。
