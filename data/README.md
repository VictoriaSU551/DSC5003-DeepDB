原始数据目录。运行 `python code/download_data.py` 可恢复六张完整 JOB-light 表。

- 来源：CWI 保存的 JOB IMDb 快照，见 `manifest.json`。
- `imdb/`：六张 CSV；不删行、不按查询筛选训练数据。
- `manifest.json`：压缩包及每张表的字节数、SHA256；纳入版本控制。
- CSV 和下载压缩包不上传 GitHub。成功校验解压后自动删除压缩包。

此快照与当前 IMDb 在线数据不同；不要替换成新版 IMDb 后沿用原查询真值。

完整阶段新增数据仍在本目录，输出另存于`output/full/`：

- `flights/`：固定原始输入、1B流式生成保留的Bernoulli样本；没有落完整1B事实表。
- `ssb/sf500_paper/`：首次失败母体的样本/维表，保留MISMATCH及诊断依赖，不用于正式作者母体模型。
- `ssb/sf500_native_v2/`：修正原生生成器的新维表和事实样本；全部作者真值及最终闭包通过后才可训练。
- `mscn/`：官方输入及本地一致样本重建输入，各自有独立来源/封印。
- `postgresql/`：项目内便携PostgreSQL的数据集群，非系统服务；数据不随Git分发。
- `dbest*/`、`verdict/`：隔离基线输入与构建材料；不上传缓存或运行环境。
- `downloads/`：被来源封印引用的固定归档，不随Git分发。

不要把任意一个已保留样本当成全部原始母体，也不要在生成期间读取增长中的样本训练。
不同阶段的具体来源与只读验收命令见[完整运行指南](../docs/FULL_RUNNING_GUIDE.md)。
