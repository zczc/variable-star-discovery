from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from run_scale_all_sources import eligible


def test_full_source_cohort_keeps_all_risks_and_only_selected_other_targets():
    for status in ['completed', 'unavailable', 'failed']:
        for period in [None, 0.8]:
            prediction = {'status': status, 'decision': {'selected_period_d': period}}
            assert eligible({'group': 'neighbor_risk'}, prediction)
            for group in ['catalog_eb', 'field_unlabelled']:
                assert eligible({'group': group}, prediction) == (status == 'completed' and period is not None)
