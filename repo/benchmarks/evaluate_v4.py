"""Save v4 predictions before scoring development or new positive-only controls."""
import argparse
from pathlib import Path
from copy import deepcopy
import subprocess
from vstar.io import read_json,write_json,sha256,now,code_fingerprint
from vstar.products import review_products
from vstar.adjudication import adjudicate,AdjudicationConfig
from run_known_controls import classify_period
ROOT=Path(__file__).resolve().parents[2];BENCH=ROOT/'repo/benchmarks'


def evaluate(mode,out):
    out.mkdir(parents=True,exist_ok=False)
    protocol_path=BENCH/'adjudication-protocol-v01.json';protocol=read_json(protocol_path)
    for item in protocol['code_files']:assert sha256(ROOT/item['path'])==item['sha256']
    cfg=AdjudicationConfig(**protocol['config'])
    path=BENCH/('products-v01/results.json' if mode=='development' else 'independent-pilot-v02/input-manifest.json')
    source=read_json(path);cases=source['results'] if mode=='development' else source['cases']
    output={'created_at':now(),'mode':mode,'complete':False,'protocol_sha256':sha256(protocol_path),
      'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'runner_sha256':sha256(Path(__file__)),'code_fingerprint':code_fingerprint(),
      'source':{'path':str(path.relative_to(ROOT)),'sha256':sha256(path)},'results':[]}
    references={}
    for case in cases:
        ident=case['id'];references[ident]=case.get('reference_period_d') if mode=='development' else case.get('reference',{}).get('period_d')
        if case.get('status')=='unavailable' or 'unavailable_reason' in case:
            row={'id':ident,'status':'unavailable','reason':case.get('reason') or case.get('unavailable_reason'),'decision':None,'products':None}
        else:
            if mode=='development':
                products=deepcopy(case)
                for key in ['score','reference_period_d']:products.pop(key,None)
            else:
                for item in case['inputs']:assert sha256(ROOT/item['path'])==item['sha256']
                products=review_products([ROOT/item['path'] for item in case['inputs']],out/ident,identity=ident)
                for obs in products['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
            decision=adjudicate(products,ROOT,cfg)
            row={'id':ident,'status':'failed' if products['errors'] else 'completed','decision':decision,'products':products}
        output['results'].append(row);write_json(out/'predictions.json',output)
        print(mode,ident,row['status'],None if not row['decision'] else (row['decision']['status'],row['decision']['selected_period_d']),flush=True)
    output.update(complete=True,completed_at=now());write_json(out/'predictions.json',output)
    output['predictions_sha256']=sha256(out/'predictions.json')
    for row in output['results']:
        p=row['decision']['selected_period_d'] if row['decision'] else None
        row['reference_period_d']=references[row['id']]
        row['score']=classify_period(p,references[row['id']],.01) if p and references[row['id']] else 'abstained_or_unscored'
    output['metrics']={'cases':len(cases),'completed':sum(r['status']=='completed' for r in output['results']),
      'unavailable':sum(r['status']=='unavailable' for r in output['results']),'failed':sum(r['status']=='failed' for r in output['results']),
      'correct':sum(r['score']=='correct_period' for r in output['results']),
      'note':'Development counts include known contaminants. Independent mode contains named positives only; no quiet-control false-positive estimate.'}
    write_json(out/'results.json',output)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['development','independent'],required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();evaluate(a.mode,a.output.resolve())
