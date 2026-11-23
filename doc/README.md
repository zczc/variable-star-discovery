# 变星发现项目文档

更新日期：2026-11-23。本文档整理项目背景、研究依据、前期试验及已经实现的分析程序。

项目目标是用公开望远镜数据，寻找此前未被报告的周期变星。当前尚无确认的新发现，也没有向 VSX 提交。

2026-11-23：[VSX 范例与材料草稿](26-vsx-examples-and-draft.md)完成。四份获批公开记录可供参考，英文复核稿和新候选模板已保存。TIC 302959739 已有 37 条先前耀发记录，退出首次发现队列；原 16 个候选只剩 HD 43737A/B，来源与新颖性未定。以下保留历史进展。

2026-11-22：[TIC 302959739 追加核验](25-candidate-302959739-followup.md)完成。7 段 PDCSAP 中 6 段检出约 10.5 小时的变化；S36 强突增屏蔽后仅在事后诊断中恢复。原始全时段裁定仍弃选，像素模型更支持目标附近来源，但近邻排除和首次发现资格尚未确认。

2026-11-20 的[候选查重更新](24-candidate-catalog-followup.md)将 16 个初筛对象中的 14 个识别为已有论文报告，剩下 TIC 302959739 和 TIC 393386173。前者优先核验，后者存在近等亮双星的来源歧义。更多文献、观测及最终周期复核尚未完成。[11 月 18 日初筛](23-first-discovery-candidates.md)原记录保留。

当前结果见[有标签千星测试的首次基线](22-labelled-thousand-validation.md)：1,000 颗全部完成，TP／FN／FP／TN 为 251／249／3／497，原始预测已封存。较严格的周期筛选与文献周期分歧另列，尚未通过新发现可靠性验收。入门可读[先验证识别能力](09-validation-first.md)与[人工识别第一次操作](10-human-walkthrough.md)。按用户要求，先完成能力验证，再讨论新对象筛选。

此前[含未标注对象的千星诊断](21-thousand-target-results.md)及其来源复核单独保留。当前基线使用 500 个论文变星和 500 个作者未见变光的真实对照，变光检出与最终周期分别评分。

## 阅读顺序

| 文档 | 内容 |
|---|---|
| [项目目标与当前状态](01-project.md) | 做什么、成功标准、用户已确定的方向 |
| [从零认识变星](02-basics.md) | 恒星、变星、新星、周期和光变曲线 |
| [发现空间与资源](03-evidence-and-resources.md) | 近期论文是否真的发现新对象、难度和资源估计 |
| [分析流程与下一步](04-workflow.md) | 数据选择、周期分析、污染排查、文献查重和下一轮建议 |
| [前期试验记录](05-pilot-2026-11-09.md) | 33 个目标的试验，以及三个重点对象的结论 |
| [VSX、发现者与命名](06-vsx-and-credit.md) | 如何提交、审核时间、发现者记录和命名限制 |
| [系统框架与执行计划](07-architecture-and-plan.md) | 第一版架构、数据与任务状态、质量验证和分阶段验收 |
| [实现进度与运行方法](08-implementation-status.md) | 已完成能力、实际验证结果和可运行的命令 |
| [先验证识别能力](09-validation-first.md) | 新的优先级、独立正反例验证与项目内验收目标 |
| [人工识别第一次操作](10-human-walkthrough.md) | 常见人工工作流程、真实数据交互练习与证据边界 |
| [真实观测里的术语](11-case-glossary.md) | 页面名词、坐标轴、处理选项和文件字段的入门解释 |
| [混合验证实际结果](12-mixed-validation-results.md) | TU Her 来源检查、模拟漏检与误报、下一步 |
| [第二版实际结果](13-v2-recognition-results.md) | 新旧对照、未参与调参的 6 颗真实星、仍有的周期错误 |

文档中的论文结论、本地计算结果和未来建议分别标明，不把候选写成已确认发现。

## 工作空间

```text
variable-star-discovery/
├── README.md
├── AGENTS.md
├── .gitignore
├── .gitattributes
├── doc/
│   ├── README.md
│   └── 01…25 文档
└── repo/
    ├── README.md
    ├── .gitignore
    ├── src/vstar/
    ├── tests/
    ├── configs/
    ├── benchmarks/
    ├── runs/
    └── experiments/2026-11-09-pilot/
```

`repo/` 已保存前期试验材料，使用方式见 [代码与实验说明](../repo/README.md)。原始观测文件与代码、图表一起纳入公开仓库，避免后续工作依赖临时目录。

按用户 2026-11-10 的要求，整个工作空间由公开仓库 [zczc/variable-star-discovery](https://github.com/zczc/variable-star-discovery) 管理，同时包含 `doc/` 和 `repo/`。仓库内容现在可公开访问；其中的候选分析不代表已经确认或获得 VSX 认可的新发现。

- [第三版改进与提交条件](14-v3-and-submission-readiness.md)：全部开发重跑、真实星退步，以及筛选验收与 VSX 单星投稿的区别。

- [测光产品为何影响周期判断](15-products-and-real-controls.md)：SAP/PDCSAP 完整比较、逐次深浅极小、实测反例资料的适用范围。

- [固定周期规则后的新测试](16-adjudication-and-new-test.md)：第四版规则、新的六星测试、RT Aur 短时段失败与验收缺口。

- [实测背景中的信号能找回多少](17-real-residuals-and-standard-controls.md)：34 个实测残差案例、三颗标准星检查、弱信号与原星残留周期的错误。

- [标准星背景下的识别边界](18-standard-star-injection-results.md)：144 个直接注入、不同食持续时间的恢复表现，以及预测门槛和三倍周期分歧导致的弃选。

- [先检查选出的信号是否可靠](19-precision-first-source-review.md)：精确率优先的新取向、来源审查、仪器耦合挑战、真实邻星污染和目标对照。

- [千星验证怎么判断结果](20-thousand-target-validation.md)：1,000 个新对象的分组、全部 349 个对象的来源复核、真实周期分歧和数据成本。

- [千星验证的本轮结论](21-thousand-target-results.md)：全部任务返回后的实际结果、选中信号与风险对照的区别，以及下一轮改进顺序。

- [用有标签的千星直接考试](22-labelled-thousand-validation.md)：独立论文标签、500 正例和 500 反例，以及直接对照的评分方式。
