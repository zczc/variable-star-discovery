"""Opt-in development v3. Old v2 science is preserved in screening.py.

Conditional and leave-one-cycle-out scores reuse search data and are diagnostic,
not false-alarm probabilities. No labels or reference periods enter decisions.
"""
from dataclasses import dataclass, asdict
import numpy as np
from . import screening as v2
from .photometry import LightCurve


@dataclass(frozen=True)
class ScreeningConfig(v2.ScreeningConfig):
    max_harmonic: int = 8
    harmonic_tolerance: float = .015
    min_conditional_variance: float = .05
    min_predictive_cycles: int = 3

    def __post_init__(self):
        super().__post_init__()
        if self.max_harmonic != int(self.max_harmonic) or self.min_predictive_cycles != int(self.min_predictive_cycles):
            raise ValueError("Harmonic order and cycle count must be integers")


def harmonic_related(a, b, config):
    ratio = max(a, b)/min(a, b)
    return any(abs(ratio/n-1) < config.harmonic_tolerance for n in range(1, config.max_harmonic+1))


def prefer_harmonic(candidates, config):
    best = max(candidates, key=lambda c: c["gain"])
    # Only prefer a genuinely shorter integer alias; same-peak refinements use gain.
    shorter = [c for c in candidates if c["period_d"] < best["period_d"]/1.5
               and harmonic_related(c["period_d"], best["period_d"], config)
               and c["gain"] >= best["gain"]-config.indistinguishable_gain]
    if not shorter:
        return best
    shortest = min(shorter, key=lambda c: c["period_d"])
    return max([c for c in shorter if abs(c["period_d"]/shortest["period_d"]-1) < .015], key=lambda c: c["gain"])


def leave_cycle_score(lc, period, config):
    """Predict each observed cycle without any points from that cycle in training.

Require three separately predicted cycles, not a fictitious positive score in
unobserved events. Negative and partial cycles remain in the total statistic.
"""
    relative = (lc.time-lc.time[0])/period
    phase, cycle = relative % 1, np.floor(relative).astype(int)
    prediction = np.zeros(len(phase))
    records = []
    for label in np.unique(cycle):
        test = cycle == label; train = ~test
        if test.sum() < 20 or train.sum() < 100:
            return {"gain": -1., "coverage": 0., "fold_gains": [-1., -1.], "cycles": [], "predictive_cycles": 0}
        pred, coverage = v2.template_predict(phase[train], lc.flux[train], lc.error[train], phase[test], config.phase_bins)
        prediction[test] = pred
        null = np.sum((lc.flux[test]/lc.error[test])**2)
        gain = 1-np.sum(((lc.flux[test]-pred)/lc.error[test])**2)/max(null, 1e-30)
        records.append({"cycle": int(label), "samples": int(test.sum()), "gain": float(gain), "coverage": coverage})
    null = np.sum((lc.flux/lc.error)**2)
    return {"gain": float(1-np.sum(((lc.flux-prediction)/lc.error)**2)/max(null, 1e-30)),
            "coverage": min(r["coverage"] for r in records), "fold_gains": [r["gain"] for r in records], "cycles": records,
            "predictive_cycles": sum(r["gain"] >= config.min_fold_gain and r["coverage"] >= config.min_template_coverage for r in records)}


def conditional_score(lc, base_period, trial_period, config):
    phase = ((lc.time-lc.time[0])/base_period) % 1
    prediction, _ = v2.template_predict(phase, lc.flux, lc.error, phase, config.phase_bins)
    residual = LightCurve(lc.time, lc.flux-prediction, lc.error, lc.metadata)
    score = v2.template_score(residual, trial_period, config)
    fraction = np.sum((residual.flux/lc.error)**2)/max(np.sum((lc.flux/lc.error)**2), 1e-30)
    score["original_variance_gain"] = float(score["gain"]*fraction)
    score["supported"] = bool(score["coverage"] >= config.min_template_coverage and score["gain"] >= config.min_cv_gain
                               and min(score["fold_gains"]) >= config.min_fold_gain
                               and score["original_variance_gain"] >= config.min_conditional_variance)
    return score


def analyze_epoch(raw, baseline, analysis=None, config=None):
    config = config or ScreeningConfig()
    result, diagnostic = v2.analyze_epoch(raw, baseline, analysis, config)
    clean = diagnostic[1]
    result["algorithm_revision"] = "v3.0-development"
    result["v2_period_status"] = result["period_status"]
    for row in result["candidates"]:
        row["score_method"] = "alternate_cycles"
        # Only address missing phase coverage of sparse, eclipse-shaped candidates.
        if (not row["qualifies"] and row["coverage"] < config.min_template_coverage
                and row["cycles"] >= config.min_cycles and not row["at_boundary"]
                and v2.morphology(clean, row["period_d"], config)["eclipse_like"]):
            loo = leave_cycle_score(clean, row["period_d"], config)
            row["leave_cycle_check"] = loo
            if (loo["gain"] >= config.min_cv_gain and loo["coverage"] >= config.min_template_coverage
                    and loo["predictive_cycles"] >= config.min_predictive_cycles):
                row["alternate_cycle_score"] = {k: row[k] for k in ["gain", "coverage", "fold_gains"]}
                row.update({k: loo[k] for k in ["gain", "coverage", "fold_gains"]})
                row.update(qualifies=True, score_method="leave_one_cycle_out")
    result["candidates"].sort(key=lambda c: c["gain"], reverse=True)
    good = [c for c in result["candidates"] if c["qualifies"]]
    result.update(periodic_detected=bool(good), selected_period_d=None, photometric_period_d=None,
                  period_status="not_established", conditional_comparisons=[], notes=result["notes"]+[
                      "Integer aliases through order 8 share a family; this does not identify a physical mode.",
                      "Conditional residual checks require >=5% of original weighted variance; weaker real modes can be missed.",
                      "Sparse eclipses can use leave-one-cycle-out coverage with at least three predictive cycles."])
    if not good:
        return result, diagnostic
    chosen = prefer_harmonic(good, config)
    for base in good:
        for trial in good:
            if not harmonic_related(base["period_d"], trial["period_d"], config):
                result["conditional_comparisons"].append({"base_period_d": base["period_d"], "trial_period_d": trial["period_d"],
                                                          **conditional_score(clean, base["period_d"], trial["period_d"], config)})
    p = chosen["period_d"]
    competing = any(c["base_period_d"] == p and c["supported"] for c in result["conditional_comparisons"])
    shape = v2.morphology(clean, p, config)
    half = v2.template_score(clean, p/2, config)
    orbital_ambiguous = shape["eclipse_like"] and (shape["secondary_snr_proxy"] < config.min_secondary_snr
                                                 or chosen["gain"]-half["gain"] < config.indistinguishable_gain)
    result.update(photometric_period_d=p, selected_period_d=None if orbital_ambiguous or competing else p,
                  period_status="competing_aliases" if competing else "half_double_ambiguous" if orbital_ambiguous else "preferred_lightcurve_cycle",
                  shape=shape, chosen_candidate=chosen, half_period_gain=half["gain"],
                  cycle_alternatives_d=[p, 2*p] if orbital_ambiguous else [p])
    return result, diagnostic


def combine_epochs(epochs, config=None, source_evidence=None):
    config = config or ScreeningConfig()
    result = v2.combine_epochs(epochs, config, source_evidence)
    result["algorithm_revision"] = "v3.0-development"
    if not result["periodic_detected"]:
        return result
    groups = result["supported_period_groups"]
    chosen = prefer_harmonic(groups, config)
    def member(epoch, period):
        pool = [c for c in epoch.get("candidates", []) if c["qualifies"] and abs(c["period_d"]/period-1) <= config.epoch_period_tolerance]
        return max(pool, key=lambda c: c["gain"])["period_d"] if pool else period
    for group in groups:
        group["harmonic_of_preferred"] = harmonic_related(group["period_d"], chosen["period_d"], config)
        checks = []
        if not group["harmonic_of_preferred"]:
            for epoch in epochs:
                base, trial = member(epoch, chosen["period_d"]), member(epoch, group["period_d"])
                checks.append(next((c for c in epoch.get("conditional_comparisons", [])
                                    if c["base_period_d"] == base and c["trial_period_d"] == trial), {"supported": False}))
        group["conditional_checks"] = checks
        group["independent_competitor"] = bool(checks and all(c["supported"] for c in checks))
    multiple = any(g["independent_competitor"] for g in groups)
    # Never average away a disagreement between individually preferred integer aliases.
    epoch_periods = [r["photometric_period_d"] for r in epochs]
    alias_conflict = any(abs(p/chosen["period_d"]-1) > config.epoch_period_tolerance
                         and harmonic_related(p, chosen["period_d"], config) for p in epoch_periods)
    orbital_ambiguous = any(r["period_status"] == "half_double_ambiguous" for r in epochs)
    ambiguous = multiple or alias_conflict or orbital_ambiguous
    status = ("multiple_supported_periods" if multiple else "cross_epoch_harmonic_conflict" if alias_conflict
              else "half_double_ambiguous" if orbital_ambiguous else "preferred_lightcurve_cycle")
    result.update(photometric_period_d=chosen["period_d"], selected_period_d=None if ambiguous else chosen["period_d"],
                  period_status=status, fractional_period_spread=chosen["fractional_spread"],
                  epoch_preferred_periods_d=epoch_periods)
    result["warnings"] = [w for w in result["warnings"] if not w.startswith("Several nonharmonic")]
    if multiple:
        result["warnings"].append("Nonharmonic competitors survive subtraction of the preferred template in every epoch; no physical mode classification.")
    if alias_conflict:
        result["warnings"].append("Epochs prefer different integer aliases; averaged scores cannot resolve the full cycle.")
    if result["source_status"] not in {"likely_contaminated", "needs_review"}:
        result["decision"] = "period_ambiguous" if ambiguous else "periodic_target_supported" if result["source_status"] == "supported_at_tess_resolution" else "periodic_source_unchecked"
    result["target_candidate"] = result["decision"] in {"periodic_source_unchecked", "periodic_target_supported", "period_ambiguous"}
    return result
