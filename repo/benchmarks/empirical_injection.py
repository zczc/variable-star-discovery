"""Reproducible post-reduction injections into cross-fitted empirical residuals.

These residuals retain stellar model errors: they are NOT labeled quiet stars.
The detector and its v4 thresholds are not changed by this benchmark.
"""
from pathlib import Path
import gzip
import io
import numpy as np
from astropy.io import fits

PRODUCTS = ('SAP', 'PDCSAP')


def fourier_design(time, period, origin, harmonics):
    phase = 2*np.pi*((np.asarray(time)-origin)/period % 1)
    return np.column_stack([np.ones(len(phase))] +
                           [fn(k*phase) for k in range(1, harmonics+1) for fn in (np.sin, np.cos)])


def crossfit_residual(time, flux, error, period, origin, harmonics=12):
    """Predict each cycle using only cycles of opposite parity.

No clipping, point shuffling, rescaling, or extra noise is applied. A constant
and 12 Fourier harmonics fit each training group; only the periodic terms are
subtracted from its held-out group. Correlations/model errors may survive.
"""
    time, flux, error = map(np.asarray, (time, flux, error))
    if period <= 0 or harmonics < 1 or len(time) != len(flux) or len(time) != len(error):
        raise ValueError('Invalid residual construction parameters')
    if not all(np.all(np.isfinite(x)) for x in (time, flux, error)) or np.any(error <= 0):
        raise ValueError('Residual construction needs finite data and positive errors')
    cycles = np.floor((time-origin)/period).astype(np.int64)
    design = fourier_design(time, period, origin, harmonics)
    prediction = np.empty_like(flux, dtype=float)
    fits_meta = []
    for parity in (0, 1):
        train = cycles % 2 != parity
        test = ~train
        if min(train.sum(), test.sum()) < 4*design.shape[1] or len(np.unique(cycles[train])) < 3:
            raise ValueError('Insufficient independent cycles for cross-fitting')
        weights = 1/error[train]
        coef, _, rank, _ = np.linalg.lstsq(design[train]*weights[:, None], flux[train]*weights, rcond=None)
        if rank != design.shape[1]:
            raise ValueError('Rank-deficient periodic template')
        prediction[test] = design[test, 1:] @ coef[1:]
        fits_meta.append({'held_out_cycle_parity': parity, 'training_points': int(train.sum()),
                         'heldout_points': int(test.sum()), 'coefficients': coef.tolist()})
    return flux-prediction, prediction, fits_meta


def injected_signal(time, spec, origin):
    """Amplitude is full peak-to-peak fractional source-median flux, not semiamplitude."""
    if spec['shape'] == 'zero':
        return np.zeros(len(time))
    period, amplitude = spec['period_d'], spec['amplitude_fraction']
    if period <= 0 or amplitude < 0:
        raise ValueError('Invalid injected signal')
    phase = ((np.asarray(time)-origin)/period + spec['phase']) % 1
    if spec['shape'] == 'sine':
        return .5*amplitude*np.sin(2*np.pi*phase)
    if spec['shape'] == 'unequal_eclipses':
        # Smooth compact dips: full widths 0.08 and 0.08 of a cycle; ratio 0.45.
        def dip(center):
            distance = abs((phase-center+.5) % 1-.5)
            return np.where(distance < .04, .5*(1+np.cos(np.pi*distance/.04)), 0.)
        return -amplitude*(dip(0)+.45*dip(.5))
    raise ValueError('Unknown signal shape')


def scatter_summary(time, values):
    close = np.diff(time) < 2*np.median(np.diff(time))
    a, b = values[:-1][close], values[1:][close]
    return {'rms_fraction': float(np.std(values)),
            'mad_sigma_fraction': float(1.4826*np.median(abs(values-np.median(values)))),
            'adjacent_correlation_excluding_gaps': float(np.corrcoef(a, b)[0, 1])}


def prepare_residual(source, parent_period, origin, out, harmonics=12):
    arrays = {}; metadata = {'parent_period_d': parent_period, 'origin_btjd': origin, 'products': {}}
    with fits.open(source, memmap=False) as h:
        data = h[1].data
        time = np.asarray(data['TIME'], float)
        for product in PRODUCTS:
            y, err = [np.asarray(data[product+suffix], float) for suffix in ('_FLUX', '_FLUX_ERR')]
            good = np.isfinite(time) & np.isfinite(y) & np.isfinite(err) & (err > 0) & (data['QUALITY'] == 0)
            median = float(np.median(y[good]))
            if median <= 0:
                raise ValueError('Nonpositive source normalization')
            normalized, errors = y[good]/median-1, err[good]/median
            residual, prediction, fit = crossfit_residual(time[good], normalized, errors, parent_period, origin, harmonics)
            arrays[product+'_indices'] = np.flatnonzero(good)
            arrays[product+'_residual'] = residual
            arrays[product+'_prediction'] = prediction
            metadata['products'][product] = {'normalization_median': median, 'fit': fit, 'samples': int(good.sum()),
                'source': scatter_summary(time[good], normalized), 'residual': scatter_summary(time[good], residual),
                'median_formal_error_fraction': float(np.median(errors))}
    np.savez_compressed(out, **arrays)
    return metadata


def materialize(source, residual_path, residual_meta, spec, origin, output):
    """Full copy with modified usable flux only; all other columns remain intact.

Gzip mtime=0 and unchanged FITS headers make identical inputs byte reproducible.
SYNTHET flags the file as artificial; it must never be cited as a raw observation.
"""
    with fits.open(source, memmap=False) as original, np.load(residual_path) as residual:
        h = fits.HDUList([x.copy() for x in original])
        h[0].header['SYNTHET'] = (True, 'ARTIFICIAL residual plus injected signal')
        h[0].header['HISTORY'] = 'Empirical injection v01; NOT a raw TESS observation.'
        time = np.asarray(h[1].data['TIME'], float)
        for product in PRODUCTS:
            indices = residual[product+'_indices']
            median = residual_meta['products'][product]['normalization_median']
            flux = median*(1+residual[product+'_residual']+injected_signal(time[indices], spec, origin))
            if not np.all(np.isfinite(flux)) or np.min(flux) <= 0:
                raise ValueError('Invalid generated flux')
            h[1].data[product+'_FLUX'][indices] = flux
        for extension in h:
            for key in ('CHECKSUM', 'DATASUM'):
                if key in extension.header: del extension.header[key]
        buffer = io.BytesIO(); h.writeto(buffer)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
            compressed.write(buffer.getvalue())
        h.close()
