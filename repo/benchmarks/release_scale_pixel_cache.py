"""Release only verified, finished, reproducible pixel caches when disk is tight.

Receipts, original hashes, source manifests, plots and conclusions are retained.
Never delete light curves, old experiments, tracked data or in-flight products.
"""
from pathlib import Path
import argparse
import fcntl
import gzip
import hashlib
import shutil
import subprocess
from vstar.io import read_json, write_json, sha256, now
from run_scale_validation import ROOT, OUT, CACHE, verify


def check_path(item, root=ROOT, cache=CACHE):
    path = (root / item['path']).resolve()
    if path.parent != cache.resolve() or not path.name.endswith('_tp.fits.gz'):
        raise ValueError('Only this experiment pixel caches may be released')
    if item['uri'] != 'mast:TESS/product/' + path.name[:-3]:
        raise ValueError('URI/cache name mismatch')
    return path


def release(free_bytes):
    verify()
    if free_bytes < 6_000_000_000:
        raise ValueError('Retain at least the existing 6 GB reserve')
    cohort = read_json(OUT / 'source-all.json')
    prefetch = {c['id'] for c in read_json(OUT / 'source-prefetch.json')['cases']}
    tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
    ledger = OUT / 'cache-release'
    ledger.mkdir(exist_ok=True)
    count, size = 0, 0
    for case in cohort['cases']:
        if shutil.disk_usage(CACHE).free >= free_bytes:
            break
        saved = OUT / 'source-results' / (case['id'] + '.json')
        manifest = OUT / 'evaluation' / case['id'] / 'source/source-manifest.json'
        if not saved.exists() or not manifest.exists():
            continue
        if read_json(saved)['status'] not in {'completed', 'incomplete'}:
            continue
        # A queued prefetch must not redownload released products later.
        if case['id'] in prefetch and not (OUT / 'prefetch-results' / (case['id'] + '.json')).exists():
            continue
        for obs in read_json(manifest)['inputs']:
            if shutil.disk_usage(CACHE).free >= free_bytes:
                break
            item = obs.get('pixels')
            if not item:
                continue
            path = check_path(item)
            if str(path.relative_to(ROOT)) in tracked:
                raise ValueError('Refuse to release Git-tracked data')
            if not path.exists():
                continue
            lock_path = CACHE / (path.name[:-3] + '.range.lock')
            with lock_path.open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                receipt_path = CACHE / (path.name[:-3] + '.receipt.json')
                receipt = read_json(receipt_path)
                assert receipt['uri'] == item['uri']
                assert receipt['sha256'] == item['sha256'] == sha256(path)
                with gzip.open(path, 'rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                assert digest == item['raw_sha256'] == receipt['raw_sha256']
                note = ledger / (path.name + '.json')
                if note.exists():
                    raise ValueError('Previous cache release exists; audit before another release')
                record = {
                    'verified_at': now(), 'case_id': case['id'], 'input': item,
                    'compressed_and_original_bytes_verified': True,
                    'source_result_sha256': sha256(saved),
                    'source_manifest_sha256': sha256(manifest),
                    'receipt': receipt,
                    'reason': 'Disk management after completed source job; public original can be restored and checked against these hashes.',
                    'released': False
                }
                write_json(note, record)
                n = path.stat().st_size
                path.unlink()
                record.update(released=True, released_at=now())
                write_json(note, record)
                count += 1
                size += n
    print({'released_products': count, 'released_bytes': size,
           'free_bytes': shutil.disk_usage(CACHE).free, 'requested_free_bytes': free_bytes}, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--free-bytes', type=int, required=True)
    a = p.parse_args()
    release(a.free_bytes)
