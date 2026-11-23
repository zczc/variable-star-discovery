"""Reconcile all targets, stage records, immutable science, and public archives."""
import argparse,gzip,hashlib,json,subprocess
from collections import Counter
from select_discovery_2000 import ROOT,OUT,read_json,write_json,sha256,now
from run_discovery_2000 import verify

def run(require_archive=False):
    protocol=verify();cases=read_json(OUT/'targets.json')['cases'];expected={c['tic'] for c in cases}
    predictions={p.stem:read_json(p) for p in (OUT/'results').glob('*.json')};assert set(predictions)==expected and len(expected)==2000
    assert all(r['status']=='completed' and not r['errors'] for r in predictions.values())
    detected={t for t,r in predictions.items() if r['periodic_detected']};assert len(detected)==43
    assert sum(r['decision']['selected_period_d'] is not None for r in predictions.values())==6
    inputs={i['path']:i for r in predictions.values() for i in r['inputs']};assert len(inputs)==4000
    errors=[];counts=Counter();source_failures={}
    for tic in detected:
        for folder in ['extension-results','followup-results','source-results']:
            r=read_json(OUT/folder/f'{tic}.json');counts[folder]+=1
            if folder=='source-results':
                if r['errors']:
                    assert all('Insufficient pixel segment cycles' in e.get('error','') for e in r['errors']),(tic,r['errors'])
                    source_failures[tic]=[e['error'] for e in r['errors']]
                for rev in r['reviews']:
                    s=read_json(ROOT/rev['path'])
                    for obs in s['observations']:
                        pix=obs['input'].get('pixels')
                        if pix:inputs[pix['path']]=pix
            else:assert r['status']=='completed',(tic,folder)
            if folder=='extension-results':
                for i in r['inputs']:inputs[i['path']]=i
        d=read_json(OUT/'raw-cadence'/tic/'summary.json');assert d['tic']==tic and d['diagnostic_only'];counts['raw-cadence']+=1
    # Inputs of incomplete segment reviews are in source manifests even when no observation was emitted.
    for p in list((OUT/'source-evaluation').glob('*/attempt-*/source-manifest.json'))+list((OUT/'focused-source').glob('*/inputs.json')):
        for i in read_json(p)['inputs']:
            inputs[i['path']]=i
            if i.get('pixels'):inputs[i['pixels']['path']]=i['pixels']
    archive={};assets={}
    if require_archive:
        repo='zczc/variable-star-discovery';tag='discovery-2000-2026-11-23-data'
        result=subprocess.check_output(['gh','api',f'repos/{repo}/releases/tags/{tag}'],cwd=ROOT,text=True);remote=json.loads(result);assets={a['name']:a for a in remote['assets']}
    for p in (OUT/'data-archive').glob('*.json'):
        r=read_json(p)
        if not p.name.startswith(('shard-','evidence-')):continue
        if r.get('status')!='published':
            if require_archive:errors.append('Unpublished archive '+p.name)
            continue
        if require_archive:
            if r.get('parts'):
                assert sum(p['bytes'] for p in r['parts'])==r['archive_bytes']
                for part in r['parts']:
                    a=assets[part['asset']['name']];assert a['digest']=='sha256:'+part['sha256'] and a['size']==part['bytes']
            else:
                a=assets[r['archive']];assert a['digest']=='sha256:'+r['archive_sha256'] and a['size']==r['archive_bytes']
        for f in r['files']:
            assert f['path'] not in archive,'duplicate archive input';archive[f['path']]=f
    for rel,r in inputs.items():
        path=ROOT/rel
        if path.exists():
            assert sha256(path)==r['sha256'],rel
            with gzip.open(path,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==r['raw_sha256'],rel
            counts['local_verified_fits']+=1
        else:
            assert rel in archive and archive[rel]['sha256']==r['sha256'] and archive[rel]['raw_sha256']==r['raw_sha256'],rel
            ledger=(OUT/'data-archive'/('pixel-release' if '_tp.fits' in rel else 'input-release')/(path.name+'.json'))
            l=read_json(ledger);assert l['released'] and l['remote_sha256_verified'] and l['input']['sha256']==r['sha256'],rel
            counts['archived_and_released_fits']+=1
        if require_archive:
            if rel not in archive:errors.append('Unarchived FITS '+rel)
            else:assert archive[rel]['sha256']==r['sha256']
    for p in (OUT/'evaluation').rglob('*.png'):
        rel=str(p.relative_to(ROOT));counts['bulk_png']+=1
        if require_archive:
            if rel not in archive:errors.append('Unarchived PNG '+rel)
            else:assert sha256(p)==archive[rel]['sha256']
    for p in (OUT/'late-catalogs').rglob('*.zip'):
        rel=str(p.relative_to(ROOT))
        if require_archive:
            if rel not in archive:errors.append('Unarchived catalogue '+rel)
            else:assert sha256(p)==archive[rel]['sha256']
    tars=read_json(OUT/'tars-zenodo-crossmatch.json');assert tars['catalogue_rows']==1046317 and len(tars['matches'])==200
    c24=read_json(OUT/'rotation2024-zenodo-crossmatch.json');assert c24['catalogue_rows']==17100
    summary=read_json(OUT/'final-summary.json');assert summary['completed']==2000 and summary['submission_ready']==0
    assert summary['source_execution'].get('incomplete',0)==0
    value={'at':now(),'status':'passed' if not errors else 'pending_archive','archive_required':require_archive,'counts':dict(counts),'original_lightcurves':4000,'unique_input_products':len(inputs),'expected_targets':2000,'detected':43,
           'source_coverage_limitations':source_failures,'errors':errors,'frozen_protocol_sha256':sha256(OUT/'analysis-protocol.json'),'detector_fingerprint':protocol['detector_fingerprint']}
    write_json(OUT/('verification-final.json' if require_archive else 'verification-local.json'),value)
    print(json.dumps({k:v for k,v in value.items() if k not in ['errors','source_coverage_limitations']},indent=2));print('Errors',len(errors),errors[:5]);assert not errors

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--require-archive',action='store_true');a=p.parse_args();run(a.require_archive)
