"""Restore exact public FITS inputs; no search or new target selection."""
from pathlib import Path
import argparse
from vstar.io import read_json,sha256
from scale_validation_support import fetch_product
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'repo/benchmarks/scale-validation-v01'

def main():
    p=argparse.ArgumentParser();p.add_argument('--tic',default='all');a=p.parse_args();seen=set()
    for c in read_json(OUT/'targets.json')['cases']:
        if a.tic!='all' and c['tic']!=a.tic:continue
        pred=OUT/'evaluation'/(c['id']+'-prediction.json')
        if not pred.exists():continue
        items=list(read_json(pred)['inputs'])
        source=OUT/'evaluation'/c['id']/'source/source-manifest.json'
        if source.exists():
            for i in read_json(source)['inputs']:
                if i.get('pixels'):items.append(dict(i['pixels'],sector=i['sector']))
        for item in items:
            if item['uri'] in seen:continue
            path,receipt=fetch_product(item['uri'],c['tic'],item['sector'],(ROOT/item['path']).parent)
            assert receipt['raw_sha256']==item['raw_sha256'] and sha256(path)==item['sha256'],'Archive bytes changed; do not silently substitute'
            seen.add(item['uri']);print(len(seen),c['tic'],item['sector'],flush=True)
    if not seen:raise ValueError('No saved products for requested TIC')
if __name__=='__main__':main()
