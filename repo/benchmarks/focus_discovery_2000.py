"""Extra-epoch source evidence at explicitly diagnostic photometric periods."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from vstar.io import read_json,write_json,now,sha256
from vstar.source_review import review_case
from select_discovery_2000 import ROOT,OUT
from scale_direct_transport import fetch_ranged


def focus(tic,period):
    dest=OUT/'focused-source'/tic;dest.mkdir(parents=True,exist_ok=True)
    if (dest/'result.json').exists():return
    ext=read_json(OUT/'extension-results'/f'{tic}.json');assert ext['status']=='completed'
    case=next(c for c in read_json(OUT/'targets.json')['cases'] if c['tic']==tic)
    neighbors=read_json(OUT/'catalog-vsx'/f'{tic}.json')
    specfile=dest/'protocol.json'
    if not specfile.exists():write_json(specfile,{'at':now(),'tic':tic,'period_d':period,'period_usage':'diagnostic_only_not_v4_adopted','basis':'Raw-cadence and cross-epoch signal review, separate from unchanged baseline. Add pixel and auxiliary diagnostics for all original and extra epochs.','extension_sha256':sha256(OUT/'extension-results'/f'{tic}.json')})
    inputs=[]
    for item in ext['inputs']:
        path,r=fetch_ranged(item['uri'].replace('_lc.fits','_tp.fits'),tic,item['sector'],OUT/'pixels')
        inputs.append(dict(item,pixels=dict(r,path=str(path.relative_to(ROOT)))))
    target={'ra_deg':case['ra'],'dec_deg':case['dec'],'vsx_neighbors':neighbors['objects']}
    write_json(dest/'inputs.json',{'inputs':inputs,'target':target})
    sub=dest/'source';result=review_case(inputs,{'selected_period_d':None},target,sub,ROOT,diagnostic_period=period)
    write_json(dest/'result.json',result);print(tic,result['conclusion'],result['errors'],flush=True)

if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=2) as p:
        jobs=[p.submit(focus,'232643687',0.3557239884562398),p.submit(focus,'289724676',1.467188050694922)]
        for j in jobs:j.result()
