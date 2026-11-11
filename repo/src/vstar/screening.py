"""Development v2: separate periodic evidence, cycle choice and source cautions.

Template cross-cycle scores are diagnostics, not calibrated false-alarm
probabilities: candidate discovery and refinement still reuse the same data.
No reference labels or catalog periods enter these functions.
"""
from dataclasses import asdict, dataclass
import numpy as np
from .models import AnalysisConfig
from .photometry import LightCurve, bin_lightcurve
from .periods import period_search, bls_search


@dataclass(frozen=True)
class ScreeningConfig:
    phase_bins: int = 96
    refinement_points: int = 31
    refinement_rounds: int = 2
    frequency_half_width_over_span: float = .4
    min_template_coverage: float = .8
    min_cv_gain: float = .20
    min_fold_gain: float = .10
    indistinguishable_gain: float = .02
    min_cycles: float = 3
    epoch_period_tolerance: float = .01
    auxiliary_correlation: float = .8
    min_auxiliary_gain: float = .2
    min_sap_gain: float = .1
    eclipse_duty_limit: float = .25
    min_secondary_depth_fraction: float = .15

    def __post_init__(self):
        if self.phase_bins < 16 or self.refinement_points < 3 or self.refinement_rounds < 1:
            raise ValueError("Insufficient template or refinement resolution")
        for key, value in asdict(self).items():
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid screening parameter {key}")
        if not 0 < self.min_fold_gain <= self.min_cv_gain < 1:
            raise ValueError("Invalid predictive improvement thresholds")


def validate_curve(lc):
    if len(lc.time) < 100 or not (len(lc.time) == len(lc.flux) == len(lc.error)):
        raise ValueError("Insufficient or unequal light-curve arrays")
    if not np.isfinite([lc.time, lc.flux, lc.error]).all() or np.any(lc.error <= 0):
        raise ValueError("Nonfinite samples or nonpositive errors")
    if np.any(np.diff(lc.time) <= 0):
        raise ValueError("Time must be strictly increasing")


def detrend(lc):
    """A single quadratic plus offsets across >0.5 d gaps; no point clipping."""
    u = (lc.time-lc.time.mean())/np.ptp(lc.time)
    segment = np.cumsum(np.r_[0, np.diff(lc.time) > .5])
    design = np.column_stack([np.ones(len(u)), u, u*u] + [(segment == s).astype(float) for s in np.unique(segment)[1:]])
    weights = 1/lc.error
    coef = np.linalg.lstsq(design*weights[:, None], lc.flux*weights, rcond=None)[0]
    trend = design@coef
    return LightCurve(lc.time, lc.flux-trend, lc.error, lc.metadata), trend


def template_predict(train_phase, train_flux, train_error, phase, bins):
    index = np.minimum((train_phase*bins).astype(int), bins-1)
    weight = 1/train_error**2
    count = np.bincount(index, minlength=bins)
    sums = np.bincount(index, weights=weight, minlength=bins)
    usable = (count >= 2) & (sums > 0)
    if usable.sum() < 3:
        return np.zeros_like(phase), float(usable.mean())
    values = np.bincount(index, weights=weight*train_flux, minlength=bins)[usable]/sums[usable]
    centers = (np.flatnonzero(usable)+.5)/bins
    return np.interp(phase, np.r_[centers-1, centers, centers+1], np.tile(values, 3)), float(usable.mean())


def template_score(lc, period, config, cross_validate=True):
    relative = (lc.time-lc.time[0])/period
    phase = relative % 1
    if cross_validate:
        folds = np.floor(relative).astype(int) % 2
        prediction = np.zeros(len(phase))
        gains, coverages = [], []
        for fold in [0, 1]:
            train, test = folds != fold, folds == fold
            if test.sum() < 20 or train.sum() < 20:
                return {"gain": -1., "fold_gains": [-1., -1.], "coverage": 0.}
            pred, coverage = template_predict(phase[train], lc.flux[train], lc.error[train], phase[test], config.phase_bins)
            prediction[test] = pred
            null = np.sum((lc.flux[test]/lc.error[test])**2)
            gain = 1-np.sum(((lc.flux[test]-pred)/lc.error[test])**2)/max(null, 1e-30)
            gains.append(float(gain)); coverages.append(coverage)
    else:
        prediction, coverage = template_predict(phase, lc.flux, lc.error, phase, config.phase_bins)
        gains, coverages = [], [coverage]
    null = np.sum((lc.flux/lc.error)**2)
    gain = 1-np.sum(((lc.flux-prediction)/lc.error)**2)/max(null, 1e-30)
    return {"gain": float(gain), "fold_gains": gains, "coverage": min(coverages)}


def refine(lc, seed, analysis, config):
    center = 1/seed
    half_width = config.frequency_half_width_over_span/np.ptp(lc.time)
    lower, upper = 1/analysis.max_period_days, 1/analysis.min_period_days
    for _ in range(config.refinement_rounds):
        grid = np.unique(np.r_[center, np.linspace(max(lower, center-half_width), min(upper, center+half_width), config.refinement_points)])
        scores = [template_score(lc, 1/f, config, cross_validate=False)["gain"] for f in grid]
        center = float(grid[int(np.argmax(scores))])
        half_width *= 2/(config.refinement_points-1)
    return 1/center


def qualifies(row, config):
    return (row["cycles"] >= config.min_cycles and not row["at_boundary"] and
            row["coverage"] >= config.min_template_coverage and row["gain"] >= config.min_cv_gain and
            min(row["fold_gains"]) >= config.min_fold_gain)


def morphology(lc, period, config):
    phase = ((lc.time-lc.time[0])/period) % 1
    grid = (np.arange(config.phase_bins)+.5)/config.phase_bins
    model, _ = template_predict(phase, lc.flux, lc.error, grid, config.phase_bins)
    baseline = float(np.median(model))
    depth = baseline-float(model.min())
    duty = float(np.mean(model < baseline-.3*depth)) if depth > 0 else 1.
    primary = int(np.argmin(model))
    opposite = ((grid-grid[primary]+.5) % 1-.5)
    secondary = model[abs(opposite) > .30]
    secondary_ratio = (baseline-float(secondary.min()))/depth if depth > 0 and len(secondary) else 0.
    return {"eclipse_like": bool(duty < config.eclipse_duty_limit), "low_flux_duty": duty,
            "secondary_depth_fraction": float(secondary_ratio),
            "note": "Shape heuristic, not a physical classification. Secondary search covers phase separations 0.3–0.5."}


def analyze_epoch(raw, baseline, analysis=None, config=None):
    analysis, config = analysis or AnalysisConfig(use_bls=True), config or ScreeningConfig()
    validate_curve(raw)
    binned = bin_lightcurve(raw, analysis.bin_minutes)
    clean, trend = detrend(binned)
    _, _, _, _, peaks = period_search(clean, analysis)
    box = bls_search(clean, analysis)
    seeds = [p["period_d"] for p in baseline["peaks"][:3]+peaks[:3]] + [baseline["bls"]["period_d"], box["period_d"]]
    trials = []
    for seed in seeds:
        for factor in [.5, 1, 2]:
            p = seed*factor
            if analysis.min_period_days <= p <= analysis.max_period_days and not any(abs(p/q-1) < .003 for q in trials):
                trials.append(p)
    candidates = []
    for seed in trials:
        p = refine(clean, seed, analysis, config)
        if any(abs(p/r["period_d"]-1) < .001 for r in candidates):
            continue
        row = {"period_d": float(p), "seed_period_d": float(seed), **template_score(clean, p, config),
               "cycles": float(np.ptp(clean.time)/p),
               "at_boundary": bool(np.isclose(p, analysis.min_period_days, rtol=1e-5) or np.isclose(p, analysis.max_period_days, rtol=1e-5))}
        row["qualifies"] = bool(qualifies(row, config))
        candidates.append(row)
    candidates.sort(key=lambda c: c["gain"], reverse=True)
    good = [c for c in candidates if c["qualifies"]]
    result = {"candidates": candidates, "periodic_detected": bool(good), "selected_period_d": None,
              "photometric_period_d": None, "period_status": "not_established", "shape": None,
              "trend_fraction_of_variance": float(1-np.var(clean.flux)/max(np.var(binned.flux), 1e-30)),
              "notes": ["Diagnostic cross-cycle prediction reuses discovery data; not a calibrated significance or period uncertainty.",
                        "A quadratic and gap offsets may attenuate long signals; no samples were removed as flux outliers."]}
    if good:
        best_gain = good[0]["gain"]
        # Prefer the smallest repeating pattern among statistically unresolved aliases.
        near = [c for c in good if c["gain"] >= best_gain-config.indistinguishable_gain]
        chosen = min((c for c in near if min(abs(c["period_d"]/(good[0]["period_d"]*h)-1) for h in [.5, 1, 2]) < .015), key=lambda c: c["period_d"])
        p = chosen["period_d"]
        competing = any(min(abs(c["period_d"]/(p*h)-1) for h in [.5, 1, 2]) >= .015 for c in near)
        shape = morphology(clean, p, config)
        half = template_score(clean, p/2, config)
        ambiguous = shape["eclipse_like"] and (shape["secondary_depth_fraction"] < config.min_secondary_depth_fraction or
                                               chosen["gain"]-half["gain"] < config.indistinguishable_gain)
        result.update(photometric_period_d=p, selected_period_d=None if ambiguous or competing else p,
                      period_status="competing_aliases" if competing else "half_double_ambiguous" if ambiguous else "preferred_lightcurve_cycle",
                      shape=shape, chosen_candidate=chosen, half_period_gain=half["gain"],
                      cycle_alternatives_d=[p, 2*p] if ambiguous else [p])
    return result, (binned, clean, trend)


def check_auxiliary(clean, auxiliary, period, config):
    diagnostics = []
    for name, channel in auxiliary.items():
        valid = np.isfinite(channel.time) & np.isfinite(channel.flux)
        time, flux = channel.time[valid], channel.flux[valid]
        if len(time) < 100 or np.any(np.diff(time) <= 0):
            diagnostics.append({"name": name, "status": "unavailable"}); continue
        mask = (clean.time >= time[0]) & (clean.time <= time[-1])
        # Avoid interpolating across gaps or long runs of missing auxiliary data.
        right = np.clip(np.searchsorted(time, clean.time), 0, len(time)-1)
        left = np.maximum(right-1, 0)
        distance = np.minimum(abs(clean.time-time[left]), abs(clean.time-time[right]))
        mask &= distance <= .015
        if mask.mean() < .8:
            diagnostics.append({"name": name, "status": "insufficient_overlap"}); continue
        samples = np.interp(clean.time[mask], time, flux)
        aux, _ = detrend(LightCurve(clean.time[mask], samples, np.ones(mask.sum()), {}))
        if np.std(aux.flux) <= 1e-12 or np.std(clean.flux[mask]) <= 1e-12:
            diagnostics.append({"name": name, "status": "constant_or_missing"}); continue
        correlation = float(np.corrcoef(clean.flux[mask], aux.flux)[0, 1])
        score = template_score(aux, period, config)
        caution = abs(correlation) >= config.auxiliary_correlation and score["gain"] >= config.min_auxiliary_gain
        diagnostics.append({"name": name, "status": "correlated_periodic_channel" if caution else "no_strong_correlation",
                            "correlation": correlation, "periodic_gain": score["gain"], "source_caution": bool(caution),
                            "note": "Correlation motivates source review; stellar variability can itself shift centroids. This is not proof of instrumental origin."})
    return diagnostics


def combine_epochs(epochs, config=None, source_evidence=None):
    config = config or ScreeningConfig()
    detected = [r for r in epochs if r["periodic_detected"]]
    result = {"periodic_detected": False, "selected_period_d": None, "photometric_period_d": None,
              "period_status": "not_established", "decision": "no_stable_signal", "source_status": "unchecked",
              "confirmed_variable": False, "source_evidence": source_evidence or [], "warnings": []}
    if len(epochs) < 2:
        result["decision"] = "insufficient_epochs"; return result
    if len(detected) != len(epochs):
        result["decision"] = "not_repeated_in_all_epochs"; return result
    periods = [r["photometric_period_d"] for r in epochs]
    spread = (max(periods)-min(periods))/np.median(periods)
    result["fractional_period_spread"] = float(spread)
    if spread > config.epoch_period_tolerance:
        result["decision"] = "competing_periods"; return result
    ambiguous = any(r["period_status"] != "preferred_lightcurve_cycle" for r in epochs)
    p = float(np.median(periods))
    result.update(periodic_detected=True, photometric_period_d=p, selected_period_d=None if ambiguous else p,
                  period_status="competing_aliases" if any(r["period_status"] == "competing_aliases" for r in epochs) else "half_double_ambiguous" if ambiguous else "preferred_lightcurve_cycle",
                  decision="period_ambiguous" if ambiguous else "periodic_source_unchecked")
    cautions = [a for r in epochs for a in r.get("auxiliary", []) if a.get("source_caution")]
    product_disagreement = any(r.get("sap_check", {}).get("gain", 1) < config.min_sap_gain for r in epochs)
    evidence = source_evidence or []
    if any(s.get("status") == "likely_contaminated" for s in evidence):
        result.update(source_status="likely_contaminated", decision="likely_contaminated")
    elif cautions or product_disagreement:
        result.update(source_status="needs_review", decision="source_caution")
        result["warnings"].append("Periodic auxiliary correlation or SAP/PDC disagreement; cannot attribute the signal automatically.")
    elif len(evidence) >= len(epochs) and all(s.get("status") == "consistent_with_target" for s in evidence):
        result.update(source_status="supported_at_tess_resolution", decision="period_ambiguous" if ambiguous else "periodic_target_supported")
    result["target_candidate"] = result["decision"] in {"periodic_source_unchecked", "periodic_target_supported", "period_ambiguous"}
    return result
