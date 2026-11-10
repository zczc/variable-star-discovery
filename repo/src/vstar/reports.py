from html import escape
from pathlib import Path
import csv
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .io import read_json


LABELS = {"periodic_candidate": "周期候选，仍待验证", "inconclusive": "证据不足或周期不一致",
          "catalog_match_unverified": "历史目录近邻匹配，身份待核实", "failed": "分析失败，需重试",
          "likely_contaminated": "疑似邻星污染", "known_variable": "已有变星记录"}
NOVELTY = {"incomplete": "查重未完成", "nearby_catalog_match_needs_identity_review": "近位置有目录记录，身份待核实"}
STYLE = """body{font:16px/1.65 system-ui,sans-serif;max-width:1150px;margin:32px auto;padding:0 20px;color:#24334a;background:#f5f7fa}h1,h2{line-height:1.25}a{color:#1657a1}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:10px;border-bottom:1px solid #dde3ed}th{background:#e9eff7}img{max-width:100%;background:white}article,.notice{background:white;padding:20px;margin:20px 0;border:1px solid #dbe2ed;border-radius:8px}input{padding:10px;width:320px;max-width:90%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.muted{color:#5d6c80}code{font-size:.9em}"""


def page(title, body):
    return f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{STYLE}</style><body>{body}</body></html>'


def period_note(obs):
    notes = []
    if obs.get("period_at_search_boundary"):
        notes.append("最强峰位于搜索边界，尚未测得有界周期。")
    alternative = obs.get("bls", {}).get("period_d")
    if alternative:
        ratio = alternative / obs["period_d"]
        if abs(ratio - 1) < .01:
            notes.append("两种搜索得到相近周期；1% 比较容差不是周期误差。")
        elif abs(ratio / 2 - 1) < .01 or abs(ratio / .5 - 1) < .01:
            notes.append("两种搜索相差约两倍，存在半周期或双周期歧义，需要复核。")
        else:
            notes.append("两种搜索周期不同，尚未自动决定采用哪一个。")
    else:
        notes.append("未运行 BLS 辅助搜索。")
    return " ".join(notes)


def plot_observation(diagnostic, result, path: Path):
    lc, freq, power = diagnostic
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5), layout="constrained")
    axes[0].plot(lc.time - lc.time.min(), lc.flux * 100, ".", ms=2, alpha=.6)
    axes[0].set(xlabel="Days since sector start", ylabel="Relative flux (%)", title="Quality-filtered, binned light curve")
    axes[1].plot(1 / freq, power, lw=.7)
    axes[1].set(xlabel="Period (days)", ylabel="Lomb-Scargle power", xscale="log", title="Screening periodogram")
    phase = (lc.time % result["period_d"]) / result["period_d"]
    axes[2].plot(phase, lc.flux * 100, ".", ms=2, alpha=.5)
    axes[2].set(xlabel="Phase (arbitrary zero)", ylabel="Relative flux (%)", title=f'P = {result["period_d"]:.6f} d')
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def generate_report(root: Path):
    summary = read_json(root / "summary.json")
    rows = summary["targets"]
    out = root / "report"
    out.mkdir(exist_ok=True)
    table = []
    for row in rows:
        tic = row["tic"]
        observations = row["results"]
        period = observations[-1]["period_d"] if observations else None
        period_text = f"{period:.6f}" if period is not None else "—"
        status = LABELS.get(row["status"], row["status"])
        alternative = observations[-1].get("bls", {}).get("period_d") if observations else None
        alternative_text = f"{alternative:.6f}" if alternative is not None else "—"
        novelty = NOVELTY.get(row["novelty"], row["novelty"])
        table.append(f'<tr><td><a href="{tic}.html">TIC {tic}</a></td><td>{escape(status)}</td><td>{len(observations)}</td><td>{period_text}</td><td>{alternative_text}</td><td>{escape(novelty)}</td></tr>')
        sections = [f'<p><a href="index.html">← 返回总览</a></p><h1>TIC {tic}</h1>',
                    f'<div class="notice"><strong>{escape(status)}</strong><p>这是筛选报告，未确认新发现，也不能代替 VSX 提交材料。</p></div>',
                    '<h2>当前判断</h2><ul>' + ''.join(f'<li>{escape(str(x))}</li>' for x in row["reasons"]) + '</ul>',
                    '<p>图中依次为亮度随时间变化、候选周期强度和折叠后的重复形状。相位零点仅供展示；纵轴是相对通量，不是标定星等。</p>']
        for obs in observations:
            bls = obs.get("bls", {}).get("period_d")
            bls_text = f"{bls:.6f} 天" if bls is not None else "未运行"
            sections.append(f'<article><h2>Sector {obs["sector"]} · LS {obs["period_d"]:.6f} 天</h2><p>BLS 辅助周期：{bls_text}</p><p>{period_note(obs)}</p><p>前半段 LS：{obs["first_period"]:.6f} 天；后半段 LS：{obs["second_period"]:.6f} 天。</p><p>相对幅度估计 {obs["phase_amplitude_pct"]:.4f}% · 有效点数 {obs["n"]}</p><img src="../{escape(obs["plot"], quote=True)}" alt="光变、周期图和 LS 相位图"><p class="muted">{escape(" ".join(obs["warnings"]))}</p></article>')
        if row.get("pixel_plot"):
            sections.append(f'<h2>探索性来源定位</h2><img src="../{escape(row["pixel_plot"], quote=True)}" alt="像素信号定位"><p>像素峰值诊断不能替代精细来源拟合或正式查找星图。</p>')
        details = {k: row.get(k) for k in ["ra_deg", "dec_deg", "catalog_queries", "vsx_neighbors", "notes", "errors", "repeatability", "localization", "submission"]}
        sections.append('<h2>来源、检查缺口和原始记录</h2><pre>' + escape(json.dumps(details, ensure_ascii=False, indent=2)) + '</pre>')
        (out / f"{tic}.html").write_text(page(f"TIC {tic}", ''.join(sections)), encoding="utf-8")
    body = f'<h1>变星候选分析</h1><p class="muted">运行 {escape(root.name)} · {escape(summary["created_at"])}</p><div class="notice">共 {len(rows)} 个目标，{sum(len(r["results"]) for r in rows)} 份光变分析。当前没有确认的新发现。目录查询与来源核验不完整的对象均不能标为可提交。</div><p><input id="filter" placeholder="搜索 TIC、状态或周期" aria-label="筛选目标"></p><table><thead><tr><th>目标</th><th>结论</th><th>观测区数</th><th>最近 LS 周期（天）</th><th>最近 BLS 周期（天）</th><th>查重</th></tr></thead><tbody>{"".join(table)}</tbody></table><p><a href="../summary.csv">下载 CSV</a> · <a href="../summary.json">完整 JSON</a></p><script>document.querySelector("#filter").addEventListener("input",e=>document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase())));</script>'
    (out / "index.html").write_text(page("变星候选分析", body), encoding="utf-8")
    with (root / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tic", "status", "sectors", "period_d", "bls_period_d", "period_note", "novelty", "reasons"], lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({"tic": r["tic"], "status": r["status"], "sectors": len(r["results"]),
                             "period_d": r["results"][-1]["period_d"] if r["results"] else "",
                             "bls_period_d": r["results"][-1].get("bls", {}).get("period_d", "") if r["results"] else "",
                             "period_note": period_note(r["results"][-1]) if r["results"] else "",
                             "novelty": r["novelty"], "reasons": " | ".join(r["reasons"])})
    return out / "index.html"
