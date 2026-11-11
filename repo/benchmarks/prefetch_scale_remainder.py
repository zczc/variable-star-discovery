"""Reuse the two finished prefetch slots for spaced, already-authorized targets.

Only transports original bytes. Full source cohort and scientific code unchanged.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
from vstar.io import read_json, write_json, sha256, now, run_lock
from run_scale_validation import OUT, ROOT, verify
from prefetch_scale_sources import fetch_case


def prepare():
    verify()
    dest = OUT / 'source-extra-prefetch.json'
    if dest.exists():
        raise FileExistsError('Extra transport schedule already frozen')
    original = {c['id'] for c in read_json(OUT / 'source-prefetch.json')['cases']}
    remaining = []
    for case in read_json(OUT / 'source-all.json')['cases']:
        result = OUT / 'source-results' / (case['id'] + '.json')
        returned = result.exists() and read_json(result)['status'] in {'completed', 'incomplete', 'transport_failed'}
        if case['id'] not in original and not returned:
            remaining.append(case)
    chosen = remaining[11::4]
    code = [Path(__file__), Path(__file__).with_name('prefetch_scale_sources.py'),
            Path(__file__).with_name('scale_range_transport.py')]
    write_json(dest, {
        'created_at': now(), 'cases': chosen,
        'full_cohort_sha256': sha256(OUT / 'source-all.json'),
        'remaining_ids_at_preparation': [c['id'] for c in remaining],
        'schedule': 'Every fourth remaining full-cohort target, starting twelve ahead; two transport workers after initial prefetch ends, plus six unchanged source workers.',
        'purpose': 'Byte-only prefetch; no science, thresholds, period predictions or source cohort membership change.',
        'frozen_files': [{'name': p.name, 'sha256': sha256(p)} for p in code]
    })
    print('Prepared extra byte-only prefetch targets:', len(chosen), flush=True)


def run():
    verify()
    assert (OUT / 'source-prefetch-status.json').exists(), 'Wait for the initial two prefetch workers to finish'
    manifest = read_json(OUT / 'source-extra-prefetch.json')
    assert manifest['full_cohort_sha256'] == sha256(OUT / 'source-all.json')
    for item in manifest['frozen_files']:
        assert sha256(Path(__file__).with_name(item['name'])) == item['sha256']
    cases = []
    skipped = []
    for case in manifest['cases']:
        result = OUT / 'source-results' / (case['id'] + '.json')
        if result.exists() and read_json(result)['status'] in {'completed', 'incomplete'}:
            skipped.append(case['id'])
        elif not (OUT / 'prefetch-results' / (case['id'] + '.json')).exists():
            cases.append(case)
    lock = ROOT / 'repo/data/scale-validation-v01/extra-prefetch-lock'
    lock.mkdir(exist_ok=True)
    with run_lock(lock), ProcessPoolExecutor(max_workers=2) as pool:
        for i, f in enumerate(as_completed([pool.submit(fetch_case, c) for c in cases]), 1):
            row = f.result()
            print('extra prefetch', i, '/', len(cases), row['id'], [p['status'] for p in row['products']], flush=True)
    write_json(OUT / 'source-extra-prefetch-status.json', {
        'completed_at': now(), 'requested': len(manifest['cases']),
        'skipped_already_reviewed': skipped, 'pixel_flux_analyzed': False,
        'manifest_sha256': sha256(OUT / 'source-extra-prefetch.json')
    })


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['prepare', 'run'])
    args = p.parse_args()
    if args.stage == 'prepare':
        prepare()
    else:
        run()
