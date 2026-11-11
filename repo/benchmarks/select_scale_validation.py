"""Select new real controls from metadata only; never read their photometry."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, Counter
import csv, json, re, subprocess
import numpy as np
from astropy.coordinates import SkyCoord, search_around_sky
import astropy.units as u
from vstar.network import ArchiveClient
from vstar.io import read_json, write_json, sha256, now

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/benchmarks/scale-validation-v01'
SEED=2026111101

def previous_tics():
    names=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    ids=set()
    for name in names:
        match=re.search(r'tess\d+-s\d+-(\d+)-',name)
        if match: ids.add(str(int(match[1])))
    for p in [ROOT/'repo/benchmarks/known-controls.json',*list((ROOT/'repo/benchmarks').glob('*/input-manifest.json')),*list((ROOT/'repo/runs').glob('*/targets.json'))]:
        def walk(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in {'tic','TICID','target_name'} and str(v).isdigit():ids.add(str(int(v)))
                    elif isinstance(v,(dict,list)):walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        walk(read_json(p))
    return ids

def usable(r):
    return str(r.get('target_name','')).isdigit() and (r.get('dataURL') or '').endswith('_lc.fits') and '_fast' not in r['dataURL']

def shuffled(items,rng):
    a=sorted(items,key=int);rng.shuffle(a);return a

def query_batch(tics):
    c=ArchiveClient(ROOT/'repo/data/scale-validation-v01',attempts=3)
    filters=[{'paramName':'obs_collection','values':['TESS']},{'paramName':'provenance_name','values':['SPOC']},
             {'paramName':'dataproduct_type','values':['timeseries']},{'paramName':'target_name','values':tics}]
    rows,receipts=c.mast_rows(filters,page_size=5000)
    return {'targets':tics,'rows':rows,'receipts':receipts}

def main():
    if (OUT/'targets.json').exists():raise FileExistsError('Selection is immutable')
    rng=np.random.default_rng(SEED);old=previous_tics()
    catalog=list(csv.DictReader((OUT/'catalogs/tess-ebs.csv').open()))
    cat=defaultdict(list)
    for r in catalog:cat[r['tess_id']].append(r)
    inventory={r['target_name']:r for r in read_json(OUT/'catalogs/mast-inventory.json')['rows'] if usable(r)}
    ids=sorted(set(inventory)-old,key=int)
    coords=SkyCoord([inventory[t]['s_ra'] for t in ids],[inventory[t]['s_dec'] for t in ids],unit='deg')
    neighbors=defaultdict(list)
    ic,jc,dist,_=search_around_sky(coords,SkyCoord([float(r['ra']) for r in catalog],[float(r['dec']) for r in catalog],unit='deg'),126*u.arcsec)
    for i,j,d in zip(ic,jc,dist.arcsec):
        r=catalog[j]
        if ids[i]!=r['tess_id'] and d>10:
            neighbors[ids[i]].append({'tic':r['tess_id'],'period_d':float(r['period']) if r['period'] else None,'ra_deg':float(r['ra']),'dec_deg':float(r['dec']),'sep_arcsec':float(d),'signal_id':r['signal_id']})
    positive=[t for t in ids if t in cat and len(cat[t])==1 and .1<=float(cat[t][0]['period'] or 'nan')<=8]
    risk=[t for t in ids if t not in cat and neighbors[t]]
    field=[t for t in ids if t not in cat and not neighbors[t]]
    pools={'catalog_eb':shuffled(positive,rng)[:650],'neighbor_risk':shuffled(risk,rng),'field_unlabelled':shuffled(field,rng)[:1400]}
    write_json(OUT/'selection-pools.json',{'created_at':now(),'seed':SEED,'previous_tics':sorted(old,key=int),'pools':pools,'candidate_definition':'catalog EB or 10–126 arcsec catalog-EB neighbor or other SPOC field; metadata only','reference_counts':{'inventory_unique':len(inventory),'catalog_unique':len(cat),'positive_eligible':len(positive),'neighbor_risks':len(risk)}})
    allids=sum(pools.values(),[]);responses=[]
    batches=[allids[s:s+50] for s in range(0,len(allids),50)]
    metadata=OUT/'metadata';metadata.mkdir(exist_ok=True)
    pending=[]
    for i,b in enumerate(batches):
        p=metadata/f'batch-{i:03}.json'
        if p.exists():responses.append(read_json(p))
        else:pending.append((i,b))
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(query_batch,b):i for i,b in pending}
        for f in as_completed(tasks):
            i=tasks[f];r=f.result();write_json(metadata/f'batch-{i:03}.json',r);responses.append(r)
            print('metadata',len(responses),'/',len(batches),flush=True)
    observations=defaultdict(dict)
    for response in responses:
        for r in response['rows']:
            if usable(r):
                tic=r['target_name'];s=int(r['sequence_number']);prior=observations[tic].get(s)
                if prior is None or r['dataURL']>prior['dataURL']:observations[tic][s]=r
    cases=[];eligibility=[]
    for group,tics in pools.items():
        quota=400 if group=='catalog_eb' else 200 if group=='neighbor_risk' else 1000-len(cases)
        count=0
        for tic in tics:
            rows=sorted(observations[tic].values(),key=lambda r:(r['t_min'],r['dataURL']))
            okay=len(rows)>=2 and rows[-1]['t_min']-rows[0]['t_min']>=180
            eligibility.append({'tic':tic,'group':group,'available_sectors':len(rows),'spans_180d':okay,'chosen':okay and count<quota})
            if not okay or count>=quota:continue
            first,last=rows[0],rows[-1]
            case={'id':'tic-'+tic,'tic':tic,'group':group,'target':{'ra_deg':inventory[tic]['s_ra'],'dec_deg':inventory[tic]['s_dec']},'inputs':[{'sector':int(r['sequence_number']),'uri':r['dataURL'],'t_min_mjd':r['t_min'],'t_max_mjd':r['t_max']} for r in [first,last]],'reference':cat.get(tic,[]),'catalog_neighbors':neighbors[tic],'truth_status':'catalog_period_reference_source_unverified' if group=='catalog_eb' else 'not_labelled_as_nonvariable','novelty_assessed':False}
            cases.append(case);count+=1
        if group=='catalog_eb' and count!=400:raise ValueError('Insufficient catalog controls; retain metadata and revise plan before analysis')
    if len(cases)!=1000 or len({c['tic'] for c in cases})!=1000:raise ValueError('Incomplete or duplicate selection')
    write_json(OUT/'eligibility.json',eligibility)
    write_json(OUT/'targets.json',{'created_at':now(),'seed':SEED,'counts':dict(Counter(c['group'] for c in cases)),'catalog_sha256':sha256(OUT/'catalogs/tess-ebs.csv'),'cases':cases})
    print('Frozen list',len(cases),dict(Counter(c['group'] for c in cases)),flush=True)

if __name__=='__main__':main()
