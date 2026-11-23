"""Batch public VizieR VSX queries, with positive control and per-cone completeness."""
import csv,io,time
from concurrent.futures import ThreadPoolExecutor
import requests
from astropy.coordinates import SkyCoord
from vstar.io import read_json,write_json,now,sha256
from select_discovery_2000 import ROOT,OUT
from catalog_discovery_2000 import summarize


def parse(receipt,count):
    if receipt.get('status_code')!=200:raise ValueError('VSX mirror transport failure')
    body=receipt['body']
    if any('Error=' in line or 'OVERFLOW' in line for line in body.splitlines() if line.startswith('#')):raise ValueError('ASU query error or truncation')
    if body.count('#INFO\t-c=')!=count:raise ValueError('Not all input cones represented')
    rows=[];header=None;data=False
    for line in body.splitlines():
        if line.startswith('#RESOURCE'):header=None;data=False
        if line.startswith('_q\t'):header=line.split('\t');data=False;continue
        if not line.strip() or line.startswith('#') or header is None:continue
        if set(line.replace('\t','').replace(' ',''))=={'-'}:data=True;continue
        if data:
            parts=line.split('\t')
            if len(parts)!=len(header):raise ValueError('ASU row width mismatch')
            row={k:v.strip() for k,v in zip(header,parts)};q=int(row['_q'])
            if not 1<=q<=count:raise ValueError('Unknown input cone index')
            float(row['RAJ2000']);float(row['DEJ2000']);rows.append(row)
    if len(rows)>=10000:raise ValueError('ASU row cap reached')
    if not any(r['_q']=='1' and r['Name']=='RR Lyr' for r in rows):raise ValueError('Missing per-batch RR Lyr positive control')
    return rows


def query(job):
    i,cases=job;folder=OUT/'sources'/f'vsx-mirror-batch-{i:03}'
    coords=['291.36630000+42.78436000']+[f"{c['ra']:.8f}{c['dec']:+.8f}" for c in cases]
    script='\n'.join(['-source=B/vsx/vsx','-out.all','-out.add=_q','-out.max=10000','-c.rs=144','-c=<<====AstroqueryList',*coords,'====AstroqueryList'])
    rows=None;error=None
    for attempt in range(1,4):
        p=folder/f'attempt-{attempt}.json'
        if p.exists():r=read_json(p)
        else:
            r={'at':now(),'url':'https://vizier.idia.ac.za/viz-bin/asu-tsv','method':'POST','script':script,'tics':[c['tic'] for c in cases]}
            try:
                response=requests.post(r['url'],data=script,timeout=(10,60));r.update(status_code=response.status_code,body=response.text)
            except requests.RequestException as exc:r['error']=str(exc)
            write_json(p,r)
        try:rows=parse(r,len(cases)+1);break
        except Exception as exc:error=str(exc)
        time.sleep(2)
    if rows is None:
        write_json(OUT/'catalog-batch-errors'/f'{i:03}.json',{'at':now(),'error':error,'tics':[c['tic'] for c in cases]});print('batch',i,'FAILED',error,flush=True);return
    for j,c in enumerate(cases,2):
        objects=[dict(x,RA2000=x['RAJ2000'],Declination2000=x['DEJ2000']) for x in rows if int(x['_q'])==j]
        point=SkyCoord(c['ra'],c['dec'],unit='deg')
        objects=[dict(o,separation_arcsec=float(point.separation(SkyCoord(float(o['RA2000']),float(o['Declination2000']),unit='deg')).arcsec)) for o in objects]
        result={'at':now(),'tic':c['tic'],'status':'completed','service':'VizieR IDIA public VSX mirror','live_vsx_status':'not_completed_human_verification_barrier','freshness_note':'Public mirror; current online Spot check remains pending for any potential submission.',
                'receipt_path':str(p.relative_to(ROOT)),'receipt_sha256':sha256(p),'objects':objects,'target_positional_matches':[o for o in objects if o['separation_arcsec']<=3],'nearby_variable_count':sum(o['separation_arcsec']<=126 for o in objects),'positive_control_passed':True,'all_query_cones_represented':True}
        dest=OUT/'catalog-vsx'/f'{c["tic"]}.json'
        if not dest.exists() or read_json(dest)['status']!='completed':write_json(dest,result)
    print('batch',i,'completed',len(cases),flush=True)


if __name__=='__main__':
    control=read_json(OUT/'sources/vsx-batch-post-control.json');rows=parse(control,2);assert not any(r['_q']=='2' for r in rows)
    plan=OUT/'vsx-batch-plan.json'
    if plan.exists():cases=read_json(plan)['cases']
    else:
        cases=[c for c in read_json(OUT/'targets.json')['cases'] if not (OUT/'catalog-vsx'/f'{c["tic"]}.json').exists() or read_json(OUT/'catalog-vsx'/f'{c["tic"]}.json')['status']!='completed']
        write_json(plan,{'at':now(),'cases':cases,'method':'ASU multiline input as implemented by astroquery; each batch includes RR Lyr, requires every input cone echoed, validates _q row mapping, preserves failures. No direct live VSX requests.'})
    jobs=list(enumerate([cases[i:i+20] for i in range(0,len(cases),20)]))
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(query,jobs))
    summarize()
