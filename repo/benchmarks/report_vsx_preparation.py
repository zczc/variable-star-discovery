"""Rebuild the dated dossier from saved public receipts, without network or detection."""
import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
from html import escape
import io
import json

from vsx_preparation_support import ROOT, OUT, parsed
from vstar.io import read_json, write_json, sha256
from vstar.reports import page

TIC = '302959739'
COMMIT = '9113bbb9de9114ea4ee74b73ddbc6cd9bbcb3411'
PRIOR = ROOT / 'repo/runs/tic-302959739-followup-2026-11-22'


def receipt(name):
    item = read_json(OUT / 'sources' / f'{name}.json')
    if 'returncode' in item:
        assert item['returncode'] == 0, name
    else:
        assert item.get('status_code') == 200, name
    assert item.get('body'), name
    return item


def csv_rows(name):
    return list(csv.DictReader(io.StringIO(receipt(name)['body'])))


def tic_id(value):
    """Normalize integral TIC strings, including decimal/exponent notation; no floats."""
    try:
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or number != number.to_integral_value():
            return None
        return str(int(number))
    except (InvalidOperation, TypeError, ValueError):
        return None


def extract():
    periods, identities, events = [csv_rows(n) for n in
        ('young-flares-periods', 'young-flares-tic', 'young-flares-events')]
    p = [r for r in periods if tic_id(r['Target_ID']) == TIC]
    ids = [r for r in identities if tic_id(r['ID']) == TIC]
    flares = [r for r in events if tic_id(r['Target_ID']) == TIC]
    assert (len(periods), len(identities), len(events)) == (3986, 6824, 26355)
    assert len(p) == len(ids) == 1 and len(flares) == 37
    assert Decimal(p[0]['Good']) == 0
    assert ids[0]['designation'] == '2MASS J09042304-7137155'
    assert abs(float(ids[0]['ra']) - 136.096059766959) < 1e-9
    assert abs(float(ids[0]['dec']) + 71.620960633465) < 1e-9
    code = receipt('young-flares-code-prot')['body']
    quality_line = "tab = tab[tab['Good'] == 1]"
    assert quality_line in code
    paper = parsed('feinstein2024-full')
    assert any('github.com/afeinstein20/young-stellar-flares' in x for x in paper.links)
    works = json.loads(receipt('crossref-flare')['body'])['message']['items']
    publication = next(x for x in works if x['DOI'] == '10.3847/1538-3881/ad4edf')
    fixed = json.loads(receipt('young-flares-commit')['body'])
    assert fixed['sha'] == COMMIT
    history = json.loads(receipt('young-flares-period-history')['body'])[0]
    prior = read_json(PRIOR / 'summary.json')
    result = {
        'as_of': '2026-11-23', 'tic': TIC,
        'publication': {k: publication.get(k) for k in
                        ('title', 'author', 'DOI', 'volume', 'page', 'published', 'container-title')},
        'repository_commit': COMMIT, 'repository_commit_date': fixed['commit']['committer']['date'],
        'period_file_last_change': {'sha': history['sha'], 'date': history['commit']['committer']['date']},
        'source_table_counts': {'periods': len(periods), 'identities': len(identities), 'flares': len(events)},
        'period_quality_values': dict(Counter(r['Good'] for r in periods)),
        'population_count_caveat': 'The saved CSV has 1848 Good=1 rows; the paper states 1847 robust periods. This difference is not reconciled and is not used for the target decision.',
        'identity_row': ids[0], 'period_row': p[0], 'flare_count': len(flares),
        'good_flag_evidence': {'file': 'src/scripts/prot_histograms.py',
                              'line': code.splitlines().index(quality_line) + 1, 'code': quality_line},
        'period_interpretation': 'Public candidate period, outside the authors Good=1 subset; not a reliable-period confirmation.',
        'old_candidate_period_d': prior['prior_period_d'],
        'relative_period_difference': abs(float(p[0]['Prot']) / prior['prior_period_d'] - 1),
        'new_discovery_eligible': False, 'submission_ready': False,
        'reason': '37 prior flare reports assigned to this exact TIC in the paper-linked final catalog.',
        'source_confirmed_by_this_project': False,
        'same_s36_flare_confirmed': False,
        's36_caveat': 'No formal event match: the authors tpeak time convention has not been fully verified. Model peak and highest sampled cadence also differ.'}
    write_json(OUT / 'prior-work.json', result)
    with (OUT / 'published-flare-rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flares[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(flares)
    write_json(OUT / 'candidate-status-update.json', {
        'as_of': '2026-11-23', 'supersedes_status_only': [
            'repo/runs/discovery-followup-2026-11-20/candidates.json',
            'repo/runs/tic-302959739-followup-2026-11-22/summary.json'],
        'historical_results_overwritten': False, 'initial_followup_count': 16,
        'previously_excluded': 14, 'newly_excluded': [TIC], 'total_excluded': 15,
        'remaining_unresolved': [{'tic': '393386173', 'name': 'HD 43737A/B',
                                  'reason': 'Near-equal components separated by about 6.17 arcsec; variable component and novelty unresolved.'}],
        'confirmed_new_discoveries': 0, 'submission_ready_count': 0,
        'formal_submissions': 0, 'target': {'tic': TIC, 'status': 'prior_published_variability',
            'new_discovery_eligible': False, 'submission_ready': False,
            'source_confirmed': False, 'proposed_route': 'Possible literature supplementation after remaining evidence and current VSX checks; no first-discovery claim.'}})
    sky = csv_rows('skymapper-target-photometry')
    masters = csv_rows('skymapper-cone')
    sky_summary = []
    for oid, gaia in [('461085890', '5221973868734158976'), ('461085894', '5221973868731579136')]:
        master = next(r for r in masters if r['object_id'] == oid)
        assert master['gaia_dr3_id1'] == gaia  # Gaia IDs remain exact strings.
        rows = [r for r in sky if r['object_id'] == oid]
        sky_summary.append({'object_id': oid, 'gaia_dr3_id': gaia, 'epochs': len(rows),
                            'filter_counts': dict(Counter(r['filter'] for r in rows)),
                            'master_flags_psf': master['flags_psf'],
                            'epoch_flag_counts': dict(Counter(r['flags'] for r in rows))})
    assert [x['epochs'] for x in sky_summary] == [37, 11]
    write_json(OUT / 'skymapper-assessment.json', {'objects': sky_summary,
        'independent_period_confirmation': False, 'neighbor_excluded': False,
        'caveats': ['Master catalog separates the identities, but single-epoch photometry includes blending flags and large PSF residuals.',
                    'No images downloaded, no period fitted, no bright outlier accepted as a flare.',
                    'FWHM columns are in pixels; target 37 photometric epochs are distinct from the 37 published flare events.']})
    (OUT / 'young-stellar-flares-LICENSE.txt').write_text(receipt('young-flares-license')['body'])
    return result


def build_examples():
    examples = read_json(OUT / 'examples.json')['examples']
    body = '<h1>VSX 公开范例与材料草稿</h1><p>2026-11-23 · 已查到先前耀发报告，TIC 302959739 退出首次变星发现候选。</p>'
    body += '<p>以下是获批条目的公开字段、备注、附件及修订记录，不是完整的私下申请与审核往来。范例图属于原作者。</p>'
    body += '<p><a href="../../../doc/26-vsx-examples-and-draft.md">本轮说明</a> · <a href="tic-302959739-draft.md">英文复核草稿</a> · <a href="new-candidate-template.md">新候选模板</a> · <a href="prior-work.json">查重证据</a> · <a href="candidate-status-update.json">当前候选状态</a></p>'
    for row in examples:
        raw = receipt(f"vsx-example-{row['oid']}")['body']
        text = parsed(f"vsx-example-{row['oid']}").text()
        assert '_images/approved.gif' in raw and row['name'] in text
        for value in row['verify_literals']:
            assert value in text, (row['name'], value)
        body += f'<article><h2><a href="{escape(row["url"])}">{escape(row["name"])}</a></h2>'
        body += f'<p>{escape(row["lesson"])}</p><p>{escape(row["fields"])}</p>'
        body += f'<p>获批修订记录时间：{escape(row["revision_time_utc"])}。不据此推算审核耗时。</p>'
        for fid in row['viewed_documents']:
            image_receipt = read_json(OUT / 'examples' / f'vsx-document-{fid}.json')
            path = ROOT / image_receipt['path']
            assert path.exists() and sha256(path) == image_receipt['sha256']
            body += f'<p>原作者附件 · <a href="{escape(image_receipt["url"])}">VSX 原件</a></p><img loading="lazy" alt="{escape(row["name"])} 原作者证据图" src="examples/{escape(path.name)}">'
        body += '</article>'
    (OUT / 'index.html').write_text(page('VSX 公开范例与材料草稿', body))


def manifest(verify=False):
    path = OUT / 'manifest.json'
    if verify:
        rows = read_json(path)['files']
        for row in rows:
            item = ROOT / row['path']
            assert item.is_file() and sha256(item) == row['sha256'], item
        print(f'Verified {len(rows)} dossier files')
        return
    paths = {p for p in OUT.rglob('*') if p.is_file() and p != path}
    paths.update(ROOT / p for p in ['repo/benchmarks/report_vsx_preparation.py',
        'repo/benchmarks/vsx_preparation_support.py', 'doc/26-vsx-examples-and-draft.md'])
    write_json(path, {'as_of': '2026-11-23', 'files': [
        {'path': str(p.relative_to(ROOT)), 'sha256': sha256(p), 'bytes': p.stat().st_size}
        for p in sorted(paths)]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        manifest(verify=True)
    else:
        result = extract()
        build_examples()
        manifest()
        print(json.dumps({'published_flare_rows': result['flare_count'],
                          'new_discovery_eligible': False, 'submission_ready': False}))
