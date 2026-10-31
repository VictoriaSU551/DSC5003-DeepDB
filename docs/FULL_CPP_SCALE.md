# 10M public-scale 模型的外部数组 C++ 适配

本文先保留 5-SPN `public_scale_rdc_n10000000_b0p5` 的完整历史门禁，后面的
“6-SPN 论文成本归一化代理模型”节记录继续执行的新任务。两种模型、缓存策略与
产物目录分别封印，不能将其中一轮计时或结论替代另一轮。

本阶段只验证已经训练并封印的 `public_scale_rdc_n10000000_b0p5` 模型的
C++ 推理。它使用全部 70 条 JOB-light 与 683 条公开分组查询，覆盖 Figure 8
所需的 4、5、6 表 × 1–5 谓词 15 个公开工作负载单元。公开 683 条查询并未被
认定为论文的确切 200 条测试集；本任务不是整篇论文复现完成的声明。

## 输入与只读边界

入口是 `code/full_cpp_scale.py`，独立的参数兼容适配在
`code/full_cpp_range_adapter.py`，输入训练回执为
`output/full/results/public_scale_rdc_n10000000_b0p5_training.json`。
入口要求训练状态 PASS、requested_samples=10,000,000、B=0.5、profile=public-scale，
并重新核对原模型摘要：

```text
7141cfcf881fe306de4c6c613c7000fe004fe9aaa67b55a77e6e826235f5c77f
```

该 public-scale 模型保留训练回执已记录的 full-outer-join population normalizer，
不是另行声称与作者未公开的训练种子、样本或 Figure 8 模型完全相同。
五个 SPN 中两个连接总体达到 10M 抽样；三个较小总体分别为 4,050,205、
3,448,422 和 4,523,930 行，使用其完整总体。适配没有降低已封印模型的样本量。

所有生成物写在 `output/full/cpp-scale/`。原模型、原 `generate_code.py`、所有
原模板、原 `full_cpp.py` 以及环境均不修改。只给输出目录中的模型副本分配 SPN ID。
编译使用已有 `.runtime/w64devkit/bin/g++.exe`、项目 pybind11 2.6.2 与 Python 3.8。

## 值与公式保持

先调用作者原 `generate_code(..., floating_data_type='double')`，完整保存每个 SPN 的
原始字面量方法到 `author_literals/`。随后只抽出三种常量数组：数值叶
`uniqueVals`、`probSum` 与类别叶 `probsNode`。严格接受十进制数值字面量，拒绝表达式，
逐值按原顺序写为小端 IEEE double；通用辅助函数也支持 float 并有逐位测试。
生产模型强制每个抽出数组都是 double，不压缩、不舍弃、不重新归一化。

每个原 SPN 方法置于独立翻译单元，共五个；小的 pybind 模块入口保持原注册内容。
抽出的数组变成函数内 `static const vector<double>`，首次实际需要时初始化一次。
`vector<double>::iterator` 改成与 const 容器匹配的 `const_iterator`；原二分查找、
加减乘除、权重、节点中间结果和推理公式保持原样。禁止 fast-math。

作者生成器在 double 模式仍声明 float 类型的数值条件端点参数，本适配保留该原签名。
因此 double 指常量数组与推理中间值，不能解读为修改了作者的全部参数精度。
当前使用已经在先前任务验证过的数值叶边界修复模板，其 SHA256 为
`ecc700ae2eee9b410dd06fdb3fee98f489ff7254bc7154f1f07355ae2de3aaee`；
本阶段不再编辑模板。

每个二进制记录全文件及逐数组 SHA256、偏移、数量、位宽和原字面量摘要。
C++ 在首次加载各 SPN 的二进制时检查大小、小端、位宽与 Windows BCrypt SHA256，
再通过 memcpy 恢复原值；同长度篡改也会抛错。Python 侧在生成缓存复用、编译、
载入及验证前检查 source/bin/model/template 摘要。原文件、带 ID 副本与扩展分别封印。

## 串行编译、资源保护与恢复

命令使用 `-O2 -std=c++11 -ftemplate-depth=2048 -D_GLIBCXX_ASSERTIONS`，
逐一编译五个 SPN 和模块入口，再链接；始终只有一个编译命令，不用并行 make。
只为子进程设置 PATH、PYTHONHASHSEED=1 和单线程数值库变量，不更改系统环境。
编译进程使用 below-normal 优先级。

Windows 标准库 ctypes 每 0.1 秒采样本工具启动的进程及其观察到的子进程，
持有稳定进程句柄，累加 resident working set。超过 8 GiB 时只终止这棵所属进程树，
保留命令、退出码、stdout/stderr、峰值和失败回执，绝不按进程名称杀其他训练。
此峰值是采样观测值，不能排除两次采样之间的短暂更高峰值。

每个 `.o` 有独立封印，绑定源代码、共享头、编译器、参数、Python/pybind11、
Python 导入库及对象摘要。只有这些一致的 PASS 对象才复用；因此中断后已完成的
SPN 不重编译。生成缓存同样检查全部输入和所有生成文件。验证缓存另绑定工作负载、
pairwise RDC、runner、重复数及结果文件摘要，不以文件存在代替有效性验证。

## 测试与差分门槛

先写六个测试，在实现不存在时实际得到 **6 failed**，随后实现并得到 **6 passed**。
测试覆盖 double/float 的精确二进制值（含负零和舍入边界）、禁止表达式且保护已有
二进制、同长度 SHA 篡改拒绝、真正编译运行的叶节点边界、所属进程内存保护，
以及 70+683 查询与 15 个 Figure 8 单元的对齐。

小模型的 Python 参考直接调用原 `identity_likelihood_range`，使用作者生成的叶代码
经外部数组适配后实际编译。12 例含 NULL、开闭端点、相等端点、无限边界和两侧域外；
同时在 C++ 可执行文件启动前翻转二进制一位，验证运行时拒绝同长度篡改。
相等端点继承参考 Python 的约定，不据此宣称独立证明全部 SQL 区间语义。
小模型门槛通过后才允许编译完整模型。

完整验证分别加载同一个带 ID 模型副本，Python 实例强制关闭生成代码，C++ 实例启用。
检查每条 SQL 与真值 CSV 的 query_no、语句及表/谓词数量；先完整预热一轮，再默认
三轮计时，每轮交替两种模式顺序。**每一条查询、每一种模式都先清空 factor cache。**
每对要求有限预测、rtol=1e-9 / atol=1e-7 一致且生成调用次数大于零。
还将 Python 预测逐条对照既有 753 条 public-scale 本地结果，作为独立历史一致性门禁。
正的生成调用数证明该查询实际经过原生调用，不证明每一种可能的因子都无需 Python 回退。

计时分别报告均值、中位数和 p95：

- total：SQL parse 后的 cardinality 查询编译、因子构造与求值。
- inference：两种模式在同一个原 `rspn.expectation` 入口处计时，包含 evidence /
  relevant-scope 处理、条件转换、递归或 native 求值与结果包装。
- C++ native bridge：原 GenCodeStats 的模块查找、native 调用与 NumPy 包装，
  不含其外的条件转换。该字段不能直接与 Python 的 inference 混为同一范围。

本机有独立长任务并行，结果是共享主机计时记录，不作为论文硬件速度复现。
计时输出为毫秒；不把毫秒误标成微秒，也不将总路径加速等同纯原生计算加速。

## 可执行命令与产物

从项目根目录运行：

```powershell
& '.venv/Scripts/python.exe' -B -m pytest -p no:cacheprovider code/tests/test_full_cpp_scale.py -q
& '.venv/Scripts/python.exe' -B code/full_cpp_scale.py all --repetitions 3
```

也支持 `boundary`、`prepare`、`build`、`verify` 独立阶段；verify 会先核验/复用构建。
本轮生成目录由输入绑定摘要派生为
`output/full/cpp-scale/public_scale_10m_double_d01024d1a4a5/`。
关键回执为该目录的 `generation.json`、逐单元 `compile_*.json` 和 `.seal.json`、
`build.json`、`verification.json`、`all_753_repeated.csv`、
`figure8_grouped_timings.json`，以及统一入口
`output/full/cpp-scale/public_scale_verification.json`。
实际运行状态与数值结论以这些回执为准，失败不得记为完成。

## 本轮已封印的生成规模

实际作者方法字面量总计 94,283,544 bytes；改写后源码（另加很小的模块入口）约
22.24MB；外部二进制 38,027,592 bytes。共抽出 4,303 个数组，4,753,449 个
double 值。这里报告实际测量值，不把编译前的体积风险估计当作实测规模。

| SPN | 原方法 bytes | 外部化后源码 bytes | 二进制 bytes | 数组数 | 值数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 65,062,301 | 6,010,230 | 30,574,504 | 1,001 | 3,821,813 |
| 1 | 16,866,638 | 7,915,231 | 5,003,824 | 1,816 | 625,478 |
| 2 | 5,661,751 | 5,408,216 | 186,072 | 836 | 23,259 |
| 3 | 3,058,263 | 2,907,354 | 116,464 | 648 | 14,558 |
| 4 | 3,634,591 | 3,594 | 2,146,728 | 2 | 268,341 |

小模型实际编译的 12 例 Python/C++ 最大相对差为 0，C++ 同长度二进制篡改拒绝通过。
编译进程树观测峰值 419,168,256 bytes，见
`output/full/cpp-scale/boundary_tdd/boundary_verification.json`。

## 2026-10-30 实际构建与首次完整验证

完整构建 PASS，六个翻译单元加链接共 553.22 秒，所属进程树观测峰值
1,555,673,088 bytes（1,483.6 MiB），没有触发 8 GiB 保护。
扩展 SHA256 为
`d7ad0da8621f1f19be34731055d8609a2d2b359182726165b32a3df8e9ef6986`。
原模型在完整生成、编译及验证后的 SHA256 均保持不变。

首次正式 **753 查询 × 3 轮 = 2,259 对**的严格差分状态为 **FAIL**：
四条公开三表查询每轮均不一致，共 12 对失败，其余 2,247 对通过。
每条至少一次原生调用，总原生调用 8,868 次。4–6 表 × 1–5 谓词的 15 个单元
在这次运行未出现不符，但不能以这个子集代替要求的完整 753 条验证门槛。
专属六项测试在该次完整运行后再次通过；测试 PASS 不等于完整模型差分 PASS。

| 公开组 | query_no（从 0 开始） | Python | 原转换路径 C++ |
| --- | ---: | ---: | ---: |
| 3_2_SPN | 20 | 758566.1980839616 | 5524002381.801513 |
| 3_2_SPN | 64 | 2620733.4156008866 | 15469149974.373411 |
| 3_4_SPN | 11 | 1.2709612165205666 | 4.318569388289856 |
| 3_4_SPN | 25 | 3236174.456926762 | 46540766959.4633 |

跟踪原 `rspn.expectation` 边界后，四条差异均来自 SPN0 的反转倍率因子。
上游 `code/rspn/code_generation/convert_conditions.py` 的 `_convert_real` 使用
`inverse = idx in inverted_features`，但调用方传入与 **有顺序的 feature_scope**
对应的布尔列表。例如 scope=[6,5,4]、flags=[False,False,True] 应反转列 4；
直接执行 `4 in [False,False,True]` 得到 False。外部数组值与该错误无关。

一次独立诊断进程只将有顺序的 `(scope, inverted_flag)` 转成实际反转列索引，
再交给原 convert_range；四条 C++ 预测全部逐值精确等于 Python，证明参数映射
是这四个失败的原因。这个诊断未改动任何原文件、数组、公式或正式扩展。
不能从布尔 feature mask 的 enumerate 次序重建原 feature_scope 次序；这项最初的
诊断假设已被否定并如实保留。完整跟踪与两个诊断结果在
`differential_failure_diagnostics.json`。

这一首次 FAIL、完整 CSV、15 个单元统计与诊断已封印保存在
`original_parameter_mapping_FAIL/`；它们仍是 FAIL，不被后续结果覆盖。

## 参数兼容修正与最终独立门禁

收到明确授权后，新增仅在本进程使用的 `full_cpp_range_adapter.py`。
适配器在原 expectation 入口保存有顺序的 scope/flags，只有进入原生转换器时才将
flags 换成实际列索引；Python 递归回退仍接收原布尔列表。ContextVar 隔离调用上下文，
finally 恢复两个原入口，且检查 scope/flag 长度、mask 一致性。
这是原生参数映射兼容修正，未改任何数值公式或原文件。

新增三个回归测试先实际得到 **3 failed**，实现后 **3 passed**，覆盖 [6,5,4]
等非升序 scope、真实原转换器、原 flags 与原源文件不变，以及异常后的入口恢复。
原 converter SHA256 前后一致：
`a1f5c0e2d3644b34a6ad5a19e39451f617b958a6fb993c08bd5aee55ecb9b255`。
适配器自己的 SHA256 独立加入验证封印，不改变已验证生成源码的摘要；六个编译对象
和扩展全部按源/模板/bin/编译参数摘要复用，没有重新大编译或伪造旧缓存。

最终再次完整预热一轮、计时三轮，**753 × 3 = 2,259 对冷缓存 Python/C++ 全部 PASS**。
最大相对差 `6.304221353344092e-16`，共 8,868 次原生调用，每条每轮至少一次。
原模型及原 converter SHA 均不变。15 个 Figure 8 单元共 413 条不同查询，分别
记录三轮的均值、中位数与 p95。最终 `status=PASS` 只覆盖这一差分与输入完整性门禁；
`historical_python_reference_gate=FAIL_ORDER_DEPENDENT` 仍明确单列，不能被总状态隐藏。

最终共享主机计时（毫秒；不作论文硬件速度比较）：

| 路径 | 均值 | 中位数 | p95 |
| --- | ---: | ---: | ---: |
| Python total | 17.9423 | 15.3507 | 39.7659 |
| C++ total | 3.0968 | 2.6760 | 5.7566 |
| Python inference，同一 expectation 入口 | 15.2371 | 12.8001 | 35.1513 |
| C++ inference，同一 expectation 入口 | 0.5707 | 0.4227 | 1.2441 |
| C++ native bridge，范围更窄 | 0.2782 | 0.2206 | 0.5865 |

## 既有结果的独立缓存审计

完整保留原 `full_evaluation.py` 及所有既有 CSV。只读重放其跨查询保留 factor cache
的策略时，**753/753 与既有 CSV 一致**；每查询清缓存时恰有 14 条不同，原生参数
映射修正前后均是同样的 14 条。两种策略不能混成同一参考结果。
`python_cache_policy_audit.json` 保存全部值与下面的直接实证：

- JOB-light q4 的物理 SPN1 将逆因子
  `/ E(title.mul_movie_keyword.movie_id * 1_{title.title_nn IS NOT NULL})`
  的值 `0.11461245279656225` 放入 hash `-2533464106076979638`。
- q43 使用同一因子字符串、同一 table_set=[]、同一 hash，但物理模型是 SPN0；
  在该模型直接求值为 `0.17102942198622903`。
- q43 返回的实际因子值仍是旧缓存 `0.11461245279656225`；因而旧 cardinality 为
  `348067.94428687723`，每查询清缓存为 `519401.32045673457`。

上游 `IndicatorExpectation.__hash__` 未包括实际物理 SPN，解释了这次跨模型复用。
本 CPP 任务没有修改原 hash、原 evaluator 或训练封印内文件，也没有覆盖既有预测。
正式 CPP 门禁只证明原查询内求值流程在每查询清缓存时两种模式一致；它不是对所有
因子公式和 SQL 语义的独立真值证明。更完整的缓存身份适配与重新命名的 Python 评估
属于根任务的独立 v2 工作。

加入参数映射后、尚未拆分历史一致性门禁时的完整运行也保留在
`corrected_mapping_cold_PASS_reference_FAIL/`，其数值比较 PASS、历史一致性 FAIL。
最终回执分别记录两个门禁，并绑定原历史 CSV 与缓存审计的摘要。

## 5-SPN 阶段的完整封存

5-SPN 最终相关测试为 **13 passed in 10.77s**：本模块九项，加既有 full_cpp 四项。
再次幂等检查确认生成、编译及完整比较全部复用摘要一致的 PASS 缓存，没有重算查询。
`sealed_public_scale_5spn.json` 封印统一回执、缓存检查与构建目录的 `final_seal.json`；
后者逐文件封印所有产物和原 FAIL，并在 `runner_snapshot/` 保留当时 runner、独立
range adapter、测试、协议及 full_cpp.py 的源快照。该构建目录从此不再写入。

## 6-SPN 论文成本归一化代理模型

继续使用已训练的 `paper_proxy_public_scale_rdc_n10000000_b0p5`，原模型 SHA256：

```text
00c14f94cbedf038e45a7d22b54236b92026f1d39faed0839ce06a0c24710197
```

它是根任务按论文基准成本代理归一化 B=0.5 选出的六个 SPN：一个
movie_companies/movie_info/title 三表 SPN，加上前述五个基础 SPN。
训练回执明确将成本定义为相同 requested row count 下的列数平方代理：
base_cost_columns_squared=539，single_cost_columns_squared=123，公开代码等效
factor=2.1910569105691056。此成本代理并不等于验证了论文未披露的精确机器实测成本。
不重训、不降低 10M requested samples；三个较小总体仍按原训练回执完整使用。

当前入口新增 `--training-label`，严格限制为字母、数字和下划线。
构建目录由完整 model SHA 与生成输入绑定摘要派生，使用短前缀避免 Windows 路径过长：
`output/full/cpp-scale/model_00c14f94cbedf038_94b1d6e702dc/`。
既有 5-SPN 目录、原回执、失败证据及其封印不覆盖。

新一轮 Python 与 C++ 都显式进入根任务已冻结的
`full_factor_cache.model_aware_factor_cache()`，并且每查询清空 cache；C++ 同时使用
独立 range adapter。缓存身份模块和原 hash 源文件摘要单独进入验证封印，原文件不改。
对照的是 `output/full/evaluation_v2/` 中同一训练模型的已封印 Python CSV。
若根任务复用数学上相同的有序组件，跟随其 `reused_from_label` 并验证其来源记录。
验证 v2 summary 的 model/protocol/query count、每份 CSV 摘要、SQL/query_no/真值
逐行对应及所有 helper SHA；旧 v1 CSV 不参与新模型的一致性门槛。

三个新增输入回归先 **3 failed**，实现后 **3 passed**：label 路径穿越拒绝、
模型 SHA 区分输出目录、v2 模型/CSV/helper/SQL 绑定和篡改拒绝。合并本模块十二项
与根任务冻结 cache 两项测试，当时 **14 passed in 6.83s**。

执行命令：

```powershell
& '.venv/Scripts/python.exe' -B code/full_cpp_scale.py all --training-label paper_proxy_public_scale_rdc_n10000000_b0p5 --repetitions 3
```

实测生成六个 SPN 的作者字面量源码 113,653,560 bytes，外部化后源码
38,218,042 bytes，二进制 40,032,128 bytes，共 5,004,016 个 double 值。
其中新增三表方法外部化后仍有约 15.96MB 源码，因此继续逐翻译单元串行编译并保留
8 GiB 观测上限；不以未经实测的内存估计代替编译回执。
此阶段只有实际编译、全部 753×3 差分、独立 v2 对齐和原模型不变均通过后才计 PASS。

本轮新增三表单元最初按 BelowNormal 创建；共享主机调度使约七分钟墙钟只获得
53 秒 CPU。根任务明确授权后，仅将本 runner 的 g++/cc1plus 恢复 Normal。
独立监督器使用已核验 runner PID 的稳定句柄及后代关系，只处理这两种所属编译进程，
后续串行单元同样调为 Normal，runner 退出后自动结束。
`compile_priority_override.json` 保存实际 PID、原/新 priority class 与时间。
逐命令回执中的 BelowNormal 是原创建参数；这一显式运行中覆盖记录才反映该轮实际
后续调度。未动其他训练进程、系统设置、单编译顺序或 8 GiB 保护。

6-SPN 最终实际结果：构建 **PASS**，七个翻译单元加链接共 **1,274.78 秒**；
进程树采样峰值 **2,732,068,864 bytes（2,605.5 MiB）**，来自 pybind 模块入口，
新增三表单元峰值为 1,201.4 MiB。原生扩展 SHA256：
`634c03f31b23ac4abcc2671db01f850f9a6bc67b80cfa4dfea42900fd467c715`。
正常优先级监督器随所属 runner 退出，`compile_priority_override.json` 状态 COMPLETE。

753 条完整预热后，三轮 **2,259 对全部 PASS**，最大相对差
`1.0012468823284646e-15`；总原生调用 **7,395**，每条每轮至少一次。
Python 与独立根任务 **v2 的 753 条 CSV 全部对齐**，v2 模型、源输入和 helper 摘要
均一致。原 6-SPN 模型和原 converter SHA 前后不变；旧 5-SPN 完整封印另行复核未变。
全部 15 个 4–6 表 × 1–5 谓词单元均有三轮计时。

| 6-SPN 路径 | 均值 ms | 中位数 ms | p95 ms |
| --- | ---: | ---: | ---: |
| Python total | 22.2904 | 19.5509 | 47.2182 |
| C++ total | 3.7482 | 3.2860 | 7.2902 |
| Python inference，同一 expectation 入口 | 19.0871 | 16.6008 | 42.2598 |
| C++ inference，同一 expectation 入口 | 0.7079 | 0.4234 | 2.2401 |
| C++ native bridge，范围更窄 | 0.3212 | 0.2170 | 0.9829 |

统一 6-SPN 回执为
`output/full/cpp-scale/model_00c14f94cbedf038_verification.json`，详情/逐查询 CSV/15 单元
统计在对应 model 子目录。保留 `full_paper_reproduction_complete=false`，没有将
公开 683 条工作负载等同于作者未标识的 200 条，也没有将本机共享计时当论文硬件复现。

最终相关测试 **18 passed in 319.74s**：本模块十二项、既有 full_cpp 四项与冻结
factor cache 两项。测试中的小边界编译起初仍使用 BelowNormal，随后只恢复了已经
核验属于该测试的两个编译进程到 Normal；测试墙钟不是推理计时。
`boundary_tdd/` 是可重跑测试目录，后续回归会更新其资源统计；6-SPN 封存时另行
复制当时的完整边界门槛与源文件。正式模型目录及其初次 FAIL/修正历史均独立封印。

