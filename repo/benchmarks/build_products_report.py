"""Human-readable product and event diagnostics, with every development case retained."""
from pathlib import Path
from html import escape
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks';RUN=BENCH/'products-v01'


def main():
    result=read_json(RUN/'results.json');events=read_json(RUN/'event-review.json')
    body='<h1>周期分歧：先检查测光产品有没有改变原来的形状</h1>'
    body+='<div class="notice">这是对已看过的真实星做的开发诊断。SAP 与 PDCSAP 来自同一批光子，不是两次独立观测。本轮没有新发现，不能据此估计真实误报率。</div>'
    body+='<p>SAP 是在指定孔径内量到的亮度；PDCSAP 又做了去除仪器趋势等校正。校正通常有帮助，但有时也会改变大幅度的恒星变化。现在两种产品各自完整搜索周期，各自比较不同观测时段，不再只让 SAP 检查 PDCSAP 已选中的周期。</p>'
    body+='<p>原 6 星组的 SAP 分支有 5 颗选对，PDCSAP 分支为 3 颗。W UMa 和 U Sge 在 SAP 的两个时段都恢复正确周期；RT Aur 长时段恢复约 3.7296 天，短时段仍不足以通过原要求。产品差异统一保留人工复核，不自动替换，也不宣布信号来自目标。</p>'
    body+='<table><tr><th>开发对象</th><th>SAP 最终周期（天）</th><th>PDCSAP 最终周期（天）</th><th>参考周期（天，仅评分）</th><th>状态</th></tr>'
    for r in result['results']:
        cs=r.get('conclusions',{});ps=[cs.get(n,{}).get('selected_period_d') for n in ['SAP','PDCSAP']]
        label=f'<a href="{r["id"]}/index.html">{escape(r["id"])}</a>' if r['status']=='completed' else escape(r['id'])
        values=['未选出' if p is None else f'{p:.8f}' for p in ps]
        status='不可用，保留原分母' if r['status']=='unavailable' else '待查产品差异' if r['comparison']['status']=='product_review_required' else '两产品优选周期一致' if r['comparison']['status']=='both_products_agree' else '未建立充分重复证据'
        body+=f'<tr><td>{label}</td><td>{values[0]}</td><td>{values[1]}</td><td>{r["reference_period_d"] or "不按目标变星评分"}</td><td>{status}</td></tr>'
    body+='</table><p>13 个预选案例，11 个完成、2 个不可用，共 24 段观测，分别分析两种产品。两个历史污染案例也保留：本轮没有重做像素定位，产品一致不能推翻先前的污染证据。AI Vel 仍有多周期歧义，不能强行压成单一周期。</p>'
    body+='<h2>把每次变暗单独量出来</h2><p>将变暗前后的局部亮度连成基线，再量谷底下降多少。蓝色和橙色分别表示相隔一次的两组极小；上排每次变暗都取，下排间隔一个极小再取。圆点是 SAP，浅色叉号是 PDCSAP。右图是对齐后的 SAP 形状。</p>'
    body+='<p>上排两种颜色若持续分开，说明相邻极小确实不同，不能把它们直接当成相同的循环。下排比较重复的同类极小。两排取样窗口不同，深度数字不能直接跨排比较。局部窗口也可能包含恒星结构，这些深度不是标定星等或正式双星模型。</p>'
    for o in events['observations']:
        body+=f'<h3>{o["id"]}：时段 {o["sector"]}</h3><img src="{o["plot"]}" alt="逐次极小深度和对齐形状">'
        body+='<table><tr><th>间隔</th><th>产品</th><th>可量事件</th><th>相邻配对</th><th>偶/奇极小深度中位数</th><th>配对平均差</th></tr>'
        for m in o['measurements']:
            s=m['summary'];delta='证据对数不足' if s['paired_difference'] is None else f'{s["paired_difference"]*100:.3f} 个百分点'
            body+=f'<tr><td>{m["spacing_d"]:.7f} 天</td><td>{m["product"]}</td><td>{s["measured_events"]}</td><td>{s["adjacent_pairs"]}</td><td>{s["even_depth_median"]*100:.3f}% / {s["odd_depth_median"]*100:.3f}%</td><td>{delta}</td></tr>'
        body+='</table>'
    body+='<p>事件配对重采样区间仅作诊断，未标定相关噪声、基线和周期误差；不能当成严格置信度。U Sge 下排每时段只有两对完整事件，程序没有计算该项区间，也没有把缺失事件补成数据。</p>'
    body+='<h2>可信反例仍待建立</h2><p>查到了 Gaia 标准星的短时稳定性监测及 SDSS Stripe 82 标准星目录。但前者多为小时尺度，后者取样稀疏、较暗，波段和精度也不同。它们可以提供待审候选，不能直接给 TESS 的 0.05–8 天筛选当作已确认反例。本轮没有增加“可靠实测安静星”的分母。</p>'
    body+='<p><a href="../../../doc/15-products-and-real-controls.md">完整说明与下一步</a> · <a href="../quiet-controls-research-v01/README.md">反例文献与适用限制</a> · <a href="results.json">结果</a> · <a href="predictions.json">参考评分前预测</a> · <a href="event-review.json">逐次测量</a></p>'
    (RUN/'index.html').write_text(page('测光产品与逐次极小复核',body))
    write_json(RUN/'report-provenance.json',{'created_at':now(),'renderer_sha256':sha256(Path(__file__)),
        'results_sha256':sha256(RUN/'results.json'),'events_sha256':sha256(RUN/'event-review.json')})
    (RUN/'README.md').write_text('''# 两种测光产品的开发诊断

[图文报告](index.html)。13 个预选真实案例，11 个完成、2 个不可用；24 段观测各分析 SAP 和 PDCSAP，所有输入来自旧开发集。先保存全部预测，再与参考周期评分。SAP 与 PDCSAP 共用原观测，不是独立复制。

`review_products.py` 运行全部对象；`review_eclipse_events.py` 量 W UMa、U Sge 每次极小；`build_products_report.py` 生成总览。规则与已看过的诊断范围记录在 `products-protocol-v01.json`。命令拒绝覆盖已有输出。

本轮没有正式选用某一测光产品，没有更新未知目标筛选，没有确认或提交新变星。事件时刻沿用输入 BTJD，未转换为 HJD；深度是本地窗口定义的相对通量变化，不是星等。
''')

if __name__=='__main__':main()
