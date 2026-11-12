"""Retry transport-only failures while preserving every original attempt."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import argparse
import os
from vstar.io import read_json, write_json, sha256, now, run_lock
from run_scale_validation import OUT, verify
from run_scale_source_sample import review_with_prefetch


def archive_failure(current, archive, expected):
    if archive.exists():
        assert sha256(archive) == expected, 'Archived attempt changed'
        return read_json(current) if current.exists() else None
    assert sha256(current) == expected, 'Original failure changed'
    assert read_json(current)['status'] == 'transport_failed', 'Only retry transport failures'
    archive.parent.mkdir(parents=True, exist_ok=True)
    os.replace(current, archive)
    return None


def prepare(folder):
    verify()
    if folder.exists():
        raise FileExistsError('Retry plan already exists')
    cohort = read_json(OUT / 'source-all.json')
    cases, preserved = [], []
    for c in cohort['cases']:
        p = OUT / 'source-results' / (c['id'] + '.json')
        r = read_json(p)
        if r['status'] == 'transport_failed':
            assert not (OUT / 'evaluation' / c['id'] / 'source').exists(), 'Unexpected partial science analysis'
            cases.append({'case': c, 'original_failure_sha256': sha256(p)})
        else:
            preserved.append({'id': c['id'], 'sha256': sha256(p)})
    if not cases:
        raise ValueError('No transport failures to retry')
    folder.mkdir(parents=True)
    write_json(folder / 'plan.json', {
        'created_at': now(), 'full_cohort_sha256': sha256(OUT / 'source-all.json'),
        'runner_sha256': sha256(Path(__file__)), 'cases': cases,
        'preserved_source_results': preserved,
        'scope': 'Retry only transport_failed records after connectivity recovery; no replacement or rescoring of existing scientific results.',
        'original_attempts_retained': True,
        'concurrency': 'At most 8 workers; both prefetch runs must have ended.'
    })
    print('Prepared retry cases:', len(cases), 'preserved source results:', len(preserved), flush=True)


def run(folder, workers):
    verify()
    assert 1 <= workers <= 8
    assert (OUT / 'source-prefetch-status.json').exists()
    assert (OUT / 'source-extra-prefetch-status.json').exists()
    plan = read_json(folder / 'plan.json')
    assert plan['runner_sha256'] == sha256(Path(__file__))
    assert plan['full_cohort_sha256'] == sha256(OUT / 'source-all.json')
    cohort = read_json(OUT / 'source-all.json')
    for item in cohort['frozen_runner_files']:
        assert sha256(Path(__file__).with_name(item['name'])) == item['sha256']
    for item in cohort['prediction_hashes']:
        assert sha256(OUT / 'evaluation' / (item['id'] + '-prediction.json')) == item['sha256']
    for item in plan['preserved_source_results']:
        assert sha256(OUT / 'source-results' / (item['id'] + '.json')) == item['sha256']
    pending, done = [], []
    for item in plan['cases']:
        ident = item['case']['id']
        archived = folder / 'original-results' / (ident + '.json')
        current = OUT / 'source-results' / (ident + '.json')
        if archived.exists() and current.exists():
            assert sha256(archived) == item['original_failure_sha256']
            done.append(read_json(current))
        else:
            pending.append(item)
    stop = False
    consecutive_failures = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        active = {}
        while pending or active:
            while pending and len(active) < workers and not stop:
                item = pending.pop(0)
                ident = item['case']['id']
                current = OUT / 'source-results' / (ident + '.json')
                archive = folder / 'original-results' / (ident + '.json')
                prior = archive_failure(current, archive, item['original_failure_sha256'])
                assert prior is None
                active[pool.submit(review_with_prefetch, item['case'])] = ident
            if not active:
                break
            finished, _ = wait(active, return_when=FIRST_COMPLETED)
            for f in finished:
                ident = active.pop(f)
                row = f.result()
                done.append(row)
                consecutive_failures = consecutive_failures + 1 if row['status'] == 'transport_failed' else 0
                if consecutive_failures >= 3:
                    stop = True
                print('retry source', len(done), '/', len(plan['cases']), ident, row['status'], row.get('source_review', {}).get('conclusion', {}).get('route'), flush=True)
            write_json(folder / 'progress.json', {
                'updated_at': now(), 'returned': len(done), 'requested': len(plan['cases']),
                'remaining_not_started': len(pending), 'active': len(active),
                'stopped_after_consecutive_transport_failures': stop
            })
    write_json(folder / 'status.json', {
        'updated_at': now(), 'returned': len(done), 'requested': len(plan['cases']),
        'remaining_not_started': len(pending), 'all_jobs_returned': not pending,
        'stopped_after_consecutive_transport_failures': stop,
        'meaning': 'Transport retry status only; incomplete science evidence never passes.'
    })
    if pending:
        raise SystemExit(2)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['prepare', 'run'])
    p.add_argument('--attempt', type=int, required=True)
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    assert 1 <= args.attempt <= 99
    folder = OUT / 'source-retries' / f'attempt-{args.attempt:02d}'
    with run_lock(OUT):
        if args.stage == 'prepare':
            prepare(folder)
        else:
            run(folder, args.workers)
