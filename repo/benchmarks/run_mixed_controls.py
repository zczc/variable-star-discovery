"""Prepare fixed inputs, then run the existing baseline without a final selector.

From repository root:
  repo/.venv/bin/python repo/benchmarks/run_mixed_controls.py --prepare-only
  repo/.venv/bin/python repo/benchmarks/run_mixed_controls.py
Use a new --output directory for a rerun; completed results are never overwritten.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import csv
import platform
import subprocess
import time
import numpy as np
import scipy
import astropy
from vstar.io import now, read_json, write_json, sha256, code_fingerprint
from vstar.models import AnalysisConfig
from vstar.photometry import read_lightcurve
from vstar.periods import analyze, analyze_series
from vstar.pipeline import assess
from vstar.localization import localize
from vstar.reports import plot_observation
from run_known_controls import classify_period
from simulate_controls import generate, as_lightcurve

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "repo/benchmarks"


def verified(item):
    path = ROOT / item["path"]
    if not path.is_file() or sha256(path) != item["sha256"]:
        raise ValueError(f"Missing or modified input: {item['path']}")
    return path


def file_record(path, **extra):
    return dict(path=str(path.relative_to(ROOT)), sha256=sha256(path), **extra)


def dependencies():
    paths = [Path(__file__), BENCH/"simulate_controls.py", BENCH/"run_known_controls.py",
             BENCH/"mixed-protocol-v01.json", BENCH/"known-controls.json", BENCH/"known-v01/results.json",
             ROOT/"repo/runs/historical-v02/summary.json", ROOT/"repo/runs/sector94-100-v02/summary.json"]
    return [file_record(p) for p in paths]


def prepare(out, protocol):
    if (out/"input-manifest.json").exists():
        raise FileExistsError("Inputs already prepared; use a new output directory")
    known = read_json(BENCH/"known-v01/results.json")["results"]
    cadences = {}
    for row in known:
        p = ROOT/"repo/data/known-controls/fits"/Path(row["uri"]).name
        item = {"path": str(p.relative_to(ROOT)), "sha256": row["sha256"], "uri": row["uri"], "sector": row["sector"]}
        verified(item)
        cadences.setdefault(row["tic"], []).append(item)
    manifest = {"created_at": now(), "stage": "inputs frozen before evaluation", "dependencies": dependencies(),
                "code_fingerprint": code_fingerprint(), "cases": []}
    for case in protocol["cases"]:
        row = {"id": case["id"], "inputs": [], "errors": []}
        try:
            if not case.get("available", True):
                row["unavailable_reason"] = case["reason"]
            elif case["kind"] == "real_known_variable":
                row["inputs"] = sorted(cadences[case["tic"]], key=lambda x: x["sector"])
            elif case["kind"] == "real_contaminated_target":
                prior = read_json(ROOT/f"repo/runs/{case['run']}/summary.json")
                target = next(x for x in prior["targets"] if x["tic"] == case["tic"])
                row["target"] = {k: target[k] for k in ["tic", "ra_deg", "dec_deg", "vsx_neighbors"]}
                for result in sorted(target["results"], key=lambda x: x["sector"]):
                    old = result["input"]
                    item = {"path": old["file"], "sha256": old["sha256"], "uri": old["uri"], "sector": result["sector"]}
                    verified(item)
                    row["inputs"].append(item)
                latest = row["inputs"][-1]
                pixel = dict(target["localization"]["pixel_input"], path=latest["path"].replace("_lc.fits", "_tp.fits"), sector=latest["sector"])
                verified(pixel)
                row["pixels"] = pixel
            else:
                cadence = sorted(cadences[case["cadence_tic"]], key=lambda x: x["sector"])
                origin = read_lightcurve(verified(cadence[0])).time.min()
                for i, sampling in enumerate(cadence):
                    raw = read_lightcurve(verified(sampling))
                    arrays = generate(case, raw.time, origin, i)
                    path = out/"inputs"/f"{case['id']}-s{sampling['sector']:04d}.npz"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(path, **arrays)
                    row["inputs"].append(file_record(path, sector=sampling["sector"], cadence=sampling))
        except Exception as exc:
            row["errors"].append(str(exc))
        manifest["cases"].append(row)
    manifest["completed_at"] = now()
    write_json(out/"input-manifest.json", manifest)
    print("INPUTS_PREPARED", len(manifest["cases"]), "errors", sum(bool(r["errors"]) for r in manifest["cases"]), flush=True)


def metrics(rows):
    groups = {}
    for kind in dict.fromkeys(r["kind"] for r in rows):
        group = [r for r in rows if r["kind"] == kind]
        groups[kind] = {"cases": len(group), "completed": sum(r["status"] == "completed" for r in group),
                        "candidate_alerts": sum(r["candidate_alert"] is True for r in group),
                        "unavailable": sum(r["status"] == "unavailable" for r in group),
                        "errors": sum(r["status"] == "failed" for r in group)}
        for method in ["ls", "bls"]:
            evaluated = [o["evaluation"][method] for r in group for o in r["observations"] if "evaluation" in o]
            groups[kind][method+"_observation_periods"] = dict(Counter(evaluated))
            groups[kind][method+"_all_epochs_correct_cases"] = sum(
                r["status"] == "completed" and bool(r["observations"]) and
                all(o.get("evaluation", {}).get(method) == "correct_period" for o in r["observations"]) for r in group)
    return {"by_kind": groups, "real_quiet_stars": 0, "real_quiet_false_positive_rate": None,
            "final_period_accuracy": None, "confirmed_new_variables": 0,
            "note": "Alerts are screening candidates. No final period selector or confirmed-variable classifier exists."}


def evaluate(out, protocol):
    if (out/"results.json").exists():
        raise FileExistsError("Results already exist; use a new output directory")
    manifest = read_json(out/"input-manifest.json")
    if manifest["code_fingerprint"] != code_fingerprint():
        raise ValueError("Analysis code changed after input freeze")
    for item in manifest["dependencies"]:
        verified(item)
    config = AnalysisConfig(**protocol["analysis"])
    truth = {t["tic"]: t for t in read_json(BENCH/"known-controls.json")["targets"]}
    output = {"created_at": now(), "complete": False, "stage": protocol["stage"], "code_fingerprint": code_fingerprint(),
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "manifest": file_record(out/"input-manifest.json"), "analysis_config": asdict(config),
              "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "astropy": astropy.__version__},
              "limitations": protocol["limitations"], "results": []}
    start = time.monotonic()
    for case, inputs in zip(protocol["cases"], manifest["cases"], strict=True):
        assert case["id"] == inputs["id"]
        row = dict(case, status="completed", observations=[], errors=list(inputs["errors"]), candidate_alert=None)
        folder = out/case["id"]
        folder.mkdir(exist_ok=True)
        if "unavailable_reason" in inputs:
            row["status"] = "unavailable"
        else:
            for item in inputs["inputs"]:
                try:
                    path = verified(item)
                    auxiliary = None
                    if case["kind"].startswith("synthetic_"):
                        with np.load(path) as data:
                            lc = as_lightcurve(data, {"SECTOR": item["sector"], "TIMESYS": "TDB", "BJDREFI": 2457000})
                            if len(data["auxiliary"]):
                                auxiliary = float(np.corrcoef(data["flux"], data["auxiliary"])[0, 1])
                            # Same samples in the two channels: no simulated independent SAP evidence.
                            result, diagnostic = analyze_series(lc, config, lc)
                    else:
                        result, diagnostic = analyze(path, config)
                    stem = f"s{item['sector']:04d}"
                    plot = folder/(stem+".png")
                    plot_observation(diagnostic, result, plot)
                    result.update(sector=item["sector"], input=item, plot=str(plot.relative_to(out)), plot_sha256=sha256(plot))
                    if auxiliary is not None:
                        result["auxiliary_correlation"] = auxiliary
                        result["auxiliary_note"] = "Diagnostic only; the baseline does not consume this instrumental channel."
                    # Reference labels only enter evaluation after numerical analysis.
                    reference = truth[case["tic"]]["period_d"] if case["kind"] == "real_known_variable" else case.get("period_d")
                    if reference is not None:
                        photometric = reference*case.get("photometric_period_fraction", 1)
                        result["evaluation"] = {"reference_period_d": reference, "photometric_reference_d": photometric,
                                                "reference_is_instrumental": case["kind"] == "synthetic_common_mode"}
                        for method, measured in [("ls", result["period_d"]), ("bls", result["bls"]["period_d"])]:
                            result["evaluation"][method] = classify_period(measured, reference, protocol["period_tolerance"])
                            result["evaluation"][method+"_photometric"] = classify_period(measured, photometric, protocol["period_tolerance"])
                    write_json(folder/(stem+".json"), result)
                    row["observations"].append(result)
                except Exception as exc:
                    row["errors"].append({"sector": item["sector"], "error": str(exc)})
            row["repeatability"] = assess(row["observations"], config.period_tolerance)
            row["candidate_alert"] = not row["errors"] and row["repeatability"]["status"] == "approximately_repeated"
            if "pixels" in inputs and row["observations"]:
                try:
                    result = next(r for r in row["observations"] if r["sector"] == inputs["pixels"]["sector"])
                    plot = folder/"pixels.png"
                    row["localization"] = localize(verified(inputs["pixels"]), verified(result["input"]), inputs["target"], result["period_d"], plot)
                    row["localization"].update(plot=str(plot.relative_to(out)), plot_sha256=sha256(plot), input=inputs["pixels"])
                except Exception as exc:
                    row["errors"].append({"localization": str(exc)})
            if row["errors"]:
                row["status"] = "failed"
            row["baseline_status"] = "failed" if row["errors"] else (
                "likely_contaminated" if row.get("localization", {}).get("status") == "likely_contaminated" else
                "periodic_candidate" if row["candidate_alert"] else "inconclusive")
        write_json(folder/"case.json", row)
        output["results"].append(row)
        write_json(out/"results.json", output)
        print(case["id"], row["status"], "alert", row["candidate_alert"], "LS", [round(r["period_d"], 6) for r in row["observations"]], flush=True)
    output.update(complete=True, completed_at=now(), runtime_seconds=time.monotonic()-start, metrics=metrics(output["results"]))
    write_json(out/"results.json", output)
    with (out/"results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        keys = ["id", "kind", "status", "candidate_alert", "baseline_status", "ls_periods_d", "bls_periods_d", "source_status", "errors"]
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for r in output["results"]:
            writer.writerow(dict(r, ls_periods_d=";".join(str(o["period_d"]) for o in r["observations"]),
                                 bls_periods_d=";".join(str(o["bls"]["period_d"]) for o in r["observations"]),
                                 source_status=r.get("localization", {}).get("status", "not_checked")))
    print("MIXED_COMPLETE", output["metrics"], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--output", type=Path, default=BENCH/"mixed-v01")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    protocol = read_json(BENCH/"mixed-protocol-v01.json")
    if args.prepare_only:
        prepare(out, protocol)
    else:
        evaluate(out, protocol)


if __name__ == "__main__":
    main()
