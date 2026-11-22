"""Numerical checks for exploratory localization, not real-sky error calibration."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest


def load_benchmark(name):
    path = Path(__file__).resolve().parents[1] / 'benchmarks' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loc = load_benchmark('localize_302959739')
followup = load_benchmark('followup_302959739')


class GaussianImage:
    """Independent analytic image used only to exercise coordinate/plane fitting."""
    @staticmethod
    def locate(x, y, shape):
        yy, xx = np.indices(shape)
        return np.exp(-((xx-x)**2 + (yy-y)**2) / (2 * .8**2))


@pytest.mark.parametrize('xy', [(5.11, 4.77), (5.34, 4.88)])
def test_subpixel_recovery_with_sloping_background(xy):
    model = GaussianImage()
    yy, xx = np.indices((11, 11))
    signal = 80*model.locate(*xy, (11, 11)) + 4 + .3*xx - .2*yy
    found, _ = loc.fit_source(model, signal, np.ones_like(signal), np.array([5., 5.]))
    assert found['optimizer_success'] and not found['search_boundary']
    assert found['position_identifiable']
    assert np.linalg.norm(np.array(found['xy']) - xy) < .001


def test_background_only_does_not_identify_a_position():
    yy, xx = np.indices((11, 11))
    signal = 4 + .3*xx - .2*yy
    found, _ = loc.fit_source(GaussianImage(), signal, np.ones_like(signal), [5., 5.])
    assert not found['position_identifiable']
    assert found['amplitude'] < 1e-9


def test_catalog_registration_recovers_shift_and_background():
    model = GaussianImage()
    sources = [{'source_id': str(i), 'pixel': np.array(p)}
               for i, p in enumerate([(2., 3.), (7., 3.), (4., 8.)])]
    shift = np.array([.17, -.11])
    yy, xx = np.indices((11, 11))
    field = 4 + .3*xx - .2*yy
    for s, amplitude in zip(sources, [20, 70, 40]):
        field += amplitude * model.locate(*(s['pixel']+shift), field.shape)
    result, _ = loc.register(model, field, np.ones_like(field), sources, sources[0]['pixel'], .02)
    assert result['optimizer_success'] and not result['boundary']
    assert np.linalg.norm(np.array(result['shift_pixel'])-shift) < .001


def test_mask_preserves_periodic_range_and_excludes_transient():
    values = 100 + np.sin(np.linspace(0, 20*np.pi, 2001))
    values[700:705] += 100
    valid = np.ones(len(values), bool)
    valid[100] = False
    mask, _, _ = followup.mask_outliers(values, valid)
    assert np.flatnonzero(mask).tolist() == list(range(700, 705))
    with pytest.raises(ValueError):
        followup.mask_outliers(np.ones(10), np.ones(10, bool))
