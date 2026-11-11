"""Fetch named catalog identities and preselected sectors, without analyzing flux."""
from pathlib import Path
import json
from astropy.coordinates import SkyCoord
from vstar.io import read_json, write_json, now, sha256
from vstar.network import ArchiveClient

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT/"repo/benchmarks"


def main():
    protocol = read_json(BENCH/"independent-pilot-protocol-v02.json")
    out = BENCH/"independent-pilot-v02"
    out.mkdir(exist_ok=False)
    client = ArchiveClient(ROOT/"repo/data/independent-pilot-v02", max_bytes=protocol["data_limit_bytes"])
    previous = set()
    for p in (ROOT/"repo/runs").glob("*/targets.json"):
        previous.update(str(t["tic"]) for t in read_json(p))
    previous.update(t["tic"] for t in read_json(BENCH/"known-controls.json")["targets"])
    for old in [BENCH/"independent-pilot-v01/input-manifest.json"]:
        previous.update(str(c["tic"]) for c in read_json(old)["cases"] if c.get("tic"))
    manifest = {"created_at": now(), "protocol_sha256": sha256(BENCH/"independent-pilot-protocol-v02.json"),
                "acquisition_script_sha256": sha256(Path(__file__)), "cases": []}
    for name in protocol["targets"]:
        case = {"id": name.lower().replace(" ", "-"), "name": name, "kind": "real_new_positive_control", "inputs": [], "errors": []}
        try:
            vsx, receipt = client.query("VSX identity", "GET", "https://vsx.aavso.org/index.php", params={"view": "api.object", "ident": name, "format": "json"})
            write_json(out/(case["id"]+"-vsx.json"), {"response": vsx, "receipt": receipt})
            star = vsx["VSXObject"]
            if star["Name"] != name:
                raise ValueError("Name resolution did not return exact preselected object")
            ra, dec = float(star["RA2000"]), float(star["Declination2000"])
            request = {"service": "Mast.Catalogs.Tic.Cone", "params": {"ra": ra, "dec": dec, "radius": 10/3600}, "format": "json", "pagesize": 1000, "page": 1}
            tic, receipt = client.query("MAST", "POST", "https://mast.stsci.edu/api/v0/invoke", data={"request": json.dumps(request)})
            write_json(out/(case["id"]+"-tic.json"), {"response": tic, "receipt": receipt})
            if tic["paging"]["pagesFiltered"] > 1 or len(tic["data"]) != tic["paging"]["rowsFiltered"]:
                raise ValueError("Incomplete TIC neighborhood")
            position = SkyCoord(ra, dec, unit="deg")
            matches = sorted(tic["data"], key=lambda t: position.separation(SkyCoord(t["ra"], t["dec"], unit="deg")).arcsec)
            if not matches:
                raise ValueError("No TIC identity within 10 arcsec")
            target = matches[0]; identity = str(target["ID"])
            if identity in previous:
                raise ValueError("Target overlaps previous development objects")
            case.update(tic=identity, identity_sep_arcsec=float(position.separation(SkyCoord(target["ra"], target["dec"], unit="deg")).arcsec),
                        reference={"period_d": float(star["Period"]), "photometric_period_d": float(star["Period"]), "source": f'https://vsx.aavso.org/index.php?view=detail.top&oid={star["OID"]}', "type": star["VariabilityType"]})
            filters = [{"paramName": "obs_collection", "values": ["TESS"]}, {"paramName": "provenance_name", "values": ["SPOC"]},
                       {"paramName": "dataproduct_type", "values": ["timeseries"]}, {"paramName": "target_name", "values": [identity]}]
            observations, receipts = client.mast_rows(filters)
            sectors = {int(o["sequence_number"]): o for o in observations if o.get("dataURL", "").endswith("_lc.fits") and "_fast" not in o["dataURL"]}
            write_json(out/(case["id"]+"-observations.json"), {"observations": observations, "receipts": receipts})
            if len(sectors) < 2:
                raise ValueError("Fewer than two supported non-fast SPOC sectors")
            ordered = sorted(sectors, key=lambda n: (sectors[n]["t_min"], sectors[n]["dataURL"]))
            for sector in [ordered[0], ordered[-1]]:
                uri = sectors[sector]["dataURL"]
                path, digest = client.download(uri)
                case["inputs"].append({"sector": sector, "uri": uri, "path": str(path.relative_to(ROOT)), "sha256": digest})
            case["target"] = {"ra_deg": target["ra"], "dec_deg": target["dec"], "vsx_neighbors": [star]}
            print(name, identity, "acquired", [i["sector"] for i in case["inputs"]], flush=True)
        except Exception as exc:
            case["unavailable_reason"] = str(exc)
            case["errors"].append(str(exc))
            print(name, "UNAVAILABLE", str(exc), flush=True)
        manifest["cases"].append(case)
        write_json(out/"input-manifest.json", manifest)
    manifest["completed_at"] = now()
    write_json(out/"input-manifest.json", manifest)


if __name__ == "__main__":
    main()
