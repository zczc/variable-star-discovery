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
