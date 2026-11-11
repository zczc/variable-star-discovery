# 第二版修正版：固定开发集对照

[打开报告](index.html) · [通俗解释](../../../doc/13-v2-recognition-results.md) · [CSV](comparison.csv)

规则为 [v2-protocol-v02.json](../v2-protocol-v02.json)，科学分析代码与新真实样本输入在 `97efb49` 冻结。沿用 `mixed-v01/input-manifest.json` 的原始输入，36 个案例中 34 个完成，2 个不可用，没有替换。

本目录的规则是开发版 v2.1，目录名表示第三次比较结果：`mixed-v01` 是原版，`mixed-v02` 是第二版首次尝试，`mixed-v03` 是有记录修正后的第二版。最初尝试及其回退保留，未覆盖。

- 原来的模拟漂移误报 1→0。
- 深浅食模拟检出 2→3（共 4 个）；仍有 1 个因缺口与模板覆盖不足而未通过。
- 4 个正弦模拟均检出，亮度候选正确，但 2 个未选择最终周期。
- 2 个完全相同的双食保留轨道歧义；这两个的亮度半轨道周期恢复。
- 3 个模拟仪器周期均转入来源复核。真实 TU Her 和 AI Vel 也被亮斑中心相关性标出，不能把来源复核一概当作证实了污染或仪器错误。
- 原 3 个真实正例均有跨时段周期证据；AI Vel 保留多组周期候选。

严格的最终周期评价没有把“参考周期在候选里”算成选择正确。源头没有检查完的对象仍是候选，确认变星数为 0。没有真实安静星反例，不估计真实总体误报率。

## 复现

在仓库根目录，使用新目录避免覆盖：

```bash
repo/.venv/bin/python repo/benchmarks/evaluate_v2.py --mode development --output repo/benchmarks/v2-dev-rerun
```

`predictions.json` 在读取参考答案进行计分之前保存；`results.json` 增加评分和汇总，保存预测文件 SHA-256、输入、协议与运行程序校验值。单案例的 `prediction.json`、`case.json`、图像和中文页面均保留。`report-provenance.json` 记录后续展示脚本版本。

与这一版冻结后的小规模新真实样本结果配套阅读：[6 颗已知变星](../independent-pilot-v01/evaluation/index.html)。不能仅从开发集得分声称准确率已经确定。
