"""Prespecified output mapping and binary scoring; never used to search periods."""


def detection_flags(conclusions, decision, errors=()):
    if errors:
        return {'repeated_signal': None, 'selected_period': None}
    if set(conclusions) != {'SAP', 'PDCSAP'}:
        raise ValueError('Both product results are required')
    return {
        # Period ambiguity must not erase an already detected repeated signal.
        'repeated_signal': any(bool(conclusions[p]['periodic_detected']) for p in conclusions),
        'selected_period': decision.get('selected_period_d') is not None,
    }


def binary_metrics(labels, predictions):
    if set(labels) != set(predictions):
        raise ValueError('All prespecified targets, including failures, must be present')
    counts = {'tp': 0, 'fn': 0, 'fp': 0, 'tn': 0, 'unavailable_positive': 0, 'unavailable_negative': 0}
    for ident, label in labels.items():
        value = predictions[ident]
        if label not in (0, 1) or value is not None and not isinstance(value, bool):
            raise ValueError('Invalid binary label or prediction')
        if value is None:
            counts['unavailable_positive' if label else 'unavailable_negative'] += 1
        else:
            counts[('tp' if value else 'fn') if label else ('fp' if value else 'tn')] += 1
    tp, fn, fp, tn = (counts[k] for k in ['tp', 'fn', 'fp', 'tn'])
    divide = lambda numerator, denominator: numerator / denominator if denominator else None
    return dict(counts, targets=len(labels), evaluated=tp+fn+fp+tn,
                accuracy_on_evaluated=divide(tp+tn, tp+fn+fp+tn),
                recall_on_evaluated_positives=divide(tp, tp+fn),
                precision_in_balanced_benchmark=divide(tp, tp+fp),
                false_positive_rate_on_evaluated_negatives=divide(fp, fp+tn),
                positive_recovery_all_prespecified=divide(tp, tp+fn+counts['unavailable_positive']),
                population_precision_estimate=False)
