"""Known artificial threats on measured backgrounds; no external source attribution truth."""
import gzip
import io
import numpy as np
from astropy.io import fits
from standard_injection import signal,good_mask,pulse_primitive


def flux_signal(time,spec,origin,exposure):
    if spec['kind']=='equal_eclipses':
        phase=(np.asarray(time)-origin)/spec['period_d']+spec['phase'];half=exposure/(2*spec['period_d']);width=.08
        return -spec['amplitude_fraction']*sum((pulse_primitive(phase-center+half,width)-pulse_primitive(phase-center-half,width))/(2*half) for center in [0,.5])
    if spec['kind']=='two_modes':
        return sum(signal(time,dict(spec,shape='sine',period_d=p),origin,exposure) for p in spec['periods_d'])
    return signal(time,dict(spec,shape='unequal_eclipses' if spec['kind']=='unequal_eclipses' else 'sine',eclipse_width_phase=.08),origin,exposure)


def construct(source,spec,origin,output):
    with fits.open(source,memmap=False) as original:
        h=fits.HDUList([x.copy() for x in original]);data=h[1].data
        exposure=float(h[1].header['TIMEDEL']);time=np.asarray(data['TIME'],float)
        metadata={'modified_auxiliary':None,'time_window_d':exposure,'flux_normalizations':{}}
        for product in ['SAP','PDCSAP']:
            good=good_mask(data,product);y=np.asarray(data[product+'_FLUX'][good],float);median=float(np.median(y))
            data[product+'_FLUX'][good]=y+median*flux_signal(time[good],spec,origin,exposure)
            metadata['flux_normalizations'][product]=median
        channel=spec.get('channel')
        if channel:
            y=np.asarray(data[channel],float);valid=np.isfinite(time)&np.isfinite(y)&(data['QUALITY']==0)
            if valid.sum()<100:raise ValueError('Insufficient auxiliary source data')
            scale=max(float(np.std(y[valid])),1e-8)
            wave=signal(time[valid],dict(spec,shape='sine',amplitude_fraction=2.),origin,exposure)
            # Artificial, known shared periodic term, twenty times the measured channel scatter.
            data[channel][valid]=y[valid]+20*scale*wave
            metadata['modified_auxiliary']={'column':channel,'original_std':scale,'added_sine_semiamplitude':20*scale}
        h[0].header['SYNTHET']=(True,'Artificial reliability challenge')
        h[0].header['HISTORY']='Precision challenge v01; simulated signal/auxiliary changes.'
        for extension in h:
            for key in ['CHECKSUM','DATASUM']:
                if key in extension.header:del extension.header[key]
        buf=io.BytesIO();h.writeto(buf);h.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('wb') as stream,gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as z:z.write(buf.getvalue())
    return metadata
