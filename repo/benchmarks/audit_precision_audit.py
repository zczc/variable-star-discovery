"""Verify old results, matched artificial light curves, source masks and provenance."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse,unquote
import numpy as np
from astropy.io import fits
from vstar.io import read_json,write_json,sha256,now
from precision_challenges import construct,flux_signal
from standard_injection import good_mask,signal
from run_precision_audit import verify
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/precision-audit-v01'


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):self.links += [v for k,v in attrs if k in ['src','href'] and v]


def main():
    verify();prior=read_json(BASE/'preserved-inputs.json')
    for item in prior['files']:assert sha256(ROOT/item['path'])==item['sha256'],item['path']
    manifest=read_json(BASE/'input-manifest.json');predictions=read_json(BASE/'evaluation/predictions.json');results=read_json(BASE/'evaluation/results.json')
    assert predictions['complete'] and len(predictions['results'])==len(manifest['cases'])==42
    assert manifest['protocol_sha256']==predictions['protocol_sha256']==sha256(BASE/'protocol.json')
    assert predictions['manifest_sha256']==sha256(BASE/'input-manifest.json')
    assert results['predictions_sha256']==sha256(BASE/'evaluation/predictions.json')
    checked=0;matched=0;rebuilt=0;cache={}
    for case in manifest['cases']:
        for item in case['inputs']:
            path=ROOT/item['path'];assert sha256(path)==item['sha256']
            if item.get('pixels'):assert sha256(ROOT/item['pixels']['path'])==item['pixels']['sha256']
            if case['kind']!='artificial':continue
            spec=case['challenge'];source=ROOT/item['source']['path'];assert sha256(source)==item['source']['sha256']
            with fits.open(source) as a,fits.open(path) as b:
                assert b[0].header['SYNTHET']
                for name in a[1].data.names:
                    if name not in ['SAP_FLUX','PDCSAP_FLUX',spec.get('channel')]:np.testing.assert_array_equal(a[1].data[name],b[1].data[name])
                exposure=item['construction']['time_window_d']
                for product in ['SAP','PDCSAP']:
                    good=good_mask(a[1].data,product);t=np.asarray(a[1].data['TIME'][good],float);y=np.asarray(a[1].data[product+'_FLUX'][good],float)
                    expected=y+np.median(y)*flux_signal(t,spec,case['origin_btjd'],exposure)
                    np.testing.assert_array_equal(expected.astype(b[1].data[product+'_FLUX'].dtype),b[1].data[product+'_FLUX'][good])
                    np.testing.assert_array_equal(a[1].data[product+'_FLUX'][~good],b[1].data[product+'_FLUX'][~good])
                    if spec['kind'] in ['unattributed_signal','background_coupled','pointing_coupled','centroid_coupled']:
                        key=(case['base_id'],item['sector'],spec['period_d'],product)
                        if key in cache:np.testing.assert_array_equal(cache[key],b[1].data[product+'_FLUX']);matched+=1
                        else:cache[key]=b[1].data[product+'_FLUX'].copy()
                if spec.get('channel'):
                    name=spec['channel'];time=np.asarray(a[1].data['TIME'],float);y=np.asarray(a[1].data[name],float)
                    valid=np.isfinite(time)&np.isfinite(y)&(a[1].data['QUALITY']==0)
                    scale=item['construction']['modified_auxiliary']['original_std']
                    expected=y[valid]+20*scale*signal(time[valid],dict(spec,shape='sine',amplitude_fraction=2.),case['origin_btjd'],exposure)
                    np.testing.assert_array_equal(expected.astype(b[1].data[name].dtype),b[1].data[name][valid])
                checked+=1
        if case['kind']=='artificial' and case['base_id']=='g191-b2b':
            item=case['inputs'][0];dest=ROOT/'repo/data/precision-audit-check'/f'{case["id"]}.fits.gz'
            construct(ROOT/item['source']['path'],case['challenge'],case['origin_btjd'],dest)
            assert sha256(dest)==item['sha256'];rebuilt+=1
    for row in predictions['results']:
        assert row['status']=='completed',(row['id'],row.get('error'),row.get('source_review',{}).get('errors'))
        con=row['source_review']['conclusion']
        assert not con['confirmed_variable'] and not con['submission_ready']
        for obs in row['products']['observations']:
            assert sha256(ROOT/obs['input']['path'])==obs['input']['sha256']
            assert sha256(BASE/'evaluation'/row['id']/'period'/obs['plot'])==obs['plot_sha256']
        for obs in row['source_review']['observations']:
            if obs['pixels']:
                p=obs['pixels']
                assert sha256(ROOT/p['pixels']['path'])==p['pixels']['sha256']
                assert sha256(ROOT/p['lightcurve']['path'])==p['lightcurve']['sha256']
                assert sha256(BASE/'evaluation'/row['id']/'source'/p['plot'])==p['plot_sha256']
    pages=0
    for path in (BASE/'evaluation').rglob('*.html'):
        links=Links();links.feed(path.read_text())
        for target in links.links:
            url=urlparse(target)
            if url.scheme or url.netloc or not url.path:continue
            assert (path.parent/unquote(url.path)).exists(),(path,target)
        pages+=1
    write_json(BASE/'integrity-audit.json',{'checked_at':now(),'old_files_unchanged':len(prior['files']),
        'artificial_FITS_verified':checked,'identical_flux_product_pairs_checked':matched,
        'deterministic_rebuilds':rebuilt,'completed_cases':42,'html_pages_checked':pages,
        'frozen_v4_unchanged':True,'independent_pilot_v02_unchanged':True,'all_source_and_period_plot_hashes_verified':True,
        'population_precision_validated':False,'audit_script_sha256':sha256(Path(__file__))})
    print('AUDIT OK',len(prior['files']),'old files',checked,'artificial FITS',matched,'same-flux checks',rebuilt,'rebuilds',pages,'pages')

if __name__=='__main__':main()
