"""Evaluate development v3, including the former six-star pilot; raw predictions are saved before reference scoring."""
import argparse
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import csv
import json
import subprocess
import time
import numpy as np
from vstar.io import read_json, write_json, sha256, now, code_fingerprint
from vstar.models import AnalysisConfig
from vstar.photometry import LightCurve, read_lightcurve, bin_lightcurve
from vstar.auxiliary import read_auxiliary
from vstar.screening_v3 import ScreeningConfig, combine_epochs
from vstar.review import review_epoch, plot_review, write_case_report
from vstar.pipeline import assess
from vstar.localization import localize
from simulate_controls import as_lightcurve
from run_known_controls import classify_period

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT/"repo/benchmarks"


def verified(item):
    path = ROOT/item["path"]
    if sha256(path) != item["sha256"]:
        raise ValueError(f"Changed input: {path}")
    return path


def development_inputs():
    manifest = read_json(BENCH/"mixed-v01/input-manifest.json")
    rows = manifest["cases"]
    old = {r["id"]: r for r in read_json(BENCH/"mixed-v01/results.json")["results"]}
    source = read_json(BENCH/"source-9473243-v01/input-manifest.json")
    identity = read_json(BENCH/"source-9473243-v01/results.json")
    for r in rows:
        r["kind"] = old[r["id"]]["kind"]
        r["old_candidate_alert"] = old[r["id"]]["candidate_alert"]
        r["baseline_observations"] = old[r["id"]]["observations"]
        if r["id"] == "known-9473243":
            r["pixel_inputs"] = [dict(o["pixels"], sector=o["sector"]) for o in source["observations"]]
            r["target"] = {"ra_deg": identity["target"]["ra"], "dec_deg": identity["target"]["dec"], "vsx_neighbors": identity["vsx"]["neighbors"]}
        elif "pixels" in r:
            r["pixel_inputs"] = [r["pixels"]]
    return rows, [BENCH/"mixed-v01/input-manifest.json", BENCH/"mixed-v01/results.json", BENCH/"source-9473243-v01/input-manifest.json", BENCH/"source-9473243-v01/results.json"]


def score(rows, mode):
    if mode == "development":
        protocol = {c["id"]: c for c in read_json(BENCH/"mixed-protocol-v01.json")["cases"]}
        known = {c["tic"]: c["period_d"] for c in read_json(BENCH/"known-controls.json")["targets"]}
        for row in rows:
            case = protocol[row["id"]]
            reference = known.get(case.get("tic")) if case["kind"] == "real_known_variable" else case.get("period_d")
            row["reference"] = {"period_d": reference, "photometric_period_d": reference*case.get("photometric_period_fraction", 1) if reference else None}
    else:
        refs = {c["id"]: c for c in read_json(BENCH/"independent-pilot-v01/input-manifest.json")["cases"]}
        for row in rows:
            row["reference"] = refs[row["id"]].get("reference", {"period_d": None, "photometric_period_d": None})
    for row in rows:
        ref = row["reference"]
        conclusion = row.get("conclusion", {})
        selected, photo = conclusion.get("selected_period_d"), conclusion.get("photometric_period_d")
        row["score"] = {
            "preferred_cycle": classify_period(selected, ref["period_d"], .01) if selected and ref["period_d"] else "abstained_or_unscored",
            "photometric_cycle": classify_period(photo, ref["photometric_period_d"], .01) if photo and ref["photometric_period_d"] else "abstained_or_unscored"}
    groups = {}
    for kind in dict.fromkeys(r["kind"] for r in rows):
        group = [r for r in rows if r["kind"] == kind]
        groups[kind] = {"cases": len(group), "completed": sum(r["status"] == "completed" for r in group),
                        "unavailable": sum(r["status"] == "unavailable" for r in group), "failed": sum(r["status"] == "failed" for r in group),
                        "old_candidate_alerts": sum(r.get("old_candidate_alert") is True for r in group),
                        "periodic_detected": sum(r.get("conclusion", {}).get("periodic_detected", False) for r in group),
                        "target_candidates": sum(r.get("conclusion", {}).get("target_candidate", False) for r in group),
                        "decisions": dict(Counter(r.get("conclusion", {}).get("decision", r["status"]) for r in group)),
                        "preferred_cycle_results": dict(Counter(r["score"]["preferred_cycle"] for r in group)),
                        "photometric_cycle_results": dict(Counter(r["score"]["photometric_cycle"] for r in group))}
    return groups


def evaluate(mode, out, protocol_path):
    out.mkdir(parents=True, exist_ok=False)
    protocol = read_json(protocol_path)
    analysis, config = AnalysisConfig(**protocol["analysis"]), ScreeningConfig(**protocol["screening"])
    if mode == "development":
        cases, sources = development_inputs()
    else:
        path = BENCH/"independent-pilot-v01/input-manifest.json"
        cases, sources = read_json(path)["cases"], [path, BENCH/"independent-pilot-protocol-v01.json"]
        previous = {r["id"]: r for r in read_json(BENCH/"independent-pilot-v01/evaluation/results.json")["results"]}
        for case in cases:
            case["baseline_observations"] = [dict(o["baseline"], sector=o["sector"]) for o in previous[case["id"]]["observations"]]
        sources.append(BENCH/"independent-pilot-v01/evaluation/results.json")
    output = {"algorithm_revision": "v3.0-development", "schema_note": "The observation key v2 is retained for report compatibility; algorithm_revision identifies the actual method.", "created_at": now(), "complete": False, "mode": mode, "code_fingerprint": code_fingerprint(),
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "runner_sha256": sha256(Path(__file__)), "protocol_sha256": sha256(protocol_path), "protocol_path": str(protocol_path.relative_to(ROOT)),
              "analysis": asdict(analysis), "screening": asdict(config),
              "sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p)} for p in sources], "results": [],
              "limitations": ["All cases in this run are development data, including the previously independent pilot.",
                              "Development rules; cross-cycle scores are not false-alarm probabilities.",
                              "Source cautions are review requests, not proof of instrumental causes.",
                              "Zero labeled quiet real-star controls: real false-positive rate unavailable."]}
    start = time.monotonic()
    for case in cases:
        folder = out/case["id"]; folder.mkdir()
        row = {"id": case["id"], "kind": case["kind"], "observations": [], "errors": list(case.get("errors", [])),
               "old_candidate_alert": case.get("old_candidate_alert"), "status": "completed"}
        evidence = []
        if "unavailable_reason" in case:
            row.update(status="unavailable", unavailable_reason=case["unavailable_reason"])
        else:
            for item in case["inputs"]:
                try:
                    path = verified(item)
                    baseline = next((b for b in case.get("baseline_observations", []) if b["sector"] == item["sector"]), None)
                    # Do not pass old evaluation, labels or reference periods to analysis.
                    baseline = {k: baseline[k] for k in ["period_d", "bls", "peaks", "period_at_search_boundary"]} if baseline else None
                    if path.suffix == ".npz":
                        with np.load(path) as arrays:
                            raw = as_lightcurve(arrays, {})
                            auxiliary = {}
                            if len(arrays["auxiliary"]):
                                channel = LightCurve(arrays["time"], arrays["auxiliary"], np.ones(len(arrays["time"])), {})
                                auxiliary["provided_instrument_channel"] = bin_lightcurve(channel, analysis.bin_minutes)
                        sap = None
                    else:
                        raw, sap, auxiliary = read_lightcurve(path), read_lightcurve(path, "SAP_FLUX"), read_auxiliary(path, analysis.bin_minutes)
                    result, diagnostic, baseline = review_epoch(raw, sap, auxiliary, baseline, analysis, config, revision="v3")
                    plot = f"s{item['sector']:04d}.png"; plot_review(diagnostic, result, folder/plot)
                    row["observations"].append({"sector": item["sector"], "input": item, "baseline": baseline, "v2": result, "plot": plot, "plot_sha256": sha256(folder/plot)})
                    pixel = next((p for p in case.get("pixel_inputs", []) if p["sector"] == item["sector"]), None)
                    if pixel:
                        pixelplot = f"s{item['sector']:04d}-pixels.png"
                        trial_period = result["photometric_period_d"] or result["candidates"][0]["period_d"]
                        source = localize(verified(pixel), path, case["target"], trial_period, folder/pixelplot)
                        source.update(plot=pixelplot, sector=item["sector"], input=pixel, period_d=trial_period,
                                      periodic_screen_passed=result["periodic_detected"]); evidence.append(source)
                except Exception as exc:
                    row["errors"].append({"sector": item["sector"], "error": str(exc)})
            row["conclusion"] = combine_epochs([o["v2"] for o in row["observations"]], config, evidence)
            if row["old_candidate_alert"] is None:
                row["old_candidate_alert"] = assess([o["baseline"] for o in row["observations"]], analysis.period_tolerance)["status"] == "approximately_repeated"
            if row["errors"]:
                row["status"] = "failed"
                row["conclusion"].update(decision="failed", periodic_detected=False, target_candidate=False, selected_period_d=None)
        write_json(folder/"prediction.json", row)
        output["results"].append(row)
        write_json(out/"predictions.json", output)
        print(row["id"], row["status"], row.get("conclusion", {}).get("decision"),
              [(o["sector"], o["v2"]["photometric_period_d"], o["v2"]["period_status"]) for o in row["observations"]], flush=True)
    output.update(complete=True, completed_at=now(), runtime_seconds=time.monotonic()-start)
    write_json(out/"predictions.json", output)
    prediction_hash = sha256(out/"predictions.json")
    output["metrics"] = score(output["results"], mode)
    output["prediction_sha256"] = prediction_hash
    write_json(out/"results.json", output)
    for row in output["results"]:
        write_json(out/row["id"]/"case.json", row); write_case_report(out/row["id"], row)
    with (out/"comparison.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["id", "kind", "status", "old_candidate", "periodic_detected", "target_candidate", "decision", "photometric_period_d", "selected_period_d", "preferred_cycle_score", "photometric_cycle_score"])
        for r in output["results"]:
            c = r.get("conclusion", {})
            writer.writerow([r["id"], r["kind"], r["status"], r["old_candidate_alert"], c.get("periodic_detected"), c.get("target_candidate"), c.get("decision"), c.get("photometric_period_d"), c.get("selected_period_d"), r["score"]["preferred_cycle"], r["score"]["photometric_cycle"]])
    print("V3_COMPLETE", json.dumps(output["metrics"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["development", "former-pilot-development"], default="development")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=BENCH/"v3-protocol-v01.json")
    args = parser.parse_args()
    evaluate(args.mode, args.output.resolve(), args.protocol.resolve())
