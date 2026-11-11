# 实现进度与运行方法

更新日期：2026-11-10。

当前优先级已调整为 [识别能力验证](09-validation-first.md) 与 [人工练习](10-human-walkthrough.md)。以下是已完成工作的记录，不表示已证明识别准确；未知对象筛选与新发现推进暂缓。

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

批量下载缓存 `repo/data/` 默认忽略；本轮基准使用的具体 FITS 另行纳入版本控制。运行中的 SQLite 数据库和锁文件不提交到 Git；配置、冻结的目标清单、计算结果、图表和报告可以提交。最初已上传的 38 个 FITS 仍保留在仓库中。

## 第二阶段与已知目标对照

已实现 MAST 分页查询、固定种子选星、带校验值的原子下载、缓存预算、VSX 查询记录、BLS 辅助搜索、探索性像素定位，以及带缺项检查的本地 VSX 草稿导出。47 项离线测试通过；`historical-v02` 的像素分析重现了 TIC 259238257 的邻星污染，TIC 458747716 保留为周期候选且存在先前研究线索。

两个历史候选的 VSX 导出都保留为草稿，分别有 22 项检查未完成；导出不发送任何资料。

```bash
repo/.venv/bin/vstar run --config repo/configs/pilot.toml --limit 100
repo/.venv/bin/vstar export-vsx 458747716 --run repo/runs/historical-v02
```

导出命令在缺资料时返回退出码 2，并写出字段、引用和缺项清单。人工复核表的结构见 `repo/configs/review-template.json`；图片应放在复核表所在目录内。内部检查通过不代表 VSX 接受。

已知变星对照见 [实际对照结果](../repo/benchmarks/known-v01/README.md)。先冻结目标、参考来源和 1% 的周期比较容差，算法运行时不接收目录周期；完成计算后再比较。3 颗有可用数据的已知变星共 6 个观测时段，Lomb–Scargle 恢复 4 个正确周期、2 个半周期；BLS 在这 6 段数据中均恢复参考周期附近的结果。另有 2 个预选对象没有当前流程支持的非 fast SPOC 光变，未计入成功数，也没有静默替换。

[图文对照报告](../repo/benchmarks/known-v01/report/index.html) 展示同一份数据按两种算法各自周期折叠后的差别。辅助搜索给出正确结果，不表示主程序已经自动选对周期。追加检查显示，这 3 颗都能通过当前的跨时段近似重复条件，包括那颗周期算成一半的食双星。

```bash
repo/.venv/bin/python repo/benchmarks/run_known_controls.py --output repo/benchmarks/known-rerun
repo/.venv/bin/python repo/benchmarks/build_known_report.py --run repo/benchmarks/known-rerun
```

这是刻意选择的小规模正例测试，6 段数据不是 6 颗独立恒星；不能推算总体准确率、误报率或新发现概率。半周期误判是实际观察到的限制，不能只看最强周期峰。

## 100 个目标的在线运行与修正

已完成固定种子的 100 个目标、295 份光变分析。两项下载超时均经恢复运行解决，最终没有运行错误。当前结果见 [运行总结](../repo/runs/sector94-100-v02/README.md) 和 [可浏览报告](../repo/runs/sector94-100-v02/report/index.html)。

新增搜索边界检查后，使用完全相同的目标及缓存离线复跑：11 个待复核周期候选、1 个疑似邻星污染、88 个证据不足。TIC 300378621 和 TIC 229804329 的最强峰触及搜索上限，已从候选降级。295 份 LS/BLS 数值与原运行一致，修正的是证据判断。TIC 294052132 的像素信号位置和周期与已知邻星 SSS_J070858.8-563748 相符，标为疑似污染。

报告同时展示 LS、BLS 和前后半段周期，提示约两倍差异及边界问题。全部 48 项测试通过，修改后再次分析 6 段已知变星数据，周期结果保持不变。

本批共缓存 303 个 FITS（295 份光变、8 份像素数据），共 1,097,930,880 字节。100 次 VSX 邻域查询均完成。没有确认的新发现；11 个候选仍含弱信号、分段不一致或已有目录近邻，不能直接当成 11 颗可靠变星。

## 当前限制

在线选择目前按观测区、标准 SPOC 产品和多时段覆盖筛选，尚未加星等和拥挤度硬筛；完整的 SIMBAD、VizieR 和 ADS 查询仍标为未执行，需后续接入或人工复核。当前查询缓存没有过期刷新命令，首次发现核验需重新查询最新记录。

像素诊断是启发式位置与谐波比较，尚无精细来源拟合及定位误差。BLS 只搜索有限食持续时间；近似周期比较没有完成正式周期误差估计和相关噪声校准。VSX 导出需要人工提供经核实的测光、历元、类型及附件，不自动编造这些量。任何当前报告都不能直接用于宣布新发现。

## 第一轮来源复核与混合开发验证

[TU Her 像素检查](../repo/benchmarks/source-9473243-v01/index.html) 已完成：第 25、79 批的深食、浅食都支持来源在目标附近，不等于精密定位或排除未分辨近邻。新增事件前后差分图，并验证线性背景漂移不会被当作该合成测试的局部食信号。当前 50 项软件测试通过。

[混合报告](../repo/benchmarks/mixed-v01/index.html) 保存 36 个冻结案例：34 个完成，2 个已知目标因数据格式不可用而保留。真实已知变量仍是原来的 3 颗、6 段；2 个旧污染案例都重现疑似污染。29 个模拟案例中，4 个深浅食仅 2 个进入候选，4 个漂移有 1 个误报，3 个仪器周期全部进入候选。算法和阈值没有为通过本轮而调整。详见[通俗结果解读](12-mixed-validation-results.md)。

`analyze_series` 与读取 FITS 的 `analyze` 共享同一套数值分析，模拟测试直接使用该核心。测试固定输入、随机种子、代码指纹、文件校验值和软件版本；模拟亮度不是真实星的噪声注入。尚无自动最终周期选择，也没有可信真实安静星反例，因此能力仍未充分验证。

```bash
repo/.venv/bin/python repo/benchmarks/restore_benchmark_inputs.py
repo/.venv/bin/python repo/benchmarks/check_known_source.py
repo/.venv/bin/python repo/benchmarks/run_mixed_controls.py --prepare-only --output repo/benchmarks/mixed-rerun
repo/.venv/bin/python repo/benchmarks/run_mixed_controls.py --output repo/benchmarks/mixed-rerun
repo/.venv/bin/python repo/benchmarks/build_mixed_report.py --run repo/benchmarks/mixed-rerun
```

混合运行拒绝覆盖已存在结果。源码变动会导致旧流水线的 `resume` 拒绝继续；已有报告仍能读取，本轮没有覆盖原 100 个目标的结果。

## 第二版开发规则与首次新样本测试（2026-11-11）

已增加 `vstar review-v2` 独立入口：多候选周期精修、交替周期模板预测、缓慢基线比较、半/倍周期与竞争候选处理、背景/指向/亮斑中心辅助检查，以及多个候选跨时段匹配。原批量 `run` 保持旧行为，第二版尚不用于新发现扩样。

57 项软件测试通过。[最终开发对照](../repo/benchmarks/mixed-v03/index.html) 使用原 36 个案例，34 个完成、2 个不可用。模拟漂移误报 1→0，深浅食检出 2→3（共 4 个），3 个模拟仪器周期均转入来源复核；同时产生过度周期歧义。第一轮第二版的回退结果保留在 `mixed-v02/`。

[新加入的 6 颗真实已知星](../repo/benchmarks/independent-pilot-v01/evaluation/index.html) 在冻结算法后分析，5 颗检出；最终周期 3 颗正确、1 颗双周期错误、1 颗保留歧义、1 颗未通过。新获取的 12 个 FITS、VSX/TIC 身份与 MAST 查询快照已保存。未按这些新结果再次调参，真实安静星反例仍为 0。完整解释见[第二版结果](13-v2-recognition-results.md)。

## 第三版开发重跑（2026-11-11）

第三版已实现 `vstar review-v3`，增加残余周期检查、整数谐波分组、跨时段谐波分歧弃选和窄食逐循环预测。64 项软件测试通过；42 个开发案例、82 段观测已重跑，无运行错误，2 个不可用案例保留。结果见 `doc/14-v3-and-submission-readiness.md`、`repo/benchmarks/mixed-v04/` 与 `repo/benchmarks/former-pilot-v3/`。

原 6 星独立测试组因本轮调试已转为开发样本，旧结果保留。新结果中 SZ Lyn 改为选对，U Sge 的双周期错误改为弃选，但 W UMa 从选对退为弃选；RT Aur 仍漏检。最终正确仍为 3/6；本轮不能作为独立准确率。真实安静星反例仍为零，未知目标筛选和 VSX 投稿仍暂停。下一步复核真实星错误，建立可信实测反例，再冻结规则执行新的独立测试。
