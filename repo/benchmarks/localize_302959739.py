"""Exploratory PRF localization, separate from the frozen variability detector."""
import argparse
import csv
import importlib.util
import io
from pathlib import Path
import warnings

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
import astropy.units as u
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import minimize, nnls

from vstar.io import read_json, write_json, sha256, now
from vstar.photometry import read_lightcurve
from vstar.source_review import harmonic_map

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'repo/runs/tic-302959739-followup-2026-11-22'
TARGET = '5221973868734158976'
NEIGHBOR = '5221973868731579136'


def plane(shape):
    y, x = np.indices(shape)
    return np.column_stack([np.ones(x.size), x.ravel() - x.mean(), y.ravel() - y.mean()])


def fit_source(model, signal, noise, center, fixed=None):
    """Variable projection: nonnegative source amplitude plus a nuisance plane."""
    center = np.asarray(center, float)
    shape = signal.shape
    if signal.ndim != 2 or noise.shape != shape or not np.isfinite(signal).all() or not np.isfinite(noise).all() or np.any(noise <= 0):
        raise ValueError('Need finite signal and positive pixel weights')
    yy, xx = np.indices(shape)
    mask = (xx-center[0])**2 + (yy-center[1])**2 <= 4**2
    w = 1 / np.maximum(noise[mask], np.median(noise[mask]))
    nuisance = plane(shape)[mask.ravel()] * w[:, None]
    q, _ = np.linalg.qr(nuisance)
    data = signal[mask] * w
    residual_data = data - q @ (q.T @ data)

    def evaluate(xy, details=False):
        prf = model.locate(*xy, shape)
        p = prf[mask] * w
        p = p - q @ (q.T @ p)
        amp = max(0., float(p @ residual_data / max(p @ p, 1e-30)))
        residual = residual_data - amp*p
        loss = float(residual @ residual)
        if not details:
            return loss
        background = np.linalg.lstsq(nuisance, (signal[mask]-amp*prf[mask])*w, rcond=None)[0]
        return {'xy': list(map(float, xy)), 'amplitude': amp, 'residual_loss': loss,
                'position_identifiable': bool(amp > 1e-10 and np.linalg.norm(residual_data) > 1e-10),
                'residual_rms': float(np.sqrt(np.mean((residual/w)**2)))}, amp*prf + (plane(shape) @ background).reshape(shape)

    if fixed is None:
        fit = minimize(evaluate, np.array(center), method='Powell',
                       bounds=[(center[0]-1., center[0]+1.), (center[1]-1., center[1]+1.)],
                       options={'xtol': 1e-5, 'ftol': 1e-7, 'maxiter': 80})
        result, image = evaluate(fit.x, True)
        result['optimizer_success'] = bool(fit.success)
        result['search_boundary'] = bool(np.any(abs(fit.x-center) > .99))
        return result, image
    return evaluate(fixed, True)


def register(model, median, error, sources, target, floor, exclude_target=False):
    yy, xx = np.indices(median.shape)
    mask = np.ones(median.shape, bool)
    if exclude_target:
        mask &= (xx-target[0])**2 + (yy-target[1])**2 > 2**2
    uncertainty = np.sqrt(error**2 + (floor*np.maximum(median, 0))**2)
    uncertainty = np.maximum(uncertainty, np.median(error))
    w = 1/uncertainty[mask]
    basis = plane(median.shape)[mask.ravel()] * w[:, None]
    q, _ = np.linalg.qr(basis)
    data = median[mask] * w
    projected = data-q @ (q.T @ data)

    def evaluate(shift, detail=False):
        images = [model.locate(*(s['pixel']+shift), median.shape) for s in sources]
        a = np.column_stack([image[mask]*w for image in images])
        a -= q @ (q.T @ a)
        amps, _ = nnls(a, projected, maxiter=2000)
        loss = float(np.sum((projected-a @ amps)**2))
        if not detail:
            return loss
        prediction = sum(amp*image for amp, image in zip(amps, images))
        bg = np.linalg.lstsq(basis, (median[mask]-prediction[mask])*w, rcond=None)[0]
        prediction += (plane(median.shape) @ bg).reshape(median.shape)
        return {'shift_pixel': list(map(float, shift)), 'model_floor_fraction': floor,
                'excluded_target_radius_pixels': 2 if exclude_target else 0,
                'loss': loss, 'fit_pixels': int(mask.sum()),
                'stellar_amplitudes': [{'source_id': s['source_id'], 'amplitude': float(a)} for s, a in zip(sources, amps)]}, prediction

    fit = minimize(evaluate, [0., 0.], method='Powell', bounds=[(-.5, .5), (-.5, .5)],
                   options={'xtol': 2e-4, 'ftol': 1e-6, 'maxiter': 60})
    record, image = evaluate(fit.x, True)
    record.update(optimizer_success=bool(fit.success), boundary=bool(np.any(abs(fit.x)>.49)))
    return record, image


def project_sources(catalog, wcs, shape, epoch):
    rows = []
    for star in catalog:
        if not star['phot_g_mean_mag'] or float(star['phot_g_mean_mag'])>18.5:
            continue
        pos = SkyCoord(float(star['ra'])*u.deg, float(star['dec'])*u.deg,
                       pm_ra_cosdec=float(star['pmra'] or 0)*u.mas/u.yr,
                       pm_dec=float(star['pmdec'] or 0)*u.mas/u.yr,
                       obstime=Time(float(star['ref_epoch']), format='jyear'))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            moved = pos.apply_space_motion(new_obstime=epoch)
        xy = np.array(wcs.world_to_pixel_values(moved.ra.deg, moved.dec.deg))
        if -.5 <= xy[0] < shape[1]-.5 and -.5 <= xy[1] < shape[0]-.5:
            rows.append(dict(star, pixel=xy, propagated_ra_deg=float(moved.ra.deg),
                             propagated_dec_deg=float(moved.dec.deg)))
    return rows


def run_epoch(item, model_class, catalog, dest):
    sec = item['sector']
    path = ROOT / item['pixels']['path']
    assert sha256(path) == item['pixels']['sha256']
    assert sha256(ROOT/item['path']) == item['sha256']
    with fits.open(path, memmap=False) as h:
        lc = read_lightcurve(ROOT/item['path'])
        meta = dict(h[0].header) | dict(h[1].header)
        for key in ['TICID', 'SECTOR', 'TIMESYS', 'BJDREFI', 'BJDREFF']:
            if meta.get(key) != lc.metadata.get(key):
                raise ValueError(f'Pixel/lightcurve mismatch: {key}')
        data = h[1].data
        good = (data['QUALITY']==0) & np.isfinite(data['TIME']) & np.isfinite(data['FLUX']).all(axis=(1,2))
        t = np.array(data['TIME'][good], float)
        cube = np.array(data['FLUX'][good], float)
        err = np.array(data['FLUX_ERR'][good], float)
        assert np.isfinite(err).all() and np.all(err>0)
        wcs = WCS(h[2].header)
        cam, ccd = h[0].header['CAMERA'], h[0].header['CCD']
        detector_col = h[2].header['CRVAL1P']+(cube.shape[2]-1)/2
        detector_row = h[2].header['CRVAL2P']+(cube.shape[1]-1)/2
    index = np.searchsorted(lc.time, t)
    index = np.minimum(index, len(lc.time)-1)
    aligned = np.isclose(lc.time[index], t, rtol=0, atol=1e-7)
    t, cube, err, index = t[aligned], cube[aligned], err[aligned], index[aligned]
    reference = lc.flux[index]
    model = model_class(cam, ccd, sec, detector_col, detector_row,
                        localdatadir=str(OUT/'prf-reference/models'))
    sources = project_sources(catalog, wcs, cube.shape[1:], Time(np.median(t)+2457000, format='jd'))
    positions = {s['source_id']: s['pixel'] for s in sources}
    target, neighbor = positions[TARGET], positions[NEIGHBOR]
    median, noise = np.median(cube, axis=0), np.median(err, axis=0)
    registration = []
    for floor, excluded in [(.01, False), (.02, False), (.05, False), (.02, True)]:
        r, field = register(model, median, noise, sources, target, floor, excluded)
        registration.append(r)
        if floor==.02 and not excluded:
            primary_field = field
    shift = np.array(registration[1]['shift_pixel'])
    p = read_json(OUT/'plan.json')['prior_period_d']
    scale = 1.4826*np.median(abs(reference-np.median(reference)))
    keep = abs(reference-np.median(reference)) <= 8*scale
    maps = {'period_all': harmonic_map(t,cube,reference,p)}
    for label, mask in [('period_event_masked',keep),
                        ('period_first_half',keep & (t <= np.median(t))),
                        ('period_second_half',keep & (t > np.median(t)))]:
        maps[label] = harmonic_map(t[mask],cube[mask],reference[mask],p)
    flare = None
    if sec==36:
        peak = float(t[np.argmax(reference)])
        event = abs(t-peak)<=.005
        before = (t>=peak-.5)&(t<=peak-.2)
        after = (t>=peak+.8)&(t<=peak+1.1)
        assert min(event.sum(), before.sum(), after.sum())>=3
        fraction = (np.mean(t[event])-np.median(t[before]))/(np.median(t[after])-np.median(t[before]))
        baseline = np.median(cube[before],axis=0)*(1-fraction)+np.median(cube[after],axis=0)*fraction
        maps['transient'] = np.mean(cube[event],axis=0)-baseline
        flare = {'peak_btjd':peak,'relative_PDCSAP_peak':float(max(reference)),
                 'event_cadences':int(event.sum()),'before_cadences':int(before.sum()),'after_cadences':int(after.sum()),
                 'time_units':'BTJD = BJD_TDB - 2457000',
                 'interpretation':'Transient morphology and position diagnostic; not a confirmed flare identity.'}
    results = {}
    for label, signal in maps.items():
        free, fitted = fit_source(model,signal,noise,target+shift)
        fixed_target, _ = fit_source(model,signal,noise,target+shift,fixed=target+shift)
        fixed_neighbor, _ = fit_source(model,signal,noise,target+shift,fixed=neighbor+shift)
        free['distance_to_target_pixel'] = float(np.linalg.norm(np.array(free['xy'])-target-shift))
        free['distance_to_neighbor_pixel'] = float(np.linalg.norm(np.array(free['xy'])-neighbor-shift))
        free['registration_sensitivity'] = [{'registration':r['shift_pixel'],
            'distance_to_target_pixel':float(np.linalg.norm(np.array(free['xy'])-target-r['shift_pixel'])),
            'distance_to_neighbor_pixel':float(np.linalg.norm(np.array(free['xy'])-neighbor-r['shift_pixel']))} for r in registration]
        results[label] = {'free_fit':free,'fixed_target':fixed_target,'fixed_neighbor':fixed_neighbor}
    # Coordinate and optimizer checks with the same forward model do not calibrate real-sky systematics.
    synthetic = []
    for name, point in [('target',target),('neighbor',neighbor)]:
        signal = 1000*model.locate(*(point+shift), median.shape) + 3
        recovered, _ = fit_source(model,signal,noise,target+shift)
        error = float(np.linalg.norm(np.array(recovered['xy'])-point-shift))
        synthetic.append({'injected':name,'position_error_pixel':error})
        assert error<.005
    serial_sources = [{**s,'pixel':s['pixel'].tolist()} for s in sources]
    record = {'created_at':now(),'sector':sec,'inputs':item,'period_d':p,
              'period_use':'Fixed prior-period source diagnostic; does not change detection status.',
              'matched_cadences':len(t),'event_masked_cadences':int((~keep).sum()),'sources':serial_sources,
              'target_pixel':target.tolist(),'neighbor_pixel':neighbor.tolist(),'registration':registration,
              'fits':results,'transient':flare,'synthetic_checks':synthetic,
              'source_confirmed':False,'limitation':'Model mismatch and WCS registration dominate possible subpixel bias; losses are not calibrated probabilities.'}
    np.savez_compressed(dest/f's{sec}-maps.npz',median=median,field_model=primary_field,**maps)
    panels=[('Median pixels',median),('Catalog + PRF fit',primary_field),
            ('Median residual',median-primary_field),('Periodic map (all)',maps['period_all']),
            ('Periodic map (event masked)',maps['period_event_masked']),
            ('Transient difference' if flare else 'Periodic second half',maps['transient'] if flare else maps['period_second_half'])]
    fig, axes = plt.subplots(2,3,figsize=(13,8),layout='constrained')
    for ax,(label,signal) in zip(axes.flat,panels):
        ax.imshow(signal,origin='lower',cmap='magma');ax.set_title(label)
        ax.plot(*(target+shift),'o',mfc='none',mec='lime',ms=11,label='target')
        ax.plot(*(neighbor+shift),'x',color='cyan',ms=9,label='5.09 arcsec neighbor')
        if label.startswith('Periodic') or label.startswith('Transient'):
            key={'Periodic map (all)':'period_all','Periodic map (event masked)':'period_event_masked',
                 'Periodic second half':'period_second_half','Transient difference':'transient'}[label]
            ax.plot(*results[key]['free_fit']['xy'],'+',color='white',ms=12,label='free PRF fit')
    axes[0,0].legend(fontsize=7)
    fig.suptitle(f'TIC 302959739 / S{sec}: exploratory PRF fits, not calibrated source confirmation')
    fig.savefig(dest/f's{sec}-diagnostics.jpg',dpi=125);plt.close(fig)
    write_json(dest/f's{sec}.json',record)
    print('Sector',sec,'registration',shift.tolist(),flush=True)
    for label,r in results.items():
        print(label,{k:round(r['free_fit'][k],4) for k in ['distance_to_target_pixel','distance_to_neighbor_pixel']},flush=True)
    return record


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New localization directory')
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    for item in read_json(OUT/'prf-reference/models.json')['files']:
        assert sha256(ROOT/item['path']) == item['sha256']
    adapter=OUT/'prf-reference/local_prf.py'
    assert sha256(adapter)==read_json(OUT/'prf-reference/adapter.json')['adapted_sha256']
    spec=importlib.util.spec_from_file_location('archived_local_prf',adapter)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    catalog=read_json(OUT/'gaia-field.json');assert catalog['status']=='completed'
    rows=list(csv.DictReader(io.StringIO(catalog['raw_response'])));assert len(rows)<1000
    results=[run_epoch(item,module.TESS_PRF,rows,dest) for item in read_json(OUT/'source-inputs.json')['inputs']]
    write_json(dest/'summary.json',{'created_at':now(),'sectors':[r['sector'] for r in results],
        'script_sha256':sha256(Path(__file__)),
        'source_confirmed':False,'note':'See temporal splits, calibration choices and residuals before interpreting offsets.'})
