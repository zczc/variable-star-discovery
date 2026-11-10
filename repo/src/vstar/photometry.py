from dataclasses import dataclass
from pathlib import Path
import numpy as np
from astropy.io import fits


@dataclass
class LightCurve:
    time: np.ndarray
    flux: np.ndarray
    error: np.ndarray
    metadata: dict


def read_lightcurve(path: Path, column="PDCSAP_FLUX") -> LightCurve:
    with fits.open(path, memmap=False) as hdul:
        data = hdul[1].data
        header = dict(hdul[0].header) | dict(hdul[1].header)
        t, y, e = (np.array(data[k], dtype=float) for k in ["TIME", column, column + "_ERR"])
        good = np.isfinite(t) & np.isfinite(y) & np.isfinite(e) & (e > 0) & (data["QUALITY"] == 0)
        t, y, e = t[good], y[good], e[good]
    if len(t) < 2 or np.ptp(t) <= 0:
        raise ValueError("No usable time series after quality filtering")
    median = float(np.median(y))
    if not np.isfinite(median) or median <= 0:
        raise ValueError("Flux normalization requires a positive finite median")
    order = np.argsort(t, kind="stable")
    metadata = {k: header.get(k) for k in ["TICID", "SECTOR", "TESSMAG", "TEFF", "CROWDSAP", "FLFRCSAP", "CAMERA", "CCD", "TIMESYS", "TIMEREF", "TIMEUNIT", "BJDREFI", "BJDREFF"]}
    metadata.update(flux_column=column, original_points=len(good), usable_points=int(good.sum()), normalization_median=median)
    return LightCurve(t[order], y[order] / median - 1, e[order] / median, metadata)


def bin_lightcurve(lc: LightCurve, minutes: float) -> LightCurve:
    key = np.floor((lc.time - lc.time.min()) / (minutes / 1440)).astype(int)
    _, idx = np.unique(key, return_inverse=True)
    n = np.bincount(idx)
    return LightCurve(np.bincount(idx, weights=lc.time) / n,
                      np.bincount(idx, weights=lc.flux) / n,
                      np.sqrt(np.bincount(idx, weights=lc.error ** 2)) / n, lc.metadata)
