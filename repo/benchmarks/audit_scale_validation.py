"""Verify preserved inputs and predictions without rescoring or changing rules."""
from pathlib import Path
import gzip,hashlib,json
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
from vstar.io import read_json,write_json,sha256,now
from run_scale_validation import verify,OUT,ROOT

def main():
    verify();targets=read_json(OUT/'targets.json')['cases'];old=read_json(OUT/'preservation-manifest.json')['files']
    for x in old:
        if sha256(ROOT/x['path'])!=x['sha256']:raise ValueError('Old evidence changed: '+x['path'])
    ids={c['tic'] for c in targets};assert len(ids)==len(targets)==1000
    assert not ids&set(read_json(OUT/'selection-pools.json')['previous_tics'])
    assert all(c['inputs'][1]['t_min_mjd']-c['inputs'][0]['t_min_mjd']>=180 for c in targets)
    checked=set();released=set();plots=0;predictions=0;source_records=0;acquisitions=0;source_states=Counter()
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
            source_records+=1;saved=read_json(s);source_states[saved['status']]+=1;source=saved.get('source_review') or {}
            assert not source.get('conclusion',{}).get('confirmed_variable',False)
            if saved['status']=='completed':
                assert len(source['observations'])==2 and not source['errors'] and not saved['acquisition_errors']
                assert all(o.get('pixels') for o in source['observations'])
            for obs in source.get('observations',[]):
                if obs.get('input',{}).get('pixels'):inputs.append(obs['input']['pixels'])
                if obs.get('pixels'):
                    m=obs['pixels'];assert sha256(OUT/'evaluation'/case['id']/'source'/m['plot'])==m['plot_sha256'];plots+=1
        for item in inputs:
            if item['path'] in checked:continue
            path=ROOT/item['path']
            if not path.exists():
                receipt=read_json(OUT/'cache-release'/(path.name+'.json'))
                assert receipt['released'] and receipt['compressed_and_original_bytes_verified']
                assert receipt['case_id']==case['id'] and receipt['input']==item
                assert receipt['receipt']['sha256']==item['sha256'] and receipt['receipt']['raw_sha256']==item['raw_sha256']
                assert receipt['source_result_sha256']==sha256(OUT/'source-results'/(case['id']+'.json'))
                assert receipt['source_manifest_sha256']==sha256(manifest)
                released.add(item['path']);checked.add(item['path']);continue
            assert sha256(path)==item['sha256']
            if item.get('raw_sha256'):
                with gzip.open(path,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['raw_sha256']
            checked.add(item['path'])
    for path in (OUT/'reference-followup').glob('*-manual-review.json'):
        for evidence in read_json(path).get('evidence',[]):
            assert sha256(OUT/evidence['path'])==evidence['sha256']
    for path in (OUT/'reference-followup').glob('*.figure.json'):
        figure=read_json(path);assert sha256(path.parent/figure['plot'])==figure['sha256']
    sample_path=OUT/'source-sample.json';sample_checked=False
    if sample_path.exists():
        from run_scale_source_sample import choose
        sample=read_json(sample_path);policy=read_json(OUT/'source-sampling-policy.json')
        assert sample['policy_sha256']==sha256(OUT/'source-sampling-policy.json')
        for key,name in [('sampler_sha256','run_scale_source_sample.py'),('transport_sha256','scale_range_transport.py')]:
            assert sample[key]==sha256(Path(__file__).with_name(name))
        assert {r['id'] for r in sample['prediction_hashes']}=={c['id'] for c in targets}
        for r in sample['prediction_hashes']:assert r['sha256']==sha256(OUT/'evaluation'/(r['id']+'-prediction.json'))
        eligible=[]
        for c in targets:
            prediction=read_json(OUT/'evaluation'/(c['id']+'-prediction.json'))
            diagnostic=c['group']=='neighbor_risk' and any(n.get('period_d') and .1<=n['period_d']<=8 for n in c['catalog_neighbors'])
            if prediction['status']=='completed' and (prediction.get('decision',{}).get('selected_period_d') is not None or diagnostic):eligible.append(c)
        assert sample['cases']==choose(eligible,policy['quota'],policy['seed'],policy['target_sample_size'])
        assert {c['id'] for c in read_json(OUT/'source-prefetch.json')['cases']}<={c['id'] for c in sample['cases']}
        sample_checked=True
    full_checked=False
    if (OUT/'source-all.json').exists():
        from run_scale_all_sources import eligible
        full=read_json(OUT/'source-all.json')
        for item in full['frozen_runner_files']:assert sha256(Path(__file__).with_name(item['name']))==item['sha256']
        assert {r['id'] for r in full['prediction_hashes']}=={c['id'] for c in targets}
        for r in full['prediction_hashes']:assert r['sha256']==sha256(OUT/'evaluation'/(r['id']+'-prediction.json'))
        expected={c['id'] for c in targets if eligible(c,read_json(OUT/'evaluation'/(c['id']+'-prediction.json')))}
        assert {c['id'] for c in full['cases']}==expected
        full_checked=True
    extra_path=OUT/'source-extra-prefetch.json'
    if extra_path.exists():
        extra=read_json(extra_path)
        assert extra['full_cohort_sha256']==sha256(OUT/'source-all.json')
        for item in extra['frozen_files']:assert sha256(Path(__file__).with_name(item['name']))==item['sha256']
        cohort={c['id']:c for c in read_json(OUT/'source-all.json')['cases']}
        assert extra['cases']==[cohort[i] for i in extra['remaining_ids_at_preparation'][11::4]]
    for plan_path in (OUT/'source-retries').glob('attempt-*/plan.json'):
        retry=read_json(plan_path)
        assert retry['full_cohort_sha256']==sha256(OUT/'source-all.json')
        assert retry['runner_sha256']==sha256(Path(__file__).with_name('retry_scale_source_transport.py'))
        for item in retry['preserved_source_results']:
            assert sha256(OUT/'source-results'/(item['id']+'.json'))==item['sha256']
        for item in retry['cases']:
            ident=item['case']['id'];original=plan_path.parent/'original-results'/(ident+'.json')
            if not original.exists():original=OUT/'source-results'/(ident+'.json')
            assert sha256(original)==item['original_failure_sha256']
            assert read_json(original)['status']=='transport_failed'
    if (OUT/'direct-prefetch/plan.json').exists():
        direct=read_json(OUT/'direct-prefetch/plan.json')
        assert direct['runner_sha256']==sha256(Path(__file__).with_name('prefetch_scale_direct.py'))
        assert direct['transport_sha256']==sha256(Path(__file__).with_name('scale_direct_transport.py'))
        assert direct['verification_sha256']==sha256(OUT/'direct-transport-verification.json')
        assert direct['retry_plan_sha256']==sha256(OUT/'source-retries/attempt-01/plan.json')
        proof=read_json(OUT/'direct-transport-verification.json')
        assert proof['code_sha256']==direct['transport_sha256']
        assert proof['known_input']['sha256']==proof['direct_receipt']['sha256']
        assert proof['known_input']['raw_sha256']==proof['direct_receipt']['raw_sha256']
        assert proof['direct_receipt']['remote_md5_verified']
    result={'checked_at':now(),'target_count':1000,'acquisition_records':acquisitions,'prediction_records':predictions,'source_records':source_records,'source_record_states':dict(source_states),'source_records_meaning':'Includes deferred and not-requested records; these are not completed source reviews.','original_products_verified_now':len(checked-released),'released_original_products_verified_previously':len(released),'plots_verified':plots,'old_files_unchanged':len(old),'frozen_code_unchanged':True,'frozen_source_sample_and_predictions_verified':sample_checked,'frozen_full_source_cohort_and_predictions_verified':full_checked,'independent_truth_adjudication_complete':False,'population_precision_validated':False}
    write_json(OUT/'integrity-audit.json',result);print(json.dumps(result,indent=2))
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):
            self.links.extend(v for k,v in attrs if k in {'href','src'} and v)
    pages=[OUT/'index.html',*sorted((OUT/'evaluation').rglob('*.html'))];missing=[];links=0
    for path in pages:
        parser=Links();parser.feed(path.read_text())
        for link in parser.links:
            url=urlsplit(link)
            if url.scheme or url.netloc or not url.path:continue
            links+=1
            if not (path.parent/unquote(url.path)).exists():missing.append({'page':str(path.relative_to(ROOT)),'link':link})
    write_json(OUT/'html-link-audit.json',{'checked_at':now(),'pages_checked':len(pages),'local_links_checked':links,'missing_links':missing,'scope':'Generated overview and evaluation pages; external catalog snapshots excluded'})
    assert not missing,missing
    print('HTML links verified:',len(pages),'pages,',links,'local links')
if __name__=='__main__':main()
