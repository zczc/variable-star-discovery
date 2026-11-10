# 变星发现项目文档

更新日期：2026-11-10。本文档整理项目背景、研究依据、前期试验及已经实现的分析程序。

项目目标是用公开望远镜数据，寻找此前未被报告的周期变星。当前尚无确认的新发现，也没有向 VSX 提交。

当前优先阅读：[先验证识别能力](09-validation-first.md) → [人工识别第一次操作](10-human-walkthrough.md)。按用户要求，先完成能力验证与亲手练习，再讨论新对象筛选。

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
│   └── 01…10 文档
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
