"""Report selection, source holds, and positive losses separately after prediction."""
from pathlib import Path
from collections import Counter
from html import escape
import csv
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
from run_known_controls import classify_period
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/precision-audit-v01'
KINDS={'unattributed_signal':'强光变，来源信息不足','background_coupled':'背景同周期','pointing_coupled':'指向同周期','centroid_coupled':'仅质心同周期','unequal_eclipses':'深浅食','equal_eclipses':'等深食','two_modes':'两个强周期','real_target_control':'真实目标 TU Her','real_neighbor_control':'真实邻星污染'}
LABELS={'manual_target_review':'来源支持目标，进入人工复核','instrument_review_required':'有背景/指向疑点，暂停推荐',
        'exclude_signal_from_target':'不将这个周期信号归属目标','source_evidence_required':'来源证据不足',
        'period_review_required':'周期仍有歧义','analysis_failed':'分析失败'}


def score_case(case,prediction):
    if prediction['status']!='completed':return {'id':case['id'],'status':'failed','error':prediction.get('error')}
    decision=prediction['decision'];review=prediction['source_review'];conclusion=review['conclusion'];period=decision['selected_period_d']
    kind=case.get('challenge',{}).get('kind',case['kind']);truth=None
    if case['kind']=='artificial':
        spec=case['challenge']
        if kind!='two_modes':truth=spec['period_d']*(.5 if kind=='equal_eclipses' else 1)
    elif case['kind']=='real_target_control':truth=case['reference_period_d']
    score=classify_period(period,truth,.01) if period is not None and truth is not None else 'abstained' if period is None else 'unscored'
    return {'id':case['id'],'status':'completed','kind':kind,'selected_period_d':period,'photometric_truth_d':truth,
            'period_score':score,'route':conclusion['route'],'source_status':conclusion['source_status'],
            'manual_target_review':conclusion['eligible_for_manual_target_review'],
            'instrument_caution_count':len(conclusion['instrument_cautions']),
            'centroid_caution_count':len(conclusion['centroid_cautions']),
            'pixel_epochs':len([o for o in review['observations'] if o['pixels']]),
            'diagnostic_period_only':review['period_usage']=='diagnostic_only_not_selected'}


def main():
    out=BASE/'evaluation';path=out/'predictions.json';predictions=read_json(path)
    if not predictions['complete']:raise ValueError('Cannot score incomplete predictions')
    manifest=read_json(BASE/'input-manifest.json');assert predictions['manifest_sha256']==sha256(BASE/'input-manifest.json')
    cases={c['id']:c for c in manifest['cases']};assert set(cases)=={r['id'] for r in predictions['results']}
    rows=[score_case(cases[r['id']],r) for r in predictions['results']];groups=[]
    for kind in sorted({r.get('kind','failed') for r in rows}):
        selected=[r for r in rows if r.get('kind','failed')==kind]
        groups.append({'kind':kind,'cases':len(selected),'v4_period_selected':sum(r.get('selected_period_d') is not None for r in selected),
            'period_scores':dict(Counter(r.get('period_score','failed') for r in selected)),
            'routes':dict(Counter(r.get('route','analysis_failed') for r in selected)),
            'manual_target_review':sum(r.get('manual_target_review',False) for r in selected)})
    result={'created_at':now(),'predictions_sha256':sha256(path),'rows':rows,'groups':groups,
            'real_population_precision':None,'real_population_false_positive_rate':None,'validated_quiet_star_denominator':0,
            'note':'Development challenge counts only. Missing evidence is not a correctly identified false positive. Real contaminants already lacked a selected v4 period.'}
    write_json(out/'results.json',result)
    with (out/'results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=sorted({k for r in rows for k in r}),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    body='<h1>强信号是否可信：来源审查</h1><p>接受弱信号漏检后，本轮检查选出的周期能否归属目标。39 个人工强信号场景，加 TU Her 和两个已知邻星污染对象。旧 v4 周期算法保持冻结。</p>'
    body+='<p>“进入人工复核”只表示本轮有基础目标来源支持，不等于确认变星、完成查重或可以投稿。信息不足会单列；不能把全部拒绝或人工缺少像素当作零误报成绩。</p><table><tr><th>场景</th><th>案例</th><th>v4 选定周期</th><th>来源审查去向</th></tr>'
    for group in groups:
        routes='；'.join(f'{LABELS[k]} {v}' for k,v in group['routes'].items())
        body+=f'<tr><td>{escape(KINDS.get(group["kind"],group["kind"]))}</td><td>{group["cases"]}</td><td>{group["v4_period_selected"]}</td><td>{routes}</td></tr>'
    body+='</table><p>背景/指向命中只说明需要检查仪器；亮斑中心变化也可能来自真实变星。邻星判断使用像素位置、前后时段一致性及已有目录周期。阈值没有标定成精确率或定位置信度。</p><h2>逐例结果</h2><table><tr><th>案例</th><th>选定周期 / 天</th><th>周期对照</th><th>来源去向</th></tr>'
    byid={r['id']:r for r in predictions['results']}
    for r in rows:
        folder=out/r['id'];folder.mkdir(exist_ok=True)
        body+=f'<tr><td><a href="{r["id"]}/index.html">{r["id"]}</a></td><td>{r.get("selected_period_d")}</td><td>{r.get("period_score")}</td><td>{LABELS.get(r.get("route"),"失败")}</td></tr>'
        p=byid[r['id']];case=cases[r['id']]
        detail=f'<h1>{escape(r["id"])}</h1><p>{"人工构造，不能作为真实发现证据。" if case["kind"]=="artificial" else "已有真实开发对照，不是新的独立测试。"}</p>'
        if p['status']!='completed':detail+=f'<pre>{escape(str(p))}</pre>'
        else:
            s=p['source_review'];c=s['conclusion']
            detail+=f'<p>v4 选定周期：{r["selected_period_d"]} 天；周期对照：{r["period_score"]}。</p><p>来源去向：{LABELS[c["route"]]}；来源状态：{c["source_status"]}。</p>'
            if r['diagnostic_period_only']:detail+=f'<p>来源图使用旧数据中保留的候选周期 {s["period_d"]} 天，仅作诊断，没有提升 v4 的周期结论。</p>'
            detail+='<p><a href="period/index.html">周期搜索与光变图</a> · <a href="source/source-review.json">完整来源依据</a> · <a href="source-manifest.json">可复现的来源输入</a></p>'
            for obs in s['observations']:
                detail+=f'<h2>时段 {obs["sector"]}</h2>'
                for product,checks in obs['auxiliary'].items():
                    detail+=f'<p>{product} 辅助通道</p><ul>'
                    for check in checks:detail+=f'<li>{check["name"]}：{check["status"]}；相关系数 {check.get("correlation")}；周期改善 {check.get("periodic_gain")}。</li>'
                    detail+='</ul>'
                if obs['pixels']:
                    image=obs['pixels'];detail+=f'<p>像素结论：{image["status"]}。</p><img src="source/{image["plot"]}" alt="全段和两个半段的周期信号地图">'
                    detail+='<p>绿色圈是目标位置；青色叉是输入目录对象；白线是原测光区域。颜色表示与光变同相的周期变化，位置判断不是精密光斑拟合。</p>'
            if s['errors']:detail+=f'<pre>{escape(str(s["errors"]))}</pre>'
        (folder/'index.html').write_text(page(r['id'],detail))
    body+='</table><p>等深食的最小亮度重复周期为标记周期的一半，完整绕转周期仍不可由该形状唯一确定。两个强周期同时存在时不以强行选一个作为成功。两个真实污染对象本来就没有 v4 最终周期，不能把它们的旧弃选算成来源模块的新成绩。</p><p><a href="results.json">结果</a> · <a href="predictions.json">评分前预测</a> · <a href="../protocol.json">冻结方案</a></p>'
    (out/'index.html').write_text(page('强信号来源审查',body))
    print(groups,flush=True)
    for row in rows:
        if row.get('kind','').startswith('real'):print(row,flush=True)

if __name__=='__main__':main()
