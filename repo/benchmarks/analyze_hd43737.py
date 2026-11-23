"""Additional blind sectors for HD 43737; diagnostic searches never overwrite baseline."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

from followup_hd43737 import ROOT,OUT,prepare
from vstar.io import read_json,write_json,sha256,code_fingerprint,now
from scale_direct_transport import fetch_ranged

OLD=ROOT/'repo/benchmarks/scale-validation-v01/evaluation/tic-393386173/period/case.json'


def freeze():
    path=OUT/'additional-observation-plan.json'
    if path.exists():return read_json(path)
    body=json.loads(read_json(OUT/'sources/mast-products.json')['body'])
    assert body['status']=='COMPLETE' and body['paging']['pagesFiltered']==1
    assert len(body['data'])==body['paging']['rowsFiltered']
    selected=[x for x in body['data'] if x['dataURL'].endswith('-s_lc.fits')]
    assert sorted(int(x['sequence_number']) for x in selected)==[6,7,32,33]
    old=read_json(OLD)
    plan={'at':now(),'purpose':'Analyze every unused standard SPOC light curve from the saved completed query; no reference period passed to detection.',
          'new_sectors':[7,32],'reused_sectors':[6,33],'detector_fingerprint':code_fingerprint(),
          'analysis':old['analysis'],'screening':old['screening'],
          'observation_rows':selected,'source_file':str(OLD.relative_to(ROOT)), 'source_sha256':sha256(OLD),
          'additional_diagnostic':'Original 0.05125-day result is close to the old 0.05-day lower bound. Separately inspect raw-cadence LS over 0.01–8 days; not a new validation score or adopted period.',
          'no_threshold_tuning':True,'submission_ready':False}
    write_json(path,plan);return plan


def run():
    from vstar.products import review_products,PRODUCTS,summarize_products
    from vstar.models import AnalysisConfig
    from vstar.screening_v3 import ScreeningConfig,combine_epochs
    from vstar.adjudication import adjudicate
    plan=freeze();assert code_fingerprint()==plan['detector_fingerprint']
    assert sha256(OLD)==plan['source_sha256']
    dest=OUT/'additional-periods'
    if dest.exists():raise FileExistsError('Refuse to overwrite analysis results')
    selected=[r for r in plan['observation_rows'] if int(r['sequence_number']) in plan['new_sectors']]
    def acquire(row):
        path,r=fetch_ranged(row['dataURL'],'393386173',int(row['sequence_number']),OUT/'inputs')
        return dict(r,sector=int(row['sequence_number']),path=str(path.relative_to(ROOT)))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(acquire,selected))
    write_json(OUT/'acquisition.json',{'results':results})
    cfg=ScreeningConfig(**plan['screening'])
    new=review_products([ROOT/r['path'] for r in results],dest,identity='TIC 393386173 / unresolved HD 43737A+B',
                        analysis=AnalysisConfig(**plan['analysis']),config=cfg)
    assert not new['errors'],new['errors']
    # Normalize paths for portable reports and the existing adjudicator.
    for obs in new['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
    write_json(dest/'case.json',new)
    write_json(dest/'adjudication.json',adjudicate(new,ROOT))
    combined=deepcopy(new)
    combined['observations']=read_json(OLD)['observations']+new['observations']
    combined['conclusions']={name:combine_epochs([o['products'][name]['result'] for o in combined['observations']],cfg) for name in PRODUCTS}
    combined['comparison']=summarize_products(combined['conclusions'],[],cfg.epoch_period_tolerance)
    write_json(OUT/'combined-four-sectors.json',combined)
    decision=adjudicate(combined,ROOT)
    write_json(OUT/'combined-adjudication.json',decision)
    print(json.dumps({k:decision[k] for k in ('status','selected_period_d','source_status')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);a=parser.parse_args()
    prepare()
    if a.action=='freeze':print(json.dumps(freeze()))
    else:run()
