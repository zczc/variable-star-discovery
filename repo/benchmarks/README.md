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

## 第二版与新样本

[第二版新旧对照](mixed-v03/index.html) · [6 颗新加入的真实已知星](independent-pilot-v01/evaluation/index.html) · [通俗解释](../../doc/13-v2-recognition-results.md)。

第一轮第二版结果保留在 `mixed-v02/`；修正版规则在 `v2-protocol-v02.json`，冻结后运行的开发结果在 `mixed-v03/`。随后没有按新真实样本的成绩再次调参。`independent-pilot-v01/` 保存身份与原始观测来源；独立性仅指这些目标未参与此前算法调试，并不代表随机总体抽样或有足够反例。

## 第三版开发对照

[原开发集重跑](mixed-v04/index.html)与[原 6 星测试组重跑](former-pilot-v3/index.html)已完成。六颗旧测试星已用于调试，现为开发样本；不将重跑称为独立测试。规则见 `v3-protocol-v01.json`，完整性记录见 `v3-integrity-audit.json`，结果与投稿条件见[第三版说明](../../doc/14-v3-and-submission-readiness.md)。

## 测光产品与逐次极小

[products-v01](products-v01/index.html)保留 13 个原有真实案例，11 个完成、2 个不可用。24 段观测各分析 SAP/PDCSAP，附 W UMa、U Sge 的逐次极小诊断；属于开发分析。[实测反例资料筛查](quiet-controls-research-v01/README.md)尚未产生可计入 TESS 验收的安静星。

## 第四版与第二次独立小测试

[原开发复核](adjudication-v01/index.html)和[新六星测试](independent-pilot-v02/evaluation/index.html)分别保存。新批共 6 个预选，4 个完成、2 个不可用，3 个最终选对、1 个保留多周期；规则和名单先冻结，未据此调参。
