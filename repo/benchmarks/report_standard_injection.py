"""Score complete saved predictions without rerunning or fitting any detector."""
from pathlib import Path
from collections import Counter
import csv
from html import escape
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
from report_empirical_injection import score_case
from run_standard_injection import verify_protocol
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/standard-injection-v01'
PROFILES=['sine','broad-eclipses','narrow-eclipses']
NAMES={'sine':'平滑起伏','broad-eclipses':'较宽的食（每谷占 8% 周期）','narrow-eclipses':'窄食（每谷占 2% 周期）'}
AMPS=[.001,.003,.01,.03]
PERIODS=[.731,2.413]


def summarize(rows):
    output=[]
    for profile in PROFILES:
        for period in PERIODS:
            for amp in AMPS:
                group=[r for r in rows if (r['profile'],r['reference_period_d'],r['amplitude_fraction'])==(profile,period,amp)]
                output.append({'profile':profile,'period_d':period,'amplitude_fraction':amp,'total':len(group),
                    'correct_final':sum(r['score']=='correct_period' for r in group),
                    'qualified_truth_candidates':sum(bool(r['truth_supported_products_all_epochs']) for r in group),
                    'counts':dict(Counter(r['score'] for r in group))})
    return output


def main():
    protocol=verify_protocol();out=BASE/'evaluation';path=out/'predictions.json';prediction=read_json(path)
    if not prediction['complete']:raise ValueError('Refuse to score partial predictions')
    assert prediction['manifest_sha256']==sha256(BASE/'input-manifest.json')
    manifest=read_json(BASE/'input-manifest.json');cases={c['id']:c for c in manifest['cases']}
    assert set(cases)=={r['id'] for r in prediction['results']} and len(cases)==len(prediction['results'])
    rows=[]
    for r in prediction['results']:
        case=cases[r['id']];score=score_case(r,case,protocol['period_tolerance'])
        score.update(profile=case['signal']['profile'],eclipse_width_phase=case['signal']['eclipse_width_phase'])
        rows.append(score)
    summary=summarize(rows);nonzero=[r for r in rows if r['profile']!='zero']
    result={'created_at':now(),'predictions_sha256':sha256(path),'report_script_sha256':sha256(Path(__file__)),
            'rows':rows,'summary':summary,'injected_counts':dict(Counter(r['score'] for r in nonzero)),
            'zero_injection':[r for r in rows if r['profile']=='zero'],'independent_background_stars':3,
            'repeated_signal_cases':sum(r['any_repeated_signal'] for r in nonzero),
            'qualified_truth_cases':sum(bool(r['truth_supported_products_all_epochs']) for r in nonzero),
            'validated_real_negative_denominator':0,'false_positive_rate':None,'confidence_interval':None,
            'note':'Repeated injections into three previously inspected backgrounds, not independent population samples.'}
    write_json(out/'results.json',result)
    with (out/'results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    grid=np.array([[s['correct_final'] for s in summary[i:i+4]] for i in range(0,len(summary),4)])
    totals=np.array([[s['total'] for s in summary[i:i+4]] for i in range(0,len(summary),4)])
    fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
    ax.imshow(grid/totals,cmap='YlGn',vmin=0,vmax=1,aspect='auto')
    for (y,x),value in np.ndenumerate(grid):ax.text(x,y,f'{value} / {totals[y,x]}',ha='center',va='center',color='white' if value>=5 else 'black',fontsize=12)
    names=[f'{profile} / {period} d' for profile in PROFILES for period in PERIODS]
    ax.set(xticks=range(4),xticklabels=['0.1%','0.3%','1%','3%'],yticks=range(6),yticklabels=names,
           xlabel='Injected instantaneous full amplitude / original median flux',title='Frozen v4: correct final period / 6 trials per cell')
    fig.savefig(out/'recovery-summary.png',dpi=150);plt.close(fig)
    categories=['correct_period','half_period','double_period','not_recovered','abstained','analysis_failed']
    labels=['OK','P/2','2P','Other','Abstain','Failed']
    for base in protocol['bases']:
        grid=[];names=[]
        for profile in PROFILES:
            for period in PERIODS:
                for phase in (.13,.57):
                    group=sorted([r for r in nonzero if (r['base_id'],r['profile'],r['reference_period_d'],r['phase'])==(base['id'],profile,period,phase)],key=lambda r:r['amplitude_fraction'])
                    assert len(group)==4
                    grid.append([categories.index(r['score']) for r in group]);names.append(f'{profile} / {period} d / phase {phase}')
        grid=np.array(grid);fig,ax=plt.subplots(figsize=(11,7),layout='constrained')
        ax.imshow(grid,cmap=ListedColormap(['#5cbb95','#e8b766','#d5a464','#e48378','#d4d9e0','#985c9c']),vmin=0,vmax=5,aspect='auto')
        for (y,x),value in np.ndenumerate(grid):ax.text(x,y,labels[value],ha='center',va='center',fontsize=10)
        ax.set(xticks=range(4),xticklabels=['0.1%','0.3%','1%','3%'],yticks=range(12),yticklabels=names,
               xlabel='Injected full amplitude',title=base['name']+' | final period recovery; same measured background reused')
        fig.savefig(out/(base['id']+'-recovery.png'),dpi=130);plt.close(fig)
    body='<h1>标准星原始测光的注入验证</h1><p>三颗标准星，各两个实测时段；直接加入信号，保留原有起伏。144 个非零注入、3 个零注入。检测规则冻结；所有预测保存后才评分。</p>'
    body+='<p>每格 6 次试验：3 颗背景星，各两个初始相位。数字是最终选对周期的次数，不能解释为总体识别准确率。幅度指最亮与最暗的全差；采样与分箱会降低窄食的实际测得深度。</p><img src="recovery-summary.png" alt="按周期、形状、幅度分组的正确周期数量">'
    body+='<p><a href="diagnostics.html">查看三个未选出周期的窄食案例和采样损失</a></p>'
    body+='<p>平滑起伏：sine；较宽的食：broad-eclipses；窄食：narrow-eclipses。每个谷分别占一个周期的 8% 或 2%。</p><table><tr><th>形状</th><th>周期 / 天</th><th>全幅度</th><th>最终选对</th><th>两时段有正确候选</th></tr>'
    for s in summary:body+=f'<tr><td>{NAMES[s["profile"]]}</td><td>{s["period_d"]}</td><td>{s["amplitude_fraction"]:.1%}</td><td>{s["correct_final"]}/{s["total"]}</td><td>{s["qualified_truth_candidates"]}/{s["total"]}</td></tr>'
    body+='</table><p>“正确候选”要求同一种产品在两时段都出现真值附近的合格候选；有其他竞争周期时可能无法最终选择。</p><h2>未注入信号的对照</h2><ul>'
    for r in result['zero_injection']:body+=f'<li>{r["base_id"]}：有跨时段重复信号 {r["any_repeated_signal"]}；最终周期 {r["selected_period_d"]} 天。</li>'
    body+='</ul><p>三颗星的外部稳定性证据有波段、精度与时间覆盖限制，不计入正式 TESS 安静星分母，不据此报告误报率。</p>'
    for base in protocol['bases']:body+=f'<h2>{base["name"]}</h2><img src="{base["id"]}-recovery.png" alt="{base["name"]} 每个注入案例的最终周期判断">'
    body+='<p>OK：选对；Abstain：未选择；P/2、2P：选到半周期或两倍周期；Other：其他周期；Failed：运行失败。未选择不等于原星不变。</p>'
    body+='<h2>逐项查看</h2><label>筛选案例 <input type="search" oninput="for(const r of document.querySelectorAll(\'#cases tbody tr\'))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())" placeholder="星名、形状、周期或结果"></label><table id="cases"><thead><tr><th>案例</th><th>最终周期</th><th>判定</th></tr></thead><tbody>'
    for r in rows:
        folder=out/r['id'];folder.mkdir(exist_ok=True)
        review=f'<h1>{escape(r["id"])}</h1><p>人工注入案例，不是这颗恒星真实变化或新发现的证据。</p><p>注入周期：{r["reference_period_d"]} 天；最终周期：{r["selected_period_d"]} 天；评分：{r["score"]}。</p>'
        if r['status']=='completed':review+='<p><a href="index.html">产品光变与竞争周期</a> · <a href="adjudication.json">第四版判断依据</a></p>'
        else:review+='<p>执行失败，保留在完整预测中。</p>'
        review+='<p>产品图里的通量已经加入人工信号；两产品来自同一批观测，不算两次独立观测。</p>'
        (folder/'review.html').write_text(page(r['id'],review))
        body+=f'<tr><td><a href="{r["id"]}/review.html">{r["id"]}</a></td><td>{r["selected_period_d"]}</td><td>{r["score"]}</td></tr>'
    body+='</tbody></table><p>这是已处理测光上的恢复试验，没有重新运行像素提取、PDC 或源定位。<a href="results.json">完整评分</a> · <a href="predictions.json">评分前预测</a> · <a href="../protocol.json">冻结方案</a> · <a href="../input-manifest.json">输入与重建信息</a></p>'
    (out/'index.html').write_text(page('标准星注入验证',body))
    print(result['injected_counts'],flush=True)
    print(summary,flush=True)

if __name__=='__main__':main()
