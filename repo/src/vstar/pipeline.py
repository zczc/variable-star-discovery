from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid
from . import __version__
from .io import now, read_json, write_json, sha256, code_fingerprint, run_lock
from .models import Config, empty_submission
from .periods import analyze
from .reports import plot_observation, generate_report
from .sources import historical_targets
from .storage import Store


def assess(results, tolerance):
    if len(results) < 2:
        return {"status": "insufficient_epochs", "fractional_spread": None}
    periods = [r["period_d"] for r in results]
    spread = (max(periods) - min(periods)) / sorted(periods)[len(periods) // 2]
    return {"status": "approximately_repeated" if spread <= tolerance else "inconsistent",
            "fractional_spread": spread, "tolerance": tolerance,
            "note": "Heuristic screening comparison, not period-error or long-term phase-coherence validation."}


def create_run(config: Config, offline=False, limit=None, run_id=None):
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if config.source != "historical":
        raise ValueError("MAST selection is not available in this build")
    targets = historical_targets(config, limit)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        raise ValueError("run-id must contain only letters, numbers, dash and underscore")
    root = config.path("runs_dir") / run_id
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "run.json", {"created_at": now(), "version": __version__, "code_fingerprint": code_fingerprint(),
                                   "config": config.snapshot(), "offline": offline, "targets_hash": None})
    write_json(root / "targets.json", targets)
    meta = read_json(root / "run.json")
    meta["targets_hash"] = sha256(root / "targets.json")
    write_json(root / "run.json", meta)
    return execute_run(root)


def execute_run(root: Path):
    root = root.resolve()
    meta = read_json(root / "run.json")
    config = Config.from_snapshot(meta["config"])
    if meta["code_fingerprint"] != code_fingerprint():
        raise ValueError("Code changed since this run. Start a new run; old reports remain readable.")
    if sha256(root / "targets.json") != meta["targets_hash"]:
        raise ValueError("Frozen target list was modified; start a new run")
    targets = read_json(root / "targets.json")
    config_hash = hashlib.sha256(json.dumps(meta["config"], sort_keys=True).encode()).hexdigest()
    with run_lock(root):
        store = Store(root)
        try:
            rows = []
            for target in targets:
                row = dict(target, results=[], errors=[], submission=empty_submission())
                folder = root / "results" / target["tic"]
                folder.mkdir(parents=True, exist_ok=True)
                for observation in sorted(target["observations"], key=lambda o: o["sector"]):
                    key = f'{target["tic"]}:{observation["sector"]}:{Path(observation["file"]).name}'
                    path = config.workspace / observation["file"]
                    fingerprint = observation["sha256"] + config_hash
                    try:
                        if not path.is_file() or sha256(path) != observation["sha256"]:
                            raise ValueError(f"Missing or modified input: {path.name}")
                        cached = store.cached(key, fingerprint)
                        if cached and (root / cached["plot"]).is_file() and sha256(root / cached["plot"]) == cached["plot_sha256"]:
                            row["results"].append(cached)
                            continue
                        store.start(key, fingerprint)
                        result, diagnostic = analyze(path, config.analysis)
                        suffix = hashlib.sha256(key.encode()).hexdigest()[:8]
                        stem = f's{observation["sector"]:04d}-{suffix}'
                        plot = folder / (stem + ".png")
                        plot_observation(diagnostic, result, plot)
                        result.update(sector=observation["sector"], input=observation, plot=str(plot.relative_to(root)), plot_sha256=sha256(plot))
                        artifact = folder / (stem + ".json")
                        write_json(artifact, result)
                        store.finish(key, artifact)
                        row["results"].append(result)
                    except Exception as exc:
                        store.start(key, fingerprint) if store.db.execute("SELECT id FROM tasks WHERE id=?", (key,)).fetchone() is None else None
                        store.fail(key, exc)
                        row["errors"].append({"task": key, "error": str(exc)})
                row["repeatability"] = assess(row["results"], config.analysis.period_tolerance)
                row["status"] = "inconclusive"
                row["reasons"] = ["目录与文献查重尚未完整完成；周期峰不是发现确认。"]
                if not target["observations"]:
                    row["status"] = "catalog_match_unverified"
                    row["reasons"].append("历史流程按近位置 VSX 条目预筛，未下载该目标光变；尚未重新确认对象身份。")
                elif row["errors"]:
                    row["status"] = "failed"
                    row["reasons"].append("部分数据分析失败，成功部分仍保留；可用 resume 重试。")
                elif row["repeatability"]["status"] == "approximately_repeated":
                    row["status"] = "periodic_candidate"
                    row["reasons"].append("多个观测区的最强周期近似重复，仍需误差、谐波和来源检查。")
                elif row["repeatability"]["status"] == "inconsistent":
                    row["reasons"].append("不同观测区的最强周期不一致；不能据此认定天体恒定。")
                else:
                    row["reasons"].append("仅有一个已分析观测区，尚无独立时段验证。")
                rows.append(row)
                write_json(root / "summary.json", {"created_at": meta["created_at"], "updated_at": now(), "complete": False, "targets": rows})
                print(f'TIC {target["tic"]}: {len(row["results"])} sectors, {row["status"]}', flush=True)
            write_json(root / "summary.json", {"created_at": meta["created_at"], "updated_at": now(), "complete": True, "targets": rows})
            generate_report(root)
        finally:
            store.close()
    return root
