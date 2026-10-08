# 官方来源及本地适配

- 论文：https://arxiv.org/abs/1909.00607
- 代码：https://github.com/DataManagementLab/deepdb-public
- 固定提交：`655ada13a043a4226a239b0c0a65bcdefef87a02`，作者提交日期 2020-06-19。
- 许可证：作者 MIT 许可原文保存在 `code/LICENSE`。
- 数据：作者 README 指向 CWI JOB 快照；旧域名连接超时，本次从 CWI 的 `event.cwi.nl/da/job/imdb.tgz` 取得。
- 快照压缩包 SHA256：`25f9d893c54f903366e0c263f88db0d429dbc2b159d4987ebc1e203242a7e988`。

## 提取范围

保留 `aqp_spn`、`benchmarks`、`data_preparation`、`ensemble_compilation`、
`ensemble_creation`、`evaluation`、`rspn`、`schemas`、`maqp.py`、作者 README、许可证与原始依赖清单。
作者 `baselines` 目录包含 Windows 不合法的历史结果文件名，因此不检出该目录。
本仓库没有重新运行或声称复现其中其他方法的历史结果。

## 三处算法源码适配

1. `data_preparation/prepare_single_tables.py`：读取 CSV 时只载入原本就会保留的列；
   用分组计数计算一对多连接倍数，用外键集合识别无子记录的父行，避免展开大型连接。
   小样本检查包含重复外键、空外键、无匹配父行和 0.5 采样率。
2. `rspn/learning/structure_learning.py`：取消导入时创建进程池；在本地实现同样的数组列切片，
   顺序构建叶节点。避免 Windows spawn 重复导入，以及复制大量训练数据。
3. `maqp.py`：在原有 NumPy 种子之外补上 Python `random.seed(1)`。

这些修改不改变 RSPN 的行列划分准则、概率叶节点、查询编译公式或官方查询真值。
兼容性补丁相对于上述作者提交生成，见 `compatibility.patch`。

## 环境差异

Python 3.8.20；NumPy 1.19.5、PyTables 3.7.0、NumExpr 2.8.4 和 psycopg2-binary 2.9.9
用于可安装的 Windows 环境。学习相关的 scikit-learn 0.22.2.post1、SciPy 1.4.1、
SPFlow 0.0.40 保持作者 Python 3.8 清单版本。其他依赖见锁定清单。

`setup.ps1` 临时使用 `subst` 缩短构建缓存路径，物理文件仍全部在项目目录中，
安装后撤销映射；不修改 Windows 系统长路径设置。
