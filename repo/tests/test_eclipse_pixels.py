import numpy as np
import pytest
from vstar.eclipse_pixels import difference_image, peak_location


def test_differencing_localizes_eclipse_and_cancels_linear_background():
    time = np.arange(0, 12, .01)
    phase_time = (time - .5 + 1) % 2 - 1
    cube = np.broadcast_to((100 + .3 * time)[:, None, None], (len(time), 5, 5)).copy()
    cube[:, 3, 1] -= 20 * (abs(phase_time) <= .05)
    signal, _, _, events = difference_image(time, cube, 2, .5, .1)
    assert len(events) >= 5
    assert peak_location(signal)["peak_pixel"] == [1, 3]
    assert signal[3, 1] == pytest.approx(20)
    signal[3, 1] = 0
    assert np.max(abs(signal)) < 1e-10


def test_unbracketed_event_is_not_accepted():
    time = np.arange(.45, .55, .01)
    with pytest.raises(ValueError, match="two events"):
        difference_image(time, np.ones((len(time), 3, 3)), 2, .5, .1)
