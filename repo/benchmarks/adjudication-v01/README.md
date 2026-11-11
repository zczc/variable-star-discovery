# 第四版开发复核

[报告](index.html)。复用 `products-v01` 全部 13 个原真实案例，11 个完成、2 个不可用。参考评分前预测、逐次极小判断和 RT Aur 短时段失败预测均保留。已有对象全部是开发数据，不估计独立准确率。

原 6 星组按新规则最终选对 5/6；RT Aur 仍未选出。运行命令：`repo/.venv/bin/python repo/benchmarks/evaluate_v4.py --mode development --output NEW_DIRECTORY`。旧报告可阅读，复现应使用本轮冻结版本。
