import os,json,time,concurrent.futures,traceback
from pathlib import Path
import requests,numpy as np
from astropy.io import fits
from astropy.timeseries import LombScargle

ROOT=Path(__file__).resolve().parent
def vsx(ra,dec):
    r=requests.get('https://vsx.aavso.org/index.php',params={'view':'api.list','ra':ra,'dec':dec,'radius':0.04,'format':'json'},timeout=40)
    r.raise_for_status(); j=r.json(); v=j.get('VSXObjects',{})
    return v.get('VSXObject',[]) if isinstance(v,dict) else []

def separation(ra,dec,r,d):
    return 3600*np.degrees(2*np.arcsin(np.sqrt(np.sin(np.radians(d-dec)/2)**2+np.cos(np.radians(dec))*np.cos(np.radians(d))*np.sin(np.radians(r-ra)/2)**2)))

def download(row):
    p=ROOT/row['dataURL'].split('/')[-1]
    if not p.exists():
        r=requests.get('https://mast.stsci.edu/api/v0.1/Download/file',params={'uri':row['dataURL']},timeout=90)
        r.raise_for_status(); p.write_bytes(r.content)
    return p

def bin_data(t,y,e,width=10/1440):
    key=np.floor((t-t.min())/width).astype(int)
    keys,idx=np.unique(key,return_inverse=True)
    n=np.bincount(idx)
    return np.bincount(idx,weights=t)/n,np.bincount(idx,weights=y)/n,np.sqrt(np.bincount(idx,weights=e*e))/n

def read_lc(p,kind='PDCSAP_FLUX'):
    p = Path(p)
    if not p.is_absolute():
        p = ROOT / p
    with fits.open(p) as f:
        d=f[1].data; h=dict(f[0].header);h.update(dict(f[1].header))
        t=np.array(d['TIME'],dtype=float);y=np.array(d[kind],dtype=float);e=np.array(d[kind+'_ERR'],dtype=float)
        q=np.array(d['QUALITY']);ok=np.isfinite(t)&np.isfinite(y)&np.isfinite(e)&(e>0)&(q==0)
        t,y,e=t[ok],y[ok],e[ok];med=np.median(y);y=y/med-1;e=e/med
    return t,y,e,h

def analyze(p):
    t,y,e,h=read_lc(p)
    if len(t)<500: return {'error':'too few samples'}
    tb,yb,eb=bin_data(t,y,e)
    ls=LombScargle(tb,yb,eb);freq,powr=ls.autopower(minimum_frequency=1/8,maximum_frequency=20,samples_per_peak=8)
    idx=np.argmax(powr);f0=freq[idx];period=1/f0
    out={'period_d':float(period),'power':float(powr[idx]),'n':len(t),'n_bin':len(tb),'span_d':float(t.max()-t.min()),'tmag':h.get('TESSMAG'),'teff':h.get('TEFF'),'crowdsap':h.get('CROWDSAP'),'flfrcsap':h.get('FLFRCSAP'),'camera':h.get('CAMERA'),'ccd':h.get('CCD')}
    for name,m in [('first',tb<(tb.min()+tb.max())/2),('second',tb>=(tb.min()+tb.max())/2)]:
        s=LombScargle(tb[m],yb[m],eb[m]);f,pow2=s.autopower(minimum_frequency=1/8,maximum_frequency=20,samples_per_peak=8)
        out[name+'_period']=float(1/f[np.argmax(pow2)]);out[name+'_power_at_period']=float(s.power(f0))
    phase=(tb%period)/period
    means=[np.median(yb[(phase>=i/50)&(phase<(i+1)/50)]) for i in range(50)]
    out['phase_amplitude_pct']=float(100*(np.nanpercentile(means,95)-np.nanpercentile(means,5)))
    out['phot_scatter_pct']=float(100*np.std(yb))
    ts,ys,es,_=read_lc(p,'SAP_FLUX');ts,ys,es=bin_data(ts,ys,es)
    out['sap_power_at_period']=float(LombScargle(ts,ys,es).power(f0))
    return out

def run(row):
    out=dict(row)
    try:
        neighbors=vsx(row['s_ra'],row['s_dec'])
        for n in neighbors:n['sep_arcsec']=float(separation(row['s_ra'],row['s_dec'],float(n['RA2000']),float(n['Declination2000'])))
        out['vsx_neighbors']=neighbors
        near=[n for n in neighbors if n['sep_arcsec']<10]
        if near:out['status']='already_in_vsx'
        else:
            p=download(row);out.update(analyze(p));out['file']=p.name;out['status']='scanned'
    except Exception as e:out.update(status='error',error=str(e))
    (ROOT/('scan-'+row['target_name']+'.json')).write_text(json.dumps(out,indent=2))
    print(json.dumps({k:out.get(k) for k in ['target_name','status','period_d','power','phase_amplitude_pct','first_period','second_period','crowdsap','error']}),flush=True)
    return out

if __name__=='__main__':
    rows=json.loads((ROOT/'mast-s85.json').read_text())['data']
    rows=[r for r in rows if '_fast' not in r['dataURL']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,rows))
    (ROOT/'scan-results.json').write_text(json.dumps(results,indent=2))
    print('COMPLETE',len(results),flush=True)
