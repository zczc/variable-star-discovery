import sys
from pathlib import Path
import numpy as np
import pytest
from astropy.io import fits
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'benchmarks'))
from empirical_injection import crossfit_residual, injected_signal, prepare_residual, materialize


def test_heldout_brightness_cannot_change_its_subtracted_model():
    t = np.arange(0, 30, .003); period = .71
    y = .04*np.sin(2*np.pi*t/period) + np.random.default_rng(125).normal(0, .002, len(t))
    err = np.full(len(t), .002)
    a, pred, _ = crossfit_residual(t, y, err, period, 0)
    heldout = np.floor(t/period).astype(int) % 2 == 0
    changed = y.copy(); changed[heldout] += np.cos(t[heldout])*.2
    b, pred_b, _ = crossfit_residual(t, changed, err, period, 0)
    np.testing.assert_array_equal(pred[heldout], pred_b[heldout])
    np.testing.assert_allclose(b[heldout]-a[heldout], changed[heldout]-y[heldout])
    assert .0019 < np.std(a) < .0021


def test_phase_is_shared_across_epochs_and_full_amplitude_defined():
    p = 1.371; t = (np.arange(2000)/2000-.17)*p
    for shape in ('sine', 'unequal_eclipses'):
        spec = dict(shape=shape, period_d=p, amplitude_fraction=.03, phase=.17)
        signal = injected_signal(t, spec, 0)
        np.testing.assert_allclose(signal, injected_signal(t+50*p, spec, 0), atol=1e-12)
        assert np.ptp(signal) == pytest.approx(.03, abs=1e-8)
    assert np.all(injected_signal(t, {'shape':'zero'}, 0) == 0)


def test_materialization_retains_measurement_columns_and_marks_artificial(tmp_path):
    t = np.arange(0, 20, .01)
    y = 1000*(1+.02*np.sin(2*np.pi*t/.6)); err = np.full(len(t), 2.)
    quality = np.zeros(len(t), np.int32); quality[20] = 1
    columns = [fits.Column(name='TIME', format='D', array=t), fits.Column(name='QUALITY', format='J', array=quality)]
    for product in ('SAP', 'PDCSAP'):
        columns += [fits.Column(name=product+'_FLUX', format='D', array=y),
                    fits.Column(name=product+'_FLUX_ERR', format='D', array=err)]
    columns.append(fits.Column(name='SAP_BKG', format='D', array=np.cos(t)))
    source = tmp_path/'source.fits'; fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]).writeto(source)
    original = source.read_bytes(); residual = tmp_path/'residual.npz'
    meta = prepare_residual(source, .6, 0, residual)
    zero = {'shape':'zero'}; spec = dict(shape='sine', period_d=.731, amplitude_fraction=.01, phase=.17)
    for name, signal in [('zero', zero), ('signal', spec), ('duplicate', spec)]:
        materialize(source, residual, meta, signal, 0, tmp_path/(name+'.fits.gz'))
    assert original == source.read_bytes()
    assert (tmp_path/'signal.fits.gz').read_bytes() == (tmp_path/'duplicate.fits.gz').read_bytes()
    with fits.open(tmp_path/'signal.fits.gz') as h, fits.open(tmp_path/'zero.fits.gz') as z:
        assert h[0].header['SYNTHET']
        np.testing.assert_array_equal(h[1].data['TIME'], t)
        np.testing.assert_array_equal(h[1].data['QUALITY'], quality)
        np.testing.assert_array_equal(h[1].data['SAP_FLUX_ERR'], err)
        np.testing.assert_array_equal(h[1].data['SAP_BKG'], np.cos(t))
        good = quality == 0
        for product in ('SAP', 'PDCSAP'):
            scale = meta['products'][product]['normalization_median']
            np.testing.assert_allclose((h[1].data[product+'_FLUX']-z[1].data[product+'_FLUX'])[good]/scale,
                                       injected_signal(t[good], spec, 0), atol=1e-15)
        assert h[1].data['SAP_FLUX'][20] == y[20]
