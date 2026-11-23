"""Catalogue screening for every fixed target, independent of blind detection."""
import argparse,csv,io,json,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
from astropy.coordinates import SkyCoord
from vstar.io import read_json,write_json,now,sha256
from select_discovery_2000 import ROOT,OUT,fetch
from triage_discovery_candidates import vsx_objects


def gaia_query(cases,name):
    circles=[f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{c['ra']},{c['dec']},0.00611111112))" for c in cases]
    sql='SELECT TOP 10000 source_id,ra,dec,ref_epoch,pmra,pmdec,phot_g_mean_mag,phot_variable_flag,ruwe FROM gaiadr3.gaia_source WHERE '+' OR '.join(circles)
    receipt=fetch('ari-'+name,'https://gaia.ari.uni-heidelberg.de/tap/sync',{'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv','QUERY':sql})
    if receipt.get('status_code')!=200:raise ValueError('Gaia query incomplete')
    reader=csv.DictReader(io.StringIO(receipt['body']))
    if not {'source_id','ra','dec','phot_variable_flag'}.issubset(reader.fieldnames or []):raise ValueError('Gaia invalid CSV')
    rows=list(reader)
    if len(rows)>=10000:raise ValueError('Gaia truncated')
    for r in rows:int(r['source_id']);float(r['ra']);float(r['dec'])
    return rows


def gaia(batch):
    i,cases=batch;path=OUT/'catalog-gaia'/f'{i:03}.json'
    if path.exists() and read_json(path)['status']=='completed':return read_json(path)
    result={'at':now(),'targets':[c['tic'] for c in cases],'status':'failed','rows':[]}
    try:
        rows=gaia_query(cases,f'gaia-batch-{i:03}')
        coords=SkyCoord([float(r['ra']) for r in rows],[float(r['dec']) for r in rows],unit='deg')
        for c in cases:
            distance=SkyCoord(c['ra'],c['dec'],unit='deg').separation(coords).arcsec
            near=sorted([dict(r,separation_arcsec=float(d)) for r,d in zip(rows,distance) if d<=22],key=lambda r:r['separation_arcsec'])
            row={'tic':c['tic'],'neighbors':near,'identity_status':'unresolved','known_variable':None,'bright_close_neighbors':[]}
            if near and near[0]['separation_arcsec']<=1.5 and near[0]['phot_g_mean_mag']:
                row.update(identity_status='positional_match_requires_alias_confirmation',target=near[0],known_variable=near[0]['phot_variable_flag']=='VARIABLE')
                row['bright_close_neighbors']=[r for r in near[1:] if r['separation_arcsec']<=21 and r['phot_g_mean_mag'] and float(r['phot_g_mean_mag'])-float(near[0]['phot_g_mean_mag'])<5]
            result['rows'].append(row)
        result['status']='completed'
    except Exception as exc:result['error']=str(exc)
    write_json(path,result);return result


def parse_vsx_mirror(receipt):
    if receipt.get('status_code')!=200:raise ValueError('VSX mirror transport failed')
    body=receipt['body']
    if '#Name: B/vsx/vsx' not in body or '#Column\tRAJ2000\t' not in body or '#Column\tn_OID\t' not in body:raise ValueError('Missing complete VSX mirror schema')
    if any(x.startswith('#') and ('Error=' in x or 'OVERFLOW' in x) for x in body.splitlines()):raise ValueError('VSX mirror query error/overflow')
    lines=[x for x in body.splitlines() if x.strip() and not x.startswith('#')]
    if not lines:return []  # ASU schema-only response, validated against saved live empty control.
    sep=next(i for i,x in enumerate(lines) if set(x.replace('\t','').replace(' ',''))=={'-'})
    rows=[{k:v.strip() for k,v in r.items()} for r in csv.DictReader(lines[sep+1:],fieldnames=lines[0].split('\t'),delimiter='\t')]
    if len(rows)>=10000:raise ValueError('VSX mirror truncated')
    return [dict(r,RA2000=r['RAJ2000'],Declination2000=r['DEJ2000']) for r in rows]


def vsx(c):
    path=OUT/'catalog-vsx'/f'{c["tic"]}.json'
    if path.exists() and read_json(path)['status']=='completed':return read_json(path)
    result={'at':now(),'tic':c['tic'],'status':'failed','service':'VizieR IDIA public VSX mirror',
            'live_vsx_status':'not_completed_human_verification_barrier','freshness_note':'Mirror cannot replace the live final Spot check; retain prior live failures separately.'}
    try:
        receipt=fetch('vsx-mirror-'+c['tic'],'https://vizier.idia.ac.za/viz-bin/asu-tsv',{'-source':'B/vsx/vsx','-c':f"{c['ra']} {c['dec']}",'-c.rs':144,'-out.all':1,'-out.max':10000})
        objects=parse_vsx_mirror(receipt);point=SkyCoord(c['ra'],c['dec'],unit='deg')
        near=[dict(o,separation_arcsec=float(point.separation(SkyCoord(float(o['RA2000']),float(o['Declination2000']),unit='deg')).arcsec)) for o in objects]
        result.update(status='completed',objects=near,target_positional_matches=[o for o in near if o['separation_arcsec']<=3],nearby_variable_count=sum(o['separation_arcsec']<=126 for o in near))
    except Exception as exc:result['error']=str(exc)
    write_json(path,result);return result


def controls():
    rr={'tic':'positive-control-RR-Lyr','ra':291.3663,'dec':42.78436}
    r=vsx(rr);assert r['status']=='completed' and any(o['Name']=='RR Lyr' for o in r['objects'])
    mirror=parse_vsx_mirror(read_json(OUT/'sources/vsx-vizier-control/attempt-1.json'));assert any(o['Name']=='RR Lyr' for o in mirror)
    assert parse_vsx_mirror(read_json(OUT/'sources/vsx-vizier-empty-control/attempt-1.json'))==[]
    g=gaia_query([rr],'gaia-positive-control-RR-Lyr')
    assert any(x['phot_variable_flag']=='VARIABLE' for x in g)
    write_json(OUT/'catalog-controls.json',{'at':now(),'vsx_positive_control':True,'gaia_positive_control':True,'fetherolf_all_three_positive_controls':True,'vsx_mirror_positive_and_empty_controls':True})


def summarize():
    cases=read_json(OUT/'targets.json')['cases'];ga={};rows=[]
    for p in (OUT/'catalog-gaia').glob('*.json'):
        r=read_json(p)
        if r['status']=='completed':ga.update({x['tic']:x for x in r['rows']})
    for c in cases:
        tic=c['tic'];p=OUT/'catalog-vsx'/f'{tic}.json';v=read_json(p) if p.exists() else {'status':'pending'}
        g=ga.get(tic);issues=[]
        if g is None:issues.append('gaia_query_incomplete')
        elif g['identity_status']=='unresolved':issues.append('gaia_identity_unresolved')
        else:
            if g['known_variable']:issues.append('gaia_variable')
            if g['bright_close_neighbors']:issues.append('bright_close_neighbor')
        if v['status']!='completed':issues.append('vsx_query_incomplete')
        else:
            if v['target_positional_matches']:issues.append('vsx_target_positional_match')
            elif v['nearby_variable_count']:issues.append('vsx_neighbor')
        rows.append({'tic':tic,'issues':issues,'gaia':g,'vsx':v,'novelty_confirmed':False})
    value={'at':now(),'planned':len(cases),'gaia_queries_complete':sum(x['gaia'] is not None for x in rows),'vsx_queries_complete':sum(x['vsx']['status']=='completed' for x in rows),'issues':dict(Counter(i for r in rows for i in r['issues'])),'rows':rows,'note':'Positional matches require aliases/proper-motion review. NOT_AVAILABLE and catalog absence do not mean constant or new.'}
    write_json(OUT/'catalog-screen.json',value);print({k:v for k,v in value.items() if k not in {'rows','note'}},flush=True)


def run(service):
    cases=read_json(OUT/'targets.json')['cases'];controls()
    if service in ('gaia','both'):
        batches=list(enumerate([cases[i:i+20] for i in range(0,len(cases),20)]))
        with ThreadPoolExecutor(max_workers=3) as pool:
            for i,r in enumerate(pool.map(gaia,batches),1):
                if i%10==0 or r['status']!='completed':print('Gaia batches',i,'/100',r['status'],r.get('error',''),flush=True)
    if service in ('vsx','both'):
        with ThreadPoolExecutor(max_workers=3) as pool:
            for i,r in enumerate(pool.map(vsx,cases),1):
                if i%100==0 or r['status']!='completed':print('VSX',i,'/2000',r['status'],r.get('error',''),flush=True)
    summarize()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['gaia','vsx','both','summary']);a=p.parse_args()
    if a.action=='summary':summarize()
    else:run(a.action)
