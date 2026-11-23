"""Independent extra-epoch checks for every repeated detection; original results stay fixed."""
import argparse,time,traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from vstar.network import ArchiveClient
from vstar.products import review_products
from vstar.adjudication import adjudicate
from select_discovery_2000 import ROOT,OUT
from select_scale_validation import usable
from scale_direct_transport import fetch_ranged


def extend(case):
    tic=case['tic'];saved=OUT/'extension-results'/f'{tic}.json'
    if saved.exists() and read_json(saved)['status']=='completed':return read_json(saved)
    parent=OUT/'extensions'/tic;parent.mkdir(parents=True,exist_ok=True)
    row={'at':now(),'tic':tic,'status':'incomplete','errors':[],'original_prediction_sha256':sha256(OUT/'results'/f'{tic}.json'),'source_confirmed':False,'novelty_confirmed':False,'submission_ready':False}
    try:
        specpath=parent/'protocol.json'
        if specpath.exists():spec=read_json(specpath)
        else:
            client=ArchiveClient(OUT/'metadata-cache')
            filters=[{'paramName':'obs_collection','values':['TESS']},{'paramName':'provenance_name','values':['SPOC']},{'paramName':'dataproduct_type','values':['timeseries']},{'paramName':'target_name','values':[tic]}]
            rows,receipts=client.mast_rows(filters,page_size=5000)
            write_json(parent/'mast-metadata.json',{'at':now(),'rows':rows,'receipts':receipts})
            used={int(r['sequence_number']) for r in case['observations']};bysector={}
            for r in rows:
                if usable(r) and int(r['sequence_number']) not in used:
                    s=int(r['sequence_number'])
                    if s not in bysector or r['dataURL']>bysector[s]['dataURL']:bysector[s]=r
            available=sorted(bysector.values(),key=lambda r:r['t_min'])
            selected=[]
            if available:
                selected=[available[-1]]
                prior=[r for r in available[:-1] if selected[0]['t_min']-r['t_min']>=180]
                if prior:selected.insert(0,prior[-1])
                elif len(available)>1:selected.insert(0,available[0])
            spec={'at':now(),'tic':tic,'detector_fingerprint':code_fingerprint(),'metadata_sha256':sha256(parent/'mast-metadata.json'),'observations':selected,'rule':'Latest unused standard SPOC sector plus latest unused >=180 days earlier; if unavailable, earliest other unused sector. Choose before downloading new photometry. Use original plus added epochs with unchanged v4; no reference periods passed.'}
            write_json(specpath,spec)
        assert spec['detector_fingerprint']==code_fingerprint()
        acquisition=[]
        for obs in spec['observations']:
            path,r=fetch_ranged(obs['dataURL'],tic,int(obs['sequence_number']),OUT/'extension-inputs')
            acquisition.append(dict(r,path=str(path.relative_to(ROOT)),sector=int(obs['sequence_number'])))
        write_json(parent/'acquisition.json',{'at':now(),'inputs':acquisition})
        original=read_json(OUT/'results'/f'{tic}.json')
        inputs=original['inputs']+acquisition
        attempt=len(list(parent.glob('evaluation-*')))+1;dest=parent/f'evaluation-{attempt:03}'
        result=review_products([ROOT/r['path'] for r in inputs],dest,identity='TIC '+tic)
        for obs in result['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
        write_json(dest/'case.json',result);decision=adjudicate(result,ROOT);write_json(dest/'adjudication.json',decision)
        row.update(status='completed' if not result['errors'] else 'incomplete',errors=result['errors'],inputs=inputs,added_epochs=len(acquisition),
                   case_path=str((dest/'case.json').relative_to(ROOT)),adjudication_path=str((dest/'adjudication.json').relative_to(ROOT)),
                   decision={k:decision[k] for k in ['status','selected_period_d','preferred_product']},product_conclusions=result['conclusions'])
    except Exception as exc:row['errors'].append({'error':str(exc),'traceback':traceback.format_exc()})
    write_json(saved,row);print(tic,row['status'],row.get('added_epochs'),row.get('decision'),row['errors'],flush=True);return row


def run(watch):
    cases={c['tic']:c for c in read_json(OUT/'targets.json')['cases']};done=set()
    while True:
        records=[read_json(p) for p in (OUT/'results').glob('*.json')]
        pending=[r['tic'] for r in records if r['status']=='completed' and r.get('periodic_detected') and r['tic'] not in done]
        with ProcessPoolExecutor(max_workers=2) as pool:list(pool.map(extend,[cases[t] for t in pending]))
        done.update(pending)
        if not watch or len(records)==2000:break
        time.sleep(20)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');a=p.parse_args();run(a.watch)
