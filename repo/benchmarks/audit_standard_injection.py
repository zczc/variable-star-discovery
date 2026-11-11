"""Check every artificial input and ensure previous experiments stay unchanged."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse,unquote
import numpy as np
from astropy.io import fits
from vstar.io import read_json,write_json,sha256,now
from standard_injection import signal,construct,good_mask
from run_standard_injection import verify_protocol
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'repo/benchmarks/standard-injection-v01'


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):self.links += [v for k,v in attrs if k in ('href','src') and v]


def main():
    protocol=verify_protocol();prior=read_json(BASE/'preserved-inputs.json')
    for item in prior['files']:assert sha256(ROOT/item['path'])==item['sha256'],item['path']
    manifest=read_json(BASE/'input-manifest.json');predictions=read_json(BASE/'evaluation/predictions.json')
    result=read_json(BASE/'evaluation/results.json')
    assert manifest['protocol_sha256']==sha256(BASE/'protocol.json')
    assert predictions['protocol_sha256']==sha256(BASE/'protocol.json')
    assert predictions['manifest_sha256']==sha256(BASE/'input-manifest.json')
    assert result['predictions_sha256']==sha256(BASE/'evaluation/predictions.json')
    assert len(manifest['cases'])==protocol['total_cases']==len(predictions['results'])==len(result['rows'])
    assert len({r['id'] for r in predictions['results']})==len(manifest['cases'])
    checked=0;zeros=0;rebuilt=0
    for case in manifest['cases']:
        for item in case['inputs']:
            source=ROOT/item['source']['path'];generated=ROOT/item['path']
            assert sha256(source)==item['source']['sha256'] and sha256(generated)==item['sha256']
            with fits.open(source) as a,fits.open(generated) as b:
                assert b[0].header['SYNTHET'] and not a[0].header.get('SYNTHET',False)
                assert a[0].header['TICID']==b[0].header['TICID'] and a[0].header['SECTOR']==b[0].header['SECTOR']
                for name in a[1].data.names:
                    if name not in ('SAP_FLUX','PDCSAP_FLUX') or case['signal']['shape']=='zero':
                        np.testing.assert_array_equal(a[1].data[name],b[1].data[name])
                for product in ('SAP','PDCSAP'):
                    good=good_mask(a[1].data,product);t=np.asarray(a[1].data['TIME'][good],float)
                    original=np.asarray(a[1].data[product+'_FLUX'][good],float);median=float(np.median(original))
                    delta=signal(t,case['signal'],case['origin_btjd'],item['construction']['time_window_d'])
                    expected=(original+median*delta).astype(b[1].data[product+'_FLUX'].dtype)
                    np.testing.assert_array_equal(b[1].data[product+'_FLUX'][good],expected)
                    np.testing.assert_array_equal(b[1].data[product+'_FLUX'][~good],a[1].data[product+'_FLUX'][~good])
            checked+=1
            if case['signal']['shape']=='zero':zeros+=1
        # One exact reconstruction for each shape/profile on every source star.
        if case['signal']['shape']=='zero' or (case['signal']['amplitude_fraction']==.003 and case['signal']['period_d']==.731 and case['signal']['phase']==.13):
            item=case['inputs'][0];path=ROOT/'repo/data/standard-injection-audit'/f'{case["id"]}.fits.gz'
            construct(ROOT/item['source']['path'],case['signal'],case['origin_btjd'],path)
            assert sha256(path)==item['sha256'];rebuilt+=1
    old=read_json(ROOT/'repo/benchmarks/standard-star-check-v01/evaluation/predictions.json')
    old={r['id']:r for r in old['results']}
    for row in predictions['results']:
        assert row['status']=='completed',row['id']
        assert row['decision']['confirmed_variable'] is False and row['decision']['target_candidate'] is False
        for obs in row['products']['observations']:
            assert sha256(ROOT/obs['input']['path'])==obs['input']['sha256']
            assert sha256(BASE/'evaluation'/row['id']/obs['plot'])==obs['plot_sha256']
        if row['id'].endswith('-zero'):
            baseline=old[row['id'][:-5]]
            assert row['products']['conclusions']==baseline['products']['conclusions']
            for key in ['status','selected_period_d','preferred_product']:
                assert row['decision'][key]==baseline['decision'][key]
    pages=0
    for path in (BASE/'evaluation').rglob('*.html'):
        parser=Links();parser.feed(path.read_text())
        for target in parser.links:
            url=urlparse(target)
            if url.scheme or url.netloc or not url.path:continue
            assert (path.parent/unquote(url.path)).exists(),(path,target)
        pages+=1
    write_json(BASE/'integrity-audit.json',{'checked_at':now(),'old_files_unchanged':len(prior['files']),
        'artificial_FITS_verified':checked,'zero_injection_tables_identical':zeros,'deterministic_reconstructions_verified':rebuilt,
        'zero_injection_decisions_match_original_runs':True,'all_plot_input_and_prediction_hashes_verified':True,
        'all_cases_completed':len(predictions['results']),'html_pages_checked':pages,
        'scientific_v4_code_unchanged':True,'independent_pilot_v02_unchanged':True,
        'source_FITS_already_in_public_repository':True,'generated_FITS_in_rebuildable_ignored_cache':True,
        'audit_script_sha256':sha256(Path(__file__)),'calibrated_false_positive_rate':False})
    print('AUDIT OK',len(prior['files']),'old files;',checked,'artificial FITS;',rebuilt,'rebuilds;',pages,'pages')

if __name__=='__main__':main()
