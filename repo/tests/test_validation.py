from pathlib import Path
import numpy as np
import pytest
from vstar.io import read_json
from vstar.localization import localize
from vstar.models import AnalysisConfig, empty_submission
from vstar.periods import bls_search
from vstar.photometry import LightCurve
from vstar.submission import validate_submission

DATA = Path(__file__).resolve().parents[1] / "experiments/2026-11-09-pilot"


@pytest.mark.parametrize("tic,status", [("259238257", "likely_contaminated"), ("458747716", "consistent_with_target")])
def test_pixel_source_cases(tic, status, tmp_path):
    row = read_json(DATA / f"scan-{tic}.json")
    target = {"ra_deg": row["s_ra"], "dec_deg": row["s_dec"], "vsx_neighbors": row["vsx_neighbors"]}
    lc = DATA / row["file"]
    result = localize(lc.with_name(lc.name.replace("_lc.fits", "_tp.fits")), lc, target, row["period_d"], tmp_path / "pixels.png")
    assert result["status"] == status
    if status == "likely_contaminated":
        assert result["possible_contaminant"]["name"] == "GSC 04448-01982"


def test_injected_box_signal():
    rng = np.random.default_rng(832)
    t = np.linspace(0, 27, 3500)
    phase = (t % 1.7) / 1.7
    y = rng.normal(0, .001, len(t)) - .015 * (phase < .025)
    result = bls_search(LightCurve(t, y, np.full(len(t), .001), {}), AnalysisConfig())
    assert result["period_d"] == pytest.approx(1.7, rel=.01)


def test_vsx_missing_fields_and_relabelled_times_block_submission():
    target = {"status": "periodic_candidate", "notes": [{"kind": "prior_lead"}]}
    fields = empty_submission()
    fields.update(period_days=2.3, epoch=2459000, epoch_time_standard="BJD", max_magnitude=float('nan'))
    report = validate_submission(target, fields, {}, {})
    assert report["status"] == "draft" and not report["officially_accepted"]
    assert any("HJD" in x for x in report["missing"])
    assert any("prior-work" in x for x in report["missing"])
    assert any("magnitudes" in x for x in report["missing"])


def test_internal_ready_status_still_is_not_official_acceptance():
    fields = dict(name="test", coordinate_source="test", coordinate_epoch="2000", variability_type="EA", discoverers=["Researcher"],
                  references=["test"], ra_deg=30, dec_deg=-20, period_days=2, period_error_days=.0001, epoch=2459000,
                  epoch_time_standard="HJD", epoch_event="primary minimum", max_magnitude=10, min_magnitude=10.1,
                  passband="V", magnitude_source="test")
    reviews = {k: {"status": "reviewed", "reference": "test", "notes": "Test fixture only"} for k in
               ["identity", "variability", "source_localization", "novelty", "period_epoch", "photometry", "classification"]}
    result = validate_submission({}, fields, reviews, {"phase": {}, "finding_chart": {}})
    assert result["status"] == "ready_for_manual_submission" and not result["officially_accepted"]
