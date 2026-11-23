"""Independent ZTF retrieval and explicit post-selection diagnostics, not v4 scores."""
import argparse,csv,io,json
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.signal import find_peaks
from scipy.optimize import minimize_scalar
from astropy.timeseries import LombScargle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from select_discovery_2000 import ROOT,OUT,fetch,read_json,write_json,now

TARGETS={'232643687':.3557239884562398,'229945262':.8654647373055471,'230089225':1.5718861247382159,'288471156':.67478}

def retrieve(tic):
    ident=read_json(OUT/'followup-results'/f'{tic}.json')['services']['tic']['data']
    planfile=OUT/f'ztf-{tic}-plan.json'
    if planfile.exists():plan=read_json(planfile)
    else:
        sql=f"SELECT * FROM ztf_objects_dr24 WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ident['ra']},{ident['dec']},0.0008333333333))=1"
        r=fetch(f'ztf-dr24-{tic}-cone','https://irsa.ipac.caltech.edu/TAP/sync',{'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv','QUERY':sql},70)
        if r.get('status_code')!=200 or not r.get('body','').startswith('cntr,'):raise ValueError('Invalid ZTF object catalogue response')
        rows=list(csv.DictReader(io.StringIO(r['body'])))
        selected=[max([r for r in rows if r['filtercode']==b],key=lambda r:int(r['ngoodobs'])) for b in sorted({r['filtercode'] for r in rows})]
        plan={'at':now(),'tic':tic,'selected_objects':selected,'all_cone_objects':rows,'diagnostic_period_d':TARGETS[tic],
              'selection':'Highest ngoodobs per filter, selected before light curves; 3 arcsec identity cone. A catalogue object is not itself a variability report.'}
        write_json(planfile,plan)
    for r in plan['selected_objects']:
        receipt=fetch('ztf-id-'+r['oid'],'https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves',{'ID':r['oid'],'FORMAT':'csv'},90)
        print(tic,r['filtercode'],receipt.get('status_code'),len(receipt.get('body','')),flush=True)

def analyze(tic):
    plan=read_json(OUT/f'ztf-{tic}-plan.json');dest=OUT/'independent-ztf'/tic;dest.mkdir(parents=True,exist_ok=True)
    summary={'at':now(),'tic':tic,'diagnostic_period_d':TARGETS[tic],'bands':[],
             'method':'Use returned HJD (heliocentric) as supplied, separately from TESS BJD_TDB; no cross-survey phase connection. catflags==0, finite HJD/mag/positive magerr, no amplitude clipping. Weighted floating-mean LS, 0.125–20/day, 5 samples/peak; narrow diagnostic refinement near TESS frequency. Aliases and year groups retained. Harmonic fit range is observed calibrated ZTF-band variability, not intrinsic deblended amplitude.',
             'confirmation_note':'Post-selection independent-survey corroboration; not a revision of frozen v4 decisions. White-noise FAP not asserted; systematic noise and source attribution assessed separately.'}
    fig,axes=plt.subplots(max(1,len(plan['selected_objects'])),3,figsize=(13,3*max(1,len(plan['selected_objects']))),squeeze=False,layout='constrained')
    for j,obj in enumerate(plan['selected_objects']):
        receipts=[p for p in (OUT/'sources'/('ztf-id-'+obj['oid'])).glob('attempt-*.json') if read_json(p).get('status_code')==200]
        if not receipts:
            summary['bands'].append({'band':obj['filtercode'],'status':'unavailable','oid':obj['oid']})
            for ax in axes[j]:ax.axis('off')
            axes[j,0].text(.05,.5,obj['filtercode']+': retrieval unavailable (timeouts)',transform=axes[j,0].transAxes)
            continue
        receipt=receipts[-1];data=read_json(receipt);rows=list(csv.DictReader(io.StringIO(data['body'])))
        if rows and any(r['oid']!=obj['oid'] for r in rows):raise ValueError('ZTF identity mismatch')
        accepted=[r for r in rows if int(r['catflags'])==0 and all(np.isfinite(float(r[k])) for k in ['hjd','mag','magerr']) and float(r['magerr'])>0]
        band=obj['filtercode'];r={'band':band,'oid':obj['oid'],'status':'completed','received':len(rows),'accepted':len(accepted),'input':str(receipt.relative_to(ROOT)),'object':obj}
        if len(accepted)<30:
            r['status']='insufficient_points';summary['bands'].append(r)
            for ax in axes[j]:ax.axis('off')
            axes[j,0].text(.05,.5,band+': '+str(len(accepted))+' accepted points; no period analysis',transform=axes[j,0].transAxes)
            continue
        t=np.array([float(x['hjd']) for x in accepted]);y=np.array([float(x['mag']) for x in accepted]);e=np.array([float(x['magerr']) for x in accepted]);t0=float(t.min());t=t-t0
        np.savetxt(dest/(band+'-accepted.csv'),np.c_[t+t0,y,e],delimiter=',',header='HJD_as_returned,mag,magerr',comments='')
        ls=LombScargle(t,y,e);freq,power=ls.autopower(minimum_frequency=.125,maximum_frequency=20,samples_per_peak=5)
        top=[]
        for k in sorted(find_peaks(power)[0],key=lambda k:power[k],reverse=True):
            if all(abs(freq[k]-z['frequency_per_d'])>2/np.ptp(t) for z in top):top.append({'frequency_per_d':float(freq[k]),'period_d':float(1/freq[k]),'power':float(power[k])})
            if len(top)==8:break
        f0=1/TARGETS[tic];grid=np.linspace(f0*.99,f0*1.01,max(2001,int(.02*f0*np.ptp(t)*10)));
        pp=ls.power(grid);best=int(np.argmax(pp));a=grid[max(0,best-1)];b=grid[min(len(grid)-1,best+1)]
        opt=minimize_scalar(lambda f:-ls.power(f),bounds=(a,b),method='bounded',options={'xatol':1e-12});f=float(opt.x);p=1/f
        ls2=LombScargle(t,y,e,nterms=2);phase=np.linspace(0,1,500,endpoint=False);curve=ls2.model(phase*p,f);minimum_time=t0+float(phase[np.argmax(curve)]*p)
        # Year groups preserve all measurements; no selecting only successful seasons.
        seasons=[]
        for year in sorted(set(np.floor(t/365.25).astype(int))):
            mask=np.floor(t/365.25).astype(int)==year
            if mask.sum()<30:continue
            sub=LombScargle(t[mask],y[mask],e[mask]);fg,pg=sub.autopower(minimum_frequency=f0*.99,maximum_frequency=f0*1.01,samples_per_peak=15);k=np.argmax(pg)
            seasons.append({'year_index':int(year),'n':int(mask.sum()),'period_d':float(1/fg[k]),'power':float(pg[k]),'fixed_power':float(sub.power(f))})
        aliases=[{'frequency_per_d':float(ff),'power':float(ls.power(ff))} for ff in [f/2,2*f,abs(f-1),f+1,abs(f-2),f+2] if .125<ff<20]
        r.update(hjd_range=[t0,float(t.max()+t0)],peaks=top,refined_near_tess_period_d=p,refined_power=float(ls.power(f)),original_tess_period_power=float(ls.power(f0)),
                 fitted_bright_mag=float(min(curve)),fitted_faint_mag=float(max(curve)),fitted_full_range_mag=float(np.ptp(curve)),
                 model_faint_epoch_hjd=minimum_time,epoch_note='Illustrative phase zero of a two-harmonic global model, not a timed eclipse or an adopted ephemeris.',aliases=aliases,seasons=seasons)
        axes[j,0].errorbar(t+t0,y,e,fmt='.',ms=1,alpha=.4,lw=.2);axes[j,0].invert_yaxis();axes[j,0].set(xlabel='HJD as returned',ylabel=band+' magnitude')
        axes[j,1].plot(freq,power,lw=.35);axes[j,1].axvline(f0,color='r',ls='--');axes[j,1].set(xlim=(0,10),xlabel='Frequency [1/day]',ylabel='LS power')
        phase_data=(t*f)%1;axes[j,2].errorbar(phase_data,y,e,fmt='.',ms=1.5,alpha=.3,lw=.2);axes[j,2].plot(phase,curve,c='r');axes[j,2].invert_yaxis();axes[j,2].set(xlabel='Phase, P='+format(p,'.8f')+' d',ylabel=band+' magnitude')
        summary['bands'].append(r)
    fig.suptitle('TIC '+tic+': independent ZTF diagnostics');fig.savefig(dest/'ztf-diagnostics.png',dpi=150);plt.close(fig)
    write_json(dest/'summary.json',summary);print(tic,[(b['band'],b['status'],b.get('accepted'),b.get('refined_near_tess_period_d'),b.get('refined_power')) for b in summary['bands']],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['retrieve','analyze']);p.add_argument('--tic',choices=list(TARGETS));a=p.parse_args();tics=[a.tic] if a.tic else list(TARGETS)
    if a.action=='retrieve':
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(retrieve,tics))
    else:
        for tic in tics:
            if (OUT/f'ztf-{tic}-plan.json').exists():analyze(tic)
