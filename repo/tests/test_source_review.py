import numpy as np
import pytest
from vstar.source_review import harmonic_map,summarize_maps,route_review


def test_harmonic_maps_locate_signal_when_fundamental_cancels():
    t=np.arange(0,20,.01);period=2.
    # Two equal minima per declared cycle: fundamental alone contains no signal.
    reference=.02*np.cos(4*np.pi*t/period)
    cube=np.broadcast_to((100+.1*t)[:,None,None],(len(t),6,6)).copy()
    cube[:,2,4]+=3000*reference
    signal=harmonic_map(t,cube,reference,period)
    assert np.unravel_index(signal.argmax(),signal.shape)==(2,4)
    assert signal[2,4]>20


def test_neighbor_requires_position_period_and_split_consistency():
    m=np.zeros((6,6));m[1,4]=10;maps={k:m for k in ['full','first_half','second_half']}
    neighbor=[{'name':'neighbor','pixel':[4.1,1.1],'period_d':1.}]
    assert summarize_maps(maps,[1,4],neighbor,.5)['status']=='likely_neighbor_contamination'
    assert summarize_maps(maps,[4,1],neighbor,.5)['status']=='consistent_with_target'
    assert summarize_maps(maps,[1,4],neighbor,.713)['status']=='off_target_signal'
    other=np.zeros((6,6));other[4,1]=10
    assert summarize_maps(dict(maps,second_half=other),[1,4],neighbor,.5)['status']=='inconsistent_pixel_maps'


def observation(sector,location='consistent_with_target',channel=None):
    checks=[{'name':n,'status':'no_strong_correlation','source_caution':False} for n in ['SAP_BKG','POS_CORR1','POS_CORR2']]
    if channel:checks.append({'name':channel,'status':'correlated_periodic_channel','source_caution':True})
    return {'sector':sector,'pixels':{'status':location},'auxiliary':{'SAP':checks,'PDCSAP':checks}}


def test_target_control_can_reach_manual_review_but_never_confirmation():
    good=[observation(1),observation(2)]
    r=route_review(.7,good)
    assert r['eligible_for_manual_target_review'] and r['route']=='manual_target_review'
    assert not r['confirmed_variable'] and not r['submission_ready']
    assert route_review(None,good)['route']=='period_review_required'
    assert route_review(.7,good,['bad checksum'])['route']=='analysis_failed'


def test_instrument_channels_block_but_centroid_alone_is_not_instrument_proof():
    for name in ['SAP_BKG','POS_CORR1','POS_CORR2']:
        r=route_review(.7,[observation(1,channel=name),observation(2)])
        assert r['route']=='instrument_review_required' and not r['eligible_for_manual_target_review']
    r=route_review(.7,[observation(1,channel='MOM_CENTR1'),observation(2)])
    assert r['route']=='manual_target_review' and r['centroid_cautions'] and not r['instrument_cautions']
    assert route_review(.7,[observation(1,'likely_neighbor_contamination'),observation(2)])['route']=='exclude_signal_from_target'


def test_missing_pixels_or_channels_do_not_become_passed_source_checks():
    a=observation(1);a['pixels']=None
    assert route_review(.7,[a,observation(2)])['route']=='source_evidence_required'
    b=observation(2);b['auxiliary']['SAP']=[]
    assert route_review(.7,[observation(1),b])['route']=='source_evidence_required'


def test_zero_variance_auxiliary_does_not_clear_instrument_review():
    a=observation(1);a['auxiliary']['SAP'][0]['status']='constant_or_missing'
    assert route_review(.7,[a,observation(2)])['route']=='source_evidence_required'


def test_equal_eclipse_challenge_repeats_at_half_input_cycle():
    from pathlib import Path
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
    from precision_challenges import flux_signal
    spec={'kind':'equal_eclipses','period_d':1.371,'phase':.13,'amplitude_fraction':.03}
    t=np.linspace(0,15,5000)
    np.testing.assert_allclose(flux_signal(t,spec,0,2/1440),flux_signal(t+spec['period_d']/2,spec,0,2/1440),atol=1e-12)
