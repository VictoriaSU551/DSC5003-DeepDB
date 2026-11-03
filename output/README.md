# 实验输出

公开结果和本地大文件分开保存，数据及模型本体不随GitHub分发。

| 目录或文件 | 内容 | GitHub交付 |
|---|---|---|
| `results/guoao_experiments/` | guoao的JOB-light实验表格、16张中英文图、2份报告、配置、37段选定压缩日志和历史源码取证 | 已同步，保留原贡献文件字节 |
| `results/guoao_integration_audit.json` | 2026-11-03同步核验：来源提交、36文件指纹、14组设置/980预测、核验边界 | 可公开 |
| `results/RESULTS.md`及原JOB-light结果 | 最初1M关系基础模型的结果和重放记录 | 小型结果可公开，原记录保留 |
| `models/` | 本地已训练模型，供重评和重放 | 不上传 |
| `hdf/` | 最终使用的预处理数据 | 保留在本地，仅清理确认不再引用的旧版本 |
| `logs/` | 本地正式运行日志 | 默认不上传；经脱敏、筛选和指纹绑定的组员交付日志单列在上述证据包 |
| `full/` | 扩展复现的本地模型、最终处理数据、运行证据和派生图表 | 大文件不上传；相应代码/小型导出见扩展分支 |
| `tmp/` | 有界测试夹具和临时产物 | 不上传；完成后按实际可执行的清理规则处理 |

先读[组员中文报告](results/guoao_experiments/report_zh.md)及[详细汇总](../docs/TEAM_EXPERIMENTS.md)。证据包按SHA256保存原字节，`.gitattributes`对该目录关闭换行符转换，避免Windows/Linux检出改变哈希。后续新增运行另建目录，不覆盖原包。

离线复核无需下载原数据或模型：

```powershell
python -B output/results/guoao_experiments/verify_results.py --repo-root .
python -B output/results/guoao_experiments/verify_evidence.py
```

`PASS`表示相应核验范围通过，不表示本次重训、重新执行数据库或完整论文复现。
13个组员模型本体不在包中，清单核对不能代替模型加载重放。

扩展结果 `results/fullpaper_*` 及完整协议在[reproduction/full-paper分支](https://github.com/VictoriaSU551/DSC5003-DeepDB/tree/reproduction/full-paper)，与本批70查询结果分别保留。其本地历史清理与运行状态见该分支记录；本文件不宣称本地临时产物已经全部删除。
