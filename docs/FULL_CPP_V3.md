# Canonical v3 Native Differential Protocol

本任务仅新增 full_cpp_v3.py、对应测试、本协议与 output/full/cpp-v3/ 输出。
MSCN final_seal.json 已交付，SHA256 为
9940f798082156164fe6b1474026f60343b692115f0590e5220c0dcce4d70114。
旧 C++ v2 及所有模型、数组、生成源码、编译产物和封印均只读。

目标模型：paper_proxy_public_scale_rdc_n10000000_b0p5，六 SPN，原模型 SHA256
00c14f94cbedf038e45a7d22b54236b92026f1d39faed0839ce06a0c24710197。
父任务已发现 v2 与 canonical v3 有30/753条预测不同，因此旧 v2 seal 是历史证据，
不能直接作为当前 v3 的 native 差分证明。本任务不生成或编译任何 C++。

## 执行计划与门禁

1. 先写失败测试：空/缺失/多余 map、路径穿越与同长篡改、精确SQL/编号/真值、
   最终38模型四seed验收、三方预测与每查询native调用、计时分组完整性。
2. 只读preflight：核验旧外层/内层seal、全部旧目录文件、pyd/模型copy/数组/object
   hash、当前原模型/模板/生成器、v3完整依赖和runtime。验收未完成只记录preflight。
3. 正式运行必须先通过 full_canonical_acceptance 的最终38模型四进程验收，
   并绑定 canonical_final_acceptance.json、四seed上下文及目标753条CSV。
4. 独立子进程中，原模型用普通Python，带固定SPN id的旧模型copy用旧native；
   两者都运行 canonical_greedy_selection、physical-model cache和原range_adapter。
   每条查询先清因子缓存；一个完整预热round，至少3个正式round，交替模式顺序。
5. 每条正式记录以实际pybind函数成功返回计数，并保留GenCodeStats交叉核验；
   native调用map不可空、每查询调用至少1次，Python模式不得调用native。
   Python/native/当前v3 CSV三方误差门限 rtol=1e-9、atol=1e-7。
6. 保存753×3的逐条记录、源SQL字节hash、query identity、15个4–6表×1–5谓词
   单元的原计时口径、资源记录、源码快照与完整self-seal。前后核验整个旧cpp-scale
   目录和原模型字节不变。8GiB cap仅管理自己的验证子进程和后代，CPU库限制1线程。

total计时不含SQL parse，包含概率查询编译与因子求值；inference使用同一
rspn.expectation入口，包含证据/scope、条件转换和递归/native包装；native bridge
保留GenCodeStats原记录子集口径，含模块查找、native调用及NumPy包装，不含条件转换。
新增cpp_physical_native_ns/ms，以perf_counter_ns包围每一次原pybind导出函数成功调用，
含Python/C++参数与返回转换、实际native求值，不含模块查找、证据转换、NumPy包装或
计数器更新；Figure8的native主口径用这一完整物理调用wall，原五项计时并列保留。
共享机器上的计时不是论文硬件性能复现。本任务仍是公开70+683查询组件，
不等同作者原200条实验或整篇论文完成。

## 原统计漏记的实际失败证据

第一次实际warmup把作者stats.calls等同物理pybind调用数而失败，失败目录
model_00c14f94cbedf038_e4b3584d981afc1c完整保留。第二次仅加入诊断仍使用同一严格
条件，在model_00c14f94cbedf038_003a42a86a97b1a4保存native_counter_failure.json：
3_2_SPN查询35、SQL SHA256 cb658dcd9a45a0e1d87c693d3bad023baeccffb91414a0d8fd63a9aa4d07982c，
实际成功spn1调用2次，GenCodeStats.calls仅1。此处未发生预测数值门禁失败。
源码中存在没有转传gen_code_stats的路径，但本证据未定位该查询确切调用栈，
因此仅证明实际统计漏记，不声称已确定具体分支。

修正后以每个物理导出函数的成功返回hook为调用证据，保留upstream_stats_calls与
upstream_omitted_calls；禁止空map/无native fallback，Python模式出现任何native调用
仍失败，作者stats多于物理hook也失败。hook对成功调用同时累计完整wall；失败调用
不计入成功次数/成功wall。TDD_counter_FAIL/PASS.log与TDD_native_wall_FAIL/PASS.log
保存先失败后通过；wall回归包含多次成功、异常、reset和ns/ms不一致拒绝。

## 状态

2026-10-30正式运行与缓存复验完成，独立门禁PASS。所有38模型四seed最终验收及
verify_current(label,753)均实际核验，最终验收文件SHA256：
d86f48f53179b6b3f437e7cb937d3045cbd5fed6a2da539c34f5c0694c8da4b0。

新结果目录：output/full/cpp-v3/model_00c14f94cbedf038_ee5c9a24b443cb6d/。
verification.json SHA256：
1687f3ba3fbbcbdb86519cc1acdbd8beef583a7501083b2fd30d96c48fe9c90b。
永久runner SHA256：
7b15355542a3d34d217dc67d8cca056937cc2021f4ff97899712b41a010a04d0。

753条完整预热通过，再执行3轮、2,259对，Python/native/v3 CSV三方全部通过；
最大相对差1.0012468823284646e-15。正式物理native成功调用7,422次，每条每轮至少1次；
作者stats.calls为7,395，漏记27次，逐条map和差值保留。完整成功native wall累计
584,884,000ns。15个4–6表×1–5谓词单元均非空，包含413条独立查询、1,239对计时。

| 全753条每查询计时 | 均值ms | 中位数ms | p95 ms |
| --- | ---: | ---: | ---: |
| Python total | 17.7122 | 15.6744 | 36.6956 |
| C++ total | 3.0248 | 2.7168 | 5.7061 |
| Python expectation入口 | 15.0812 | 13.2660 | 32.5248 |
| C++ expectation入口 | 0.6007 | 0.4532 | 1.2711 |
| 原GenCodeStats bridge子集 | 0.3269 | 0.2653 | 0.6646 |
| 完整物理pybind成功调用wall | 0.2589 | 0.2065 | 0.5009 |

两项native时间的范围不同，bridge包含额外包装但漏记部分调用，不能据其大小推断
计时缺失量。Figure8分组完整数值见figure8_grouped_timings.json，均为当前共享主机。

资源监控实际118.1367秒，进程树RSS峰值1,137,213,440bytes（1,084.53125MiB），
8GiB保护未触发，编译进程0。只复用已封pyd/数组，pyd SHA256仍为
634c03f31b23ac4abcc2671db01f850f9a6bc67b80cfa4dfea42900fd467c715。
旧cpp-scale全部222文件、604,865,936bytes以及原模型SHA前后不变。

最终相关测试27项通过（0.98秒）。cache_reuse_check.py实际阻止启动worker和加载native
后再次verify，仍返回reused_verified_comparison=true，实际新增预测0；当前源/依赖/
验收/工作负载/旧asset hash与逐条记录仍重新核验。完整namespace含失败历史、TDD日志、
协议/测试/源码快照与缓存证明，另由最终final_seal.json封存；旧C++v2全部保留原字节。

## 重跑入口

在项目根目录使用现有Python3.8环境：

```powershell
.\.venv\Scripts\python.exe -B code/full_cpp_v3.py preflight
.\.venv\Scripts\python.exe -B code/full_cpp_v3.py verify --repetitions 3
.\.venv\Scripts\python.exe -B -m pytest code/tests/test_full_cpp_v3.py code/tests/test_full_factor_cache.py code/tests/test_full_stable_selection.py -q
```

相同科学source/input摘要仅校验并复用封存差分，不重新推理。任何实际输入、源码或
运行时差异均产生新namespace或失败；不会修改原模型、重新生成数组或自动编译。
cache_reuse_check.py是本轮审计脚本，不是跨仓库缺少data/model时可独立工作的入口。
full_paper_reproduction_complete始终为false。
