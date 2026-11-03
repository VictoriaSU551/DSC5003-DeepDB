# 最终公开输入缺口复核（2026-11-03）

本轮结论：组员新包补充了同一套70条JOB-light的训练、估计、核验与分析记录，没有关闭下列四项作者输入缺口。在本轮限定范围内，新增可据现有材料原样执行的作者实验为0；这不表示项目其余已具输入的CI、重放或基线工程不能继续。本说明不验收正在执行的任务，也不把“公开材料中尚未定位”扩大成“全球不存在”。用户已确认没有额外作者材料，本轮不再索取同一资料。

## 新材料实际覆盖什么

`output/results/guoao_experiments/`实有36文件、2,871,252字节。其`source_manifest.json`列出的35个公开文件，与物理文件集合（另加清单自身）、字节数及SHA256全部一致；ZIP恰有9成员，逐项长度和公开SHA也与清单一致。这是文件一致性检查，不是重新训练或模型科学验收。

新包的[README第72、80、82行](../output/results/guoao_experiments/README.md)、[settings](../output/results/guoao_experiments/settings.json)和[交付范围](../output/results/guoao_experiments/DELIVERY_MAP.md)明确描述：9个relationship设置、4个RDC设置和1个PostgreSQL16.15设置，全部使用相同70条查询。`predictions.csv`实有70行、14个估计列（980单元），`metrics.csv`14行，`truth_audit.csv`70行；本轮另核70个有序ID、逐SQL摘要与原IMDb标签完全对应。没有把同一查询的多模型、多种子、双语图或重复评估算作新查询。RDC记录预算为5，不能据此消除论文默认0.5与公开CLI配置的既有差异。

ZIP包含`maqp.py`、`repeat_seeds.py`、`joblight_exact_count.py`、`recompute_joblight_truth.py`、`postgres_baseline.py`、`verify_results.py`、`tools/run_rdc_visible.py`、LICENSE及UPSTREAM说明；可见评估驱动均指向既有`job_light_queries.sql`。没有200条成员清单、IMDb合成数据库生成器、Wavelet关系执行器或Fig.12微基准驱动。包内也声明未提供端到端重训套件；日志、模型摘要和来源快照不等于其依赖的数据/HDF/运行环境已随包交付。对应Git对象为`10770d75a22319938dbbb53fe855ae6b6d29e5bd`和合并提交`1d7e44aca7394652c1487810cc30139f642073f7`，本轮只读取对象信息。

## 四项缺口及执行边界

### 1. 作者200条泛化查询成员

[DeepDB论文](https://www.vldb.org/pvldb/vol13/p992-hilprecht.pdf)§6.1说明另构造200条查询，涉及3—6表、1—5过滤谓词；参数探索亦使用这200条。当前文本`output/full/paper/deepdb.txt`对应第623—627、794—796行。固定[上游scale_sql树](https://github.com/DataManagementLab/deepdb-public/tree/655ada13a043a4226a239b0c0a65bcdefef87a02/benchmarks/job-light/scale_sql)公开的是20组683条，其中4—6表413条；详见[原来源清点](FULL_SOURCE_AUDIT.md)第33—56行。

仍缺确切200条的SQL/有序ID清单，或能唯一恢复成员的原选择规则、随机种子与版本映射。组员包只绑定原70条，未增加这项映射。不能任取683中的200条、用500条scale或5000条synthetic查询替代后称为作者原集合，也不能从汇总q-error反推唯一成员。公开683/413集可以按明确的LOCAL/公开全集协议执行，项目已有该方向结果；重跑它们不会关闭作者200成员缺口。

### 2. Fig.5的IMDb合成数据库生成配方

论文§6.1“合成数据”段（当前文本第714—726行）描述IMDb schema生成器、均匀独立分布、偏斜与列间相关，并用原70条JOB-light计算非零真值查询的平均q-error；图中标出Zipf(2/3/4)和20%—100%相关属性（第658、672—675行）。这些是部分实验条件，尚不是可唯一执行的生成配方。

仍缺生成器或精确算法、表规模与键/外键生成规则、各列取值域与分布映射、相关列选择及耦合方式、随机种子，以及各生成母体的真值和零真值排除集合。组员提供的是真实IMDb数据及其70条真值，不是这些合成母体。`synthetic_queries.sql`是查询文件，也不是Fig.5数据库生成器。依据论文文字另写一个生成器可以形成LOCAL实验，但无法证明是作者原配方；旧曲线或真实IMDb结果也不能作为新生成/新估计的替代。

### 3. Wavelet基线与Fig.12右图

论文§6.1报告每表wavelet及20K系数的基数估计配置（当前文本第627、634—638行）；§6.2解释已知查询列组合时可构建逐查询最小维摘要，并在Fig.12右图观察维数增加时的误差变化（第1243—1254行）。原方法来源为[Chakrabarti等的VLDB论文](https://www.vldb.org/conf/2000/P111.pdf)，另有[作者期刊条目](https://minosng.github.io/Abstracts/vldbj01-abs.html)及[Microsoft Research发布页](https://www.microsoft.com/en-us/research/publication/approximate-query-processing-using-wavelets-3/)。这些链接来自既有定点原始来源审计，本轮没有重新联网验证可达性。

已有Wavelet输入审计（本地路径`output/full/reviews/figure12_wavelet_inputs_v1/memo.json`）保存18份历史CSV（基数估计5、AQP13）的来源；其中12份`curse_of_dim`文件含112行历史结果，部分记录了2—12维、30000系数、`max_samples=1000000`、`sample_percentage=1`及`upsampling=1000`等字面值。该参数不是§6.1的20K系数配置；缺失的维数组合不能补成完整网格，字面值也不足以推定实际训练行或概率。

既有有界检索未定位可固定且许可明确的原多维Haar关系执行器。仍缺额外维度列及顺序、类别编码/数值网格/NULL规则、系数归一化与选择/平局规则、每表或逐查询摘要、select/join/aggregate驱动、原训练选择/种子和图形聚合协议。新包无此实现或参数。通用PyWavelets函数、新写Haar近似或重绘历史CSV都不能算原基线重跑。参见[FULL_BASELINE_FEASIBILITY](FULL_BASELINE_FEASIBILITY.md)第215—230行；结论只覆盖已审来源，非全网不存在证明。

### 4. Fig.12左图DBEst原执行材料

Fig.12标题为非临时查询方法微基准：左图是DBEst随数值过滤属性数变化的延迟，右图是Wavelet随维数变化的误差（当前文本第1060、1243—1254、1293—1298行）。它不是SPN叶、batch或SIMD/vectorization微基准；这些新本地微基准不能用来补该图。

既有DBEst专项审计（本地路径`output/full/reviews/figure12_dbest_multidim_v1.json`）已经固定官方`DBEstPy@2220a937b5eef358eb42a715da328915048b7250`。固定DeepDB树中可读到1D/2D/3D各9条历史`times.csv`标识及范围条件，但未证明它们与Fig.12图点的精确映射。仍缺原驱动/物化查询映射、原训练数据与选择、每组N来源、模型与带宽/归一化选项、多维代码快照、有效积分容差、硬件及计时协议。新包只有JOB-light基数估计流程，不含DBEst/SSB/Flights微基准材料。

原官方快照还有已记录的实际2D构造失败，以及静态可见的训练数据删除后读取和缺少独立多谓词矩形接口问题。本轮没有重复该失败、拟合或积分。修复构造/训练域保存并扩展积分接口可以成为明确授权的LOCAL兼容实验，不能据此声称恢复作者Fig.12。已有真实1D引擎和Flights routes结果仍按其原范围保留，不能当作2D/3D历史延迟实验。

## 最终交付的诚实边界

这四项均保持“原输入/原执行材料未定位，按作者原配置不可执行”的状态。原因不是尚未多训练一次或重画图，而是无法唯一确定应执行的母体、查询成员、算法/接口或参数。新增包没有提供补齐依据，故本轮不提出新的近似变体来充当完整复现，也不重跑已有70条或已验证失败。

组员包可作为独立贡献结果与来源证据交付；作者历史CSV可用于明确标注的历史图形重建。两者均不冒充本轮原基线执行。后续README/最终交付清单应同时保留已实际完成的结果与这四项限制；本次专项审计未修改README、未删除原物；最终整合由主任务另行提交。若最终清理退役旧递归审计依赖，应另在交付清单标明验收已退役，不能声称只凭最终结果和README仍能执行旧完整重放。

机器可读记录：[fullpaper_final_public_input_gaps.json](../output/results/fullpaper_final_public_input_gaps.json)。本轮0网页检索/下载、0原始数据表扫描、0训练/推断/积分、0父F、0数据库/JVM；仅核对现有小文件、压缩包成员及Git对象。新包出现的官方链接均已在既有审计范围内，因此没有触发额外原始来源访问。
