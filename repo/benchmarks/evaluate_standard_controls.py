"""Describe v4 behavior on three externally selected, bounded standard controls."""
from pathlib import Path
import subprocess
from vstar.io import read_json,write_json,sha256,now
from vstar.products import review_products
from vstar.adjudication import adjudicate,AdjudicationConfig
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/standard-star-check-v01'


def main():
    protocol=read_json(ROOT/'repo/benchmarks/adjudication-protocol-v01.json')
    for item in protocol['code_files']:
        if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Frozen detector changed')
    manifest=read_json(BASE/'input-manifest.json');out=BASE/'evaluation';out.mkdir(exist_ok=False)
    result={'created_at':now(),'complete':False,'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'runner_sha256':sha256(Path(__file__)),'manifest_sha256':sha256(BASE/'input-manifest.json'),
            'label_scope':'Literature-bounded standards, NOT calibrated TESS negatives','false_positive_denominator':0,'results':[]}
    for case in manifest['cases']:
        row={'id':case['id'],'name':case['name'],'status':'unavailable','decision':None,'products':None}
        if case['status']=='acquired':
            for item in case['inputs']:
                if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Input changed')
            products=review_products([ROOT/i['path'] for i in case['inputs']],out/case['id'],identity=case['id'])
            for obs in products['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
            write_json(out/case['id']/'case.json',products)
            decision=adjudicate(products,ROOT,AdjudicationConfig(**protocol['config']))
            write_json(out/case['id']/'adjudication.json',decision)
            row.update(status='failed' if products['errors'] else 'completed',products=products,decision=decision)
        else:row['reason']=case['unavailable_reason']
        result['results'].append(row);write_json(out/'predictions.json',result)
        print(row['name'],row['status'],(row['decision'] or {}).get('selected_period_d'),flush=True)
    result.update(complete=True,completed_at=now());write_json(out/'predictions.json',result)

if __name__=='__main__':main()
