"""Scientific-label boundaries and safe resumable downloads for the larger test."""
from pathlib import Path
import sys, io, gzip, hashlib
import numpy as np
import pytest
from astropy.io import fits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from scale_validation_support import period_relation, zero_error_upper, fetch_product

URI='mast:TESS/product/tess2018206045859-s0001-0000000000000123-0120-s_lc.fits'

def content(tic=123):
    primary=fits.PrimaryHDU();primary.header['TICID']=tic;primary.header['SECTOR']=1
    tab=fits.BinTableHDU.from_columns([fits.Column(name='TIME',format='D',array=np.arange(3.))])
    f=io.BytesIO();fits.HDUList([primary,tab]).writeto(f);return f.getvalue()

class Response:
    def __init__(self,data,length=None):self.data=data;self.headers={'Content-Length':str(len(data) if length is None else length)}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def raise_for_status(self):pass
    def iter_content(self,*args):yield self.data

def test_period_alias_not_silently_scored_as_correct():
    assert period_relation(1,2)=='half_catalog_period'
    assert period_relation(4,2)=='double_catalog_period'
    assert period_relation(2.01,2)=='catalog_period_match'
    assert period_relation(1.4,2)=='other_period'
    assert period_relation(None,2)=='abstained'
    assert period_relation(2,None)=='no_reference'
    assert zero_error_upper(0) is None
    assert .009<zero_error_upper(300)<.011

def test_download_preserves_original_and_reuses_verified_cache(tmp_path,monkeypatch):
    data=content();monkeypatch.setattr('scale_validation_support.requests.get',lambda *a,**k:Response(data))
    p,record=fetch_product(URI,'123',1,tmp_path)
    assert gzip.decompress(p.read_bytes())==data
    assert record['raw_sha256']==hashlib.sha256(data).hexdigest()
    monkeypatch.setattr('scale_validation_support.requests.get',lambda *a,**k:pytest.fail('cache should avoid HTTP'))
    assert fetch_product(URI,'123',1,tmp_path)[0]==p
    p.write_bytes(b'broken')
    with pytest.raises(ValueError,match='Corrupt cache'):fetch_product(URI,'123',1,tmp_path)

def test_wrong_identity_and_truncation_cannot_create_receipts(tmp_path,monkeypatch):
    monkeypatch.setattr('scale_validation_support.time.sleep',lambda *a:None)
    monkeypatch.setattr('scale_validation_support.requests.get',lambda *a,**k:Response(content(tic=999)))
    with pytest.raises(ValueError,match='target/sector'):fetch_product(URI,'123',1,tmp_path)
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr('scale_validation_support.requests.get',lambda *a,**k:Response(content(),length=999999))
    with pytest.raises(ValueError,match='Truncated'):fetch_product(URI,'123',1,tmp_path)
    assert not list(tmp_path.iterdir())
