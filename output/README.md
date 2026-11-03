# 实验输出与交付

[全部扩展结果](results/FULL_PAPER_RESULTS.md)是表图和阶段状态入口；[公开摘要](results/fullpaper_summary.json)记录来源与SHA256。2026-11-03快照含31项派生交付文件，没有EVIDENCE_INVALID；**整篇论文仍未完成**，PENDING、作者母体失败与来源缺口保留。

| 路径 | 内容及适用范围 | GitHub交付 |
|---|---|---|
| `results/fullpaper_cardinality_*` | JOB-light配置、参数、增量、公开泛化及C++；作者值和本地值分别标注。 | CSV/PNG可公开 |
| `results/fullpaper_flights_*` | 实际1B本地母体AQP/CI、部分DBEst及已有样本Verdict，缺组和不支持项明确。 | CSV/PNG可公开 |
| `results/fullpaper_ssb_local_continuation_*` | LOCAL1M/table：复用已验收正向、新逆向及表图。 | CSV/PNG/来源JSON可公开 |
| `results/fullpaper_ssb_local_ci10m_*` | 五个新10M/table cap模型、逆序13载入/26调用、2,059点/4,118端点最大差0；事实样本9,996,946行，CI1,253可用/806排除。 | CSV/PNG/来源JSON可公开 |
| `results/fullpaper_additional_baselines.json`及Scalar/采样/DBEst报告 | 实际调用、覆盖、零估计、条件分母及计分政策。 | 可公开 |
| `results/guoao_experiments/` | guoao/breck1016的14组JOB-light、980预测、报告、选定压缩日志和来源取证。 | 原贡献字节、署名和协议保留 |
| `results/RESULTS.md`及原JOB-light结果 | 最初1M关系基础模型及重放记录。 | 小型结果可公开 |
| `full/` | 本地运行闭包、来源、正式工件、模型和派生表图。 | 不整体上传；只导出白名单到 `results/` |
| `models/`、`hdf/`、`logs/`、`tmp/` | 本地模型、预处理、日志和测试夹具。 | 默认不上传；组员审查后日志在其证据包单列 |

SSB的1,713项作者customer连接真值差异保留，LOCAL结果不替代作者母体。LOCAL Verdict SF500待最终验收，见[当前状态](../docs/FULL_REPRODUCTION_STATUS.md)；SF2接入不代替SF500。完整3B数据库、原表建样本和XDB等未执行比较不计完成。

组员包维护见 [TEAM_EXPERIMENTS.md](../docs/TEAM_EXPERIMENTS.md)，标准库离线复核无需数据/模型：

```powershell
python -B output/results/guoao_experiments/verify_results.py --repo-root .
python -B output/results/guoao_experiments/verify_evidence.py
```

PASS只表示保存数值与对应证据范围通过，不代表本次重训或重新执行数据库。模型清单不是13个模型本体随包交付。`.gitattributes`关闭原证据包换行转换；新增结果另建目录，不覆盖原包。

GitHub最终在 `main`交付源码和审查后共享结果；数据、模型本体、环境、数据库、PDF和凭据不上传。本地最终目标为根 `README.md`加 `results/`，实际保留集合以最终清单为准，当前不宣称清理完成。若历史来源闭包移除，fullF及其传递依赖入口须明确退役，摘要不能冒充现场完整验收。未确认去留的最终模型先安全保留。
