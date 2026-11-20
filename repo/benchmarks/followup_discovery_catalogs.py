"""Read-only Gaia/ASAS-SN follow-up; preserve the original discovery triage."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from html.parser import HTMLParser
import io
from pathlib import Path

from astropy.coordinates import SkyCoord
import astropy.units as u
import requests

from vstar.io import now, read_json, sha256, write_json

ROOT = Path(__file__).resolve().parents[2]
INITIAL = ROOT / 'repo/runs/discovery-triage-2026-11-18'
OUT = ROOT / 'repo/runs/discovery-followup-2026-11-20'


class SearchTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ('tr', 'thead'):
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []
        elif tag == 'a' and self.row is not None:
            self.links.extend(v for k, v in attrs if k == 'href' and v.startswith('/variables/'))

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif tag in ('tr', 'thead') and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def parse_asassn(body):
    table = SearchTable()
    table.feed(body)
    expected = ['ASAS-SN Name', 'Other Names', 'Right Ascension', 'Declination',
                'Distance from Search (arcsec)', 'Mean VMag', 'Amplitude', 'Period', 'Type']
    if not table.rows or table.rows[0] != expected:
        raise ValueError('Missing ASAS-SN results table; not an empty result')
    if len(table.rows) == 1 and 'No Variables found' not in body:
        raise ValueError('Empty table without explicit no-results confirmation')
    if any(len(r) != len(expected) for r in table.rows[1:]):
        raise ValueError('Unexpected ASAS-SN table columns')
    return {'rows': [dict(zip(expected, row)) for row in table.rows[1:]],
            'detail_links': table.links,
            'pagination_present': 'page-item next disabled' not in body}


def parse_gaia(body):
    reader = csv.DictReader(io.StringIO(body))
    required = {'source_id', 'ra', 'dec', 'pmra', 'pmdec', 'phot_variable_flag', 'best_class_name'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Missing Gaia CSV columns; not an empty result')
    rows = list(reader)
    if len(rows) >= 1000:
        raise ValueError('Gaia result reached row limit')
    for row in rows:
        int(row['source_id'])  # Keep the original string: source IDs exceed float precision.
        float(row['ra']); float(row['dec'])
    return {'rows': rows}


def query(case, service):
    path = OUT / service / (case['id'] + '.json')
    if path.exists():
        return read_json(path)
    ra, dec = case['target']['ra_deg'], case['target']['dec_deg']
    if service == 'gaia':
        endpoint = 'https://gea.esac.esa.int/tap-server/tap/sync'
        sql = f'''SELECT TOP 1000 g.source_id,g.ref_epoch,g.ra,g.dec,g.pmra,g.pmdec,
            g.phot_g_mean_mag,g.phot_variable_flag,g.ruwe,
            c.best_class_name,c.best_class_score,c.classifier_name,
            s.num_selected_g_fov,s.trimmed_range_mag_g_fov,
            s.in_vari_eclipsing_binary,s.in_vari_rotation_modulation,s.in_vari_ms_oscillator
            FROM gaiadr3.gaia_source AS g
            LEFT OUTER JOIN gaiadr3.vari_classifier_result AS c ON g.source_id=c.source_id
            LEFT OUTER JOIN gaiadr3.vari_summary AS s ON g.source_id=s.source_id
            WHERE 1=CONTAINS(POINT('ICRS',g.ra,g.dec),CIRCLE('ICRS',{ra},{dec},0.002777777778))'''
        params = {'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'QUERY': sql}
        parser = parse_gaia
    else:
        endpoint = 'https://asas-sn.osu.edu/variables'
        params = {'ra': ra, 'dec': dec, 'radius': 2.4, 'show_non_periodic': 'on',
                  'show_without_class': 'on', 'sort_by': 'distance', 'sort_order': 'asc'}
        parser = parse_asassn
    result = {'checked_at': now(), 'tic': case['tic'], 'service': service,
              'endpoint': endpoint, 'params': params, 'status': 'failed'}
    try:
        response = requests.get(endpoint, params=params, timeout=(10, 45))
        result.update(http_status=response.status_code, url=response.url, raw_response=response.text)
        response.raise_for_status()
        result.update(parser(response.text))
        if service == 'gaia':
            point = SkyCoord(ra, dec, unit='deg')
            for row in result['rows']:
                row['separation_arcsec'] = float(point.separation(
                    SkyCoord(float(row['ra']), float(row['dec']), unit='deg')).to_value(u.arcsec))
            result['rows'].sort(key=lambda x: x['separation_arcsec'])
        result['status'] = 'completed'
    except (requests.RequestException, ValueError, KeyError) as exc:
        result['error'] = str(exc)
    write_json(path, result)
    print(case['tic'], service, result['status'], len(result.get('rows', [])), flush=True)
    return result


def prepare():
    path = OUT / 'plan.json'
    if path.exists():
        return read_json(path)
    candidates = read_json(INITIAL / 'candidates.json')['candidates']
    initial = {r['tic']: r for r in read_json(INITIAL / 'selection.json')['cases']}
    plan = {'created_at': now(), 'purpose': 'Catalogue follow-up of all 16 initial candidates.',
            'inputs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha256(p)}
                       for p in (INITIAL / 'candidates.json', INITIAL / 'selection.json')],
            'gaia_radius_arcsec': 10, 'asassn_radius_arcsec': 144,
            'position_note': 'Nearby records require TIC identity/proper-motion confirmation; Gaia NOT_AVAILABLE is not proof of constant brightness.',
            'cases': [initial[r['tic']] for r in candidates]}
    write_json(path, plan)
    return plan


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--service', choices=['gaia', 'asassn', 'both'], default='both')
    args = ap.parse_args()
    plan = prepare()
    for source in plan['inputs']:
        assert sha256(ROOT / source['path']) == source['sha256']
    jobs = [(c, s) for c in plan['cases'] for s in ('gaia', 'asassn')
            if args.service in ('both', s)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda job: query(*job), jobs))
