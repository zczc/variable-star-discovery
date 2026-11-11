"""Read-only aggregation of preserved predictions; no automatic truth assignment."""
from pathlib import Path
from collections import Counter
from html import escape
import argparse,csv,json
import numpy as np
from vstar.io import read_json,write_json,now,sha256
from vstar.reports import page
from scale_validation_support import period_relation
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'repo/benchmarks/scale-validation-v01'
GROUPS={'catalog_eb':'目录食双星','neighbor_risk':'邻星风险对象','field_unlabelled':'未标注普通目标'}
RELATIONS={'catalog_period_match':'与目录周期一致','half_catalog_period':'约为目录一半','double_catalog_period':'约为目录两倍','other_period':'与目录不同','no_reference':'暂无参考周期','abstained':'未选定周期','pending':'尚未分析'}
RUNLABEL={'completed':'分析完成','pending':'等待分析','unavailable':'数据不可用','failed':'分析失败'}
ROUTES={'not_reviewed':'尚未复核','manual_target_review':'目标位置获支持，待人工复核','period_review_required':'周期待查','instrument_review_required':'仪器复核','source_evidence_required':'来源证据不足','exclude_signal_from_target':'信号不归属目标','analysis_failed':'来源分析失败'}

def main():
    targets=read_json(OUT/'targets.json');rows=[];groups={g:Counter() for g in GROUPS};times=[]
    body='<h1>1,000 颗真实目标的验证</h1><p>规则和名单先固定，再取得光变。保留失败、弃选和未完成项；没有自动确认新发现。</p>'
    body+='<p>本轮先完成千星光变，再按固定规则抽取 100 个选中或高风险对象深入复核来源。其余待查，已开始的额外复核保留。</p>'
    body+='<div class="notice">400 个目录食双星、50 个邻星风险对象、550 个未标注普通目标。风险组不等于已确认污染，普通组不等于不变星。下列来源结果是同一算法的审查输出，尚未经逐例独立裁定，因此不报告总体精确率。</div>'
    table=[]
    for c in targets['cases']:
        ident=c['id'];file=OUT/'evaluation'/(ident+'-prediction.json');p=read_json(file) if file.exists() else {}
        sfile=OUT/'source-results'/(ident+'.json');s=read_json(sfile) if sfile.exists() else None
        selected=p.get('decision',{}).get('selected_period_d');reference=float(c['reference'][0]['period']) if c['reference'] else None
        relation=period_relation(selected,reference) if p else 'pending'
        source=(s or {}).get('source_review') or p.get('preliminary_source',{})
        route=source.get('conclusion',{}).get('route','not_reviewed')
        status=p.get('status','pending');g=groups[c['group']];g['selected_inputs']+=1;g[status]+=1
        if selected is not None:g['period_selected']+=1
        if c['group']=='catalog_eb' and p:g[relation]+=1
        if s and s['status'] in {'completed','incomplete'}:g['source_attempted']+=1;g['source_'+s['status']]+=1
        if p:g['route_'+route]+=1
        if p.get('elapsed_seconds'):times.append(p['elapsed_seconds'])
        row={'id':ident,'tic':c['tic'],'group':c['group'],'status':status,'selected_period_d':selected,'catalog_orbital_period_d':reference,'period_relation':relation,'source_route':route,'pixel_review_status':s['status'] if s else 'pending','independent_verdict':'not_completed','confirmed_variable':False,'submission_ready':False}
        rows.append(row)
        entry=f'<h1>TIC {c["tic"]}</h1><p>组别：{GROUPS[c["group"]]}；分析状态：{RUNLABEL.get(status,status)}。</p><p>选定光度周期：{selected} 天；目录轨道周期：{reference} 天；比较：{RELATIONS.get(relation,relation)}。</p><p>来源处理：{ROUTES.get(route,route)}。目录组也需要独立来源核验。</p>'
        folder=OUT/'evaluation'/ident
        if p:
            entry+='<p><a href="../'+ident+'-prediction.json">保存的周期预测</a></p>'
            if (folder/'period/index.html').exists():entry+='<p><a href="period/index.html">两产品光变和周期图</a></p>'
        if s and (folder/'source/source-review.json').exists():
            entry+='<p><a href="source/source-review.json">完整来源判据</a> · <a href="source/source-manifest.json">来源复现输入</a></p>'
            for obs in source.get('observations',[]):
                if obs.get('pixels'):entry+=f'<img src="source/{escape(obs["pixels"]["plot"])}" alt="周期信号位置图">'
        followup=OUT/'reference-followup'/(ident+'-comparison.json')
        if followup.exists():entry+='<p><a href="../../reference-followup/'+ident+'-comparison.json">另查 VSX 的周期对照</a></p>'
        figure=OUT/'reference-followup'/(ident+'-periods.png')
        if figure.exists():entry+='<img src="../../reference-followup/'+ident+'-periods.png" alt="按选定周期和目录周期折叠">'
        entry+='<p>目录邻星信息只覆盖 TESS-EBs v1.0。位置相符不排除未分辨近邻；目录周期的半/双倍关系需人工辨别。尚未完成独立裁定，也未查首次发现资格。</p><p><a href="../../index.html">返回总览</a></p>'
        # Pending directories must not be created: the runner treats partial dirs as errors.
        if p:
            folder.mkdir(parents=True,exist_ok=True);(folder/'index.html').write_text(page(ident,entry))
        cell=f'<a href="evaluation/{ident}/index.html">{c["tic"]}</a>' if p else c['tic']
        table.append(f'<tr><td>{cell}</td><td>{GROUPS[c["group"]]}</td><td>{RUNLABEL.get(status,status)}</td><td>{selected:.7f}</td><td>{RELATIONS.get(relation,relation)}</td><td>{ROUTES.get(route,route)}</td></tr>' if selected is not None else f'<tr><td>{cell}</td><td>{GROUPS[c["group"]]}</td><td>{RUNLABEL.get(status,status)}</td><td>—</td><td>{RELATIONS.get(relation,relation)}</td><td>{ROUTES.get(route,route)}</td></tr>')
    summary={'updated_at':now(),'targets':len(rows),'groups':{g:dict(v) for g,v in groups.items()},'total_status':dict(Counter(r['status'] for r in rows)),'selected_periods':sum(r['selected_period_d'] is not None for r in rows),'independently_adjudicated_targets':0,'population_precision_validated':False,'median_analysis_seconds':float(np.median(times)) if times else None,'targets_sha256':sha256(OUT/'targets.json'),'rows':rows}
    write_json(OUT/'summary.json',summary)
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    body+='<p>更新时间：'+summary['updated_at']+'</p><table><tr><th>组别</th><th>输入</th><th>分析完成</th><th>不可用/失败</th><th>尚未完成</th><th>选出周期</th><th>追加来源审查</th></tr>'
    for g,counts in groups.items():body+=f'<tr><td>{GROUPS[g]}</td><td>{counts["selected_inputs"]}</td><td>{counts["completed"]}</td><td>{counts["unavailable"]+counts["failed"]}</td><td>{counts["pending"]}</td><td>{counts["period_selected"]}</td><td>{counts["source_attempted"]}</td></tr>'
    body+='</table><p>这里的“分析完成”只表示程序成功运行。科学结论分列显示，不等同于验证通过。半/双目录周期单独列出，尚未直接记成正确或错误。</p><p><a href="summary.json">汇总 JSON</a> · <a href="summary.csv">CSV</a> · <a href="README.md">预定方案</a> · <a href="targets.json">冻结名单</a></p><input id="filter" placeholder="筛选 TIC、状态或组别"><table id="results"><thead><tr><th>TIC</th><th>组别</th><th>运行</th><th>选定周期（天）</th><th>目录周期比较</th><th>来源处理</th></tr></thead><tbody>'+''.join(table)+'</tbody></table><script>document.getElementById("filter").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#results tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script>'
    (OUT/'index.html').write_text(page('千星实测验证',body))
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
