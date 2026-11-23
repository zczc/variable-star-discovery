"""Blind frozen-v4 searches for the preselected discovery batch; all outcomes retained."""
import argparse
from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor,as_completed
from pathlib import Path
import subprocess
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from scale_direct_transport import fetch_ranged
from search_discovery_batch import ROOT,OUT


def freeze():
    path=OUT/'analysis-protocol.json'
    if path.exists():return read_json(path)
    targets=read_json(OUT/'targets.json')
    files=[OUT/'pool.json',OUT/'targets.json',OUT/'catalog-screen.json',Path(__file__).resolve(),
           ROOT/'repo/benchmarks/search_discovery_batch.py',ROOT/'repo/benchmarks/scale_direct_transport.py']
    result={'at':now(),'detector_fingerprint':targets['detector_fingerprint'],'science':'Unmodified v4; period 0.05–8 days; defaults match the sealed labelled baseline.',
            'planned':len(targets['cases']),'frozen_files':[{'path':str(p.relative_to(ROOT)),'sha256':sha256(p)} for p in files],
            'novelty_confirmed':False,'submission_ready':False,'reference_information_passed_to_detection':False}
    write_json(path,result);return result


def verify():
    plan=read_json(OUT/'analysis-protocol.json')
    assert code_fingerprint()==plan['detector_fingerprint']
    for r in plan['frozen_files']:assert sha256(ROOT/r['path'])==r['sha256'],r['path']
    return plan


def acquire(case):
    receipt=OUT/'acquisition'/f'{case["tic"]}.json'
    if receipt.exists():
        row=read_json(receipt)
        for r in row['inputs']:assert sha256(ROOT/r['path'])==r['sha256']
        return row
    row={'tic':case['tic'],'inputs':[],'errors':[],'at':now()}
    for spec in case['observations']:
        try:
            p,r=fetch_ranged(spec['dataURL'],case['tic'],int(spec['sequence_number']),OUT/'inputs')
            row['inputs'].append(dict(r,path=str(p.relative_to(ROOT)),sector=int(spec['sequence_number'])))
        except Exception as exc:row['errors'].append({'uri':spec['dataURL'],'error':str(exc)})
    row['status']='available' if len(row['inputs'])==2 and not row['errors'] else 'unavailable'
    write_json(receipt,row);return row


def detect(acquisition):
    from vstar.products import review_products
    from vstar.adjudication import adjudicate
    tic=acquisition['tic'];dest=OUT/'evaluation'/tic
    result={'tic':tic,'at':now(),'inputs':acquisition['inputs'],'errors':acquisition['errors'],
            'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False}
    if acquisition['status']!='available':result['status']='unavailable'
    else:
        assert not dest.exists(),'Partial result directory requires review'
        for r in acquisition['inputs']:assert sha256(ROOT/r['path'])==r['sha256']
        row=review_products([ROOT/r['path'] for r in acquisition['inputs']],dest,identity='TIC '+tic)
        for obs in row['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
        write_json(dest/'case.json',row)
        decision=adjudicate(row,ROOT);write_json(dest/'adjudication.json',decision)
        result.update(status='failed' if row['errors'] else 'completed',errors=row['errors'],
                      decision={k:decision[k] for k in ['status','selected_period_d','preferred_product']},
                      periodic_detected=any(v.get('periodic_detected',False) for v in row['conclusions'].values()),
                      product_conclusions=row['conclusions'])
    write_json(OUT/'results'/f'{tic}.json',result)
    return result


def run():
    plan=verify();cases=read_json(OUT/'targets.json')['cases']
    pending=[c for c in cases if not (OUT/'results'/f'{c["tic"]}.json').exists()]
    with ThreadPoolExecutor(max_workers=4) as downloads,ProcessPoolExecutor(max_workers=2) as analyses:
        jobs=[downloads.submit(acquire,c) for c in pending];calculations=[]
        for job in as_completed(jobs):calculations.append(analyses.submit(detect,job.result()))
        for i,job in enumerate(as_completed(calculations),1):
            r=job.result();print(i,'/',len(pending),r['tic'],r['status'],r.get('decision',{}),flush=True)
    rows=[read_json(OUT/'results'/f'{c["tic"]}.json') for c in cases]
    write_json(OUT/'run-status.json',{'at':now(),'planned':plan['planned'],'completed_records':len(rows),
        'completed':sum(r['status']=='completed' for r in rows),'failed_or_unavailable':sum(r['status']!='completed' for r in rows),
        'selected_periods':sum(r.get('decision',{}).get('selected_period_d') is not None for r in rows),
        'protocol_sha256':sha256(OUT/'analysis-protocol.json'),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})
    print(read_json(OUT/'run-status.json'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','verify','run']);a=p.parse_args()
    if a.action=='freeze':print(freeze())
    elif a.action=='verify':print(verify())
    else:run()
