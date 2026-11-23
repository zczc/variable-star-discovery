"""Summarize the saved component follow-up without rerunning detection."""
import csv,io,json
from html import escape
from followup_hd43737 import ROOT,OUT,parse_tap
from vstar.io import read_json,write_json,sha256
from vstar.reports import page
from triage_discovery_candidates import vsx_objects
from search_discovery_batch import parse_tsv


def build():
    case=read_json(OUT/'combined-four-sectors.json');decision=read_json(OUT/'combined-adjudication.json')
    plan=read_json(OUT/'plan.json')
    for r in plan['inputs']:assert sha256(ROOT/r['path'])==r['sha256'],r['path']
    sectors=[]
    for obs in sorted(case['observations'],key=lambda x:x['sector']):
        row={'sector':obs['sector']}
        for name,p in obs['products'].items():row[name]={k:p['result'][k] for k in ['periodic_detected','photometric_period_d','selected_period_d','period_status']}
        sectors.append(row)
    table_results=[]
    for i,control in [(1,'99990178'),(2,'99921371'),(3,'99920728')]:
        receipt=read_json(OUT/'sources'/f'fetherolf-table{i}.json')
        rows=parse_tsv(receipt);assert control in {r['TIC'] for r in rows}
        table_results.append({'table':i,'positive_control_returned':control,'target_rows':[r for r in rows if r['TIC'] in ['393386173','393386168']]})
    query=read_json(OUT/'sources/vsx-cone.json');assert query['status_code']==200
    vsx=vsx_objects(json.loads(query['body']))
    aliases=parse_tap('simbad-aliases');refs=parse_tap('simbad-references')
    summary={'date':'2026-11-23','tic_A':'393386173','tic_B':'393386168','component_aliases':aliases,
             'simbad_reference_associations':refs,'reference_count_unique':len({r['bibcode'] for r in refs}),
             'references_scope':'Read the returned titles and available abstracts. No full-text search of every paper. Generic spectral/astrometric records do not alone establish previous variability.',
             'vsx_objects':vsx,'fetherolf_tables':table_results,'sectors':sectors,
             'new_sectors':[7,32],'old_sectors':[6,33],
             'combined_decision':{k:decision[k] for k in ['status','selected_period_d','source_status']},
             'raw_frequency_diagnostic':'Strongest peak near 0.05125 d in all four epochs/both products; secondary peaks near 0.04871 and 0.05438 d. Peaks not independently assigned physical modes or components.',
             'route':'deferred_close_binary_source_and_period_unresolved','source_confirmed':False,
             'novelty_confirmed':False,'submission_ready':False,'original_results_overwritten':False}
    write_json(OUT/'summary.json',summary)
    body='<h1>HD 43737A/B：四段观测复核</h1><p>双星混合光中有重复变化，仍不能确定变光分量；原规则合并周期未决。</p>'
    body+='<p>A：TIC 393386173；B：TIC 393386168；间距约 6.17 角秒，G 星等相差约 0.08。来源确认、新颖性确认和可提交状态均为 false。</p>'
    body+='<table><tr><th>观测区</th><th>SAP 选定周期／天</th><th>PDCSAP 选定周期／天</th></tr>'
    for row in sectors:body+=f'<tr><td>S{row["sector"]}</td><td>{row["SAP"]["selected_period_d"]:.8f}</td><td>{row["PDCSAP"]["selected_period_d"]:.8f}</td></tr>'
    body+='</table><p>S32 的 PDCSAP 选出两倍周期；合并后 SAP 保留约 0.05125 天，PDCSAP 有跨时段谐波冲突，最终裁定 unresolved。任何人工偏好都未替换这一结果。</p>'
    body+='<h2>新增两段光变</h2><img src="additional-periods/s0007-products.png" alt="S7 双产品光变及相位图"><img src="additional-periods/s0032-products.png" alt="S32 双产品周期冲突">'
    body+='<h2>原始采样的宽频率诊断</h2><p>为检查原 0.05 天下限附近的信号，单独搜索 0.01–8 天，未额外分箱、去趋势或筛点。这是事后诊断，不改变冻结检测器。附近多个峰在各段出现，不等于已排除所有采样别名或完成脉动分类。</p><img src="wide-frequency/periodograms.png" alt="四段原始采样周期图">'
    body+='<p>VSX 本次 144 角秒范围有效返回零条；Fetherolf 三表对 A、B 均无匹配，各表正例均检出。SIMBAD 返回的光谱、测光校准和年轻星空间分布资料未构成当前已确认的先前变光报告。Crossref 关键词搜索仅返回无关结果；VizieR 全目录请求未完成；这些都不证明新颖性。</p>'
    body+='<p><a href="summary.json">完整结论与身份</a> · <a href="wide-frequency/summary.json">宽频率数值</a> · <a href="combined-adjudication.json">原合并裁定</a> · <a href="../discovery-batch-2026-11-23/index.html">新一批对象结果</a></p>'
    (OUT/'index.html').write_text(page('HD 43737A/B 复核',body))
    write_json(OUT/'visual-notes.json',{'date':'2026-11-23','viewed':['additional-periods/s0007-products.png','additional-periods/s0032-products.png','wide-frequency/periodograms.png'],
        'notes':['S7 has a weak smooth fold in both products and a mid-sector gap; PDCSAP scatter/amplitude differs from SAP.',
                 'S32 has a SAP offset around its central gap; PDCSAP chooses twice the SAP period. No clear eclipse-like minima established.',
                 'Broad-frequency spectra have several repeatable peaks near and above the former 20/day limit; dominant peak remains near 19.51/day. No source separation or calibrated mode claim.'],
        'threshold_changes':False})
    print('HD 43737 report built; source and final period unresolved')

if __name__=='__main__':build()
