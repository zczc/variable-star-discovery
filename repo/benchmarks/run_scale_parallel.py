"""Transport scheduling only: reuse frozen acquisition, analysis and source functions."""
from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor,as_completed
from pathlib import Path
import subprocess
from vstar.io import read_json,write_json,sha256,now,run_lock
from run_scale_validation import ROOT,OUT,verify,acquire,analyze_case,source_case

def main():
    verify();addendum=read_json(OUT/'transport-addendum.json')
    assert sha256(Path(__file__))==addendum['launcher_sha256']
    cases=read_json(OUT/'targets.json')['cases'];byid={c['id']:c for c in cases};done=[];pending=[]
    with run_lock(OUT),ThreadPoolExecutor(max_workers=8) as downloads,ProcessPoolExecutor(max_workers=6) as calculations,ProcessPoolExecutor(max_workers=4) as pixels:
        analyses={};sources={};source_done=0
        def enqueue_source(row):
            nonlocal source_done
            dest=OUT/'source-results'/(row['id']+'.json')
            if dest.exists():source_done+=1
            else:sources[pixels.submit(source_case,byid[row['id']])]=row['id']
        def drain_sources():
            nonlocal source_done
            for f in list(sources):
                if f.done():
                    r=f.result();del sources[f];source_done+=1
                    if r['status']!='not_requested':print('source',source_done,'/1000',r['id'],r['status'],r.get('source_review',{}).get('conclusion',{}).get('route'),flush=True)
        def consume(row):
            done.append(row['id']);enqueue_source(row)
            print('analyzed',len(done),'/1000',row['id'],row['status'],'P',row.get('decision',{}).get('selected_period_d'),flush=True)
        for c in cases:
            file=OUT/'evaluation'/(c['id']+'-prediction.json')
            if file.exists():done.append(c['id']);enqueue_source(read_json(file))
            else:
                if (OUT/'evaluation'/c['id']).exists():raise RuntimeError('Partial analysis directory requires audit: '+c['id'])
                pending.append(c)
        print('Starting frozen test:',len(done),'existing,',len(pending),'pending',flush=True)
        jobs={downloads.submit(acquire,c):c['id'] for c in pending}
        for job in as_completed(jobs):
            a=job.result();analyses[calculations.submit(analyze_case,a)]=a['id']
            for f in list(analyses):
                if f.done():consume(f.result());del analyses[f]
            drain_sources()
        for f in as_completed(analyses):consume(f.result());drain_sources()
        for f in as_completed(list(sources)):
            r=f.result();source_done+=1
            if r['status']!='not_requested':print('source',source_done,'/1000',r['id'],r['status'],r.get('source_review',{}).get('conclusion',{}).get('route'),flush=True)
        write_json(OUT/'run-status.json',{'updated_at':now(),'requested':1000,'completed_records':len(done),'source_records':source_done,'full_1000':True,'targets_sha256':sha256(OUT/'targets.json'),'protocol_sha256':sha256(OUT/'protocol.json'),'transport_addendum_sha256':sha256(OUT/'transport-addendum.json'),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})
        print('Finished all scheduled records',len(done),source_done,flush=True)
if __name__=='__main__':main()
