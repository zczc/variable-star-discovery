"""Reproduce the archived follow-up; never rewrite the first detection results."""
import argparse
from copy import deepcopy
import gzip
import hashlib
from pathlib import Path

import numpy as np
from astropy.io import fits

from vstar.adjudication import adjudicate
from vstar.io import code_fingerprint, now, read_json, sha256, write_json
from vstar.models import AnalysisConfig
from vstar.photometry import read_lightcurve
from vstar.products import PRODUCTS, review_products, summarize_products
from vstar.screening_v3 import ScreeningConfig, combine_epochs

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'repo/runs/tic-302959739-followup-2026-11-22'


def verify_inputs():
    plan = read_json(RUN / 'plan.json')
    assert code_fingerprint() == plan['detector_fingerprint'], 'Frozen detector changed'
    checked = set()
    records = (plan['preserved_inputs'] + plan['immutable_references']
               + read_json(RUN / 'acquisition.json')['results']
               + read_json(RUN / 'prf-reference/models.json')['files'])
    for item in read_json(RUN / 'source-inputs.json')['inputs']:
        records.extend([item, item['pixels']])
    for item in records:
        path = ROOT / item['path']
        assert sha256(path) == item['sha256'], str(path)
        checked.add(str(path.relative_to(ROOT)))
        if 'raw_sha256' in item:
            with gzip.open(path, 'rb') as handle:
                raw = handle.read()
            assert hashlib.sha256(raw).hexdigest() == item['raw_sha256']
            assert len(raw) == item['raw_bytes']
    return {'checked_files': len(checked), 'detector_fingerprint': code_fingerprint()}


def rerun(out):
    """Blind searches use the same saved parameters and all five unused epochs."""
    out.mkdir(parents=True, exist_ok=False)
    reference = read_json(RUN / 'combined-seven-sectors.json')
    acquisition = read_json(RUN / 'acquisition.json')['results']
    paths = [ROOT / x['path'] for x in acquisition if '_lc.fits' in x['path']]
    row = review_products(paths, out / 'new-periods', identity='TIC 302959739',
                          analysis=AnalysisConfig(**reference['analysis']),
                          config=ScreeningConfig(**reference['screening']))
    assert not row['errors'], row['errors']
    write_json(out / 'new-periods/adjudication.json', adjudicate(row, ROOT))
    combined = deepcopy(row)
    # These two archived epochs are reused, not counted as new observations.
    combined['observations'] = [deepcopy(o) for o in reference['observations']
                                if o['sector'] in (10, 39)] + row['observations']
    cfg = ScreeningConfig(**reference['screening'])
    combined['conclusions'] = {name: combine_epochs(
        [o['products'][name]['result'] for o in combined['observations']], cfg)
        for name in PRODUCTS}
    combined['comparison'] = summarize_products(combined['conclusions'], [], cfg.epoch_period_tolerance)
    write_json(out / 'combined-seven-sectors.json', combined)
    write_json(out / 'combined-adjudication.json', adjudicate(combined, ROOT))


def mask_outliers(values, valid, multiplier=8.):
    center = np.median(values[valid])
    scale = 1.4826 * np.median(abs(values[valid] - center))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('Cannot define the diagnostic MAD mask')
    return valid & (abs(values - center) > multiplier * scale), float(center), float(scale)


def masked_diagnostic(out):
    """Post-hoc transient diagnostic; this does not replace the original failure."""
    out.mkdir(parents=True, exist_ok=False)
    original = read_json(RUN / 'combined-seven-sectors.json')
    item = next(x for x in read_json(RUN / 'acquisition.json')['results']
                if x['sector'] == 36 and '_lc.fits' in x['path'])
    path = ROOT / item['path']
    with fits.open(path, memmap=False) as hdus:
        d = hdus[1].data
        values = np.array(d['PDCSAP_FLUX'], float)
        valid = (np.isfinite(values) & np.isfinite(d['TIME'])
                 & np.isfinite(d['PDCSAP_FLUX_ERR']) & (d['PDCSAP_FLUX_ERR'] > 0)
                 & (d['QUALITY'] == 0))
        excluded, center, scale = mask_outliers(values, valid)
        receipt = {'created_at': now(), 'post_hoc': True, 'original_detection_replaced': False,
                   'source': item, 'rule': 'Absolute PDCSAP deviation > 8 x 1.4826 x MAD; same times removed from both products.',
                   'median_e_per_s': center, 'mad_sigma_e_per_s': scale,
                   'valid_cadences': int(valid.sum()), 'excluded_cadences': int(excluded.sum()),
                   'excluded_btjd': d['TIME'][excluded].astype(float).tolist()}
        write_json(out / 'mask.json', receipt)
        # A clearly marked derived copy. Flux values and original flags are retained.
        d['QUALITY'][excluded] |= 1 << 30
        hdus[0].header['DIAGNOST'] = (True, 'Post-hoc derived data, not original SPOC')
        hdus[0].header.add_history('Diagnostic only: bit 30 marks >8 MAD PDCSAP excursions.')
        derived = out / 'derived-s36-event-masked.fits.gz'
        hdus.writeto(derived, checksum=True)
    row = review_products([derived], out / 'products', identity='TIC 302959739 / post-hoc S36 mask',
                          analysis=AnalysisConfig(**original['analysis']),
                          config=ScreeningConfig(**original['screening']))
    assert not row['errors'], row['errors']
    receipt['derived'] = {'path': str(derived.relative_to(ROOT)), 'sha256': sha256(derived)}
    receipt['results'] = {name: row['observations'][0]['products'][name]['result'] for name in PRODUCTS}
    # Raw cadence peaks are measured relative to each product's full-sector median.
    receipt['raw_peak_relative_to_sector_median'] = {
        name: float(read_lightcurve(path, name + '_FLUX').flux.max()) for name in PRODUCTS}
    write_json(out / 'diagnostic.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify', 'rerun', 'masked-diagnostic'])
    parser.add_argument('--output', type=Path, help='New directory; existing results are never overwritten')
    args = parser.parse_args()
    print(verify_inputs(), flush=True)
    if args.action != 'verify':
        if args.output is None:
            parser.error('--output is required for recomputation')
        (rerun if args.action == 'rerun' else masked_diagnostic)(args.output.resolve())
