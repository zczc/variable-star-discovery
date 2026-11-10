# 已知变星对照

`known-controls.json` 保存参考周期及来源，`run_known_controls.py` 使用与主程序相同的分析模块，先计算、后比较。`known-v01/README.md` 是第一轮实测结果。

[打开图文对照报告](known-v01/report/index.html)：表格比较参考周期与两种算法结果；图片展示同一份数据按各自周期折叠后的形状。报告不会代替程序自动选择最终周期。

```bash
repo/.venv/bin/python repo/benchmarks/run_known_controls.py --output repo/benchmarks/known-rerun
repo/.venv/bin/python repo/benchmarks/build_known_report.py --run repo/benchmarks/known-rerun
```

图文报告从保存结果和通过校验值检查的观测文件生成，不重跑搜索。首轮使用固定的 10 分钟分箱；后续运行会把完整分析配置写入结果。原始下载位于 `repo/data/known-controls/`，本轮使用的 FITS 已与来源、校验值、结果和图表一同纳入 Git。

对象包括三颗论文中的食双星，以及 VSX 中的 RR Lyr 和 AI Vel。保留了未取得支持格式数据的对象，不把它们悄悄排除后宣称全部成功。

同一颗星的多个观测区不是独立恒星样本，结果仅用于发现算法问题。完整准确率评估仍需更多类型和幅度的正例、足够的非变星或噪声对照，以及预先固定的判定标准。

对这 3 颗星追加的 [跨时段检查记录](known-v01/repeatability-audit.json) 显示，全部通过当前 5% 容差的近似周期重复检查，其中包含 TIC 9473243 的错误半周期。它不是额外的独立样本，也说明跨时段一致不能单独保证周期正确。完整流水线目前没有自动选择最终物理周期或分类的能力。

RR Lyr 的 TIC 星等字段与其 V 星等明显不一致，身份对应也保存了 HIP/KIC 等信息。这个问题提醒我们不能盲目信任单个目录字段。这里只评价时间序列的周期恢复，不据此声称完成了绝对测光和无污染定位。

## 新完成的来源检查与混合测试

- [TU Her 来源复核](source-9473243-v01/index.html)：两时段深食与浅食差分、邻域目录、三种测光区域。
- [36 个混合案例](mixed-v01/index.html)：3 个可用真实正例、2 个不可用正例、2 个旧污染例、29 个明确模拟的正反例。
- [结果与下一步](../../doc/12-mixed-validation-results.md)：目前不能宣称识别准确率已确定。

方法在 `mixed-protocol-v01.json`、`simulate_controls.py`、`run_mixed_controls.py`，输入与结果分别保存。复跑命令见 [mixed-v01/README.md](mixed-v01/README.md)。
