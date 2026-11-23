"""Bounded transport-only prefetch; same frozen inputs and checks, no detection."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from vstar.io import read_json,write_json,now
from run_discovery_2000 import verify,ROOT,OUT
from scale_direct_transport import fetch_ranged

def fetch(job):
    tic,spec=job
    try:
        p,r=fetch_ranged(spec['dataURL'],tic,int(spec['sequence_number']),OUT/'inputs')
        return {'tic':tic,'uri':spec['dataURL'],'status':'available'}
    except Exception as e:return {'tic':tic,'uri':spec['dataURL'],'status':'failed','error':str(e)}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--order',choices=['reverse','middle'],default='reverse');ap.add_argument('--workers',type=int,default=16);args=ap.parse_args()
    verify();cases=read_json(OUT/'targets.json')['cases']
    ordered=list(reversed(cases)) if args.order=='reverse' else sorted(cases,key=lambda c:abs(cases.index(c)-len(cases)//2))
    jobs=[(c['tic'],s) for c in ordered for s in c['observations'] if not (OUT/'inputs'/(s['dataURL'].split('/')[-1]+'.gz')).exists()]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i,r in enumerate(pool.map(fetch,jobs),1):
            if r['status']!='available':write_json(OUT/'prefetch-errors'/f'{r["tic"]}-{r["uri"].split("/")[-1]}.json',dict(r,at=now()))
            if i%100==0 or r['status']!='available':print(i,'/',len(jobs),r,flush=True)
