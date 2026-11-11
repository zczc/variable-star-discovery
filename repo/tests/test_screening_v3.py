import numpy as np
import pytest
from vstar.photometry import LightCurve
from vstar.screening import detrend, template_score
from vstar.screening_v3 import (ScreeningConfig, harmonic_related, prefer_harmonic,
                               leave_cycle_score, conditional_score, combine_epochs)


def curve(signal, time, sigma=.001):
    return detrend(LightCurve(time, signal, np.full(len(time), sigma), {}))[0]


def test_integer_family_and_same_peak_refinement():
    cfg = ScreeningConfig()
    assert harmonic_related(1, 3, cfg) and harmonic_related(1, 4, cfg)
    assert not harmonic_related(1, 1.5, cfg)
    best = {"period_d": 4.004, "gain": .9}
    peak = {"period_d": 4., "gain": .89}
    assert prefer_harmonic([best, peak], cfg) is best
    fundamental = {"period_d": 1., "gain": .89}
    assert prefer_harmonic([best, peak, fundamental], cfg) is fundamental
    assert prefer_harmonic([best, {"period_d": 1., "gain": .6}], cfg) is best


def test_conditional_check_removes_weak_alias_but_retains_second_mode():
    t = np.linspace(0, 26, 6000); rng = np.random.default_rng(6159)
    main = .03*np.sin(2*np.pi*t/.173)
    first = curve(main+rng.normal(0, .001, len(t)), t)
    cfg = ScreeningConfig()
    alias = conditional_score(first, .173, .1702, cfg)
    assert not alias['supported']
    # The second signal contributes enough variance after removing the first.
    two = curve(main+.02*np.sin(2*np.pi*t/.223)+rng.normal(0, .001, len(t)), t)
    assert conditional_score(two, .173, .223, cfg)['supported']
    assert conditional_score(two, .223, .173, cfg)['supported']


def test_leave_cycle_handles_complementary_phase_gaps():
    rng = np.random.default_rng(927); t = np.linspace(0, 24, 7200)
    cyc = np.floor(t/6).astype(int); ph = (t/6) % 1
    # Different cycles miss different regions; pooled training retains coverage.
    mask = ~(((cyc == 0) & (ph > .4) & (ph < .65)) | ((cyc == 2) & (ph > .4) & (ph < .65)))
    t, ph = t[mask], ph[mask]
    signal = -.04*np.maximum(0, 1-abs((ph-.2+.5)%1-.5)/.025)
    lc = curve(signal+rng.normal(0, .001, len(t)), t)
    cfg = ScreeningConfig()
    # Drop the one-point final cycle; input time coverage remains ~4 cycles.
    lc = LightCurve(lc.time[:-1], lc.flux[:-1], lc.error[:-1], {})
    assert template_score(lc, 6, cfg)['coverage'] < cfg.min_template_coverage
    score = leave_cycle_score(lc, 6, cfg)
    assert score['coverage'] >= .8 and score['gain'] > .5 and score['predictive_cycles'] >= 3


def test_one_isolated_dip_cannot_validate_three_cycles():
    t = np.linspace(0, 24, 7200, endpoint=False); rng = np.random.default_rng(184)
    lc = curve(-.05*np.maximum(0, 1-abs(t-8.2)/.12)+rng.normal(0,.001,len(t)),t)
    score = leave_cycle_score(lc,6,ScreeningConfig())
    assert score['predictive_cycles'] < 3


def epoch(chosen, gains):
    return {'periodic_detected':True,'photometric_period_d':chosen,'period_status':'preferred_lightcurve_cycle',
            'candidates':[{'period_d':p,'gain':g,'qualifies':True} for p,g in gains], 'conditional_comparisons':[]}


def test_epoch_harmonic_disagreement_abstains_instead_of_averaging():
    a = epoch(3.38,[(3.38,.93),(6.76,.935)])
    b = epoch(6.76,[(3.38,.84),(6.76,.92)])
    out=combine_epochs([a,b])
    assert out['periodic_detected'] and out['selected_period_d'] is None
    assert out['period_status']=='cross_epoch_harmonic_conflict'
    assert not out['confirmed_variable']


def test_weak_competitor_does_not_force_abstention_and_source_caution_remains():
    a=epoch(.173,[(.173,.77),(.346,.78),(.3402,.25)])
    a['auxiliary']=[{'source_caution':True}]
    out=combine_epochs([a,a])
    assert out['selected_period_d']==pytest.approx(.173)
    assert out['decision']=='source_caution' and not out['target_candidate']


def test_equal_eclipse_status_is_not_erased_by_harmonic_grouping():
    a=epoch(.9,[(.9,.9),(1.8,.9)])
    a['period_status']='half_double_ambiguous'
    out=combine_epochs([a,a])
    assert out['selected_period_d'] is None and out['period_status']=='half_double_ambiguous'
