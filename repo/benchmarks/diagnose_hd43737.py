"""Raw-cadence broad-frequency diagnostic, separate from the frozen detector."""
import numpy as np
from astropy.timeseries import LombScargle
from scipy.signal import find_peaks
from scipy.optimize import minimize_scalar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from followup_hd43737 import ROOT,OUT
from vstar.photometry import read_lightcurve
from vstar.io import read_json,write_json,sha256


def run():
    dest=OUT/'wide-frequency'
    dest.mkdir(exist_ok=False)
    cases=read_json(OUT/'combined-four-sectors.json')['observations']
    rows=[];fig,axs=plt.subplots(4,2,figsize=(12,11),layout='constrained')
    for i,obs in enumerate(sorted(cases,key=lambda x:x['sector'])):
        p=ROOT/obs['input']['path'];assert sha256(p)==obs['input']['sha256']
        for j,name in enumerate(['SAP','PDCSAP']):
            lc=read_lightcurve(p,name+'_FLUX')
            t,y=lc.time,lc.flux
            delta=np.median(np.diff(t));assert .5/delta>100
            # Full raw valid-cadence data, floating mean, no added clipping or detrending.
            ls=LombScargle(t-t[0],y,lc.error,fit_mean=True)
            f,power=ls.autopower(minimum_frequency=.125,maximum_frequency=100,samples_per_peak=8)
            inds=find_peaks(power)[0]
            inds=sorted(inds,key=lambda k:power[k],reverse=True)
            chosen=[]
            for k in inds:
                if all(abs(f[k]-f[x])>2/(t[-1]-t[0]) for x in chosen):chosen.append(k)
                if len(chosen)==8:break
            peaks=[]
            for k in chosen:
                opt=minimize_scalar(lambda freq:-float(ls.power(freq)),bounds=(f[max(k-1,0)],f[min(k+1,len(f)-1)]),method='bounded')
                params=ls.model_parameters(opt.x)
                peaks.append({'period_d':float(1/opt.x),'frequency_per_d':float(opt.x),
                              'ls_power':float(-opt.fun),'observed_sinusoid_semi_amplitude_fraction':float(np.hypot(params[1],params[2]))})
            row={'sector':obs['sector'],'product':name,'cadences':len(t),'nominal_cadence_d':float(delta),'peaks':peaks}
            rows.append(row)
            np.savez_compressed(dest/f's{obs["sector"]}-{name}.npz',frequency_per_d=f,power=power)
            ax=axs[i,j];ax.plot(f,power,lw=.6);ax.axvline(20,color='red',ls='--',lw=.8,label='Old search limit')
            ax.set(title=f'S{obs["sector"]} {name}',xlabel='Frequency [1/day]',ylabel='LS power',xlim=(0,100));ax.legend(fontsize=7)
    fig.suptitle('HD 43737 A+B: raw-cadence diagnostic; component unresolved')
    fig.savefig(dest/'periodograms.png',dpi=120);plt.close(fig)
    write_json(dest/'summary.json',{'diagnostic_only':True,'search_period_d':[.01,8],
        'original_results_replaced':False,'source_confirmed':False,'rows':rows,
        'limitations':'No new calibrated detection threshold or physical period classification. Same TESS pixels underlie both products. Amplitude is blended product amplitude, not intrinsic stellar amplitude.'})
    print([(r['sector'],r['product'],round(r['peaks'][0]['period_d'],8)) for r in rows])

if __name__=='__main__':run()
