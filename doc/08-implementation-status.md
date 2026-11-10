# 实现进度与运行方法

更新日期：2026-11-10。

## 第一阶段

已实现可安装的 Python 工程、TOML 配置、离线历史数据导入、质量过滤与分箱、Lomb–Scargle 周期初筛、分段及跨观测区比较、SQLite 任务记录和恢复、HTML/CSV/JSON 报告。

在干净的 Python 3.12 环境完成验证，依赖锁定在 `repo/uv.lock`。38 项测试通过，包括全部 29 个历史初筛周期复现、带数据缺口的人工正弦信号、失败重试和损坏结果重算。历史输入文件没有改动。

示例运行是 `repo/runs/historical-v01/`：33 个目标记录，29 个有光变数据，包含追加观测共 35 份光变分析。4 个历史目录位置匹配保留为未重新核验的预筛结果。没有确认的新发现。

## 运行

以下命令在工作空间根目录执行。支持 macOS 和 Linux；运行锁目前使用 POSIX 文件锁。

```bash
uv sync --project repo --extra dev --locked
repo/.venv/bin/vstar run --config repo/configs/historical.toml --offline
repo/.venv/bin/python -m pytest repo/tests -q
```

`run` 会显示新运行目录和报告路径。打开其中 `report/index.html` 查看总览，点击 TIC 编号查看单星报告。运行目录可以使用绝对路径：

```bash
repo/.venv/bin/vstar resume repo/runs/<run_id>
repo/.venv/bin/vstar report repo/runs/<run_id>
repo/.venv/bin/vstar inspect 458747716 --run repo/runs/<run_id>
```

恢复会检查源数据及已完成结果的校验值。程序源码发生变化后应创建新运行，旧报告仍能阅读。已有运行名不能覆盖。退出码 2 表示部分目标失败，成功结果会保留。

下载缓存 `repo/data/`、运行中的 SQLite 数据库和锁文件不提交到 Git；配置、冻结的目标清单、计算结果、图表和报告可以提交。最初已上传的 38 个 FITS 仍保留在仓库中。

## 仍待实现

在线选星与下载、完整的像素诊断、目录查询状态、VSX 草稿导出等按后续阶段推进。当前的近似周期比较只是筛选规则，没有完成正式周期误差估计和相关噪声校准；不能将报告直接用于宣布新发现。
