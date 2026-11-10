from pathlib import Path
from .io import read_json
from .network import ArchiveClient
import numpy as np


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


def mast_targets(config, offline=False, limit=None):
    cfg = config.selection
    count = limit if limit is not None else int(cfg.get("limit", 100))
    if count < 1 or count > 1000:
        raise ValueError("Select 1–1000 targets per run")
    client = ArchiveClient(config.path("cache_dir"), offline=offline,
                           max_bytes=int(cfg.get("max_cache_bytes", 20_000_000_000)))
    base = [{"paramName": "obs_collection", "values": ["TESS"]},
            {"paramName": "dataproduct_type", "values": ["timeseries"]},
            {"paramName": "provenance_name", "values": ["SPOC"]}]
    rows, receipts = client.mast_rows(base + [{"paramName": "sequence_number", "values": [str(cfg.get("sector", 94))]}])
    def usable(row):
        return bool(row.get("dataURL")) and row["dataURL"].endswith("_lc.fits") and "_fast" not in row["dataURL"] and str(row["target_name"]).isdigit()
    by_id = {str(r["target_name"]): r for r in rows if usable(r)}
    historical = config.path("historical_dir") / "scan-results.json"
    excluded = {str(r["target_name"]) for r in read_json(historical)} if historical.exists() else set()
    ids = sorted(set(by_id) - excluded, key=int)
    np.random.default_rng(config.seed).shuffle(ids)
    pool = ids[: min(len(ids), max(count * 3, 50))]
    all_observations = []
    for start in range(0, len(pool), 50):
        batch, source_receipts = client.mast_rows(base + [{"paramName": "target_name", "values": pool[start:start+50]}])
        all_observations.extend(r for r in batch if usable(r))
        receipts.extend(source_receipts)
    grouped = {}
    for row in all_observations:
        grouped.setdefault(str(row["target_name"]), {})[int(row["sequence_number"])] = row
    targets = []
    for tic in pool:
        sectors = sorted(grouped.get(tic, {}))
        if len(sectors) < int(cfg.get("min_sectors", 2)):
            continue
        cap = int(cfg.get("max_sectors", 3))
        if cap < 2:
            raise ValueError("max_sectors must be at least 2")
        positions = np.linspace(0, len(sectors)-1, min(cap, len(sectors))).round().astype(int)
        chosen = [grouped[tic][sectors[i]] for i in positions]
        observations = [{"sector": int(r["sequence_number"]), "uri": r["dataURL"],
                         "file": str((client.cache / "fits" / Path(r["dataURL"]).name).relative_to(config.workspace)), "sha256": None} for r in chosen]
        row = by_id[tic]
        targets.append({"tic": tic, "ra_deg": row["s_ra"], "dec_deg": row["s_dec"], "observations": observations,
                        "selection": {"sector": int(cfg.get("sector", 94)), "seed": config.seed, "eligible_sectors": sectors,
                                      "inventory_objects": len(by_id), "candidate_pool": len(pool), "condition": "SPOC light curves, repeated sectors; no magnitude or crowding cut yet"},
                        "vsx_neighbors": [], "catalog_queries": [], "novelty": "incomplete", "notes": [], "source_receipts": receipts})
        if len(targets) == count:
            break
    if len(targets) != count:
        raise ValueError(f"Only {len(targets)}/{count} targets meet repeated-sector selection in the frozen candidate pool")
    return targets
