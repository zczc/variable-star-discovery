"""Revisit all existing real development cases, without switching targets."""
from pathlib import Path
from dataclasses import asdict
import json
import subprocess
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from vstar.models import AnalysisConfig
from vstar.screening_v3 import ScreeningConfig
from vstar.products import review_products
from run_known_controls import classify_period
from evaluate_v2 import development_inputs
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks'
PROTOCOL=BENCH/'products-protocol-v01.json'


def main():
    protocol=read_json(PROTOCOL);out=BENCH/'products-v01';out.mkdir(exist_ok=False)
    old,sources=development_inputs()
    cases=[c for c in old if c['kind'] in {'real_known_variable','real_contaminated_target'}]
    pilot=BENCH/'independent-pilot-v01/input-manifest.json';cases+=read_json(pilot)['cases'];sources.append(pilot)
    assert [c['id'] for c in cases]==protocol['cases']
    record={'created_at':now(),'complete':False,'protocol_sha256':sha256(PROTOCOL),'runner_sha256':sha256(Path(__file__)),
            'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'code_fingerprint':code_fingerprint(),'sources':[{'path':str(p.relative_to(ROOT)),'sha256':sha256(p)} for p in sources],
            'stage':'All objects are previously inspected development cases; no new independent test.','results':[]}
    for case in cases:
        if 'unavailable_reason' in case:
            row={'id':case['id'],'status':'unavailable','reason':case['unavailable_reason'],'errors':[]}
        else:
            for item in case['inputs']:assert sha256(ROOT/item['path'])==item['sha256']
            row=review_products([ROOT/i['path'] for i in case['inputs']],out/case['id'],identity=case['id'],
                                analysis=AnalysisConfig(**protocol['analysis']),config=ScreeningConfig(**protocol['screening']))
            row['status']='failed' if row['errors'] else 'completed'
            # Portable references in committed evidence. Raw FITS bytes already exist in Git.
            for obs in row['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
            write_json(out/case['id']/'case.json',row)
        row['kind']=case['kind'];record['results'].append(row)
        write_json(out/'predictions.json',record)
        print(case['id'],row['status'],{n:c['selected_period_d'] for n,c in row.get('conclusions',{}).items()},flush=True)
    record.update(complete=True,completed_at=now());write_json(out/'predictions.json',record)
    record['predictions_sha256']=sha256(out/'predictions.json')
    # Score only after every prediction has been persisted.
    known={c['tic']:c['period_d'] for c in read_json(BENCH/'known-controls.json')['targets']}
    for row,case in zip(record['results'],cases):
        ref=case.get('reference',{}).get('period_d') or known.get(case.get('tic'))
        row['reference_period_d']=ref
        row['score']={name:classify_period(c['selected_period_d'],ref,.01) if ref and c['selected_period_d'] else 'abstained_or_unscored'
                      for name,c in row.get('conclusions',{}).items()}
    write_json(out/'results.json',record)

if __name__=='__main__':main()
