# DeepDB 完整复现执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成论文全部实验的可审计复现，沿用现有项目和已验证结果。

**Architecture:** 以固定上游为算法基础，在独立 `full` 模块实现数据准备、数据库核验、实验配置、模型检查点和汇总。
论文与代码差异显式记录；未满足完成条件的实验保持未完成。

**Tech Stack:** Python 3.8.20，固定 SPFlow/NumPy/SciPy，PostgreSQL 11.5，后续 C++/pybind11。

**Spec:** `docs/FULL_REPRODUCTION_PROTOCOL.md`

## Global Constraints

- 全部内容留在 Deep DB；数据 data，输出 output；不覆盖原有 1M 基础结果。
- 不重复已完成且已验证的训练；恢复必须核对输入和代码摘要。
- 论文 B=0.5、10M 与 README B=5、不同多表样本量分别标记。
- 保留必要测试、模型和恢复检查点；完成后清理不用的临时文件。
- 不用作者历史结果冒充本地重跑，不用缩小规模冒充完整实验。

## Review Focus

- 空值/无匹配连接行与重复外键的标定是否一致。
- 旧模型是否因参数或代码变化被误用。
- 查询和真值是否按 SQL 内容对应，零真值是否被不当删除。
- 更新时间划分是否被 NULL 哨兵或全量连接大小污染。
- 较大连接的样本中间结果是否超出可用内存。

## Tasks

- [ ] 1. 精读并清点论文图表、公开代码和输入；保存来源/缺口清单。
- [ ] 2. 项目内安装 PostgreSQL 11.5，加载六张完整表，校验行数，独立计算全部 70 条真值与 EXPLAIN 基线。
- [ ] 3. 修复 RDC 管线已确认的接口缺陷、浮点预算、增量状态缺陷，先失败测试再修复。
- [ ] 4. 创建实验配置与分模型原子检查点，恢复输入封印验证；复用可信结果。
- [ ] 5. 执行存储优化/单表/10M 基础和 RDC 0.5；评估 JOB-light 与公开泛化分组。
- [ ] 6. 执行预算/样本量/时间划分更新实验；保存前后模型和实际样本比例。
- [ ] 7. 编译 C++ 推理并逐条对比；完成分组耗时实验。
- [ ] 8. 补 AQP 数据、SSB/Flights 原规模训练/真值/CI/对照方法；真实缺口保留状态。
- [ ] 9. 汇总图表与论文对照，检查所有完成条件、回归测试和清理；同步协作分支。

## Ledger

- 2026-10-30：原工作区干净，切换 `reproduction/full-paper`，起点 `ac2485496157092bcdbe85f61e18db216168566e`。
- Ruling: 按用户要求原文件夹原地继续，以新分支及 output/full 隔离；不再创建另一份项目环境。
- Ruling: 原范围已由用户扩展到完整复现；协议以论文为目标，版本差异记为差异，不擅自缩减目标。
- 现有 Docker Linux daemon 未运行；选择项目内便携 PostgreSQL 11.5，不修改 Docker/WSL 配置。
- 2026-10-30：精读完成；实数公开分组查询为 683 条（4--6 表 413 条），论文 200 条无法精确绑定。
- 2026-10-30：PostgreSQL 11.5 六表完整导入、行数及全部外键对应域检查通过。前 59 条真值已直接执行核对。
- Ruling: 第 60 条查询真实连接产生约 95 亿行，直接枚举超过 7 分钟；只取消该专用数据库上的本次语句。
  改用按 movie_id 预聚合计数后相乘的等价精确 SQL；SQLite 重复键/过滤/NULL 回归检查通过，前 59 条已核验结果不重算。
- 2026-10-30：原 schema 的 100K RDC 基础模型训练完成，JOB-light 中位 q-error 1.514916；保留独立结果。
- Ruling: 泛化查询实际使用被官方轻量 schema 排除的 person_id。新增 public-scale profile 并仅重建 cast_info，
  其余 HDF 通过项目内硬链接复用，防止对已验证内容重复处理。
- 2026-10-30：项目内 Flights 原始 5M 输入下载、CRC、SHA256、列/年份核验完成；这不计为 1B 复现。
- 2026-10-30：全部 70 条官方真值已独立核对，PostgreSQL 11.5 EXPLAIN 基线完成。
- 2026-10-30：public-scale 100K 基础模型完成，70+683=753 条评估与重载复核通过；旧 profile 结果独立保留。
- 2026-10-30：现有 1M 模型 C++ 编译，70 条×5轮差分通过；数值叶两个边界错误已有编译失败证据与最小修复。
- 2026-10-30：Flights 200K 原生成器/流式逐行与12查询SQLite真值门禁通过；1B尚未执行。
- 正在执行：public-scale 10M、代码预算0.5；组件逐个写入sealed checkpoint，训练进程不要重复启动。
- 后续独立任务：MSCN隔离环境和恢复训练入口；SSB SF1流式门禁。各代理只拥有相应full_*文件和vendor子目录。
