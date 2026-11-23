"""Offline ledger and report of the frozen 2000 TIC-target search."""
import csv,html,json
from collections import Counter
from pathlib import Path
from select_discovery_2000 import ROOT,OUT,read_json,write_json,now
from run_discovery_2000 import verify

NOTES={
 '232643687':'ZTF 2020 table3 已刊疑似变星 ZTFJ184640.02+543905.4，g/r 周期 0.3557800/0.3557000 d；本轮 ZTF DR24 r/i 与四段 TESS 支持约 0.35572 d。首次发现资格排除；原 v4 合并仍未决。',
 '229945262':'Colman 2024 全表精确 TIC 匹配 4 行，两个分类器均为 1，LS 周期约 0.865144 d；本轮四段周期约 0.8663 d、ZTF r 亦支持。已有报告，不是新发现。',
 '1102716939':'TIC 标明 DUPLICATE，canonical TIC160097983（SPLIT），对应 BD+86 230A；约 2 角秒伴星。Colman 2024 有 5 条通过两分类器的记录。追加周期约 5.13–5.75 d 不一致，像素半段周期数不足。',
 '289724676':'HD234605/ADS11244 B；原始及追加像素均判 off_target，近等亮 ADS11244 A 约 11 角秒。Colman 2024 已报告约 1.47 d，不能归属 B 或重新声称发现 A。',
 '300741820':'Zhan 2019 表1已列 TIC300741820，P=3.168(1) 小时；本轮约 0.132005 d。',
 '31381302':'Zhan 2019 表1 P=3.965(1) 小时；Günther 2020 表2 有 7 个耀发、Prot=0.165190 d。',
 '150145456':'Günther 2020 表2精确 TIC 匹配，7 个耀发、Prot=0.214977 d。',
 '300039094':'Balona 2019 全表精确 TIC 匹配 DSCT+ROT；原始采样的约 0.036818 d 峰低于冻结搜索下限，不能当成新发现。',
 '269792987':'与邻星 TIC269792989/HD29783/NSV16112 共享约 0.843 d 信号，分量归属未分清；自身亦有 Colman 2024 周期记录。',
 '269792989':'HD29783/NSV16112，Balona 2019 DSCT+ROT；与 TIC269792987 混光。',
 '271725679':'Günther 2020 表2有 15 个耀发与 Prot=1.807819 d；本轮约 0.8121 d 与该周期不同，已有变光报告仍排除首次发现。',
 '30189015':'SIMBAD 精确别名关联 MACHO/EROS 变星文献，需警惕前景高自行星与 LMC 对象的历史交叉识别；本轮周期未获最终采用，不作首次发现主张。',
 '300292124':'HD58896，Colman 2024 有两条合格周期记录约 0.955/0.475 d；本轮追加时段后规则弃选。',
 '230089225':'四段原始测光主要在约 1.57 d，而原重复候选为约 3.14 d；ZTF g/i 诊断约 1.5688 d，有季节变化与半倍周期歧义，不能覆盖原 v4 未决。',
 '288471156':'四段 TESS 约 0.675 d，ZTF r 有 42 个合格点支持附近周期，g 仅 29 点；需结合后续全表查重，不由 X 射线/射电收录直接判定光学变光已知。',
}

def build():
    verify();cases=read_json(OUT/'targets.json')['cases'];preds={p.stem:read_json(p) for p in (OUT/'results').glob('*.json')}
    assert len(preds)==2000 and all(p['status']=='completed' for p in preds.values())
    known={};late={};published={}
    def add(tic,source):known.setdefault(str(tic),[]).append(source)
    for name in ['tars-zenodo','rotation2024-zenodo']:
        p=OUT/f'{name}-crossmatch.json'
        if p.exists():
            late[name]=read_json(p)
            for m in late[name]['matches']:
                row=m['row']
                if name=='rotation2024-zenodo' and not (row['Classifier 1']=='1' and row['Classifier 2']=='1'):continue
                if name=='tars-zenodo':
                    assert float(row['adopted_period'])>0
                    published.setdefault(m['project_tic'],[]).append({'catalogue':'Boyle2026 TARS','matched_tic':m['matched_tic'],'gaia_dr3':row['dr3_source_id'],
                        'period_d':row['adopted_period'],'period_unc_d':row['adopted_period_unc'],'possible_binary':row['flag_possible_binary'],
                        'multiple_periods':row['flag_multiple_periods'],'contaminants':row['final_n_contams'],'n_sectors':row['n_secs']})
                add(m['project_tic'],name)
    for r in read_json(OUT/'gunther2020-crossmatch.json')['matches']:add(r['TIC'],'Günther2020 flares/rotation')
    for r in read_json(OUT/'zhan2019-crossmatch.json')['matches']:add(r['tic'],'Zhan2019 Table1')
    add('232643687','Chen2020 ZTF suspected-variable table3')
    for tic in ['300039094','269792989']:add(tic,'Balona2019 DSCT+ROT')
    catalog=read_json(OUT/'catalog-screen.json');screen={r['tic']:r for r in catalog['rows']}
    assert catalog['gaia_queries_complete']==catalog['vsx_queries_complete']==2000
    rows=[];details=[]
    for c in cases:
        tic=c['tic'];r=preds[tic];gaia=screen[tic]['gaia'];vsx=screen[tic]['vsx']
        assert gaia is not None and vsx['status']=='completed'
        row={'tic':tic,'analysis_status':r['status'],'repeated_detection':bool(r['periodic_detected']),
             'initial_period_d':r['decision']['selected_period_d'],'gaia_query':'completed','vsx_query':'completed',
             'catalog_issues':'; '.join(screen[tic]['issues']),
             'additional_epochs':'not_triggered','source_execution':'not_triggered','identity_followup':'not_triggered',
             'prior_publication_matches':'; '.join(known.get(tic,[])),'disposition':'no_repeated_signal_under_frozen_rule','submission_ready':False}
        if r['periodic_detected']:
            source=read_json(OUT/'source-results'/f'{tic}.json');ext=read_json(OUT/'extension-results'/f'{tic}.json');fol=read_json(OUT/'followup-results'/f'{tic}.json');raw=read_json(OUT/'raw-cadence'/tic/'summary.json')
            assert ext['status']==fol['status']=='completed'
            states=[x['conclusion']['source_status'] for x in source.get('reviews',[])];errors=[e.get('error','') for e in source.get('errors',[])]
            coverage=bool(errors) and all('Insufficient pixel segment cycles' in e for e in errors)
            source_exec='coverage_insufficient' if coverage else source['status']
            maxraw=max(q['raw_ls_power'] for x in raw['rows'] for q in x['fixed_period_diagnostics'])
            ids=fol['services']['simbad_identity']['data'];name=ids[0]['main_id'] if ids else ''
            gaiaids={str(x['dr3_source_id']) for x in fol['services'].get('gaia_dr2_dr3',{}).get('data',[])}
            vmatches=[o for o in vsx['objects'] if o['Name'].startswith('Gaia DR3 ') and o['Name'][9:] in gaiaids]
            if not vmatches:
                vmatches=[o for o in vsx['objects'] if o['separation_arcsec']<1 and (name.replace(' ','')==o['Name'].replace(' ','') or len(gaiaids)==1)]
            if vmatches:add(tic,'VSX '+', '.join(o['Name'] for o in vmatches))
            if tic in known:disposition='prior_public_report'
            elif 'off_target_signal' in states:disposition='signal_not_attributed_to_target'
            else:disposition='evidence_insufficient_for_submission'
            note=NOTES.get(tic,'')
            if maxraw<.002:note+=' 原候选及半倍/两倍在未分箱测光中的 LS power 均低于 0.002；此为诊断描述，不是新评分门槛，不能据此断言整颗星恒定或已证明仪器故障。'
            if tic in known:note+=' 已有公开报告的命中见逐表原始行；目录记录未必保证来源、物理分类或周期正确。'
            row.update(name=name,additional_epochs=ext['added_epochs'],extended_period_d=ext['decision']['selected_period_d'],source_execution=source_exec,
                       source_status='; '.join(states),identity_followup=fol['status'],raw_cadence='completed',max_fixed_raw_power=maxraw,
                       prior_publication_matches='; '.join(known.get(tic,[])),disposition=disposition,note=note)
            refs=[z for z in fol['services'].get('simbad_references',{}).get('data',[]) if z['oidref'] in fol['target_simbad_oids']]
            details.append(dict(row,source_errors=errors,reference_index=refs,published_periods=published.get(tic,[]),diagnostic_periods_d=raw['candidate_periods_d'],
                                initial_result=r['case_path'],extension_result=ext['case_path'],source_result=str((OUT/'source-results'/f'{tic}.json').relative_to(ROOT))))
        rows.append(row)
    assert len(details)==43
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/'ledger-2000.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    write_json(OUT/'review-43.json',{'at':now(),'rows':details,'policy':'Late manual and catalogue review; original detections and period decisions remain frozen. Query completion is not exhaustive full-text review. References are preserved as an index unless exact-table/full-text evidence is explicitly recorded.'})
    stats={'at':now(),'planned':2000,'completed':2000,'analysis_failures':0,'original_lightcurves':sum(len(r['inputs']) for r in preds.values()),'repeated_detections':43,'initial_adopted_periods':sum(r['decision']['selected_period_d'] is not None for r in preds.values()),
           'additional_lightcurves':sum(r['additional_epochs'] for r in details),'extended_adopted_periods':sum(r.get('extended_period_d') is not None for r in details),
           'source_execution':dict(Counter(r['source_execution'] for r in details)),'dispositions':dict(Counter(r['disposition'] for r in details)),
           'confirmed_first_discoveries':0,'submission_ready':0,'late_catalogues':{n:{'rows':v['catalogue_rows'],'matched_rows':len(v['matches']),'matched_targets':len({m['project_tic'] for m in v['matches']})} for n,v in late.items()},
           'limits':['2000 fixed TIC targets, not truth-labelled objects; cannot estimate accuracy or discovery probability.','Gaia main service maintenance; validated public ARI mirror used.','Live VSX Human Verification stopped; public VizieR mirror dated 2026-10-19 is not a current submission Spot check.','Source execution and TESS-resolution support do not establish unresolved binary component attribution.']}
    write_json(OUT/'final-summary.json',stats)
    body=['# 2,000 个 TESS 目标检索与复核','',f"基础分析 **2,000/2,000 完成，失败 0**；原始双时段共 4,000 份光变。冻结规则检出 43 个跨时段重复信号，初步采用周期 6 个。新增 {stats['additional_lightcurves']} 份光变用于全部 43 个对象的追加时段检查。",'',
          '当前确认的首次新发现 **0**，可以直接正式提交的对象 **0**。这些是固定名单的实际结果；没有为了得到发现调整检测门槛或补入替代对象。','',
          '## 复核结果','',f"43 个对象的当前处理：{stats['dispositions']}。像素来源执行状态：{stats['source_execution']}。coverage_insufficient 表示观测半段不足指定周期数，不是一次通过，也不是光变下载失败。",'',
          '初步周期采用的 6 个对象均有先前公开变光/周期记录。TIC232643687 的地面观测重现约 0.35572 d，但 Chen 2020 疑似变星表已有同一对象和相同周期，退出首次发现队列。完整结论见下表及 `review-43.json`。','',
          '## 数据与重算','',
          '固定名单与科学代码于 fd0d79e9 提交后才取得新光变。初筛只接收身份与测光，不接收目录周期。后续新增目录查询属于结果查重，不能反过来改变本轮分母。',
          '[2,000 行逐目标表](ledger-2000.csv)；[43 个信号详细判定](review-43.json)；[机器摘要](final-summary.json)。未检出只表示未达到冻结规则，不等于恒定星。',
          '[原始 FITS 与批量图表公开归档](https://github.com/zczc/variable-star-discovery/releases/tag/discovery-2000-2026-11-23-data)。`data-archive/` 含每个文件 SHA256 和经核验的 GitHub 资产 digest；按仓库相对路径解压即可恢复。已完成非检出对象的部分本地 FITS 缓存因磁盘空间释放，逐项留有校验及公开副本。',
          '全部原始结果 JSON、下载回执、追加诊断和论文命中行保留。初筛 2,000 星 PNG 在公开图表归档；43 星追加时段图保留在 `extensions/`。','',
          '## 逐对象结果','', '| TIC | 原周期/d | 追加周期/d | 处置 | 说明 |','|---|---:|---:|---|---|']
    for r in sorted(details,key=lambda r:int(r['tic'])):
        body.append(f"| {r['tic']} | {r['initial_period_d'] or '—'} | {r.get('extended_period_d') or '—'} | {r['disposition']} | {r['note']} |")
    body += ['','## 边界与引用','',
             '本轮保存了 Gaia、VSX、SIMBAD 和 ASAS-SN 查询；针对有希望的信号检查了原始论文表、全目录和独立观测。没有把所有对象关联的每篇论文声称为全文读完。源未解、周期未定或查询不足的对象不升级为发现。',
             '使用镜像的原因、日期和失败回执均保留。VSX 网站的人机验证未绕过；任何未来正式提交仍须登录后 Check name / Spot check 与署名确认。','',
             '- Zhan et al. (2019), https://doi.org/10.3847/1538-4357/ab158c ：表1精确 TIC 和小时周期。',
             '- Günther et al. (2020), '+read_json(OUT/'gunther2020-crossmatch.json')['reference']+' ：完整 VizieR table2，耀发和周期各自标明。',
             '- Chen et al. (2020), https://doi.org/10.3847/1538-4365/ab9cae ：疑似变星表3也属于先前公开报告。',
             '- Colman et al. (2024), https://arxiv.org/abs/2402.14954 ；数据 https://doi.org/10.5281/zenodo.10684613 ，按分类器字段核对。',
             '- TESS All-Sky Rotation Survey (2026), https://arxiv.org/abs/2603.05586 ；全表 https://doi.org/10.5281/zenodo.19917941 。',
             '- Balona (2019), https://doi.org/10.1093/mnras/stz2808 ：完整表中的 DSCT+ROT 记录，不混淆自转频率与脉动频率。',
             '- Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065 。文献核对流程的软件方法来源，非天文发现证据。','']
    (OUT/'REPORT.md').write_text('\n'.join(body))
    # Lightweight, local table with direct source and extended-plot links.
    trs=[]
    for r in sorted(details,key=lambda r:int(r['tic'])):
        tic=r['tic'];images=sorted((OUT/'extensions'/tic).rglob('*.png'))
        links=' '.join(f'<a href="{p.relative_to(OUT)}">{p.name}</a>' for p in images)
        trs.append(f"<tr><td>{tic}</td><td>{html.escape(r['name'])}</td><td>{html.escape(r['disposition'])}</td><td>{html.escape(r['note'])}<br>{links}</td></tr>")
    (OUT/'index.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>2,000 星复核</title><style>body{font:16px system-ui;max-width:1450px;margin:30px auto;color:#172337}td,th{padding:10px;border:1px solid #ccd2da;vertical-align:top}table{border-collapse:collapse}a{color:#1653a4}input{padding:10px;width:45%}</style><h1>2,000 星检索与复核</h1><p>2,000 完成；43 个重复信号；6 个初步采用周期；当前首次发现与可提交对象均为 0。</p><p><a href="REPORT.md">完整报告</a> · <a href="ledger-2000.csv">2,000 行数据</a> · <a href="review-43.json">详细审查记录</a></p><input id="q" placeholder="按 TIC、名称或结论筛选"><table><thead><tr><th>TIC</th><th>名称</th><th>处置</th><th>证据与局限</th></tr></thead><tbody>'+''.join(trs)+'</tbody></table><script>document.querySelector("#q").oninput=e=>document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase()))</script></html>')
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':build()
