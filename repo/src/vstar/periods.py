from pathlib import Path
import numpy as np
from astropy.timeseries import LombScargle
from scipy.signal import find_peaks
from .models import AnalysisConfig
from .photometry import LightCurve, read_lightcurve, bin_lightcurve


def period_search(lc: LightCurve, config: AnalysisConfig):
    if len(lc.time) < 20 or np.ptp(lc.time) <= 0 or np.std(lc.flux) == 0:
        raise ValueError("Too few independent bins or constant flux for period search")
    ls = LombScargle(lc.time, lc.flux, lc.error)
    frequency, power = ls.autopower(minimum_frequency=1 / config.max_period_days,
                                    maximum_frequency=1 / config.min_period_days,
                                    samples_per_peak=config.samples_per_peak)
    if not np.isfinite(power).all():
        raise ValueError("Periodogram contains non-finite power")
    best = int(np.argmax(power))
    peaks, _ = find_peaks(power)
    indices = sorted(set(peaks.tolist() + [best]), key=lambda i: power[i], reverse=True)[:5]
    return float(1 / frequency[best]), float(power[best]), frequency, power, [
        {"period_d": float(1 / frequency[i]), "power": float(power[i])} for i in indices]


def analyze(path: Path, config: AnalysisConfig):
    raw = read_lightcurve(path)
    if len(raw.time) < config.min_points:
        raise ValueError(f"Only {len(raw.time)} usable points; need {config.min_points}")
    lc = bin_lightcurve(raw, config.bin_minutes)
    period, power, frequency, powers, peaks = period_search(lc, config)
    result = {"period_d": period, "power": power, "n": len(raw.time), "n_bin": len(lc.time),
              "span_d": float(np.ptp(raw.time)), "metadata": raw.metadata, "peaks": peaks,
              "period_error_d": None, "epoch": None,
              "warnings": ["Screening peak only; no correlated-noise false-alarm calibration or physical classification."]}
    midpoint = (lc.time.min() + lc.time.max()) / 2
    for name, mask in [("first", lc.time < midpoint), ("second", lc.time >= midpoint)]:
        half = LightCurve(lc.time[mask], lc.flux[mask], lc.error[mask], lc.metadata)
        p, _, _, _, _ = period_search(half, config)
        result[name + "_period"] = p
    phase = (lc.time % period) / period
    bins = [np.median(lc.flux[(phase >= i / 50) & (phase < (i + 1) / 50)])
            for i in range(50) if np.any((phase >= i / 50) & (phase < (i + 1) / 50))]
    result["phase_amplitude_pct"] = float(100 * (np.percentile(bins, 95) - np.percentile(bins, 5)))
    result["phot_scatter_pct"] = float(100 * np.std(lc.flux))
    sap = bin_lightcurve(read_lightcurve(path, "SAP_FLUX"), config.bin_minutes)
    result["sap_power_at_period"] = float(LombScargle(sap.time, sap.flux, sap.error).power(1 / period))
    result["harmonics_d"] = [period / 2, period, period * 2]
    if period > result["span_d"] / 3:
        result["warnings"].append("Fewer than three cycles observed; long-period evidence is limited.")
    if len(lc.time) > 1 and period < 4 * np.median(np.diff(lc.time)):
        result["warnings"].append("Period is poorly sampled; inspect cadence aliases.")
    return result, (lc, frequency, powers)
