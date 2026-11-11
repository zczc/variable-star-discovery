"""Verify frozen v4, untouched test provenance, results and reports."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime
import subprocess,re
from urllib.parse import urlsplit,unquote
from astropy.io import fits
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from audit_v2 import Links
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks'


def main():
    protocol=read_json(BENCH/'adjudication-protocol-v01.json')
    for item in protocol['code_files']:
        assert sha256(ROOT/item['path'])==item['sha256']
        assert (ROOT/item['path']).read_bytes()==subprocess.check_output(['git','show','9a2bc4c:'+item['path']],cwd=ROOT)
    record={'checked_at':now(),'runs':[],'broken_links':[],'science_unchanged_since_freeze':'9a2bc4c'}
    for run in [BENCH/'adjudication-v01',BENCH/'independent-pilot-v02/evaluation']:
        pred=read_json(run/'predictions.json');r=read_json(run/'results.json')
        assert pred['complete'] and sha256(run/'predictions.json')==r['predictions_sha256']
        assert r['code_fingerprint']==code_fingerprint()
        assert r['protocol_sha256']==sha256(BENCH/'adjudication-protocol-v01.json')
        assert r['runner_sha256']==sha256(BENCH/'evaluate_v4.py')
        assert sha256(ROOT/r['source']['path'])==r['source']['sha256']
        stripped=deepcopy(r);del stripped['predictions_sha256'],stripped['metrics']
        for row in stripped['results']:del row['score'],row['reference_period_d']
        assert stripped==pred
        count=0
        for row in r['results']:
            if not row['products']:continue
            assert not row['decision']['confirmed_variable'] and not row['decision']['target_candidate']
            for o in row['products']['observations']:
                assert sha256(ROOT/o['input']['path'])==o['input']['sha256'];count+=1
                plotbase=BENCH/'products-v01' if r['mode']=='development' else run
                assert sha256(plotbase/row['id']/o['plot'])==o['plot_sha256']
        prov=read_json(run/'report-provenance.json')
        assert prov['results_sha256']==sha256(run/'results.json') and prov['renderer_sha256']==sha256(BENCH/'build_v4_report.py')
        for f in run.rglob('*.html'):
            parser=Links();parser.feed(f.read_text())
            for link in parser.links:
                u=urlsplit(link)
                if not u.scheme and not u.netloc and u.path and not (f.parent/unquote(u.path)).exists():record['broken_links'].append([str(f),link])
        record['runs'].append({'path':str(run.relative_to(ROOT)),**r['metrics'],'observations':count,'predictions_unchanged_by_scoring':True})
    fresh=BENCH/'independent-pilot-v02';m=read_json(fresh/'input-manifest.json');p=read_json(BENCH/'independent-pilot-protocol-v02.json')
    assert [c['name'] for c in m['cases']]==p['targets']
    assert m['protocol_sha256']==sha256(BENCH/'independent-pilot-protocol-v02.json')
    assert p['algorithm_protocol_sha256']==sha256(BENCH/'adjudication-protocol-v01.json')
    assert m['acquisition_script_sha256']==sha256(BENCH/'acquire_independent_pilot_v02.py')
    old=set()
    for path in (ROOT/'repo/runs').glob('*/targets.json'):old.update(str(x['tic']) for x in read_json(path))
    old.update(str(x['tic']) for x in read_json(BENCH/'known-controls.json')['targets'])
    old.update(str(x['tic']) for x in read_json(BENCH/'independent-pilot-v01/input-manifest.json')['cases'] if x.get('tic'))
    assert not old.intersection(c['tic'] for c in m['cases'] if c.get('tic'))
    observations=0
    for c in m['cases']:
        for item in c['inputs']:
            path=ROOT/item['path'];receipt=read_json(path.with_suffix('.receipt.json'))
            assert sha256(path)==item['sha256']==receipt['sha256']
            assert datetime.fromisoformat(receipt['downloaded_at'])>datetime.fromisoformat(p['frozen_at'])
            with fits.open(path) as f:
                assert str(f[0].header['TICID'])==c['tic'] and f[0].header['SECTOR']==item['sector']
            observations+=1
    preserved=['repo/src/vstar/screening.py','repo/src/vstar/screening_v3.py','repo/src/vstar/products.py','repo/src/vstar/review.py','repo/src/vstar/eclipse_events.py',
      'repo/benchmarks/mixed-v01','repo/benchmarks/mixed-v02','repo/benchmarks/mixed-v03','repo/benchmarks/mixed-v04','repo/benchmarks/former-pilot-v3',
      'repo/benchmarks/products-v01','repo/benchmarks/independent-pilot-v01','repo/runs/sector94-100-v02']
    assert not subprocess.check_output(['git','diff','--name-only','7e559cd','--',*preserved],cwd=ROOT,text=True)
    doc=ROOT/'doc/16-adjudication-and-new-test.md'
    for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
        u=urlsplit(link)
        if not u.scheme and u.path and not (doc.parent/unquote(u.path)).exists():record['broken_links'].append([str(doc),link])
    assert not record['broken_links'],record['broken_links']
    smoke=read_json(ROOT/'repo/data/v4-cli-smoke/adjudication.json')
    assert smoke['status']=='event_supported_period_product_caution' and not smoke['confirmed_variable']
    transfer=read_json(BENCH/'adjudication-v01/rt-aur-transfer.json')
    assert sha256(BENCH/'adjudication-v01'/transfer['plot'])==transfer['plot_sha256']
    assert transfer['holdout_gain_vs_heldout_mean']<0 and not transfer['independent_period_measurement']
    record.update(new_fits=observations,new_test_overlaps_prior_tics=False,download_after_rule_freeze=True,
        old_results_preserved=preserved,cli_smoke='passed',quiet_real_controls=0,
        note='The new test has6 preselected known positives,4 available and3 correct final periods. No population or false-positive certification.')
    write_json(BENCH/'v4-integrity-audit.json',record);print(record)

if __name__=='__main__':main()
