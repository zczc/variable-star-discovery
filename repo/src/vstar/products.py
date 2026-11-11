"""Independent SAP/PDC searches on supplied data; product disputes require review."""
from dataclasses import asdict
from pathlib import Path
from html import escape
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .photometry import read_lightcurve,bin_lightcurve
from .auxiliary import read_auxiliary
from .review import review_epoch
from .screening_v3 import ScreeningConfig,combine_epochs
from .models import AnalysisConfig
from .io import write_json,now,sha256,code_fingerprint
from .reports import page

PRODUCTS={'SAP':'SAP_FLUX','PDCSAP':'PDCSAP_FLUX'}


def summarize_products(conclusions,errors=None,tolerance=.01):
    """Keep competing product hypotheses; a clearer SAP curve is not source proof."""
    hypotheses=[]
    for name,c in conclusions.items():
        if c.get('periodic_detected'):
            hypotheses.append({'product':name,'photometric_period_d':c['photometric_period_d'],
                               'selected_period_d':c['selected_period_d'],'period_status':c['period_status'],
                               'source_status':c['source_status']})
    selected=[c['selected_period_d'] for c in conclusions.values() if c.get('selected_period_d')]
    agreement=(len(selected)==2 and abs(selected[0]/selected[1]-1)<=tolerance)
    status=('analysis_failed' if errors else 'both_products_agree' if agreement else
            'product_review_required' if hypotheses else 'insufficient_repeated_evidence')
    return {'status':status,'period_hypotheses':hypotheses,
            'agreed_period_d':float(np.median(selected)) if agreement and not errors else None,
            'confirmed_variable':False,'target_candidate':False,'source_status':'not_assessed_by_product_comparison',
            'note':'SAP and PDCSAP are reductions of the same pixels, not independent observations. Agreement cannot exclude common contamination; disagreement is not automatically proof of overcorrection.'}


def analyze_product_epoch(path,analysis=None,config=None):
    analysis=analysis or AnalysisConfig(use_bls=True);config=config or ScreeningConfig()
    auxiliary=read_auxiliary(path,analysis.bin_minutes)
    results={};diagnostics={}
    for name,column in PRODUCTS.items():
        raw=read_lightcurve(path,column)
        # Neither product borrows the other's discovered periods or catalogue labels.
        result,diagnostic,baseline=review_epoch(raw,auxiliary=auxiliary,analysis=analysis,config=config,revision='v3')
        results[name]={'result':result,'baseline':baseline}
        diagnostics[name]=diagnostic
    return results,diagnostics


def plot_products(diagnostics,results,path):
    fig,axes=plt.subplots(2,3,figsize=(14,6),layout='constrained')
    for i,name in enumerate(PRODUCTS):
        raw,clean,trend=diagnostics[name];result=results[name]['result']
        p=result['photometric_period_d'] or result['candidates'][0]['period_d']
        axes[i,0].plot(raw.time-raw.time.min(),raw.flux*100,'.',ms=1)
        axes[i,0].plot(raw.time-raw.time.min(),trend*100,'r-',lw=.8)
        axes[i,0].set(title=f'{name}: measured flux',xlabel='Days from start',ylabel='Relative flux (%)')
        for j,period in enumerate([p,2*p],1):
            axes[i,j].plot(((clean.time-clean.time.min())/period)%1,clean.flux*100,'.',ms=1,alpha=.5)
            axes[i,j].set(title=f'{name}: {period:.8f} d',xlabel='Phase (arbitrary zero)')
    fig.suptitle('Independent product searches; same photons, not independent detections')
    fig.savefig(path,dpi=130);plt.close(fig)


def write_product_report(out,row):
    body=f'<h1>{escape(row["id"])}：两种测光产品独立分析</h1>'
    body+='<div class="notice">SAP 是孔径测光；PDCSAP 是进一步校正后的产品。两者来自同一批观测，不能算两次独立验证。较规律的图也不能证明来源一定是目标。</div>'
    body+='<p>两种产品分别搜索周期，再分别比较观测时段。这里保留产品之间的分歧，不按得分挑选一个产品自动宣布发现。</p>'
    body+='<table><tr><th>产品</th><th>跨时段检出</th><th>最终优选周期（天）</th><th>周期状态</th></tr>'
    for name,c in row['conclusions'].items():
        body+=f'<tr><td>{name}</td><td>{c["periodic_detected"]}</td><td>{c["selected_period_d"]}</td><td>{escape(c["period_status"])}</td></tr>'
    body+='</table>'
    if row['errors']:body+=f'<pre>{escape(str(row["errors"]))}</pre>'
    for obs in row['observations']:
        body+=f'<h2>观测时段 {obs["sector"]}</h2><img src="{obs["plot"]}" alt="SAP 和 PDCSAP 各自的光变及周期折叠图">'
        body+='<p>左图是未经本项目去趋势的测光，红线是拟合基线；中、右图去掉基线后，分别按各自候选周期及两倍折叠。未通过重复要求时，折叠图只展示最高分解释。</p>'
    body+='<p><a href="case.json">完整预测、处理参数和文件校验值</a></p>'
    (out/'index.html').write_text(page(row['id'],body))


def review_products(paths,out,identity='Supplied target',analysis=None,config=None):
    analysis=analysis or AnalysisConfig(use_bls=True);config=config or ScreeningConfig()
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    row={'id':identity,'created_at':now(),'code_fingerprint':code_fingerprint(),
         'analysis':asdict(analysis),'screening':asdict(config),'observations':[],'errors':[]}
    identities=set();sectors=set()
    for supplied in paths:
        path=Path(supplied).resolve()
        try:
            raw=read_lightcurve(path);tic=raw.metadata['TICID'];sector=raw.metadata['SECTOR']
            identities.add(tic)
            if len(identities)!=1 or sector in sectors:raise ValueError('Supply distinct sectors of one TIC')
            sectors.add(sector)
            result,diagnostic=analyze_product_epoch(path,analysis,config)
            plot=f's{sector:04d}-products.png';plot_products(diagnostic,result,out/plot)
            row['observations'].append({'sector':sector,'tic':tic,'input':{'path':str(path),'sha256':sha256(path)},
                                        'products':result,'plot':plot,'plot_sha256':sha256(out/plot)})
        except Exception as exc:row['errors'].append({'path':str(path),'error':str(exc)})
    row['conclusions']={name:combine_epochs([o['products'][name]['result'] for o in row['observations']],config) for name in PRODUCTS}
    row['comparison']=summarize_products(row['conclusions'],row['errors'],config.epoch_period_tolerance)
    write_json(out/'case.json',row);write_product_report(out,row)
    return row
