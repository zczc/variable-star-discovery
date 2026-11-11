"""Post-score diagnostics: noise, binning losses, and predeclared failure examples.

Reference periods are used only to display known injections after prediction.
No diagnostic result changes the saved prediction or its score.
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
from vstar.photometry import read_lightcurve,bin_lightcurve,LightCurve
from vstar.screening import detrend
from standard_injection import signal
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/standard-injection-v01'


def main():
    result=read_json(BASE/'evaluation/results.json');protocol=read_json(BASE/'protocol.json')
    manifest=read_json(BASE/'input-manifest.json');cases={c['id']:c for c in manifest['cases']}
    backgrounds=[]
    for base in protocol['bases']:
        for item in base['inputs']:
            for product in ['SAP','PDCSAP']:
                raw=read_lightcurve(ROOT/item['path'],product+'_FLUX');binned=bin_lightcurve(raw,10);clean,_=detrend(binned)
                backgrounds.append({'id':base['id'],'sector':item['sector'],'product':product,'tessmag':raw.metadata['TESSMAG'],
                    'points_after_bin':len(clean.time),'span_d':float(np.ptp(clean.time)),
                    'detrended_rms_fraction':float(np.std(clean.flux)),
                    'median_formal_error_fraction':float(np.median(clean.error))})
    losses=[]
    for case in manifest['cases']:
        if case['signal']['shape']=='zero':continue
        for item in case['inputs']:
            for product in ['SAP','PDCSAP']:
                raw=read_lightcurve(ROOT/item['source']['path'],product+'_FLUX')
                delta=signal(raw.time,case['signal'],case['origin_btjd'],item['construction']['time_window_d'])
                binned=bin_lightcurve(LightCurve(raw.time,delta,raw.error,{}),10)
                losses.append({'id':case['id'],'sector':item['sector'],'product':product,
                    'profile':case['signal']['profile'],'period_d':case['signal']['period_d'],
                    'sampled_and_binned_range_fraction':float(np.ptp(binned.flux)),
                    'retained_peak_range_ratio':float(np.ptp(binned.flux)/case['signal']['amplitude_fraction'])})
    examples=[]
    # Deterministic post-score choice: first maximum-amplitude narrow-eclipse failure per star.
    for base in protocol['bases']:
        eligible=sorted([r for r in result['rows'] if r['base_id']==base['id'] and r['profile']=='narrow-eclipses'
                         and r['amplitude_fraction']==.03 and r['score'] not in ('correct_period','analysis_failed')],key=lambda r:r['id'])
        if not eligible:continue
        selected=eligible[0];case=cases[selected['id']]
        fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
        for j,item in enumerate(case['inputs']):
            for i,product in enumerate(['SAP','PDCSAP']):
                raw=read_lightcurve(ROOT/item['path'],product+'_FLUX');clean,_=detrend(bin_lightcurve(raw,10))
                ph=((clean.time-case['origin_btjd'])/case['signal']['period_d']+case['signal']['phase'])%1
                ax=axes[j,i];ax.plot(ph,clean.flux*100,'.',ms=2,alpha=.5)
                dense=np.linspace(0,1,2001);spec=dict(case['signal'],phase=0)
                template=signal(dense*spec['period_d'],spec,0)
                # Shift only for display; not a fit and never enters the detector.
                template-=np.median(template)
                ax.plot(dense,template*100,'r-',lw=1,label='Injected shape (not fitted)')
                ax.set(title=f'{product} / Sector {item["sector"]}',xlabel='Known injected phase (post-score only)',ylabel='Detrended relative flux (%)')
                ax.legend(loc='lower right',fontsize=8)
        fig.suptitle(selected['id']+'\nFrozen v4: '+selected['score'])
        plot=selected['id']+'-known-phase.png';fig.savefig(BASE/'evaluation'/plot,dpi=140);plt.close(fig)
        products=read_json(BASE/'evaluation'/selected['id']/'case.json')
        decision=read_json(BASE/'evaluation'/selected['id']/'adjudication.json')
        candidates=[]
        for obs in products['observations']:
            for product in ['SAP','PDCSAP']:
                detection=obs['products'][product]['result']
                nearest=min(detection['candidates'],key=lambda c:abs(c['period_d']/case['signal']['period_d']-1))
                candidates.append({'sector':obs['sector'],'product':product,'selected_period_d':detection['selected_period_d'],
                                   'period_status':detection['period_status'],'nearest_injected_period_candidate':nearest})
        checks=[{'sector':e['sector'],'passed':e['passed'],'adjacent_pairs':e.get('half_cycle',{}).get('count'),
                 'primary_same_family_pairs':e.get('primary_same_family',{}).get('count'),
                 'secondary_same_family_pairs':e.get('secondary_same_family',{}).get('count')} for e in decision['event_checks']]
        examples.append({'id':selected['id'],'score':selected['score'],'plot':plot,
                         'truth_supported_products_all_epochs':selected['truth_supported_products_all_epochs'],
                         'candidates':candidates,'event_checks':checks})
    summary=[]
    for profile in ['sine','broad-eclipses','narrow-eclipses']:
        for period in [.731,2.413]:
            values=[r['retained_peak_range_ratio'] for r in losses if r['profile']==profile and r['period_d']==period]
            summary.append({'profile':profile,'period_d':period,'min_retained_range':min(values),'max_retained_range':max(values),
                            'eclipse_duration_minutes':None if profile=='sine' else period*(.08 if profile=='broad-eclipses' else .02)*1440})
    write_json(BASE/'evaluation/diagnostics.json',{'created_at':now(),'scored_results_sha256':sha256(BASE/'evaluation/results.json'),
        'backgrounds':backgrounds,'sampling_summary':summary,'sampling_losses':losses,'examples':examples,
        'example_selection':'Lexicographically first maximum-amplitude narrow-eclipse non-recovery per star, after scoring; no rerun or threshold change.',
        'detrending':'Existing quadratic + gap-offset diagnostic; not a calibrated noise or significance model.'})
    body='<h1>窄食为什么没有选出最终周期</h1><p>在全量预测与评分保存后，每颗星选取编号最靠前的 3% 窄食失败案例。图按已知注入周期折叠；红线是加入的信号。此图帮助检查失败，不证明程序能够盲找出周期，也不改变评分。</p>'
    body+='<p>G 191-B2B 的例子：PDCSAP 两段选对；SAP 后一段偏向三倍周期。补充的同类极小比较对数不足，最终弃选。GD 71、GD 153 的例子：真值附近周期已经进入搜索结果，但多数时段的预测改善低于固定的 20% 门槛。这个门槛是开发规则，不是显著性概率。</p>'
    for example in examples:
        body+=f'<h2>{example["id"]}</h2><img src="{example["plot"]}" alt="按已知注入周期展示的窄食失败案例"><table><tr><th>时段 / 产品</th><th>最接近注入值的周期 / 天</th><th>预测改善</th><th>合格</th><th>该产品最终周期</th></tr>'
        for c in example['candidates']:
            near=c['nearest_injected_period_candidate']
            body+=f'<tr><td>{c["sector"]} / {c["product"]}</td><td>{near["period_d"]:.7f}</td><td>{near["gain"]:.1%}</td><td>{near["qualifies"]}</td><td>{c["selected_period_d"]}</td></tr>'
        body+='</table>'
    body+='<h2>采样与分箱后的信号深度</h2><table><tr><th>形状</th><th>周期 / 天</th><th>保留峰谷差</th></tr>'
    for item in summary:body+=f'<tr><td>{item["profile"]}</td><td>{item["period_d"]}</td><td>{item["min_retained_range"]:.1%}–{item["max_retained_range"]:.1%}</td></tr>'
    body+='</table><p>以上只计算加入信号经过采样窗口平均和 10 分钟分箱后，实际采到的最大峰谷差；未叠加噪声，也不是每一次食的深度下限。</p><p><a href="index.html">全部结果</a> · <a href="diagnostics.json">诊断数据</a></p>'
    (BASE/'evaluation/diagnostics.html').write_text(page('窄食诊断',body))
    print('Diagnostic examples' ,[e['id'] for e in examples]);print(summary)

if __name__=='__main__':main()
