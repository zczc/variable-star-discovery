"""Integrity checks for v3 development artifacts; no accuracy certification."""
from copy import deepcopy
from pathlib import Path
import subprocess
import re
from urllib.parse import urlsplit,unquote
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from audit_v2 import Links
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks'

def main():
    record={'checked_at':now(),'runs':[],'broken_links':[]}
    protocol=BENCH/'v3-protocol-v01.json';p=read_json(protocol)
    for item in p['code_files']:
        assert sha256(ROOT/item['path'])==item['sha256'],item['path']
    record['frozen_code_files_verified']=p['code_files']
    for run in [BENCH/'mixed-v04',BENCH/'former-pilot-v3']:
        pred=read_json(run/'predictions.json');res=read_json(run/'results.json')
        assert pred['complete'] and res['protocol_sha256']==sha256(protocol)
        assert res['code_fingerprint']==code_fingerprint()
        assert res['prediction_sha256']==sha256(run/'predictions.json')
        copy=deepcopy(res);del copy['metrics'],copy['prediction_sha256']
        for row in copy['results']:del row['reference'],row['score']
        assert pred==copy
        count=0
        for row in res['results']:
            assert row==read_json(run/row['id']/'case.json')
            assert not row.get('conclusion',{}).get('confirmed_variable',False)
            for obs in row['observations']:
                assert sha256(ROOT/obs['input']['path'])==obs['input']['sha256']
                assert sha256(run/row['id']/obs['plot'])==obs['plot_sha256']
                assert obs['v2']['algorithm_revision']=='v3.0-development'
                count+=1
            for evidence in row.get('conclusion',{}).get('source_evidence',[]):
                assert sha256(ROOT/evidence['input']['path'])==evidence['input']['sha256']
        for item in res['sources']:assert sha256(ROOT/item['path'])==item['sha256']
        for f in run.rglob('*.html'):
            parser=Links();parser.feed(f.read_text())
            for link in parser.links:
                u=urlsplit(link)
                if not u.scheme and not u.netloc and u.path and not (f.parent/unquote(u.path)).exists():
                    record['broken_links'].append([str(f.relative_to(ROOT)),link])
        prov=read_json(run/'report-provenance.json')
        assert prov['results_sha256']==sha256(run/'results.json')
        assert prov['renderer_sha256']==sha256(BENCH/'build_v3_report.py')
        record['runs'].append({'path':str(run.relative_to(ROOT)),'cases':len(res['results']),'observations':count,
                               'failed':sum(r['status']=='failed' for r in res['results']),
                               'unavailable':sum(r['status']=='unavailable' for r in res['results']),
                               'predictions_unchanged_by_reference_scoring':True})
    # Preserve all historical science and run artifacts. review.py added explicit backend dispatch.
    preserved=['repo/src/vstar/screening.py','repo/src/vstar/auxiliary.py','repo/benchmarks/evaluate_v2.py',
               'repo/benchmarks/mixed-v01','repo/benchmarks/mixed-v02','repo/benchmarks/mixed-v03',
               'repo/benchmarks/independent-pilot-v01','repo/benchmarks/known-v01','repo/runs/sector94-100-v02',
               'repo/benchmarks/v2-integrity-audit.json']
    assert not subprocess.check_output(['git','diff','--name-only','edbcca5','--',*preserved],cwd=ROOT,text=True)
    record['preserved_since_edbcca5']=preserved
    for f in [ROOT/'doc/14-v3-and-submission-readiness.md', ROOT/'doc/06-vsx-and-credit.md']:
        for link in re.findall(r'\]\(([^)]+)\)',f.read_text()):
            u=urlsplit(link)
            if not u.scheme and u.path and not (f.parent/unquote(u.path)).exists():record['broken_links'].append([str(f),link])
    assert not record['broken_links'],record['broken_links']
    src=ROOT/'doc/sources/vsx-guidelines-2026-11-11'
    assert sha256(src/'notice.html')==read_json(src/'receipt.json')['sha256']
    record['official_guidelines_snapshot_verified']=True
    smoke=read_json(ROOT/'repo/data/v3-cli-smoke/case.json')
    assert not smoke['errors'] and smoke['conclusion']['periodic_detected'] and not smoke['conclusion']['confirmed_variable']
    assert smoke['conclusion']['algorithm_revision']=='v3.0-development'
    record['cli_smoke']='passed'
    record['note']='42 development cases, not 42 independent stars; no new untouched evaluation or real quiet-control accuracy claim.'
    write_json(BENCH/'v3-integrity-audit.json',record)
    print(record)

if __name__=='__main__':main()
