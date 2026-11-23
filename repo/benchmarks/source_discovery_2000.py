"""Source checks of every cross-epoch detection, including ambiguous periods."""
import argparse,time,traceback
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from vstar.io import read_json,write_json,sha256,now
from vstar.source_review import review_case
from run_discovery_2000 import verify,ROOT,OUT
from scale_direct_transport import fetch_ranged
from catalog_discovery_2000 import vsx


def periods(prediction):
    selected=prediction['decision']['selected_period_d']
    if selected is not None:return [selected]
    values=[]
    for r in prediction['product_conclusions'].values():
        p=r.get('photometric_period_d')
        if r.get('periodic_detected') and p and not any(abs(p/q-1)<.01 for q in values):values.append(p)
    if not values:raise ValueError('Repeated detection without diagnostic period')
    return values


def review(case):
    tic=case['tic'];p=OUT/'results'/f'{tic}.json';prediction=read_json(p)
    assert prediction['status']=='completed' and prediction.get('periodic_detected')
    saved=OUT/'source-results'/f'{tic}.json'
    if saved.exists() and read_json(saved)['status']=='completed':return read_json(saved)
    parent=OUT/'source-evaluation'/tic;parent.mkdir(parents=True,exist_ok=True)
    attempt=len(list(parent.glob('attempt-*')))+1;dest=parent/f'attempt-{attempt:03}';dest.mkdir()
    row={'at':now(),'tic':tic,'attempt':attempt,'prediction_sha256':sha256(p),'status':'incomplete','reviews':[],'errors':[],
         'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False}
    try:
        neighbors=vsx(case)
        if neighbors['status']!='completed':raise ValueError('VSX source-neighbor query incomplete')
        target={'ra_deg':case['ra'],'dec_deg':case['dec'],'vsx_neighbors':neighbors['objects']}
        inputs=[]
        for item in prediction['inputs']:
            path,receipt=fetch_ranged(item['uri'].replace('_lc.fits','_tp.fits'),tic,item['sector'],OUT/'pixels')
            inputs.append(dict(item,pixels=dict(receipt,path=str(path.relative_to(ROOT)))))
        decision=read_json(ROOT/prediction['adjudication_path'])
        spec={'at':now(),'inputs':inputs,'target':target,'decision':decision,'periods':periods(prediction),'period_note':'Selected by frozen v4 if available; otherwise product photometric periods are diagnostic only, never adopted.'}
        write_json(dest/'source-manifest.json',spec)
        for i,period in enumerate(spec['periods']):
            sub=dest/f'period-{i:02}'
            result=review_case(inputs,decision,target,sub,ROOT,diagnostic_period=period)
            write_json(sub/'source-review.json',result)
            row['reviews'].append({'period_d':period,'path':str((sub/'source-review.json').relative_to(ROOT)),'conclusion':result['conclusion'],'errors':result['errors']})
            row['errors']+=result['errors']
        row['status']='completed' if not row['errors'] else 'incomplete'
    except Exception as exc:row['errors'].append({'error':str(exc),'traceback':traceback.format_exc()})
    write_json(dest/'result.json',row);write_json(saved,row);return row


def run(watch):
    verify();cases={c['tic']:c for c in read_json(OUT/'targets.json')['cases']};submitted=set();jobs={}
    with ProcessPoolExecutor(max_workers=2) as pool:
        while True:
            detected=[];records=list((OUT/'results').glob('*.json'))
            for p in records:
                r=read_json(p)
                if r['status']=='completed' and r.get('periodic_detected'):detected.append(r['tic'])
            for tic in detected:
                if tic not in submitted:
                    jobs[pool.submit(review,cases[tic])]=tic;submitted.add(tic)
            if jobs:
                done,_=wait(jobs,timeout=20,return_when=FIRST_COMPLETED)
                for job in done:
                    tic=jobs.pop(job)
                    try:
                        r=job.result();print(tic,r['status'],[x['conclusion']['route'] for x in r['reviews']],r['errors'],flush=True)
                    except Exception as exc:print(tic,'worker_failed',str(exc),flush=True)
            elif not watch or len(records)==2000:break
            else:time.sleep(20)
    write_json(OUT/'source-status.json',{'at':now(),'detected_count':len(detected),'submitted_count':len(submitted),'note':'Execution complete is not source confirmation. Incomplete records remain pending evidence.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');a=p.parse_args();run(a.watch)
