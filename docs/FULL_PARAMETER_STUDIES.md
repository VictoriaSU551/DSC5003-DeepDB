# 参数、schema与成本口径

原 `joblight` profile 去掉了 `cast_info.person_id`，用于原始JOB70与单表退化/存储优化。
公开分组查询中157条使用person_id，因此泛化另用 `public-scale` profile。
后者只重建cast_info，其余准备表及元数据由原profile复用；不混写两个结果。

## 预算

论文规定额外预算为 `B*CBase`，并用 `cols²*rows` 估计相对训练成本。
公开驱动却把数值因子乘以所有单表的 `cols²` 总和。
因此直接将公开CLI从整数改成浮点，仅使0.5可以传入，并没有统一归一化的分母。

`full_training.py` 保留公开驱动的归一化；`full_paper_budget.py` 单独使用基础ensemble的
列数平方代理成本归一化。相同请求行数的因子抵消，实际有限表样本数仍逐项记录，
这不是对实测训练秒数的硬保证。

| profile | 所有单表代理成本 | 基础ensemble代理成本 | 论文代理B=.5对应公开CLI因子 |
|---|---:|---:|---:|
| joblight | 116 | 404 | 1.7413793103448276 |
| public-scale | 123 | 539 | 2.1910569105691056 |

在本地选择中，public-scale直接代码因子0/.5/1得到相同的5个基础模型；
论文代理B=.5加入一个三表模型。两种配置和标签均保留，不用数字巧合合并实验。
公开代码的候选搜索、RDC阈值及列数估算也不能证明它恢复了作者未发布的具体配置。

## 复用与时间

`full_joblight_variants.py` 在原schema评估单表模型和论文代理预算模型。
对于不涉及cast_info的模型，只有在相关表定义、全部元数据和所引用HDF内容均相同后，
才从public-scale取回已验证组件；cast_info绝不跨profile复用。
这使新ensemble不需要重训相同的可信输入。所有复用记录指向原组件及摘要。

样本量扫描保留1K、10K、100K、1M、10M各自的组件；预算配置共用相同组件检查点。
必须区分原组件实际训练耗时、本次仅组装的耗时、数据准备耗时与端到端时间。
不能把缓存复用时间当作从头训练速度，也不能把学习阶段秒数与论文包含准备的48分钟直接相比。

所有新比较采用v2模型身份缓存策略，见 `FULL_INFERENCE_CORRECTIONS.md`。
公开泛化是683条（4--6表413条），论文200条的具体成员仍未找到，故扫描为公开工作负载版本。

## 两个RDC阈值

原CLI `--rdc_threshold=.3` 传给每个RSPN的列独立性学习；
`ensemble_creation/rdc_based.py::candidate_evaluation` 另有 `.15` 的ensemble选择默认值，
CLI没有把前一个参数传到后一个位置。此前 `full_training.py` 忠实保留这个 `.15`。
不能笼统称作“所有RDC阈值均为.3”。

论文3.3节说表间独立性使用标准SPN阈值，因此新增独立 `full_ensemble_threshold.py`
将表间阈值也设为.3，保留原 `.15` 所有模型和评估。它直接使用已封存RDC结果，
不重算依赖统计；小于等于.3的值清零，按同一公开候选算法及B*CBase代理成本重新选择。
全量组件沿用原训练检查点，跨profile仍只允许已证明完全相同的非cast输入复用。

两种选择的public-scale基础成本分别为539和411；.3下cast_info单独建模，
其与title的最大已测RDC约.16485。原joblight基础成本仍为404。
`threshold03_*` 标签清楚标识这一正文解释，不把它覆盖到公开默认的旧标签。

此外另跑100K和10M的全部五条关系模型，作为公开README `relationship` 策略的独立对照。
它与按RDC自动排除低依赖关系的基础ensemble不同，不用更好的指标替换原配置的差异。
