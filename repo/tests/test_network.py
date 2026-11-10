import json
import pytest
from vstar.network import ArchiveClient
from vstar.io import read_json


class Response:
    headers = {}
    status_code = 200
    def close(self):
        pass
    def iter_content(self, size):
        yield b'HTML error page pretending to be a FITS file'


def test_invalid_download_is_never_accepted(tmp_path, monkeypatch):
    client = ArchiveClient(tmp_path)
    monkeypatch.setattr(client, "request", lambda *a, **k: Response())
    with pytest.raises(OSError):
        client.download("mast:TESS/product/bad_lc.fits")
    assert not list(tmp_path.rglob("*.fits"))
    assert not list(tmp_path.rglob("*.part"))


def test_incomplete_pagination_is_not_a_complete_catalog(tmp_path, monkeypatch):
    client = ArchiveClient(tmp_path)
    monkeypatch.setattr(client, "query", lambda *a, **k: ({"data": [{}], "paging": {"pagesFiltered": 3}}, {}))
    with pytest.raises(ValueError, match="partial catalog"):
        client.mast_rows([], max_pages=2)


def test_vsx_failure_and_empty_results_are_distinct(tmp_path, monkeypatch):
    client = ArchiveClient(tmp_path, offline=True)
    objects, receipt = client.vsx(10, 20)
    assert objects == [] and receipt["status"] == "failed"
    monkeypatch.setattr(client, "query", lambda *a, **k: ({"VSXObjects": []}, {"source": "VSX"}))
    objects, receipt = client.vsx(10, 20)
    assert objects == [] and receipt["status"] == "completed" and receipt["match_count"] == 0


def test_offline_mode_never_attempts_http(tmp_path, monkeypatch):
    client = ArchiveClient(tmp_path, offline=True)
    with pytest.raises(RuntimeError, match="offline"):
        client.request("GET", "https://mast.stsci.edu/")
