"""Prefetch fixed benchmark bytes through the same locked, hash-checked transport.

This worker neither reads labels nor analyzes flux. It can run beside the main
runner because each product is locked by the existing transport implementation.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter
import argparse

from vstar.io import read_json, write_json, sha256, now, run_lock
from run_labelled_validation import verify, OUT, CACHE
from scale_direct_transport import fetch_ranged


def prepare():
    verify()
    path = OUT / 'prefetch/plan.json'
    if path.exists():
        raise FileExistsError(path)
    cases = read_json(OUT / 'blind-inputs.json')['cases']
    # Reverse the same immutable ordering to start away from foreground downloads.
    products = [{'id': c['id'], 'tic': c['tic'], **s} for c in reversed(cases[32:]) for s in c['inputs']]
    write_json(path, {'created_at': now(), 'blind_inputs_sha256': sha256(OUT / 'blind-inputs.json'),
        'runner_sha256': sha256(Path(__file__)), 'products': products,
        'scientific_results_changed': False, 'purpose': 'Byte prefetch only; no labels or flux analysis'})


def fetch(product):
    path, receipt = fetch_ranged(product['uri'], product['tic'], product['sector'], CACHE)
    return {'id': product['id'], 'sector': product['sector'], 'status': 'cached',
            'path': str(path), 'receipt': receipt}


def run(workers):
    verify()
    plan = read_json(OUT / 'prefetch/plan.json')
    assert plan['blind_inputs_sha256'] == sha256(OUT / 'blind-inputs.json')
    assert plan['runner_sha256'] == sha256(Path(__file__))
    states = Counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch, p): p for p in plan['products']}
        for index, future in enumerate(as_completed(futures), 1):
            p = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {'id': p['id'], 'sector': p['sector'], 'status': 'failed', 'error': str(exc)}
            states[result['status']] += 1
            write_json(OUT / 'prefetch/results' / f'{p["id"]}-s{p["sector"]}.json', result)
            write_json(OUT / 'prefetch/status.json', {'updated_at': now(), 'requested': len(futures),
                       'returned': index, 'states': dict(states), 'science_analyzed': False})
            print('prefetched', index, '/', len(futures), result['status'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'run'])
    parser.add_argument('--workers', type=int, default=24)
    args = parser.parse_args()
    (OUT / 'prefetch').mkdir(parents=True, exist_ok=True)
    with run_lock(OUT / 'prefetch'):
        prepare() if args.command == 'prepare' else run(args.workers)
