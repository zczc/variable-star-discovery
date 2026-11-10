from pathlib import Path
import pytest
from vstar.models import Config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config(tmp_path):
    return Config(workspace=ROOT, runs_dir=str(tmp_path / "runs"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not contact remote services")
    monkeypatch.setattr("requests.sessions.Session.send", forbidden)
