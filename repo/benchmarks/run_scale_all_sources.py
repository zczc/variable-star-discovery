"""Review every selected target and every risk target after all predictions exist.

The user's later response superseded the proposed 100-target resource limit.
Only orchestration changes; original period and source functions remain frozen.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import os
from vstar.io import read_json, write_json, sha256, now, run_lock
from run_scale_validation import OUT, verify
from run_scale_source_sample import review_with_prefetch


def eligible(case, prediction):
    return case['group'] == 'neighbor_risk' or (
        prediction['status'] == 'completed'
        and prediction.get('decision', {}).get('selected_period_d') is not None
    )


def prepare():
    verify()
    path = OUT / 'source-all.json'
    if path.exists():
        raise FileExistsError('Full source cohort already frozen')
    cases = read_json(OUT / 'targets.json')['cases']
    chosen, predictions = [], []
    for case in cases:
        p = OUT / 'evaluation' / (case['id'] + '-prediction.json')
        row = read_json(p)  # Missing predictions stop preparation.
        predictions.append({'id': case['id'], 'sha256': sha256(p)})
        if eligible(case, row):
            chosen.append(case)
    assert len(predictions) == 1000
    prefetch_ids = {c['id'] for c in read_json(OUT / 'source-prefetch.json')['cases']}
    assert prefetch_ids <= {c['id'] for c in chosen}
    # Cached objects first; this affects queue order only, never membership.
    chosen.sort(key=lambda c: (c['id'] not in prefetch_ids, int(c['tic'])))
    code = [Path(__file__), Path(__file__).with_name('run_scale_source_sample.py'),
            Path(__file__).with_name('scale_range_transport.py')]
    write_json(path, {
        'created_at': now(),
        'scope': 'Every selected-period target and all 50 neighbor-risk targets',
        'authorization': 'User answered the pending resource question: review all selected and high-risk targets, accept longer runtime; handle disk space if needed.',
        'supersedes': 'source-sampling-policy.json proposed 100-case limit; no source-sample.json was prepared or run',
        'scientific_rules_changed': False,
        'cases': chosen,
        'prediction_hashes': predictions,
        'frozen_runner_files': [{'name': p.name, 'sha256': sha256(p)} for p in code],
        'meaning': 'No selection by source outcome; unavailable, incomplete and failed evidence remain in the cohort.'
    })
    print('Prepared full source cohort:', len(chosen), flush=True)


def run(workers):
    verify()
    if not 1 <= workers <= 6:
        raise ValueError('Use at most 6 workers alongside 2 prefetch workers')
    manifest = read_json(OUT / 'source-all.json')
    for item in manifest['frozen_runner_files']:
        assert sha256(Path(__file__).with_name(item['name'])) == item['sha256']
    for item in manifest['prediction_hashes']:
        assert sha256(OUT / 'evaluation' / (item['id'] + '-prediction.json')) == item['sha256']
    archive = OUT / 'source-deferrals'
    archive.mkdir(exist_ok=True)
    for case in manifest['cases']:
        p = OUT / 'source-results' / (case['id'] + '.json')
        if p.exists() and read_json(p)['status'] == 'deferred_source_review':
            dest = archive / p.name
            if dest.exists():
                raise FileExistsError('Deferral already archived; audit before retry')
            os.replace(p, dest)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(review_with_prefetch, c) for c in manifest['cases']]
        for i, f in enumerate(as_completed(futures), 1):
            row = f.result()
            print('full source', i, '/', len(futures), row['id'], row['status'],
                  row.get('source_review', {}).get('conclusion', {}).get('route'), flush=True)
    write_json(OUT / 'source-all-status.json', {
        'completed_at': now(), 'requested': len(manifest['cases']),
        'cohort_sha256': sha256(OUT / 'source-all.json'),
        'meaning': 'All jobs returned records; failed or incomplete evidence does not pass.'
    })


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['prepare', 'run'])
    p.add_argument('--workers', type=int, default=6)
    args = p.parse_args()
    with run_lock(OUT):
        if args.stage == 'prepare':
            prepare()
        else:
            run(args.workers)
