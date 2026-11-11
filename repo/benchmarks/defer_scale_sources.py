"""Record a staged source-review policy without modifying any scientific result."""
from pathlib import Path
import os,json,tempfile
from vstar.io import read_json,write_json,now,sha256
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'repo/benchmarks/scale-validation-v01'

def main():
    policy=OUT/'source-sampling-policy.json'
    if not policy.exists():
        write_json(policy,{'created_at':now(),'reason':'Measured pixel transport is much slower and larger than LC transport; default to proposed staged resource plan after optional preference question. No scientific thresholds change.','target_sample_size':100,'seed':'scale-source-sample-20261111-v1','quota':{'catalog_eb':40,'neighbor_risk':30,'field_unlabelled':30},'eligibility':'Completed period analysis: selected period for catalog/field, or selected period/nearest catalog neighbor diagnostic in 0.1–8 d for risk. No exclusion by source outcome, apparent image quality, or period agreement.','selection':'Within each group sort SHA256(seed+":"+tic); take quota; fill shortfall from all remaining eligible targets by same key. Freeze actual list after all1000 predictions, before running its new source reviews.','pilot_handling':'Source jobs already in flight may finish; retain them as additional convenience controls if not sampled. Do not replace sampled targets with successful pilot cases.','interpretation':'100 sampled source reviews are not100 independent truth labels; no population precision claim. Deferred objects do not pass.','complete_results_immutable':True})
    dest=OUT/'source-results';dest.mkdir(exist_ok=True);created=0
    for c in read_json(OUT/'targets.json')['cases']:
        path=dest/(c['id']+'.json')
        if path.exists():continue
        record={'id':c['id'],'status':'deferred_source_review','created_at':now(),'reason':'Awaiting fixed100 source sample after full1000 lightcurve analysis; not a passed check','source_review':{},'policy_sha256':sha256(policy)}
        # Link a complete temp file atomically only if no result already exists.
        fd,tmp=tempfile.mkstemp(prefix='.defer-',dir=dest)
        try:
            with os.fdopen(fd,'w') as f:json.dump(record,f,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
            try:os.link(tmp,path);created+=1
            except FileExistsError:pass
        finally:Path(tmp).unlink(missing_ok=True)
    print('Deferred records created:',created,'; active source jobs may still finish and supply actual results.')
if __name__=='__main__':main()
