from vstar.products import summarize_products


def conclusion(p=None,detected=True):
    return {'periodic_detected':detected,'photometric_period_d':p,'selected_period_d':p,
            'period_status':'preferred_lightcurve_cycle','source_status':'unchecked'}


def test_two_products_are_not_two_independent_detections():
    r=summarize_products({'SAP':conclusion(.5),'PDCSAP':conclusion(.5001)})
    assert r['status']=='both_products_agree'
    assert not r['confirmed_variable'] and not r['target_candidate']


def test_sap_only_does_not_silently_override_pdc():
    r=summarize_products({'SAP':conclusion(.5),'PDCSAP':conclusion(None,False)})
    assert r['status']=='product_review_required' and r['agreed_period_d'] is None
    assert r['period_hypotheses'][0]['selected_period_d']==.5


def test_product_harmonic_conflict_is_explicit():
    r=summarize_products({'SAP':conclusion(.5),'PDCSAP':conclusion(1.)})
    assert r['status']=='product_review_required' and len(r['period_hypotheses'])==2


def test_failure_cannot_become_agreement():
    r=summarize_products({'SAP':conclusion(.5),'PDCSAP':conclusion(.5)},['missing input'])
    assert r['status']=='analysis_failed' and r['agreed_period_d'] is None
