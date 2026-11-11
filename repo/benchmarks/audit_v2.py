"""Integrity, label-stage and presentation audits; not accuracy validation."""
import ast
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, unquote
from vstar.io import read_json, write_json, sha256

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT/"repo/benchmarks"


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(v for k, v in attrs if k in {"src", "href"} and v)


def main():
    record = {"runs": [], "broken_links": [], "scientific_functions_unchanged_since_freeze": []}
    for run in [BENCH/"mixed-v03", BENCH/"independent-pilot-v01/evaluation"]:
        prediction = read_json(run/"predictions.json")
        result = read_json(run/"results.json")
        assert sha256(run/"predictions.json") == result["prediction_sha256"]
        unscored = deepcopy(result)
        del unscored["metrics"], unscored["prediction_sha256"]
        for row in unscored["results"]:
            del row["reference"], row["score"]
        assert prediction == unscored
        count = 0
        for row in result["results"]:
            assert read_json(run/row["id"]/"case.json") == row
            for observation in row["observations"]:
                item = observation["input"]
                assert sha256(ROOT/item["path"]) == item["sha256"]
                assert sha256(run/row["id"]/observation["plot"]) == observation["plot_sha256"]
                count += 1
        for item in result["sources"]:
            assert sha256(ROOT/item["path"]) == item["sha256"]
        for file in run.rglob("*.html"):
            parser = Links(); parser.feed(file.read_text())
            for link in parser.links:
                url = urlsplit(link)
                if not url.scheme and not url.netloc and url.path and not (file.parent/unquote(url.path)).exists():
                    record["broken_links"].append([str(file.relative_to(ROOT)), link])
        prov = read_json(run/"report-provenance.json")
        assert prov["results_sha256"] == sha256(run/"results.json")
        assert prov["renderer_sha256"] == sha256(BENCH/"build_v2_report.py")
        record["runs"].append({"path": str(run.relative_to(ROOT)), "cases": len(result["results"]), "observations": count,
                                "predictions_unchanged_by_scoring": True, "errors": sum(bool(r["errors"]) for r in result["results"])})
    for path in ["repo/src/vstar/screening.py", "repo/src/vstar/auxiliary.py", "repo/benchmarks/evaluate_v2.py"]:
        old = subprocess.check_output(["git", "show", f"97efb49:{path}"], cwd=ROOT)
        assert old == (ROOT/path).read_bytes()
        record["scientific_functions_unchanged_since_freeze"].append(path)
    path = "repo/src/vstar/review.py"
    old = ast.parse(subprocess.check_output(["git", "show", f"97efb49:{path}"], cwd=ROOT, text=True))
    new = ast.parse((ROOT/path).read_text())
    for name in ["review_epoch", "review_files"]:
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(a) == ast.dump(b)
        record["scientific_functions_unchanged_since_freeze"].append(path+":"+name)
    changed = subprocess.check_output(["git", "diff", "--name-only", "7f7fc3f", "--", "repo/benchmarks/mixed-v01", "repo/benchmarks/known-v01", "repo/runs/sector94-100-v02"], cwd=ROOT, text=True)
    assert not changed
    record["old_v1_results_and_unknown_target_run_unchanged"] = True
    for file in [ROOT/"doc/13-v2-recognition-results.md", BENCH/"mixed-v03/README.md", BENCH/"independent-pilot-v01/README.md"]:
        for link in re.findall(r'\]\(([^)]+)\)', file.read_text()):
            url = urlsplit(link)
            if not url.scheme and not (file.parent/unquote(url.path)).exists():
                record["broken_links"].append([str(file.relative_to(ROOT)), link])
    assert not record["broken_links"], record["broken_links"]
    smoke = ROOT/"repo/data/v2-cli-smoke/case.json"
    if smoke.exists():
        c = read_json(smoke)
        assert not c["errors"] and c["conclusion"]["periodic_detected"] and not c["conclusion"]["confirmed_variable"]
        record["cli_same_target_two_epoch_smoke"] = "passed"
    record["note"] = "Software and evidence integrity checks; do not constitute population accuracy or false-positive validation."
    write_json(BENCH/"v2-integrity-audit.json", record)
    print(record)


if __name__ == "__main__":
    main()
