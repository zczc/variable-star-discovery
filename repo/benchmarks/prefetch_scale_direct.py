"""Byte-only direct-archive prefetch for the unchanged transport retry cohort."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import argparse
from vstar.io import read_json, write_json, sha256, now, run_lock
from run_scale_validation import OUT, ROOT, CACHE, verify
from scale_direct_transport import fetch_ranged


FOLDER = OUT / 'direct-prefetch'


def prepare():
    verify()
    verification = OUT / 'direct-transport-verification.json'
    proof = read_json(verification)
    transport = Path(__file__).with_name('scale_direct_transport.py')
    assert proof['code_sha256'] == sha256(transport)
    plan = FOLDER / 'plan.json'
    if plan.exists():
        raise FileExistsError('Direct prefetch plan already frozen')
    retry = OUT / 'source-retries/attempt-01/plan.json'
    write_json(plan, {
        'created_at': now(), 'cases': [x['case'] for x in read_json(retry)['cases']],
        'retry_plan_sha256': sha256(retry),
        'runner_sha256': sha256(Path(__file__)), 'transport_sha256': sha256(transport),
        'verification_sha256': sha256(verification),
        'purpose': 'Fetch the same public TESS product bytes directly from the storage that MAST redirects to. No pixel analysis or changes to the 349-case source cohort or frozen scientific rules.',
        'workers_limit': 8
    })
    print('Prepared direct prefetch plan:', len(read_json(plan)['cases']), flush=True)


def fetch_case(case):
    dest = FOLDER / 'results' / (case['id'] + '.json')
    previous = read_json(dest) if dest.exists() else None
    history = []
    if previous:
        history = previous.get('previous_attempts', []) + [{k: v for k, v in previous.items() if k != 'previous_attempts'}]
    products = []
    for item in case['inputs']:
        uri = item['uri'].replace('_lc.fits', '_tp.fits')
        try:
            path, receipt = fetch_ranged(uri, case['tic'], item['sector'], CACHE)
            products.append({'uri': uri, 'path': str(path.relative_to(ROOT)), 'status': 'cached', 'receipt': receipt})
        except Exception as exc:
            products.append({'uri': uri, 'status': 'failed', 'error': str(exc)})
    result = {
        'id': case['id'], 'completed_at': now(), 'products': products,
        'status': 'cached' if len(products) == 2 and all(p['status'] == 'cached' for p in products) else 'failed',
        'pixel_flux_analyzed': False, 'previous_attempts': history
    }
    write_json(dest, result)
    return result


def run(workers):
    verify()
    assert 1 <= workers <= 8
    # Do not overlap eight downloads with a still-running source retry.
    state = read_json(OUT / 'source-retries/attempt-01/status.json')
    assert state['remaining_not_started'] >= 0
    plan = read_json(FOLDER / 'plan.json')
    assert plan['runner_sha256'] == sha256(Path(__file__))
    assert plan['transport_sha256'] == sha256(Path(__file__).with_name('scale_direct_transport.py'))
    assert plan['verification_sha256'] == sha256(OUT / 'direct-transport-verification.json')
    assert plan['retry_plan_sha256'] == sha256(OUT / 'source-retries/attempt-01/plan.json')
    pending, skipped = [], []
    for case in plan['cases']:
        result = OUT / 'source-results' / (case['id'] + '.json')
        if result.exists() and read_json(result)['status'] in {'completed', 'incomplete'}:
            skipped.append(case['id'])
        else:
            pending.append(case)
    requested = len(pending)
    done, failures, stopped = 0, 0, False
    with ProcessPoolExecutor(max_workers=workers) as pool:
        active = {}
        while pending or active:
            while pending and len(active) < workers and not stopped:
                case = pending.pop(0)
                active[pool.submit(fetch_case, case)] = case['id']
            if not active:
                break
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            for f in ready:
                active.pop(f)
                result = f.result()
                done += 1
                failures = failures + 1 if result['status'] == 'failed' else 0
                stopped = stopped or failures >= 3
                print('direct prefetch', done, '/', requested, result['id'], result['status'], flush=True)
            write_json(FOLDER / 'progress.json', {'updated_at': now(), 'returned': done, 'requested_this_run': requested, 'active': len(active), 'remaining_not_started': len(pending), 'stopped_after_consecutive_failures': stopped})
    write_json(FOLDER / 'status.json', {'updated_at': now(), 'returned': done, 'requested_this_run': requested, 'skipped_already_reviewed': skipped, 'remaining_not_started': len(pending), 'stopped_after_consecutive_failures': stopped, 'pixel_flux_analyzed': False})
    if pending:
        raise SystemExit(2)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['prepare', 'run'])
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    if args.stage == 'prepare':
        prepare()
    else:
        with run_lock(OUT):
            run(args.workers)
