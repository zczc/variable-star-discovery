from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from labelled_validation_support import detection_flags, binary_metrics
from select_labelled_validation import reference_label


def test_period_ambiguity_does_not_erase_detection():
    conclusions = {'SAP': {'periodic_detected': True}, 'PDCSAP': {'periodic_detected': False}}
    result = detection_flags(conclusions, {'selected_period_d': None})
    assert result == {'repeated_signal': True, 'selected_period': False}


def test_failure_never_becomes_a_negative_prediction():
    flags = detection_flags({}, {}, ['download unavailable'])
    metrics = binary_metrics({'p': 1, 'n': 0}, {'p': flags['repeated_signal'], 'n': None})
    assert metrics['tn'] == metrics['fn'] == metrics['evaluated'] == 0
    assert metrics['unavailable_positive'] == metrics['unavailable_negative'] == 1
    assert metrics['accuracy_on_evaluated'] is None


def test_complete_binary_confusion_matrix_and_denominators():
    labels = dict(a=1, b=1, c=0, d=0, e=1)
    scores = binary_metrics(labels, dict(a=True, b=False, c=True, d=False, e=None))
    assert [scores[k] for k in ('tp', 'fn', 'fp', 'tn')] == [1, 1, 1, 1]
    assert scores['accuracy_on_evaluated'] == scores['precision_in_balanced_benchmark'] == .5
    assert scores['positive_recovery_all_prespecified'] == 1/3
    with pytest.raises(ValueError):
        binary_metrics(labels, dict(a=True))


def test_unclear_and_conflicting_catalogue_labels_are_not_negatives():
    assert reference_label({'VType': '', 'VSX': ''}) == 0
    assert reference_label({'VType': '', 'VSX': 'known variable'}) is None
    assert reference_label({'VType': 'VAR', 'VSX': '', 'f': '1'}) is None
    assert reference_label({'VType': 'DSCT|EW', 'VSX': '', 'f': '1'}) is None
    assert reference_label({'VType': 'DSCT', 'VSX': '', 'f': '40'}) is None
    assert reference_label({'VType': 'EA', 'VSX': '', 'f': '1'}) == 1
