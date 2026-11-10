"""Render saved development results; reference periods appear only in diagnostic plots."""
import argparse
from html import escape
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vstar.io import read_json, sha256, write_json
from vstar.photometry import read_lightcurve, bin_lightcurve
from vstar.reports import page
from simulate_controls import as_lightcurve

ROOT = Path(__file__).resolve().parents[2]
KINDS = {
    "real_known_variable": "真实已知变星", "real_contaminated_target": "真实邻星污染案例",
    "synthetic_white_noise": "模拟：独立随机噪声", "synthetic_correlated_noise": "模拟：相邻时刻相关的噪声",
    "synthetic_trend": "模拟：缓慢漂移", "synthetic_sinusoid": "模拟：波浪形周期变化",
    "synthetic_unequal_eclipses": "模拟：深浅不同的两次食", "synthetic_equal_eclipses": "模拟：完全相同的两次食",
    "synthetic_common_mode": "模拟：仪器周期干扰",
}
STATUS = {"periodic_candidate": "留下周期候选", "inconclusive": "未留下候选，不能据此判为恒定",
          "likely_contaminated": "标为疑似邻星污染", "failed": "分析失败", "unavailable": "数据不可用"}
PERIOD = {"correct_period": "与参考相差小于 1%", "half_period": "约为参考的一半", "double_period": "约为参考的两倍", "not_recovered": "未恢复参考周期"}


def comparison(out, row, observation, bin_minutes):
    source = ROOT/observation["input"]["path"]
    assert sha256(source) == observation["input"]["sha256"]
    synthetic = row["kind"].startswith("synthetic_")
    if synthetic:
        with np.load(source) as arrays:
            lc = as_lightcurve(arrays, {})
    else:
        lc = read_lightcurve(source)
    lc = bin_lightcurve(lc, bin_minutes)
    reference = observation["evaluation"]["reference_period_d"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.3), layout="constrained", sharey=True)
    for ax, label, period in zip(axes, ["LS candidate", "BLS candidate", "Injected P" if synthetic else "Catalog / literature P"],
                                [observation["period_d"], observation["bls"]["period_d"], reference]):
        ax.plot(((lc.time-lc.time.min())/period) % 1, lc.flux*100, ".", ms=2, alpha=.45)
        ax.set(title=f"{label}: {period:.6f} d", xlabel="Phase (arbitrary zero)")
    axes[0].set_ylabel("Relative flux (%)")
    fig.suptitle(f"{'SIMULATION' if synthetic else 'REAL DATA'}: {row['id']} / S{observation['sector']}; reference used for display only")
    path = out/row["id"]/f"s{observation['sector']:04d}-comparison.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT/"repo/benchmarks/mixed-v01")
    args = parser.parse_args()
    out = args.run.resolve()
    result = read_json(out/"results.json")
    assert result["complete"]
    # The Chinese narrative explains the frozen v01 outcomes. Do not silently
    # reuse those claims when a later algorithm or environment changes results.
    original = read_json(ROOT/"repo/benchmarks/mixed-v01/results.json")
    if result["code_fingerprint"] != original["code_fingerprint"] or result["metrics"] != original["metrics"]:
        raise ValueError("This explanatory report is specific to v01; revise the narrative for changed results")
    # Normalize the display CSV's line endings without changing frozen analysis.
    csv_path = out/"results.csv"
    csv_path.write_bytes(csv_path.read_bytes().replace(b"\r\n", b"\n"))
    plots = []
    for row in result["results"]:
        folder = out/row["id"]
        body = f'<p><a href="../index.html">← 返回全部结果</a></p><h1>{escape(row["id"])}</h1><p>{KINDS[row["kind"]]}</p>'
        body += f'<div class="notice">{STATUS.get(row.get("baseline_status", row["status"]), row["status"])}</div>'
        if row["kind"].startswith("synthetic_"):
            body += '<p>这不是一颗真实恒星。仅观测时间取自真实数据，亮度由固定公式和随机种子生成。测量与模拟仪器通道均保存在输入 NPZ 中。</p>'
        if row["kind"] == "synthetic_equal_eclipses":
            body += '<p>生成时设定的绕转周期里有两次完全相同的食。亮度实际每半圈重复一次，因此仅凭这份光变不能唯一确定完整绕转周期。下表的“半周期”不能直接当作错误的亮度周期。</p>'
        if row["kind"] == "synthetic_common_mode":
            body += '<p>输入中没有恒星自身的周期变化。目标与辅助仪器通道共享同一个模拟周期信号。现有初筛不使用辅助通道，因而可能留下候选；即便周期算对，也没有认对来源。</p>'
        if not row["observations"]:
            body += f'<p>{escape(row.get("reason", "没有可分析观测"))}</p>'
        for obs in row["observations"]:
            body += f'<h2>观测时段 {obs["sector"]}</h2><p>LS 候选：{obs["period_d"]:.8f} 天；BLS 候选：{obs["bls"]["period_d"]:.8f} 天。</p>'
            body += f'<img src="{Path(obs["plot"]).name}" alt="亮度随时间、周期评分和 LS 相位图">'
            if "evaluation" in obs:
                evaluation = obs["evaluation"]
                body += f'<p>参考周期 {evaluation["reference_period_d"]:.8f} 天。LS：{PERIOD[evaluation["ls"]]}；BLS：{PERIOD[evaluation["bls"]]}。比较容差不是测量误差。</p>'
                if row["kind"] == "synthetic_equal_eclipses":
                    body += f'<p>亮度重复周期为 {evaluation["photometric_reference_d"]:.8f} 天；按它比较，LS：{PERIOD[evaluation["ls_photometric"]]}；BLS：{PERIOD[evaluation["bls_photometric"]]}。</p>'
                p = comparison(out, row, obs, result["analysis_config"]["bin_minutes"])
                plots.append({"path": str(p.relative_to(out)), "sha256": sha256(p)})
                body += f'<img src="{p.name}" alt="同一数据按 LS、BLS、已知参考周期折叠"><p>三图只改变摆放数据的周期。参考答案只用于此处解释，不曾输入周期搜索。</p>'
            if "auxiliary_correlation" in obs:
                body += f'<p>目标与模拟仪器通道的相关系数为 {obs["auxiliary_correlation"]:.3f}（越接近 1 越同步）。这是额外诊断，现有初筛没有使用。</p>'
        if "localization" in row:
            loc = row["localization"]
            name = loc.get("possible_contaminant", {}).get("name", "待核实")
            body += f'<h2>来源检查</h2><p>结果：{STATUS.get(loc["status"], loc["status"])}。对应邻星：{escape(name)}。这是以前看过的开发案例，不是独立验证。</p><img src="pixels.png" alt="目标与邻星的像素信号位置">'
        if row["errors"]:
            body += f'<pre>{escape(str(row["errors"]))}</pre>'
        body += '<p><a href="case.json">完整机器结果与输入记录</a></p>'
        (folder/"index.html").write_text(page(row["id"], body))
    metrics = result["metrics"]["by_kind"]
    body = '<h1>这一轮识别测试：有用，但还不够可靠</h1><div class="notice">这是开发诊断，包含 36 个预先固定的案例；34 个完成，2 个因数据格式不可用而保留。没有开展新变星发现，没有独立封存测试，也没有已核实的真实安静恒星反例。</div>'
    body += '<p>“留下候选”表示现有程序觉得两个时段的周期相近，需要继续检查。它不表示变星已经确认；没留下候选也不表示恒星不变。</p>'
    body += '<table><tr><th>输入类型</th><th>完成 / 清单数</th><th>留下候选数</th><th>应怎样理解</th></tr>'
    notes = {"real_known_variable": "3 颗均检出；另外 2 颗不可用。普通搜索仍有半周期。",
             "real_contaminated_target": "像素检查后，2 个都标为疑似污染；开发旧例的重现。",
             "synthetic_white_noise": "这 6 个没有误报，不能代表所有真实噪声。",
             "synthetic_correlated_noise": "这 6 个没有误报，真实系统效应仍更复杂。",
             "synthetic_trend": "1 个非周期漂移被误报。",
             "synthetic_sinusoid": "全被检出；检出不等于每段周期都在 1% 容差内。",
             "synthetic_unequal_eclipses": "漏掉 2 个；被留下的 2 个，普通搜索均选了半周期。",
             "synthetic_equal_eclipses": "亮度每半圈重复；不能凭完全一样的两次食唯一确定绕转周期。",
             "synthetic_common_mode": "3 个仪器干扰全部进入候选，来源不能靠周期一致确定。"}
    for kind, m in metrics.items():
        body += f'<tr><td>{KINDS[kind]}</td><td>{m["completed"]} / {m["cases"]}</td><td>{m["candidate_alerts"]}</td><td>{notes[kind]}</td></tr>'
    body += '</table><h2>最值得看懂的三个失败</h2><ul><li><a href="trend-02/index.html">缓慢漂移被误报</a>：亮度一直在缓慢上升，没有周期；程序却在两段数据中都找到了约 6.74 天的峰。只有跨时段周期一致这条规则不够。</li><li><a href="unequal_eclipses-04/index.html">6.2 天的食双星被漏掉</a>：辅助 BLS 在两个时段都找到正确周期，但初筛仍只比较 LS，因此没有留下候选。</li><li><a href="common_mode-01/index.html">仪器周期通过初筛</a>：模拟仪器通道与测得亮度同步变化，初筛没有读取这条线索。</li></ul>'
    body += '<h2>周期有没有选对</h2><p>真实已知星：普通 LS 搜索在 6 段观测中有 4 段符合参考、2 段为半周期；BLS 为 6 段符合。按星统计，LS 是 2 / 3 颗的所有时段都符合，BLS 是 3 / 3。两种算法还没有自动合成一个最终答案。</p><p>模拟深浅不同的食：8 段观测中，BLS 有 5 段符合绕转周期、3 段选了半周期；按案例计，仅 2 / 4 个在两段都恢复绕转周期。可见把 BLS 的输出一律当作最终周期也不行。</p>'
    body += '<h2>我们还缺什么</h2><p>需要把食形搜索纳入候选判断，比较完整周期与半周期，并加强对漂移、相关噪声和来源的检验。改进先在开发集检查，再用没有看过答案的独立测试集验证。真实安静星目前为 0 颗，因此真实误报率仍然未知。</p>'
    body += '<p>配套教学：<a href="../source-9473243-v01/index.html">TU Her 两个时段的变光位置检查</a> · <a href="../../tutorials/first-variable-star/index.html">亲手操作光变练习</a> · <a href="../../../doc/12-mixed-validation-results.md">通俗结果解读与下一步</a></p>'
    body += '<h2>全部案例</h2><table><tr><th>案例</th><th>类型</th><th>最后处理</th></tr>'
    for r in result["results"]:
        status = STATUS.get(r.get("baseline_status", r["status"]), r["status"])
        body += f'<tr><td><a href="{r["id"]}/index.html">{r["id"]}</a></td><td>{KINDS[r["kind"]]}</td><td>{status}</td></tr>'
    body += '</table><p><a href="results.json">完整 JSON</a> · <a href="results.csv">CSV 汇总</a> · <a href="input-manifest.json">冻结输入与校验值</a> · <a href="../mixed-protocol-v01.json">运行前的测试方案</a></p>'
    (out/"index.html").write_text(page("变星识别混合测试", body))
    write_json(out/"report-provenance.json", {"results_sha256": sha256(out/"results.json"), "renderer_sha256": sha256(Path(__file__)),
                                             "comparison_plots": plots, "note": "Post-evaluation display; reference periods used only for plotting, no new selection or thresholds."})
    print(out/"index.html")


if __name__ == "__main__":
    main()
