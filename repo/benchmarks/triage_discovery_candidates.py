"""Start discovery triage from preserved unlabelled detections; never alter the baseline."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
import argparse
import csv
import json
import time

import astropy.units as u
from astropy.coordinates import SkyCoord
import requests

from vstar.io import now, read_json, sha256, write_json
from vstar.reports import page

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / 'repo/benchmarks/scale-validation-v01'
OUT = ROOT / 'repo/runs/discovery-triage-2026-11-18'


def vsx_objects(body):
    if not isinstance(body, dict) or 'VSXObjects' not in body:
        raise ValueError('Missing VSXObjects: do not interpret as an empty catalogue result')
    block = body['VSXObjects']
    if isinstance(block, dict):
        if 'VSXObject' not in block:
            raise ValueError('Unrecognized VSX response object')
        block = block['VSXObject']
    records = [block] if isinstance(block, dict) else block
    if not isinstance(records, list):
        raise ValueError('Unrecognized VSX list')
    return records


def prepare():
    path = OUT / 'selection.json'
    if path.exists():
        return read_json(path)
    summary = read_json(OLD / 'summary.json')
    targets = {r['id']: r for r in read_json(OLD / 'targets.json')['cases']}
    records = []
    for row in summary['rows']:
        if row['group'] == 'catalog_eb' or row['selected_period_d'] is None:
            continue
        ident = row['id']
        records.append(dict(row, target=targets[ident]['target'],
            priority_catalog_check=row['source_route'] == 'manual_target_review',
            observations=targets[ident]['inputs'],
            old_prediction_sha256=sha256(OLD / 'evaluation' / (ident + '-prediction.json')),
            old_source_sha256=sha256(OLD / 'source-results' / (ident + '.json'))))
    result = {'created_at': now(), 'authorization_date': '2026-11-18',
        'purpose': 'Discovery candidate triage, authorized after the labelled baseline; no discovery claims or external submissions.',
        'selection': 'All non-catalog-EB objects with a preserved selected period. Initial catalogue checks cover all with manual_target_review source route.',
        'vsx_cone_radius_deg': .04, 'tight_position_threshold_arcsec': 3.,
        'identity_caveat': 'A position within 3 arcsec is a provisional crossmatch, not an identification proof. All neighbors and proper motion remain available for review.',
        'reference_files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha256(p)}
                            for p in (OLD / 'targets.json', OLD / 'summary.json')],
        'cases': records}
    write_json(path, result)
    return result


def query_vsx(case):
    path = OUT / 'vsx' / (case['id'] + '.json')
    if path.exists():
        return read_json(path)
    coords = case['target']
    params = {'view': 'api.list', 'ra': coords['ra_deg'], 'dec': coords['dec_deg'],
              'radius': .04, 'format': 'json'}
    receipt = {'tic': case['tic'], 'checked_at': now(), 'service': 'VSX live API',
               'endpoint': 'https://vsx.aavso.org/index.php', 'query': params, 'attempts': []}
    for attempt in range(2):
        try:
            response = requests.get(receipt['endpoint'], params=params, timeout=(8, 30),
                                    headers={'User-Agent': 'variable-star-discovery public-research'})
            receipt.update(url=response.url, http_status=response.status_code)
            response.raise_for_status()
            body = response.json()
            records = vsx_objects(body)
            target = SkyCoord(coords['ra_deg'], coords['dec_deg'], unit='deg')
            matches = []
            for record in records:
                point = SkyCoord(float(record['RA2000']), float(record['Declination2000']), unit='deg')
                matches.append(dict(record, separation_arcsec=float(target.separation(point).to_value(u.arcsec))))
            receipt.update(status='completed', raw_response=body,
                           objects=sorted(matches, key=lambda r: r['separation_arcsec']))
            break
        except (requests.RequestException, ValueError, KeyError) as exc:
            receipt['attempts'].append({'attempt': attempt + 1, 'error': str(exc)})
            receipt['status'] = 'failed'
            if attempt == 0:
                time.sleep(1)
    write_json(path, receipt)
    print(case['tic'], receipt['status'], len(receipt.get('objects', [])), flush=True)
    return receipt


def report(selection):
    for item in selection['reference_files']:
        assert sha256(ROOT / item['path']) == item['sha256']
    literature_path = ROOT / 'repo/benchmarks/labelled-validation-v01/sources/north-harvard.txt'
    lines = [line for line in literature_path.read_text().splitlines() if line.strip() and not line.startswith('#')]
    literature = [{k: v.strip() for k, v in row.items()} for row in
                  csv.DictReader(lines[3:], fieldnames=lines[0].split('\t'), delimiter='\t')]
    assert len(literature) == 5923
    published = {r['Name']: r for r in literature if r['VType']}
    local_matches = {c['tic']: published[c['tic']] for c in selection['cases'] if c['tic'] in published}
    write_json(OUT / 'literature-matches.json', {
        'checked_at': now(), 'source': 'Skarka et al. 2022 complete Table 5',
        'doi': '10.1051/0004-6361/202244037', 'source_rows': 5923,
        'source_path': str(literature_path.relative_to(ROOT)), 'source_sha256': sha256(literature_path),
        'matching_rule': 'Exact TIC identifier and nonempty published variability type; candidate or uncertain types also count as prior reports.',
        'matches': local_matches})
    rows = []
    for case in selection['cases']:
        ident = case['id']
        assert sha256(OLD / 'evaluation' / (ident + '-prediction.json')) == case['old_prediction_sha256']
        assert sha256(OLD / 'source-results' / (ident + '.json')) == case['old_source_sha256']
        query_path = OUT / 'vsx' / (ident + '.json')
        query = read_json(query_path) if query_path.exists() else {'status': 'not_requested'}
        near = [r for r in query.get('objects', []) if r['separation_arcsec'] <= 3]
        if not case['priority_catalog_check']:
            route = 'source_evidence_not_ready'
        elif query['status'] != 'completed':
            route = 'catalog_query_incomplete'
        elif near:
            route = 'prior_vsx_record_near_target'
        elif case['tic'] in published:
            route = 'prior_published_variability_record'
        else:
            route = 'candidate_needs_catalog_and_identity_followup'
        prediction = read_json(OLD / 'evaluation' / (ident + '-prediction.json'))
        gains = []
        for product in prediction['product_conclusions'].values():
            groups = [g for g in product.get('supported_period_groups', [])
                      if abs(g['period_d'] / case['selected_period_d'] - 1) <= .01]
            gains.append(max(g['gain'] for g in groups) if groups else 0.)
        rows.append({'tic': case['tic'], 'id': ident, 'group': case['group'],
            'period_d': case['selected_period_d'], 'source_route': case['source_route'],
            'vsx_status': query['status'], 'near_vsx_count': len(near),
            'near_vsx_names': '; '.join(r['Name'] for r in near),
            'near_vsx_categories': '; '.join(r.get('Category', '') for r in near),
            'near_vsx_types': '; '.join(r.get('VariabilityType', '') for r in near),
            'near_vsx_periods': '; '.join(r.get('Period', '') for r in near),
            'published_type': published.get(case['tic'], {}).get('VType', ''),
            'review_priority_score': min(gains),
            'nearest_vsx_separation_arcsec': query.get('objects', [{}])[0].get('separation_arcsec') if query.get('objects') else None,
            'route': route, 'novelty_confirmed': False, 'submission_ready': False})
    summary = {'generated_at': now(), 'selection_sha256': sha256(OUT / 'selection.json'),
               'counts': dict(Counter(r['route'] for r in rows)), 'rows': rows,
               'catalog_coverage': 'Live VSX neighborhood queries and exact-TIC checks against the full Skarka 2022 Table 5. Other catalogues and broader literature searches remain incomplete.',
               'meaning': 'Initial triage only. A VSX no-match is neither proof of novelty nor a negative variability label.'}
    write_json(OUT / 'summary.json', summary)
    candidates = sorted([r for r in rows if r['route'] == 'candidate_needs_catalog_and_identity_followup'],
                        key=lambda r: (-r['review_priority_score'], int(r['tic'])))
    write_json(OUT / 'candidates.json', {'created_at': now(),
        'ranking': 'Descending minimum, across SAP/PDCSAP, of saved supported-group template gain at the selected period. Review ordering only, not probability or new detection threshold.',
        'candidates': candidates})
    with (OUT / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    body = '<h1>新候选初筛 · 2026-11-18</h1><p>复用此前未标注与邻星风险组中选出周期的 41 个对象；优先对来源位置获支持的 24 个做当前 VSX 查重。已知标签测试及原算法结果保持不变。</p>'
    body += '<p>3 角秒内的 VSX 记录先作为位置匹配保留，仍须核对别名、自行和近邻。没有近距离记录的对象继续查其他目录和文献；这里没有确认新发现，也没有提交 VSX。</p>'
    body += '<p>本轮另按 TIC 逐一比对 Skarka 2022 完整论文表，非空变光类型均作为已有发表线索；无变光记录不被当作新发现证明。</p>'
    route_labels = {'source_evidence_not_ready': '来源证据待补',
        'prior_vsx_record_near_target': '已有 VSX 近位置记录',
        'prior_published_variability_record': '已有论文变光记录',
        'candidate_needs_catalog_and_identity_followup': '待进一步查重的候选',
        'catalog_query_incomplete': '目录查询未完成'}
    source_labels = {'manual_target_review': '目标位置获支持', 'analysis_failed': '覆盖或计算未完成',
                     'source_evidence_required': '来源证据不足', 'exclude_signal_from_target': '来源程序建议排除'}
    body += '<p>当前初筛状态：' + '；'.join(route_labels[k] + ' ' + str(v) + ' 个' for k, v in summary['counts'].items()) + '。</p>'
    body += '<h2>待查候选的复核顺序</h2><p>先看两种测光产品中重复性较强的对象；这项排序不是发现概率。其他巡天目录、文献、邻星身份与最终周期仍需逐一检查。</p><ol>'
    for candidate in candidates:
        body += '<li>TIC ' + candidate['tic'] + '，暂定周期 ' + f"{candidate['period_d']:.8f}" + ' 天。</li>'
    body += '</ol><p><a href="candidates.json">候选名单与排序依据</a> · <a href="literature-matches.json">已有论文匹配</a></p>'
    body += '<p>SIMBAD 查询预检出现接口错误、超时与域名解析失败；ASAS-SN 的 VizieR 表名预检未通过，后续目录元数据与 Gaia 预检超时。这些均未记为无匹配。其他巡天与更广泛论文查重尚未完成。</p>'
    if (OUT / 'review/visual-notes.json').exists():
        body += '<h2>前三个对象的初步看图</h2>'
        for note in read_json(OUT / 'review/visual-notes.json')['records']:
            body += '<p><strong>TIC ' + note['tic'] + '</strong>：' + escape(note['finding']) + '</p>'
            body += '<p><a href="review/tic-' + note['tic'] + '-period.jpg">两时段光变图</a> · <a href="review/tic-' + note['tic'] + '-source.jpg">两时段来源图</a></p>'
    body += '<p><a href="summary.csv">CSV</a> · <a href="summary.json">JSON</a> · <a href="selection.json">选样与原结果校验</a></p>'
    body += '<table><tr><th>TIC</th><th>候选周期／天</th><th>来源结果</th><th>VSX 近距离记录</th><th>初筛状态</th></tr>'
    for row in rows:
        href = '../../benchmarks/scale-validation-v01/evaluation/' + row['id'] + '/index.html'
        body += '<tr><td><a href="' + href + '">' + row['tic'] + '</a></td>'
        values = (f"{row['period_d']:.8f}", source_labels.get(row['source_route'], row['source_route']),
                  row['near_vsx_names'] or ('Skarka 2022：' + row['published_type'] if row['published_type'] else '尚未找到'), route_labels[row['route']])
        body += ''.join('<td>' + escape(str(value)) + '</td>' for value in values) + '</tr>'
    body += '</table>'
    (OUT / 'index.html').write_text(page('新候选初筛', body))
    print(json.dumps(summary['counts'], ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    selection = prepare()
    if not args.report_only:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(query_vsx, [c for c in selection['cases'] if c['priority_catalog_check']]))
    report(selection)
