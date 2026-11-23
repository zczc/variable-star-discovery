"""Report all frozen discovery targets, including failures and nondetections."""
import csv
from collections import Counter
from html import escape
from run_discovery_batch import ROOT,OUT,verify
from vstar.io import read_json,write_json
from vstar.reports import page


def build():
    verify()
    targets=read_json(OUT/'targets.json');screen=read_json(OUT/'catalog-screen.json');run=read_json(OUT/'run-status.json')
    rows=[]
    for c in targets['cases']:
        r=read_json(OUT/'results'/f'{c["tic"]}.json')
        row={'tic':c['tic'],'status':r['status'],'periodic_detected':r.get('periodic_detected',False),
             'selected_period_d':r.get('decision',{}).get('selected_period_d'),
             'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False}
        if r['status']=='completed':
            d=read_json(OUT/'evaluation'/c['tic']/'case.json')
            for name in ['SAP','PDCSAP']:
                row[name+'_positive_epochs']=sum(o['products'][name]['result']['periodic_detected'] for o in d['observations'])
            row['sectors']=' / '.join(str(o['sector']) for o in d['observations'])
            row['route']='period_candidate_source_unchecked' if row['selected_period_d'] is not None else ('repeated_signal_period_unresolved' if row['periodic_detected'] else 'not_repeated_by_frozen_detector')
        else:row['route']='analysis_unavailable'
        rows.append(row)
    summary={'date':'2026-11-23','frozen_commit':'a86ae7a3','pool':100,'catalog_screen_counts':screen['counts'],
             'eligible':targets['all_eligible'],'analyzed':len(rows),'eligible_deferred_by_cap':targets['remaining_eligible_deferred'],
             'run_status':run,'counts':dict(Counter(r['route'] for r in rows)),
             'confirmed_new_discoveries':0,'submission_ready_count':0,'rows':rows,
             'limitations':['This is discovery screening of unlabelled stars, not an accuracy or false-positive evaluation.',
                           'No source-pixel follow-up was initiated because no target passed cross-epoch detection.',
                           'Catalogue and isolation restrictions are conservative operational criteria; they do not prove novelty or source attribution.',
                           'All 20 outcomes retained; no replacement objects, threshold change, or reinterpretation as known constant stars.']}
    write_json(OUT/'summary.json',summary)
    keys=sorted(set().union(*(r.keys() for r in rows)))
    with (OUT/'summary.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    body='<h1>新一批对象：100 颗预筛，20 颗盲测</h1><p>2026-11-23。20 颗全部完成、运行失败 0、跨时段检出 0、最终周期 0、确认新发现 0。</p>'
    body+='<p>目录和邻星筛选：43 个已有变光报告，13 个近亮邻星，8 个有附近 VSX 记录，15 个 Gaia 身份未明确，21 个满足本轮预筛。按冻结顺序取前 20 个，1 个按数量上限暂缓。</p>'
    body+='<p>15 颗两产品在两个时段均未通过检出；5 颗仅 SAP 在一个时段通过，均未形成跨时段重复。它们没有真值标签，不能称为 20 个正确反例或据此计算准确率。</p>'
    body+='<p><a href="summary.csv">逐星 CSV</a> · <a href="catalog-screen.json">全部 100 个预筛原因</a> · <a href="analysis-protocol.json">冻结规则</a> · <a href="../hd43737-followup-2026-11-23/index.html">HD 43737A/B 复核</a></p>'
    body+='<table><tr><th>TIC</th><th>观测区</th><th>SAP 合格时段</th><th>PDCSAP 合格时段</th><th>跨时段判断</th></tr>'
    for r in rows:
        body+=f'<tr><td><a href="evaluation/{r["tic"]}/index.html">{r["tic"]}</a></td><td>{r.get("sectors","")}</td><td>{r.get("SAP_positive_epochs","")} / 2</td><td>{r.get("PDCSAP_positive_epochs","")} / 2</td><td>{escape(r["route"])}</td></tr>'
    body+='</table><p>本轮未逐张人工裁定全部新光变图；此表是冻结算法的保存输出。未为获得候选而放宽标准。</p>'
    (OUT/'index.html').write_text(page('新对象搜索批次',body))
    print(summary['counts'])

if __name__=='__main__':build()
