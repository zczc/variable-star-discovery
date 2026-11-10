import json
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.timeseries import LombScargle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scan import ROOT,read_lc,bin_data
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
summary=[]
for tic in ['458747716','259238257']:
    row=json.loads((ROOT/f'scan-{tic}.json').read_text());p=ROOT/row['dataURL'].split('/')[-1].replace('_lc.fits','_tp.fits')
    with fits.open(p) as hd:
        d=hd[1].data;ap=np.array(hd[2].data);w=WCS(hd[2].header);t=np.array(d['TIME'],float);cube=np.array(d['FLUX'],float);q=np.array(d['QUALITY']);bkg=np.array(d['FLUX_BKG'],float)
        ok=np.isfinite(t)&(q==0)&np.isfinite(cube).all(axis=(1,2));t=t[ok];cube=cube[ok];bkg=bkg[ok]
        y,x=np.indices(ap.shape);x0,y0=w.world_to_pixel_values(row['s_ra'],row['s_dec'])
        near=row['vsx_neighbors'][0];xn,yn=w.world_to_pixel_values(float(near['RA2000']),float(near['Declination2000']))
        lc_t,lc_y,lc_e,h=read_lc(row['file']);ref=np.interp(t,lc_t,lc_y)
        phase=2*np.pi*t/row['period_d'];u=(t-np.mean(t))/np.ptp(t)
        gap=np.cumsum(np.r_[0,np.diff(t)>.5]);cols=[np.ones(len(t)),u,u*u,u*u*u]
        cols += [(gap==g).astype(float) for g in np.unique(gap)[1:]]
        X=np.column_stack(cols+[np.sin(phase),np.cos(phase)])
        coef=np.linalg.lstsq(X,cube.reshape(len(t),-1),rcond=None)[0]
        refc=np.linalg.lstsq(X,ref,rcond=None)[0][-2:];refc=refc/np.linalg.norm(refc)
        signal=(refc@coef[-2:]).reshape(ap.shape)
        residual=cube.reshape(len(t),-1)-X@coef;sd=np.std(residual,axis=0)
        varcoeff=np.linalg.pinv(X.T@X)[-2:,-2:];se=sd*np.sqrt(refc@varcoeff@refc)
        snr=(signal.flatten()/se).reshape(ap.shape)
        mean=np.median(cube,axis=0)
        pk=np.unravel_index(np.argmax(signal),signal.shape)
        out={'tic':tic,'target_pixel':[float(x0),float(y0)],'known_neighbor':near,'neighbor_pixel':[float(xn),float(yn)],'signal_peak_xy':[int(pk[1]),int(pk[0])],'signal_peak_snr_iid_only':float(snr[pk]),'period':row['period_d']}
        summary.append(out)
        fig,ax=plt.subplots(1,2,figsize=(10,4.3),layout='constrained')
        im=ax[0].imshow(np.log10(np.maximum(mean,1)),origin='lower',cmap='magma');fig.colorbar(im,ax=ax[0],label='log10 median flux (electrons/s)')
        im=ax[1].imshow(signal,origin='lower',cmap='coolwarm',vmin=-np.max(abs(signal)),vmax=np.max(abs(signal)));fig.colorbar(im,ax=ax[1],label='Coherent signal amplitude (electrons/s)')
        for a in ax:
            a.plot(x0,y0,'o',mfc='none',mec='lime',ms=13,label='Target TIC '+tic)
            a.plot(xn,yn,'x',color='cyan',ms=10,label='Known variable nearby')
            a.contour((ap&2)>0,levels=[.5],colors=['white'],linewidths=.8)
            a.set(xlabel='Pixel column in cutout',ylabel='Pixel row in cutout',xlim=(-.5,ap.shape[1]-.5),ylim=(-.5,ap.shape[0]-.5))
        ax[0].set_title('TESS sector 85: mean image');ax[1].set_title(f'Signal near {row["period_d"]:.4f} days')
        ax[0].legend(fontsize=8,loc='upper left');fig.suptitle('TIC '+tic+' | exploratory localization (not a PRF fit)')
        fig.savefig(ROOT/f'pixels-{tic}.png',dpi=150);plt.close(fig)
        np.savez_compressed(ROOT/f'pixels-{tic}.npz',mean=mean,signal=signal,snr=snr,aperture=ap)
(ROOT/'localization.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))

tic='458747716';rows=json.loads((ROOT/f'followup-{tic}.json').read_text())+[json.loads((ROOT/f'scan-{tic}.json').read_text())]
fig,axs=plt.subplots(3,2,figsize=(11,8),layout='constrained')
export=[]
for i,r in enumerate(rows):
    t,y,e,h=read_lc(r['file']);t,y,e=bin_data(t,y,e,20/1440)
    per=r['period_d'];tt=t-t.min();phase=((t-t.min())%per)/per
    axs[i,0].scatter(tt,y*100,s=3,alpha=.65,c='#215d9c',rasterized=True)
    axs[i,1].scatter(phase,y*100,s=3,alpha=.35,c='#215d9c',rasterized=True)
    b=np.linspace(0,1,41);yy=[np.median(y[(phase>=b[k])&(phase<b[k+1])])*100 for k in range(40)]
    axs[i,1].plot((b[:-1]+b[1:])/2,yy,c='#dd702d',lw=2)
    axs[i,0].set_title(f'Sector {r["sequence_number"]} | P ~ {per:.2f} d');axs[i,1].set_title('Folded separately within this sector')
    for a in axs[i]:a.set_ylabel('Relative flux change (%)');a.grid(alpha=.15)
    axs[i,0].set_xlabel('Days since sector start');axs[i,1].set_xlabel('Phase (one cycle)')
    export.append({'sector':r['sequence_number'],'period_d':per,'time':[round(float(z),5) for z in tt],'flux_pct':[round(float(z),5) for z in y*100]})
fig.suptitle('TIC 458747716: recurring ~2.3-day variability\nAlready appears in an existing periodic-source training set; not claimed as a discovery')
fig.savefig(ROOT/'real-lightcurves.png',dpi=150);plt.close(fig)
(ROOT/'lightcurve-display.json').write_text(json.dumps(export))
