import numpy as np
import pytest
from vstar.photometry import LightCurve
from vstar.eclipse_events import measure_events,EventConfig


def test_local_brackets_recover_alternation_under_linear_baseline():
    t=np.linspace(0,20,20001);distance=abs((t-.5+.5)%1-.5)
    cycles=np.rint(t-.5).astype(int)
    depth=np.where(cycles%2==0,.05,.02)
    trend=.002*t
    y=trend-depth*(distance<.07)
    lc=LightCurve(t,y,np.full(len(t),.0001),{})
    res,_=measure_events(lc,1,.5)
    assert res['summary']['measured_events']==20
    # Depth is divided by the actual local total flux, rather than median flux.
    for r in res['events']:
        mask=abs(t-r['center_input_time'])<=.06
        expected=np.mean((.05 if r['cycle']%2==0 else .02)/(1+.002*t[mask]))
        assert r['depth_fraction']==pytest.approx(expected,rel=1e-6)
    assert res['summary']['bootstrap_interval_95'][0]>.025


def test_repeated_equal_events_have_no_depth_alternation():
    t=np.linspace(0,20,20001);dist=abs((t-.5+.5)%1-.5)
    lc=LightCurve(t,-.04*(dist<.07),np.full(len(t),.001),{})
    res,_=measure_events(lc,1,.5)
    assert abs(res['summary']['paired_difference'])<1e-10


def test_missing_side_windows_are_recorded_not_interpolated_as_events():
    t=np.linspace(0,10,10001);keep=~((t>3.02)&(t<3.16));t=t[keep]
    lc=LightCurve(t,-.04*(abs((t-.5+.5)%1-.5)<.07),np.full(len(t),.001),{})
    res,_=measure_events(lc,1,.5)
    assert any(r['status']=='missing_bracketing_data' for r in res['events'])
    assert res['summary']['missing_events']>=1


def test_event_windows_must_not_cross_neighboring_minima():
    with pytest.raises(ValueError):EventConfig(side_outer=.6)
