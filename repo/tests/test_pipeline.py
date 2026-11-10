import sqlite3
import pytest
from vstar.io import read_json, write_json
from vstar.pipeline import create_run, execute_run
from vstar.reports import page


def test_offline_run_resume_and_corrupt_artifact_recovery(config, monkeypatch):
    root = create_run(config, offline=True, limit=2, run_id="offline-test")
    before = read_json(root / "summary.json")
    assert len(before["targets"]) == 2
    assert all(r["novelty"] == "incomplete" for r in before["targets"])
    assert (root / "report/index.html").is_file()
    import vstar.pipeline as pipeline
    original = pipeline.analyze
    calls = []
    def count(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(pipeline, "analyze", count)
    execute_run(root)
    assert not calls
    artifact = next((root / "results").rglob("*.json"))
    artifact.write_text("corrupt")
    execute_run(root)
    assert len(calls) == 1
    with sqlite3.connect(root / "state.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM tasks WHERE state != 'success'").fetchone()[0] == 0


def test_failure_is_saved_and_retryable(config, monkeypatch):
    import vstar.pipeline as pipeline
    original = pipeline.analyze
    def fail(*args, **kwargs):
        raise ValueError("bad FITS")
    monkeypatch.setattr(pipeline, "analyze", fail)
    root = create_run(config, offline=True, limit=1)
    assert read_json(root / "summary.json")["targets"][0]["status"] == "failed"
    monkeypatch.setattr(pipeline, "analyze", original)
    execute_run(root)
    assert not read_json(root / "summary.json")["targets"][0]["errors"]


def test_frozen_inputs_cannot_be_silently_changed(config):
    root = create_run(config, offline=True, limit=1)
    write_json(root / "targets.json", [])
    with pytest.raises(ValueError, match="Frozen"):
        execute_run(root)


def test_html_title_is_escaped():
    assert "<title>&lt;script&gt;" in page("<script>", "safe")
