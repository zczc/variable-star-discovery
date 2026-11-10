from pathlib import Path
import json
import numpy as np
import pytest
from vstar.models import AnalysisConfig
from vstar.photometry import LightCurve
from vstar.periods import period_search, analyze
from vstar.pipeline import assess

DATA = Path(__file__).resolve().parents[1] / "experiments/2026-11-09-pilot"
ROWS = [r for r in json.loads((DATA / "scan-results.json").read_text()) if r.get("file")]


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["target_name"])
def test_historical_periods(row):
    result, _ = analyze(DATA / row["file"], AnalysisConfig())
    for key in ["period_d", "power", "first_period", "second_period", "phase_amplitude_pct"]:
        assert result[key] == pytest.approx(row[key], rel=1e-8)
    assert result["epoch"] is None
    assert result["metadata"]["TIMESYS"] == "TDB"


@pytest.mark.parametrize("period", [.173, 1.73, 4.2])
def test_injected_sinusoid_with_gaps(period):
    rng = np.random.default_rng(739)
    t = np.sort(rng.uniform(0, 27, 3500))
    t = t[(t < 12) | (t > 14)]
    y = .01 * np.sin(2 * np.pi * t / period) + rng.normal(0, .003, len(t))
    recovered, *_ = period_search(LightCurve(t, y, np.full(len(t), .003), {}), AnalysisConfig())
    assert recovered == pytest.approx(period, rel=.01)


def test_constant_and_invalid_series_are_rejected():
    with pytest.raises(ValueError, match="constant"):
        period_search(LightCurve(np.arange(30), np.ones(30), np.ones(30), {}), AnalysisConfig())
    with pytest.raises(ValueError):
        AnalysisConfig(min_period_days=10)


def test_multiple_epochs_not_inferred_from_single_period():
    assert assess([{"period_d": 2.3}], .05)["status"] == "insufficient_epochs"
    assert assess([{"period_d": 2.23}, {"period_d": 2.29}], .05)["status"] == "approximately_repeated"
    assert assess([{"period_d": 7.37}, {"period_d": 2.59}], .05)["status"] == "inconsistent"
