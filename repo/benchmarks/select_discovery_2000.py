"""Metadata-only selection of 2,000 new discovery targets. No photometry reads."""
import argparse,csv,hashlib,io,json,time
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
from astropy.coordinates import SkyCoord,search_around_sky
import astropy.units as u
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from select_scale_validation import previous_tics,usable
from search_discovery_batch import collect_tics

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/runs/discovery-2000-2026-11-23'
OLD=ROOT/'repo/benchmarks/scale-validation-v01'
SEED='20261123-discovery-2000-v1'


def fetch(name,url,params,timeout=55):
    dest=OUT/'sources'/name
    for attempt in range(1,4):
        p=dest/f'attempt-{attempt}.json'
        if p.exists():r=read_json(p)
        else:
            r={'at':now(),'url':url,'params':params,'attempt':attempt}
            try:
                response=requests.get(url,params=params,timeout=(12,timeout))
                r.update(status_code=response.status_code,body=response.text)
            except requests.RequestException as exc:r['error']=str(exc)
            write_json(p,r)
        if r.get('status_code')==200:return r
        if attempt<3:time.sleep(attempt*2)
    return r


def parse_tsv(receipt):
    if receipt.get('status_code')!=200:raise ValueError('VizieR transport failed')
    body=receipt['body']
    if '#Table\t' not in body:raise ValueError('Missing table')
    lines=[line for line in body.splitlines() if not line.startswith('#') and line.strip()]
    header=next(i for i,line in enumerate(lines) if 'TIC' in line.split('\t'))
    separator=next(i for i in range(header+1,len(lines)) if set(lines[i].replace('\t','').replace(' ',''))=={'-'})
    rows=list(csv.DictReader(lines[separator+1:],fieldnames=lines[header].split('\t'),delimiter='\t'))
    return [{k:v.strip() for k,v in row.items()} for row in rows]


def catalogs():
    def query(i):
        r=fetch(f'fetherolf-table{i}','https://vizier.idia.ac.za/viz-bin/asu-tsv',
                {'-source':f'J/ApJS/268/4/table{i}','-out':'TIC,Sec','-out.max':300000},90)
        rows=parse_tsv(r)
        controls={1:'99990178',2:'99921371',3:'99920728'}
        assert controls[i] in {x['TIC'] for x in rows}
        assert len(rows)<300000 and 'QUERY_STATUS\tOVERFLOW' not in r['body']
        print('Fetherolf',i,len(rows),flush=True)
        return i,rows
    with ThreadPoolExecutor(max_workers=3) as pool:tables=dict(pool.map(query,[1,2,3]))
    write_json(OUT/'catalog-index.json',{'at':now(),'tables':{str(k):{'rows':len(v),'tics':sorted({r['TIC'] for r in v},key=int)} for k,v in tables.items()},'note':'Published variability records, including candidates; absence is not proof of novelty.'})


def select():
    if (OUT/'targets.json').exists():raise FileExistsError('Selection is immutable')
    index=read_json(OUT/'catalog-index.json');known=set()
    for v in index['tables'].values():known.update(v['tics'])
    excluded=previous_tics();sources=[]
    for folder in [ROOT/'repo/benchmarks',ROOT/'repo/runs']:
        for name in ['targets.json','blind-inputs.json','input-manifest.json','candidates.json','pool.json']:
            for p in folder.glob('*/'+name):
                if p.parent==OUT:continue
                collect_tics(read_json(p),excluded);sources.append(p)
    inventory=OLD/'catalogs/mast-inventory.json';ebpath=OLD/'catalogs/tess-ebs.csv'
    skarka=ROOT/'repo/benchmarks/labelled-validation-v01/sources/north-harvard.txt'
    lines=[x for x in skarka.read_text().splitlines() if x.strip() and not x.startswith('#')]
    for r in csv.DictReader(lines[3:],fieldnames=lines[0].split('\t'),delimiter='\t'):
        r={k:v.strip() for k,v in r.items()}
        if r.get('VType'):known.add(r['Name'])
    eb=list(csv.DictReader(ebpath.open()));known.update(r['tess_id'] for r in eb)
    obs=defaultdict(dict)
    for r in read_json(inventory)['rows']:
        if usable(r):
            tic=str(int(r['target_name']));sec=int(r['sequence_number']);prior=obs[tic].get(sec)
            if prior is None or r['dataURL']>prior['dataURL']:obs[tic][sec]=r
    cases=[];counts=Counter()
    for tic,rs in obs.items():
        if tic in excluded:counts['prior_project_target']+=1;continue
        if tic in known:counts['published_variability']+=1;continue
        rows=sorted(rs.values(),key=lambda r:(r['t_min'],r['dataURL']))
        if len(rows)<2 or rows[-1]['t_min']-rows[0]['t_min']<180:counts['insufficient_inventory_epochs']+=1;continue
        cases.append({'tic':tic,'id':'tic-'+tic,'ra':rows[0]['s_ra'],'dec':rows[0]['s_dec'],'observations':[rows[0],rows[-1]],'selection_rank':hashlib.sha256((SEED+tic).encode()).hexdigest()})
    coords=SkyCoord([c['ra'] for c in cases],[c['dec'] for c in cases],unit='deg')
    ci,ei,ds,_=search_around_sky(coords,SkyCoord([float(r['ra']) for r in eb],[float(r['dec']) for r in eb],unit='deg'),126*u.arcsec)
    near={int(i) for i in ci};counts['known_eb_neighbor_126arcsec']=len(near)
    eligible=sorted([c for i,c in enumerate(cases) if i not in near],key=lambda c:c['selection_rank'])
    assert len(eligible)>=2000
    sources+= [inventory,ebpath,skarka,OUT/'catalog-index.json']
    sources+=list((OUT/'sources').rglob('attempt-*.json'))
    plan={'at':now(),'seed':SEED,'planned':2000,'eligible_count':len(eligible),'exclusions':dict(counts),'prior_excluded_tics':sorted(excluded,key=int),
          'selection':'First 2000 by seeded SHA256 of previously unused standard SPOC targets with >=180-day separation in saved MAST inventory; absent from all three Fetherolf tables and labelled Skarka variables; exclude known TESS EB within 126 arcsec. No new light curve read. Use earliest/latest available inventory sectors, not a claim of complete MAST coverage.',
          'scope':'All 2000 receive two-epoch SAP/PDCSAP v4 analysis and Gaia/VSX screening; every repeated detection receives applicable source and prior-report follow-up. Failures remain in denominator and are retried without replacement. Nondetection is not a nonvariable label.',
          'followup':'Check pixels and auxiliary signals for each repeated detection; examine neighboring identities, known reports, harmonics, additional epochs and independent surveys as applicable. Do not assert source/novelty/submission readiness when evidence remains unresolved. Draft genuine discoveries only; no formal submission.',
          'science':'Unchanged sealed v4; 0.05-8 days, default binning and thresholds. No catalog values passed to detector.',
          'detector_fingerprint':code_fingerprint(),'sources':[{'path':str(p.relative_to(ROOT)),'sha256':sha256(p)} for p in sorted(set(sources))],
          'cases':eligible[:2000]}
    write_json(OUT/'targets.json',plan)
    print({'planned':2000,'eligible':len(eligible),'exclusions':dict(counts)},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['catalogs','select']);a=p.parse_args()
    if a.action=='catalogs':catalogs()
    else:select()
