"""Public archive adapters with bounded retries, atomic downloads and query receipts."""
from pathlib import Path
import hashlib
import json
import os
import time
import requests
from astropy.io import fits
from .io import now, read_json, write_json, sha256


class ArchiveClient:
    def __init__(self, cache: Path, offline=False, attempts=3, max_bytes=20_000_000_000):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline, self.attempts, self.max_bytes = offline, attempts, max_bytes
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "variable-star-discovery/0.1 public-research"

    def request(self, method, url, **kwargs):
        if self.offline:
            raise RuntimeError("Network disabled by --offline")
        for attempt in range(self.attempts):
            try:
                r = self.session.request(method, url, timeout=(10, 45), **kwargs)
                if r.status_code == 429 or r.status_code >= 500:
                    r.close()
                    raise requests.ConnectionError("Remote service temporarily unavailable")
                r.raise_for_status()
                return r
            except (requests.Timeout, requests.ConnectionError):
                if attempt + 1 == self.attempts:
                    raise
                time.sleep(min(2 ** attempt, 4))

    def query(self, name, method, url, **kwargs):
        key = hashlib.sha256(json.dumps([name, method, url, kwargs], sort_keys=True).encode()).hexdigest()
        path = self.cache / "queries" / (key + ".json")
        if path.exists():
            receipt = read_json(path)
            return receipt["response"], {k: receipt[k] for k in ["source", "checked_at", "url", "query"]}
        r = self.request(method, url, **kwargs)
        try:
            response = r.json()
        finally:
            r.close()
        if name == "MAST" and (not isinstance(response, dict) or response.get("status") != "COMPLETE"):
            raise ValueError("MAST returned an incomplete/error response")
        if name == "VSX" and (not isinstance(response, dict) or "VSXObjects" not in response):
            raise ValueError("Unrecognized VSX response; not interpreted as no match")
        receipt = {"source": name, "checked_at": now(), "url": url, "query": kwargs, "response": response}
        write_json(path, receipt)
        return response, {k: receipt[k] for k in ["source", "checked_at", "url", "query"]}

    def mast_rows(self, filters, max_pages=40, page_size=1000):
        rows, receipts = [], []
        for page in range(1, max_pages + 1):
            req = {"service": "Mast.Caom.Filtered", "params": {"columns": "obsid,obs_id,target_name,s_ra,s_dec,sequence_number,t_min,t_max,dataURL,provenance_name", "filters": filters},
                   "format": "json", "pagesize": page_size, "page": page}
            response, receipt = self.query("MAST", "POST", "https://mast.stsci.edu/api/v0/invoke", data={"request": json.dumps(req)})
            data, paging = response.get("data"), response.get("paging", {})
            if not isinstance(data, list) or "pagesFiltered" not in paging:
                raise ValueError("Missing MAST pagination; completeness cannot be established")
            rows.extend(data)
            receipts.append(receipt)
            if page >= int(paging["pagesFiltered"]):
                if "rowsFiltered" in paging and len(rows) != int(paging["rowsFiltered"]):
                    raise ValueError("MAST row count changed during pagination; retry with a fresh cache")
                return rows, receipts
        raise ValueError(f"MAST pagination exceeded {max_pages} pages; refusing a partial catalog")

    def download(self, uri):
        if not uri.startswith("mast:TESS/product/") or Path(uri).name != uri.split("/")[-1]:
            raise ValueError("Only MAST TESS product URIs are supported")
        name = uri.rsplit("/", 1)[-1]
        if not name.endswith(".fits") or ".." in name:
            raise ValueError("Invalid FITS product name")
        path = self.cache / "fits" / name
        receipt_path = path.with_suffix(".receipt.json")
        if path.is_file() and receipt_path.is_file():
            receipt = read_json(receipt_path)
            if receipt["uri"] == uri and sha256(path) == receipt["sha256"]:
                return path, receipt["sha256"]
            if self.offline:
                raise ValueError("Corrupt cached FITS in offline mode")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Single writer in the pipeline: the budget cannot race with other downloads.
        used = sum(p.stat().st_size for p in self.cache.rglob("*") if p.is_file())
        remaining = self.max_bytes - used
        if remaining <= 0:
            raise OSError("Download cache budget exhausted")
        temporary = path.with_suffix(".fits.part")
        r = self.request("GET", "https://mast.stsci.edu/api/v0.1/Download/file", params={"uri": uri}, stream=True)
        total = 0
        try:
            with temporary.open("wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    total += len(chunk)
                    if total > remaining:
                        raise OSError("Download exceeds remaining disk budget")
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            length = r.headers.get("Content-Length")
            if length and not r.headers.get("Content-Encoding") and total != int(length):
                raise ValueError("Incomplete HTTP download")
            with fits.open(temporary, memmap=False) as hdul:
                hdul.verify("exception")
                if len(hdul) < 2 or hdul[1].data is None:
                    raise ValueError("Downloaded product is not a usable FITS table")
                # Read the last row to expose a truncated table before accepting the file.
                if len(hdul[1].data):
                    _ = hdul[1].data[-1]
            digest = sha256(temporary)
            os.replace(temporary, path)
            write_json(receipt_path, {"uri": uri, "sha256": digest, "bytes": total, "downloaded_at": now()})
            return path, digest
        finally:
            r.close()
            temporary.unlink(missing_ok=True)

    def vsx(self, ra, dec):
        try:
            response, receipt = self.query("VSX", "GET", "https://vsx.aavso.org/index.php",
                                           params={"view": "api.list", "ra": ra, "dec": dec, "radius": .04, "format": "json"})
            block = response["VSXObjects"]
            objects = block.get("VSXObject", []) if isinstance(block, dict) else block
            if isinstance(objects, dict):
                objects = [objects]
            if not isinstance(objects, list):
                raise ValueError("Invalid VSX object list")
            from astropy.coordinates import SkyCoord
            import astropy.units as u
            position = SkyCoord(ra, dec, unit="deg")
            for obj in objects:
                other = SkyCoord(float(obj["RA2000"]), float(obj["Declination2000"]), unit="deg")
                obj["sep_arcsec"] = float(position.separation(other).to_value(u.arcsec))
            return objects, {**receipt, "status": "completed", "match_count": len(objects), "note": "VSX neighborhood only; no-match is not novelty confirmation."}
        except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
            return [], {"source": "VSX", "status": "failed", "checked_at": now(), "error": str(exc)}
