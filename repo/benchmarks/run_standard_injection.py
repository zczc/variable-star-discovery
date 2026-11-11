"""Freeze -> prepare -> predict -> score separately; resumable immutable case predictions."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import subprocess
from vstar.io import read_json,write_json,sha256,now
from vstar.products import review_products
from vstar.adjudication import adjudicate,AdjudicationConfig
from standard_injection import construct
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/benchmarks/standard-injection-v01'


def verify_protocol():
    protocol=read_json(OUT/'protocol.json')
    for item in protocol['frozen_files']:
        if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Frozen code changed: '+item['path'])
    return protocol


def prepare():
    protocol=verify_protocol();path=OUT/'input-manifest.json'
    if path.exists():raise FileExistsError('Prepared study cannot be replaced')
    manifest={'created_at':now(),'protocol_sha256':sha256(OUT/'protocol.json'),'cases':[]}
    for base in protocol['bases']:
        for spec in protocol['signals']:
            ident=base['id']+'-'+spec['id'];inputs=[]
            for source in base['inputs']:
                if sha256(ROOT/source['path'])!=source['sha256']:raise ValueError('Source changed')
                generated=ROOT/'repo/data/standard-injection-v01'/ident/f's{source["sector"]}.fits.gz'
                metadata=construct(ROOT/source['path'],spec,base['origin_btjd'],generated)
                inputs.append({'path':str(generated.relative_to(ROOT)),'sha256':sha256(generated),
                    'sector':source['sector'],'source':source,'construction':metadata})
            manifest['cases'].append({'id':ident,'base_id':base['id'],'signal':spec,'origin_btjd':base['origin_btjd'],'inputs':inputs})
        print('Prepared',base['id'],len(protocol['signals']),'cases',flush=True)
    manifest['completed_at']=now();write_json(path,manifest)


def rebuild(ident):
    verify_protocol();manifest=read_json(OUT/'input-manifest.json')
    selected=[c for c in manifest['cases'] if ident=='all' or c['id']==ident]
    if not selected:raise ValueError('Unknown case ID')
    for case in selected:
        for item in case['inputs']:
            source=item['source']
            if sha256(ROOT/source['path'])!=source['sha256']:raise ValueError('Source changed')
            construct(ROOT/source['path'],case['signal'],case['origin_btjd'],ROOT/item['path'])
            if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Rebuilt input differs')
    print('Rebuilt and hash verified',len(selected),'cases',flush=True)


def analyze_case(case):
    ident=case['id'];folder=OUT/'evaluation'/ident
    try:
        for item in case['inputs']:
            if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Input hash mismatch; rebuild first')
        products=review_products([ROOT/i['path'] for i in case['inputs']],folder,identity=ident)
        for obs in products['observations']:obs['input']['path']=str(Path(obs['input']['path']).relative_to(ROOT))
        write_json(folder/'case.json',products)
        config=read_json(ROOT/'repo/benchmarks/adjudication-protocol-v01.json')['config']
        decision=adjudicate(products,ROOT,AdjudicationConfig(**config));write_json(folder/'adjudication.json',decision)
        row={'id':ident,'status':'failed' if products['errors'] else 'completed','products':products,'decision':decision}
    except Exception as exc:
        row={'id':ident,'status':'failed','error':str(exc),'products':None,'decision':None}
    write_json(OUT/'evaluation'/(ident+'-prediction.json'),row)
    return row


def evaluate(workers):
    verify_protocol();manifest=read_json(OUT/'input-manifest.json');folder=OUT/'evaluation';folder.mkdir(exist_ok=True)
    path=folder/'predictions.json'
    if path.exists() and read_json(path).get('complete'):raise FileExistsError('Completed predictions immutable')
    output={'created_at':now(),'complete':False,'manifest_sha256':sha256(OUT/'input-manifest.json'),
            'protocol_sha256':sha256(OUT/'protocol.json'),
            'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'results':[]}
    pending=[]
    for case in manifest['cases']:
        saved=folder/(case['id']+'-prediction.json')
        if saved.exists():output['results'].append(read_json(saved))
        else:
            if (folder/case['id']).exists():raise RuntimeError('Partial case needs audit: '+case['id'])
            # Detector has no access to injected truth or the source-star label.
            pending.append({'id':case['id'],'inputs':[{'path':i['path'],'sha256':i['sha256']} for i in case['inputs']]})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(analyze_case,pending):
            output['results'].append(row);write_json(path,output)
            print(len(output['results']),row['id'],row['status'],(row['decision'] or {}).get('selected_period_d'),flush=True)
    output.update(complete=True,completed_at=now());write_json(path,output)
    print('Saved all unscored predictions',sha256(path),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','evaluate','rebuild'])
    p.add_argument('--workers',type=int,default=2);p.add_argument('--case',default='all');a=p.parse_args()
    if a.stage=='prepare':prepare()
    elif a.stage=='rebuild':rebuild(a.case)
    else:evaluate(a.workers)
