"""Human-review figures for reference disagreements; no detection changes."""
from pathlib import Path
import argparse,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from vstar.io import read_json,write_json,sha256
from vstar.photometry import read_lightcurve,bin_lightcurve
from vstar.screening import detrend
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'repo/benchmarks/scale-validation-v01'
def main():
 p=argparse.ArgumentParser();p.add_argument('tic');a=p.parse_args()
 case=next(c for c in read_json(OUT/'targets.json')['cases'] if c['tic']==a.tic)
 pred=read_json(OUT/'evaluation'/(case['id']+'-prediction.json'));period=pred['decision']['selected_period_d'];reference=float(case['reference'][0]['period'])
 fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
 for i,item in enumerate(pred['inputs']):
  lc,_=detrend(bin_lightcurve(read_lightcurve(ROOT/item['path'],'SAP_FLUX'),10))
  for ax,p,label in zip(axes[i],[period,reference],['Selected photometric cycle','Frozen catalog orbital cycle']):
   phase=((lc.time-lc.time[0])/p)%1
   bins=np.floor(phase*80).astype(int)
   x=[];y=[]
   for k in range(80):
    valid=bins==k
    if valid.sum()>=3:x.append((k+.5)/80);y.append(np.median(lc.flux[valid])*100)
   ax.plot(phase,lc.flux*100,'.',ms=1,alpha=.25);ax.plot(x,y,'k.-',lw=1,ms=3)
   ax.set(title=f'Sector {item["sector"]}: {label}\nP = {p:.8f} d',xlabel='Phase (separate arbitrary zero)',ylabel='Relative SAP flux (%)')
 fig.suptitle(f'TIC {a.tic}: reference comparison only; no rule changes')
 dest=OUT/'reference-followup'/(case['id']+'-periods.png');fig.savefig(dest,dpi=140);plt.close(fig)
 write_json(dest.with_suffix('.figure.json'),{'plot':dest.name,'sha256':sha256(dest),'inputs':pred['inputs'],'selected_period_d':period,'catalog_period_d':reference,'time_note':'Each epoch has its own arbitrary phase zero; no coherent epoch fit'})
 print(dest)
if __name__=='__main__':main()
