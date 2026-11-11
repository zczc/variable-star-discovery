"""Frozen strong-signal threats and known-source controls; preserve all predictions."""
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import subprocess
from vstar.io import read_json,write_json,sha256,now
from vstar.products import review_products
from vstar.adjudication import adjudicate,AdjudicationConfig
from vstar.source_review import review_case
from precision_challenges import construct
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/benchmarks/precision-audit-v01'


def verify():
    protocol=read_json(OUT/'protocol.json')
    for item in protocol['frozen_files']:
        if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Frozen file changed: '+item['path'])
    return protocol


def prepare():
    protocol=verify()
    if (OUT/'input-manifest.json').exists():raise FileExistsError('Prepared inputs already exist')
    manifest={'created_at':now(),'protocol_sha256':sha256(OUT/'protocol.json'),'cases':[]}
    for base in protocol['bases']:
        for spec in protocol['challenges']:
            ident=base['id']+'-'+spec['id'];inputs=[]
            for source in base['inputs']:
                if sha256(ROOT/source['path'])!=source['sha256']:raise ValueError('Source hash mismatch')
                path=ROOT/'repo/data/precision-audit-v01'/ident/f's{source["sector"]}.fits.gz'
                metadata=construct(ROOT/source['path'],spec,base['origin_btjd'],path)
                inputs.append({'path':str(path.relative_to(ROOT)),'sha256':sha256(path),'sector':source['sector'],
                    'source':source,'construction':metadata})
            manifest['cases'].append({'id':ident,'kind':'artificial','challenge':spec,'base_id':base['id'],
                'origin_btjd':base['origin_btjd'],'inputs':inputs,'target':None,'diagnostic_period':None})
    manifest['cases']+=protocol['real_cases'];write_json(OUT/'input-manifest.json',manifest)
    print('Prepared',len(manifest['cases']),'cases',flush=True)


def analyze_case(case):
    ident=case['id'];folder=OUT/'evaluation'/ident
    try:
        for item in case['inputs']:
            if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Input hash mismatch')
        products=review_products([ROOT/item['path'] for item in case['inputs']],folder/'period',identity=ident)
        for obs in products['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
        write_json(folder/'period/case.json',products)
        cfg=AdjudicationConfig(**read_json(ROOT/'repo/benchmarks/adjudication-protocol-v01.json')['config'])
        decision=adjudicate(products,ROOT,cfg);write_json(folder/'period/adjudication.json',decision)
        source=review_case(case['inputs'],decision,case.get('target'),folder/'source',ROOT,case.get('diagnostic_period'))
        write_json(folder/'source/source-review.json',source)
        write_json(folder/'source-manifest.json',{'inputs':case['inputs'],'decision':decision,'target':case.get('target'),'diagnostic_period':case.get('diagnostic_period')})
        row={'id':ident,'status':'failed' if products['errors'] or source['errors'] else 'completed',
             'products':products,'decision':decision,'source_review':source}
    except Exception as exc:row={'id':ident,'status':'failed','error':str(exc)}
    write_json(OUT/'evaluation'/(ident+'-prediction.json'),row)
    return row


def evaluate(workers):
    verify();manifest=read_json(OUT/'input-manifest.json');folder=OUT/'evaluation';folder.mkdir(exist_ok=True)
    path=folder/'predictions.json'
    if path.exists() and read_json(path).get('complete'):raise FileExistsError('Predictions immutable')
    output={'created_at':now(),'complete':False,'manifest_sha256':sha256(OUT/'input-manifest.json'),
        'protocol_sha256':sha256(OUT/'protocol.json'),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'results':[]}
    pending=[]
    for case in manifest['cases']:
        saved=folder/(case['id']+'-prediction.json')
        if saved.exists():output['results'].append(read_json(saved))
        else:
            if (folder/case['id']).exists():raise RuntimeError('Partial case requires audit')
            pending.append({k:case.get(k) for k in ['id','inputs','target','diagnostic_period']})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(analyze_case,pending):
            output['results'].append(row);write_json(path,output)
            print(len(output['results']),row['id'],row['status'],row.get('source_review',{}).get('conclusion',{}).get('route'),flush=True)
    output.update(complete=True,completed_at=now());write_json(path,output)
    print('Predictions saved before challenge labels are compared',sha256(path),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','evaluate']);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    if a.stage=='prepare':prepare()
    else:evaluate(a.workers)
