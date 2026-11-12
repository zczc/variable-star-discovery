"""Run frozen v4 science on a label-free manifest; retain every target and failure."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections import Counter
import argparse
import subprocess
import time

from vstar.io import read_json, write_json, sha256, now, run_lock
from scale_direct_transport import fetch_ranged
from labelled_validation_support import detection_flags

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'repo/benchmarks/labelled-validation-v01'
CACHE = ROOT / 'repo/data/labelled-validation-v01/fits'


def verify():
    protocol = read_json(OUT / 'protocol.json')
    for item in protocol['frozen_files']:
        if sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Frozen code or input changed: ' + item['path'])
    for case in read_json(OUT / 'blind-inputs.json')['cases']:
        assert set(case) == {'id', 'tic', 'inputs'}
        assert len(case['inputs']) == 2
    return protocol


def acquire(case):
    path = OUT / 'acquisition' / (case['id'] + '.json')
    if path.exists():
        return read_json(path)
    row = {'id': case['id'], 'tic': case['tic'], 'inputs': [], 'errors': [], 'started_at': now()}
    start = time.monotonic()
    for spec in case['inputs']:
        try:
            file, receipt = fetch_ranged(spec['uri'], case['tic'], spec['sector'], CACHE)
            row['inputs'].append(dict(spec, path=str(file.relative_to(ROOT)),
                sha256=receipt['sha256'], raw_sha256=receipt['raw_sha256'],
                raw_bytes=receipt['raw_bytes'], compressed_bytes=receipt['compressed_bytes']))
        except Exception as exc:
            row['errors'].append({'uri': spec['uri'], 'error': str(exc)})
    row.update(status='available' if len(row['inputs']) == 2 and not row['errors'] else 'unavailable',
               completed_at=now(), elapsed_seconds=time.monotonic()-start)
    write_json(path, row)
    return row


def analyze(acquisition):
    from vstar.products import review_products
    from vstar.adjudication import adjudicate
    ident = acquisition['id']
    start = time.monotonic()
    folder = OUT / 'evaluation' / ident
    row = {'id': ident, 'started_at': now(), 'inputs': acquisition['inputs'], 'status': 'unavailable',
           'errors': acquisition['errors'], 'detection': {'repeated_signal': None, 'selected_period': None}}
    if acquisition['status'] == 'available':
        try:
            for item in acquisition['inputs']:
                if sha256(ROOT / item['path']) != item['sha256']:
                    raise ValueError('Input changed')
            products = review_products([ROOT / x['path'] for x in acquisition['inputs']], folder / 'period', identity=ident)
            for observation in products['observations']:
                observation['input']['path'] = str(Path(observation['input']['path']).relative_to(ROOT))
            write_json(folder / 'period/case.json', products)
            decision = adjudicate(products, ROOT)
            write_json(folder / 'period/adjudication.json', decision)
            row.update(status='failed' if products['errors'] else 'completed', errors=products['errors'],
                product_conclusions=products['conclusions'], decision=decision,
                detection=detection_flags(products['conclusions'], decision, products['errors']))
        except Exception as exc:
            row.update(status='failed', errors=[{'error': str(exc)}])
    row.update(completed_at=now(), elapsed_seconds=time.monotonic()-start)
    write_json(OUT / 'evaluation' / (ident + '-prediction.json'), row)
    return row


def run(workers, downloads, limit=None):
    verify()
    cases = read_json(OUT / 'blind-inputs.json')['cases']
    if limit is not None:
        cases = cases[:limit]
    pending, done = [], []
    for case in cases:
        prediction = OUT / 'evaluation' / (case['id'] + '-prediction.json')
        if prediction.exists():
            done.append(read_json(prediction))
        else:
            if (OUT / 'evaluation' / case['id']).exists():
                raise RuntimeError('Partial analysis requires audit: ' + case['id'])
            pending.append(case)

    def record(row):
        done.append(row)
        states = dict(Counter(x['status'] for x in done))
        write_json(OUT / 'run-status.json', {'updated_at': now(), 'requested_this_run': len(cases),
            'returned': len(done), 'states': states, 'all_jobs_returned': len(done) == len(cases),
            'full_thousand': len(cases) == 1000, 'labels_read_by_detector': False,
            'protocol_sha256': sha256(OUT / 'protocol.json')})
        print('returned', len(done), '/', len(cases), row['id'], row['status'], row['detection'], flush=True)

    print('Requested', len(cases), 'existing', len(done), 'pending', len(pending), flush=True)
    with ThreadPoolExecutor(max_workers=downloads) as dl, ProcessPoolExecutor(max_workers=workers) as calc:
        futures = {dl.submit(acquire, c): c['id'] for c in pending}
        calculations = {}
        for future in as_completed(futures):
            acquisition = future.result()
            calculations[calc.submit(analyze, acquisition)] = acquisition['id']
            for completed in list(calculations):
                if completed.done():
                    record(completed.result())
                    del calculations[completed]
        for completed in as_completed(calculations):
            record(completed.result())
    print('Finished:', dict(Counter(x['status'] for x in done)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--downloads', type=int, default=8)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    with run_lock(OUT):
        run(args.workers, args.downloads, args.limit)
