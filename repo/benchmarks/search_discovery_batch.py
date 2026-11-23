"""Metadata-first discovery batch; frozen v4, known reports and crowding screened first."""
import argparse
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv,io,json,hashlib
from pathlib import Path
import requests
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from triage_discovery_candidates import vsx_objects
from select_scale_validation import previous_tics,usable

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/runs/discovery-batch-2026-11-23'
OLD=ROOT/'repo/benchmarks/scale-validation-v01'
SEED='20261123-metadata-first'


def fetch(name,url,params):
    path=OUT/'sources'/f'{name}.json'
    if path.exists():return read_json(path)
    row={'at':now(),'url':url,'params':params}
    try:
        r=requests.get(url,params=params,timeout=(10,40));row.update(status_code=r.status_code,body=r.text)
    except requests.RequestException as exc:row['error']=str(exc)
    write_json(path,row);return row


def collect_tics(value,result):
    if isinstance(value,dict):
        for k,v in value.items():
            if k in {'tic','TICID','target_name'} and str(v).isdigit():result.add(str(int(v)))
            elif isinstance(v,(dict,list)):collect_tics(v,result)
    elif isinstance(value,list):
        for v in value:collect_tics(v,result)


def prepare():
    path=OUT/'pool.json'
    if path.exists():return read_json(path)
    excluded=previous_tics()
    records=[]
    for folder in [ROOT/'repo/benchmarks',ROOT/'repo/runs']:
        for name in ['targets.json','blind-inputs.json','input-manifest.json','candidates.json']:
            for p in folder.glob('*/'+name):
                collect_tics(read_json(p),excluded);records.append(p)
    observations=defaultdict(dict)
    meta=sorted((OLD/'metadata').glob('*.json'))
    for p in meta:
        for r in read_json(p)['rows']:
            if usable(r):
                tic=r['target_name'];sec=int(r['sequence_number'])
                if sec not in observations[tic] or r['dataURL']>observations[tic][sec]['dataURL']:observations[tic][sec]=r
    field=read_json(OLD/'selection-pools.json')['pools']['field_unlabelled']
    candidates=[]
    for tic in field:
        if tic in excluded:continue
        rows=sorted(observations[tic].values(),key=lambda r:(r['t_min'],r['dataURL']))
        if len(rows)<2 or rows[-1]['t_min']-rows[0]['t_min']<180:continue
        candidates.append({'tic':tic,'id':'tic-'+tic,'ra':rows[0]['s_ra'],'dec':rows[0]['s_dec'],
                           'observations':[rows[0],rows[-1]],'selection_rank':hashlib.sha256((SEED+tic).encode()).hexdigest()})
    candidates.sort(key=lambda r:r['selection_rank']);chosen=candidates[:100]
    assert len(chosen)==100
    value={'at':now(),'seed':SEED,'prior_excluded_count':len(excluded),'eligible_unused_count':len(candidates),
           'selection':'First 100 by seeded SHA256 ordering of unused field metadata with two standard sectors at least 180 days apart. No new photometry read.',
           'screening':'Reject exact prior Fetherolf/Skarka reports or Gaia VARIABLE. Defer unidentified Gaia target, bright neighbor within 21 arcsec (delta G < 5), or known VSX variable within 126 arcsec. These restrictions improve tractability, not a validated source guarantee.',
           'analysis_cap':20,'detector_fingerprint':code_fingerprint(),'min_period_d':.05,'max_period_d':8,
           'claim_scope':'Candidate search, not an independent accuracy test. No previous nondetections called nonvariables.',
           'sources':[{'path':str(p.relative_to(ROOT)),'sha256':sha256(p)} for p in sorted(set(records+meta))],
           'excluded_tics':sorted(excluded,key=int),'cases':chosen}
    write_json(path,value);print('Fixed metadata pool',len(chosen),'from',len(candidates),'unused eligible targets');return value


def parse_tsv(receipt):
    if receipt.get('status_code')!=200:raise ValueError('VizieR transport failed')
    body=receipt['body']
    if '#Table\t' not in body or 'TIC\t' not in body:raise ValueError('Missing VizieR table')
    lines=[x for x in body.splitlines() if x.strip() and not x.startswith('#')]
    reader=csv.DictReader(lines[3:],fieldnames=lines[0].split('\t'),delimiter='\t')
    return [{k:v.strip() for k,v in r.items()} for r in reader]


def screen():
    if (OUT/'targets.json').exists():raise FileExistsError('Frozen detection list exists; use saved screening results')
    plan=prepare();cases=plan['cases'];jobs=[];controls={1:'99990178',2:'99921371',3:'99920728'}
    for i,control in controls.items():
        jobs.append((f'fetherolf-{i}','https://vizier.idia.ac.za/viz-bin/asu-tsv',
                     {'-source':f'J/ApJS/268/4/table{i}','TIC':','.join([r['tic'] for r in cases]+[control]),'-out.all':1,'-out.max':10000}))
    for i in range(0,len(cases),20):
        expressions=[f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{r['ra']},{r['dec']},0.00611111112))" for r in cases[i:i+20]]
        sql='SELECT TOP 10000 source_id,ra,dec,ref_epoch,pmra,pmdec,phot_g_mean_mag,phot_variable_flag FROM gaiadr3.gaia_source WHERE '+ ' OR '.join(expressions)
        jobs.append((f'gaia-{i//20}','https://gea.esac.esa.int/tap-server/tap/sync',{'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv','QUERY':sql}))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for _ in pool.map(lambda j:fetch(*j),jobs):pass
    known=defaultdict(list)
    for i,control in controls.items():
        rows=parse_tsv(read_json(OUT/'sources'/f'fetherolf-{i}.json'))
        assert control in {r['TIC'] for r in rows},f'Positive control missing in table {i}'
        assert len(rows)<10000
        for r in rows:known[r['TIC']].append({'source':f'Fetherolf 2023 table {i}','row':r})
    skarka=ROOT/'repo/benchmarks/labelled-validation-v01/sources/north-harvard.txt'
    lines=[x for x in skarka.read_text().splitlines() if x.strip() and not x.startswith('#')]
    for r in csv.DictReader(lines[3:],fieldnames=lines[0].split('\t'),delimiter='\t'):
        r={k:v.strip() for k,v in r.items()}
        if r.get('VType'):known[r['Name']].append({'source':'Skarka 2022','row':r})
    results=[];gaia_rows={}
    for i in range(5):
        r=read_json(OUT/'sources'/f'gaia-{i}.json')
        if r.get('status_code')!=200:continue
        rows=list(csv.DictReader(io.StringIO(r['body'])))
        if not rows or 'source_id' not in rows[0] or len(rows)>=10000:continue
        gaia_rows[i]=rows
    for index,case in enumerate(cases):
        result={'tic':case['tic'],'prior_reports':known.get(case['tic'],[]),'route':None}
        if index//20 not in gaia_rows:
            result['route']='gaia_query_incomplete';results.append(result);continue
        rows=gaia_rows[index//20]
        point=SkyCoord(case['ra'],case['dec'],unit='deg')
        sep=point.separation(SkyCoord([float(x['ra']) for x in rows],[float(x['dec']) for x in rows],unit='deg')).arcsec
        near=sorted([dict(r,separation_arcsec=float(d)) for r,d in zip(rows,sep) if d<=22],key=lambda r:r['separation_arcsec'])
        result['gaia_neighbors']=near
        if not near or near[0]['separation_arcsec']>1.5 or not near[0]['phot_g_mean_mag']:
            result['route']='gaia_identity_unresolved'
        else:
            target=near[0];result['gaia_target']=target
            close=[r for r in near[1:] if r['separation_arcsec']<=21 and r['phot_g_mean_mag'] and float(r['phot_g_mean_mag'])-float(target['phot_g_mean_mag'])<5]
            result['bright_close_neighbors']=close
            if result['prior_reports'] or target['phot_variable_flag']=='VARIABLE':result['route']='prior_variability_report'
            elif close:result['route']='crowded_deferred'
            else:result['route']='awaiting_vsx'
        results.append(result)
    lookup={r['tic']:r for r in cases}
    pending=[r for r in results if r['route']=='awaiting_vsx']
    def vsx(r):
        c=lookup[r['tic']]
        return r,fetch('vsx-'+r['tic'],'https://vsx.aavso.org/index.php',{'view':'api.list','ra':c['ra'],'dec':c['dec'],'radius':.04,'format':'json'})
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row,receipt in pool.map(vsx,pending):
            try:
                assert receipt.get('status_code')==200
                objects=vsx_objects(json.loads(receipt['body']))
                point=SkyCoord(lookup[row['tic']]['ra'],lookup[row['tic']]['dec'],unit='deg')
                near=[dict(o,separation_arcsec=float(point.separation(SkyCoord(float(o['RA2000']),float(o['Declination2000']),unit='deg')).arcsec)) for o in objects]
                row['vsx_objects']=near
                row['route']='vsx_neighbor_or_target_deferred' if any(o['separation_arcsec']<=126 for o in near) else 'eligible_for_blind_detection'
            except (ValueError,KeyError,AssertionError):row['route']='vsx_query_incomplete'
    eligible=[r for r in results if r['route']=='eligible_for_blind_detection']
    selected=eligible[:plan['analysis_cap']]
    write_json(OUT/'catalog-screen.json',{'at':now(),'counts':dict(Counter(r['route'] for r in results)),'rows':results,
        'scope':'Catalogue and isolation screen only; no confirmation of novelty/source/variability. Gaia positions compared at catalog epoch without propagation; ambiguous matches deferred.'})
    frozen={'at':now(),'pool_sha256':sha256(OUT/'pool.json'),'screen_sha256':sha256(OUT/'catalog-screen.json'),
            'detector_fingerprint':plan['detector_fingerprint'],'cases':[lookup[r['tic']] for r in selected],
            'all_eligible':len(eligible),'planned':len(selected),'remaining_eligible_deferred':len(eligible)-len(selected),
            'scientific_note':'Analysis capped before reading any new light curve. Retain every result and failure.'}
    write_json(OUT/'targets.json',frozen)
    print('Catalog screening',dict(Counter(r['route'] for r in results)),'chosen',len(selected),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','screen']);a=parser.parse_args()
    if a.action=='prepare':prepare()
    else:screen()
