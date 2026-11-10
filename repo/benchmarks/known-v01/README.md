# 已知变星周期对照

参数在分析前固定；目录周期不传入算法。下表按 1% 相对差比较，半周期和双周期单独列为错误。

| 对象 | 观测区 | 参考周期（天） | LS 周期 | LS 结果 | BLS 周期 | BLS 结果 |
|---|---|---|---|---|---|---|
| TIC 9473243 | 25 | 2.26690000 | 1.13578937 | half_period | 2.26656143 | correct_period |
| TIC 9473243 | 79 | 2.26690000 | 1.13560605 | half_period | 2.26656143 | correct_period |
| RR Lyr | 14 | 0.56677500 | 0.56690980 | correct_period | 0.56618838 | correct_period |
| RR Lyr | 41 | 0.56677500 | 0.56622695 | correct_period | 0.56733941 | correct_period |
| AI Vel | 34 | 0.11157411 | 0.11157154 | correct_period | 0.11152194 | correct_period |
| AI Vel | 35 | 0.11157411 | 0.11154340 | correct_period | 0.11152194 | correct_period |

## 数量与局限

{"ls": {"half_period": 2, "correct_period": 4}, "bls": {"correct_period": 6}}

这是一组特意选择的已知正例，其中包括目录曾给错周期的食双星。多个观测区不等于多个独立恒星。结果不能换算为总体准确率、假阳性率或新发现概率。
误差与不可用目标：
[{"tic": "2597145", "error": "No non-fast SPOC light curves available; target remains an unavailable control"}, {"tic": "403072759", "error": "No non-fast SPOC light curves available; target remains an unavailable control"}]
