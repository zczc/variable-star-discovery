"""Check frozen truth, complete outputs, scoring denominators and original bytes."""
from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import gzip
import hashlib
import json

from vstar.io import read_json, write_json, sha256, now
from run_labelled_validation import verify, ROOT, OUT
from select_labelled_validation import verify_pool, reference_label
from labelled_validation_support import detection_flags, binary_metrics
from scale_validation_support import period_relation


def main():
    verify()
    pool = verify_pool()
    targets = read_json(OUT / 'targets.json')['cases']
    blind = read_json(OUT / 'blind-inputs.json')
    assert blind['targets_sha256'] == sha256(OUT / 'targets.json')
    assert blind['cases'] == [{k: c[k] for k in ['id', 'tic', 'inputs']} for c in targets]
    assert len(targets) == len({c['tic'] for c in targets}) == 1000
    assert Counter(c['label'] for c in targets) == {0: 500, 1: 500}
    assert not {c['tic'] for c in targets} & set(pool['previous_tics'])
    raw = {r['tic']: r for r in pool['records']}
    for c in targets:
        assert c['reference'] == raw[c['tic']]['row']
        assert c['label'] == reference_label(c['reference']) == raw[c['tic']]['label']
        assert len(c['inputs']) == 2
        assert all(14 <= o['sector'] <= 26 for o in c['inputs'])
        assert c['inputs'][1]['t_min_mjd'] - c['inputs'][0]['t_min_mjd'] >= 180
    for item in read_json(OUT / 'targets.json')['metadata_files']:
        assert sha256(ROOT / item['path']) == item['sha256']
    eligibility = read_json(OUT / 'eligibility.json')['rows']
    for label in [0, 1]:
        ranked = sorted([r['tic'] for r in eligibility if r['label'] == label and r['two_epochs_180d']],
                        key=lambda tic: hashlib.sha256(f'{pool["seed"]}:{tic}'.encode()).hexdigest())
        assert {c['tic'] for c in targets if c['label'] == label} == set(ranked[:500])
    old = read_json(OUT / 'preserved-old-results.json')['files']
    for item in old:
        assert sha256(ROOT / item['path']) == item['sha256']
    checked, plots, predictions, states, outputs = set(), 0, {}, Counter(), {}
    for case in targets:
        prediction_path = OUT / 'evaluation' / (case['id'] + '-prediction.json')
        prediction = read_json(prediction_path)
        outputs[case['id']] = prediction
        predictions[case['id']] = sha256(prediction_path)
        states[prediction['status']] += 1
        assert prediction['id'] == case['id']
        acquisition = read_json(OUT / 'acquisition' / (case['id'] + '.json'))
        assert prediction['inputs'] == acquisition['inputs']
        if prediction['status'] == 'completed':
            assert not prediction['errors'] and len(prediction['inputs']) == 2
            assert prediction['detection'] == detection_flags(prediction['product_conclusions'], prediction['decision'])
            assert not prediction['decision']['confirmed_variable']
        else:
            assert prediction['detection'] == {'repeated_signal': None, 'selected_period': None}
        product_path = OUT / 'evaluation' / case['id'] / 'period/case.json'
        if product_path.exists():
            products = read_json(product_path)
            if 'product_conclusions' in prediction:
                assert products['conclusions'] == prediction['product_conclusions']
            else:
                assert prediction['status'] == 'failed'
            for obs in products['observations']:
                assert str(obs['tic']) == case['tic']
                assert sha256(product_path.parent / obs['plot']) == obs['plot_sha256']
                plots += 1
        for item in acquisition['inputs']:
            assert {'sector': item['sector'], 'uri': item['uri'], 't_min_mjd': item['t_min_mjd'],
                    't_max_mjd': item['t_max_mjd']} in case['inputs']
            if item['path'] in checked:
                continue
            path = ROOT / item['path']
            receipt = read_json(path.with_name(path.name.replace('.gz', '.receipt.json')))
            assert receipt['uri'] == item['uri']
            assert receipt['sha256'] == item['sha256'] == sha256(path)
            with gzip.open(path, 'rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['raw_sha256'] == receipt['raw_sha256']
            checked.add(item['path'])
    summary = read_json(OUT / 'summary.json')
    assert len(summary['rows']) == 1000
    assert {r['id'] for r in summary['rows']} == {c['id'] for c in targets}
    assert summary['status_counts'] == dict(states)
    assert summary['targets_sha256'] == sha256(OUT / 'targets.json')
    assert summary['protocol_sha256'] == sha256(OUT / 'protocol.json')
    labels = {c['id']: c['label'] for c in targets}
    for key, field in [('primary_repeated_signal', 'repeated_signal'), ('secondary_selected_period', 'selected_period')]:
        flags = {ident: read_json(OUT / 'evaluation' / (ident + '-prediction.json'))['detection'][field] for ident in labels}
        assert summary[key] == binary_metrics(labels, flags)
    by_id = {c['id']: c for c in targets}
    for row in summary['rows']:
        case, prediction = by_id[row['id']], outputs[row['id']]
        assert row['label'] == case['label'] and row['tic'] == case['tic']
        assert row['status'] == prediction['status']
        assert row['repeated_signal'] == prediction['detection']['repeated_signal']
        assert row['selected_period_d'] == prediction.get('decision', {}).get('selected_period_d')
        expected_type = case['reference']['VType'] or 'author_nonvariable'
        assert row['reference_type'] == expected_type
        frequency = float(case['reference']['f']) if case['reference']['f'] else None
        cycle = 1 / frequency if frequency else None
        assert row['reference_dominant_frequency_cpd'] == frequency
        assert row['reference_dominant_cycle_d'] == cycle
        assert row['selected_to_reference_cycle'] == period_relation(row['selected_period_d'], cycle)
        assert row['source_independently_confirmed_by_this_run'] is False
    for kind, metrics in summary['by_reference_type'].items():
        ids = {r['id'] for r in summary['rows'] if r['reference_type'] == kind}
        assert metrics == binary_metrics({i: labels[i] for i in ids},
            {i: outputs[i]['detection']['repeated_signal'] for i in ids})
    assert summary['period_comparison_on_selected_positives'] == dict(Counter(
        r['selected_to_reference_cycle'] for r in summary['rows']
        if r['label'] == 1 and r['selected_period_d'] is not None))
    disagreements = read_json(OUT / 'disagreements.json')
    assert disagreements['labels_unchanged'] is True
    assert disagreements['records'] == [r for r in summary['rows']
        if r['binary_outcome'] in {'fp', 'fn', 'unavailable'}]
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []
        def handle_starttag(self, tag, attrs):
            self.links.extend(v for k, v in attrs if k in {'href', 'src'} and v)
    pages = [OUT / 'index.html', *sorted((OUT / 'evaluation').rglob('*.html'))]
    count = 0
    for page in pages:
        parser = Links()
        parser.feed(page.read_text())
        for link in parser.links:
            url = urlsplit(link)
            if not url.scheme and not url.netloc and url.path:
                assert (page.parent / unquote(url.path)).exists(), (page, link)
                count += 1
    audit = {'checked_at': now(), 'target_count': 1000, 'labels': {'positive': 500, 'negative': 500},
             'prediction_states': dict(states), 'original_products_verified': len(checked),
             'plots_verified': plots, 'preserved_old_results': len(old), 'html_pages': len(pages),
             'local_links_verified': count, 'frozen_code_and_labels_unchanged': True,
             'score_matches_raw_predictions': True, 'prediction_sha256': predictions,
             'meaning': 'Data and scoring integrity; benchmark label agreement is not discovery certification.'}
    write_json(OUT / 'integrity-audit.json', audit)
    print(json.dumps({k: v for k, v in audit.items() if k != 'prediction_sha256'}, indent=2))


if __name__ == '__main__':
    main()
