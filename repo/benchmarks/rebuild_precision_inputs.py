"""Recreate cached artificial inputs from the public manifest without overwriting results."""
import argparse
from vstar.io import read_json,sha256
from precision_challenges import construct
from run_precision_audit import ROOT,OUT,verify


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',default='all');a=p.parse_args();verify()
    manifest=read_json(OUT/'input-manifest.json')
    selected=[c for c in manifest['cases'] if c['kind']=='artificial' and (a.case=='all' or a.case==c['id'])]
    if not selected:raise ValueError('Unknown artificial case')
    for case in selected:
        for item in case['inputs']:
            source=item['source']
            if sha256(ROOT/source['path'])!=source['sha256']:raise ValueError('Original input changed')
            construct(ROOT/source['path'],case['challenge'],case['origin_btjd'],ROOT/item['path'])
            if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Reconstructed bytes differ')
    print('Rebuilt and hash checked',len(selected),'cases')

if __name__=='__main__':main()
