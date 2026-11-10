# 第一次人工识别练习

[打开练习](index.html) · [操作说明](../../../doc/10-human-walkthrough.md) · [来源清单](provenance.json)

基于 TIC 9473243 的 Sector 25、79 已下载观测，提供光变、周期图、可调周期的相位图，以及测光和质量筛选切换。页面可离线运行，没有外部脚本或网络请求。来源和说明链接需要文件位于仓库中；单独复制 HTML 后核心交互仍可使用。

本例用于学习，不是新的独立准确率测试。没有完成本例的精细像素来源定位、跨年相位连接、正式周期误差或物理分类验证。

在项目根目录重新生成：

```bash
repo/.venv/bin/python repo/tutorials/build_first_lab.py
```

需要已知目标观测缓存 `repo/data/known-controls/`；构建器校验 FITS 的 SHA-256，并检查基准方案的 LS/BLS 周期与已保存结果一致。CSV 保留源观测的时间、质量标记、两个测光产品和误差；不是标准星等表或 VSX 提交文件。
