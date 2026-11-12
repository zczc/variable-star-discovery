from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from scale_direct_transport import direct_url


def test_direct_public_key_matches_observed_archive_layout():
    name = 'tess2024196212429-s0081-0000000123416563-0276-s_tp.fits'
    assert direct_url('mast:TESS/product/' + name) == 'https://stpubdata.s3.us-east-1.amazonaws.com/tess/public/tid/s0081/0000/0001/2341/6563/' + name
    name = 'tess2024114025118-s0078-0000000017562290-0273-s_tp.fits'
    assert direct_url('mast:TESS/product/' + name).endswith('/s0078/0000/0000/1756/2290/' + name)


@pytest.mark.parametrize('uri', ['https://example.com/file', 'mast:TESS/product/../tess1-s0001-0000000000000001-1-s_tp.fits', 'mast:TESS/product/tess1-s0001-1-1-s_tp.fits'])
def test_direct_public_key_rejects_non_products(uri):
    with pytest.raises(ValueError):
        direct_url(uri)
