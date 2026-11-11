from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))

def test_source_sampling_is_deterministic_without_outcome_cherry_picking():
    from run_scale_source_sample import choose
    cases=[{'tic':str(i),'group':g} for i,g in enumerate(['catalog_eb']*70+['neighbor_risk']*40+['field_unlabelled']*10)]
    quota={'catalog_eb':40,'neighbor_risk':30,'field_unlabelled':30}
    a=choose(cases,quota,'fixed-seed',100)
    b=choose(list(reversed(cases)),quota,'fixed-seed',100)
    assert a==b and len({c['tic'] for c in a})==100
    assert sum(c['group']=='field_unlabelled' for c in a)==10
    assert sum(c['group']=='catalog_eb' for c in a)>=40
    assert sum(c['group']=='neighbor_risk' for c in a)>=30
    with pytest.raises(ValueError):choose(cases[:10],quota,'fixed-seed',100)
