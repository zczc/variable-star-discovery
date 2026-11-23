# 公开数据中的变星发现

使用 TESS 等公开观测数据，寻找此前未被报告的周期变星。项目从入门学习、小规模试验和可重复验证开始，目前尚无经过完整核验的新发现，也未向 VSX 提交。

2026-11-23：[VSX 范例与材料草稿](doc/26-vsx-examples-and-draft.md)已完成。核对四份获批公开记录，写好英文复核稿及新候选模板。TIC 302959739 已在 Feinstein 2024 的最终耀发表中有 37 条记录，退出首次变星发现队列；作者候选周期的 Good＝0 限制保留。原 16 个候选累计排除 15 个，只剩 HD 43737A/B 来源未解；当前无可提交对象。以下为各日期的历史记录。

2026-11-22：[TIC 302959739 追加核验](doc/25-candidate-302959739-followup.md)完成。7 段 PDCSAP 中 6 段检出约 10.5 小时的变化；S36 强突增屏蔽后仅在事后诊断中恢复。原始全时段裁定仍弃选，像素模型更支持目标附近来源，但近邻排除和首次发现资格尚未确认。

2026-11-20：[候选查重更新](doc/24-candidate-catalog-followup.md)已完成本轮目录比对。初筛的 16 个对象中，14 个已有 Fetherolf 2023 变光报告，保留 TIC 302959739 和 TIC 393386173 继续核验。前者优先检查，后者与几乎同亮的 HD 43737B 混在 TESS 像素中，来源归属未定。没有确认新发现。

2026-11-18 的[首轮初筛](doc/23-first-discovery-candidates.md)及原始 16 个候选记录保留。本轮补齐 TIC、Gaia、ASAS-SN 和 SIMBAD 备用站查询，更广泛文献及逐星确认仍未完成。

初学者可从 [识别能力验证](doc/09-validation-first.md)、[亲手操作一次](doc/10-human-walkthrough.md) 和 [交互练习](repo/tutorials/first-variable-star/index.html) 开始。

2026-11-12：[有标签千星测试的首次基线](doc/22-labelled-thousand-validation.md)已完成并封存。500 颗已知变星检出 251、漏检 249；500 颗作者未见变光的对照误报 3。精确率 98.82%、检出率 50.20%。最终周期筛选留下 153 颗已知变星，但仅 98 个周期与文献主频倒数直接吻合，其余分歧另列。见[基线与错误复核报告](repo/benchmarks/labelled-validation-v01/baseline-review/index.html)。

上一轮[含未标注对象的千星诊断](doc/21-thousand-target-results.md)仍保留：306 个选中信号、349 个来源任务全部返回，尚有半周期与来源歧义。该轮不用于计算有标签测试的准确率。

## 内容

- [doc/](doc/README.md)：入门知识、项目目标、研究依据、分析流程、前期结果和 VSX 提交说明。
- [repo/](repo/README.md)：代码、实验记录、图表和观测数据。
- [AGENTS.md](AGENTS.md)：后续协作所需的项目约定。

Git 仓库根目录是整个 `variable-star-discovery/`，`repo/` 是代码与数据子目录，不是嵌套的独立 Git 仓库。

仓库按用户要求设为公开，并保存当前完整项目材料，包括前期试验的 38 个 FITS 文件，约 233 MB。代码和数据来源及校验值见 [前期试验说明](repo/experiments/2026-11-09-pilot/README.md)。虚拟环境、缓存和本地凭据配置不纳入版本控制。

## 从哪里开始

先读 [文档入口](doc/README.md)，再看 [已完成试验及限制](doc/05-pilot-2026-11-09.md)。运行现有脚本前，请查看 [环境准备与离线复现说明](repo/experiments/2026-11-09-pilot/README.md)。

实现方案见 [系统框架与执行计划](doc/07-architecture-and-plan.md)，已完成能力和命令见 [实现进度与运行方法](doc/08-implementation-status.md)。

```bash
uv sync --project repo --extra dev --locked
repo/.venv/bin/vstar run --config repo/configs/historical.toml --offline
```

已完成 [100 个目标的筛选](repo/runs/sector94-100-v02/README.md) 和 [已知变星的周期对照](repo/benchmarks/README.md)。对照发现食双星的半周期误判；100 个目标中另有邻星污染和搜索边界造成的误报。结果用于验证、改进流程，尚不能宣布新发现。

新增[第一轮混合验证解读](doc/12-mixed-validation-results.md)与[图文报告](repo/benchmarks/mixed-v01/index.html)：教学对象 TU Her 的基础来源检查支持信号在目标附近；混合测试同时发现窄食漏检、漂移误报和仪器周期进入候选。识别能力仍未充分验证。

2026-11-11：[第二版识别结果](doc/13-v2-recognition-results.md)已保存。开发集有改善；6 颗新加入的真实已知星中，最终周期 3 颗正确、1 颗双周期错误、2 颗未选择，尚未达到可靠识别的验收目标。

同日完成[第三版改进与投稿条件](doc/14-v3-and-submission-readiness.md)：模拟深浅食与平滑周期分别达到 4/4，真实星仍有弃选和漏检。原 6 星测试组现用于开发，最终正确仍为 3/6；没有新的独立验收结果。

最新进展：[测光产品与真实对照复核](doc/15-products-and-real-controls.md)。新增 SAP/PDCSAP 独立搜索，旧 6 星组的 SAP 分支选对 5/6，PDCSAP 仍为 3/6；这是开发诊断，没有新的独立验收结果。

[第四版与新的六星测试](doc/16-adjudication-and-new-test.md)：固定产品/极小规则后，4 个可分析新对象均检出变化，3 个最终周期正确、1 个弃选，另 2 个预选对象不可用；未按这批结果调参。
