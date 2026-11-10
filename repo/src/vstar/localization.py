"""Exploratory coherent pixel maps; not a PRF fit or a validated localization error."""
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .photometry import read_lightcurve


def localize(tpf: Path, lightcurve: Path, target, period, plot: Path):
    with fits.open(tpf, memmap=False) as hdul:
        table, aperture = hdul[1].data, np.array(hdul[2].data)
        wcs = WCS(hdul[2].header)
        t, cube = np.array(table["TIME"], float), np.array(table["FLUX"], float)
        good = np.isfinite(t) & (table["QUALITY"] == 0) & np.isfinite(cube).all(axis=(1, 2))
        t, cube = t[good], cube[good]
    if len(t) < 100 or np.ptp(t) <= 0:
        raise ValueError("Insufficient good target-pixel samples")
    lc = read_lightcurve(lightcurve)
    inside = (t >= lc.time.min()) & (t <= lc.time.max())
    t, cube = t[inside], cube[inside]
    if len(t) < 100:
        raise ValueError("Target pixels and light curve do not overlap")
    ref = np.interp(t, lc.time, lc.flux)
    x0, y0 = map(float, wcs.world_to_pixel_values(target["ra_deg"], target["dec_deg"]))
    u = (t - np.mean(t)) / np.ptp(t)
    gaps = np.cumsum(np.r_[0, np.diff(t) > .5])
    columns = [np.ones(len(t)), u, u ** 2, u ** 3]
    columns += [(gaps == g).astype(float) for g in np.unique(gaps)[1:]]
    angle = 2 * np.pi * t / period
    design = np.column_stack(columns + [np.sin(angle), np.cos(angle)])
    coefficients = np.linalg.lstsq(design, cube.reshape(len(t), -1), rcond=None)[0]
    reference = np.linalg.lstsq(design, ref, rcond=None)[0][-2:]
    norm = np.linalg.norm(reference)
    if norm <= 1e-12:
        raise ValueError("No coherent reference signal for localization")
    signal = (reference / norm @ coefficients[-2:]).reshape(aperture.shape)
    ypeak, xpeak = np.unravel_index(np.argmax(signal), signal.shape)
    target_distance = float(np.hypot(xpeak - x0, ypeak - y0))
    neighbors = []
    for obj in target.get("vsx_neighbors", []):
        xn, yn = map(float, wcs.world_to_pixel_values(float(obj["RA2000"]), float(obj["Declination2000"])))
        p = float(obj.get("Period", 0) or 0)
        ratio_error = min(abs(period / (p * h) - 1) for h in [.5, 1, 2]) if p > 0 else None
        neighbors.append({"name": obj["Name"], "x": xn, "y": yn, "distance_from_peak_pixels": float(np.hypot(xpeak-xn, ypeak-yn)),
                          "period_d": p or None, "period_harmonic_fractional_error": ratio_error})
    contaminant = next((n for n in sorted(neighbors, key=lambda n: n["distance_from_peak_pixels"])
                        if n["distance_from_peak_pixels"] < .75 and n["period_harmonic_fractional_error"] is not None and n["period_harmonic_fractional_error"] < .02 and target_distance > 1), None)
    status = "likely_contaminated" if contaminant else ("consistent_with_target" if target_distance < 1 else "unresolved")
    mean = np.median(cube, axis=0)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), layout="constrained")
    a = axes[0].imshow(np.log10(np.maximum(mean, 1)), origin="lower", cmap="magma")
    fig.colorbar(a, ax=axes[0], label="log10 median flux")
    scale = max(float(np.max(np.abs(signal))), 1e-10)
    a = axes[1].imshow(signal, origin="lower", cmap="coolwarm", vmin=-scale, vmax=scale)
    fig.colorbar(a, ax=axes[1], label="Coherent signal (electrons/s)")
    for ax in axes:
        ax.plot(x0, y0, "o", mfc="none", mec="lime", ms=12, label="Target")
        for n in neighbors:
            ax.plot(n["x"], n["y"], "x", color="cyan")
        if np.any((aperture & 2) > 0) and np.any((aperture & 2) == 0):
            ax.contour((aperture & 2) > 0, levels=[.5], colors="white", linewidths=.8)
        ax.set(xlim=(-.5, aperture.shape[1]-.5), ylim=(-.5, aperture.shape[0]-.5), xlabel="Pixel column", ylabel="Pixel row")
    axes[0].set_title("Target and catalog neighbors")
    axes[1].set_title(f"Signal at {period:.6f} days")
    fig.suptitle("Exploratory pixel localization; not a precision position fit")
    fig.savefig(plot, dpi=130)
    plt.close(fig)
    return {"status": status, "target_pixel": [x0, y0], "peak_pixel": [int(xpeak), int(ypeak)],
            "target_peak_distance_pixels": target_distance, "neighbors": neighbors, "possible_contaminant": contaminant,
            "limitations": "Heuristic peak/harmonic matching; no PRF fit, localization uncertainty or correlated-noise significance. This is not a submission finding chart."}
