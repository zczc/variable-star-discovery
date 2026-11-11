"""Fetch only a mathematically guaranteed subset; do not analyze pixel flux."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import argparse
from vstar.io import read_json,write_json,sha256,now,run_lock
from run_scale_validation import ROOT,OUT,CACHE,verify
from run_scale_source_sample import choose
from scale_range_transport import fetch_ranged

def prepare():
    verify();out=OUT/'source-prefetch.json'
    if out.exists():raise FileExistsError('Prefetch subset already frozen')
    policy=read_json(OUT/'source-sampling-policy.json');groups={'catalog_eb':[],'neighbor_risk':[]};hashes=[]
    for c in read_json(OUT/'targets.json')['cases']:
        if c['group'] not in groups:continue
        p=OUT/'evaluation'/(c['id']+'-prediction.json')
        if not p.exists():raise ValueError('Both completed strata must be fully predicted')
        r=read_json(p);hashes.append({'id':c['id'],'sha256':sha256(p)})
        diagnostic=c['group']=='neighbor_risk' and any(n.get('period_d') and .1<=n['period_d']<=8 for n in c['catalog_neighbors'])
        if r['status']=='completed' and (r.get('decision',{}).get('selected_period_d') is not None or diagnostic):groups[c['group']].append(c)
    cases=[]
    for group,pool in groups.items():
        count=min(policy['quota'][group],len(pool))
        cases+=choose(pool,{group:count},policy['seed'],count)
    write_json(out,{'created_at':now(),'purpose':'Metadata-frozen guaranteed subset of final source sample. Byte transport only; no new pixel maps or source conclusions before full1000 predictions and final source-sample freeze.','guarantee':'Group quotas are selected before the fill step. Future field outcomes can add cases but cannot remove these quota members. Assert subset membership when preparing final sample.','policy_sha256':sha256(OUT/'source-sampling-policy.json'),'code_sha256':sha256(Path(__file__)),'transport_sha256':sha256(Path(__file__).with_name('scale_range_transport.py')),'cases':cases,'prediction_hashes':hashes})
    print('Prepared guaranteed pixel prefetch subset',len(cases))

def fetch_case(c):
    rows=[]
    for item in c['inputs']:
        uri=item['uri'].replace('_lc.fits','_tp.fits')
        try:
            p,r=fetch_ranged(uri,c['tic'],item['sector'],CACHE);rows.append({'uri':uri,'path':str(p.relative_to(ROOT)),'status':'cached','receipt':r})
        except Exception as exc:rows.append({'uri':uri,'status':'failed','error':str(exc)})
    row={'id':c['id'],'completed_at':now(),'products':rows,'pixel_flux_analyzed':False}
    write_json(OUT/'prefetch-results'/(c['id']+'.json'),row);return row

def run():
    verify();manifest=read_json(OUT/'source-prefetch.json')
    assert sha256(Path(__file__))==manifest['code_sha256']
    assert sha256(Path(__file__).with_name('scale_range_transport.py'))==manifest['transport_sha256']
    for item in manifest['prediction_hashes']:assert sha256(OUT/'evaluation'/(item['id']+'-prediction.json'))==item['sha256']
    lock=ROOT/'repo/data/scale-validation-v01/prefetch-lock';lock.mkdir(exist_ok=True)
    with run_lock(lock),ProcessPoolExecutor(max_workers=2) as pool:
        for i,f in enumerate(as_completed([pool.submit(fetch_case,c) for c in manifest['cases']]),1):
            row=f.result();print('prefetch',i,'/',len(manifest['cases']),row['id'],[p['status'] for p in row['products']],flush=True)
    write_json(OUT/'source-prefetch-status.json',{'completed_at':now(),'cases':len(manifest['cases']),'manifest_sha256':sha256(OUT/'source-prefetch.json'),'pixel_flux_analyzed':False})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);a=p.parse_args()
    if a.stage=='prepare':prepare()
    else:run()
