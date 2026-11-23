"""Read-only component-aware follow-up; failures remain distinct from empty matches."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import requests
from vstar.io import now,read_json,write_json,sha256,code_fingerprint

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/runs/hd43737-followup-2026-11-23'


def fetch(name,url,params=None,data=None):
    path=OUT/'sources'/f'{name}.json'
    if path.exists():return read_json(path)
    r={'at':now(),'url':url,'params':params,'data':data,'method':'POST' if data else 'GET'}
    try:
        response=requests.request(r['method'],url,params=params,data=data,timeout=(10,40))
        r.update(status_code=response.status_code,resolved_url=response.url,body=response.text)
    except requests.RequestException as e:r['error']=str(e)
    write_json(path,r)
    print(name,r.get('status_code','transport_failed'),flush=True)
    return r


def tap(name,sql):
    return fetch(name,'https://simbad.idia.ac.za/simbad/sim-tap/sync',
                 params={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'json','QUERY':sql})


def parse_tap(name):
    r=read_json(OUT/'sources'/f'{name}.json')
    assert r.get('status_code')==200,name
    d=json.loads(r['body']);cols=[m['name'] for m in d['metadata']]
    assert isinstance(d['data'],list)
    return [dict(zip(cols,row)) for row in d['data']]


def prepare():
    p=OUT/'plan.json'
    if p.exists():return read_json(p)
    old=ROOT/'repo/benchmarks/scale-validation-v01'
    paths=[ROOT/'repo/runs/discovery-followup-2026-11-20/candidates.json',
           old/'evaluation/tic-393386173/period/case.json',
           old/'evaluation/tic-393386173/period/adjudication.json',
           old/'source-results/tic-393386173.json']
    plan={'created_at':now(),'tic':'393386173','scope':'Search both stellar components and the unresolved system before considering additional data or source attribution.',
          'prior_period_d':0.051250784881620076,'simbad_oids':[11467043,883219,883218],
          'gaia_ids':['5574663835616721536','5574663835616722048'],
          'detector_fingerprint':code_fingerprint(),'detector_changes':False,
          'original_results_preserved':True,'formal_submission':False,
          'inputs':[{'path':str(x.relative_to(ROOT)),'sha256':sha256(x)} for x in paths]}
    write_json(p,plan);return plan


if __name__=='__main__':
    prepare()
    jobs=[
      ('simbad-aliases',"SELECT oidref,id FROM ident WHERE oidref IN (11467043,883219,883218)"),
      ('simbad-references',"SELECT h.oidref,r.bibcode,r.title,r.doi,r.abstract FROM has_ref AS h JOIN ref AS r ON h.oidbibref=r.oidbib WHERE h.oidref IN (11467043,883219,883218)"),
      ('simbad-basic',"SELECT oid,main_id,otype,ra,dec,sp_type FROM basic WHERE oid IN (11467043,883219,883218)")]
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda j:tap(*j),jobs))
    fetch('vsx-cone','https://vsx.aavso.org/index.php',params={'view':'api.list','ra':94.02693014443,'dec':-38.57953714005,'radius':.04,'format':'json'})
