"""Direct public TESS S3 transport; unchanged products with version and hash checks."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urlparse
import gzip,hashlib,json,os,re,shutil,time,fcntl
import requests
from vstar.io import read_json,write_json,sha256,now
from scale_validation_support import checked_product,MIN_FREE

CHUNK=2*1024*1024

def direct_url(uri):
    name=uri.rsplit('/',1)[-1]
    match=re.fullmatch(r'tess\d+-s(\d{4})-(\d{16})-\d+-s_(lc|tp)\.fits',name)
    if not match or uri!='mast:TESS/product/'+name:raise ValueError('Unsupported TESS product URI')
    sector,tic=match.group(1),match.group(2)
    return 'https://stpubdata.s3.us-east-1.amazonaws.com/tess/public/tid/s'+sector+'/'+('/'.join(tic[i:i+4] for i in range(0,16,4)))+'/'+name

def fetch_range(url,start,end,total,etag,part):
    expected=f'bytes {start}-{end}/{total}'
    checksum=part.with_suffix('.sha256')
    if part.exists():
        if not checksum.exists() or part.stat().st_size!=end-start+1 or sha256(part)!=checksum.read_text().strip():raise ValueError('Corrupt range cache')
        return
    for attempt in range(3):
        try:
            with requests.get(url,headers={'Range':f'bytes={start}-{end}','If-Match':etag,'Accept-Encoding':'identity'},timeout=(12,45),stream=True) as r:
                r.raise_for_status()
                if r.status_code!=206 or r.headers.get('Content-Range')!=expected or r.headers.get('ETag')!=etag:raise ValueError('Range or version mismatch')
                chunks=[];size=0
                for block in r.iter_content(1024*1024):
                    size+=len(block)
                    if size>end-start+1:raise ValueError('Oversized byte range')
                    chunks.append(block)
                data=b''.join(chunks)
                if size!=end-start+1:raise ValueError('Incomplete byte range')
            temp=part.with_suffix('.part');temp.write_bytes(data);os.replace(temp,part);checksum.write_text(hashlib.sha256(data).hexdigest()+'\n');return
        except (requests.RequestException,ValueError):
            if attempt==2:raise
            time.sleep(2**attempt)

def _fetch_ranged(uri,tic,sector,cache):
    name=uri.rsplit('/',1)[-1]
    if not uri.startswith('mast:TESS/product/') or not re.fullmatch(r'tess\d+-s\d+-\d+-\d+-s_(lc|tp)\.fits',name):raise ValueError('Unsupported URI')
    cache.mkdir(parents=True,exist_ok=True);path=cache/(name+'.gz');receipt=cache/(name+'.receipt.json')
    if path.exists():
        r=read_json(receipt)
        if r['uri']!=uri or sha256(path)!=r['sha256']:raise ValueError('Corrupt completed cache')
        checked_product(path,tic,sector);return path,r
    url=direct_url(uri)
    previous=cache/(name+'.ranges')/'version.json'
    if previous.exists():
        prior=read_json(previous)
        if prior['uri']!=uri or urlparse(prior['url']).path!=urlparse(url).path or urlparse(prior['url']).hostname not in {'stpubdata.s3.us-east-1.amazonaws.com','stpubdata.s3.amazonaws.com'}:raise ValueError('Unrecognized cached product endpoint')
        url=prior['url']
    for attempt in range(3):
        try:
            with requests.head(url,allow_redirects=False,timeout=(20,60)) as h:
                h.raise_for_status()
                if h.status_code!=200:raise ValueError('Unexpected direct archive response')
                total=int(h.headers['Content-Length']);etag=h.headers.get('ETag');encryption=h.headers.get('x-amz-server-side-encryption')
            break
        except (requests.RequestException,ValueError,KeyError):
            if attempt==2:raise
            time.sleep(2**attempt)
    host=urlparse(url).hostname
    if host not in {'stpubdata.s3.us-east-1.amazonaws.com','stpubdata.s3.amazonaws.com'} or not urlparse(url).path.endswith('/'+name) or not etag:raise ValueError('Unrecognized public product endpoint or missing version')
    limit=400_000_000 if name.endswith('_tp.fits') else 16_000_000
    if total>limit or shutil.disk_usage(cache).free<MIN_FREE+max(24*total,2_000_000_000):raise OSError('File/disk resource limit')
    directory=cache/(name+'.ranges');directory.mkdir(exist_ok=True)
    version={'uri':uri,'url':url,'bytes':total,'etag':etag,'chunk_bytes':CHUNK}
    manifest=directory/'version.json'
    if manifest.exists() and read_json(manifest)!=version:raise ValueError('Remote version changed during resume')
    if not manifest.exists():write_json(manifest,version)
    pieces=[(start,min(start+CHUNK,total)-1,directory/f'{start:012d}.bin') for start in range(0,total,CHUNK)]
    began=time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(fetch_range,url,start,end,total,etag,p) for start,end,p in pieces]):f.result()
    temporary=cache/(name+'.assembled');packed=cache/(name+'.packed')
    try:
        with temporary.open('wb') as dest:
            for start,end,p in pieces:
                if p.stat().st_size!=end-start+1:raise ValueError('Part length changed')
                with p.open('rb') as source:shutil.copyfileobj(source,dest)
            dest.flush();os.fsync(dest.fileno())
        checked_product(temporary,tic,sector);raw_hash=sha256(temporary)
        remote_md5_verified=False
        if re.fullmatch(r'"[0-9a-fA-F]{32}"',etag) and encryption in {None,'AES256'}:
            with temporary.open('rb') as stream:
                if hashlib.file_digest(stream,'md5').hexdigest()!=etag.strip('"').lower():raise ValueError('Remote complete-file checksum mismatch')
            remote_md5_verified=True
        with temporary.open('rb') as src,packed.open('wb') as dest,gzip.GzipFile(filename='',mode='wb',fileobj=dest,mtime=0,compresslevel=1) as gz:shutil.copyfileobj(src,gz)
        record={'uri':uri,'download_url':url,'downloaded_at':now(),'raw_sha256':raw_hash,'raw_bytes':total,'sha256':sha256(packed),'compressed_bytes':packed.stat().st_size,'compression':'gzip level 1, mtime 0; original bytes unchanged','transport':'version-pinned direct public TESS S3 HTTP ranges','remote_md5_verified':remote_md5_verified,'etag':etag,'range_bytes':CHUNK,'elapsed_seconds':time.monotonic()-began}
        os.replace(packed,path);write_json(receipt,record)
        for _,_,p in pieces:
            p.unlink();p.with_suffix('.sha256').unlink(missing_ok=True)
        manifest.unlink();directory.rmdir()
        return path,record
    finally:temporary.unlink(missing_ok=True);packed.unlink(missing_ok=True)

def fetch_ranged(uri,tic,sector,cache):
    name=uri.rsplit('/',1)[-1]
    if not re.fullmatch(r'tess\d+-s\d+-\d+-\d+-s_(lc|tp)\.fits',name):raise ValueError('Unsupported product name')
    cache.mkdir(parents=True,exist_ok=True)
    with (cache/(name+'.range.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:return _fetch_ranged(uri,tic,sector,cache)
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--uri',required=True);p.add_argument('--tic',required=True);p.add_argument('--sector',type=int,required=True);p.add_argument('--cache',type=Path,required=True);a=p.parse_args()
    path,r=fetch_ranged(a.uri,a.tic,a.sector,a.cache);print(json.dumps(r,indent=2))
