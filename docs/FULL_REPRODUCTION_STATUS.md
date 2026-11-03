# 完整复现阶段状态

更新：2026-11-03。当前状态为 `INCOMPLETE_FULL_PAPER`，`full_paper_complete=false`。
[公开结果索引](../output/results/FULL_PAPER_RESULTS.md)及[摘要](../output/results/fullpaper_summary.json)来源于 `2026-11-03T14:44:58.354882+00:00` 的封存状态：31项派生交付文件，没有EVIDENCE_INVALID；待完成、作者母体失败和输入缺口仍保留。PASS仅适用于各自命名的实验及验收范围。

## 已完成并保留的实验

| 范围 | 实际执行与核验 | 证据入口 |
|---|---|---|
| 基础JOB-light与真值 | 原1M五关系基础模型保留；六张完整IMDb表在PG11.5导入，70条真值独立核对。 | [原结果](../output/results/RESULTS.md)、[基数实验表](../output/results/fullpaper_cardinality_studies.csv) |
| 参数与配置 | 原schema100K存储、10M单表/RDC、public-scale配置、1K至10M样本、B=0/.5/1/2/3及阈值解释分别保存。 | [参数协议](FULL_PARAMETER_STUDIES.md) |
| 增量更新 | 五个10M请求规模时间切点；逐批恢复、实际标量差分、前后模型及70条逆序重载。 | [更新时间图](../output/results/fullpaper_cardinality_temporal_updates.png) |
| Python/C++ | 38配置通过四个真实hash seed、62,548次预测门禁；canonical C++执行753条×3次、7,422次实际native成功调用，Python/native/CSV逐条匹配，最大相对差约1e-15，全部15个4–6表分组有耗时。 | [C++审计](FULL_CPP_V3_AUDIT.md) |
| MSCN | 官方100K查询/匹配位图训练100轮、70条原loader重放一致；一致样本重建MSCN另训练100轮、评估753条。 | [官方核验](FULL_MSCN_VERIFY.md)、[重建协议](FULL_MSCN_REBUILT.md) |
| Flights 1B | 实际遍历1,000,000,000行，实际样本9,997,912行；12SQL、331组全部对应，逆序24次point/CI调用一致；参考CI322可用/9排除。 | [模型](FULL_FLIGHTS_MODEL_RUN.md)、[重放](FULL_FLIGHTS_REPLAY_AUDIT.md) |
| LOCAL SSB 1M continuation | 复用已验收正向26次调用，新做逆序13次载入/26次调用；2,059点/4,118端点最大差0，无缺组、额外组或非有限输出；参考CI1,253可用/806排除。旧失败保留。 | [continuation](FULL_SSB_LOCAL_CONTINUATION.md)、[公开来源](../output/results/fullpaper_ssb_local_continuation_sources.json) |
| LOCAL SSB 10M cap | 五个新模型正式训练、完整来源验收、独立逆序及3表/2图均通过。 | [公开来源](../output/results/fullpaper_ssb_local_ci10m_sources.json)、[补充摘要](../output/results/fullpaper_additional_baselines.json) |
| Scalar / SRS / IBJS | Scalar完成50项单表计数/70预测；SRS和IBJS各完成70条，无超时或查询错误，零估计及无穷大q-error保留。 | [Scalar](../output/results/fullpaper_scalar_RESULTS.md)、[采样](../output/results/fullpaper_sampling_RESULTS.md) |
| DBEst / Flights Verdict | 原DBEst的1B母体20K拟合、4类SQL完成76次调用；新路由99次原生调用/101次拟合尝试。原Verdict0.4.7在同一Flights已有样本执行12SQL，point/native95%CI各14次物理调用。 | [DBEst路由](../output/results/fullpaper_dbest_routes_RESULTS.md)、[Verdict](FULL_VERDICT_PROTOCOL.md) |

组员guoao（贡献署名 `breck1016`）另交付14组JOB-light设置、980预测、多预算/多种子基础模型/RDC、PG16.15和独立真值记录。原提交、文件字节、归属与协议保留；本次整合未重训或重新执行其SQL。详见 [TEAM_EXPERIMENTS.md](TEAM_EXPERIMENTS.md)。

## LOCAL SSB 10M CI的最终证据

状态为 **`PASS_VERIFIED_LOCAL_10M_CAP_CI_MODEL_REVERSE_AND_DERIVED_TABLES`**。小黄金仅为独立SF2/10K算法等价证据；正式结论由实际SF500训练和重放支撑。

- 训练上限10M/table；五表实际训练行数：lineorder **9,996,946**、dwdate **2,556**、customer **10,000,000**、part **1,800,000**、supplier **1,000,000**，五个新模型。
- 本地母体3,000,028,242行，复用封存预处理与独立样本统计，采用canonical配对分组顺序。
- 新进程逆序13SQL，**13次模型载入、26次evaluator调用**，**2,059个点、4,118个CI端点**最大绝对/相对差均为0。
- 无缺组、额外组或非有限输出；参考CI **1,253组可用、806组因样本少于10行排除**。一次样本不证明重复抽样校准。
- 正式报告SHA256：`cfdd8a8033a624505a5705d95e7b8fcb37af2151616922efa1f452094a53f6fd`。
- 逆序报告SHA256：`29701ebec287bcd588e3a1b78034ba35243352c49ccb2a2206cf6b6fb88f2874`。
- 公开输出 `output/results/fullpaper_ssb_local_ci10m_*`：[全部分组](../output/results/fullpaper_ssb_local_ci10m_all_groups.csv)、[训练行数](../output/results/fullpaper_ssb_local_ci10m_training_tables.csv)、[区间图](../output/results/fullpaper_ssb_local_ci10m_ssb_ci_half_width.png)。

表图与状态消费者经[固定调用拼写适配](FULL_SSB_LOCAL_CI_ACCEPTANCE.md)使用一次原完整验收器；其余来源、封印、进程凭据、参数和数值检查不变，不补跑科学调用或改写凭据。

## 差异与适用边界

SSB修正生成器完成4,000片、3,000,028,242行及9,996,946样本。作者行数和查询0–5的346项真值匹配，但查询6–12的 **1,713项customer连接真值不同**；无缺/额外组。作者母体MISMATCH及外层失败不改写，LOCAL结果仅对本地同母体精确真值评分。两实现的完整维表字段一致也不证明作者原始母体相同。

JOB-light正文预算代理结果中位q-error1.344960、p90为3.837906、p95为4.313755、最大256.651971；作者Table1为1.34/2.50/3.16/39.63，中位接近不能消除尾部差异。公开683条查询（4–6表413条）不能标作作者200条。74个公开4表标签差异由另一套PG精确语句确认本地值；原标签/预测保留，local评分另存。

Scalar使用本地uniform-title-key组合公式和独立 `EVALUATION_ONLY_FLOOR1` 计分，中位8.739292、p95为818.658286，不是已恢复的作者Perfect Selectivities。SRS的70条均为原始零估计，q-error均无穷大；IBJS有13条零估计，完整70条中位1.458495，p90/p95/最大无穷大。有限57条的条件指标另列，不添加floor或丢弃零值。

Flights生成参数未完全绑定作者种子，属同原规模本地母体。DBEst新路由有204组件、103空样本、2个数值预算不支持项，拟合/数值验证错误为0；F3.3精确年份预筛是显式本地变体，双SUM差值没有联合CI。Flights Verdict有331真值/329原始预测组，缺2组；F5.2原错误和两SUM外部差分分开保留。原生95%CI不与DeepDB中央90%混作覆盖率或延迟排名。

## 尚未完成

- **LOCAL Verdict SF500：待最终验收。** v9在 `COPY ... ORDER BY ctid` 的数据库暂存文件触及1GiB上限后失败；有界往返修正及独立v10命名空间待实际完成。实现、模拟测试或SF2证据不能写成SF500成功。
- **四项作者公开输入缺口**：作者200条泛化成员、Figure5合成数据库配方、Wavelet及Figure12右图材料、Figure12左图DBEst原材料。见 [FINAL_PUBLIC_INPUT_GAPS.md](FINAL_PUBLIC_INPUT_GAPS.md)。
- **原规模完整数据库基线未执行**：3B事实表仅9个int4列的载荷下界108,001,016,712字节，另需行头/WAL/索引/排序空间。已有样本不替代原表建样本、TABLESAMPLE、XDB或端到端成本，见[资源说明](FULL_BASELINE_FEASIBILITY.md)。
- 其他作者原配置、完整比较方法和一致预算/计时条件未齐备，保持PENDING/SOURCE_GAP，不记为全论文完成。

## 交付与继续

GitHub最终在 `main`交付代码和审查后的共享结果，数据/HDF、模型本体、环境、数据库、PDF和凭据不上传；`reproduction/full-paper`保留扩展开发历史，[PR #3](https://github.com/VictoriaSU551/DSC5003-DeepDB/pull/3)记录整合。

本地最终目标为根 `README.md`加 `results/`结果包，实际保留集合以最终清单为准；当前不宣称清理完成。若精简移除历史来源闭包，须明确退役对应fullF及传递依赖入口，保留结果、哈希、验收时间和退役边界。未确认去留的最终模型先安全保留。已验证结果直接使用，不重复训练或推断。继续工作按[运行指南](FULL_RUNNING_GUIDE.md)，不自动重启TAINTED控制器。
