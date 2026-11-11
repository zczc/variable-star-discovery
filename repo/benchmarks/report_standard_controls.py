from pathlib import Path
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/standard-star-check-v01'


def main():
    out=BASE/'evaluation';path=out/'predictions.json';data=read_json(path)
    assert data['complete']
    manifest=read_json(BASE/'input-manifest.json');identities={c['id']:c for c in manifest['cases']}
    rows=[];body='<h1>三颗有文献依据的标准星：实测检查</h1>'
    body+='<p>在查看 TESS 光变前，选定 Marinoni 等论文表 3 的前三颗基础标准星。每颗取最早、最晚两个受支持时段，使用已冻结的 v4。</p><p>原论文的“不变”只适用于其测量波段、时段和精度；这三颗不计入正式 TESS 安静星分母。程序没有找到周期，也不能反过来证明标签正确。</p>'
    body+='<table><tr><th>对象 / TIC</th><th>时段</th><th>SAP 跨时段周期</th><th>PDCSAP 跨时段周期</th><th>最终周期</th></tr>'
    for case in data['results']:
        products=case['products'] or {};decision=case['decision'] or {};source=identities[case['id']]
        row={'id':case['id'],'name':case['name'],'tic':source.get('tic'),'status':case['status'],
             'sectors':[i['sector'] for i in source['inputs']],
             'selected_period_d':decision.get('selected_period_d'),
             'products':{k:{'periodic_detected':v['periodic_detected'],'period_status':v['period_status']} for k,v in products.get('conclusions',{}).items()}}
        rows.append(row)
        texts=[('未建立' if not v['periodic_detected'] else '有候选') for v in row['products'].values()]
        body+=f'<tr><td><a href="{row["id"]}/index.html">{row["name"]} / {row["tic"]}</a></td><td>{row["sectors"]}</td><td>{texts[0]}</td><td>{texts[1]}</td><td>{row["selected_period_d"]}</td></tr>'
    result={'created_at':now(),'predictions_sha256':sha256(path),'rows':rows,'completed_stars':sum(r['status']=='completed' for r in rows),
            'repeated_candidates_stars':sum(any(p['periodic_detected'] for p in r['products'].values()) for r in rows),
            'validated_TESS_quiet_stars':0,'false_positive_rate':None,
            'note':'Descriptive check with external bounded priors. Neither accepted true-negative labels nor calibrated false-positive statistics.'}
    write_json(out/'results.json',result)
    body+='<p>没有建立周期：只表示本次方法未找到满足重复条件的信号，不表示恒星绝对不变。原始 FITS、身份匹配与下载记录均保留。</p><p><a href="../protocol.json">预先选定的名单及文献限制</a> · <a href="../input-manifest.json">原始数据来源</a> · <a href="results.json">汇总数据</a></p>'
    (out/'index.html').write_text(page('三颗标准星实测检查',body))

if __name__=='__main__':main()
