# 推理修正与结果版本

完整复现阶段保留原模型和全部 v1 CSV。后续基数结果采用
`code/full_evaluation_v2.py`，输出在 `output/full/evaluation_v2/`，
汇总为 `output/full/results/*_evaluation_v2.json`。模型没有因此重新训练。

## 物理模型缺失的缓存键

原 `IndicatorExpectation.__hash__` 包含公式、条件、逻辑表集合，却没有实际 RSPN 身份。
相同公式可能由两个不同样本训练的模型分别估计，其值并不严格相同。
跨查询沿用原 ensemble cache 会让后续结果依赖前面的查询。

本地实证：JOB-light 查询4在 SPN1 缓存了逆因子 `0.11461245279656225`；
查询43使用物理 SPN0，直接计算该因子为 `0.17102942198622903`，
原缓存却返回 SPN1 的值。查询43的预测因此分别为
`348067.94428687723` 和 `519401.32045673457`。
旧策略重放753条全部吻合旧CSV；其中14条与逐查询冷缓存结果不同。
证据位于原5模型 C++ 目录的 `python_cache_policy_audit.json`。

`full_factor_cache.py` 只在本次推理进程的上下文中，把物理 SPN 身份加入缓存键，
退出或异常后恢复原方法；每条查询还清空缓存。原算法文件字节、模型参数和因子公式不改。
回归检查覆盖同公式的两模型不同值、同模型缓存复用及异常恢复。
v2重载复核按每组逆序计算，要求逐条与正序结果一致。

因此旧CSV的“可重放”不能证明它没有顺序依赖。v1保留为历史证据，论文对照采用v2。

## C++反转特征参数

上游 `convert_conditions.py` 把 `inverted_features` 当列索引集合，但调用者传入
与 `feature_scope` 逐项对应的布尔列表。例如 scope `[6,5,4]`、flags
`[False,False,True]` 应反转列4。该差异在公开753条中造成4条Python/C++不一致。

`full_cpp_range_adapter.py` 在独立上下文中将有序flags映射为实际列索引，
随后调用原转换器。原文件不改，原FAIL及诊断完整保留。
具体门禁、编译版本和每条native调用证据见 `FULL_CPP_SCALE.md`。

另有数值叶C++的开区间及域外端点错误，已先以真实编译观察失败，再实施最小模板修复；
见 `FULL_CPP_PROTOCOL.md`。不能将仅同一错误路径的Python/C++一致性当作SQL语义的独立证明。
