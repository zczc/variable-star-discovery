"""Render saved control results and compare LS/BLS folds without repeating the search."""
import argparse
from collections import Counter
from html import escape
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from vstar.io import read_json, sha256
from vstar.photometry import read_lightcurve, bin_lightcurve
from vstar.reports import page


LABELS = {"correct_period": "参考周期附近", "half_period": "误判为半周期",
          "double_period": "误判为双周期", "not_recovered": "未恢复参考周期"}


def build(root, cache):
    saved = read_json(root / "results.json")
    counts = {method: Counter(r[method + "_result"] for r in saved["results"]) for method in ["ls", "bls"]}
    stars = len({r["tic"] for r in saved["results"]})
    count = len(saved["results"])
    output = root / "report"
    output.mkdir(exist_ok=True)
    table, sections = [], []
    for result in saved["results"]:
        name = escape(result["name"])
        stem = f'{result["tic"]}-s{result["sector"]:04d}'
        table.append(f'<tr><td><a href="#{stem}">{name}</a></td><td>{result["sector"]}</td>'
                     f'<td>{result["reference_period_d"]:.8f}</td>'
                     f'<td>{result["ls_period_d"]:.8f}<br>{LABELS[result["ls_result"]]}</td>'
                     f'<td>{result["bls_period_d"]:.8f}<br>{LABELS[result["bls_result"]]}</td></tr>')
        path = cache / "fits" / result["uri"].rsplit("/", 1)[-1]
        if sha256(path) != result["sha256"]:
            raise ValueError(f"Control input changed: {path.name}")
        # Display the original 10-minute bins; neither method uses the reference period.
        lc = bin_lightcurve(read_lightcurve(path), saved.get("analysis_config", {}).get("bin_minutes", 10))
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.5), layout="constrained", sharey=True)
        for ax, method in zip(axes, ["ls", "bls"]):
            period = result[method + "_period_d"]
            phase = (lc.time % period) / period
            ax.plot(phase, 100 * lc.flux, ".", ms=2, alpha=.5)
            ax.set(xlabel="Phase (arbitrary zero)", title=f"{method.upper()}: {period:.6f} days")
            ax.grid(alpha=.2)
        axes[0].set_ylabel("Relative flux (%)")
        fig.suptitle(f'{result["name"]} / Sector {result["sector"]} / Reference: {result["reference_period_d"]:.8f} d')
        fig.savefig(output / (stem + ".png"), dpi=130)
        plt.close(fig)
        sections.append(f'<article id="{stem}"><h2>{name} · Sector {result["sector"]}</h2>'
                        f'<img src="{stem}.png" alt="LS 与 BLS 各自周期的相位折叠图">'
                        '<p>左右图使用同一份观测，按两种算法各自算出的周期折叠。相位零点任意，纵轴是相对通量。</p></article>')
    unavailable = ''.join(f'<li>TIC {escape(e["tic"])}：{escape(e["error"])}</li>' for e in saved["errors"])
    references = ''.join(f'<li>{escape(t["name"])}：<a href="{escape(t["source"], quote=True)}">参考来源</a></li>'
                         for t in saved["truth"]["targets"])
    body = ('<h1>用已知变星检查周期识别</h1>'
            f'<div class="notice">预选 {len(saved["truth"]["targets"])} 颗已知变星，取得其中 {stars} 颗、共 {count} 个观测时段的数据。'
            f'普通 LS 搜索得到参考周期附近结果 {counts["ls"]["correct_period"]} 段、半周期 {counts["ls"]["half_period"]} 段；'
            f'辅助 BLS 搜索得到参考周期附近结果 {counts["bls"]["correct_period"]} 段。'
            '这不表示程序已经能自动选对周期，也不是总体准确率。</div>'
            '<p>目录给出的周期相当于参考答案。先固定目标和参数，让程序只看观测数据，计算完成后才对答案。'
            f'本次用 {saved["truth"]["relative_period_tolerance"]:.0%} 的相对差作为比较容差；半周期和双周期算作错误。</p>'
            '<table><thead><tr><th>对象</th><th>观测区</th><th>参考周期（天）</th><th>LS 结果（天）</th><th>BLS 结果（天）</th></tr></thead>'
            f'<tbody>{"".join(table)}</tbody></table>'
            '<p>食双星每圈可能发生两次亮度下降，LS 容易把间隔当成完整周期。BLS 会寻找反复出现的亮度下降，'
            '但也可能遇到半周期、倍周期或其他错误；本例不能证明它总是更准。</p>'
            '<p>仍缺更多类型、幅度的目标，以及噪声和稳定星对照。这里只测试周期恢复，未验证自动分类、信号来源或新发现资格。'
            'RR Lyr 的 TIC 星等字段存在冲突，具体身份核对与局限见上一层 README。</p>'
            f'<h2>未取得支持格式数据的对象</h2><ul>{unavailable}</ul>'
            + ''.join(sections) + f'<h2>参考记录</h2><ul>{references}</ul>'
            '<p><a href="../results.csv">数值 CSV</a> · <a href="../results.json">结果和数据来源 JSON</a></p>')
    path = output / "index.html"
    path.write_text(page("已知变星周期对照", body), encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=Path("repo/benchmarks/known-v01"))
    parser.add_argument("--cache", type=Path, default=Path("repo/data/known-controls"))
    args = parser.parse_args()
    print(build(args.run.resolve(), args.cache.resolve()))
