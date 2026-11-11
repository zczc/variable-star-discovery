"""Verify source preservation, all injected samples, prediction links and old results."""
from pathlib import Path
from urllib.parse import urlparse,unquote
from html.parser import HTMLParser
import numpy as np
from astropy.io import fits
from vstar.io import read_json,write_json,sha256,now
from empirical_injection import injected_signal,materialize
from run_empirical_injection import verify_protocol
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/empirical-injection-v01'
STD=ROOT/'repo/benchmarks/standard-star-check-v01'


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        self.links += [v for k,v in attrs if k in ('href','src') and v]


def main():
    verify_protocol();prior=read_json(BASE/'preserved-inputs.json')
    for item in prior['files']:assert sha256(ROOT/item['path'])==item['sha256'],item['path']
    manifest=read_json(BASE/'input-manifest.json');bases={b['id']:b for b in manifest['bases']}
    assert manifest['protocol_sha256']==sha256(BASE/'protocol.json')
    checks=0
    for case in manifest['cases']:
        base=bases[case['base_id']]
        for item,observation in zip(case['inputs'],base['observations'],strict=True):
            assert sha256(ROOT/item['path'])==item['sha256']
            assert sha256(ROOT/observation['source']['path'])==observation['source']['sha256']
            assert sha256(ROOT/observation['residual_path'])==observation['residual_sha256']
            with fits.open(ROOT/item['path']) as injected, fits.open(ROOT/observation['source']['path']) as original, np.load(ROOT/observation['residual_path']) as arrays:
                assert injected[0].header['SYNTHET']
                assert injected[0].header['TICID']==original[0].header['TICID']
                for column in original[1].data.names:
                    if column in ('SAP_FLUX','PDCSAP_FLUX'):continue
                    np.testing.assert_array_equal(injected[1].data[column],original[1].data[column])
                for product in ('SAP','PDCSAP'):
                    indices=arrays[product+'_indices'];time=original[1].data['TIME'][indices]
                    assert np.all(np.diff(time)>0)
                    median=observation['metadata']['products'][product]['normalization_median']
                    values=median*(1+arrays[product+'_residual']+injected_signal(time,case['signal'],base['origin_btjd']))
                    dtype=injected[1].data[product+'_FLUX'].dtype
                    np.testing.assert_array_equal(injected[1].data[product+'_FLUX'][indices],values.astype(dtype))
                    unused=np.ones(len(original[1].data),dtype=bool);unused[indices]=False
                    np.testing.assert_array_equal(injected[1].data[product+'_FLUX'][unused],original[1].data[product+'_FLUX'][unused])
            checks+=1
    # Byte-identical materialization from the public residuals and parent observation.
    case=manifest['cases'][1];base=bases[case['base_id']];obs=base['observations'][0]
    rebuilt=ROOT/'repo/data/empirical-audit/rebuilt.fits.gz'
    materialize(ROOT/obs['source']['path'],ROOT/obs['residual_path'],obs['metadata'],case['signal'],base['origin_btjd'],rebuilt)
    assert sha256(rebuilt)==case['inputs'][0]['sha256']
    std=read_json(STD/'input-manifest.json');raw_checks=0
    for case in std['cases']:
        for item in case['inputs']:
            path=ROOT/item['path'];assert sha256(path)==item['sha256']
            receipt=read_json(path.with_suffix('.receipt.json'))
            assert receipt['uri']==item['uri'] and receipt['sha256']==item['sha256']
            with fits.open(path) as h:
                assert str(h[0].header['TICID'])==case['tic'] and h[0].header['SECTOR']==item['sector']
                assert not h[0].header.get('SYNTHET',False)
            raw_checks+=1
    assert std['protocol_sha256']==sha256(STD/'protocol.json')
    html_checks=0
    for folder in (BASE,STD):
        predictions=read_json(folder/'evaluation/predictions.json')
        assert predictions['complete']
        results=read_json(folder/'evaluation/results.json')
        assert results['predictions_sha256']==sha256(folder/'evaluation/predictions.json')
        for row in predictions['results']:
            assert row['status']=='completed'
            for obs in row['products']['observations']:
                assert sha256(ROOT/obs['input']['path'])==obs['input']['sha256']
                assert sha256(folder/'evaluation'/row['id']/obs['plot'])==obs['plot_sha256']
        for path in (folder/'evaluation').rglob('*.html'):
            parser=Links();parser.feed(path.read_text())
            for target in parser.links:
                url=urlparse(target)
                if url.scheme or url.netloc or not url.path:continue
                assert (path.parent/unquote(url.path)).exists(),(path,target)
            html_checks+=1
    write_json(BASE/'integrity-audit.json',{'checked_at':now(),'old_files_unchanged':len(prior['files']),
        'all_injected_FITS_checked':checks,'raw_standard_FITS_and_receipts_checked':raw_checks,'html_pages_checked':html_checks,
        'v4_scientific_files_unchanged':True,'independent_pilot_v02_unchanged':True,'sample_materialization_byte_reproduced':True,
        'all_observation_and_plot_hashes_verified':True,'predictions_saved_and_hashed_before_scoring':True,
        'scientific_validity_or_false_positive_calibration_claimed':False,'audit_script_sha256':sha256(Path(__file__))})
    print('AUDIT OK',len(prior['files']),'old files,',checks,'artificial FITS,',raw_checks,'raw standards,',html_checks,'HTML pages')

if __name__=='__main__':main()
