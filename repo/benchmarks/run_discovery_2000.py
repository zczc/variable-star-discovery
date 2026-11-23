"""Resumable, blind frozen-v4 analysis of all 2000 fixed targets."""
import argparse,os,subprocess,time,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor,wait,FIRST_COMPLETED
from vstar.io import read_json,write_json,sha256,now,code_fingerprint,run_lock
from scale_direct_transport import fetch_ranged
from select_discovery_2000 import ROOT,OUT


def freeze():
    path=OUT/'analysis-protocol.json'
    if path.exists():return verify()
    targets=read_json(OUT/'targets.json')
    files=[OUT/'targets.json']+[ROOT/'repo/benchmarks'/n for n in ['select_discovery_2000.py','run_discovery_2000.py','scale_direct_transport.py','scale_validation_support.py','select_scale_validation.py','search_discovery_batch.py']]
    plan={'at':now(),'planned':2000,'detector_fingerprint':targets['detector_fingerprint'],'reference_information_passed_to_detection':False,
          'frozen_files':[{'path':str(p.relative_to(ROOT)),'sha256':sha256(p)} for p in files],
          'completion':'Every fixed target retains successful analysis or explicit failure. Retry transport failures without substitution. Downstream scientific gates remain separate from execution success.',
          'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False}
    write_json(path,plan);return plan


def verify():
    plan=read_json(OUT/'analysis-protocol.json')
    assert plan['planned']==2000 and code_fingerprint()==plan['detector_fingerprint']
    for r in plan['frozen_files']:assert sha256(ROOT/r['path'])==r['sha256'],r['path']
    assert len(read_json(OUT/'targets.json')['cases'])==2000
    return plan


def acquire(case):
    dest=OUT/'acquisition'/case['tic'];dest.mkdir(parents=True,exist_ok=True)
    saved=sorted(dest.glob('attempt-*.json'))
    if saved:
        last=read_json(saved[-1])
        if last['status']=='available':
            for r in last['inputs']:assert sha256(ROOT/r['path'])==r['sha256']
            return last
    row={'tic':case['tic'],'inputs':[],'errors':[],'at':now(),'attempt':len(saved)+1}
    for spec in case['observations']:
        try:
            p,r=fetch_ranged(spec['dataURL'],case['tic'],int(spec['sequence_number']),OUT/'inputs')
            row['inputs'].append(dict(r,path=str(p.relative_to(ROOT)),sector=int(spec['sequence_number'])))
        except Exception as exc:row['errors'].append({'uri':spec['dataURL'],'error':str(exc)})
    row['status']='available' if len(row['inputs'])==2 and not row['errors'] else 'unavailable'
    write_json(dest/f'attempt-{row["attempt"]:03}.json',row);return row


def detect(acquisition):
    from vstar.products import review_products
    from vstar.adjudication import adjudicate
    tic=acquisition['tic'];parent=OUT/'evaluation'/tic
    parent.mkdir(parents=True,exist_ok=True)
    attempt=len(list(parent.glob('attempt-*')))+1;dest=parent/f'attempt-{attempt:03}'
    result={'tic':tic,'at':now(),'inputs':acquisition['inputs'],'errors':acquisition['errors'],'attempt':attempt,
            'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False,'status':'unavailable'}
    if acquisition['status']=='available':
        try:
            for r in acquisition['inputs']:assert sha256(ROOT/r['path'])==r['sha256']
            row=review_products([ROOT/r['path'] for r in acquisition['inputs']],dest,identity='TIC '+tic)
            for obs in row['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
            write_json(dest/'case.json',row)
            decision=adjudicate(row,ROOT);write_json(dest/'adjudication.json',decision)
            result.update(status='failed' if row['errors'] else 'completed',errors=row['errors'],
                case_path=str((dest/'case.json').relative_to(ROOT)),adjudication_path=str((dest/'adjudication.json').relative_to(ROOT)),
                decision={k:decision[k] for k in ['status','selected_period_d','preferred_product']},
                periodic_detected=any(v.get('periodic_detected',False) for v in row['conclusions'].values()),product_conclusions=row['conclusions'])
        except Exception as exc:result.update(status='failed',errors=[{'error':str(exc),'traceback':traceback.format_exc()}])
    write_json(dest/'result.json',result)
    write_json(OUT/'results'/f'{tic}.json',result)
    return result


def status():
    rows=[read_json(p) for p in (OUT/'results').glob('*.json')]
    result={'at':now(),'planned':2000,'records':len(rows),'completed':sum(r['status']=='completed' for r in rows),
            'failed_or_unavailable':sum(r['status']!='completed' for r in rows),
            'repeated_detections':sum(bool(r.get('periodic_detected')) for r in rows),
            'selected_periods':sum(r.get('decision',{}).get('selected_period_d') is not None for r in rows),
            'acquired_targets':sum(1 for p in (OUT/'acquisition').glob('*/attempt-*.json') if read_json(p)['status']=='available'),
            'protocol_sha256':sha256(OUT/'analysis-protocol.json')}
    write_json(OUT/'run-status.json',result);return result


def run(download_workers,analysis_workers):
    verify();cases=read_json(OUT/'targets.json')['cases']
    pending=[c for c in cases if not (OUT/'results'/f'{c["tic"]}.json').exists() or read_json(OUT/'results'/f'{c["tic"]}.json')['status']!='completed']
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    with run_lock(OUT),ThreadPoolExecutor(max_workers=download_workers) as downloads,ProcessPoolExecutor(max_workers=analysis_workers) as analyses:
        jobs={downloads.submit(acquire,c):('acquire',c['tic']) for c in pending}
        finished=0;last_finished=0;last=time.monotonic()
        while jobs:
            done,_=wait(jobs,timeout=30,return_when=FIRST_COMPLETED)
            for job in done:
                kind,tic=jobs.pop(job)
                try:r=job.result()
                except Exception as exc:
                    write_json(OUT/'orchestration-errors'/f'{tic}-{time.time_ns()}.json',{'at':now(),'stage':kind,'tic':tic,'error':str(exc)})
                    print('ERROR',kind,tic,str(exc),flush=True);continue
                if kind=='acquire':jobs[analyses.submit(detect,r)]=('detect',tic)
                else:
                    finished+=1
                    if r.get('periodic_detected') or r['status']!='completed':print('RESULT',tic,r['status'],r.get('decision'),flush=True)
            if finished-last_finished>=20 or time.monotonic()-last>30:
                print(status(),flush=True);last=time.monotonic();last_finished=finished
        print(status(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','verify','run','status']);p.add_argument('--downloads',type=int,default=8);p.add_argument('--analyses',type=int,default=4);a=p.parse_args()
    if a.action=='freeze':print({'planned':freeze()['planned']})
    elif a.action=='verify':print({'verified':verify()['planned']})
    elif a.action=='status':print(status())
    else:run(a.downloads,a.analyses)
