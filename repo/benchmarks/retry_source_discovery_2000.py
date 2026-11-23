"""Retry actual transport failures concurrently; do not rerun coverage failures."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from source_discovery_2000 import review,verify,OUT,read_json,write_json,now

def run():
    verify();cases={r['tic']:r for r in read_json(OUT/'targets.json')['cases']};pending=[]
    for p in (OUT/'source-results').glob('*.json'):
        r=read_json(p)
        if r['status']!='completed' and any('Insufficient pixel segment cycles' not in e.get('error','') for e in r['errors']):pending.append(r['tic'])
    write_json(OUT/'source-retry-plan.json',{'at':now(),'tics':pending,'workers':3,'reason':'Disk reserve restored using verified public data archive. Reuse original product bytes and partial transfers; no scientific thresholds changed. Former sequential worker interrupted first.'})
    with ProcessPoolExecutor(max_workers=3) as ex:
        jobs={ex.submit(review,cases[t]):t for t in pending}
        for j in as_completed(jobs):
            r=j.result();print(r['tic'],r['status'],[e.get('error') for e in r['errors']],flush=True)
if __name__=='__main__':run()
