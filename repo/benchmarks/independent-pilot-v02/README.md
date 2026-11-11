# 第二次独立小规模正例测试

[完整报告](evaluation/index.html)。名单和 v4.0 规则在取得本批光变前已提交，未按结果调参。6 个预选对象，4 个可分析、2 个不可用；4 个均检出变化，3 个选对最终周期，VZ Cnc 保留多周期歧义。没有实测反例，不能测出误报率或宣称完成总体验收。

获取脚本 `acquire_independent_pilot_v02.py`，冻结名单 `independent-pilot-protocol-v02.json`，分析脚本 `evaluate_v4.py`。`input-manifest.json` 保存 8 个原始 FITS 的 MAST URI、位置和校验值；`identity-audit.json` 核对 VSX、TIC 和 FITS 标识。原始 FITS 与对应下载记录单独纳入 Git，其他缓存不纳入。

如果后续按本批错误调试，必须改记为开发数据，不能继续声称独立验证。
