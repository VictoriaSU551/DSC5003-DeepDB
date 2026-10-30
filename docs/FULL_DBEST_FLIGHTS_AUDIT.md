# Frozen DBEst1B independent final audit

本层只读审计已完成的官方原DBEst 1B population/20K fit实验，不拟合、积分、重算tiny，
不修改`full_dbest.py`、`full_dbest_flights.py`、原模型、原query、原verification或原seal。
消费者应运行本层`verify`，不再以旧`full_dbest_flights.verify()`为最终有效性标准。

旧verify只遍历seal现有map，空map可导致真空通过；source_binding又没有wrapper自身源码，
因而旧执行器中断后改wrapper可能复用旧缓存再写新wrapperSHA。
本层独立固定已由review逐项核对的完成工件，不从当前任意seal自动重新学习可信pin。

固定边界：

- 原verification_seal文件SHA：`2c0d86b156fa1da40a68180ae9a9fb54a7e79992fd5c027333bc76117e6c84c1`。
- 规范化256项manifest摘要：`841bdc9866326bccbdef382d48a9344b1d4b24fa5c57fc3af517c2ccfefc0b73`。
- 原verification文件SHA：`de73e1110d7299e8fdd092e0ab2e0502b8502da783a0e35602889b2e56159b30`。
- 冻结wrapper SHA：`2c690c33c8b875a9794addaf2143f2b6e1d8f0e2da145cef9a5da4ee13e54073`。
- 完整611项依赖摘要：`f0b369776c4a8d95e4973964f11a357427980805755bc1cf4bdb46ed07304edc`。

256项必需集合由代码独立列出：主report、selection seal/pickle、training metadata共4项，
12query加12seal共24项，76个固定group的模型pkl/metadata/积分JSON共228项。
精确等于256，非空、无缺少/多余；JSON重复键在变成dict之前拒绝，路径分隔符规范化后重复也拒绝。
models/integrals目录实际文件集合也必须精确相同。随后校验每个物理文件SHA。
611项加入原seal、冻结wrapper、582MB retained sample及原report已绑定的输入/348项受保护来源、
原200K输入/模型/环境/代码等依赖；完整摘要另有固定常量，不能任意少列。

内容门禁同时要求真实1B母体、9,997,912保留样本、20K唯一uniform retained-row IDs、seed74131、
76真实native aggregate调用/429156 KDE evaluations、76个固定model group、12个完整查询且8类UNSUPPORTED，
峰值<=512MiB；F4.1 DE缺训练样本仍为null/coverage gap。独立检查selection pickle的ID实际等于
固定seed的random.sample结果，重核每组metadata、原始query与评估report/model/integral的一致性。
F1/F3仅使用原stream已提供的pre-range COUNT；F4母体N必须来自全retained-state count/.01，
不是查询distance过滤后的truth COUNT。没有再训练，也没有新调用原KDE积分。

新的`output/full/dbest_flights_audit/verification.json`及`verification_seal.json`自封印report、
auditor源码、源manifest摘要、完整依赖摘要和精确必需集合；`verify`重新只读审计实际文件，
不会只遍历新report声明的map。即便把新report的map清空后重新计算外层reportSHA，仍必须失败。

```powershell
.venv/Scripts/python.exe -B code/full_dbest_flights_audit.py audit
.venv/Scripts/python.exe -B code/full_dbest_flights_audit.py verify
.venv/Scripts/python.exe -B code/full_dbest_flights_audit.py recovery-gate
```

`recovery-gate`首先核对冻结wrapper pin，在打开任何cache manifest前拒绝wrapper变更；
随后只读验证冻结namespace当前存在的工件，列出缺项，不执行恢复。
今后的partial recovery必须先调用该守门，变化的wrapper必须使用源码版本绑定的新namespace，
不能在本已完成的冻结科学目录内重盖seal。直接使用旧执行器的结果不被本最终audit接纳。
当前所有256项均存在且通过，本层没有实际执行partial recovery。

11个初始测试先全部失败（模块不存在）后通过；另加入重新计算外层selfseal但清空科学map的拒绝回归。
门禁覆盖空/少/多/规范路径重复/JSON重复/物理篡改、wrapper变更、1B/20K/76calls降格，以及真实完成工件。
结果仍为`PASS_WITH_GAPS`：这是实际原引擎在1B母体、20K子样本上的结果，
不是已恢复论文DBEst训练规模/配置或原规模训练性能；8类查询和DE coverage gap继续明确保留。
