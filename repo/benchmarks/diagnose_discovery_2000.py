"""Raw-cadence and harmonic diagnostics; never promotes a frozen detection."""
import argparse,time
import numpy as np
from scipy.signal import find_peaks
from astropy.timeseries import LombScargle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from vstar.photometry import read_lightcurve
from vstar.io import read_json,write_json,sha256,now
from select_discovery_2000 import ROOT,OUT
from source_discovery_2000 import periods


def diagnose(tic):
    ext=read_json(OUT/'extension-results'/f'{tic}.json');pred=read_json(OUT/'results'/f'{tic}.json')
    if ext['status']!='completed':return
    dest=OUT/'raw-cadence'/tic
    if (dest/'summary.json').exists():return
    dest.mkdir(parents=True,exist_ok=True)
    ps=periods(pred);rows=[];fig,axs=plt.subplots(len(ext['inputs']),2,figsize=(11,2.4*len(ext['inputs'])),squeeze=False,layout='constrained')
    for i,item in enumerate(sorted(ext['inputs'],key=lambda r:r['sector'])):
        path=ROOT/item['path'];assert sha256(path)==item['sha256']
        for j,product in enumerate(['SAP','PDCSAP']):
            lc=read_lightcurve(path,product+'_FLUX');t=lc.time-lc.time[0];ls=LombScargle(t,lc.flux,lc.error,fit_mean=True)
            maximum=min(100.,.45/np.median(np.diff(t)));freq,power=ls.autopower(minimum_frequency=.125,maximum_frequency=maximum,samples_per_peak=8)
            peaks=[]
            for index in sorted(find_peaks(power)[0],key=lambda k:power[k],reverse=True):
                if all(abs(freq[index]-r['frequency_per_d'])>2/np.ptp(t) for r in peaks):peaks.append({'period_d':float(1/freq[index]),'frequency_per_d':float(freq[index]),'ls_power':float(power[index])})
                if len(peaks)==8:break
            fixed=[]
            for p in ps:
                for factor in [.5,1.,2.]:
                    period=p*factor;par=ls.model_parameters(1/period)
                    fixed.append({'diagnostic_period_d':period,'factor':factor,'raw_ls_power':float(ls.power(1/period)),'raw_sinusoid_semi_amplitude_fraction':float(np.hypot(par[1],par[2]))})
            rows.append({'sector':item['sector'],'product':product,'valid_raw_cadences':len(t),'nominal_cadence_d':float(np.median(np.diff(t))),'peaks':peaks,'fixed_period_diagnostics':fixed})
            np.savez_compressed(dest/f's{item["sector"]}-{product}.npz',frequency=freq,power=power)
            ax=axs[i,j];ax.plot(freq,power,lw=.5)
            for p in ps:ax.axvline(1/p,color='red',lw=.8,ls='--')
            ax.set(title=f'S{item["sector"]} {product}',xlabel='Frequency [1/day]',ylabel='Raw-cadence LS power',xlim=(0,maximum))
    fig.suptitle(f'TIC {tic}: diagnostic only; red = original candidate frequency')
    fig.savefig(dest/'periodograms.png',dpi=110);plt.close(fig)
    write_json(dest/'summary.json',{'at':now(),'tic':tic,'diagnostic_only':True,'reference_periods_from_catalog':False,'inputs':ext['inputs'],'candidate_periods_d':ps,'rows':rows,
        'method':'Quality-zero finite raw cadences, floating-mean weighted Lomb-Scargle, no added clipping/detrending/binning; 0.125-100/day capped below Nyquist. Evaluate original candidate and half/double periods separately.',
        'limitations':'Colored noise and trends remain. No new calibrated detection threshold, period adoption, source confirmation, or intrinsic amplitude is claimed.'})
    print('raw cadence',tic,'completed',flush=True)


def run(watch):
    done=set()
    while True:
        records=[read_json(p) for p in (OUT/'extension-results').glob('*.json')]
        for r in records:
            if r['status']=='completed' and r['tic'] not in done:diagnose(r['tic']);done.add(r['tic'])
        predictions=[read_json(p) for p in (OUT/'results').glob('*.json')]
        needed={r['tic'] for r in predictions if r.get('periodic_detected')}
        if not watch or len(predictions)==2000 and needed<=done:break
        time.sleep(20)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');a=p.parse_args();run(a.watch)
