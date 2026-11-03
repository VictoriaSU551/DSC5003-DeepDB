# 协作约定

1. 克隆仓库，按 README 安装固定依赖，下载并校验原始数据。
2. 每人使用独立分支，例如 `feature/rdc-ensemble`、`experiment/ssb`，通过 Pull Request 合并。
3. 原始 CSV 留在 `data/`；模型、表格和日志留在 `output/`，不要提交虚拟环境和大文件。
4. 修改算法前记录训练样本量、随机种子、数据版本和运行命令。新实验用独立输出名称，保留已验证结果。
5. 提交前运行 `.venv/Scripts/python.exe -m pytest`。改动学习或推理后，还要重新训练或重新评估并复核结果。
6. 不把基础双表关系模型的结果写成论文优化版 RDC ensemble 的结果；不把示例查询检查写成全部真值重算。

仓库所有者可在 GitHub **Settings → Collaborators** 邀请组员。
公开访问不等于拥有直接推送权限；尚未指定组员，因此没有发送邀请。

## 已同步实验的维护

- `main` 已收录 guoao 的 JOB-light 交付包；[结果与核验边界](docs/TEAM_EXPERIMENTS.md)是小组整理入口，贡献提交及署名保留。
- 修改文档或结果索引后，执行 `python -B output/results/guoao_experiments/verify_results.py --repo-root .` 和 `python -B output/results/guoao_experiments/verify_evidence.py`。改动算法仍执行上面的训练/重评要求。
- 原交付包的文件哈希受 `evidence/source_manifest.json` 约束；新实验使用新编号和独立结果目录，勿覆盖原预测、日志、图或来源证据。
- 模型清单不是模型本体。复训交接需要另外提供匹配指纹的本地模型、数据/HDF、环境和数据库配置；历史源码ZIP保持取证用途，不直接覆盖当前算法文件。
- 不把14组设置写成14套不同查询，不把8类中英文图写成16个实验，不把离线指标核验写成重新训练或重新运行数据库。
