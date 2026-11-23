"""Publish unchanged public FITS in bounded GitHub data assets, with SHA256 receipts."""
import argparse,gzip,hashlib,json,os,shutil,subprocess,tarfile,time
from pathlib import Path
from vstar.io import read_json,write_json,sha256,now
from select_discovery_2000 import ROOT,OUT
REPO='zczc/variable-star-discovery';TAG='discovery-2000-2026-11-23-data'
DEST=OUT/'data-archive';STAGE=ROOT/'repo/data/discovery-2000-publish'


def gh(*args):
    for attempt in range(3):
        try:return subprocess.check_output(['gh',*args],cwd=ROOT,text=True,timeout=120)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
            if attempt==2:raise
            time.sleep(2**attempt)


def identity():
    assert subprocess.check_output(['git','remote','get-url','origin'],cwd=ROOT,text=True).strip()=='https://github.com/'+REPO+'.git'
    assert subprocess.check_output(['git','remote','get-url','--push','origin'],cwd=ROOT,text=True).strip()=='https://github.com/'+REPO+'.git'
    assert gh('api','user','--jq','.login').strip()=='zczc'


def setup():
    identity();DEST.mkdir(exist_ok=True);STAGE.mkdir(parents=True,exist_ok=True)
    body=DEST/'README.md'
    body.write_text('''# Public photometry archive: 2000-target discovery search

Unchanged public TESS SPOC FITS, compressed losslessly. This is a data archive for reproducibility. It is not an announcement of new variables or a VSX submission. The fixed target/protocol commit is fd0d79e9.

Each tar asset contains repository-relative `.fits.gz` paths. The adjacent `shard-NNN.json` in the repository records compressed and original FITS SHA256 hashes, public MAST URIs and the verified GitHub asset digest. Original acquisition receipts, scripts, results and plots remain in the repository. Extract an asset from the repository root to restore exactly those file bytes. No private credentials or user data are included.

GitHub release: https://github.com/zczc/variable-star-discovery/releases/tag/discovery-2000-2026-11-23-data
''')
    try:return json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'))
    except subprocess.CalledProcessError:
        gh('release','create',TAG,'--repo',REPO,'--target',subprocess.check_output(['git','rev-parse','fd0d79e9'],cwd=ROOT,text=True).strip(),'--title','Public TESS inputs for the 2000-target search','--notes-file',str(body),'--prerelease','--latest=false')
        return json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'))


def receipt(path):
    r=read_json(path.with_name(path.name[:-3]+'.receipt.json'))
    assert sha256(path)==r['sha256']
    with gzip.open(path,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==r['raw_sha256']
    return {'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':r['sha256'],'raw_sha256':r['raw_sha256'],'raw_bytes':r['raw_bytes'],'uri':r['uri']}


def upload(max_shards):
    release=setup();saved=list(DEST.glob('shard-*.json'));recorded={r['path'] for p in saved for r in read_json(p)['files']}
    pending=[]
    for folder in ['pixels','extension-inputs','inputs']:
        for p in sorted((OUT/folder).glob('*.fits.gz')):
            if str(p.relative_to(ROOT)) not in recorded and p.with_name(p.name[:-3]+'.receipt.json').exists():pending.append(p)
    groups=[];group=[];size=0
    for p in pending:
        if size+p.stat().st_size>400_000_000 and group:groups.append(group);group=[];size=0
        group.append(p);size+=p.stat().st_size
    if group:groups.append(group)
    # Recover and finish prepared shards before starting more.
    for p in sorted(DEST.glob('shard-*.json')):
        r=read_json(p)
        if r.get('status')!='published':publish(p,r)
    for group in groups[:max_shards or None]:
        if shutil.disk_usage(STAGE).free<6_500_000_000:raise OSError('Keep 6GB reserve plus archive staging')
        n=len(list(DEST.glob('shard-*.json')))+1;name=f'tess-inputs-{n:03}.tar';path=STAGE/name
        files=[receipt(p) for p in group]
        with tarfile.open(path,'w') as tar:
            for p in group:tar.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
        r={'at':now(),'status':'prepared','archive':name,'archive_bytes':path.stat().st_size,'archive_sha256':sha256(path),'files':files,'original_and_compressed_hashes_verified':True,'source':'Public TESS SPOC archive'}
        manifest=DEST/f'shard-{n:03}.json';write_json(manifest,r);publish(manifest,r)


def publish(manifest,r):
    path=STAGE/r['archive'];assert path.exists() and sha256(path)==r['archive_sha256']
    identity();release=json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'))
    assets=[a for a in release['assets'] if a['name']==r['archive']]
    if not assets and r['archive_bytes']>32_000_000:
        return publish_parts(manifest,r,path)
    if not assets:
        try:gh('release','upload',TAG,str(path),'--repo',REPO)
        except subprocess.CalledProcessError:
            # A lost final response can report failure after a successful upload.
            # Reconcile exact name/size/digest below; never overwrite an asset.
            pass
        release=json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'));assets=[a for a in release['assets'] if a['name']==r['archive']]
    assert len(assets)==1;asset=assets[0]
    assert asset['state']=='uploaded' and asset['size']==r['archive_bytes']
    assert asset.get('digest')=='sha256:'+r['archive_sha256'],'Remote asset digest missing or mismatched; do not release local copies'
    r.update(status='published',published_at=now(),asset={k:asset.get(k) for k in ['id','name','size','digest','browser_download_url','created_at']})
    write_json(manifest,r);path.unlink();print('Published',r['archive'],len(r['files']),r['archive_bytes'],flush=True)


def publish_parts(manifest,r,path):
    """Bound each HTTP upload; concatenate ordered parts before tar extraction."""
    chunk_bytes=16_000_000
    r.setdefault('parts',[])
    with path.open('rb') as source:
        index=0
        while block:=source.read(chunk_bytes):
            index+=1;name=r['archive']+f'.part-{index:03}';digest=hashlib.sha256(block).hexdigest()
            release=json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'))
            assets=[a for a in release['assets'] if a['name']==name]
            if not assets:
                part=STAGE/name;part.write_bytes(block)
                identity()
                try:gh('release','upload',TAG,str(part),'--repo',REPO)
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired):pass
                release=json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'));assets=[a for a in release['assets'] if a['name']==name]
            assert len(assets)==1 and assets[0]['state']=='uploaded',name
            asset=assets[0];assert asset['size']==len(block) and asset.get('digest')=='sha256:'+digest,name
            entry={'index':index,'bytes':len(block),'sha256':digest,'asset':{k:asset.get(k) for k in ['id','name','size','digest','browser_download_url','created_at']}}
            if len(r['parts'])>=index:assert r['parts'][index-1]['sha256']==digest
            else:r['parts'].append(entry)
            write_json(manifest,r);(STAGE/name).unlink(missing_ok=True);print('Verified part',name,flush=True)
    assert sum(p['bytes'] for p in r['parts'])==r['archive_bytes']
    r.update(status='published',published_at=now(),part_reassembly='Concatenate parts in index order; verify archive_sha256, then extract tar at repository root.')
    write_json(manifest,r);path.unlink();print('Published multipart',r['archive'],len(r['parts']),flush=True)


def release_pixels():
    mapping={r['path']:(r,p) for p in DEST.glob('shard-*.json') if read_json(p).get('status')=='published' for r in read_json(p)['files']}
    count=0;released=0
    for p in (OUT/'source-results').glob('*.json'):
        row=read_json(p)
        if row['status']!='completed':continue
        for review in row['reviews']:
            source=ROOT/review['path']
            for obs in read_json(source)['observations']:
                item=obs['input'].get('pixels');path=ROOT/item['path'] if item else None
                if path is None or not path.exists() or item['path'] not in mapping:continue
                assert path.parent==(OUT/'pixels') and path.name.endswith('_tp.fits.gz')
                record,archive=mapping[item['path']];assert sha256(path)==record['sha256']==item['sha256']
                # Do not release Git-tracked data or light curves.
                tracked=subprocess.check_output(['git','ls-files','--',item['path']],cwd=ROOT,text=True)
                assert not tracked
                ledger=DEST/'pixel-release'/(path.name+'.json')
                if ledger.exists():continue  # A deliberately restored cache remains present.
                note={'at':now(),'tic':row['tic'],'input':record,'archive_manifest':str(archive.relative_to(ROOT)),'source_result_sha256':sha256(p),'source_review_sha256':sha256(source),'remote_sha256_verified':True,'released':False}
                write_json(ledger,note);size=path.stat().st_size;path.unlink();note.update(released=True,released_at=now());write_json(ledger,note);count+=1;released+=size
    print('Released archived completed pixel caches',count,released,'bytes',flush=True)


def release_nondetection_inputs():
    """Release only verified public copies of completed, non-detection inputs."""
    identity()
    release=json.loads(gh('api',f'repos/{REPO}/releases/tags/{TAG}'))
    assets={a['name']:a for a in release['assets']}
    mapping={}
    for manifest in DEST.glob('shard-*.json'):
        shard=read_json(manifest)
        if shard.get('status')!='published':continue
        if shard.get('parts'):
            for part in shard['parts']:
                asset=assets[part['asset']['name']]
                assert asset['size']==part['bytes'] and asset['digest']=='sha256:'+part['sha256']
        else:
            asset=assets[shard['archive']]
            assert asset['size']==shard['archive_bytes'] and asset['digest']=='sha256:'+shard['archive_sha256']
        for item in shard['files']:mapping[item['path']]=(item,manifest)
    count=size=0
    for prediction in sorted((OUT/'results').glob('*.json')):
        row=read_json(prediction)
        if row['status']!='completed' or row.get('periodic_detected'):continue
        for item in row['inputs']:
            path=ROOT/item['path']
            if not path.exists() or item['path'] not in mapping:continue
            record,manifest=mapping[item['path']]
            assert path.parent==OUT/'inputs' and path.name.endswith('_lc.fits.gz')
            assert not subprocess.check_output(['git','ls-files','--',item['path']],cwd=ROOT,text=True)
            assert receipt(path)['sha256']==record['sha256']==item['sha256']
            ledger=DEST/'input-release'/(path.name+'.json')
            if ledger.exists():continue
            note={'at':now(),'tic':row['tic'],'input':record,'archive_manifest':str(manifest.relative_to(ROOT)),
                  'prediction_sha256':sha256(prediction),'remote_sha256_verified':True,'released':False,
                  'reason':'Completed non-detection; restore original bytes from verified public archive before reanalysis. Retain every detection locally.'}
            write_json(ledger,note);size+=path.stat().st_size;path.unlink();note.update(released=True,released_at=now());write_json(ledger,note);count+=1
    print('Released archived completed non-detection inputs',count,size,'bytes',flush=True)


def upload_evidence():
    """Preserve bulk original diagnostic PNGs and full external catalogues."""
    setup()
    saved=list(DEST.glob('evidence-*.json'))
    recorded={r['path'] for p in saved for r in read_json(p)['files']}
    for p in sorted(saved):
        r=read_json(p)
        if r.get('status')!='published':publish(p,r)
    files=list((OUT/'evaluation').rglob('*.png'))+list((OUT/'late-catalogs').rglob('*.zip'))
    groups=[];group=[];size=0
    for p in sorted(files):
        if str(p.relative_to(ROOT)) in recorded:continue
        if group and size+p.stat().st_size>350_000_000:groups.append(group);group=[];size=0
        group.append(p);size+=p.stat().st_size
    if group:groups.append(group)
    for group in groups:
        assert shutil.disk_usage(STAGE).free>3_000_000_000
        n=len(list(DEST.glob('evidence-*.json')))+1;name=f'diagnostic-evidence-{n:03}.tar';path=STAGE/name
        records=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha256(p)} for p in group]
        with tarfile.open(path,'w') as tar:
            for p in group:tar.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
        r={'at':now(),'status':'prepared','archive':name,'archive_bytes':path.stat().st_size,'archive_sha256':sha256(path),'files':records,
           'purpose':'Original per-target diagnostic PNGs and checksum-verified full public reference catalogues; restore at repository root. JSON science results and 43 extended-target plots remain in Git.'}
        manifest=DEST/f'evidence-{n:03}.json';write_json(manifest,r);publish(manifest,r)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['upload','upload-evidence','release-pixels','release-nondetection-inputs']);p.add_argument('--max-shards',type=int,default=0);a=p.parse_args()
    if a.action=='upload':upload(a.max_shards)
    elif a.action=='upload-evidence':upload_evidence()
    elif a.action=='release-pixels':release_pixels()
    else:release_nondetection_inputs()
