"""Seal the first labelled run and describe saved decisions without rerunning science."""
import argparse
from collections import Counter
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from vstar.io import now, read_json, sha256, write_json
from vstar.reports import page
from run_labelled_validation import ROOT, OUT, verify

REVIEW = OUT / 'baseline-review'
MANIFEST = OUT / 'baseline-manifest.json'
PRODUCTS = ('SAP', 'PDCSAP')


def seal_or_verify(create=False):
    if not MANIFEST.exists():
        if not create:
            raise FileNotFoundError(MANIFEST)
        verify()
        files = {ROOT / f['path'] for f in read_json(OUT / 'protocol.json')['frozen_files']}
        for directory in ('evaluation', 'acquisition'):
            files.update(p for p in (OUT / directory).rglob('*') if p.is_file())
        files.update(OUT / p for p in ('protocol.json', 'summary.json', 'summary.csv',
                                      'disagreements.json', 'integrity-audit.json', 'run-status.json', 'index.html'))
        write_json(MANIFEST, {
            'sealed_at': now(), 'baseline': 'labelled-validation-v01',
            'pre_run_commit': '9bb841b4', 'science': 'unchanged v4',
            'meaning': 'First-run inputs, code and results. Post-result review is separate; no labels or predictions changed.',
            'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha256(p)} for p in sorted(files)],
        })
    manifest = read_json(MANIFEST)
    for item in manifest['files']:
        if sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Baseline changed: ' + item['path'])
    print(f"Baseline verified: {len(manifest['files'])} files")
    return manifest


def diagnostic_record(row):
    folder = OUT / 'evaluation' / row['id']
    prediction = read_json(OUT / 'evaluation' / (row['id'] + '-prediction.json'))
    case = read_json(folder / 'period/case.json')
    record = dict(row, final_status=prediction['decision']['status'],
                  conclusions=prediction['product_conclusions'], epochs=[])
    for obs in case['observations']:
        epoch = {'sector': obs['sector'], 'plot': f"evaluation/{row['id']}/period/{obs['plot']}",
                 'plot_sha256': obs['plot_sha256'], 'products': {}}
        for name in PRODUCTS:
            result = obs['products'][name]['result']
            epoch['products'][name] = {
                k: result.get(k) for k in ('periodic_detected', 'period_status', 'photometric_period_d')}
            epoch['products'][name]['top_candidates'] = [
                {k: c[k] for k in ('period_d', 'gain', 'qualifies')} for c in result['candidates'][:3]]
        record['epochs'].append(epoch)
    return record


def fn_path(record):
    decisions = [record['conclusions'][p]['decision'] for p in PRODUCTS]
    if decisions == ['not_repeated_in_all_epochs'] * 2:
        return 'both_products_missing_a_qualified_epoch'
    if decisions == ['competing_periods'] * 2:
        return 'both_products_no_matching_cross_epoch_period'
    if set(decisions) == {'not_repeated_in_all_epochs', 'competing_periods'}:
        return 'mixed_missing_epoch_and_period_mismatch'
    return 'other'


def make_diagnostics():
    summary = read_json(OUT / 'summary.json')
    targets = {c['id']: c for c in read_json(OUT / 'targets.json')['cases']}
    rows = summary['rows']
    assert summary['status_counts'] == {'completed': 1000}
    errors = [diagnostic_record(r) for r in rows if r['binary_outcome'] in ('fp', 'fn')]
    for record in errors:
        if record['binary_outcome'] == 'fn':
            record['decision_path'] = fn_path(record)
    missed = [r for r in errors if r['binary_outcome'] == 'fn']
    representative_ids = []
    for kind in ('GDOR', 'ROTS', 'EA'):
        choices = [r for r in missed if r['reference_type'] == kind]
        representative_ids.append(max(choices, key=lambda r: (
            float(targets[r['id']]['reference']['dT']), r['tic']))['id'])
    half = [diagnostic_record(r) for r in rows if r['selected_to_reference_cycle'] == 'half_catalog_period']
    support = Counter()
    final_states = Counter()
    for row in rows:
        prediction = read_json(OUT / 'evaluation' / (row['id'] + '-prediction.json'))
        if row['repeated_signal']:
            pattern = '+'.join(p for p in PRODUCTS if prediction['product_conclusions'][p]['periodic_detected'])
            support[(row['label'], pattern)] += 1
        if row['repeated_signal'] and row['selected_period_d'] is None:
            final_states[(row['label'], prediction['decision']['status'])] += 1
    result = {
        'generated_at': now(), 'baseline_manifest_sha256': sha256(MANIFEST),
        'summary_sha256': sha256(OUT / 'summary.json'), 'post_result_diagnostic_only': True,
        'labels_and_predictions_unchanged': True,
        'primary': summary['primary_repeated_signal'], 'strict': summary['secondary_selected_period'],
        'by_reference_type': summary['by_reference_type'],
        'period_relations': summary['period_comparison_on_selected_positives'],
        'false_negative_decision_paths': dict(Counter(r['decision_path'] for r in missed)),
        'support_patterns': [{'label': label, 'products': products, 'count': count}
                             for (label, products), count in sorted(support.items())],
        'detected_but_abstained': [{'label': label, 'status': status, 'count': count}
                                 for (label, status), count in sorted(final_states.items())],
        'representative_selection': 'Post-result examples: maximum published dT within missed GDOR, ROTS and EA; all false positives and all half-cycle selections. Not a random audit.',
        'representative_false_negative_ids': representative_ids,
        'errors': errors, 'half_cycle_selections': half,
        'strict_zero_false_positive_one_sided_95_upper': 1 - .05 ** (1 / 500),
        'interval_caveat': 'Illustrative binomial upper bound; common sectors/systematics may correlate errors. Not a population guarantee.',
    }
    assert len(errors) == 252 and len(missed) == 249
    assert sum(result['false_negative_decision_paths'].values()) == 249
    write_json(REVIEW / 'diagnostics.json', result)
    return result


def table(headers, rows):
    return '<table><thead><tr>' + ''.join(f'<th>{escape(str(x))}</th>' for x in headers) + \
        '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{escape(str(x))}</td>' for x in row) +
                                       '</tr>' for row in rows) + '</tbody></table>'


def make_report(d):
    p, s = d['primary'], d['strict']
    body = '<h1>有标签千星测试：首次基线</h1><p>2026-11-12 · 全部 1,000 颗完成，失败 0。名单和规则在 9bb841b4 固定。这里补充结果解释；原始预测、答案和评分均已封存。</p>'
    body += '<h2>直接对答案</h2>' + table(['文献标签', '检出重复变光', '未检出'], [
        ['变星 500 颗', p['tp'], p['fn']], ['作者未见变光 500 颗', p['fp'], p['tn']]])
    body += '<p>精确率 251/254＝98.82%；正例检出率 251/500＝50.20%；反例误报率 3/500＝0.60%；准确率 748/1000＝74.80%。这些比例仅描述这份正反例各半、较亮 A-F 星的测试。</p>'
    body += '<h2>最终周期筛选</h2>' + table(['参考组', '选定周期', '弃选'], [
        ['变星 500 颗', s['tp'], s['fn']], ['作者未见变光 500 颗', s['fp'], s['tn']]])
    body += '<p>153 个选中对象均在变星组，保留了正例的 30.6%。这只说明对象标签一致，不能说 153 个周期全部正确。0/500 误报也不能证明总体误报率为零；若暂按独立二项试验近似，单侧 95% 上界约为 0.60%，共同仪器误差会限制这一近似。</p>'
    body += table(['所选周期与文献主频倒数的关系', '数量'], [
        ['直接吻合（1% 容差）', d['period_relations']['catalog_period_match']],
        ['半倍', d['period_relations']['half_catalog_period']],
        ['两倍', d['period_relations']['double_catalog_period']],
        ['其他', d['period_relations']['other_period']]])
    body += '<p>文献主频倒数未必是双星轨道周期，多周期星也可能有别的真实模式。因此 55 个分歧需要单独核验，不能全部改判为对或错。本轮没有为这 153 颗追加像素来源确认。</p>'
    body += '<h2>各类型检出情况</h2>'
    body += table(['参考类型', '总数', '检出', '漏检', '检出率'], [
        [kind, m['targets'], m['tp'], m['fn'], f"{m['recall_on_evaluated_positives']:.1%}"]
        for kind, m in d['by_reference_type'].items() if kind != 'author_nonvariable'])
    body += '<h2>漏检在哪一步发生</h2>' + table(['保存结果中的决策路径', '数量'], [
        ['两种产品都缺至少一个合格时段', d['false_negative_decision_paths']['both_products_missing_a_qualified_epoch']],
        ['两种产品各时段均有候选，但跨时段没有匹配周期', d['false_negative_decision_paths']['both_products_no_matching_cross_epoch_period']],
        ['一种产品缺合格时段，另一种跨时段周期不匹配', d['false_negative_decision_paths']['mixed_missing_epoch_and_period_mismatch']]])
    body += '<p>这是程序路径统计，不能据此把所有漏检归因于弱信号或某一种物理机制。下列三个漏检示例按各类型文献变幅最大者选择；它们不代表随机人工抽检。</p>'
    notes = read_json(REVIEW / 'visual-review.json')
    expected = {r['tic'] for r in d['errors'] if r['binary_outcome'] == 'fp'}
    expected.update(i.removeprefix('tic-') for i in d['representative_false_negative_ids'])
    expected.update(r['tic'] for r in d['half_cycle_selections'])
    assert len(notes['records']) == len(expected) == 9
    assert {r['tic'] for r in notes['records']} == expected
    for row in notes['records']:
        assert sha256(REVIEW / row['review_contact_sheet']) == row['contact_sheet_sha256']
        assert len(row['inspected_plots']) == 2
        for plot in row['inspected_plots']:
            assert sha256(OUT / plot['path']) == plot['sha256']
    for group, title in [('false_positive', '三个误报'), ('false_negative_example', '三个漏检示例'),
                         ('half_cycle_selection', '三个半周期分歧')]:
        body += f'<h2>{title}</h2>'
        for row in notes['records']:
            if row['group'] != group:
                continue
            tic = row['tic']
            body += f'<h3>TIC {escape(tic)}</h3><p>{escape(row["finding"])}</p><p>{escape(row["limit"])}</p>'
            body += f'<p><a href="../evaluation/tic-{tic}/period/index.html">两时段完整原图与预测</a> · <a href="tic-{tic}-review.jpg">查看拼图</a></p>'
    body += '<h2>后续比较怎么做</h2><p>保留本轮首次成绩。下一版本先处理强信号的半周期检查和产品分歧，并同时记录因此损失的正例。任何使用这批标签或错误调参的新版本，都只能把本批重跑视为开发比较；新的独立成绩应另取未使用对象。未知目标筛选和 VSX 投稿继续暂停。</p>'
    body += '<p><a href="../index.html">全部 1,000 颗可筛选结果</a> · <a href="../summary.csv">逐星 CSV</a> · <a href="diagnostics.json">全部 252 个错误的保存决策</a> · <a href="visual-review.json">九星看图备注</a> · <a href="../baseline-manifest.json">首次结果校验清单</a></p>'
    (REVIEW / 'index.html').write_text(page('千星首次基线', body))

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attrs):
            self.links.extend(v for k, v in attrs if k in ('href', 'src') and v)

    parser = Links()
    parser.feed((REVIEW / 'index.html').read_text())
    checked = 0
    for link in parser.links:
        url = urlsplit(link)
        if not url.scheme and not url.netloc and url.path:
            assert (REVIEW / unquote(url.path)).exists(), link
            checked += 1
    write_json(REVIEW / 'verification.json', {
        'checked_at': now(), 'baseline_manifest_sha256': sha256(MANIFEST),
        'diagnostics_sha256': sha256(REVIEW / 'diagnostics.json'),
        'visual_review_sha256': sha256(REVIEW / 'visual-review.json'),
        'report_sha256': sha256(REVIEW / 'index.html'),
        'error_records': len(d['errors']), 'false_negatives': 249,
        'reviewed_stars': len(notes['records']), 'reviewed_original_plots': 18,
        'report_local_links_verified': checked,
        'note': 'Checks data consistency and links, not physical-source or period certification.',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal', action='store_true', help='Create the baseline manifest if absent')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    seal_or_verify(args.seal)
    if not args.verify_only:
        REVIEW.mkdir(exist_ok=True)
        make_report(make_diagnostics())
        seal_or_verify()
        print(REVIEW / 'index.html')
