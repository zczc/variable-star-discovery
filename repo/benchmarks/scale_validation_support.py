"""Batch transport and scoring helpers; no changes to scientific v4 rules."""
from pathlib import Path
import gzip, hashlib, math, os, re, shutil, time
import requests
from astropy.io import fits
from vstar.io import sha256, read_json, write_json, now

MIN_FREE=6_000_000_000

def period_relation(selected, reference, tolerance=.01):
    if selected is None:return 'abstained'
    if reference is None:return 'no_reference'
    for ratio,label in [(1.,'catalog_period_match'),(.5,'half_catalog_period'),(2.,'double_catalog_period')]:
        if abs(selected/(reference*ratio)-1)<=tolerance:return label
    return 'other_period'

def zero_error_upper(n,alpha=.05):
    return None if n<=0 else 1-alpha**(1/n)

def checked_product(path,tic,sector):
    with fits.open(path,memmap=False) as hdul:
        hdul.verify('exception')
        if len(hdul)<2 or hdul[1].data is None or len(hdul[1].data)==0:raise ValueError('Empty FITS')
        meta=dict(hdul[0].header)|dict(hdul[1].header)
        if str(meta.get('TICID'))!=str(tic) or int(meta.get('SECTOR',-1))!=int(sector):raise ValueError('FITS target/sector mismatch')
        _=hdul[1].data[-1]

def fetch_product(uri,tic,sector,cache):
    """Keep compressed original bytes, transport hash and gzip hash, with disk guards.

    Distinct URI paths must be assigned to only one worker. A failed attempt never
    produces a receipt. No external filenames or commands are executed.
    """
    name=uri.rsplit('/',1)[-1]
    if not re.fullmatch(r'tess\d+-s\d+-\d+-\d+-s_(lc|tp)\.fits',name) or not uri.startswith('mast:TESS/product/'):
        raise ValueError('Unsupported product URI')
    cache.mkdir(parents=True,exist_ok=True)
    path=cache/(name+'.gz');receipt=cache/(name+'.receipt.json')
    if path.exists() and receipt.exists():
        record=read_json(receipt)
        if record['uri']!=uri or record['sha256']!=sha256(path):raise ValueError('Corrupt cache; refusing silent replacement')
        checked_product(path,tic,sector)
        return path,record
    if path.exists():raise ValueError('Unreceipted cache requires audit')
    temporary=cache/(name+'.part');packed=cache/(name+'.gz.part')
    limit=400_000_000 if name.endswith('_tp.fits') else 16_000_000
    url='https://mast.stsci.edu/api/v0.1/Download/file'
    errors=[]
    for attempt in range(3):
        try:
            if shutil.disk_usage(cache).free<MIN_FREE+limit*2:raise OSError('Disk guard: preserve 6 GB free')
            with requests.get(url,params={'uri':uri},stream=True,timeout=(12,50),headers={'User-Agent':'variable-star-discovery/0.1 public-research'}) as response:
                response.raise_for_status();total=0;digest=hashlib.sha256()
                with temporary.open('wb') as f:
                    for chunk in response.iter_content(1024*1024):
                        total+=len(chunk)
                        if total>limit or shutil.disk_usage(cache).free<MIN_FREE:raise OSError('Product/disk size guard exceeded')
                        digest.update(chunk);f.write(chunk)
                    f.flush();os.fsync(f.fileno())
                expected=response.headers.get('Content-Length')
                if expected and not response.headers.get('Content-Encoding') and total!=int(expected):raise ValueError('Truncated HTTP download')
            checked_product(temporary,tic,sector)
            with temporary.open('rb') as src,packed.open('wb') as dest,gzip.GzipFile(filename='',mode='wb',fileobj=dest,mtime=0,compresslevel=1) as gz:
                shutil.copyfileobj(src,gz)
            os.replace(packed,path)
            record={'uri':uri,'download_url':url+'?uri='+uri,'downloaded_at':now(),'raw_sha256':digest.hexdigest(),'raw_bytes':total,'sha256':sha256(path),'compressed_bytes':path.stat().st_size,'compression':'gzip level 1, mtime 0; decompresses to original FITS bytes','attempt_errors':errors}
            write_json(receipt,record);return path,record
        except (requests.RequestException,ValueError,OSError) as exc:
            errors.append(str(exc))
            if attempt==2 or isinstance(exc,OSError) and not isinstance(exc,requests.RequestException):raise
            time.sleep(min(2**attempt,4))
        finally:
            temporary.unlink(missing_ok=True);packed.unlink(missing_ok=True)
    raise RuntimeError(errors)
