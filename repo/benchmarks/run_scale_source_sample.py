"""Fixed sample of source reviews after blind thousand-star period predictions."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,hashlib,os
from vstar.io import read_json,write_json,sha256,now,run_lock
from run_scale_validation import ROOT,OUT,verify,source_case,CACHE
from scale_range_transport import fetch_ranged

def choose(cases,quota,seed,total):
    key=lambda c:(hashlib.sha256((seed+':'+c['tic']).encode()).hexdigest(),c['tic'])
    ordered=sorted(cases,key=key);chosen=[]
    for group,limit in quota.items():chosen.extend([c for c in ordered if c['group']==group][:limit])
    ids={c['tic'] for c in chosen}
    chosen.extend([c for c in ordered if c['tic'] not in ids][:max(0,total-len(chosen))])
    if len(chosen)!=total or len({c['tic'] for c in chosen})!=total:raise ValueError('Insufficient or duplicate eligible source targets')
    return sorted(chosen,key=key)

def prepare():
    verify();path=OUT/'source-sample.json'
    if path.exists():raise FileExistsError('Source sample already frozen')
    policy=read_json(OUT/'source-sampling-policy.json');eligible=[];predictions=[]
    for c in read_json(OUT/'targets.json')['cases']:
        p=OUT/'evaluation'/(c['id']+'-prediction.json')
        if not p.exists():raise ValueError('Wait for all1000 predictions before sampling')
        r=read_json(p);predictions.append({'id':c['id'],'sha256':sha256(p)})
        diagnostic=c['group']=='neighbor_risk' and any(n.get('period_d') and .1<=n['period_d']<=8 for n in c['catalog_neighbors'])
        if r['status']=='completed' and (r.get('decision',{}).get('selected_period_d') is not None or diagnostic):eligible.append(c)
    sample=choose(eligible,policy['quota'],policy['seed'],policy['target_sample_size'])
    write_json(path,{'created_at':now(),'policy_sha256':sha256(OUT/'source-sampling-policy.json'),'sampler_sha256':sha256(Path(__file__)),'transport_sha256':sha256(Path(__file__).with_name('scale_range_transport.py')),'eligible_count':len(eligible),'eligible_ids':[c['id'] for c in eligible],'cases':sample,'prediction_hashes':predictions})
    print('Prepared source sample',len(sample),'eligible',len(eligible),flush=True)

def review_with_prefetch(case):
    saved=OUT/'source-results'/(case['id']+'.json')
    if saved.exists():return read_json(saved)
    prediction=read_json(OUT/'evaluation'/(case['id']+'-prediction.json'))
    try:
        for item in prediction['inputs']:
            fetch_ranged(item['uri'].replace('_lc.fits','_tp.fits'),case['tic'],item['sector'],CACHE)
    except Exception as exc:
        row={'id':case['id'],'status':'transport_failed','created_at':now(),'source_review':{},'acquisition_errors':[{'uri':item['uri'].replace('_lc.fits','_tp.fits'),'error':str(exc)}],'meaning':'No source conclusion; preserve transport failure for retry/audit'}
        write_json(saved,row);return row
    return source_case(case)

def run(workers):
    verify();sample=read_json(OUT/'source-sample.json')
    if not 1<=workers<=8:raise ValueError('Use at most8 source workers')
    if sha256(Path(__file__))!=sample['sampler_sha256']:raise ValueError('Frozen sampler changed')
    if sha256(Path(__file__).with_name('scale_range_transport.py'))!=sample['transport_sha256']:raise ValueError('Frozen transport changed')
    for item in sample['prediction_hashes']:
        if sha256(OUT/'evaluation'/(item['id']+'-prediction.json'))!=item['sha256']:raise ValueError('Prediction changed after sampling')
    archive=OUT/'source-deferrals';archive.mkdir(exist_ok=True)
    for c in sample['cases']:
        p=OUT/'source-results'/(c['id']+'.json')
        if p.exists() and read_json(p)['status']=='deferred_source_review':
            dest=archive/p.name
            if dest.exists():raise FileExistsError('Deferral already archived; audit before retry')
            os.replace(p,dest)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i,f in enumerate(as_completed([pool.submit(review_with_prefetch,c) for c in sample['cases']]),1):
            r=f.result();print('sample source',i,'/100',r['id'],r['status'],r.get('source_review',{}).get('conclusion',{}).get('route'),flush=True)
    write_json(OUT/'source-sample-status.json',{'completed_at':now(),'requested':len(sample['cases']),'sample_sha256':sha256(OUT/'source-sample.json'),'meaning':'All sampled jobs returned records; incomplete evidence and failures remain incomplete, not passed.'})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    with run_lock(OUT):
        if a.stage=='prepare':prepare()
        else:run(a.workers)
