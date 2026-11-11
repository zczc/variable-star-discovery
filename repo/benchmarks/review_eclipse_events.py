"""Diagnostic events in the two existing alias-disagreement cases."""
from pathlib import Path
from dataclasses import asdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from vstar.photometry import read_lightcurve
from vstar.eclipse_events import EventConfig,phase_anchor,measure_events
from vstar.io import read_json,write_json,sha256,now
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks'

def main():
    protocol=read_json(BENCH/'products-protocol-v01.json');cfg=EventConfig(**protocol['event_config'])
    run=BENCH/'products-v01';all_results=read_json(run/'results.json');output={'created_at':now(),'config':asdict(cfg),'inputs':[],
        'period_source':'Per-epoch SAP independent v3 search; catalog reference periods never enter event extraction.',
        'script_sha256':sha256(Path(__file__)),'observations':[]}
    for row in all_results['results']:
        if row['id'] not in protocol['event_cases']:continue
        for obs in row['observations']:
            path=ROOT/obs['input']['path'];assert sha256(path)==obs['input']['sha256']
            sap=read_lightcurve(path,'SAP_FLUX');p=obs['products']['SAP']['result']['selected_period_d']
            if p is None:raise ValueError('No selected SAP period; do not substitute catalog period')
            anchor=phase_anchor(sap,p)
            epoch={'id':row['id'],'sector':obs['sector'],'input':obs['input'],'sap_period_d':p,'epoch_input_time':anchor,'measurements':[]}
            fig,axes=plt.subplots(2,2,figsize=(13,7),layout='constrained')
            for i,factor in enumerate([.5,1.]):
                for name,col in [('SAP','SAP_FLUX'),('PDCSAP','PDCSAP_FLUX')]:
                    measured,profiles=measure_events(read_lightcurve(path,col),p*factor,anchor,cfg)
                    epoch['measurements'].append({'product':name,'spacing_factor':factor,**measured})
                    usable=[r for r in measured['events'] if r['status']=='measured']
                    for parity,color in [(0,'#137caa'),(1,'#d06a14')]:
                        points=[r for r in usable if r['cycle']%2==parity]
                        axes[i,0].plot([r['center_input_time']-sap.time[0] for r in points],[r['depth_fraction']*100 for r in points],
                                       'o-' if name=='SAP' else 'x:',ms=3,lw=.6,color=color,alpha=1 if name=='SAP' else .5,
                                       label=f'{name} {"even" if parity==0 else "odd"}')
                        if name=='SAP':
                            for profile in profiles:
                                if profile['cycle']%2==parity:axes[i,1].plot(profile['phase_from_event'],profile['relative_decrease']*100,'.',ms=.8,alpha=.12,color=color)
                axes[i,0].set(title=f'Event spacing {p*factor:.7f} d',xlabel='Days from start',ylabel='Local depth (%)')
                axes[i,0].legend(fontsize=7,ncol=2)
                axes[i,1].set(title='SAP: overlaid locally normalized minima',xlabel='Offset / event spacing',ylabel='Local light decrease (%)')
            fig.suptitle(f'{row["id"]} / sector {obs["sector"]}: alternate minima and repeated same-family minima')
            dest=run/row['id']/f's{obs["sector"]:04d}-events.png';fig.savefig(dest,dpi=130);plt.close(fig)
            epoch.update(plot=str(dest.relative_to(run)),plot_sha256=sha256(dest));output['observations'].append(epoch)
            print(row['id'],obs['sector'],[(m['product'],m['spacing_factor'],m['summary']) for m in epoch['measurements']],flush=True)
    write_json(run/'event-review.json',output)

if __name__=='__main__':main()
