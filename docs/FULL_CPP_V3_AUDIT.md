# Read-only current native audit

永久只读入口（在项目根目录）：

```powershell
.\.venv\Scripts\python.exe -B code/full_cpp_v3_audit.py
```

它没有生成/编译/worker/predict路径。缺少final_current_seal.json或任一工件即失败，
不会补做推理。实际执行fresh inputs及verify_current(label,753)，核验38模型四seed
最终验收与当前label、科学source/runtime、753条精确SQL与CSV、原模型与旧222文件。
逐条重验已有2,259对三方预测、每查询完整成功调用map与正wall、作者漏记差、15cells
和资源cap。这里只读取已有预测并计算校验，不执行模型推断。

科学runner full_cpp_v3.py SHA256仍为
7b15355542a3d34d217dc67d8cca056937cc2021f4ff97899712b41a010a04d0。
首次科学final_seal.json SHA256仍为
2bff5c7946546ce51c7636e94c8ba9458edf8cd61d7a53cf4db675388bc2e9e9；
其中68工件和源码快照一字节未改。新增的只读模块/测试/本文及源码快照由外层
final_current_seal.json完整绑定，不能把修改只读入口说成重跑了科学门禁。

最终指针：output/full/cpp-v3/final_current_seal.json。
科学verification指针仍为output/full/cpp-v3/latest.json，指向
model_00c14f94cbedf038_ee5c9a24b443cb6d/verification.json，SHA256
1687f3ba3fbbcbdb86519cc1acdbd8beef583a7501083b2fd30d96c48fe9c90b。
外层manifest要求非空、不重复、与namespace完整文件集合相等（仅排除其自身），
逐文件记录path/bytes/SHA256；sources额外绑定永久模块、对应测试和协议。原科学
seal/verification自摘要再次校验，原科学module与model/compiled assets均不变。

Figure8的15cells读取科学目录内figure8_grouped_timings.json的groups数组；
每格键为tables、predicates、unique_queries、timed_pairs、timing_ms。
主native字段timing_ms.cpp_physical_native_ms.{mean,median,p95}包括所有成功物理
pybind调用；同入口对比用python_inference_ms/cpp_inference_ms，total用
python_total_ms/cpp_total_ms；cpp_native_bridge_ms保留作者原stats子集口径。
三个范围不互换、不混成同一条曲线。

三个新增只读测试先失败，加入实现后连同科学runner与cache/canonical回归共30项通过。
最终正式推理仍为之前的753×3，当前只读审计新增预测数为0。详情及边界见FULL_CPP_V3.md。
