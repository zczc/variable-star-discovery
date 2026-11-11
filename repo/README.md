# 变星发现代码与实验

这里是公开仓库 [zczc/variable-star-discovery](https://github.com/zczc/variable-star-discovery) 的代码与数据子目录。Git 根目录在上一级，同时管理 `doc/` 和 `repo/`；本目录不单独初始化 Git。

入门与项目资料在 [文档入口](../doc/README.md)。当前没有确认的新变星发现。

## 已有材料

`experiments/2026-11-09-pilot/` 保存前期 33 个目标的探索性分析，包括脚本、查询结果、图表和本地观测文件。见 [试验说明](experiments/2026-11-09-pilot/README.md)。

按用户要求，约 233 MB 的原始 FITS 文件与代码、分析结果一起纳入公开仓库。迁移清单保留文件来源和校验值。没有复制原来的虚拟环境、缓存或第三方论文全文。

## 使用 GitHub

从工作空间根目录执行 Git 操作，保持仓库公开。不要在 `repo/` 内再初始化或克隆一个嵌套仓库。

每次提交或推送前，检查远端是否正确、当前 GitHub 账号是否为 `zczc`，以及作者和提交者邮箱是否均为 `zc3930155@gmail.com`。如果远端已有内容，先检查并整合，不能用强制推送覆盖。

历史脚本保留为原始试验记录。新的可安装工程位于 `src/vstar/`，运行入口、实际进度和限制见 [实现进度](../doc/08-implementation-status.md)，整体方向见 [分析流程与下一步](../doc/04-workflow.md)。

## 第二版开发入口

`vstar review-v2 first_lc.fits second_lc.fits --output path/to/new-review` 检查同一 TIC 的不同观测时段，输出周期候选、来源疑点和 HTML 报告。当前仍是开发版，原批量命令不自动采用它。[实际对照及限制](../doc/13-v2-recognition-results.md)。

## 第三版开发入口

```bash
repo/.venv/bin/vstar review-v3 first_lc.fits second_lc.fits --output path/to/new-review
repo/.venv/bin/python repo/benchmarks/evaluate_v3.py --mode development --output path/to/new-development
repo/.venv/bin/python repo/benchmarks/evaluate_v3.py --mode former-pilot-development --output path/to/new-former-pilot
```

在项目根目录运行，输出目录必须尚不存在。`review-v3` 保留第二版搜索，并增加残余周期证据、整数谐波分组、跨时段歧义处理和窄食逐循环预测；批量 `run` 保持原行为。

[36 个开发案例报告](benchmarks/mixed-v04/index.html)、[原 6 星测试组的开发重跑](benchmarks/former-pilot-v3/index.html)、[完整验收与投稿条件](../doc/14-v3-and-submission-readiness.md)。`v3-integrity-audit.json` 核对 82 段观测、评分前预测、来源及图片校验值和旧结果未改动；它是完整性检查，不是准确率认证。原 `audit_v2.py` 验证历史冻结版本，应在对应 Git 版本运行。

## 两种测光产品的独立检查

`vstar review-products first_lc.fits second_lc.fits --output path/to/new-review` 对 SAP 和 PDCSAP 各自完整搜索，再分别比较观测时段。产品分歧保留人工复核，两种产品一致不自动确认来源。[最新报告](benchmarks/products-v01/index.html)与[说明](../doc/15-products-and-real-controls.md)。
