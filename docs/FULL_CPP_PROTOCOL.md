# 原 1M 模型的 C++ 推理验证协议

本任务验证此前已经训练、验证的关系基础模型能否通过 C++ 代码生成正确推理。
范围是现有 1M/RSPN、5 个 SPN、70 条 JOB-light，加数值边界回归；
不重训模型，也不能计为论文 Figure 8（4--6 表泛化集）或完整论文复现。

## 原模型保护与输出

原模型 `output/models/ensemble_relationships_imdb-light_1000000.pkl` 只读，任务开始 SHA256：

```text
b97d8732f2219e4d4593516f39762af2d898f613493c9badef57f52b18b86d86
```

先复制到 `output/full/cpp/double/ensemble_with_ids.pkl`，核对复制前后 SHA256。
官方 `generate_ensemble_code` 为 SPN 分配 ID 并保存模型，只允许其写这个副本。
生成源码、编译命令/输出/退出码、编译后的 .pyd、副本模型、重复计时 CSV 均在
`output/full/cpp/`；最后回执为 `output/full/results/cpp_verification.json`。
原模型在生成后和全部验证后再次核对 SHA256。

构建缓存绑定原模型、数值叶模板、原生成器、编译器、runner 的 SHA256，
以及 Python、pybind11、浮点类型及优化选项；还核对副本、生成源码与 .pyd 摘要。
只有这些都一致的 PASS 构建才复用，不因已有文件就跳过验证。

## 项目内工具链

采用 [w64devkit v2.0.0 官方发布](https://github.com/skeeto/w64devkit/releases/tag/v2.0.0)：
GCC 14.2.0、Mingw-w64 12.0.0。无需安装系统服务、Visual Studio 或修改系统环境。
下载包放 `data/downloads/w64devkit-x64-2.0.0.exe`，解压到 `.runtime/w64devkit/`。
发布包36581551字节，本次下载 SHA256：

```text
cea23fc56a5e61457492113a8377c8ab0c42ed82303fcc454ccd1963a46f8ce1
```

该 SHA 为本次实际文件摘要，不声称是作者提供的签名验证。
解压结果约392MB；包、工具链、源码、模型副本等新增数据保持2GB预算以内。
通过子进程 PATH 找到同目录 assembler，不永久修改用户或系统 PATH。
`toolchain_download.json` 与 `toolchain_extract.log` 留存来源和执行结果。

pybind11 固定 **2.6.2**，只安装到项目 `.venv`。系统 pip 的现有代理配置导致网络安装失败，
因此从 PyPI 元数据定位官方 wheel，用标准库下载并核对 PyPI SHA256，然后离线安装：

```powershell
python -m pip --python .venv/Scripts/python.exe install --no-index --no-deps data/downloads/pybind11-2.6.2-py2.py3-none-any.whl
```

wheel SHA256：`2d8aebe1709bc367e34e3b23d8eccbf3f387ee9d5640548c6260d33b59f02405`。
原 Python 3.8.20 x64 的 Python.h、python38.lib 已在 `.runtime`，编译得到
`optimized_inference.cp38-win_amd64.pyd`。

## 失败证据与最小模板修复

先写实际编译的数值叶差分测试，数值集合[-99,1,3,5]，概率[0.1,0.2,0.3,0.4]，
-99 为 NULL。Python 参考值由原 `identity_likelihood_range` 计算，而非复制 C++ 公式。

原模板的两项已实际触发的问题：

1. P(X<3)：Python=0.20000000000000007，编译后的原 C++=0.5。
   回执 `output/full/cpp/boundary_before_fix/boundary_verification.json`。
2. 域外开区间(10,20)：Python=0，原 C++ 在 `_GLIBCXX_ASSERTIONS` 下退出3；
   `out_of_domain_before_fix/execute.json` 保存断言错误。

只对 `code/rspn/code_generation/templates/identity_leave.cpp` 做两处改动：

- 左端点排除前检查 lower_bound 索引小于 uniqueVals.size()。
- 右端点排除前检查 upper_bound>0，并将 `rightIdx-node_id` 改成 `rightIdx-1`。

修复前模板 SHA：`1015d1d9e54bd39180a60fd7cc2a0a040690b44ab586d4ad450f511b9dbb6d59`。
修复后 SHA：`ecc700ae2eee9b410dd06fdb3fee98f489ff7254bc7154f1f07355ae2de3aaee`。
不编辑原 generate_code.py 或任何其他原算法 .py，避免影响独立训练代码封印。

边界矩阵含12例：开/闭上界、最小值、最大值、相等端点、两侧域外、无限边界及 NULL。
相等端点继承 Python 参考实现的约定；例如[3,3)在原 Python 中返回该点概率，
本任务只证明与参考实现一致，不据此宣称已独立证明所有区间的 SQL 语义。
`equal_endpoint_before_fix` 是此项调查的 PASS 证据，不是修复前失败案例。

独立边界可执行文件使用 `_GLIBCXX_ASSERTIONS`，使 vector 越界成为可复核失败。
修复后12例差分在 float 类型下按 rtol=1e-6、atol=1e-6 判断。
接近零的消减误差按绝对容差处理；不把归一化残差误写成处处相同的相对误差。

## 主模型构建兼容性

直接调用原生成器支持的 `floating_data_type='double'`，使用 double 储存概率/中间值，
降低 float CDF 相减的消减误差。原生成器的数值条件参数类型仍由原代码定义。
这个配置不是宣称复现作者未说明的确切 C++ 浮点配置。
`--floating-type float` 可以另建 float 目录进行独立对照，不能混用两种二进制与模型绑定。

生成文件前补显式 `<cstdint>` 与 `<algorithm>` include；不修改原 Python 生成器。
GCC14 编译旧 pybind11 2.6.2 时曾实测报 std::uint16_t 未定义，根因是缺少显式 cstdint。
首次编译错误保存在 `double/compile_missing_cstdint.json`，失败构建回执也留存。
编译参数为 -O2、-shared、-std=c++11、-ftemplate-depth=2048，静态链接 libgcc/libstdc++；
一次仅一个 GCC 编译进程，无并行构建。

## 70 条核验与重复计时

1. 读取70条 SQL、CSV真值和query_no，逐条检查其对应关系。
2. 分别加载同一个带ID副本模型，Python实例强制关闭生成代码，C++实例启用生成代码。
3. 预先导入指定绝对路径的扩展，避免意外载入其他目录同名模块。
4. 先完整预热一轮，随后默认5轮；每轮都评估70条，并交替两种模式先后顺序。
5. **每条查询之前清空两种实例的 factor expectation cache**，防止以缓存结果冒充生成代码调用。
6. 保存全部350对预测、真值、两种总耗时、生成推理耗时和 generated_spn_calls。
7. 每对要求有限值、rtol=1e-5/atol=1e-6一致，并要求每条查询的生成代码调用数>0。
8. 加上修复后边界矩阵 PASS 与原模型 SHA 未变，才可写总体 PASS。

计时与原 evaluator 同样在 SQL parse 后开始，包含概率查询编译和因子求值；
GenCodeStats 的 inference 部分包含模块查找、C++调用和 NumPy结果包装，条件转换在其计时外。
单位均为毫秒，不能把该字段直接标成微秒。
本机同时有其他独立复现任务，计时只是本机重复运行记录，不作论文硬件速度比较。
正的生成代码调用数证明存在原生调用，不证明所有可能条件均无需 Python 回退。

## 重跑命令与通过门槛

从项目根目录：

```powershell
.venv/Scripts/python.exe -m pytest code/tests/test_full_cpp.py -q
.venv/Scripts/python.exe code/full_cpp.py boundary --label boundary_after_fix
.venv/Scripts/python.exe code/full_cpp.py all --floating-type double --repetitions 5
```

入口会为本次子进程设置 PYTHONHASHSEED=1 与单线程数值库变量，不修改全局设置。
命令退出码与 JSON 的 status 必须同时成功；编译失败或差分不符不得记为完成。
最终实际结果以 `cpp_verification.json`、逐行 CSV 及对应 build/compile 回执为准。
未commit或push，未运行大规模模型训练。

## 本次实际结果

2026-10-30：double扩展实际编译通过，用时170.93秒；后续验证复用摘要一致的已编译产物。
70条×5轮共350对预测全部通过，Python/C++最大相对差为6.15e-16；
总生成调用1490次，每条每轮至少1次。12例边界回归通过，原模型SHA保持不变。
新Python预测与旧 `output/results/job_light_1000000.csv` 的全部预测完全一致，
独立回执为 `output/full/cpp/original_prediction_match.json`。

共享机器此次重复计时的中位数为Python总路径5.299ms、C++总路径0.988ms、
生成推理0.199ms。只记录本机条件，不推断论文速度复现。
工具链、下载包和本任务CPP产物合计约494.9MB（不含很小的venv pybind包），低于2GB。
任务专属测试4项通过；当时整个项目测试52项通过，另有一条并行准备测试产生的
pandas int/float merge UserWarning，未隐藏该警告。
