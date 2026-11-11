import sys
from pathlib import Path
import numpy as np
import pytest
from astropy.io import fits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from standard_injection import signal,construct


def test_cadence_averaging_matches_dense_integration_at_eclipse_edges():
    spec={'shape':'unequal_eclipses','period_d':.731,'amplitude_fraction':.03,'phase':.13,'eclipse_width_phase':.02}
    # Include both minima, edges, negative phases, and a distant second epoch.
    phase=np.array([-.01,-.0099,0,.0099,.01,.49,.5,.51,2300.0099])
    t=(phase-.13)*spec['period_d'];exposure=2/1440
    numerical=np.array([np.mean(signal(x+(np.arange(10001)+.5)/10001*exposure-exposure/2,spec,0,0)) for x in t])
    np.testing.assert_allclose(signal(t,spec,0,exposure),numerical,atol=1e-9)
    np.testing.assert_allclose(signal(t,spec,0,exposure),signal(t+30*spec['period_d'],spec,0,exposure),atol=1e-10)


def test_full_amplitude_and_width_do_not_mean_half_amplitude():
    spec={'shape':'unequal_eclipses','period_d':1.,'amplitude_fraction':.03,'phase':0.,'eclipse_width_phase':.02}
    np.testing.assert_allclose(signal(np.array([0,.01,.25,.5,.51]),spec,0),[-.03,0,0,-.0135,0],atol=1e-15)
    sine=dict(spec,shape='sine')
    np.testing.assert_allclose(signal(np.array([.25,.75]),sine,0),[.015,-.015])
    assert abs(signal(np.array([0.]),spec,0,.005)[0])<.03
    with pytest.raises(ValueError):signal(np.array([0.]),dict(spec,eclipse_width_phase=0),0)


def test_direct_injection_preserves_columns_and_zero_flux_exactly(tmp_path):
    t=np.arange(0,10,.01);y=1000+3*np.sin(t)+np.arange(len(t))*.01
    quality=np.zeros(len(t),np.int32);quality[5]=1
    cols=[fits.Column(name='TIME',format='D',array=t),fits.Column(name='QUALITY',format='J',array=quality)]
    for product in ('SAP','PDCSAP'):
        cols += [fits.Column(name=product+'_FLUX',format='E',array=y),fits.Column(name=product+'_FLUX_ERR',format='E',array=np.full(len(t),2.))]
    cols.append(fits.Column(name='SAP_BKG',format='D',array=np.cos(t)))
    h=fits.HDUList([fits.PrimaryHDU(),fits.BinTableHDU.from_columns(cols)])
    for key,value in [('TIMESYS','TDB'),('TIMEUNIT','d'),('TIMEDEL',.01)]:h[1].header[key]=value
    source=tmp_path/'source.fits';h.writeto(source);before=source.read_bytes()
    spec={'shape':'sine','period_d':.731,'amplitude_fraction':.03,'phase':.13}
    construct(source,{'shape':'zero'},0,tmp_path/'zero.fits.gz')
    meta=construct(source,spec,0,tmp_path/'injected.fits.gz')
    construct(source,spec,0,tmp_path/'repeat.fits.gz')
    assert source.read_bytes()==before
    assert (tmp_path/'injected.fits.gz').read_bytes()==(tmp_path/'repeat.fits.gz').read_bytes()
    with fits.open(source) as a,fits.open(tmp_path/'zero.fits.gz') as z,fits.open(tmp_path/'injected.fits.gz') as b:
        assert b[0].header['SYNTHET']
        for name in a[1].data.names:
            np.testing.assert_array_equal(a[1].data[name],z[1].data[name])
            if name not in ('SAP_FLUX','PDCSAP_FLUX'):np.testing.assert_array_equal(a[1].data[name],b[1].data[name])
        good=quality==0
        expected=(a[1].data['SAP_FLUX'][good].astype(float)+meta['products']['SAP']['normalization_median']*signal(t[good],spec,0,.01)).astype('f4')
        np.testing.assert_array_equal(b[1].data['SAP_FLUX'][good],expected)
        assert a[1].data['SAP_FLUX'][5]==b[1].data['SAP_FLUX'][5]


def test_runner_passes_only_paths_to_detector(tmp_path,monkeypatch):
    import run_standard_injection as runner
    from vstar.io import write_json,sha256
    monkeypatch.setattr(runner,'ROOT',tmp_path);monkeypatch.setattr(runner,'OUT',tmp_path/'experiment')
    source=tmp_path/'fixture';source.write_bytes(b'fixture')
    write_json(tmp_path/'repo/benchmarks/adjudication-protocol-v01.json',{'config':{}})
    def review(paths,folder,identity):
        assert paths==[source];return {'observations':[],'errors':[]}
    monkeypatch.setattr(runner,'review_products',review);monkeypatch.setattr(runner,'adjudicate',lambda *args:{'selected_period_d':None})
    row=runner.analyze_case({'id':'case','inputs':[{'path':'fixture','sha256':sha256(source)}]})
    assert row['status']=='completed'
