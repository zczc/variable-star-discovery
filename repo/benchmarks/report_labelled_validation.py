"""Compare preserved, label-blind predictions with frozen literature labels."""
from pathlib import Path
from collections import Counter
from html import escape
import csv
import json

from vstar.io import read_json, write_json, sha256, now
from vstar.reports import page
from labelled_validation_support import binary_metrics, detection_flags
from scale_validation_support import period_relation

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'repo/benchmarks/labelled-validation-v01'


def main():
    targets = read_json(OUT / 'targets.json')['cases']
    labels = {c['id']: c['label'] for c in targets}
    primary, strict, rows, states = {}, {}, [], Counter()
    for case in targets:
        ident = case['id']
        path = OUT / 'evaluation' / (ident + '-prediction.json')
        prediction = read_json(path) if path.exists() else {'status': 'pending'}
        flags = prediction.get('detection', {'repeated_signal': None, 'selected_period': None})
        if prediction['status'] == 'completed':
            assert flags == detection_flags(prediction['product_conclusions'], prediction['decision'])
        else:
            assert flags == {'repeated_signal': None, 'selected_period': None}
        states[prediction['status']] += 1
        primary[ident], strict[ident] = flags['repeated_signal'], flags['selected_period']
        actual = flags['repeated_signal']
        outcome = 'unavailable' if actual is None else ('tp' if actual else 'fn') if case['label'] else ('fp' if actual else 'tn')
        frequency = float(case['reference']['f']) if case['reference']['f'] else None
        reference_period = 1 / frequency if frequency else None
        selected = prediction.get('decision', {}).get('selected_period_d')
        row = {'id': ident, 'tic': case['tic'], 'label': case['label'],
               'reference_type': case['reference']['VType'] or 'author_nonvariable',
               'status': prediction['status'], 'repeated_signal': actual, 'binary_outcome': outcome,
               'selected_period_d': selected, 'reference_dominant_frequency_cpd': frequency,
               'reference_dominant_cycle_d': reference_period,
               'selected_to_reference_cycle': period_relation(selected, reference_period),
               'source_independently_confirmed_by_this_run': False}
        rows.append(row)
    summary = {'generated_at': now(), 'targets_sha256': sha256(OUT / 'targets.json'),
               'protocol_sha256': sha256(OUT / 'protocol.json'), 'status_counts': dict(states),
               'primary_repeated_signal': binary_metrics(labels, primary),
               'secondary_selected_period': binary_metrics(labels, strict),
               'by_reference_type': {}, 'period_comparison_on_selected_positives': {}, 'rows': rows}
    for kind in sorted({r['reference_type'] for r in rows}):
        ids = {r['id'] for r in rows if r['reference_type'] == kind}
        summary['by_reference_type'][kind] = binary_metrics({i: labels[i] for i in ids}, {i: primary[i] for i in ids})
    summary['period_comparison_on_selected_positives'] = dict(Counter(
        r['selected_to_reference_cycle'] for r in rows if r['label'] == 1 and r['selected_period_d'] is not None))
    write_json(OUT / 'summary.json', summary)
    with (OUT / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    write_json(OUT / 'disagreements.json', {'generated_at': now(),
        'labels_unchanged': True, 'records': [r for r in rows if r['binary_outcome'] in {'fp', 'fn', 'unavailable'}]})
    score = summary['primary_repeated_signal']
    body = '<h1>有参考标签的 1,000 星测试</h1><p>500 个论文确认的周期变星，500 个作者逐颗检查后未见变光的对照；均来自 TESS Cycle 2。参考标签不传给检测器。</p>'
    body += '<p>主指标只问有没有跨时段重复信号：SAP 或 PDCSAP 任一产品建立重复信号即为检出。半周期、多周期歧义不抹掉检出。最终周期能否选定另列，来源定位和新发现资格不由本次考试确认。</p>'
    body += '<table><tr><th>论文参考标签</th><th>程序检出</th><th>程序未检出</th><th>不可用／未完成</th></tr>'
    body += f'<tr><td>有周期变光（500）</td><td>{score["tp"]}</td><td>{score["fn"]}</td><td>{score["unavailable_positive"]}</td></tr>'
    body += f'<tr><td>作者未见变光（500）</td><td>{score["fp"]}</td><td>{score["tn"]}</td><td>{score["unavailable_negative"]}</td></tr></table>'
    for title, key in [('已完成对象的准确率', 'accuracy_on_evaluated'), ('正例检出率', 'recall_on_evaluated_positives'),
                       ('本平衡测试集的精确率', 'precision_in_balanced_benchmark'), ('反例误报率', 'false_positive_rate_on_evaluated_negatives')]:
        value = score[key]
        body += '<p>' + title + '：' + (f'{100*value:.2f}%' if value is not None else '尚无分母') + '。</p>'
    body += '<p>这是一组限定亮度、温度、频率与观测覆盖的 A-F 星，正反例各占一半。精确率仅适用于这份测试集，不能当作未来随机筛星的精确率。标签是论文作者在规定观测中作出的判断，并非恒星永远不变的证明。保留所有与标签的分歧，不按本次结果修改答案。</p>'
    body += '<p>完整周期与论文主频的倒数另行比较；后者不一定是食双星轨道周期，也不代表多周期星只有一个周期。<a href="summary.json">完整评分</a> · <a href="summary.csv">逐星结果</a> · <a href="disagreements.json">全部分歧</a> · <a href="README.md">方案及标签出处</a>。</p>'
    body += '<input id="filter" placeholder="筛选 TIC、类型或 tp/fp/fn/tn"><table id="results"><thead><tr><th>TIC</th><th>参考类型</th><th>程序检出</th><th>对比</th><th>选定周期（天）</th><th>主频周期比较</th></tr></thead><tbody>'
    for r in rows:
        link = OUT / 'evaluation' / r['id'] / 'period/index.html'
        name = f'<a href="evaluation/{r["id"]}/period/index.html">{r["tic"]}</a>' if link.exists() else r['tic']
        body += f'<tr><td>{name}</td><td>{escape(r["reference_type"])}</td><td>{r["repeated_signal"]}</td><td>{r["binary_outcome"]}</td><td>{r["selected_period_d"]}</td><td>{r["selected_to_reference_cycle"]}</td></tr>'
    body += '</tbody></table><script>document.getElementById("filter").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#results tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script>'
    (OUT / 'index.html').write_text(page('有标签的千星测试', body))
    print(json.dumps({k: v for k, v in summary.items() if k not in {'rows', 'by_reference_type'}}, indent=2))


if __name__ == '__main__':
    main()
