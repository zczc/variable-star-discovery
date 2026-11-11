"""Frozen thousand-target validation; labelled reference periods never enter search."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import argparse, os, subprocess, time
from vstar.io import read_json, write_json, sha256, now, run_lock
from scale_validation_support import fetch_product

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/benchmarks/scale-validation-v01'
CACHE=ROOT/'repo/data/scale-validation-v01/fits'

def verify():
    protocol=read_json(OUT/'protocol.json')
    for item in protocol['frozen_files']:
        if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Frozen code/input changed: '+item['path'])
    return protocol

def acquire(case):
    path=OUT/'acquisition'/(case['id']+'.json')
    if path.exists():
        row=read_json(path)
        for x in row['inputs']:
            if sha256(ROOT/x['path'])!=x['sha256']:raise ValueError('Cached input hash mismatch')
        return row
    start=time.monotonic();row={'id':case['id'],'tic':case['tic'],'inputs':[],'errors':[],'started_at':now()}
    for spec in case['inputs']:
        try:
            f,receipt=fetch_product(spec['uri'],case['tic'],spec['sector'],CACHE)
            row['inputs'].append(dict(spec,path=str(f.relative_to(ROOT)),sha256=receipt['sha256'],raw_sha256=receipt['raw_sha256'],raw_bytes=receipt['raw_bytes'],compressed_bytes=receipt['compressed_bytes']))
        except Exception as exc:row['errors'].append({'uri':spec['uri'],'error':str(exc)})
    row.update(status='available' if len(row['inputs'])==2 and not row['errors'] else 'unavailable',elapsed_seconds=time.monotonic()-start,completed_at=now())
    write_json(path,row);return row

def analyze_case(acquisition):
    from vstar.products import review_products
    from vstar.adjudication import adjudicate
    from vstar.source_review import review_case
    ident=acquisition['id'];folder=OUT/'evaluation'/ident
    start=time.monotonic();row={'id':ident,'started_at':now(),'inputs':acquisition['inputs'],'status':'unavailable'}
    if acquisition['status']!='available':
        row['errors']=acquisition['errors']
    else:
        try:
            for item in acquisition['inputs']:
                if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Input hash mismatch')
            products=review_products([ROOT/x['path'] for x in acquisition['inputs']],folder/'period',identity=ident)
            for obs in products['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
            write_json(folder/'period/case.json',products)
            decision=adjudicate(products,ROOT);write_json(folder/'period/adjudication.json',decision)
            source=review_case(acquisition['inputs'],decision,None,folder/'source-preliminary',ROOT)
            write_json(folder/'source-preliminary/source-review.json',source)
            row.update(status='failed' if products['errors'] or source['errors'] else 'completed',decision=decision,preliminary_source=source,
                product_conclusions=products['conclusions'],errors=products['errors']+source['errors'])
        except Exception as exc:row.update(status='failed',errors=[{'error':str(exc)}])
    row.update(elapsed_seconds=time.monotonic()-start,completed_at=now())
    write_json(OUT/'evaluation'/(ident+'-prediction.json'),row)
    return row

def run(limit,workers):
    verify();cases=read_json(OUT/'targets.json')['cases'];cases=cases if limit is None else cases[:limit]
    pending=[];done=[]
    for case in cases:
        pred=OUT/'evaluation'/(case['id']+'-prediction.json')
        if pred.exists():done.append(read_json(pred))
        else:
            if (OUT/'evaluation'/case['id']).exists():raise RuntimeError('Partial analysis directory requires audit: '+case['id'])
            pending.append(case)
    print('run',len(cases),'existing',len(done),'pending',len(pending),flush=True)
    with ThreadPoolExecutor(max_workers=4) as downloads,ProcessPoolExecutor(max_workers=workers) as calculations:
        jobs={downloads.submit(acquire,c):c['id'] for c in pending};analyses={}
        for job in as_completed(jobs):
            a=job.result();analyses[calculations.submit(analyze_case,a)]=a['id']
            # Consume completed calculations during download as well as after.
            for f in list(analyses):
                if f.done():
                    row=f.result();done.append(row);del analyses[f]
                    print('analyzed',len(done),'/',len(cases),row['id'],row['status'],'P',row.get('decision',{}).get('selected_period_d'),flush=True)
        for f in as_completed(analyses):
            row=f.result();done.append(row)
            print('analyzed',len(done),'/',len(cases),row['id'],row['status'],'P',row.get('decision',{}).get('selected_period_d'),flush=True)
    write_json(OUT/'run-status.json',{'updated_at':now(),'requested':len(cases),'completed_records':len(done),'full_1000':len(cases)==1000,'targets_sha256':sha256(OUT/'targets.json'),'protocol_sha256':sha256(OUT/'protocol.json'),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})

def source_case(case):
    from vstar.source_review import review_case
    ident=case['id'];prediction=read_json(OUT/'evaluation'/(ident+'-prediction.json'))
    dest=OUT/'source-results'/(ident+'.json')
    if dest.exists():return read_json(dest)
    decision=prediction.get('decision',{});selected=decision.get('selected_period_d')
    diagnostic=None
    if selected is None and case['group']=='neighbor_risk':
        candidates=[n for n in case['catalog_neighbors'] if n['period_d'] and .1<=n['period_d']<=8]
        if candidates:diagnostic=min(candidates,key=lambda n:n['sep_arcsec'])['period_d']
    if prediction['status']!='completed' or selected is None and diagnostic is None:
        row={'id':ident,'status':'not_requested','reason':'no selected period, or unavailable analysis; no target-source claim','source_review':prediction.get('preliminary_source')}
        write_json(dest,row);return row
    inputs=[];acquisition_errors=[]
    for item in prediction['inputs']:
        x=dict(item)
        try:
            uri=x['uri'].replace('_lc.fits','_tp.fits');p,r=fetch_product(uri,case['tic'],x['sector'],CACHE)
            x['pixels']={'uri':uri,'path':str(p.relative_to(ROOT)),'sha256':r['sha256'],'raw_sha256':r['raw_sha256'],'raw_bytes':r['raw_bytes'],'compressed_bytes':r['compressed_bytes']}
        except Exception as exc:acquisition_errors.append({'sector':x['sector'],'error':str(exc)})
        inputs.append(x)
    target=dict(case['target']);target['vsx_neighbors']=[{'Name':'TESS-EBs TIC '+n['tic'],'Period':n['period_d'],'RA2000':n['ra_deg'],'Declination2000':n['dec_deg']} for n in case['catalog_neighbors']]
    # Catalog neighbors enrich source attribution only AFTER blind period search.
    folder=OUT/'evaluation'/ident/'source'
    result=review_case(inputs,decision,target,folder,ROOT,diagnostic)
    write_json(folder/'source-review.json',result)
    write_json(folder/'source-manifest.json',{'inputs':inputs,'decision':decision,'target':target,'diagnostic_period':diagnostic})
    row={'id':ident,'status':'completed' if not result['errors'] and not acquisition_errors else 'incomplete','created_at':now(),'source_review':result,'acquisition_errors':acquisition_errors,'catalog_scope':'TESS-EBs frozen catalog only, not exhaustive neighbor identification','diagnostic_period_origin':'nearest catalog EB; source-only diagnostic' if diagnostic else None}
    write_json(dest,row);return row

def sources(limit,workers):
    verify();cases=read_json(OUT/'targets.json')['cases']
    cases=[c for c in cases if (OUT/'evaluation'/(c['id']+'-prediction.json')).exists()]
    if limit is not None:cases=cases[:limit]
    with ProcessPoolExecutor(max_workers=min(workers,3)) as pool:
        futures={pool.submit(source_case,c):c['id'] for c in cases}
        for i,f in enumerate(as_completed(futures),1):
            r=f.result()
            if r['status']!='not_requested':print('source',i,'/',len(cases),r['id'],r['status'],r.get('source_review',{}).get('conclusion',{}).get('route'),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['run','sources']);p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=6);a=p.parse_args()
    if a.limit is not None and not 1<=a.limit<=1000:raise ValueError('limit 1..1000')
    with run_lock(OUT):
        if a.stage=='run':run(a.limit,a.workers)
        else:sources(a.limit,a.workers)

if __name__=='__main__':main()
