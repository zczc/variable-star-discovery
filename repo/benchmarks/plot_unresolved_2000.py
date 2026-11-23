"""Raw original-cadence phase views for the ten objects without exact prior reports."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from select_discovery_2000 import ROOT,OUT,read_json,write_json,now
from vstar.photometry import read_lightcurve

def run():
    rows=[r for r in read_json(OUT/'review-43.json')['rows'] if r['disposition']!='prior_public_report'];record=[]
    for start in range(0,len(rows),5):
        group=rows[start:start+5];fig,axs=plt.subplots(len(group),2,figsize=(12,2.4*len(group)),squeeze=False,layout='constrained')
        for i,r in enumerate(group):
            pred=read_json(OUT/'results'/f'{r["tic"]}.json');period=r['diagnostic_periods_d'][0]
            for j,product in enumerate(['SAP','PDCSAP']):
                ax=axs[i,j]
                for inp in pred['inputs']:
                    lc=read_lightcurve(ROOT/inp['path'],product+'_FLUX');phase=((lc.time-lc.time.min())/period)%1;y=lc.flux*100
                    ax.scatter(phase[::10],y[::10],s=.4,alpha=.3)
                    edges=np.linspace(0,1,31);idx=np.digitize(phase,edges)-1;med=np.array([np.median(y[idx==k]) for k in range(30)])
                    ax.plot((edges[:-1]+edges[1:])/2,med,lw=1,label='S'+str(inp['sector']))
                ax.set(title=f'TIC {r["tic"]} / {product}, P={period:.8f} d',xlabel='Phase (each epoch has its own zero)',ylabel='Relative flux [%]');ax.legend(fontsize=7)
            record.append({'tic':r['tic'],'diagnostic_period_d':period,'initial_inputs':[x['path'] for x in pred['inputs']]})
        fig.suptitle('Raw-cadence review; every 10th raw point displayed, all valid points used for bin medians')
        fig.savefig(OUT/'manual-review'/f'unresolved-raw-{start//5+1}.png',dpi=130);plt.close(fig)
    write_json(OUT/'manual-review/unresolved-raw.json',{'at':now(),'method':'Quality-zero finite original LC points. No extra detrending or clipping. Thirty phase-bin medians for visibility, not a detection statistic; thinning only for scatter display. Same candidate period in both epochs, independent phase zeros.','rows':record})
if __name__=='__main__':run()
