"""Verify preserved inputs and predictions without rescoring or changing rules."""
from pathlib import Path
import gzip,hashlib,json
from vstar.io import read_json,write_json,sha256,now
from run_scale_validation import verify,OUT,ROOT

def main():
    verify();targets=read_json(OUT/'targets.json')['cases'];old=read_json(OUT/'preservation-manifest.json')['files']
    for x in old:
        if sha256(ROOT/x['path'])!=x['sha256']:raise ValueError('Old evidence changed: '+x['path'])
    ids={c['tic'] for c in targets};assert len(ids)==len(targets)==1000
    assert not ids&set(read_json(OUT/'selection-pools.json')['previous_tics'])
    assert all(c['inputs'][1]['t_min_mjd']-c['inputs'][0]['t_min_mjd']>=180 for c in targets)
    checked=set();plots=0;predictions=0;source_records=0;acquisitions=0
    for case in targets:
        a=OUT/'acquisition'/(case['id']+'.json')
        if a.exists():acquisitions+=1
        p=OUT/'evaluation'/(case['id']+'-prediction.json')
        if not p.exists():continue
        row=read_json(p);predictions+=1
        assert row['id']==case['id']
        if row['status']=='completed':assert len(row['inputs'])==2 and not row.get('errors')
        inputs=list(row['inputs'])
        if row.get('decision'):assert not row['decision']['confirmed_variable']
        products=OUT/'evaluation'/case['id']/'period/case.json'
        if products.exists():
            for obs in read_json(products)['observations']:
                assert sha256(products.parent/obs['plot'])==obs['plot_sha256'];plots+=1
        manifest=OUT/'evaluation'/case['id']/'source/source-manifest.json'
        if manifest.exists():
            for observation in read_json(manifest)['inputs']:
                if observation.get('pixels'):inputs.append(observation['pixels'])
        s=OUT/'source-results'/(case['id']+'.json')
        if s.exists():
            source_records+=1;source=read_json(s).get('source_review') or {}
            assert not source.get('conclusion',{}).get('confirmed_variable',False)
            for obs in source.get('observations',[]):
                if obs.get('input',{}).get('pixels'):inputs.append(obs['input']['pixels'])
                if obs.get('pixels'):
                    m=obs['pixels'];assert sha256(OUT/'evaluation'/case['id']/'source'/m['plot'])==m['plot_sha256'];plots+=1
        for item in inputs:
            if item['path'] in checked:continue
            path=ROOT/item['path'];assert sha256(path)==item['sha256']
            if item.get('raw_sha256'):
                with gzip.open(path,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['raw_sha256']
            checked.add(item['path'])
    result={'checked_at':now(),'target_count':1000,'acquisition_records':acquisitions,'prediction_records':predictions,'source_records':source_records,'original_products_verified':len(checked),'plots_verified':plots,'old_files_unchanged':len(old),'frozen_code_unchanged':True,'independent_truth_adjudication_complete':False,'population_precision_validated':False}
    write_json(OUT/'integrity-audit.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
