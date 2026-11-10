"""Analyze known targets with fixed parameters, then compare independently supplied periods."""
import argparse
from collections import Counter
from pathlib import Path
import csv
import json
from vstar.io import now, read_json, write_json, code_fingerprint
from vstar.network import ArchiveClient
from vstar.models import AnalysisConfig
from vstar.periods import analyze
from vstar.reports import plot_observation


def classify_period(measured, truth, tolerance):
    if abs(measured / truth - 1) < tolerance:
        return "correct_period"
    if abs(measured / truth / .5 - 1) < tolerance:
        return "half_period"
    if abs(measured / truth / 2 - 1) < tolerance:
        return "double_period"
    return "not_recovered"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("repo/benchmarks/known-v01"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    truth = read_json(Path(__file__).with_name("known-controls.json"))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    client = ArchiveClient(root / "repo/data/known-controls", offline=args.offline)
    config = AnalysisConfig(use_bls=True)
    output = {"created_at": now(), "code_fingerprint": code_fingerprint(), "truth": truth,
              "evaluation": "Fixed 1% relative tolerance; half/double periods reported as errors, not exact recovery. No population accuracy estimate.", "results": [], "errors": []}
    write_json(out / "results.json", output)
    for target in truth["targets"]:
        try:
            filters = [{"paramName": "obs_collection", "values": ["TESS"]}, {"paramName": "dataproduct_type", "values": ["timeseries"]},
                       {"paramName": "provenance_name", "values": ["SPOC"]}, {"paramName": "target_name", "values": [target["tic"]]}]
            rows, receipts = client.mast_rows(filters)
            sectors = {int(r["sequence_number"]): r for r in rows if r.get("dataURL", "").endswith("_lc.fits") and "_fast" not in r["dataURL"]}
            if not sectors:
                raise ValueError("No non-fast SPOC light curves available; target remains an unavailable control")
            chosen = [sectors[s] for s in sorted(set([min(sectors), max(sectors)]))]
            write_json(out / (target["tic"] + "-observations.json"), {"selected": chosen, "receipts": receipts})
            for row in chosen:
                path, digest = client.download(row["dataURL"])
                # No reference period or variability type is passed into the analysis.
                result, diagnostic = analyze(path, config)
                stem = f'{target["tic"]}-s{row["sequence_number"]:04d}'
                plot_observation(diagnostic, result, out / (stem + ".png"))
                write_json(out / (stem + ".json"), result)
                evaluation = {"tic": target["tic"], "name": target["name"], "sector": row["sequence_number"],
                              "reference_period_d": target["period_d"], "ls_period_d": result["period_d"], "bls_period_d": result["bls"]["period_d"],
                              "ls_result": classify_period(result["period_d"], target["period_d"], truth["relative_period_tolerance"]),
                              "bls_result": classify_period(result["bls"]["period_d"], target["period_d"], truth["relative_period_tolerance"]),
                              "uri": row["dataURL"], "sha256": digest, "plot": stem + ".png"}
                output["results"].append(evaluation)
                print(json.dumps(evaluation), flush=True)
                write_json(out / "results.json", output)
        except Exception as exc:
            output["errors"].append({"tic": target["tic"], "error": str(exc)})
            print(target["tic"], "FAILED", str(exc), flush=True)
            write_json(out / "results.json", output)
    output["counts"] = {method: dict(Counter(r[method + "_result"] for r in output["results"])) for method in ["ls", "bls"]}
    output["completed_at"] = now()
    write_json(out / "results.json", output)
    with (out / "results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        keys = ["tic", "name", "sector", "reference_period_d", "ls_period_d", "ls_result", "bls_period_d", "bls_result"]
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(output["results"])
    lines = ["# 已知变星周期对照", "", "参数在分析前固定；目录周期不传入算法。下表按 1% 相对差比较，半周期和双周期单独列为错误。", "",
             "| 对象 | 观测区 | 参考周期（天） | LS 周期 | LS 结果 | BLS 周期 | BLS 结果 |", "|---|---|---|---|---|---|---|"]
    for r in output["results"]:
        lines.append(f'| {r["name"]} | {r["sector"]} | {r["reference_period_d"]:.8f} | {r["ls_period_d"]:.8f} | {r["ls_result"]} | {r["bls_period_d"]:.8f} | {r["bls_result"]} |')
    lines += ["", "## 数量与局限", "", json.dumps(output["counts"], ensure_ascii=False), "",
              "这是一组特意选择的已知正例，其中包括目录曾给错周期的食双星。多个观测区不等于多个独立恒星。结果不能换算为总体准确率、假阳性率或新发现概率。",
              "误差与不可用目标：", json.dumps(output["errors"], ensure_ascii=False), ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print("BENCHMARK_COMPLETE", json.dumps(output["counts"]), "errors", len(output["errors"]), flush=True)


if __name__ == "__main__":
    main()
