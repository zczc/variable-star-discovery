# 公开数据中的变星发现

使用 TESS 等公开观测数据，寻找此前未被报告的周期变星。项目从入门学习、小规模试验和可重复验证开始，目前尚无经过完整核验的新发现，也未向 VSX 提交。

当前先做 [识别能力验证](doc/09-validation-first.md)，再考虑新对象筛选。初学者可从 [亲手操作一次](doc/10-human-walkthrough.md) 和 [交互练习](repo/tutorials/first-variable-star/index.html) 开始。

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
