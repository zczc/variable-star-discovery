"""Post-output catalog positions, independent of the frozen source decisions.

Read only the final FITS blocks to recover released TPF aperture headers. Require
the original download's ETag and size, then compare its WCS with the retained LC.
This supplements the existing maps; it does not rerun or score the detector.
"""
from pathlib import Path
import argparse
import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS
from vstar.io import read_json, write_json, sha256, now

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'repo/benchmarks/scale-validation-v01'


def aperture_header(item):
    pixel = ROOT / item['path']
    receipt_path = pixel.with_name(pixel.name.removesuffix('.gz') + '.receipt.json')
    original = read_json(receipt_path)
    assert original['raw_sha256'] == item['raw_sha256']
    assert original['sha256'] == item['sha256']
    folder = OUT / 'reference-followup/position-headers'
    folder.mkdir(exist_ok=True)
    fragment = folder / (pixel.name.removesuffix('.fits.gz') + '-tail.bin')
    record_path = fragment.with_suffix('.json')
    total = original['raw_bytes']
    start = max(0, total - 20 * 2880)
    expected_range = f'bytes {start}-{total - 1}/{total}'
    if not fragment.exists():
        with requests.get(original['download_url'], headers={
            'Range': f'bytes={start}-{total - 1}',
            'If-Match': original['etag'], 'Accept-Encoding': 'identity',
        }, timeout=(15, 45)) as response:
            response.raise_for_status()
            assert response.status_code == 206
            assert response.headers['Content-Range'] == expected_range
            assert response.headers['ETag'] == original['etag']
            data = response.content
            assert len(data) == total - start
        fragment.write_bytes(data)
        write_json(record_path, {
            'retrieved_at': now(), 'url': original['download_url'],
            'uri': original['uri'], 'etag': original['etag'],
            'content_range': expected_range, 'sha256': sha256(fragment),
            'original_receipt': original,
            'scope': 'Version-checked suffix only, not a newly verified full FITS file.',
        })
    record = read_json(record_path)
    assert record['etag'] == original['etag']
    assert record['content_range'] == expected_range
    assert sha256(fragment) == record['sha256']
    data = fragment.read_bytes()
    for offset in range(0, len(data), 2880):
        if not data[offset:offset + 80].startswith(b'XTENSION='):
            continue
        for end in range(offset, len(data), 80):
            if data[end:end + 8] == b'END     ':
                header = fits.Header.fromstring(data[offset:end + 80].decode('ascii'), sep='')
                if header.get('EXTNAME') == 'APERTURE':
                    return header, fragment, record_path
                break
    raise ValueError('APERTURE header missing from version-checked suffix')


def main(tic, oid):
    ident = 'tic-' + tic
    dest = OUT / 'reference-followup' / (ident + '-catalog-position.json')
    if dest.exists():
        raise FileExistsError(dest)
    source_path = OUT / 'source-results' / (ident + '.json')
    catalog_path = OUT / 'reference-followup' / (ident + '-source-vsx.json')
    source = read_json(source_path)['source_review']
    catalog = read_json(catalog_path)
    assert catalog['receipt']['status'] == 'completed'
    neighbor = next(x for x in catalog['objects'] if str(x['OID']) == oid)
    target = next(c['target'] for c in read_json(OUT / 'targets.json')['cases'] if c['tic'] == tic)
    evidence = [source_path, catalog_path]
    positions = []
    for observation in source['observations']:
        item = observation['input']
        header, fragment, receipt = aperture_header(item['pixels'])
        wcs = WCS(header)
        with fits.open(ROOT / item['path'], memmap=False) as h:
            lc_wcs = WCS(h[2].header)
            assert (header['NAXIS1'], header['NAXIS2']) == (h[2].header['NAXIS1'], h[2].header['NAXIS2'])
        points = np.array([[0., 0.], [header['NAXIS1'] - 1., 0.], [0., header['NAXIS2'] - 1.]])
        assert np.allclose(wcs.all_pix2world(points, 0), lc_wcs.all_pix2world(points, 0), rtol=0, atol=1e-10)
        target_pixel = np.array(wcs.world_to_pixel_values(target['ra_deg'], target['dec_deg']))
        assert np.allclose(target_pixel, observation['pixels']['target_pixel'], rtol=0, atol=1e-8)
        xy = np.array(wcs.world_to_pixel_values(float(neighbor['RA2000']), float(neighbor['Declination2000'])))
        positions.append({
            'sector': observation['sector'], 'vsx_pixel': xy.tolist(),
            'target_pixel': target_pixel.tolist(),
            'distances_to_peak_pixels': [float(np.linalg.norm(xy - p['peak_pixel'])) for p in observation['pixels']['segments']],
            'lc_and_tpf_wcs_agree': True,
            'pixel_input': item['pixels'], 'lightcurve_input': {k: v for k, v in item.items() if k != 'pixels'},
        })
        evidence.extend([fragment, receipt, OUT / 'evaluation' / ident / 'source' / observation['pixels']['plot']])
    result = {
        'created_at': now(), 'tic': tic, 'vsx_reference': neighbor,
        'selected_period_d': source['selected_period_d'],
        'projected_catalog_positions': positions,
        'projection_method': 'WCS from original-version TPF APERTURE header; checked against retained LC WCS. Catalog RA2000/Declination2000 without proper-motion propagation. Peak distances are not localization uncertainties.',
        'evidence': [{'path': str(p.relative_to(OUT)), 'sha256': sha256(p)} for p in evidence],
        'script_sha256': sha256(Path(__file__)),
        'detector_modified': False, 'independent_population_precision_estimate': False,
    }
    write_json(dest, result)
    print(tic, neighbor['Name'], positions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tic', required=True)
    parser.add_argument('--oid', required=True)
    args = parser.parse_args()
    main(args.tic, args.oid)
