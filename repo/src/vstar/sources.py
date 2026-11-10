from pathlib import Path
from .io import read_json


def historical_targets(config, limit=None):
    root = config.path("historical_dir")
    rows = read_json(root / "scan-results.json")
    manifest = read_json(root / "migration-manifest.json")
    hashes = {r["file"]: r["saved_sha256"] for r in manifest["files"]}
    targets = []
    for row in rows[:limit]:
        tic = str(row["target_name"])
        records = [row] if row.get("file") else []
        followup = root / f"followup-{tic}.json"
        if followup.exists():
            records += read_json(followup)
        observations = []
        for r in records:
            name = Path(r["file"]).name
            observations.append({"sector": int(r["sequence_number"]), "uri": r["dataURL"],
                                 "file": str((root / name).relative_to(config.workspace)), "sha256": hashes[name]})
        targets.append({"tic": tic, "ra_deg": row["s_ra"], "dec_deg": row["s_dec"],
                        "observations": observations, "selection": "historical convenience sample",
                        "historical_status": row["status"], "vsx_neighbors": row.get("vsx_neighbors", []),
                        "catalog_queries": [{"source": "VSX", "status": "historical_snapshot", "checked_at": "2026-11-09",
                                             "note": "Archived neighborhood query only; identity and novelty not fully reviewed."}],
                        "novelty": "incomplete", "notes": []})
    return targets
