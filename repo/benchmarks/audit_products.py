"""Verify product/event development artifacts and unchanged historical results."""
from pathlib import Path
from copy import deepcopy
import subprocess,re
from urllib.parse import urlsplit,unquote
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from audit_v2 import Links
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks';RUN=BENCH/'products-v01'


def main():
    protocol=read_json(BENCH/'products-protocol-v01.json')
    for item in protocol['code_files']:assert sha256(ROOT/item['path'])==item['sha256'],item['path']
    pred=read_json(RUN/'predictions.json');result=read_json(RUN/'results.json')
    assert pred['complete'] and sha256(RUN/'predictions.json')==result['predictions_sha256']
    assert result['protocol_sha256']==sha256(BENCH/'products-protocol-v01.json')
    assert result['code_fingerprint']==code_fingerprint()
    stripped=deepcopy(result);del stripped['predictions_sha256']
    for row in stripped['results']:del row['score'],row['reference_period_d']
    assert stripped==pred
    count=0;period_scores={'SAP':0,'PDCSAP':0}
    for row in result['results']:
        if row['status']=='unavailable':continue
        case=deepcopy(row)
        for key in ['kind','score','reference_period_d']:del case[key]
        assert case==read_json(RUN/row['id']/'case.json')
        assert not row['comparison']['confirmed_variable'] and not row['comparison']['target_candidate']
        for obs in row['observations']:
            assert sha256(ROOT/obs['input']['path'])==obs['input']['sha256']
            assert sha256(RUN/row['id']/obs['plot'])==obs['plot_sha256']
            assert set(obs['products'])=={'SAP','PDCSAP'}
            count+=1
        if row['kind']=='real_new_positive_control':
            for name in period_scores:period_scores[name]+=row['score'][name]=='correct_period'
    for item in result['sources']:assert sha256(ROOT/item['path'])==item['sha256']
    ev=read_json(RUN/'event-review.json')
    assert ev['script_sha256']==sha256(BENCH/'review_eclipse_events.py')
    for obs in ev['observations']:
        assert sha256(ROOT/obs['input']['path'])==obs['input']['sha256']
        assert sha256(RUN/obs['plot'])==obs['plot_sha256']
        for m in obs['measurements']:
            s=m['summary'];assert s['measured_events']+s['missing_events']==len(m['events'])
            if s['adjacent_pairs']<3:assert s['bootstrap_interval_95'] is None
    prov=read_json(RUN/'report-provenance.json')
    assert prov['renderer_sha256']==sha256(BENCH/'build_products_report.py')
    assert prov['results_sha256']==sha256(RUN/'results.json') and prov['events_sha256']==sha256(RUN/'event-review.json')
    broken=[]
    for f in RUN.rglob('*.html'):
        parser=Links();parser.feed(f.read_text())
        for link in parser.links:
            u=urlsplit(link)
            if not u.scheme and not u.netloc and u.path and not (f.parent/unquote(u.path)).exists():broken.append([str(f),link])
    for f in [ROOT/'doc/15-products-and-real-controls.md',BENCH/'quiet-controls-research-v01/README.md']:
        for link in re.findall(r'\]\(([^)]+)\)',f.read_text()):
            u=urlsplit(link)
            if not u.scheme and u.path and not (f.parent/unquote(u.path)).exists():broken.append([str(f),link])
    assert not broken,broken
    preserved=['repo/src/vstar/screening.py','repo/src/vstar/screening_v3.py','repo/src/vstar/review.py',
        'repo/benchmarks/mixed-v01','repo/benchmarks/mixed-v02','repo/benchmarks/mixed-v03','repo/benchmarks/mixed-v04',
        'repo/benchmarks/former-pilot-v3','repo/benchmarks/independent-pilot-v01','repo/runs/sector94-100-v02']
    assert not subprocess.check_output(['git','diff','--name-only','8fc001c','--',*preserved],cwd=ROOT,text=True)
    smoke=read_json(ROOT/'repo/data/products-cli-smoke/case.json')
    assert not smoke['errors'] and smoke['comparison']['status']=='product_review_required'
    assert smoke['conclusions']['SAP']['selected_period_d'] and smoke['conclusions']['PDCSAP']['selected_period_d'] is None
    assessment=read_json(BENCH/'quiet-controls-research-v01/assessment.json')
    assert assessment['trusted_tess_quiet_controls_added']==0
    arxiv=BENCH/'quiet-controls-research-v01'
    assert sha256(arxiv/'arxiv-abstract.html')==read_json(arxiv/'arxiv-abstract-receipt.json')['sha256']
    report={'checked_at':now(),'cases':len(result['results']),'completed':sum(r['status']=='completed' for r in result['results']),
            'unavailable':sum(r['status']=='unavailable' for r in result['results']),'failed':sum(r['status']=='failed' for r in result['results']),
            'observations':count,'product_searches':count*2,'reference_scoring_did_not_change_predictions':True,
            'former_six_correct_by_product':period_scores,'event_observations':len(ev['observations']),
            'frozen_code_verified':protocol['code_files'],'historical_results_preserved':preserved,'broken_links':broken,
            'cli_smoke':'passed','trusted_quiet_controls_added':0,
            'note':'Development and artifact integrity only; same-photon products are not independent observations. No new population accuracy validation.'}
    write_json(BENCH/'products-integrity-audit.json',report);print(report)

if __name__=='__main__':main()
