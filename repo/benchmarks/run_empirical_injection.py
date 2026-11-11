"""Prepare derived inputs, then run frozen v4 without giving it injection truth."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import subprocess
import numpy as np
from astropy.io import fits
from vstar.io import read_json, write_json, now, sha256
from vstar.products import review_products
from vstar.adjudication import adjudicate, AdjudicationConfig
from empirical_injection import prepare_residual, materialize

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'repo/benchmarks/empirical-injection-v01'
PROTOCOL = OUT/'protocol.json'


def verify_protocol():
    protocol = read_json(PROTOCOL)
    for item in protocol['frozen_files']:
        if sha256(ROOT/item['path']) != item['sha256']:
            raise ValueError('Frozen file changed: '+item['path'])
    return protocol


def prepare():
    protocol = verify_protocol()
    if (OUT/'input-manifest.json').exists():
        raise FileExistsError('Prepared inputs already exist; use a new version for changes')
    bases = []
    for base in protocol['bases']:
        observations = []
        with fits.open(ROOT/base['inputs'][0]['path']) as h:
            origin = float(np.nanmin(h[1].data['TIME']))
        for item in base['inputs']:
            source = ROOT/item['path']
            if sha256(source) != item['sha256']: raise ValueError('Source hash mismatch')
            path = OUT/'residuals'/f'{base["id"]}-s{item["sector"]}.npz'
            path.parent.mkdir(exist_ok=True)
            meta = prepare_residual(source, base['parent_period_d'], origin, path, protocol['harmonics'])
            observations.append({'source': item, 'residual_path': str(path.relative_to(ROOT)),
                                 'residual_sha256': sha256(path), 'metadata': meta})
        bases.append({'id': base['id'], 'origin_btjd': origin, 'observations': observations})
    manifest = {'created_at': now(), 'protocol_sha256': sha256(PROTOCOL), 'bases': bases, 'cases': []}
    # All amplitude/phase choices are in the committed protocol before fitting data.
    for base in bases:
        for spec in protocol['signals']:
            ident = base['id']+'-'+spec['id']; inputs = []
            for obs in base['observations']:
                path = OUT/'inputs'/ident/f's{obs["source"]["sector"]}.fits.gz'
                materialize(ROOT/obs['source']['path'], ROOT/obs['residual_path'], obs['metadata'], spec, base['origin_btjd'], path)
                inputs.append({'sector': obs['source']['sector'], 'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)})
            manifest['cases'].append({'id': ident, 'base_id': base['id'], 'signal': spec, 'inputs': inputs,
                                      'kind': 'artificial_post_reduction_injection_into_empirical_residuals'})
    write_json(OUT/'input-manifest.json', manifest)
    print('Prepared', len(manifest['cases']), 'cases', flush=True)


def analyze_case(case):
    ident = case['id']; folder = OUT/'evaluation'/ident
    # Only paths and neutral ID enter the detector; no parent/injected period is passed.
    try:
        for item in case['inputs']:
            if sha256(ROOT/item['path']) != item['sha256']: raise ValueError('Injected FITS hash mismatch')
        products = review_products([ROOT[i['path']] for i in case['inputs']], folder, identity=ident)
        for obs in products['observations']:
            obs['input']['path'] = str(Path(obs['input']['path']).relative_to(ROOT))
        write_json(folder/'case.json', products)
        config = read_json(ROOT/'repo/benchmarks/adjudication-protocol-v01.json')['config']
        decision = adjudicate(products, ROOT, AdjudicationConfig(**config))
        write_json(folder/'adjudication.json', decision)
        row = {'id': ident, 'status': 'failed' if products['errors'] else 'completed', 'decision': decision,
               'products': products}
    except Exception as exc:
        row = {'id': ident, 'status': 'failed', 'error': str(exc), 'decision': None, 'products': None}
    write_json(OUT/'evaluation'/(ident+'-prediction.json'), row)
    return row


def evaluate(workers):
    verify_protocol(); manifest = read_json(OUT/'input-manifest.json')
    folder = OUT/'evaluation'; folder.mkdir(exist_ok=True)
    path = folder/'predictions.json'
    if path.exists() and read_json(path).get('complete'):
        raise FileExistsError('Completed predictions cannot be replaced')
    output = {'created_at': now(), 'complete': False, 'protocol_sha256': sha256(PROTOCOL),
              'manifest_sha256': sha256(OUT/'input-manifest.json'),
              'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'results': []}
    pending = []
    for case in manifest['cases']:
        saved = folder/(case['id']+'-prediction.json')
        if saved.exists(): output['results'].append(read_json(saved))
        else:
            if (folder/case['id']).exists(): raise RuntimeError('Partial case directory requires explicit audit: '+case['id'])
            pending.append({'id': case['id'], 'inputs': case['inputs']})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(analyze_case, pending):
            output['results'].append(row); write_json(path, output)
            print(row['id'], row['status'], (row['decision'] or {}).get('selected_period_d'), flush=True)
    output.update(complete=True, completed_at=now()); write_json(path, output)
    print('Predictions saved before scoring:', sha256(path), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['prepare', 'evaluate'])
    parser.add_argument('--workers', type=int, default=2); args = parser.parse_args()
    if args.stage == 'prepare': prepare()
    else: evaluate(args.workers)
