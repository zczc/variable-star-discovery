"""Build a self-contained teaching lab from two archived, identified observations."""
from dataclasses import asdict
from pathlib import Path
import csv
import json
import numpy as np
from astropy.io import fits
from vstar.io import read_json, write_json, sha256
from vstar.models import AnalysisConfig
from vstar.photometry import LightCurve, bin_lightcurve
from vstar.periods import period_search, bls_search


def build():
    workspace = Path(__file__).resolve().parents[2]
    out = Path(__file__).with_name("first-variable-star")
    out.mkdir(exist_ok=True)
    controls = read_json(workspace / "repo/benchmarks/known-v01/results.json")
    config = AnalysisConfig(use_bls=True)
    lab = {"tic": "9473243", "reference_period_d": 2.2669, "config": asdict(config), "sectors": {}}
    provenance = {"purpose": "Teaching example, not a blinded or independent performance evaluation", "config": asdict(config), "files": []}
    for record in controls["results"]:
        if record["tic"] != lab["tic"]:
            continue
        path = workspace / "repo/data/known-controls/fits" / record["uri"].rsplit("/", 1)[-1]
        assert sha256(path) == record["sha256"]
        with fits.open(path, memmap=False) as hdul:
            table, header = hdul[1].data, hdul[1].header
            assert header["TIMESYS"] == "TDB" and header["TIMEUNIT"] == "d"
            offset = header["BJDREFI"] + header.get("BJDREFF", 0)
            t = np.asarray(table["TIME"], float)
            q = np.asarray(table["QUALITY"], int)
            columns = {k: np.asarray(table[k], float) for k in ["SAP_FLUX", "SAP_FLUX_ERR", "PDCSAP_FLUX", "PDCSAP_FLUX_ERR"]}
        sector = str(record["sector"])
        filename = f"tic9473243-sector{sector}.csv"
        with (out / filename).open("w", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(["TIME_BTJD_TDB_d", "BJD_TDB_d", "QUALITY", *[k + "_electrons_per_s" for k in columns]])
            for i in range(len(t)):
                writer.writerow([t[i], t[i] + offset, q[i], *[values[i] for values in columns.values()]])
        info = {"offset": offset, "original_points": len(t), "csv": filename, "scenarios": {}}
        for column in ["PDCSAP_FLUX", "SAP_FLUX"]:
            for quality in [True, False]:
                y, e = columns[column], columns[column + "_ERR"]
                good = np.isfinite(t) & np.isfinite(y) & np.isfinite(e) & (e > 0)
                if quality:
                    good &= q == 0
                order = np.argsort(t[good])
                norm = float(np.median(y[good]))
                lc = LightCurve(t[good][order], y[good][order] / norm - 1, e[good][order] / norm, {})
                lc = bin_lightcurve(lc, config.bin_minutes)
                period, _, frequency, power, _ = period_search(lc, config)
                bls = bls_search(lc, config)
                if column == "PDCSAP_FLUX" and quality:
                    assert np.isclose(period, record["ls_period_d"], rtol=1e-12)
                    assert np.isclose(bls["period_d"], record["bls_period_d"], rtol=1e-12)
                info["scenarios"][column + ("_good" if quality else "_all")] = {
                    "time": np.round(lc.time, 8).tolist(), "flux_pct": np.round(lc.flux * 100, 7).tolist(),
                    "error_pct": np.round(lc.error * 100, 7).tolist(), "periods": (1 / frequency).tolist(), "power": power.tolist(),
                    "ls_period": period, "bls_period": bls["period_d"], "used_points": int(good.sum()),
                    "median_error_pct": float(np.median(lc.error) * 100), "time_zero": float(lc.time.min())}
        lab["sectors"][sector] = info
        provenance["files"].append({"sector": int(sector), "uri": record["uri"], "fits_sha256": record["sha256"],
                                    "csv": filename, "csv_sha256": sha256(out / filename), "bjd_reference": offset})
    assert set(lab["sectors"]) == {"25", "79"}
    template = Path(__file__).with_name("first-lab-template.html").read_text()
    (out / "index.html").write_text(template.replace("__LAB_DATA__", json.dumps(lab, separators=(",", ":"))))
    provenance["display"] = "10-minute means. Time displayed to 8 decimal days; normalized flux to 7 decimal percent. CSV retains FITS values, including invalid measurements and quality flags."
    write_json(out / "provenance.json", provenance)
    print(out / "index.html")


if __name__ == "__main__":
    build()
