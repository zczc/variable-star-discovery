"""Identity, cross-survey and literature receipts for every repeated detection."""
import argparse,csv,io,json,time
from concurrent.futures import ThreadPoolExecutor
import requests
from vstar.io import read_json,write_json,now
from select_discovery_2000 import ROOT,OUT,fetch
from followup_discovery_catalogs import parse_asassn,parse_gaia


def tap(name,sql,gaia=False):
    endpoint='https://gaia.ari.uni-heidelberg.de/tap/sync' if gaia else 'https://simbad.idia.ac.za/simbad/sim-tap/sync'
    r=fetch(name,endpoint,{'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv' if gaia else 'json','QUERY':sql})
    if r.get('status_code')!=200:raise ValueError(name+' transport failure')
    if gaia:
        reader=csv.DictReader(io.StringIO(r['body']))
        if not reader.fieldnames or '<' in ','.join(reader.fieldnames):raise ValueError(name+' invalid CSV')
        return list(reader)
    data=json.loads(r['body'])
    if not isinstance(data.get('metadata'),list) or not isinstance(data.get('data'),list):raise ValueError(name+' missing TAP data')
    return [dict(zip([m['name'] for m in data['metadata']],row)) for row in data['data']]


def identity(tic):
    p=OUT/'sources'/f'tic-{tic}'/'response.json'
    if p.exists():r=read_json(p)
    else:
        req={'service':'Mast.Catalogs.Filtered.Tic','params':{'columns':'*','filters':[{'paramName':'ID','values':[tic]}]},'format':'json','pagesize':1000,'page':1}
        r={'at':now(),'url':'https://mast.stsci.edu/api/v0/invoke','request':req}
        try:
            response=requests.post(r['url'],data={'request':json.dumps(req)},timeout=(10,45));r.update(status_code=response.status_code,body=response.text)
        except requests.RequestException as exc:r['error']=str(exc)
        write_json(p,r)
    if r.get('status_code')!=200:raise ValueError('TIC transport incomplete')
    data=json.loads(r['body'])
    if data.get('status')!='COMPLETE' or len(data.get('data',[]))!=1 or str(data['data'][0]['ID'])!=tic:raise ValueError('TIC identity incomplete')
    return data['data'][0]


def follow(case):
    tic=case['tic'];saved=OUT/'followup-results'/f'{tic}.json'
    if saved.exists() and read_json(saved)['status']=='completed':return read_json(saved)
    row={'at':now(),'tic':tic,'status':'incomplete','services':{},'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False}
    def save(name,fn):
        try:row['services'][name]={'status':'completed','data':fn()}
        except Exception as exc:row['services'][name]={'status':'failed','error':str(exc)}
        write_json(saved,row)
    save('tic',lambda:identity(tic))
    ident=row['services']['tic'].get('data',{})
    aliases=['TIC '+tic]
    for key,prefix in [('GAIA','Gaia DR2 '),('TWOMASS','2MASS J'),('HIP','HIP ')]:
        if ident.get(key):aliases.append(prefix+str(ident[key]))
    if ident.get('GAIA'):
        save('gaia_dr2_dr3',lambda:tap(f'dr2-dr3-{tic}',f"SELECT dr2_source_id,dr3_source_id,angular_distance,magnitude_difference FROM gaiadr3.dr2_neighbourhood WHERE dr2_source_id={int(ident['GAIA'])}",True))
        aliases += ['Gaia DR3 '+r['dr3_source_id'] for r in row['services'].get('gaia_dr2_dr3',{}).get('data',[])]
    quoted=','.join("'"+a.replace("'","''")+"'" for a in aliases)
    save('simbad_identity',lambda:tap(f'simbad-identities-{tic}',f'SELECT i.id,b.oid,b.main_id,b.otype,b.ra,b.dec,b.nbref,b.sp_type FROM basic AS b JOIN ident AS i ON b.oid=i.oidref WHERE i.id IN ({quoted})'))
    oids=sorted({r['oid'] for r in row['services']['simbad_identity'].get('data',[])})
    # Query the surrounding field as well: a companion may have a separate name/report.
    save('simbad_cone',lambda:tap(f'simbad-cone-{tic}',f"SELECT TOP 1000 oid,main_id,otype,ra,dec,sp_type FROM basic WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{case['ra']},{case['dec']},0.04))"))
    cone=row['services']['simbad_cone'].get('data',[])
    if len(cone)>=1000:row['services']['simbad_cone']['status']='truncated'
    alloids=sorted(set(oids)|{r['oid'] for r in cone})
    if alloids:
        sqlids=','.join(str(x) for x in alloids)
        save('simbad_aliases',lambda:tap(f'simbad-aliases-{tic}',f'SELECT oidref,id FROM ident WHERE oidref IN ({sqlids})'))
        save('simbad_alltypes',lambda:tap(f'simbad-types-{tic}',f'SELECT oidref,otypes FROM alltypes WHERE oidref IN ({sqlids})'))
        save('simbad_references',lambda:tap(f'simbad-references-{tic}',f'SELECT h.oidref,r.bibcode,r.title,r.doi,r.abstract FROM has_ref AS h JOIN ref AS r ON h.oidbibref=r.oidbib WHERE h.oidref IN ({sqlids})'))
    def gaia():
        sql=f'''SELECT TOP 1000 g.source_id,g.ref_epoch,g.ra,g.dec,g.pmra,g.pmdec,g.phot_g_mean_mag,g.phot_variable_flag,g.ruwe,c.best_class_name,c.best_class_score,c.classifier_name,s.num_selected_g_fov,s.trimmed_range_mag_g_fov,s.in_vari_eclipsing_binary,s.in_vari_rotation_modulation,s.in_vari_ms_oscillator FROM gaiadr3.gaia_source AS g LEFT OUTER JOIN gaiadr3.vari_classifier_result AS c ON g.source_id=c.source_id LEFT OUTER JOIN gaiadr3.vari_summary AS s ON g.source_id=s.source_id WHERE 1=CONTAINS(POINT('ICRS',g.ra,g.dec),CIRCLE('ICRS',{case['ra']},{case['dec']},0.00611111112))'''
        r=fetch(f'gaia-classification-{tic}','https://gaia.ari.uni-heidelberg.de/tap/sync',{'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv','QUERY':sql})
        if r.get('status_code')!=200:raise ValueError('Gaia followup transport incomplete')
        return parse_gaia(r['body'])
    save('gaia_classification',gaia)
    def asassn():
        r=fetch(f'asassn-{tic}','https://asas-sn.osu.edu/variables',{'ra':case['ra'],'dec':case['dec'],'radius':2.4,'show_non_periodic':'on','show_without_class':'on','sort_by':'distance','sort_order':'asc'})
        if r.get('status_code')!=200:raise ValueError('ASAS-SN transport incomplete')
        parsed=parse_asassn(r['body'])
        if parsed['pagination_present']:raise ValueError('ASAS-SN incomplete pagination')
        return parsed
    save('asassn',asassn)
    row['aliases_searched']=aliases;row['target_simbad_oids']=oids
    row['status']='completed' if all(r['status']=='completed' for r in row['services'].values()) else 'incomplete'
    row['note']='Catalogue query completion only; literature references/abstracts require review, aliases require cross-identification, and no match does not establish novelty.'
    write_json(saved,row);print(tic,row['status'],{k:v['status'] for k,v in row['services'].items()},flush=True);return row


def run(watch):
    cases={c['tic']:c for c in read_json(OUT/'targets.json')['cases']};done=set()
    while True:
        records=[read_json(p) for p in (OUT/'results').glob('*.json')]
        pending=[r['tic'] for r in records if r['status']=='completed' and r.get('periodic_detected') and r['tic'] not in done]
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda tic:follow(cases[tic]),pending))
        done.update(pending)
        if not watch or len(records)==2000:break
        time.sleep(20)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');a=p.parse_args();run(a.watch)
