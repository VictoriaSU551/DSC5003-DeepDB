# 复现与核验运行指南

所有命令从源码检出的项目根目录、Windows PowerShell运行。先读[当前状态](FULL_REPRODUCTION_STATUS.md)和[公开结果](../output/results/FULL_PAPER_RESULTS.md)。已验证结果不重复训练；阅读文件、核验现存闭包、生成派生表图与执行新科学实验分别处理。

## 克隆与环境

`main`是代码和共享结果的最终交付入口；完整阶段整合见[PR #3](https://github.com/VictoriaSU551/DSC5003-DeepDB/pull/3)，`reproduction/full-paper`保留开发历史。公开仓库不带数据/HDF、模型本体、数据库、环境或PDF。

```powershell
git clone https://github.com/VictoriaSU551/DSC5003-DeepDB.git
Set-Location DSC5003-DeepDB
powershell -ExecutionPolicy Bypass -File setup.ps1
.venv/Scripts/python.exe -B code/download_data.py
```

主环境固定Python3.8.20及 `requirements-lock.txt`，使用项目 `.runtime`/`.venv`，不登记全局Python。需要Git、curl和uv；本机验证过uv0.9.11。已有匹配环境先核版本，不重复建立。MSCN使用独立环境：

```powershell
.venv/Scripts/python.exe -B code/full_mscn_sources.py
powershell -ExecutionPolicy Bypass -File setup-mscn.ps1
```

10个Windows/Python3.8 wheel由[固定清单](manifests/mscn-windows-py38-wheels.json)约束；这是本地兼容环境，不是作者原Python3.7/PyTorch1.0环境。`full_mscn_sources.py --offline`仅核现存固定输入。数据库、Flights/SSB生成、C++及Java依赖按对应协议准备，基础安装不等于全部实验可直接执行。

## 基础流程与测试

```powershell
# 基础纯/小型合成回归
.venv/Scripts/python.exe -B -m pytest code/tests/test_learning.py code/tests/test_preparation.py

# 以下是实际预处理/训练/评估，仅在需要重建基础实验时运行
.venv/Scripts/python.exe -B code/reproduce.py all
.venv/Scripts/python.exe -B code/verify_results.py
```

基础 `all`不恢复组员全部13轮训练，也不启动全部full-paper实验；已有模型仅重评可用 `code/reproduce.py evaluate`。完整测试目录存在真实生成器、原生编译及数据库/科学门禁。改动选择对应纯/合成测试，不用不带文件选择的 `pytest`检查状态，也不关闭测试遇到的实时操作守门。

CI消费者纯回归示例：

```powershell
.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider code/tests/test_full_ssb_local_ci_acceptance.py code/tests/test_full_local_ssb_status.py code/tests/test_full_ssb_local_tables.py code/tests/test_full_ssb_local_ci_group_replay.py
```

CI验收夹具使用合成封存文件，可位于项目外默认临时目录。原生/Java专项测试若有深路径限制，使用其协议规定的短临时目录；这不授权启动正式科学门禁。

## 公开结果可直接阅读

克隆后的 `output/results/FULL_PAPER_RESULTS.md`、`fullpaper_summary.json`、CSV/PNG与补充报告不依赖本地大文件。组员包另有两个标准库离线入口：

```powershell
python -B output/results/guoao_experiments/verify_results.py --repo-root .
python -B output/results/guoao_experiments/verify_evidence.py
```

它们重算保存的指标和文件指纹，不训练、连接数据库或重新加载13个模型。历史源码ZIP是来源取证；组员端到端复训还需匹配数据/HDF、模型、环境和数据库，见 [TEAM_EXPERIMENTS.md](TEAM_EXPERIMENTS.md)。

## 保留完整本地闭包时的验收

下列入口消费现存封存证据；verify/audit在缺少工件时失败，不补跑科学任务。派生入口会写新表图和指针。它们可能遍历大量来源文件，不是公开结果包的轻量检查。最终精简若移除闭包，相关入口必须退役，不能用摘要伪造现存完整验收。

```powershell
# 重建当前账本；无新训练或数据库科学执行
.venv/Scripts/python.exe -B code/full_status.py

# canonical Python/C++：不补跑推断或编译
.venv/Scripts/python.exe -B code/full_canonical_acceptance.py
.venv/Scripts/python.exe -B code/full_cpp_v3_audit.py

# 已保存预测的基数表图与另行local真值评分
.venv/Scripts/python.exe -B code/full_paper_tables.py
.venv/Scripts/python.exe -B code/full_local_truth_eval_v3.py

# Flights封存逆序及派生表图
.venv/Scripts/python.exe -B code/full_flights_replay_audit.py verify
.venv/Scripts/python.exe -B code/full_aqp_tables.py
.venv/Scripts/python.exe -B code/full_aqp_comparisons.py
.venv/Scripts/python.exe -B code/full_verdict_audit.py
.venv/Scripts/python.exe -B code/full_verdict_tables.py

# LOCAL SSB1M：已接受正向和新continuation逆向
.venv/Scripts/python.exe -B code/full_ssb_local_continuation_run.py verify
.venv/Scripts/python.exe -B code/full_ssb_local_continuation_tables.py

# LOCAL SSB10M/table：正式模型、逆序和表图已通过
.venv/Scripts/python.exe -B code/full_ssb_local_ci_group_replay.py verify
.venv/Scripts/python.exe -B code/full_ssb_local_ci_tables.py

# 两种采样的封存结果，不连接PG或补跑采样
.venv/Scripts/python.exe -B code/full_job_sampling_tables.py --srs-run output/full/sampling/job70/runs/bfdbb8efeab95c9c1ba9 --ibjs-run output/full/sampling/job70_ibjs/runs/da6334a896570c01d792

# 白名单派生CSV/PNG与摘要，保留全论文未完成
.venv/Scripts/python.exe -B code/full_public_summary.py
```

10M表图与状态消费者通过[固定ROOT相对调用适配](FULL_SSB_LOCAL_CI_ACCEPTANCE.md)调用一次原完整验收器；不改原provider、其余命令参数、来源或数值检查。必须从ROOT运行，不能以旧1M模型或小黄金代替已完成正式10M结果。

Scalar与DBEst专项只读入口、所需run目录见 [Scalar协议](FULL_SCALAR_ORACLE_PROTOCOL.md)、[DBEst路由](FULL_DBEST_FLIGHTS_ROUTES.md)。LOCAL Verdict SF500 v13已完成38次原始物理调用及一次新鲜完整只读验收/导出；[最终交付](../output/results/FINAL_DELIVERY.md)记录范围、原错误和缺组，来源闭包精简后原验收入口退役，不重启已完成或失败控制器。

## 新科学执行与恢复

科学执行包括训练、实际推断重放、原生生成器、数据库SQL或建样本，需要独立计划、资源窗口和唯一控制器。恢复前核对完整输入/源码/运行绑定和检查点，仅执行缺失阶段。

- 新训练使用完整预处理封印和训练守门，见[依赖与恢复审计](FULL_DEPENDENCY_AUDIT.md)。metadata级检查点不等于原始/HDF字节身份。
- v1/v2预测、published标签和失败状态保留；当前v3通过完整依赖与四hash seed门禁。更换机器或metadata路径可能改变种子和训练样本，不承诺新机器逐位同模型。
- SSB作者母体门禁仍失败；LOCAL成功不消除1,713项customer连接真值差异。不得改真值、执行闩锁或绕过守门。
- LOCAL SSB10M已完成，不能因历史文档“运行中”重启训练/逆序；实际事实样本9,996,946行、CI1,253可用/806排除，单样本不是重复抽样校准。
- 3B完整数据库须先证明容量可行性；已有样本不代表原表建样本和完整索引成本，见[资源说明](FULL_BASELINE_FEASIBILITY.md)。
- `.gitattributes`固定部分封存来源的字节，不全目录转换换行或覆盖上游。新实验独立命名，已验证结果不重复运行。

## 协议索引

| 内容 | 说明 |
|---|---|
| 论文定义与缺口 | [完整协议](FULL_REPRODUCTION_PROTOCOL.md)、[实际状态](FULL_REPRODUCTION_STATUS.md)、[四项输入缺口](FINAL_PUBLIC_INPUT_GAPS.md) |
| 参数与canonical推断 | [参数](FULL_PARAMETER_STUDIES.md)、[C++审计](FULL_CPP_V3_AUDIT.md) |
| MSCN | [官方](FULL_MSCN_PROTOCOL.md)、[核验](FULL_MSCN_VERIFY.md)、[一致样本重建](FULL_MSCN_REBUILT.md) |
| Flights | [模型](FULL_FLIGHTS_MODEL_RUN.md)、[parser外层](FULL_FLIGHTS_REPLAY_AUDIT.md)、[Verdict](FULL_VERDICT_PROTOCOL.md) |
| SSB生成与LOCAL模型 | [生成器](FULL_SSB_NATIVE_V2.md)、[LOCAL1M](FULL_SSB_LOCAL_REPLAY.md)、[continuation](FULL_SSB_LOCAL_CONTINUATION.md)、[LOCAL10M](FULL_SSB_LOCAL_CI_PROTOCOL.md)、[逆序](FULL_SSB_LOCAL_CI_REPLAY.md) |
| 比较方法 | [DBEst](FULL_DBEST_FLIGHTS_ROUTES.md)、[SRS/IBJS](FULL_JOB_SAMPLING_PROTOCOL.md)、[Scalar](FULL_SCALAR_ORACLE_PROTOCOL.md)、[LOCAL Verdict](FULL_VERDICT_LOCAL_SSB_IMPLEMENTATION.md)、[Verdict SF2](FULL_VERDICT_SSB_SF2_AUDIT.md) |

本地最终目标为 `README.md`与 `results/`，实际精简与清理状态见[清理凭据](../output/results/cleanup_status.json)。模型和必要大文件按最终清单处理；来源闭包移除后原fullF及其传递依赖必须退役。源码克隆可重新建立环境和数据，精简结果包仅提供其清单声明内容。
