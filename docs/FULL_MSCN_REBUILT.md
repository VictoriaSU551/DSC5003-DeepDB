# MSCN Consistent Bitmap Rebuild Implementation Plan

> 本文同时是独立重建协议。按 executing-plans 与 TDD 逐阶段执行；不 commit/push。

**Goal:** 为完整六表统一固定样本，重建 100K 训练、JOB70、683 公开泛化查询的位图，
训练独立 seed1/100epoch MSCN，保留官方模型和全部 CPP 封印。

**Architecture:** 从已封印 public-scale 完整 HDF 每表均匀无放回取 1000 行，保留抽样顺序、
HDF 位置、主键、原始值与 SQL NULL 值。以向量谓词计算 bitmap，并用独立 SQLite 逐表 SQL
交叉验证；完全沿用官方训练词表、SetConv、标签归一化、q-error 损失和可恢复检查点。

**Tech Stack:** 准备阶段使用既有 `.venv` 的 pandas/PyTables/NumPy，训练使用冻结的
`.venv-mscn`（Python3.8.20、NumPy1.24.4、Torch1.13.1+cpu），SQLite 与 I/O 使用标准库。

**Spec:** 根任务 2026-10-30 明确授权的独立 rebuilt MSCN 任务；原模块及原数据只读。

## Global Constraints

- 仅修改 `code/full_mscn_rebuilt.py`、`code/tests/test_full_mscn_rebuilt.py` 和本协议。
- 数据仅写 `data/mscn/rebuilt/`，运行输出和检查点仅写
  `output/full/mscn/rebuilt_seed1/results/`（测试使用独立临时目录）。
- 原 `full_mscn.py`、官方 100K/70/500 数据、环境、原训练与 CPP 封印完全保留。
- 训练为 seed1、100epochs、CPU4、batch1024、hidden256、Adam lr0.001，前90K训练后10K验证，不洗牌。
- 先完整100K单epoch、有限参数/Adam/RNG恢复门禁，再从2继续100，绝不重跑已提交epoch1。
- 独立重建不能命名为作者原 bitmap、原模型或未标识的200条论文实验。

## Review Focus

- NULL 哨兵不得作为真实 production_year，带谓词 unknown 不通过，无谓词全通过。
- 非训练支持的谓词不能被静默编码；整数闭区间转换必须逐样本证明与原 SQL 等价。
- bitmap 表顺序与字节高位优先必须和 CSV/样本顺序一致，别名必须解析到真实表。
- 源 SQL/真值、训练词表、1000个主键/顺序、全部位图必须形成联合摘要，不能混用旧500scale。
- 异常/中断不能覆盖最后提交检查点；恢复必须还原模型、Adam与三种 RNG。

## 已核实的输入事实

完整 public-scale HDF 位于 `output/full/prepared/public-scale/hdf/`，上游封印为
`output/full/checkpoints/prepared_public-scale.json`。六表都是 table-format 的完整 HDF：
title 2,528,312；cast_info 36,244,344；movie_info 14,835,720；movie_info_idx 1,380,035；
movie_keyword 4,523,930；movie_companies 2,609,129 行。只用这些完整文件，不用 `_sampled.hdf`。
cast 的 public-scale 版本包含 person_id。HDF 顺序有时并非主键排序，因此持久化物理位置和主键。

元数据以 `null_values_column` 对应 `relevant_attributes_full`，数值 NULL 为原准备器的
mean+0.0001。title.production_year 当前哨兵为 `1992.7887619952553`；准备时已断言它不与
真实值冲突。本任务按元数据恢复 NULL，不能将其当作真实1992年。

官方100K训练已含全部六表、九种谓词列（含 ci.person_id）与三个操作符 `=`, `>`, `<`。
因此新模型直接沿用原训练词表和官方 minmax 文件，不使用评估标签扩词表或归一化。
标签归一化仍按官方整份100K训练输入确定。所有泛化符号必须在训练词表内，缺失即失败。

## 阶段 1：样本与谓词金标准

接口：`sample_positions(length, table, seed=1, count=1000)` 用表名与 seed 派生独立
stdlib Random 流，无放回均匀抽样，O(1000) 内存，绝不创建3600万行的随机排列。
按物理位置分块读 HDF，再恢复抽取顺序；采样 RNG 不接触训练全局 RNG。

接口：`predicate_bitmap(sample, predicates)` 对原始值及显式 NULL mask 求向量布尔值；
`sqlite_bitmap(sample, predicates)` 独立建立真实 NULL 的固定样本 SQL 表，以 SELECT 槽位
产生金标准。共享的是样本与谓词输入，不复制向量比较代码。

- [x] 先写失败测试：NULL、严格/闭边界、多谓词、无谓词、空结果、别名、bit order。
- [x] 实现只接受明确支持的比较；整数 `<=k` 可映射 `<k+1`、`>=k` 可映射 `>k-1`，
  拒绝非整数/溢出边界，并逐样本以原 SQLite 条件验证等价。
- [x] 固定每表1000行，保存位置、主键、全部源列、SQL NULL、顺序与来源摘要。
- [x] 源 HDF/元数据与原完整准备封印 SHA 一致，缓存样本校验自身摘要。

## 阶段 2：全部统一位图与编码

接口：`prepare_rebuilt()` 保存独立 `data/train.csv/.bitmaps`、minmax副本与
`workloads/job-light.csv/.bitmaps`、`workloads/public-grouped.csv/.bitmaps`，
另外保存公开组/行号追踪。源官方 CSV 与公开 SQL/真值保持只读。
按每行 table 顺序写 little-endian uint32 数量和每表125字节，样本 index0 对应字节最高位。
对每种不同的“真实表+本表谓词集”用 SQLite 核验，可复用完全相同的已核验结果。
每个查询另存源、真值、顺序、样本封印、bitmap记录的联合摘要。

- [x] 先失败测试：错 alias/未声明列/未知操作符/表顺序/同长位图篡改/封印拒绝。
- [x] 100000+70+683 查询逐表计算并核验，保存完整计数与 source manifest。
- [x] 保存官方训练的排序词表、minmax 摘要与编码规则；全部公开查询无未知符号。
- [x] 幂等重跑只复用全部输入和输出摘要一致的 PASS 材料，禁止只看文件存在。

## 阶段 3：独立训练与恢复

复用冻结 `full_mscn.prepare_datasets`、`BitmapDataset`、`setup_runtime`、
`model_and_optimizer`、官方 qerror_loss、`save_training_checkpoint`、
`restore_training_checkpoint`、`checkpoint_record`、`pending_epochs` 与 `run_lock`。
只新增 rebuilt 绑定/路径与逐epoch有限性门槛，不修改原包装器或原训练目录。
绑定包括本模块 SHA、原包装器/vendor SHA、pinned runtime、数值协议、样本/位图/编码封印
与训练参数；本文可追加实测结果，不把解释性文档字节当成训练算法变更。

- [x] 回归测试证明模型、Adam、Python/NumPy/Torch RNG 恢复后的下一更新完全相同。
- [x] 完整100K的一轮训练先提交epoch1，检查 loss、模型与 Adam 有限，并在同一配置下
  用下一完整batch比较连续更新与从已封印epoch1恢复的更新；保留独立门禁。
- [ ] 门禁通过自动以100为累计目标，从2继续，逐epoch原子提交，不重算已完成epoch。

## 阶段 4：753条与分组评估

- [ ] 100epochs后从封印模型评估 JOB70+683；查询/真值/位图联合来源逐条校验。
- [ ] 输出每条预测与 qerror，另报4–6表×1–5谓词15组及全部组的指标与样本来源。
- [ ] 独立检查样本、原模型/官方输入与 CPP 封印未变；报告实际状态和任何真实缺口。

以下记录实际阶段结果。完整100epoch与753条最终评估只有实际完成后才能标为完成。

## 已完成的真实门槛

新测试按阶段实际先失败，再通过：7个纯数据测试、1个 Torch 恢复测试、6个SQL/联合摘要测试、
1个非有限状态测试。冻结的 `.venv-mscn` 最终 **15 passed in 3.72s**。
纯位图测试也在原 `.venv` 的 NumPy 版本下通过。

全量准备 PASS，`data/mscn/rebuilt/manifest.json` 保存45个源查询/真值/minmax文件、
七个完整 HDF/元数据摘要、六份样本、编码、三个 CSV/bitmap/joint 文件及阶段回执。
train.csv、JOB CSV 和 minmax 副本与官方原文件逐字节一致；全部 bitmap 为重新计算。

| 输入 | 查询数 | 逐表位图引用 | 新的独立 SQLite 谓词集核验 |
| --- | ---: | ---: | ---: |
| 官方训练 | 100,000 | 216,476 | 61,246 |
| JOB-light | 70 | 254 | 17 |
| 公开泛化 | 683 | 2,684 | 498 |
| 合计 | 100,753 | 219,414 | 61,761 |

相同“物理表+谓词集”复用此前已核验的同一固定样本结果；不重复执行相同 SQL。
所有实际源操作符均为 `=`, `>`, `<`，因此生产中的闭边界转换计数为0；该能力已由
独立 SQLite 单元用例验证，不能声称实际数据使用了原本不存在的闭边界查询。

title 的固定1000行中有20行 NULL 年份，原哨兵正确恢复为 None/SQL NULL。
样本总封印 SHA256：

```text
b008866db64b1876dd2078cb73a89d1176982f59d3a42a3e8ddf90a4d34a4103
```

编码封印：`eb7f911e5815679e9e8e05c9199a2b63891fac8843ee459f0c8e4776099be869`。
每行 joint 摘要绑定源行/SQL/真值、表顺序、样本与 bitmap；阶段回执再将其与编码摘要联合，
最终 data manifest 和训练 checkpoint 绑定整个图。无旧500scale位图参与生成或训练。

完整100K输入按原协议前90K训练、后10K验证。首轮88个batch，用时73.8614秒，
mean-of-batches loss=89.99336991526864，模型与 Adam 状态均有限。
`epoch1_gate.json` 验证真实下一完整batch的连续/恢复更新及三种 RNG 全部精确相同；
门禁中的额外更新仅在内存进行，随后还原epoch1，不作为训练epoch或新checkpoint提交。

首轮 checkpoint SHA256：

```text
daaba98c1c853b50618d21dd386f95174fd0f1bcb1820ee4168bf753328ca9f8
```

绑定 SHA256：`ab773a425149511ddafa49630694ba9469d6141e9fa7e78125d48508329f3d90`。
源码在训练开始前冻结；协议说明可追加实测结果，不改变数值协议或该绑定。
已经以100为累计目标启动，从epoch2继续，每个epoch原子提交，结束后自动评估JOB70+683。
在最终 evaluation.json 出现之前，状态仍是独立模型训练中，不能记作100epoch完成。

## 命令和恢复

从项目根目录运行：

```powershell
& '.venv/Scripts/python.exe' -B code/full_mscn_rebuilt.py prepare
& '.venv-mscn/Scripts/python.exe' -B -m pytest -p no:cacheprovider code/tests/test_full_mscn_rebuilt.py -q
& '.venv-mscn/Scripts/python.exe' -B code/full_mscn_rebuilt.py train --epochs 1
& '.venv-mscn/Scripts/python.exe' -B code/full_mscn_rebuilt.py all
```

`all` 对已有 PASS 数据只核对封印，从最后提交epoch继续到100并评估；不重跑epoch1。
已有完整且摘要一致的评估也复用。单独 `evaluate` 要求100个提交epoch与首轮门禁。
运行目录为 `output/full/mscn/rebuilt_seed1/results/`，其中保存 `.log`、`binding.json`、
`epoch1_gate.json`、`history.json`、`training_state.json`、`checkpoints/latest.json`
及逐epoch `.pt`。每个checkpoint包括 Adam和三RNG；模型空间统计与checkpoint空间分开。

原 official 运行仍使用自己的目录和文件锁，不与这里共享检查点。
数据/训练绑定同时记录并复核原 `full_mscn.py`、两份 CPP 外层封印及其原模型 SHA，
不会通过新任务修改它们。最终指标和15个公开泛化单元将在训练真实完成后记录。

## 续跑审计与真值口径

`resume_and_materialization_check.json` 已实测 PASS：再次 `prepare_rebuilt()` 只复用
摘要一致的材料；epoch1 SHA 保持不变；当前训练源码仍等于 checkpoint binding；
正式续跑日志首项是 epoch2。审计时已连续提交1至7轮；之后训练继续逐轮原子提交。
该检查没有重新抽样、重算已核验位图或重训epoch1。

根任务另行对683条公开 SQL 的本地完整表 COUNT 做独立审计，初步发现74条 published
truth 与本地数据不一致（最终结论以根任务 SQL 凭据为准）。本任务冻结的 published
truth、训练和位图完全保留；最终 `evaluation.json` 及分组 CSV 仍明确使用这些原始
published truth。若后续采用本地独立核验真值，应从同一份已保存预测另输出指标，
不覆盖原评估、不重新训练、也不重做预测。逐表1000行样本的 SQLite 位图金标准与
完整六表 join COUNT 真值是不同门禁，不能用前者替代后者。
