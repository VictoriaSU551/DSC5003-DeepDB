实验输出目录。

- `results/`：每条查询的估计、真值、耗时，以及复核记录；小文件可上传仓库。
- `models/`：已训练模型，保留供重新评估；不上传 GitHub。
- `logs/`：正式运行日志；不上传 GitHub。
- `hdf/`：可重新生成的预处理数据；最终核验后可以删除。

`results/verification_1000000.json` 的 PASS 仅表示本次 JOB-light 基础模型流程与数值复核通过，
不表示论文所有实验和最优性能均已复现。

完整阶段单独放在`full/`，与上述首阶段结果隔离：

- `full/completion_status.json`：从既有凭据重建的覆盖状态；整篇论文未完成时明确标记`INCOMPLETE_FULL_PAPER`。
- `full/models/`、`full/prepared/`、`full/checkpoints/`及各实验的嵌套目录：正式模型、HDF和恢复依赖。
  即使它们可以重建，也不能在仍被最终封印/恢复点引用时删除。
- `full/evaluation_v3/`及`full/cpp-v3/`：当前canonical推断及原生差分证据；v1/v2另保留为历史。
- `full/flights*/`、`full/mscn/`、`full/dbest*/`、`full/verdict/`：数据集/方法各自的正式证据。
- `full/ssb/native_v2/`、`native_v2_models/`、`native_v2_replay/`：修正SSB生成、模型与独立重放命名空间。
  目录或候选代码存在不等于实际训练/重放已经完成；以严格验收结果为准。
- `full/figures/`：按输入摘要分目录的派生表图；`full/results/*_latest.json`指向当前已接纳版本。
- `tmp/`：有界测试夹具，相关测试/审查结束后清理；保留必要的正式测试源。

`results/fullpaper_*`是显式白名单导出的协作快照，只含派生CSV/PNG及状态摘要；
不发布数据、模型、环境、PDF或未接纳的结果。日常验收命令见[运行指南](../docs/FULL_RUNNING_GUIDE.md)。
