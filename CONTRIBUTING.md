# 协作约定

1. 克隆仓库，按 README 安装固定依赖，下载并校验原始数据。
2. 每人使用独立分支，例如 `feature/rdc-ensemble`、`experiment/ssb`，通过 Pull Request 合并。
3. 原始 CSV 留在 `data/`；模型、表格和日志留在 `output/`，不要提交虚拟环境和大文件。
4. 修改算法前记录训练样本量、随机种子、数据版本和运行命令。新实验用独立输出名称，保留已验证结果。
5. 提交前运行 `.venv/Scripts/python.exe -m pytest`。改动学习或推理后，还要重新训练或重新评估并复核结果。
6. 不把基础双表关系模型的结果写成论文优化版 RDC ensemble 的结果；不把示例查询检查写成全部真值重算。

仓库所有者可在 GitHub **Settings → Collaborators** 邀请组员。
公开访问不等于拥有直接推送权限；尚未指定组员，因此没有发送邀请。
