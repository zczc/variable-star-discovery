"""Render frozen v4 outcomes; do not hide errors or abstentions."""
from pathlib import Path
from html import escape
import os
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks'
STATUS={'product_agreement':'两产品周期一致','event_supported_period_product_caution':'逐次极小支持周期，产品/来源仍需复核',
        'unresolved':'未确定周期','nonharmonic_or_missing_product_support':'另一产品缺少相同周期或有其他竞争解释','analysis_failed':'分析失败'}


def build(run):
    r=read_json(run/'results.json');independent=r['mode']=='independent';m=r['metrics']
    title='第四版：新的六星正例测试' if independent else '第四版：固定规则后的开发复核'
    body=f'<h1>{title}</h1><div class="notice">'
    body+=('规则和名单在获取这组光变前已提交，未按本轮结果调参。只有 6 个预选正例，不能代表总体准确率，更没有测出误报率。' if independent else '所有对象已经参与调试，不能把这里的改善称为独立准确率。')
    body+='选择亮度周期不等于确认变化来源，也不等于发现新变星。</div>'
    body+=f'<p>预选 {m["cases"]} 个，完成 {m["completed"]} 个，不可用 {m["unavailable"]} 个，运行失败 {m["failed"]} 个；最终周期正确 {m["correct"]} 个。未选出、选错和不可用全部保留。</p>'
    body+='<p>两种产品各自完整搜索；若只剩半/倍周期分歧，要求同一周期在两种产品的每个时段都有支持，再检查深浅交替及同类极小。等深、证据不足或其他竞争解释继续保留疑问。短时段的预测诊断不增加独立周期测量次数。</p>'
    body+='<table><tr><th>对象及产品证据</th><th>参考周期（天）</th><th>第四版周期（天）</th><th>评分</th><th>说明</th></tr>'
    for x in r['results']:
        d=x.get('decision');p=d['selected_period_d'] if d else None
        url=f'{x["id"]}/index.html' if independent else f'../products-v01/{x["id"]}/index.html'
        name=f'<a href="{url}">{escape(x["id"])}</a>' if x['status']=='completed' else escape(x['id'])
        status=STATUS.get(d['status'],d['status']) if d else x.get('reason','不可用')
        body+=f'<tr><td>{name}</td><td>{x["reference_period_d"] or "不按目标周期评分"}</td><td>{f"{p:.8f}" if p else "未选出"}</td><td>{escape(x["score"])}</td><td>{escape(status)}</td></tr>'
    body+='</table>'
    if not independent:
        body+='<h2>RT Aur 短时段：预测没有通过</h2><p>用长时段的周期和形状，在短时段第一轮可见的数据上拟合相位、幅度及基线，再预测后面的亮度。预测比只取后段平均亮度更差，因此没有把短观测补算为通过。</p><img src="rt-aur-transfer.png" alt="拟合段与未参与拟合的后段预测">'
    else:
        body+='<p>本轮没有调整阈值或替换失败对象。若后续用这些错误调试，这批对象也必须转为开发样本；不能反复测试后仍称其为独立成绩。</p>'
    doc=os.path.relpath(ROOT/'doc/16-adjudication-and-new-test.md',run)
    body+=f'<p><a href="{doc}">通俗说明、限制与下一步</a> · <a href="results.json">全部结果与逐次极小证据</a> · <a href="predictions.json">参考周期评分前的预测</a></p>'
    (run/'index.html').write_text(page(title,body))
    write_json(run/'report-provenance.json',{'created_at':now(),'results_sha256':sha256(run/'results.json'),'renderer_sha256':sha256(Path(__file__))})

if __name__=='__main__':
    build(BENCH/'adjudication-v01')
    build(BENCH/'independent-pilot-v02/evaluation')
