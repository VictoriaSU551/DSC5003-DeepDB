实验输出目录。

- `results/`：每条查询的估计、真值、耗时，以及复核记录；小文件可上传仓库。
- `models/`：已训练模型，保留供重新评估；不上传 GitHub。
- `logs/`：正式运行日志；不上传 GitHub。
- `hdf/`：保留最终使用的预处理数据，仅将不再引用的旧版本列为清理候选。

`results/verification_1000000.json` 的 PASS 仅表示本次 JOB-light 基础模型流程与数值复核通过，
不表示论文所有实验和最优性能均已复现。

`results/fullpaper_sampling_predictions_scored.csv`保留两种LOCAL采样方法的全部140条预测，
`fullpaper_sampling_method_costs.csv`和`fullpaper_sampling_RESULTS.md`分别说明耗时口径与评分范围。
`fullpaper_sampling_manifest.json`绑定三个文件及其已验收本地来源，公开文件与对应来源逐字节相同。
没有公开原始表、模型或运行环境，也不把两种LOCAL配置当作作者Table1原配置。

`results/fullpaper_ssb_local_continuation_*`为已接纳SSB接续事务的3张最终数据表、2张图及来源哈希记录。
范围是LOCAL SF500/1M每表模型，保留2059组及1713项作者真值差异；独立10M训练阶段另行验收。

完整阶段单独放在`full/`，与上述首阶段结果隔离：

- `full/completion_status.json`：从既有凭据重建的覆盖状态；整篇论文未完成时明确标记`INCOMPLETE_FULL_PAPER`。
- `full/models/`、`full/prepared/`及各实验的嵌套目录：保留最终已接纳模型和必要的最终处理数据。
  训练中间checkpoint、失败运行、重复源码副本和过期恢复目录属于清理候选。
  删除历史闭包依赖前应明确退役对应旧验收入口，不能删除后仍声称旧封印可完整回放。
- `full/evaluation_v3/`及`full/cpp-v3/`：当前canonical推断及原生差分结果；过期v1/v2列入待清理候选。
- `full/flights*/`、`full/mscn/`、`full/dbest*/`、`full/verdict/`：数据集/方法各自的正式证据。
- `full/ssb/native_v2/`、`native_v2_models/`、`native_v2_replay/`：修正SSB生成、模型与独立重放命名空间。
  目录或候选代码存在不等于实际训练/重放已经完成；以严格验收结果为准。
- `full/figures/`：按输入摘要分目录的派生表图；`full/results/*_latest.json`指向当前已接纳版本。
- `tmp/`：有界测试夹具，相关测试/审查结束后清理；保留必要的正式测试源。

本轮已盘点131,008个文件（不含`.git`），约46.24GB。清理请求被系统自动审批以
`blocked by policy`拒绝，缓存和失败目录仍在，尚未完成删除。
两个原汇总草稿已补齐为正式采样消费者的代码、测试和协议，已验收提交。
最近一次清理9个已结束的测试临时目录也被同一审批拒绝，实际删除仍为0。
详细保留路径、待清理类别和拒绝记录见`full/results/cleanup_plan_current.json`。
其中TAINTED canonical父目录包含已验收的`forward/`及`forward_control/`，不可整目录删除。
不把“未能删除”解释为这些中间产物都必须保留。

`results/fullpaper_*`是显式白名单导出的协作快照，只含派生CSV/PNG及状态摘要；
不发布数据、模型、环境、PDF或未接纳的结果。日常验收命令见[运行指南](../docs/FULL_RUNNING_GUIDE.md)。
