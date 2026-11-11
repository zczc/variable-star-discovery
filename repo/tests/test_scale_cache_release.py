import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from release_scale_pixel_cache import check_path


def test_release_rejects_lightcurves_outside_paths_and_uri_mismatch(tmp_path):
    cache = tmp_path / 'cache'
    name = 'tess1-s0001-0000000000000001-0001-s_tp.fits'
    good = {'path': 'cache/' + name + '.gz', 'uri': 'mast:TESS/product/' + name}
    assert check_path(good, tmp_path, cache) == cache / (name + '.gz')
    for bad in [dict(good, path=good['path'].replace('_tp.', '_lc.')),
                dict(good, path='other/' + name + '.gz'),
                dict(good, uri='mast:TESS/product/another_tp.fits')]:
        with pytest.raises(ValueError):
            check_path(bad, tmp_path, cache)
