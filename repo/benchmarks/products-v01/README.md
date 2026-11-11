# 两种测光产品的开发诊断

[图文报告](index.html)。13 个预选真实案例，11 个完成、2 个不可用；24 段观测各分析 SAP 和 PDCSAP，所有输入来自旧开发集。先保存全部预测，再与参考周期评分。SAP 与 PDCSAP 共用原观测，不是独立复制。

`review_products.py` 运行全部对象；`review_eclipse_events.py` 量 W UMa、U Sge 每次极小；`build_products_report.py` 生成总览。规则与已看过的诊断范围记录在 `products-protocol-v01.json`。命令拒绝覆盖已有输出。

本轮没有正式选用某一测光产品，没有更新未知目标筛选，没有确认或提交新变星。事件时刻沿用输入 BTJD，未转换为 HJD；深度是本地窗口定义的相对通量变化，不是星等。
