"""Add predeclared, cadence-averaged signals directly to measured SPOC flux.

No fitted stellar template, residual rescaling, clipping, or added random noise.
This tests post-reduction recovery, not upstream extraction/PDC or localization.
"""
import gzip
import io
import numpy as np
from astropy.io import fits

PRODUCTS = ('SAP', 'PDCSAP')


def pulse_primitive(x, width):
    """Antiderivative of a periodic raised-cosine pulse centered on integer phase."""
    shifted = np.asarray(x)+width/2
    cycles = np.floor(shifted)
    r = np.clip(shifted-cycles, 0, width)
    return cycles*width/2 + r/2 - width/(4*np.pi)*np.sin(2*np.pi*r/width)


def signal(time, spec, origin, exposure_d=0):
    time = np.asarray(time, float)
    if not np.all(np.isfinite(time)) or not np.isfinite(exposure_d) or exposure_d < 0:
        raise ValueError('Finite times and nonnegative averaging window required')
    if spec['shape'] == 'zero': return np.zeros(len(time))
    period, amplitude, phase0 = (spec[k] for k in ('period_d', 'amplitude_fraction', 'phase'))
    if not all(np.isfinite(x) for x in (period, amplitude, phase0, origin)) or period <= 0 or amplitude < 0:
        raise ValueError('Invalid injected signal parameters')
    phase = (time-origin)/period+phase0
    if spec['shape'] == 'sine':
        return amplitude/2*np.sin(2*np.pi*(phase % 1))*np.sinc(exposure_d/period)
    if spec['shape'] != 'unequal_eclipses': raise ValueError('Unknown signal shape')
    width = spec['eclipse_width_phase']
    if not 0 < width < .5: raise ValueError('Invalid eclipse duration')
    def dip(center):
        x = phase-center
        if exposure_d == 0:
            distance = abs((x+.5) % 1-.5)
            return np.where(distance < width/2, .5*(1+np.cos(2*np.pi*distance/width)), 0.)
        half = exposure_d/(2*period)
        return np.clip((pulse_primitive(x+half,width)-pulse_primitive(x-half,width))/(2*half),0,1)
    return -amplitude*(dip(0)+.45*dip(.5))


def good_mask(data, product):
    t,y,e = (np.asarray(data[k],float) for k in ('TIME',product+'_FLUX',product+'_FLUX_ERR'))
    return np.isfinite(t)&np.isfinite(y)&np.isfinite(e)&(e>0)&(data['QUALITY']==0)


def construct(source, spec, origin, output):
    """Deterministic full FITS copy; only usable flux values and provenance change."""
    with fits.open(source,memmap=False) as original:
        h = fits.HDUList([x.copy() for x in original]);data=h[1].data
        header = dict(h[0].header)|dict(h[1].header)
        if header.get('TIMESYS') != 'TDB' or header.get('TIMEUNIT') != 'd':
            raise ValueError('Expected original TESS TDB day time coordinates')
        exposure = float(header['TIMEDEL'])
        if not np.isfinite(exposure) or exposure <= 0: raise ValueError('Missing cadence window')
        metadata={'time_window_d':exposure,'products':{}}
        for product in PRODUCTS:
            good=good_mask(data,product);time=np.asarray(data['TIME'][good],float)
            values=np.asarray(data[product+'_FLUX'][good],float)
            median=float(np.median(values))
            if not np.isfinite(median) or median <= 0:raise ValueError('Invalid source normalization')
            delta=signal(time,spec,origin,exposure)
            changed=values+median*delta
            if not np.all(np.isfinite(changed)):raise ValueError('Invalid generated flux')
            data[product+'_FLUX'][good]=changed
            metadata['products'][product]={'normalization_median':median,'samples':int(good.sum()),
                'sampled_signal_range_fraction':float(np.ptp(delta)),
                'source_rms_about_mean_fraction':float(np.std(values/median)),
                'source_median_formal_error_fraction':float(np.median(data[product+'_FLUX_ERR'][good])/median)}
        h[0].header['SYNTHET']=(True,'ARTIFICIAL post-reduction injection')
        h[0].header['HISTORY']='Standard injection v01; original plus artificial signal.'
        for extension in h:
            for key in ('CHECKSUM','DATASUM'):
                if key in extension.header:del extension.header[key]
        buffer=io.BytesIO();h.writeto(buffer);h.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('wb') as stream,gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed:
        compressed.write(buffer.getvalue())
    return metadata
