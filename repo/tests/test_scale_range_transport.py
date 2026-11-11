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
