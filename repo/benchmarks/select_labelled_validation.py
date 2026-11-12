"""Build a labelled TESS benchmark from independent, visually vetted literature labels.

Selection reads catalogue rows and observing metadata only, never light-curve flux.
"""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import re

from vstar.io import read_json, write_json, sha256, now
from vstar.network import ArchiveClient

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'repo/benchmarks/labelled-validation-v01'
CACHE = ROOT / 'repo/data/labelled-validation-v01'
SEED = 2026111201
POSITIVE_TYPES = {'DSCT', 'GDOR', 'DSCT+GDOR', 'GDOR+DSCT', 'ROTS',
                  'ROT', 'ROTM', 'EA', 'EB', 'EW', 'ELL'}


def catalogue_rows():
    lines = (OUT / 'sources/north-harvard.txt').read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('Name\t'))
    columns = lines[start].split('\t')
    rows = []
    for line in lines[start + 3:]:
        if not line or line.startswith('#'):
            continue
        values = [v.strip() for v in line.split('\t')]
        if len(values) != len(columns):
            raise ValueError('Malformed catalogue row')
        rows.append(dict(zip(columns, values)))
    # Table 5 is the COMPLETE inspected sample, not a variable-only catalogue.
    assert len(rows) == 5923
    assert sum(not r['VType'] for r in rows) == 2898
    assert sum(bool(r['VType']) for r in rows) == 3025
    assert all(not r['f'] and not r['dT'] for r in rows if not r['VType'])
    return rows


def reference_label(row):
    if not row['VType'] and not row['VSX']:
        return 0
    if row['VType'] in POSITIVE_TYPES and row['f'] and .125 <= float(row['f']) <= 20:
        return 1
    return None


def verify_pool():
    pool = read_json(OUT / 'candidate-pool.json')
    assert pool['seed'] == SEED
    assert pool['catalog_sha256'] == sha256(OUT / 'sources/north-harvard.txt')
    assert pool['positive_types'] == sorted(POSITIVE_TYPES)
    rows = catalogue_rows()
    frequencies = Counter(r['Name'] for r in rows)
    blends = {r['Name'] for r in rows if r['Blend']} | {r['Blend'] for r in rows if r['Blend']}
    assert sorted(blends, key=int) == pool['excluded_blend_system_tics']
    old = set(pool['previous_tics'])
    expected = []
    for row in rows:
        if frequencies[row['Name']] != 1 or row['Name'] in old | blends:
            continue
        label = reference_label(row)
        if label is not None:
            expected.append({'tic': row['Name'], 'label': label, 'row': row})
    assert expected == pool['records']
    return pool


def query_batch(ids):
    client = ArchiveClient(CACHE, attempts=2)
    filters = [{'paramName': 'obs_collection', 'values': ['TESS']},
               {'paramName': 'provenance_name', 'values': ['SPOC']},
               {'paramName': 'dataproduct_type', 'values': ['timeseries']},
               {'paramName': 'sequence_number', 'values': [str(i) for i in range(14, 27)]},
               {'paramName': 'target_name', 'values': ids}]
    rows, receipts = client.mast_rows(filters, page_size=5000)
    return {'targets': ids, 'rows': rows, 'receipts': receipts}


def metadata(workers):
    pool = verify_pool()
    ids = sorted([r['tic'] for r in pool['records']], key=int)
    jobs = []
    for i in range(0, len(ids), 100):
        path = OUT / f'metadata/batch-{i // 100:03d}.json'
        batch = ids[i:i + 100]
        if path.exists():
            assert read_json(path)['targets'] == batch
        else:
            jobs.append((path, batch))
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(query_batch, batch): (path, batch) for path, batch in jobs}
        for i, future in enumerate(as_completed(futures), 1):
            path, batch = futures[future]
            try:
                result = future.result()
                write_json(path, result)
                print('metadata', i, '/', len(jobs), path.name, len(result['rows']), flush=True)
            except Exception as exc:
                failure = {'batch': path.name, 'targets': batch, 'error': str(exc), 'at': now()}
                write_json(OUT / 'metadata-failures' / (path.stem + '.json'), failure)
                failures.append(failure)
                print('metadata failed', path.name, str(exc), flush=True)
    if failures:
        raise RuntimeError(f'{len(failures)} metadata batches failed; resume before freezing')


def freeze():
    if (OUT / 'targets.json').exists():
        raise FileExistsError('Frozen targets already exist')
    pool = verify_pool()
    ids = sorted([r['tic'] for r in pool['records']], key=int)
    obs = defaultdict(dict)
    files = []
    for i in range(0, len(ids), 100):
        path = OUT / f'metadata/batch-{i // 100:03d}.json'
        result = read_json(path)
        assert result['targets'] == ids[i:i + 100]
        files.append({'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)})
        for r in result['rows']:
            uri = r.get('dataURL') or ''
            if not re.fullmatch(r'mast:TESS/product/tess\d+-s\d{4}-\d{16}-\d+-s_lc\.fits', uri):
                continue
            tic = str(r['target_name'])
            sector = int(r['sequence_number'])
            assert tic in result['targets'] and 14 <= sector <= 26 and r['provenance_name'] == 'SPOC'
            prior = obs[tic].get(sector)
            if prior is None or uri > prior['dataURL']:
                obs[tic][sector] = r
    eligibility, eligible = [], {0: [], 1: []}
    for row in pool['records']:
        observations = sorted(obs[row['tic']].values(), key=lambda x: (x['t_min'], x['dataURL']))
        good = len(observations) >= 2 and observations[-1]['t_min'] - observations[0]['t_min'] >= 180
        eligibility.append({'tic': row['tic'], 'label': row['label'],
                            'sectors': [int(o['sequence_number']) for o in observations],
                            'two_epochs_180d': good})
        if good:
            eligible[row['label']].append((row, observations))
    write_json(OUT / 'eligibility.json', {'created_at': now(), 'rows': eligibility,
               'eligible_counts': {str(k): len(v) for k, v in eligible.items()}})
    if min(len(v) for v in eligible.values()) < 500:
        raise ValueError('Fewer than 500 eligible objects in a labelled class; do not relabel or duplicate')
    cases = []
    rank = lambda row: hashlib.sha256(f'{SEED}:{row[0]["tic"]}'.encode()).hexdigest()
    for label in [0, 1]:
        for row, observations in sorted(eligible[label], key=rank)[:500]:
            first, last = observations[0], observations[-1]
            cases.append({'id': 'tic-' + row['tic'], 'tic': row['tic'], 'label': label,
                          'reference': row['row'],
                          'label_meaning': 'author_inspected_no_variability_in_cycle2' if label == 0 else 'author_classified_periodic_variable',
                          'inputs': [{'sector': int(o['sequence_number']), 'uri': o['dataURL'],
                                      't_min_mjd': o['t_min'], 't_max_mjd': o['t_max']}
                                     for o in [first, last]]})
    cases.sort(key=lambda c: hashlib.sha256(f'run:{SEED}:{c["tic"]}'.encode()).hexdigest())
    assert len({c['tic'] for c in cases}) == 1000
    assert not {c['tic'] for c in cases} & set(pool['previous_tics'])
    write_json(OUT / 'targets.json', {'created_at': now(), 'seed': SEED,
               'candidate_pool_sha256': sha256(OUT / 'candidate-pool.json'),
               'catalogue_reference': 'Skarka et al. 2022, A&A 666 A142, Table 5',
               'catalogue_doi': '10.26093/cds/vizier.36660142',
               'counts': dict(Counter(c['label'] for c in cases)),
               'metadata_files': files, 'cases': cases})
    # This is the only manifest read by detection workers. No truth labels or
    # reference frequencies are supplied to their acquisition or search calls.
    write_json(OUT / 'blind-inputs.json', {'targets_sha256': sha256(OUT / 'targets.json'),
               'cases': [{k: c[k] for k in ['id', 'tic', 'inputs']} for c in cases]})
    print('Frozen', len(cases), 'objects; eligible classes', {k: len(v) for k, v in eligible.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['metadata', 'freeze'])
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    metadata(args.workers) if args.command == 'metadata' else freeze()
