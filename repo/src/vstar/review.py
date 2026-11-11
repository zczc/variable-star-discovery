"""Opt-in v2 review of supplied light curves; never declares or submits a discovery."""
from dataclasses import asdict
from pathlib import Path
from html import escape
import numpy as np
from astropy.io import fits
from .models import AnalysisConfig
from .io import read_json, write_json, code_fingerprint, sha256, now
from .photometry import LightCurve, read_lightcurve, bin_lightcurve
from .periods import analyze_series
from .screening import ScreeningConfig, analyze_epoch, detrend, template_score, check_auxiliary, combine_epochs
from .auxiliary import read_auxiliary
from .localization import localize
from .reports import page
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


DECISIONS = {"no_stable_signal": "未建立稳定周期", "not_repeated_in_all_epochs": "并非所有时段都支持重复变化",
             "insufficient_epochs": "观测时段不足", "competing_periods": "不同观测时段的周期仍有分歧",
             "period_ambiguous": "亮度重复，完整绕转周期有歧义", "periodic_source_unchecked": "有重复信号，来源尚未充分检查",
             "periodic_target_supported": "周期与基础定位支持目标，仍待复核", "likely_contaminated": "疑似邻星污染",
             "source_caution": "存在来源疑点，保留人工复核"}


def review_epoch(raw, sap=None, auxiliary=None, baseline=None, analysis=None, config=None):
    analysis, config = analysis or AnalysisConfig(use_bls=True), config or ScreeningConfig()
    if baseline is None:
        baseline, _ = analyze_series(raw, analysis, sap if sap is not None else raw)
    result, diagnostic = analyze_epoch(raw, baseline, analysis, config)
    if result["periodic_detected"]:
        period = result["photometric_period_d"]
        result["auxiliary"] = check_auxiliary(diagnostic[1], auxiliary or {}, period, config)
        if sap is not None:
            sap_clean, _ = detrend(bin_lightcurve(sap, analysis.bin_minutes))
            result["sap_check"] = template_score(sap_clean, period, config)
        else:
            result["sap_check"] = {"status": "not_independently_available"}
    return result, diagnostic, baseline


def plot_review(diagnostic, result, path):
    raw, clean, trend = diagnostic
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5), layout="constrained")
    axes[0].plot(raw.time-raw.time.min(), raw.flux*100, ".", ms=1.5, alpha=.5)
    axes[0].plot(raw.time-raw.time.min(), trend*100, "r-", lw=1)
    axes[0].set(title="Measured flux and quadratic baseline", xlabel="Days from start", ylabel="Relative flux (%)")
    period = result["photometric_period_d"] or result["candidates"][0]["period_d"]
    for ax, p in zip(axes[1:], [period, 2*period]):
        ax.plot(((clean.time-clean.time.min())/p) % 1, clean.flux*100, ".", ms=1.5, alpha=.5)
        ax.set(title=f"P = {p:.7f} d", xlabel="Phase (arbitrary zero)")
    fig.suptitle("Development diagnostic: preferred cycle and doubled cycle; no physical classification")
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_case_report(folder, row):
    conclusion = row.get("conclusion", {})
    body = f'<h1>{escape(row["id"])}</h1><p>{DECISIONS.get(conclusion.get("decision"), "数据不足或分析失败")}</p>'
    body += '<div class="notice">第二版开发结果。检出周期、选择完整亮度周期、判断来源是三件事；这里没有确认新变星。</div>'
    if row.get("errors"):
        body += f'<pre>{escape(str(row["errors"]))}</pre>'
    if conclusion.get("photometric_period_d"):
        body += f'<p>亮度重复周期约 {conclusion["photometric_period_d"]:.8f} 天。'
        body += '仍保留完整绕转周期的歧义。</p>' if conclusion["selected_period_d"] is None else '这是优选亮度周期，未给出正式误差或物理分类。</p>'
    for obs in row.get("observations", []):
        result = obs["v2"]
        body += f'<h2>观测时段 {obs["sector"]}</h2><p>第二版周期：{result["photometric_period_d"]} 天；状态：{escape(result["period_status"])}。</p>'
        body += f'<img src="{obs["plot"]}" alt="原始变化及按优选周期和两倍周期折叠后的图"><p>左图红线是缓慢基线；右面两图去除该基线。若未通过周期要求，两图只展示得分最高的竞争解释。</p>'
        body += '<table><tr><th>竞争周期（天）</th><th>交替周期预测改善</th><th>两组各自改善</th><th>通过初筛</th></tr>'
        for c in result["candidates"][:8]:
            body += f'<tr><td>{c["period_d"]:.7f}</td><td>{c["gain"]:.1%}</td><td>{c["fold_gains"][0]:.1%} / {c["fold_gains"][1]:.1%}</td><td>{"是" if c["qualifies"] else "否"}</td></tr>'
        body += '</table><p>“预测改善”衡量用一组周期的形状预测另一组，比只有缓慢基线好多少；负数表示更差。搜索和预测共用了资料，因此这不是可信概率，也不是独立验证。</p>'
        channels = result.get("auxiliary", [])
        if channels:
            body += '<p>辅助数据检查：背景 SAP_BKG、指向修正 POS_CORR、亮斑中心 MOM_CENTR，或明确提供的仪器通道。</p><ul>'
            for a in channels:
                body += f'<li>{escape(a["name"])}：{escape(a["status"])}'
                if "correlation" in a:
                    body += f'，相关系数 {a["correlation"]:.3f}'
                body += '</li>'
            body += '</ul><p>相关性只提示需要检查来源。恒星自身变暗也可能导致亮斑中心移动，不能据此断定是仪器。</p>'
    for evidence in conclusion.get("source_evidence", []):
        if "plot" in evidence:
            body += f'<img src="{escape(evidence["plot"])}" alt="探索性像素信号定位">'
    body += '<p><a href="case.json">完整结果与理由</a></p>'
    (folder/"index.html").write_text(page(row["id"], body))


def review_files(paths, out, neighbors=None):
    out = out.resolve(); out.mkdir(parents=True, exist_ok=False)
    analysis, config = AnalysisConfig(use_bls=True), ScreeningConfig()
    row = {"id": "Supplied light-curve review", "created_at": now(), "code_fingerprint": code_fingerprint(),
           "analysis_config": asdict(analysis), "screening_config": asdict(config), "observations": [], "errors": []}
    evidence, identities, sectors = [], set(), set()
    for path in paths:
        path = path.resolve()
        try:
            raw, sap = read_lightcurve(path), read_lightcurve(path, "SAP_FLUX")
            identity, sector = raw.metadata["TICID"], raw.metadata["SECTOR"]
            identities.add(identity)
            if len(identities) != 1 or sector in sectors:
                raise ValueError("Supply different sectors of the same TIC; duplicates are not independent epochs")
            sectors.add(sector)
            result, diagnostic, baseline = review_epoch(raw, sap, read_auxiliary(path), analysis=analysis, config=config)
            plot = f"sector-{sector}.png"; plot_review(diagnostic, result, out/plot)
            row["observations"].append({"sector": sector, "input": {"path": str(path), "sha256": sha256(path)}, "baseline": baseline, "v2": result, "plot": plot})
            pixels = path.with_name(path.name.replace("_lc.fits", "_tp.fits"))
            if pixels != path and pixels.is_file() and result["periodic_detected"]:
                with fits.open(path) as h:
                    target = {"ra_deg": h[0].header["RA_OBJ"], "dec_deg": h[0].header["DEC_OBJ"], "vsx_neighbors": neighbors or []}
                pixelplot = f"sector-{sector}-pixels.png"
                source = localize(pixels, path, target, result["photometric_period_d"], out/pixelplot)
                source.update(sector=sector, plot=pixelplot, input_sha256=sha256(pixels)); evidence.append(source)
        except Exception as exc:
            row["errors"].append({"path": str(path), "error": str(exc)})
    row["conclusion"] = combine_epochs([o["v2"] for o in row["observations"]], config, evidence)
    if row["errors"]:
        row["conclusion"].update(decision="failed", periodic_detected=False, selected_period_d=None, target_candidate=False)
    write_json(out/"case.json", row); write_case_report(out, row)
    return row
