"""Render recorded v2 outcomes and the separately acquired real-positive pilot."""
from pathlib import Path
from html import escape
import os
from vstar.io import read_json, write_json, sha256
from vstar.reports import page
from vstar.review import write_case_report

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT/"repo/benchmarks"
KINDS = {
    "real_known_variable": "真实已知变星（原开发样本）", "real_contaminated_target": "真实邻星污染（旧案例）",
    "synthetic_white_noise": "模拟独立噪声", "synthetic_correlated_noise": "模拟相关噪声", "synthetic_trend": "模拟缓慢漂移",
    "synthetic_sinusoid": "模拟波浪形周期", "synthetic_unequal_eclipses": "模拟深浅不同的食",
    "synthetic_equal_eclipses": "模拟完全相同的食", "synthetic_common_mode": "模拟仪器周期",
    "real_new_positive_control": "首次用于测试的真实已知变星"}
DECISIONS = {"not_repeated_in_all_epochs": "未通过全部时段的重复要求", "competing_periods": "时段间周期有分歧",
             "period_ambiguous": "有周期，保留歧义", "source_caution": "有周期，来源需复核",
             "periodic_source_unchecked": "有周期，来源未充分检查", "periodic_target_supported": "周期和基础定位支持目标",
             "likely_contaminated": "疑似邻星污染", "unavailable": "数据不可用", "failed": "运行失败"}
PERIOD_STATUS = {"preferred_lightcurve_cycle": "优选亮度周期", "half_double_ambiguous": "完整绕转周期仍有歧义",
                 "multiple_supported_periods": "多组周期候选尚未排清", "competing_aliases": "竞争周期尚未排清", "not_established": "未建立周期"}
SCORES = {"correct_period": "符合参考（1% 内）", "half_period": "错误：半周期", "double_period": "错误：双周期",
          "not_recovered": "未恢复参考", "abstained_or_unscored": "未选择最终周期"}


def format_period(value):
    return f"{value:.8f}" if value is not None else "—"


def render(run, other):
    data = read_json(run/"results.json")
    for row in data["results"]:
        write_case_report(run/row["id"], row)
    pilot = data["mode"] == "independent-pilot"
    title = "新加入的真实已知变星：未参与调参的小测试" if pilot else "第二版识别：进步和剩下的错误"
    body = f'<h1>{title}</h1><div class="notice">'
    body += ('6 颗真实已知变星，算法冻结后才分析光变。5 颗检出重复信号；3 颗最终周期正确，1 颗双周期错误，1 颗保留歧义，1 颗未通过。'
             if pilot else '在原有开发案例上，漂移误报消失，深浅食检出从 2 / 4 增至 3 / 4，仪器周期被转入来源复核。但还有漏检和不必要的周期歧义。')
    body += '没有足够的真实反例，识别能力仍未通过完整验收。</div>'
    other_link = os.path.relpath(other/"index.html", run)
    doc_link = os.path.relpath(ROOT/"doc/13-v2-recognition-results.md", run)
    body += f'<p><a href="{other_link}">{"查看原开发集对照" if pilot else "查看另外 6 颗真实已知变星的结果"}</a> · <a href="{doc_link}">通俗解读和下一步</a></p>'
    body += '<p>“检出重复信号”只表示时段间存在可重复的变化。“最终周期”是程序是否愿意选择一个值。“来源复核”提示检查邻星、背景或指向，不能直接断定是仪器，也不表示目标已被确认。</p>'
    if not pilot:
        first = read_json(BENCH/"mixed-v02/results.json")
        body += '<h2>同一份输入，新旧结果</h2><table><tr><th>类型</th><th>完成 / 原清单</th><th>旧版周期候选</th><th>v2 首轮检出</th><th>v2.1 检出</th><th>来源检查后仍保留的候选</th></tr>'
        for kind, m in data["metrics"].items():
            a = first["metrics"][kind]
            body += f'<tr><td>{KINDS[kind]}</td><td>{m["completed"]} / {m["cases"]}</td><td>{m["old_candidate_alerts"]}</td><td>{a["periodic_detected"]}</td><td>{m["periodic_detected"]}</td><td>{m["target_candidates"]}</td></tr>'
        body += '</table><p>最后一列仍包含周期歧义和来源未查完的候选，不是确认数。源头有疑点的对象保留在复核队列。全部案例仍计数，没有把困难对象悄悄移走。</p>'
        body += '<h2>进步与代价</h2><ul><li>4 个模拟漂移不再误报；12 个噪声模拟仍未报周期。</li><li>4 个深浅食中检出 3 个，另 1 个因观测缺口造成交替周期训练覆盖不足而未通过。3 个检出对象的亮度周期接近参考，但其中 2 个仍被竞争周期规则留为歧义。</li><li>4 个模拟正弦都检出，亮度周期都符合；其中 2 个被较弱的竞争解释阻止选择最终周期，属于新增的过度保守判断。</li><li>3 个模拟仪器周期都被辅助通道相关性标出。同时，真实 TU Her 和 AI Vel 也因亮斑中心变化进入复核：相关性不是仪器故障的证明。</li><li>AI Vel 的两个时段都支持约 0.08617 和 0.11160 天。程序保留多组候选，不再因为最强峰交换就漏掉变化；尚未选定目录所列主周期。</li></ul>'
    else:
        body += '<h2>逐星结果</h2><table><tr><th>已知星</th><th>参考周期（天）</th><th>最终选定周期</th><th>评价</th><th>处理</th></tr>'
        for r in data["results"]:
            c = r["conclusion"]
            body += f'<tr><td><a href="{r["id"]}/index.html">{r["id"].upper()}</a></td><td>{format_period(r["reference"]["period_d"])}</td><td>{format_period(c["selected_period_d"])}</td><td>{SCORES[r["score"]["preferred_cycle"]]}</td><td>{DECISIONS[c["decision"]]}</td></tr>'
        body += '</table><p>分母始终是 6 颗：不能去掉未通过和保留歧义的对象，只按给了答案的 4 颗计算成绩。这个小样本按名字挑选，不代表真实总体。</p>'
        body += '<h2>独立小测试暴露的问题</h2><ul><li>U Sge：目录约 3.380656 天，程序选了约 6.760592 天。两倍周期模型得分更高时，目前的选择规则仍可能出错。</li><li>SZ Lyn：亮度周期约 0.120535 天已恢复，但规则把其他倍周期或别名也留在候选中，未选择最终值。这不证明恒星有多种独立物理周期。</li><li>RT Aur：第 20 批也未通过交替周期预测要求；第 1751 批是约 7 天的实际短观测，少于三轮 3.72824 天的变化。不能把未通过全归因于短观测，也没有更换这个预选样本。</li><li>RZ Cas：周期符合，但亮斑中心与光变相关，保留来源复核。真实食本身也会改变混合光的中心。</li></ul>'
    body += '<h2>全部案例与证据</h2><table><tr><th>案例</th><th>类型</th><th>处理</th><th>周期状态</th></tr>'
    for r in data["results"]:
        c = r.get("conclusion", {})
        body += f'<tr><td><a href="{r["id"]}/index.html">{escape(r["id"])}</a></td><td>{KINDS[r["kind"]]}</td><td>{DECISIONS.get(c.get("decision", r["status"]), c.get("decision", r["status"]))}</td><td>{PERIOD_STATUS.get(c.get("period_status"), "未分析")}</td></tr>'
    body += '</table><p><a href="comparison.csv">下载对照表</a> · <a href="results.json">完整结果</a> · <a href="predictions.json">对照目录答案之前保存的预测</a></p>'
    body += '<p>没有向 AAVSO 提交，没有恢复未知对象筛选。下一步要改进倍周期与弱竞争峰处理、稀疏事件验证，再补有可靠标签的真实反例。若用本次 6 颗星调试，它们之后就属于开发集，不能再充当独立测试。</p>'
    (run/"index.html").write_text(page(title, body))
    write_json(run/"report-provenance.json", {"renderer_sha256": sha256(Path(__file__)), "results_sha256": sha256(run/"results.json"),
                                             "case_renderer_sha256": sha256(ROOT/"repo/src/vstar/review.py"),
                                             "note": "Post-evaluation narrative; does not change predictions or decision thresholds."})


if __name__ == "__main__":
    development, pilot = BENCH/"mixed-v03", BENCH/"independent-pilot-v01/evaluation"
    render(development, pilot); render(pilot, development)
    print(development/"index.html")
