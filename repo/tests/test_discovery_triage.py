from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
import triage_discovery_candidates as triage


def test_catalogue_error_payloads_are_not_empty_results():
    for payload in ({}, {'VSXObjects': None}, {'VSXObjects': {'Error': 'query failed'}}):
        with pytest.raises(ValueError):
            triage.vsx_objects(payload)
    assert triage.vsx_objects({'VSXObjects': []}) == []


def test_single_catalogue_object_is_retained():
    star = {'Name': 'Known variable', 'Category': 'Suspected', 'RA2000': '10', 'Declination2000': '20'}
    assert triage.vsx_objects({'VSXObjects': {'VSXObject': star}}) == [star]


def test_http_success_with_catalogue_error_stays_failed(tmp_path, monkeypatch):
    class Response:
        url = 'https://vsx.aavso.org/index.php'
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {'VSXObjects': {'Error': 'backend unavailable'}}

    monkeypatch.setattr(triage, 'OUT', tmp_path)
    monkeypatch.setattr(triage.requests, 'get', lambda *args, **kwargs: Response())
    monkeypatch.setattr(triage.time, 'sleep', lambda _: None)
    result = triage.query_vsx({'id': 'tic-1', 'tic': '1', 'target': {'ra_deg': 10, 'dec_deg': 20}})
    assert result['status'] == 'failed'
    assert 'objects' not in result
    assert len(result['attempts']) == 2
