from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from scale_range_transport import fetch_range

class Response:
    def __init__(self,status=206,etag='"version"',content_range='bytes 0-3/8',data=b'abcd'):
        self.status_code=status;self.headers={'ETag':etag,'Content-Range':content_range};self.data=data
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def raise_for_status(self):pass
    def iter_content(self,*a):yield self.data

def test_ranges_require_exact_version_and_offsets(tmp_path,monkeypatch):
    monkeypatch.setattr('scale_range_transport.time.sleep',lambda *a:None)
    for response in [Response(status=200),Response(etag='"changed"'),Response(content_range='bytes 4-7/8'),Response(data=b'ab')]:
        monkeypatch.setattr('scale_range_transport.requests.get',lambda *a,**k:response)
        with pytest.raises(ValueError):fetch_range('https://example.invalid',0,3,8,'"version"',tmp_path/'0.bin')
        assert not (tmp_path/'0.bin').exists()

def test_resume_verifies_saved_chunk_hash(tmp_path,monkeypatch):
    monkeypatch.setattr('scale_range_transport.requests.get',lambda *a,**k:Response())
    p=tmp_path/'0.bin';fetch_range('https://example.invalid',0,3,8,'"version"',p)
    monkeypatch.setattr('scale_range_transport.requests.get',lambda *a,**k:pytest.fail('saved chunk should be reused'))
    fetch_range('https://example.invalid',0,3,8,'"version"',p)
    p.write_bytes(b'bad!')
    with pytest.raises(ValueError,match='Corrupt'):fetch_range('https://example.invalid',0,3,8,'"version"',p)

def test_product_lock_serializes_overlapping_prefetch(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading,time
    import scale_range_transport as module
    active=0;peak=0;guard=threading.Lock()
    def fake(*args):
        nonlocal active,peak
        with guard:active+=1;peak=max(peak,active)
        time.sleep(.03)
        with guard:active-=1
        return ('cached',{})
    monkeypatch.setattr(module,'_fetch_ranged',fake)
    uri='mast:TESS/product/tess2019198215352-s0014-0000000164674992-0150-s_tp.fits'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(module.fetch_ranged,uri,'164674992',14,tmp_path) for _ in range(2)]
        assert all(f.result()[0]=='cached' for f in futures)
    assert peak==1
