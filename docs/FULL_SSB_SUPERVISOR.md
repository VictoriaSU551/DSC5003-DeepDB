# SSB formal operational supervisor

`code/full_ssb_supervisor.py`是独立控制器，只监控根任务已经运行的SF500生成器，
不启动、停止、重启生成器，不修改已封存的科学模块/计划/tiny结果。
生成器工具会话号70812不是Windows PID；控制器不据此查进程或判断生成器生死。

```powershell
.venv/Scripts/python.exe -B -u code/full_ssb_supervisor.py --interval 60
```

checkpoint读取间隔至少60秒。根`ssb_paper.json`仍为CHECKPOINTED时只能等待，
不能把checkpoint临时行数或样本文件已有长度当作生成完成。最终必须4000个连续分片、
3,000,028,242行及13作者整数聚合全部PASS，sample_rows与checkpoint一致。
再调用冻结`full_ssb_model.py formal-gate`独立核对实际raw sample/dimensions的SHA、字节、真实行数。
作者MISMATCH或任何门禁错误保留FAIL，绝不训练后再补称完成。

控制器固定正式plan SHA
`6c4dbad583371c8cee01f7ccd4d9045071f73273cca1f9ffb3d8138ff56a6aca`、
readiness SHA `23c998881c15775449eb0d1c7cfccc1c732459bc803f2c72d046b24498431fc7`、
tiny outer proof SHA `b6aecc212ba4e1b436456729ba6c82bed2f715e3394e31d4e15f6a08818d150d`，
逐一验证readiness中5份代码/测试/协议实际SHA。新增supervisor不属于冻结科学依赖，
其自身及根既有I/O重试适配的SHA写入操作回执。

启动正式模型前必须两套MSCN各100epochs/COMMITTED且无MSCN Python进程，
可用RAM>=4GiB、空闲磁盘>=6GiB。完整physical gate前后都检查资源；
`prelaunch_resources.json`和`launch_resources.json`分别保存检查及MSCN证据。
随后调用已授权的`formal-all --formal-memory-approved`，不重跑SF2或tiny。
OS lock防止两个supervisor重叠；已有FORMAL_RUNNING/FAIL状态拒绝自动重启，
冻结科学guard会进一步保留RUNNING/TAINTED，不能洗白失败namespace。

Windows读取边界已实际验证：在独立temp文件上，即使CreateFileW使用GENERIC_READ及
READ|WRITE|DELETE共享7，raw handle打开时本机`os.replace`仍可能WinError5；
raw/CRT/text wrapper三条路径失败、关闭handle后成功的原证据保留在
`output/full/ssb/supervisor/shared_read_probe/receipt.json`。
不能将share7描述为绝对不阻塞替换。
最终控制器仍请求share7，但一次有界读取<=32MiB bytes后立即关闭handle，再解析JSON。
测试明确在parser执行期间对同一路径替换成功，且读者拿到原完整快照；
state记录每次checkpoint bytes和handle_read_seconds。
仍存在短binary read窗口，由根任务已运行的`full_ssb_run.py`/`full_flights_run.py`
对WinError5/32的有界原子写重试覆盖；没有改生成器/注册表/文件系统来掩盖该限制。

控制器自己的首轮monitor曾在上述并发test失败后被停止，停止的仅为
supervisor两个Python launcher进程；生成器、consumer、模型和数据均未停止或重启。
所有诊断证据保留。修复后8个控制器测试通过（0.09秒）。

正式stdout/stderr、进程回执、资源门禁、最终摘要及selfseal均写
`output/full/ssb/supervisor/`。最终只在冻结模型/13point/13CI与FORMAL外层receipt通过后，
写`FORMAL_COMPLETE_PENDING_ROOT_REVIEW`，统计缺组/额外组、CI可用组、真实时间/峰值/磁盘。
等待生成期间的状态始终为WAIT_GENERATION或WAIT_RESOURCES，不报告正式阶段已完成。
