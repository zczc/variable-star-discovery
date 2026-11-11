"""Score saved predictions; never fit or change the detector."""
from collections import Counter
from html import escape
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from vstar.io import read_json,write_json,sha256,now
from vstar.photometry import read_lightcurve,LightCurve,bin_lightcurve
from vstar.reports import page
from run_known_controls import classify_period
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/benchmarks/empirical-injection-v01'


def score_case(row,case,tolerance):
    spec=case['signal'];decision=row.get('decision') or {};products=row.get('products') or {}
    period=decision.get('selected_period_d');truth=spec['period_d']
    if row['status']!='completed':score='analysis_failed'
    elif not truth:score='baseline_period_selected' if period else 'baseline_abstained'
    else:score=classify_period(period,truth,tolerance) if period else 'abstained'
    supported=[]
    if truth:
        for name in ('SAP','PDCSAP'):
            observations=products.get('observations',[])
            if len(observations)>=2 and all(any(c['qualifies'] and abs(c['period_d']/truth-1)<tolerance
                for c in o['products'][name]['result']['candidates']) for o in observations):supported.append(name)
    any_repeated=any(c['periodic_detected'] for c in products.get('conclusions',{}).values())
    return {'id':row['id'],'base_id':case['base_id'],'shape':spec['shape'],'amplitude_fraction':spec['amplitude_fraction'],
            'phase':spec['phase'],'reference_period_d':truth,'selected_period_d':period,'score':score,
            'truth_supported_products_all_epochs':supported,'any_repeated_signal':any_repeated,
            'decision_status':decision.get('status'),'status':row['status']}


def main():
    predictions_path=OUT/'evaluation/predictions.json';prediction=read_json(predictions_path)
    if not prediction['complete']:raise ValueError('Cannot score incomplete prediction set')
    manifest=read_json(OUT/'input-manifest.json');protocol=read_json(OUT/'protocol.json')
    assert prediction['manifest_sha256']==sha256(OUT/'input-manifest.json')
    cases={c['id']:c for c in manifest['cases']}
    assert len(prediction['results'])==len(cases)==len({r['id'] for r in prediction['results']})
    rows=[score_case(r,cases[r['id']],protocol['period_tolerance']) for r in prediction['results']]
    nonzero=[r for r in rows if r['shape']!='zero'];summary=[]
    for shape in ('sine','unequal_eclipses'):
        for amp in (.001,.003,.01,.03):
            group=[r for r in nonzero if r['shape']==shape and r['amplitude_fraction']==amp]
            summary.append({'shape':shape,'amplitude_fraction':amp,'total':len(group),
                            'correct_final':sum(r['score']=='correct_period' for r in group),
                            'qualified_truth_candidates':sum(bool(r['truth_supported_products_all_epochs']) for r in group),
                            'counts':dict(Counter(r['score'] for r in group))})
    result={'created_at':now(),'predictions_sha256':sha256(predictions_path),'report_script_sha256':sha256(Path(__file__)),
            'rows':rows,'summary':summary,'injected_counts':dict(Counter(r['score'] for r in nonzero)),
            'zero_injection':[r for r in rows if r['shape']=='zero'],'independent_background_stars':2,
            'population_false_positive_denominator':0,'confidence_interval':None,
            'note':'Correlated injections into two variable-star residual backgrounds. No population accuracy, discovery probability, or calibrated sensitivity limit.'}
    write_json(OUT/'evaluation/results.json',result)
    with (OUT/'evaluation/results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
    categories=['correct_period','half_period','double_period','not_recovered','abstained','analysis_failed']
    labels=['OK','P/2','2P','Other','Abstain','Failed']
    grid=[];names=[]
    for base in ('sz-lyn','rs-boo'):
        for shape in ('sine','unequal_eclipses'):
            for phase in (.13,.57):
                group=sorted([r for r in nonzero if (r['base_id'],r['shape'],r['phase'])==(base,shape,phase)],key=lambda r:r['amplitude_fraction'])
                grid.append([categories.index(r['score']) for r in group]);names.append(f'{base} / {"sine" if shape=="sine" else "eclipses"} / phase {phase}')
    grid=np.array(grid);fig,ax=plt.subplots(figsize=(10,6),layout='constrained')
    ax.imshow(grid,cmap=ListedColormap(['#5cbb95','#e8b766','#d5a464','#e48378','#d4d9e0','#985c9c']),vmin=0,vmax=5,aspect='auto')
    for (y,x),value in np.ndenumerate(grid):ax.text(x,y,labels[value],ha='center',va='center',fontsize=11)
    ax.set(xticks=range(4),xticklabels=['0.1%','0.3%','1%','3%'],yticks=range(8),yticklabels=names,
           xlabel='Injected full peak-to-peak flux / source median',title='Frozen v4 final period recovery | two empirical residual backgrounds')
    fig.savefig(OUT/'evaluation/recovery.png',dpi=150);plt.close(fig)
    for base in manifest['bases']:
        fig,axes=plt.subplots(4,2,figsize=(12,9),layout='constrained')
        for j,obs in enumerate(base['observations']):
            with np.load(ROOT/obs['residual_path']) as arrays:
                for i,product in enumerate(('SAP','PDCSAP')):
                    lc=read_lightcurve(ROOT/obs['source']['path'],product+'_FLUX');raw=bin_lightcurve(lc,10)
                    residual=bin_lightcurve(LightCurve(lc.time,arrays[product+'_residual'],lc.error,{}),10)
                    for k,curve in enumerate((raw,residual)):
                        ax=axes[j*2+i,k];ax.plot(curve.time-curve.time.min(),curve.flux*100,'.',ms=1)
                        ax.set(title=f'Sector {obs["source"]["sector"]} {product}: '+('original' if k==0 else 'cross-fitted residual'),ylabel='Relative flux (%)',xlabel='Days from epoch start')
        fig.suptitle(base['id']+': residuals can retain stellar variability and correlated errors')
        fig.savefig(OUT/'evaluation'/(base['id']+'-background.png'),dpi=130);plt.close(fig)
    body='<h1>实测残差注入：第四版固定规则的压力测试</h1>'
    body+='<p>从旧开发样本扣除主要周期，留下实测起伏，再加入已知信号。共有两颗背景星、32 个注入案例和 2 个零注入。它们不是 34 颗独立恒星，也不是已证明不变的反例。</p>'
    body+='<p>幅度是亮度最高与最低的全差，占源通量中位数的比例。OK 表示最终周期在注入真值的 1% 内；Abstain 表示没有选择最终周期；Other 表示选择了其他周期。没有选择不等于没有变化。</p><img src="recovery.png" alt="按背景、形状、相位和幅度划分的最终周期恢复结果">'
    body+='<table><tr><th>信号</th><th>全幅度</th><th>最终选对</th><th>两时段都有真值附近合格候选</th></tr>'
    for s in summary:body+=f'<tr><td>{"平滑起伏" if s["shape"]=="sine" else "深浅不等的食"}</td><td>{s["amplitude_fraction"]:.1%}</td><td>{s["correct_final"]}/{s["total"]}</td><td>{s["qualified_truth_candidates"]}/{s["total"]}</td></tr>'
    body+='</table><p>“合格候选”要求至少一种产品在两个时段都有注入周期附近的合格候选，仍可能有竞争周期。某个幅度恢复良好不代表所有周期、所有恒星都能达到。</p><h2>零注入背景</h2><ul>'
    for r in result['zero_injection']:body+=f'<li>{r["base_id"]}：{r["decision_status"]}；选定周期 {r["selected_period_d"]} 天；至少一种产品有跨时段重复信号：{r["any_repeated_signal"]}。</li>'
    body+='</ul><p>背景来自真实变星的残差，可能还有原星变化；以上结果不能叫作真实安静星误报或正确拒绝。</p>'
    for base in manifest['bases']:body+=f'<img src="{base["id"]}-background.png" alt="{base["id"]} 原始与实测残差比较">'
    body+='<h2>逐项结果</h2><table><tr><th>案例</th><th>最终周期</th><th>判定</th></tr>'
    for r in rows:
        review=f'<h1>{escape(r["id"])}</h1><p>这是人工注入案例，非原始恒星观测，也不是新发现。</p>'
        review+=f'<p>加入信号的周期：{r["reference_period_d"]} 天；v4 最终周期：{r["selected_period_d"]} 天；评分：{r["score"]}。</p>'
        review+='<p>零注入的参考周期为空；任何残留变化仍可能来自原星或模型误差。产品图中的通量已经被人工修改。</p><p><a href="index.html">SAP/PDCSAP 详细比较</a> · <a href="adjudication.json">v4 判据</a></p>'
        (OUT/'evaluation'/r['id']/'review.html').write_text(page(r['id'],review))
        body+=f'<tr><td><a href="{escape(r["id"])}/review.html">{escape(r["id"])}</a></td><td>{r["selected_period_d"]}</td><td>{r["score"]}</td></tr>'
    body+='</table><p>注入发生在 SAP/PDCSAP 已处理通量上，不检验上游像素提取、PDC 校正或来源定位。数据不能支持总体准确率、误报率、发现概率或 VSX 投稿。<a href="results.json">完整评分</a> · <a href="predictions.json">评分前预测</a> · <a href="../protocol.json">冻结方案</a></p>'
    (OUT/'evaluation/index.html').write_text(page('实测残差注入',body))
    print(result['injected_counts']);print(summary)

if __name__=='__main__':main()
