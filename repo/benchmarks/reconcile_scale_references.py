"""Post-prediction catalog cross-checks, never fed back into frozen detection."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from vstar.io import read_json,write_json,now
from vstar.network import ArchiveClient
from scale_validation_support import period_relation
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'repo/benchmarks/scale-validation-v01'

def reconcile(c):
    path=OUT/'reference-followup'/(c['id']+'-vsx.json')
    if path.exists():receipt=read_json(path)
    else:
        client=ArchiveClient(ROOT/'repo/data/scale-validation-v01/catalog-followup')
        objects,query=client.vsx(c['target']['ra_deg'],c['target']['dec_deg'])
        receipt={'objects':objects,'receipt':query,'use':'Post-prediction reference review; never fed to detector'};write_json(path,receipt)
    pred=read_json(OUT/'evaluation'/(c['id']+'-prediction.json'));selected=pred['decision']['selected_period_d'];reference=float(c['reference'][0]['period'])
    matches=[]
    for obj in receipt['objects']:
        if obj.get('sep_arcsec',999)>2:continue
        try:p=float(obj.get('Period') or 0)
        except (ValueError,TypeError):continue
        if p<=0:continue
        matches.append({'name':obj['Name'],'oid':obj.get('OID'),'period_d':p,'sep_arcsec':obj['sep_arcsec'],'selected_agrees':abs(selected/p-1)<=.01,'old_reference_agrees':abs(reference/p-1)<=.01,'type':obj.get('VariabilityType')})
    status='query_failed' if receipt['receipt']['status']!='completed' else 'no_close_period_reference' if not matches else 'reference_conflict_supports_selected' if any(m['selected_agrees'] and not m['old_reference_agrees'] for m in matches) else 'reference_supports_catalog' if any(m['old_reference_agrees'] for m in matches) else 'references_disagree'
    row={'tic':c['tic'],'id':c['id'],'selected_period_d':selected,'frozen_catalog_period_d':reference,'status':status,'close_matches':matches,'confirmed_correct':False,'note':'Catalog comparison only. Period definition, original references and source still require review; keep frozen original score.'}
    write_json(OUT/'reference-followup'/(c['id']+'-comparison.json'),row);return row

def main():
    cases=[]
    for c in read_json(OUT/'targets.json')['cases']:
        file=OUT/'evaluation'/(c['id']+'-prediction.json')
        if c['group']!='catalog_eb' or not file.exists():continue
        r=read_json(file);p=r.get('decision',{}).get('selected_period_d')
        if p and period_relation(p,float(c['reference'][0]['period']))!='catalog_period_match':cases.append(c)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=[]
        for f in as_completed([pool.submit(reconcile,c) for c in cases]):
            r=f.result();rows.append(r);print(r['tic'],r['status'],flush=True)
    write_json(OUT/'reference-followup/summary.json',{'updated_at':now(),'scope':'All completed catalogue-group period disagreements at this timestamp','cases':rows})
if __name__=='__main__':main()
