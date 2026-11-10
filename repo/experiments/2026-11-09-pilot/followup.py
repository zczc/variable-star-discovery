import json,requests,concurrent.futures
from pathlib import Path
from scan import ROOT,download,analyze
ids=['458747716','259238257','10604247']
def mast(tic):
    req={'service':'Mast.Caom.Filtered','params':{'columns':'obsid,obs_id,target_name,s_ra,s_dec,sequence_number,t_min,t_max,dataURL','filters':[{'paramName':'obs_collection','values':['TESS']},{'paramName':'dataproduct_type','values':['timeseries']},{'paramName':'target_name','values':[tic]}]},'format':'json','pagesize':500,'page':1}
    r=requests.post('https://mast.stsci.edu/api/v0/invoke',data={'request':json.dumps(req)},timeout=60);r.raise_for_status();j=r.json()
    (ROOT/f'observations-{tic}.json').write_text(json.dumps(j,indent=2));return j['data']
def tic_info(row):
    req={'service':'Mast.Catalogs.Filtered.Tic.Position','params':{'columns':'ID,ra,dec,Tmag,Teff,rad,mass,GAIA,pmRA,pmDEC','ra':row['s_ra'],'dec':row['s_dec'],'radius':0.05,'filters':[]},'format':'json','pagesize':500,'page':1}
    r=requests.post('https://mast.stsci.edu/api/v0/invoke',data={'request':json.dumps(req)},timeout=60);r.raise_for_status();j=r.json();(ROOT/f'tic-neighbors-{row["target_name"]}.json').write_text(json.dumps(j,indent=2));return j
def go(tic):
    rows=mast(tic);rows=[r for r in rows if r['dataURL'] and '_fast' not in r['dataURL']];rows=sorted(rows,key=lambda r:r['sequence_number'])
    print('OBSERVATIONS',tic,[r['sequence_number'] for r in rows],flush=True)
    tic_info(rows[-1])
    others=[r for r in rows if r['sequence_number']!=85]
    chosen=[]
    if others:chosen.append(others[0])
    if len(others)>1:chosen.append(others[-1])
    if len(others)>2:chosen.append(others[len(others)//2])
    result=[]
    for row in chosen:
        try:
            p=download(row);out=dict(row);out.update(analyze(p));out['file']=p.name;result.append(out)
            print('FOLLOWUP',tic,row['sequence_number'],{k:out[k] for k in ['period_d','power','phase_amplitude_pct','first_period','second_period','crowdsap']},flush=True)
        except Exception as e:print('ERROR',tic,str(e),flush=True)
    (ROOT/f'followup-{tic}.json').write_text(json.dumps(result,indent=2))
with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(go,ids))
