import numpy as np
from vstar.photometry import LightCurve
from vstar.adjudication import event_alias_check,transfer_short_epoch,adjudicate


def make_eclipses(equal=False,alternating=False):
    t=np.linspace(0,30,15001);phase=(t/2)%1;cycle=np.floor(t/2).astype(int)
    primary=.05+(np.where(cycle%2==0,.015,-.015) if alternating else 0)
    y=-primary*(abs((phase+.5)%1-.5)<.04)-(.05 if equal else .02)*(abs(phase-.5)<.04)
    return LightCurve(t,y,np.full(len(t),.001),{})


def test_unequal_minima_support_full_cycle_but_equal_minima_do_not():
    assert event_alias_check(make_eclipses(),2)['passed']
    assert not event_alias_check(make_eclipses(equal=True),2)['passed']


def test_alternating_primary_depths_retain_double_cycle_question():
    result=event_alias_check(make_eclipses(alternating=True),2)
    assert result['primary_same_family']['different'] and not result['passed']


def test_short_transfer_fits_no_heldout_brightness():
    t=np.linspace(0,25,10000);period=2.3
    y=.03*np.sin(2*np.pi*t/period)+.006*np.cos(4*np.pi*t/period)
    train=LightCurve(t,y,np.full(len(t),.001),{})
    u=np.linspace(100,105.5,3000);phase=(u-u[0])/period+.17
    y=.025*np.sin(2*np.pi*phase)+.005*np.cos(4*np.pi*phase)+.0001*(u-u[0])
    target=LightCurve(u,y,np.full(len(u),.001),{})
    a,_=transfer_short_epoch(train,target,period)
    changed=y.copy();changed[u-u[0]>period+.1]+=.2
    b,_=transfer_short_epoch(train,LightCurve(u,changed,target.error,{}),period)
    assert a['phase_offset_fit_first_cycle']==b['phase_offset_fit_first_cycle']
    assert a['template_amplitude']==b['template_amplitude']
    assert a['holdout_gain_vs_heldout_mean']>.8 and b['holdout_gain_vs_heldout_mean']<0
    assert not a['independent_period_measurement']


def test_failed_input_cannot_be_promoted():
    r=adjudicate({'errors':['missing sector']})
    assert r['selected_period_d'] is None and not r['confirmed_variable']


def test_product_agreement_selects_period_only():
    c={'selected_period_d':1.,'period_status':'preferred_lightcurve_cycle'}
    r=adjudicate({'errors':[],'conclusions':{'SAP':c,'PDCSAP':c},'observations':[]})
    assert r['selected_period_d']==1. and not r['target_candidate'] and not r['confirmed_variable']
