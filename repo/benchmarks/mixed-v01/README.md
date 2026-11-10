# 第一轮混合开发测试

[图文报告](index.html) · [通俗解释](../../../doc/12-mixed-validation-results.md) · [CSV](results.csv) · [JSON](results.json)

本轮完成 34 / 36 个案例，另外 2 个预选已知星缺少当前支持的数据产品，保留为不可用。没有新的变星发现，也没有建立真实总体准确率。

- 3 个真实已知星均进入周期候选；2 个旧污染例均重现疑似邻星污染。
- 6 个独立噪声、6 个相关噪声模拟均未进入候选；4 个非周期漂移有 1 个误报。
- 4 个正弦模拟全进入候选，4 个深浅不同的食仅 2 个进入候选。
- 2 个相同双食模拟都恢复亮度的半轨道周期，不能唯一认定绕转周期。
- 3 个模拟仪器周期全部进入候选。辅助仪器通道保留，但现有初筛不使用。

这些是候选告警与漏检，不能叫误确认的新发现。可信真实安静星数是 0，真实误报率未知。没有自动最终周期选择器，分别报告 LS 与 BLS 的结果。

## 固定顺序与文件

1. `70b43f2` 提交 [mixed-protocol-v01.json](../mixed-protocol-v01.json)：36 个案例、参数、种子、计分口径。
2. `d008540` 提交模拟公式、分析脚本、全部模拟输入和 [input-manifest.json](input-manifest.json)，此时没有运行混合分析。
3. 运行同一个 `analyze` / `analyze_series` 数值核心，以 `pipeline.assess` 的 5% 跨时段规则进行初筛，再对两个旧污染例运行已有像素检查。最终保存所有结果，没有修改标准以追求通过。

`results.json` 包含完整配置、依赖版本、Git 提交、代码指纹、输入校验值、每段观测及错误记录。每个案例目录有自己的 `case.json`、单段结果和图像。模拟数据在 `inputs/*.npz`，原始时间分辨率的数据与生成信号都保留。

`report-provenance.json` 记录报告脚本、结果和额外相位比较图的校验值。相位比较图可以使用参考周期做解释；参考值没有送入周期搜索。报告是在看过结果后写的解释，不是预先冻结的算法组成部分。解释脚本仅适用于这一版结果；如果复跑的代码指纹或汇总指标不同，它会要求重写说明，避免沿用旧结论。

真实输入共 12 个光变 FITS；加上本轮来源检查共 4 个像素 FITS，两个基准合计 16 个唯一 FITS、206,291,520 字节。其中 4 个已包含在最初试验中，其余本轮纳入版本控制。虽然所在的 `repo/data/` 默认用于缓存，这些具体文件已显式跟踪。模拟数组约 15 MB，也已跟踪；虚拟环境和其他批量缓存仍不提交。

## 模拟公式

模拟仅借用 3 颗已知星的两段质量筛选后、尚未分箱的真实时间戳，不使用其真实亮度。所有模拟再按主程序规则分为 10 分钟平均值。随机生成器为 NumPy `default_rng(SeedSequence([seed, epoch_index]))`，不同时段使用独立噪声。周期信号使用第一个时段起点为共同时间零点，固定初相位为 0.137 圈。

- 独立噪声：每次测量加标准差 0.0025 的零均值高斯噪声。
- 相关噪声：平稳 OU 过程，相关系数 `rho = exp(-dt/tau)`，一步为 `rho * previous + sigma * sqrt(1-rho^2) * N(0,1)`，另加上述独立噪声；时间间隔包含真实缺口。
- 漂移：`u = (t-t_min)/(t_max-t_min)-0.5`；信号为 `slope * (u + curvature*u^2)`。每个时段使用同样的规定形状，但噪声独立。
- 正弦和仪器周期：`amplitude * sin(2*pi*((t-origin)/P+0.137))`，其中 amplitude 是半振幅。仪器模拟另保存同一信号叠加独立噪声的辅助通道。
- 食：在相位 0、0.5 各放一个有限宽的下降；相位距离 `d < width/2` 时，下降为 `depth*cos(pi*d/width)^2`，之外为零。次食深度乘以预定比例。相同双食的亮度周期就是 `P/2`。

保存的 `flux` 为 `1 + signal + noise`。送入分析时除以中位数再减 1，与真实读取逻辑一致。误差列只提供独立噪声的标准差；相关噪声并未被伪装成已经建模的独立误差。模拟的 SAP/PDC 共用同一测量序列，不提供独立证据，也没有模拟真实仪器校正。

## 复跑

在仓库根目录执行，使用新的输出目录，避免覆盖旧结果：

```bash
uv sync --project repo --extra dev --locked
repo/.venv/bin/python repo/benchmarks/restore_benchmark_inputs.py
repo/.venv/bin/python repo/benchmarks/run_mixed_controls.py --prepare-only --output repo/benchmarks/mixed-rerun
repo/.venv/bin/python repo/benchmarks/run_mixed_controls.py --output repo/benchmarks/mixed-rerun
repo/.venv/bin/python repo/benchmarks/build_mixed_report.py --run repo/benchmarks/mixed-rerun
```

恢复脚本默认只验证。若从部分副本开始，可加 `--download-missing`，从冻结的 MAST URI 下载并核对 SHA-256；不会覆盖已有但校验不符的文件。已完成的混合结果不可覆盖；准备输入后若代码或参考文件变化，分析会拒绝继续。

## 局限与下一步

这是开发集。3 个真实正例和 2 个污染例以前已经看过，模拟也不是独立恒星样本。相同天体不同时段不增加独立天体数，模拟数量不能替代真实反例数。下一步是改进周期选择与漂移、仪器来源检查，建立有可信标签的实测对照，冻结独立测试集；此前继续暂停新发现推进。
