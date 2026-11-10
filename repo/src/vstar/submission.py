"""Local VSX draft export. This module never submits data to AAVSO."""
from pathlib import Path
import math
import shutil
from PIL import Image
from .io import read_json, write_json, now, sha256
from .models import empty_submission


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_submission(target, fields, review, attachments):
    missing = []
    for name in ["name", "coordinate_source", "coordinate_epoch", "variability_type", "epoch_time_standard", "epoch_event", "discoverers", "references"]:
        if not fields.get(name):
            missing.append(name)
    for name, lower, upper in [("ra_deg", 0, 360), ("dec_deg", -90, 90), ("period_days", 0, 100000), ("epoch", 2400000, 3000000)]:
        value = fields.get(name)
        if not finite(value) or not lower <= value <= upper or (name == "period_days" and value == 0):
            missing.append(name + ": missing or invalid")
    if not finite(fields.get("period_error_days")) or fields["period_error_days"] <= 0:
        missing.append("period uncertainty with a documented method (project requirement)")
    if fields.get("epoch_time_standard") != "HJD":
        missing.append("epoch must be checked against the VSX HJD requirement; no automatic BJD relabeling")
    maxmag, minmag = fields.get("max_magnitude"), fields.get("min_magnitude")
    calibrated = (finite(maxmag) and finite(minmag) and maxmag <= minmag and fields.get("passband") and fields.get("magnitude_source"))
    alternative = (finite(fields.get("mean_magnitude")) and finite(fields.get("amplitude_magnitude"))
                   and fields["amplitude_magnitude"] > 0 and fields.get("passband") and fields.get("amplitude_passband")
                   and fields.get("magnitude_source") and review.get("photometry", {}).get("alternative_basis"))
    if not (calibrated or alternative):
        missing.append("calibrated max/min magnitudes and passband, or documented guideline IV.c alternative")
    # Reviewed evidence is supplied by the researcher, never inferred from a high periodogram peak.
    for key in ["identity", "variability", "source_localization", "novelty", "period_epoch", "photometry", "classification"]:
        record = review.get(key, {})
        if record.get("status") != "reviewed" or not record.get("reference") or not record.get("notes"):
            missing.append("documented review: " + key)
    for name in ["phase", "finding_chart"]:
        if name not in attachments:
            missing.append("verified attachment: " + name)
    if target.get("errors"):
        missing.append("resolve failed analysis/check tasks")
    if target.get("status") == "likely_contaminated":
        missing.append("source contamination must be resolved in a new analysis")
    if target.get("notes") and not review.get("novelty", {}).get("prior_leads_resolved"):
        missing.append("resolve recorded prior-work leads")
    return {"schema_version": 1, "checked_at": now(), "status": "draft" if missing else "ready_for_manual_submission",
            "missing": missing, "officially_accepted": False,
            "notice": "Internal completeness and researcher-review check only. It cannot certify the scientific claims or guarantee AAVSO acceptance."}


def export_vsx(root: Path, tic: str, review_path: Path | None = None):
    root = root.resolve()
    target = next((r for r in read_json(root / "summary.json")["targets"] if r["tic"] == tic), None)
    if target is None:
        raise ValueError("Target not present in this run")
    supplied = read_json(review_path) if review_path else {}
    if supplied and str(supplied.get("tic")) != tic:
        raise ValueError("Review identity does not match the selected TIC")
    fields = empty_submission()
    fields.update(name="TIC " + tic, ra_deg=target["ra_deg"], dec_deg=target["dec_deg"])
    fields.update(supplied.get("fields", {}))
    reviews = supplied.get("reviews", {})
    # Each export is a separate snapshot; a later draft cannot leave obsolete approved attachments behind.
    import uuid
    out = root / "exports" / tic / uuid.uuid4().hex[:10]
    out.mkdir(parents=True, exist_ok=False)
    attachments = {}
    for kind, name in supplied.get("attachments", {}).items():
        if kind not in {"phase", "finding_chart", "lightcurve"} or not review_path:
            raise ValueError("Unsupported attachment role")
        path = (review_path.parent / name).resolve()
        if not path.is_relative_to(review_path.parent.resolve()) or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif"}:
            raise ValueError("Attachments must be image files inside the review directory")
        with Image.open(path) as img:
            img.verify()
        saved = out / (kind + path.suffix.lower())
        shutil.copyfile(path, saved)
        attachments[kind] = {"file": saved.name, "sha256": sha256(saved)}
    validation = validate_submission(target, fields, reviews, attachments)
    write_json(out / "validation.json", validation)
    write_json(out / "submission.json", {"tic": tic, "fields": fields, "reviews": reviews, "attachments": attachments})
    lines = ["# VSX submission draft", "", "Status: " + validation["status"], "",
             "This file is a worksheet for the VSX New Star Form, not an official import format or acceptance certificate.", ""]
    lines += [f"- {key}: {value if value is not None else 'MISSING'}" for key, value in fields.items()]
    lines += ["", "## Missing evidence", ""] + ["- " + item for item in validation["missing"]]
    lines += ["", "Screening plots in the analysis report use relative flux and arbitrary phase zero. They are not automatically submission-ready calibrated photometry.", ""]
    (out / "submission-fields.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "references.md").write_text("# References\n\nVSX guidelines: https://vsx.aavso.org/index.php?view=about.notice\n\nResearcher-supplied survey and literature references:\n\n" + str(fields.get("references") or "MISSING") + "\n", encoding="utf-8")
    return out, validation
