# 协作约定

`main`为代码和审查后共享结果的最终交付入口；扩展整合见[PR #3](https://github.com/VictoriaSU551/DSC5003-DeepDB/pull/3)。按[README](README.md)准备环境和数据，独立分支/PR协作，不提交环境、数据/HDF、大型模型、数据库、PDF、凭据或私人文件。

## 改动与测试

1. 先读[状态](docs/FULL_REPRODUCTION_STATUS.md)、对应实验协议和来源封印，复用已经完成且验证的结果。
2. 新实验使用独立配置/运行编号/输出目录，记录输入摘要、实际样本量、种子、预算、版本、命令和调用数；保留原标签、预测、失败及恢复点，不覆盖或静默重评分。
3. 文档改动检查链接、数字、来源和范围。代码改动选择对应纯/合成测试；基础回归只运行以下两个文件：

```powershell
.venv/Scripts/python.exe -B -m pytest code/tests/test_learning.py code/tests/test_preparation.py
```

4. **不把不带文件选择的完整pytest用作例行检查。** `code/tests/`含原生编译、实际生成器、数据库和科学接入。确需这些门禁时先确认任务授权、资源、既有工件及唯一控制器；不得关闭实时操作守门来通过测试。
5. 学习/推断语义改变先写有意义的失败回归，再修复；只对被改变的独立实验安排必要重训/重评，原结果保留。纯测试不等于正式科学执行通过。
6. `.gitattributes`固定部分来源原字节，不全目录转换换行或格式化冻结provider/上游；消费者改动使用独立适配，保留完整验收契约。

## 结果表述

- 作者历史数字、本地结果、小黄金、合成夹具及待完成阶段分别标明。基础关系模型不能称为优化RDC ensemble；公开683条/4–6表413条不能称作者200条。
- LOCAL SSB有1,713项作者customer连接真值差异；10M/table cap的事实表实际9,996,946行，CI1,253可用/806排除。不声称作者母体、恰好10M事实行或重复抽样校准已复现。
- 原零估计、无穷大q-error、缺组、非有限值、条件分母和不支持项保留。Scalar的floor1不与SRS/IBJS零值无穷大政策静默共榜。
- 已有样本Verdict/DBEst执行不替代原表建样本及3B数据库端到端成本；计时使用实际测量范围，中央90%与原生95%CI分开。
- `full_paper_complete`保持false，直至[全部完成条件](docs/FULL_REPRODUCTION_PROTOCOL.md)满足；四项缺口见[公开材料复核](docs/FINAL_PUBLIC_INPUT_GAPS.md)。

## 组员交付维护

guoao贡献署名 `breck1016`，原提交和文件保留，入口为 [TEAM_EXPERIMENTS.md](docs/TEAM_EXPERIMENTS.md)。14组设置共用70条不同SQL，不是14套查询；16张中英文图对应8类图，不计为16个实验。

改动索引或分析后，执行下列只读核验，不改受 `evidence/source_manifest.json`约束的原文件：

```powershell
python -B output/results/guoao_experiments/verify_results.py --repo-root .
python -B output/results/guoao_experiments/verify_evidence.py
```

清单不是模型本体；端到端复训仍需匹配数据/HDF、模型、环境和数据库。历史源码ZIP仅作来源取证，不覆盖当前算法。整合、离线核验和绘图不计新增训练或数据库执行。

## 本地整理与发布

共享结果在 `output/results/`，完整本地工件在 `output/full/`等路径，见[输出说明](output/README.md)。本地最终目标为 `README.md`加 `results/`；清理依据最终清单，不能凭旧候选删除当前引用工件或最终模型。

来源闭包移除时，明确退役相关fullF及其传递依赖，保留验收时间、哈希和退役边界。摘要不代替已移除数据的现场完整验收。权限和邀请由仓库所有者在GitHub设置管理，公开可读不代表直接推送权限。
