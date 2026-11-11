"""Render the complete v3 development comparison, including regressions."""
from pathlib import Path
from html import escape
from vstar.io import read_json,write_json,sha256,now
from vstar.reports import page
from vstar.review import DECISIONS
ROOT=Path(__file__).resolve().parents[2]
BENCH=ROOT/'repo/benchmarks'
KINDS={'real_known_variable':'原有真实变星（含 2 个不可用）','real_contaminated_target':'真实污染案例',
       'real_new_positive_control':'原 6 星测试组，现为开发样本','synthetic_white_noise':'模拟白噪声',
       'synthetic_correlated_noise':'模拟相关噪声','synthetic_trend':'模拟漂移','synthetic_sinusoid':'模拟平滑周期',
       'synthetic_unequal_eclipses':'模拟深浅食','synthetic_equal_eclipses':'模拟等深食','synthetic_common_mode':'模拟仪器周期'}
STATUS={'preferred_lightcurve_cycle':'选定优选周期','multiple_supported_periods':'残余变化支持竞争周期',
        'cross_epoch_harmonic_conflict':'各时段对半/倍周期仍有分歧','half_double_ambiguous':'完整绕转周期有歧义',
        'not_established':'未建立周期','competing_aliases':'竞争周期未排清'}

def fmt(row):
    c=row.get('conclusion',{});p=c.get('selected_period_d')
    return f'{p:.8f} 天' if p else STATUS.get(c.get('period_status'),'不可用或失败')

def build(name,previous):
    run=BENCH/name;result=read_json(run/'results.json');old={r['id']:r for r in read_json(BENCH/previous/'results.json')['results']}
    body='<h1>第三版：哪些问题改善了，哪些还没有</h1><div class="notice">本页全部是开发案例。原来的 6 颗独立测试星现已用于调试；重跑不是独立验证。尚无真实安静星反例，尚无确认的新变星。</div>'
    body+='<p>周期表示“亮度形状隔多久重复”。即使选中了周期，还要核实变化来自哪颗星、是否有人已经报告。所有预测分数都是算法诊断，不是可信概率。</p>'
    body+='<p>模拟深浅食从检出 3/4 改为 4/4，最终周期从正确 1/4 改为 4/4；模拟平滑周期最终正确 2/4→4/4。16 个模拟噪声/漂移仍无误报。真实星 SZ Lyn 修复弃选、U Sge 从选错转为弃选，但 W UMa 从选对转为弃选，RT Aur 仍漏检。</p>'
    body+='<p>6 颗真实星最终正确仍为 3/6，选错 1→0，未选出 2→3。谨慎减少了一项明确错误，也损失了一项原先正确的判断，尚未达到验收要求。</p>'
    body+='<p><a href="../mixed-v04/index.html">原 36 个开发案例</a> · <a href="../former-pilot-v3/index.html">原 6 星测试组</a> · <a href="../../../doc/14-v3-and-submission-readiness.md">何时能用于筛选、何时能投稿</a></p>'
    body+='<table><tr><th>类别</th><th>总数</th><th>完成/不可用/失败</th><th>检出周期</th><th>最终周期正确</th></tr>'
    for kind,m in result['metrics'].items():
        body+=f'<tr><td>{KINDS.get(kind,kind)}</td><td>{m["cases"]}</td><td>{m["completed"]}/{m["unavailable"]}/{m["failed"]}</td><td>{m["periodic_detected"]}</td><td>{m["preferred_cycle_results"].get("correct_period",0)}</td></tr>'
    body+='</table><p>无周期的模拟对照和来源污染案例不以“最终周期正确”验收。等深食能恢复亮度重复周期，但不能因此唯一确定完整轨道；两个等深案例均保留这个疑问。</p>'
    body+='<table><tr><th>案例及证据图</th><th>上一版最终周期</th><th>第三版最终周期</th><th>处理</th></tr>'
    for row in result['results']:
        c=row.get('conclusion',{})
        body+=f'<tr><td><a href="{escape(row["id"])}/index.html">{escape(row["id"])}</a></td><td>{fmt(old[row["id"]])}</td><td>{fmt(row)}</td><td>{DECISIONS.get(c.get("decision"),row["status"])}</td></tr>'
    body+='</table><p>下一步要用逐次食事件和基线复核解决 W UMa、U Sge 的分歧，处理 RT Aur 的漏检，再补可信实测反例及全新的独立测试。原未知目标筛选保持暂停。</p><p><a href="results.json">完整结果</a> · <a href="predictions.json">参考答案评分前的预测</a> · <a href="comparison.csv">逐案例数据表</a></p>'
    (run/'index.html').write_text(page('第三版开发对照',body))
    write_json(run/'report-provenance.json',{'created_at':now(),'results_sha256':sha256(run/'results.json'),'renderer_sha256':sha256(Path(__file__))})
    (run/'README.md').write_text(f'# 第三版开发结果\n\n[打开完整报告](index.html)。本目录 {len(result["results"])} 个案例全部是开发样本，不是新的独立测试；包含全部错误、不可用和弃选结果。\n\n旧结果保留在 `{previous}`。本轮规则为 `v3-protocol-v01.json`，入口为 `evaluate_v3.py`；逐案例图表和评分前预测可复核。观测结果沿用 `v2` 键以兼容报告，实际算法由 `algorithm_revision` 字段标明。\n\n当前没有确认的新变星，也没有向 VSX 提交。\n')

if __name__=='__main__':
    build('mixed-v04','mixed-v03')
    build('former-pilot-v3','independent-pilot-v01/evaluation')
