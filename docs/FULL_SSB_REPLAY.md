# Independent SSB formal reverse replay

本层与冻结的SSB生成/准备/训练/推断core和guard分开。不会修改原结果、模型、科学源码或seal。
只在正式模型与13条原顺序point/CI已完成后显式执行一次：

```powershell
.venv/Scripts/python.exe -B code/full_ssb_replay.py replay
```

`replay()`启动新鲜Python进程，固定PYTHONHASHSEED=173、Python/NumPy seed74031及四个数值线程限制=1。
按query12→0执行，每条重新从相同pkl加载ensemble、建立reverse dict、解析逐字原SQL，
分别真实调用原evaluate_query point与confidence_intervals=True；实际13次模型加载、26次原evaluator调用。
每次使用新factor cache，CI事实样本数仍为最终actual sample_rows，不能用每SPN1M训练行数替代。
baseline冻结runner没有保存其进程hash secret；如实记录此缺口，不假称恢复了baseline hash环境。
新重放完整保存自身环境、hash probe及随机种子，模型和完整依赖前后SHA必须不变。

每条必须query_no/query_name/逐字SQL精确相同；组key集合精确相同、无缺少/额外/重复，
不能因为组顺序不同失败，也不能填0后相等。有限point和两CI端点使用明确容差
relative=1e-9、absolute=1e-5，同时记录实际最大绝对/相对差异。
原始CI预测行先完整物化并检查唯一key与完整point key集合；即使intervals缺失也检查全部CI行。
存在intervals时还必须原始CI行数与interval数量精确相等，全部校验完成后才允许zip，避免尾部静默截断。
baseline非有限point只保存null、未保存NaN/Inf种类，因此不能由null==null认证，直接拒绝。
CI若两边都缺失则明确计数为gap；原非有限CI还必须raw NaN/Inf状态字符串和组key完全相同，
不通过NaN算术相等吞过。

原正式status PASS仅表示0调用异常。新replay PASS只表示独立行为重放一致，
不表示所有AQP组和CI coverage完整。`coverage`独立返回：truth/model/missing/extra总组数、
nonfinite_point_groups、nonfinite_original_ci_groups、missing_or_nonfinite_model_interval_groups、
zero_truth_groups、reference_ci_eligible_truth_groups、reference_ci_excluded_truth_groups及全部union参考CI状态计数。
模型多余组保留；缺模型组、参考样本不足10行或CI排除均不静默丢弃。

最终只读验收入口供root表/状态调用：

```python
from full_ssb_replay import verify
accepted = verify()
```

```powershell
.venv/Scripts/python.exe -B code/full_ssb_replay.py verify
```

`verify()`严格只读：没有正式结果或没有重放证据即失败；不调用replay/worker、prepare、train、
模型反序列化/构造、推断、native编译，不以缓存缺失为由执行任何补算。
它读JSON和哈希实际raw/HDF/model/metadata/13原query+seal/精确moments及完整parser/SPFlow依赖，
核对FORMAL/三阶段持久PASS和准确清单，再验证新13条query+13seal、SQL/组key/数值对照与自封印。
不会调用可能将RUNNING改写为TAINTED的guard require函数；异常也不改旧状态。
因此verify可能有多GB只读哈希I/O，不能等同为轻量mtime检查。

`output/full/ssb/replay/verification.json`和`verification_seal.json`为最终入口，
实际query/FAIL evidence在`runs/<binding>/`，日志在`logs/`，`last_run.json`/`last_process.json`为操作状态。
namespace绑定科学snapshot、replay源码、种子和容差；失败namespace保留，禁止自动重跑/洗白。
worker通过单次mkdir(exist_ok=False)原子认领namespace；已有目录即拒绝，即使尚无lifecycle，
因此同时启动的worker不能在exists→RUNNING间隙共同认领和重复计算。
新replay实现或修复使用另一个源码绑定namespace，冻结正式科学产物不动。
主runner尚未完成时不能把“测试通过/接口准备好”报告为实际重放已完成。

2026-10-31执行边界回归：新增五类原始CI错配/重复/完整集合检查及无lifecycle已占用目录检查；
修复前4 failed / 13 passed，修复后17 passed（0.25s）。测试替换模型读入和evaluator的外部边界，
真实执行本层execute_query/worker校验；没有读取或重算SF2/tiny/正式模型。
冻结core、guard、formal_plan的SHA保持原值。本层源码SHA由实际执行binding记录，文档不自引用绑定。
