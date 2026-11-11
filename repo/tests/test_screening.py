import numpy as np
import pytest
from vstar.models import AnalysisConfig
from vstar.photometry import LightCurve, bin_lightcurve
from vstar.periods import analyze_series
from vstar.review import review_epoch
from vstar.screening import ScreeningConfig, detrend, template_score, check_auxiliary, combine_epochs, prefer_smallest_harmonic


def test_quadratic_drift_does_not_gain_a_repeatable_template():
    rng = np.random.default_rng(5021)
    t = np.linspace(0, 26, 3000)
    y = .03*(t/26-.5)+.008*(t/26-.5)**2+rng.normal(0, .001, len(t))
    clean, _ = detrend(LightCurve(t, y, np.full(len(t), .001), {}))
    assert template_score(clean, 6.75, ScreeningConfig())["gain"] < .1


def test_cross_cycle_prediction_rejects_alternating_unequal_eclipses():
    rng = np.random.default_rng(5923)
    t = np.linspace(0, 29, 6000)
    phase = (t/2.15) % 1
    y = rng.normal(0, .0005, len(t))-.04*(abs((phase+.5) % 1-.5)<.025)-.015*(abs(phase-.5)<.025)
    clean, _ = detrend(LightCurve(t, y, np.full(len(t), .0005), {}))
    full = template_score(clean, 2.15, ScreeningConfig())["gain"]
    half = template_score(clean, 1.075, ScreeningConfig())["gain"]
    assert full > .7 and full > half+.1


def test_equal_eclipses_preserve_orbital_ambiguity():
    rng = np.random.default_rng(4055)
    t = np.linspace(0, 26, 6000)
    distance = abs((t/1.16+.5) % 1-.5)
    y = -.02*np.maximum(0, 1-distance/.035)+rng.normal(0, .0007, len(t))
    lc = LightCurve(t, y, np.full(len(t), .0007), {})
    result, _, _ = review_epoch(lc)
    assert result["periodic_detected"]
    assert result["photometric_period_d"] == pytest.approx(1.16, rel=.01)
    assert result["selected_period_d"] is None
    assert result["period_status"] == "half_double_ambiguous"


def test_auxiliary_correlation_is_review_flag_not_instrumental_proof():
    rng = np.random.default_rng(781)
    t = np.linspace(0, 25, 3500)
    signal = .02*np.sin(2*np.pi*t/.85)
    lc = LightCurve(t, signal+rng.normal(0, .001, len(t)), np.full(len(t), .001), {})
    aux = LightCurve(t, signal+rng.normal(0, .001, len(t)), np.ones(len(t)), {})
    clean, _ = detrend(lc)
    flags = check_auxiliary(clean, {"pointing": aux}, .85, ScreeningConfig())
    assert flags[0]["source_caution"]
    epoch = {"periodic_detected": True, "photometric_period_d": .85, "period_status": "preferred_lightcurve_cycle", "auxiliary": flags}
    result = combine_epochs([epoch, epoch])
    assert result["periodic_detected"] and result["decision"] == "source_caution"
    assert result["confirmed_variable"] is False and result["target_candidate"] is False


def test_missing_and_inconsistent_epochs_do_not_become_confirmations():
    a = {"periodic_detected": True, "photometric_period_d": 1., "period_status": "preferred_lightcurve_cycle"}
    assert combine_epochs([a])["decision"] == "insufficient_epochs"
    assert combine_epochs([a, dict(a, photometric_period_d=1.5)])["decision"] == "competing_periods"
    assert combine_epochs([a, dict(a, periodic_detected=False)])["periodic_detected"] is False
    assert combine_epochs([a, a])["source_status"] == "unchecked"


def test_harmonic_tie_break_does_not_bias_one_peak_shorter():
    peak = {"period_d": 5.1, "gain": .52}
    assert prefer_smallest_harmonic([peak, {"period_d": 5.06, "gain": .51}], .02) is peak
    half = {"period_d": 2.55, "gain": .51}
    assert prefer_smallest_harmonic([peak, half], .02) is half


def test_switching_dominant_modes_preserves_periodicity_and_ambiguity():
    first = {"periodic_detected": True, "photometric_period_d": .11, "period_status": "preferred_lightcurve_cycle",
             "candidates": [{"period_d": .11, "gain": .6, "qualifies": True}, {"period_d": .086, "gain": .5, "qualifies": True}]}
    second = dict(first, photometric_period_d=.086,
                  candidates=[{"period_d": .11001, "gain": .5, "qualifies": True}, {"period_d": .08601, "gain": .6, "qualifies": True}])
    result = combine_epochs([first, second])
    assert result["periodic_detected"] and result["selected_period_d"] is None
    assert result["period_status"] == "multiple_supported_periods"
    assert len(result["supported_period_groups"]) == 2
