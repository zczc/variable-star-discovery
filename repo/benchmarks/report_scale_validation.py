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
RELATIONS={'not_evaluable':'未能评估周期','catalog_period_match':'与目录周期一致','half_catalog_period':'约为目录一半','double_catalog_period':'约为目录两倍','other_period':'与目录不同','no_reference':'暂无参考周期','abstained':'未选定周期','pending':'尚未分析'}
RUNLABEL={'completed':'分析完成','pending':'等待分析','unavailable':'数据不可用','failed':'分析失败'}
ROUTES={'not_reviewed':'尚未复核','manual_target_review':'目标位置获支持，待人工复核','period_review_required':'周期待查','instrument_review_required':'仪器复核','source_evidence_required':'来源证据不足','exclude_signal_from_target':'信号不归属目标','analysis_failed':'来源分析未完成，见原因'}

def main():
    targets=read_json(OUT/'targets.json');rows=[];groups={g:Counter() for g in GROUPS};times=[]
    body='<h1>1,000 颗真实目标的验证</h1><p>规则和名单先固定，再取得光变。保留失败、弃选和未完成项；没有自动确认新发现。</p>'
    full_cohort=(OUT/'source-all.json').exists()
    body+='<p>千星光变完成后，按用户回复对全部选出周期的对象及全部高风险对象复核来源，覆盖 349 个目标。此前提出的 100 个抽样限额已取消。</p>' if full_cohort else '<p>本轮先完成千星光变，再固定来源复核名单。</p>'
    body+='<div class="notice">400 个目录食双星、50 个邻星风险对象、550 个未标注普通目标。风险组不等于已确认污染，普通组不等于不变星。下列来源结果是同一算法的审查输出，尚未经逐例独立裁定，因此不报告总体精确率。</div>'
    table=[]
    for c in targets['cases']:
        ident=c['id'];file=OUT/'evaluation'/(ident+'-prediction.json');p=read_json(file) if file.exists() else {}
        sfile=OUT/'source-results'/(ident+'.json');s=read_json(sfile) if sfile.exists() else None
        selected=p.get('decision',{}).get('selected_period_d');reference=float(c['reference'][0]['period']) if c['reference'] else None
        relation=(period_relation(selected,reference) if p.get('status')=='completed' else 'not_evaluable') if p else 'pending'
        source=(s or {}).get('source_review') or p.get('preliminary_source',{})
        route=source.get('conclusion',{}).get('route','not_reviewed')
        status=p.get('status','pending');g=groups[c['group']];g['selected_inputs']+=1;g[status]+=1
        if selected is not None:g['period_selected']+=1
        if c['group']=='catalog_eb' and p:g[relation]+=1
        if s and s['status'] in {'completed','incomplete','transport_failed'}:g['source_attempted']+=1;g['source_'+s['status']]+=1
        if p:g['route_'+route]+=1
        if p.get('elapsed_seconds'):times.append(p['elapsed_seconds'])
        row={'id':ident,'tic':c['tic'],'group':c['group'],'status':status,'selected_period_d':selected,'catalog_orbital_period_d':reference,'period_relation':relation,'source_route':route,'pixel_review_status':s['status'] if s else 'pending','independent_verdict':'not_completed','confirmed_variable':False,'submission_ready':False}
        rows.append(row)
        entry=f'<h1>TIC {c["tic"]}</h1><p>组别：{GROUPS[c["group"]]}；分析状态：{RUNLABEL.get(status,status)}。</p><p>选定光度周期：{selected} 天；目录轨道周期：{reference} 天；比较：{RELATIONS.get(relation,relation)}。</p><p>来源处理：{ROUTES.get(route,route)}。目录组也需要独立来源核验。</p>'
        folder=OUT/'evaluation'/ident
        if p:
            entry+='<p><a href="../'+ident+'-prediction.json">保存的周期预测</a></p>'
            if (folder/'period/index.html').exists():entry+='<p><a href="period/index.html">两产品光变和周期图</a></p>'
        if s:entry+='<p><a href="../../source-results/'+ident+'.json">来源任务状态及获取问题</a></p>'
        if s and s.get('source_review',{}).get('errors'):
            entry+='<p>未完成原因：'+escape('; '.join(e['error'] for e in s['source_review']['errors']))+'</p>'
        if s and (folder/'source/source-review.json').exists():
            entry+='<p><a href="source/source-review.json">完整来源判据</a> · <a href="source/source-manifest.json">来源复现输入</a></p>'
            for obs in source.get('observations',[]):
                if obs.get('pixels'):entry+=f'<img src="source/{escape(obs["pixels"]["plot"])}" alt="周期信号位置图">'
        followup=OUT/'reference-followup'/(ident+'-comparison.json')
        if followup.exists():entry+='<p><a href="../../reference-followup/'+ident+'-comparison.json">另查 VSX 的周期对照</a></p>'
        manual=OUT/'reference-followup'/(ident+'-manual-review.json')
        if manual.exists():entry+='<p><a href="../../reference-followup/'+ident+'-manual-review.json">人工看图备注及未解决的问题</a></p>'
        figure=OUT/'reference-followup'/(ident+'-periods.png')
        if figure.exists():entry+='<img src="../../reference-followup/'+ident+'-periods.png" alt="按选定周期和目录周期折叠">'
        entry+='<p>目录邻星信息只覆盖 TESS-EBs v1.0。位置相符不排除未分辨近邻；目录周期的半/双倍关系需人工辨别。尚未完成独立裁定，也未查首次发现资格。</p><p><a href="../../index.html">返回总览</a></p>'
        # Pending directories must not be created: the runner treats partial dirs as errors.
        if p:
            folder.mkdir(parents=True,exist_ok=True);(folder/'index.html').write_text(page(ident,entry))
        cell=f'<a href="evaluation/{ident}/index.html">{c["tic"]}</a>' if p else c['tic']
        table.append(f'<tr><td>{cell}</td><td>{GROUPS[c["group"]]}</td><td>{RUNLABEL.get(status,status)}</td><td>{selected:.7f}</td><td>{RELATIONS.get(relation,relation)}</td><td>{ROUTES.get(route,route)}</td></tr>' if selected is not None else f'<tr><td>{cell}</td><td>{GROUPS[c["group"]]}</td><td>{RUNLABEL.get(status,status)}</td><td>—</td><td>{RELATIONS.get(relation,relation)}</td><td>{ROUTES.get(route,route)}</td></tr>')
    summary={'updated_at':now(),'targets':len(rows),'groups':{g:dict(v) for g,v in groups.items()},'total_status':dict(Counter(r['status'] for r in rows)),'selected_periods':sum(r['selected_period_d'] is not None for r in rows),'independently_adjudicated_targets':0,'population_precision_validated':False,'median_analysis_seconds':float(np.median(times)) if times else None,'targets_sha256':sha256(OUT/'targets.json'),'rows':rows}
    sample_path=OUT/('source-all.json' if full_cohort else 'source-sample.json')
    if sample_path.exists():
        sample=read_json(sample_path);sample_ids={c['id'] for c in sample['cases']}
        selected_rows=[r for r in rows if r['id'] in sample_ids]
        strata={}
        for group in GROUPS:
            subset=[r for r in selected_rows if r['group']==group]
            strata[group]={'requested':len(subset),'period_selected':sum(r['selected_period_d'] is not None for r in subset),'states':dict(Counter(r['pixel_review_status'] for r in subset)),'routes':dict(Counter(r['source_route'] for r in subset))}
        summary['source_cohort']={'scope':'all_selected_and_all_risk' if full_cohort else 'fixed_sample','requested':len(sample_ids),'groups':dict(Counter(r['group'] for r in selected_rows)),'states':dict(Counter(r['pixel_review_status'] for r in selected_rows)),'routes':dict(Counter(r['source_route'] for r in selected_rows)),'strata':strata,'additional_source_cases':[r['id'] for r in rows if r['id'] not in sample_ids and r['pixel_review_status'] in {'completed','incomplete','transport_failed'}]}
        returned=[r for r in selected_rows if r['pixel_review_status'] in {'completed','incomplete','transport_failed'}]
        summary['source_cohort']['returned_routes_by_period_usage']={
            'selected_by_detector':dict(Counter(r['source_route'] for r in returned if r['selected_period_d'] is not None)),
            'neighbor_period_diagnostic_only':dict(Counter(r['source_route'] for r in returned if r['selected_period_d'] is None))}
        issues=Counter()
        for ident in sample_ids:
            path=OUT/'source-results'/(ident+'.json')
            if not path.exists():continue
            saved=read_json(path);errors=saved.get('source_review',{}).get('errors',[])
            if any('Insufficient pixel segment cycles:' in e['error'] for e in errors):issues['insufficient_pixel_segment_cycles']+=1
            if any('Insufficient pixel segment cycles:' not in e['error'] for e in errors):issues['other_source_analysis_errors']+=1
            if saved.get('acquisition_errors'):issues['acquisition_errors']+=1
        summary['source_cohort']['incomplete_reasons_nonexclusive']=dict(issues)
    prefetched=[read_json(p) for p in (OUT/'prefetch-results').glob('*.json')]
    summary['pixel_prefetch']={'records':len(prefetched),'fully_cached_cases':sum(all(x['status']=='cached' for x in r['products']) for r in prefetched),'source_flux_analyzed_by_prefetch':False}
    write_json(OUT/'summary.json',summary)
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    body+='<p>更新时间：'+summary['updated_at']+'</p><table><tr><th>组别</th><th>输入</th><th>分析完成</th><th>不可用/失败</th><th>尚未完成</th><th>选出周期</th><th>追加来源审查</th></tr>'
    for g,counts in groups.items():body+=f'<tr><td>{GROUPS[g]}</td><td>{counts["selected_inputs"]}</td><td>{counts["completed"]}</td><td>{counts["unavailable"]+counts["failed"]}</td><td>{counts["pending"]}</td><td>{counts["period_selected"]}</td><td>{counts["source_attempted"]}</td></tr>'
    body+='</table>'
    if summary.get('source_cohort'):
        body+=f'<h2>固定的 {summary["source_cohort"]["requested"]} 个来源复核对象</h2><p>风险组未选出周期的对象使用邻星目录周期作位置诊断，不能记作程序检出。<a href="{sample_path.name}">冻结名单和全部周期预测校验值</a>。</p><table><tr><th>组别</th><th>复核对象</th><th>程序选出周期</th><th>来源运行完成</th><th>证据不完整</th><th>下载失败</th><th>尚待完成</th></tr>'
        for group,stats in summary['source_cohort']['strata'].items():
            states=stats['states'];done=sum(states.get(k,0) for k in ['completed','incomplete','transport_failed'])
            body+=f'<tr><td>{GROUPS[group]}</td><td>{stats["requested"]}</td><td>{stats["period_selected"]}</td><td>{states.get("completed",0)}</td><td>{states.get("incomplete",0)}</td><td>{states.get("transport_failed",0)}</td><td>{stats["requested"]-done}</td></tr>'
        body+='</table><p>运行完成仍只表示程序产生了结果。来源去向：</p><ul>'
        for route,count in summary['source_cohort']['routes'].items():body+='<li>'+escape(ROUTES.get(route,route))+f'：{count}</li>'
        body+='</ul><p>名单以外另有 '+str(len(summary['source_cohort']['additional_source_cases']))+' 个已启动的来源案例，分别保留。</p>'
        coverage=summary['source_cohort']['incomplete_reasons_nonexclusive'].get('insufficient_pixel_segment_cycles',0)
        body+=f'<p>其中 {coverage} 个对象因每半段覆盖不足三次周期而不能完成像素来源复核。这是证据覆盖不足，不表示确认了污染。</p>'
    body+='<p>像素预取已保存 '+str(summary['pixel_prefetch']['fully_cached_cases'])+' 组完整文件。预取不产生来源结论。</p>'
    body+='<p>这里的“分析完成”只表示程序成功运行。科学结论分列显示，不等同于验证通过。半/双目录周期单独列出，尚未直接记成正确或错误。</p><p><a href="summary.json">汇总 JSON</a> · <a href="summary.csv">CSV</a> · <a href="README.md">预定方案</a> · <a href="targets.json">冻结名单</a></p><input id="filter" placeholder="筛选 TIC、状态或组别"><table id="results"><thead><tr><th>TIC</th><th>组别</th><th>运行</th><th>选定周期（天）</th><th>目录周期比较</th><th>来源处理</th></tr></thead><tbody>'+''.join(table)+'</tbody></table><script>document.getElementById("filter").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#results tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script>'
    (OUT/'index.html').write_text(page('千星实测验证',body))
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
