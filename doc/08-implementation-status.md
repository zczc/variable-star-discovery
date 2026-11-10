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

## 第二阶段与已知目标对照

已实现 MAST 分页查询、固定种子选星、带校验值的原子下载、缓存预算、VSX 查询记录、BLS 辅助搜索、探索性像素定位，以及带缺项检查的本地 VSX 草稿导出。47 项离线测试通过；`historical-v02` 的像素分析重现了 TIC 259238257 的邻星污染，TIC 458747716 保留为周期候选且存在先前研究线索。

两个历史候选的 VSX 导出都保留为草稿，分别有 22 项检查未完成；导出不发送任何资料。

```bash
repo/.venv/bin/vstar run --config repo/configs/pilot.toml --limit 100
repo/.venv/bin/vstar export-vsx 458747716 --run repo/runs/historical-v02
```

导出命令在缺资料时返回退出码 2，并写出字段、引用和缺项清单。人工复核表的结构见 `repo/configs/review-template.json`；图片应放在复核表所在目录内。内部检查通过不代表 VSX 接受。

已知变星对照见 [实际对照结果](../repo/benchmarks/known-v01/README.md)。先冻结目标、参考来源和 1% 的周期比较容差，算法运行时不接收目录周期；完成计算后再比较。3 颗有可用数据的已知变星共 6 个观测时段，Lomb–Scargle 恢复 4 个正确周期、2 个半周期；BLS 在这 6 段数据中均恢复参考周期附近的结果。另有 2 个预选对象没有当前流程支持的非 fast SPOC 光变，未计入成功数，也没有静默替换。

```bash
repo/.venv/bin/python repo/benchmarks/run_known_controls.py --output repo/benchmarks/known-rerun
```

这是刻意选择的小规模正例测试，6 段数据不是 6 颗独立恒星；不能推算总体准确率、误报率或新发现概率。半周期误判是实际观察到的限制，不能只看最强周期峰。

## 当前限制

100 个新目标的运行已启动，结果尚在生成。在线选择目前按观测区、标准 SPOC 产品和多时段覆盖筛选，尚未加星等和拥挤度硬筛；完整的 SIMBAD、VizieR 和 ADS 查询仍标为未执行，需后续接入或人工复核。

像素诊断是启发式位置与谐波比较，尚无精细来源拟合及定位误差。BLS 只搜索有限食持续时间；近似周期比较没有完成正式周期误差估计和相关噪声校准。VSX 导出需要人工提供经核实的测光、历元、类型及附件，不自动编造这些量。任何当前报告都不能直接用于宣布新发现。
