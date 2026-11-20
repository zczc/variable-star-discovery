"""Build the 2026-11-20 follow-up from archived responses, without network calls."""
from collections import Counter
import csv
from html import escape
import json
from pathlib import Path

from astropy.coordinates import SkyCoord
import astropy.units as u

from followup_discovery_catalogs import ROOT, OUT, INITIAL, parse_asassn, parse_gaia
from vstar.io import now, read_json, write_json, sha256
from vstar.reports import page


def tap_rows(receipt):
    if receipt.get('http_status') != 200:
        raise ValueError('TAP transport incomplete')
    body = json.loads(receipt.get('raw_response', receipt.get('body', '')))
    if not isinstance(body.get('metadata'), list) or not isinstance(body.get('data'), list):
        raise ValueError('TAP metadata/data missing')
    keys = [x['name'] for x in body['metadata']]
    if any(len(row) != len(keys) for row in body['data']):
        raise ValueError('TAP row width mismatch')
    return [dict(zip(keys, row)) for row in body['data']]


def vizier_rows(receipt, table):
    body = receipt.get('body', '')
    if receipt.get('http_status') != 200 or '#Name: ' + table + '\n' not in body:
        raise ValueError('Requested VizieR table was not returned')
    if any(line.startswith('#') and ('Error=' in line or 'QUERY_STATUS=OVERFLOW' in line)
           for line in body.splitlines()):
        raise ValueError('VizieR error/overflow is not an empty result')
    lines = [line for line in body.splitlines() if line.strip() and not line.startswith('#')]
    if len(lines) < 3 or 'TIC' not in lines[0].split('\t'):
        raise ValueError('VizieR TIC header missing')
    rows = list(csv.DictReader(lines[3:], fieldnames=lines[0].split('\t'), delimiter='\t'))
    return [{k: v.strip() for k, v in row.items()} for row in rows]


def normalized_tic(value):
    # Some public files encode TICs in scientific notation. TICs fit exactly in float;
    # never apply this conversion to Gaia source IDs.
    numeric = float(value)
    if not numeric.is_integer() or not 0 < numeric < 2**53:
        raise ValueError('Invalid TIC identifier')
    return str(int(numeric))


def build():
    plan = read_json(OUT / 'plan.json')
    for item in plan['inputs']:
        assert sha256(ROOT / item['path']) == item['sha256']
    cases = plan['cases']
    wanted = {case['tic'] for case in cases}
    control = read_json(OUT / 'asassn/control-asassn-102648.json')
    assert control['http_status'] == 200
    control_rows = parse_asassn(control['raw_response'])['rows']
    assert any(r['ASAS-SN Name'] == 'ASASSN-V J102648.32+690405.9'
               and float(r['Distance from Search (arcsec)']) < 3 for r in control_rows)
    published = {tic: [] for tic in wanted}
    for name in ('table1', 'table2', 'table3'):
        path = OUT / 'literature' / ('fetherolf-' + name + '.json')
        receipt = read_json(path)
        rows = vizier_rows(receipt, 'J/ApJS/268/4/' + name)
        controls = set(receipt['params']['TIC'].split(',')) - wanted
        assert len(controls) == 1 and controls <= {r['TIC'] for r in rows}
        assert all(r['TIC'] in wanted | controls for r in rows)
        assert len(rows) < int(receipt['params']['-out.max'])
        for row in rows:
            if row['TIC'] in wanted:
                published[row['TIC']].append({'table': name, 'row': row,
                    'receipt_path': str(path.relative_to(ROOT)), 'receipt_sha256': sha256(path)})
    write_json(OUT / 'fetherolf-matches.json', {'created_at': now(),
        'doi': '10.3847/1538-4365/acdee5', 'matching_rule': 'Exact TIC in all three published variable-star tables, including moderate-confidence reports.',
        'positive_controls': 'One separately known published TIC was found in each requested table.',
        'matches': {k: v for k, v in published.items() if v}})
    tic_receipt = read_json(OUT / 'tic-identities.json')
    assert tic_receipt['status'] == 'completed'
    identities = {str(x['ID']): x for x in tic_receipt['rows']}
    mapping = read_json(OUT / 'gaia-dr2-dr3-identities.json')
    assert mapping['status'] == 'completed'
    simbad = tap_rows(read_json(OUT / 'literature/simbad-identities.json'))
    alltypes = {r['oidref']: r['otypes'] for r in tap_rows(read_json(OUT / 'literature/simbad-alltypes.json'))}
    refs = tap_rows(read_json(OUT / 'literature/simbad-references.json'))
    rows = []
    for case in cases:
        tic = case['tic']
        ident = identities[tic]
        aliases = {'TIC ' + tic, 'Gaia DR2 ' + ident['GAIA'], '2MASS J' + ident['TWOMASS']}
        matches = [r for r in simbad if r['id'] in aliases]
        oids = {r['oid'] for r in matches}
        assert len(oids) == 1, (tic, oids)
        oid = next(iter(oids))
        gaia = read_json(OUT / 'gaia' / (case['id'] + '.json'))
        assert gaia['status'] == 'completed'
        parse_gaia(gaia['raw_response'])
        dr3_ids = {r['dr3_source_id'] for r in mapping['rows'] if r['dr2_source_id'] == ident['GAIA']}
        targets = [r for r in gaia['rows'] if r['source_id'] in dr3_ids]
        assert targets, tic
        variable_records = [r for r in targets if r['phot_variable_flag'] == 'VARIABLE' or r['best_class_name']]
        asassn_path = OUT / 'asassn' / (case['id'] + '.json')
        asassn_raw = read_json(asassn_path)
        assert asassn_raw['http_status'] == 200
        asassn = parse_asassn(asassn_raw['raw_response'])
        assert not asassn['pagination_present'], tic
        target_pos = SkyCoord(case['target']['ra_deg'], case['target']['dec_deg'], unit='deg')
        for obj in asassn['rows']:
            obj['computed_separation_arcsec'] = float(target_pos.separation(SkyCoord(
                float(obj['Right Ascension']), float(obj['Declination']), unit='deg')).to_value(u.arcsec))
        asassn.update(source_path=str(asassn_path.relative_to(ROOT)), source_sha256=sha256(asassn_path),
                      parsed_at=now(), status='completed',
                      note='Offline reparse of preserved HTTP 200 responses. Original parser errors are retained. Server-returned neighbors beyond the requested radius remain labeled with computed distances.')
        write_json(OUT / 'asassn-parsed' / (case['id'] + '.json'), asassn)
        asassn_near = [x for x in asassn['rows'] if x['computed_separation_arcsec'] <= 3]
        prior = []
        if published[tic]:
            prior.append('Fetherolf 2023')
        if variable_records:
            prior.append('Gaia DR3 variability')
        if asassn_near:
            prior.append('ASAS-SN near-position record; identity needs review')
        l8_path = OUT / 'tess-l8' / (case['id'] + '.json')
        l8 = read_json(l8_path)
        assert l8['http_status'] == 200
        l8_data = json.loads(l8['body'])
        assert normalized_tic(l8_data['tic']) == tic
        # TESS-L8 processes nearly all quality-passing light curves: membership is not a variable label.
        write_json(OUT / 'tess-l8-parsed' / (case['id'] + '.json'), {
            'source_path': str(l8_path.relative_to(ROOT)), 'source_sha256': sha256(l8_path),
            'tic': tic, 'status': 'completed', 'repeat_summary': l8_data['repeat_summary'],
            'interpretation': 'Processed light-curve membership only; no target-specific published variability designation established.'})
        row = {'tic': tic, 'period_d': case['selected_period_d'], 'simbad_name': matches[0]['main_id'],
            'simbad_oid': oid, 'simbad_alltypes': alltypes[oid],
            'simbad_references': [r for r in refs if r['oidref'] == oid],
            'tic_gaia_dr2_id': ident['GAIA'], 'gaia_dr3_mapped_ids': sorted(dr3_ids),
            'gaia_target_records': targets, 'gaia_cone_records': gaia['rows'],
            'asassn_neighbors': asassn['rows'], 'prior_variability_sources': prior,
            'fetherolf_matches': published[tic],
            'route': 'prior_published_variability' if prior else 'candidate_needs_further_review',
            'novelty_confirmed': False, 'submission_ready': False}
        rows.append(row)
    result = {'created_at': now(), 'counts': dict(Counter(x['route'] for x in rows)),
              'rows': rows, 'coverage': {'TIC': 16, 'Gaia_DR3': 16, 'ASAS_SN': 16,
              'SIMBAD_IDIA_identities_and_reference_lists': 16, 'Fetherolf_2023_three_tables': 16},
              'limitations': ['SIMBAD reference lists are not an exhaustive literature search; only selected full texts examined.',
                'Gaia NOT_AVAILABLE does not establish constant brightness.',
                'No additional TESS epochs or precision source localization performed in this follow-up.',
                'SIMBAD mirror data may lag ingestion at the unavailable main service.']}
    write_json(OUT / 'summary.json', result)
    candidates = [r for r in rows if not r['prior_variability_sources']]
    write_json(OUT / 'candidates.json', {'created_at': now(), 'candidates': candidates})
    with (OUT / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['tic', 'simbad_name', 'period_d', 'prior_variability_sources', 'route'], lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '; '.join(row[k]) if isinstance(row[k], list) else row[k] for k in writer.fieldnames})
    body = '<h1>候选查重更新 · 2026-11-20</h1><p>16 个初筛对象中，14 个已有 Fetherolf 2023 变光记录，其中 1 个也有 Gaia DR3 变光分类。当前保留 2 个待查对象。</p>'
    body += '<p>已完成 TIC、Gaia DR3、ASAS-SN、SIMBAD 备用站身份与文献清单查询，以及 Fetherolf 2023 三份变量表的逐 TIC 比对。目录无匹配不能证明新颖性。</p>'
    body += '<table><tr><th>TIC</th><th>SIMBAD 名称</th><th>暂定周期／天</th><th>已有变光报告</th></tr>'
    for row in rows:
        body += '<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in [row['tic'], row['simbad_name'], f"{row['period_d']:.8f}", '; '.join(row['prior_variability_sources']) or '未在本轮完成的查询中找到']) + '</tr>'
    body += '</table><h2>剩余对象</h2><p>TIC 302959739：约 0.437677 天重复变化，仍须检查约 5.09 角秒近邻以及文献。TIC 393386173（HD 43737A）：约 0.051251 天弱变化，约 6.17 角秒外有几乎同亮的 HD 43737B，来源归属待解。</p>'
    for row in candidates:
        tic = row['tic']
        body += f'<p>TIC {tic}：<a href="review/tic-{tic}-period.jpg">两时段光变</a> · <a href="review/tic-{tic}-source.jpg">来源图</a></p>'
    body += '<p><a href="summary.csv">处理清单 CSV</a> · <a href="summary.json">完整证据与局限</a> · <a href="fetherolf-matches.json">14 个论文匹配</a></p>'
    (OUT / 'index.html').write_text(page('候选查重更新', body))
    print(result['counts'])


if __name__ == '__main__':
    build()
