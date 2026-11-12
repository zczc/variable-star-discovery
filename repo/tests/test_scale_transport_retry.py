from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from retry_scale_source_transport import archive_failure
from vstar.io import write_json, read_json, sha256


def test_transport_retry_retains_original_and_does_not_rewrite_finished_output(tmp_path):
    current, archive = tmp_path / 'current.json', tmp_path / 'archive/original.json'
    write_json(current, {'status': 'transport_failed', 'reason': 'network'})
    original = sha256(current)
    assert archive_failure(current, archive, original) is None
    assert not current.exists() and sha256(archive) == original
    write_json(current, {'status': 'completed', 'source': 'unchanged'})
    assert archive_failure(current, archive, original) == read_json(current)
    assert sha256(archive) == original


def test_transport_retry_refuses_science_result_or_changed_failure(tmp_path):
    current, archive = tmp_path / 'current.json', tmp_path / 'archive.json'
    for state in ['completed', 'incomplete', 'not_requested']:
        write_json(current, {'status': state})
        with pytest.raises(AssertionError):
            archive_failure(current, archive, sha256(current))
        assert current.exists() and not archive.exists()
    write_json(current, {'status': 'transport_failed'})
    with pytest.raises(AssertionError):
        archive_failure(current, archive, 'invalid checksum')
    assert current.exists() and not archive.exists()
