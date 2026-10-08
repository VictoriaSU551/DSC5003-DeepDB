原始数据目录。运行 `python code/download_data.py` 可恢复六张完整 JOB-light 表。

- 来源：CWI 保存的 JOB IMDb 快照，见 `manifest.json`。
- `imdb/`：六张 CSV；不删行、不按查询筛选训练数据。
- `manifest.json`：压缩包及每张表的字节数、SHA256；纳入版本控制。
- CSV 和下载压缩包不上传 GitHub。成功校验解压后自动删除压缩包。

此快照与当前 IMDb 在线数据不同；不要替换成新版 IMDb 后沿用原查询真值。
