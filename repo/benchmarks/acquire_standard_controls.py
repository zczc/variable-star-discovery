"""A fixed three-star standard challenge; not a validated quiet-star denominator."""
from pathlib import Path
import json
from astropy.coordinates import SkyCoord
from astropy.io import fits
from vstar.io import read_json,write_json,sha256,now
from vstar.network import ArchiveClient
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'repo/benchmarks/standard-star-check-v01'


def main():
    protocol=read_json(OUT/'protocol.json')
    if (OUT/'input-manifest.json').exists(): raise FileExistsError('Do not replace acquisition')
    client=ArchiveClient(ROOT/'repo/data/standard-star-check-v01',attempts=2,max_bytes=100_000_000)
    manifest={'created_at':now(),'protocol_sha256':sha256(OUT/'protocol.json'),'cases':[]}
    for star in protocol['targets']:
        case={'id':star['id'],'name':star['name'],'label':'literature_bounded_standard_not_validated_TESS_negative','inputs':[],'errors':[]}
        try:
            pos=SkyCoord(star['ra_hms'],star['dec_dms'],unit=('hourangle','deg'))
            request={'service':'Mast.Catalogs.Tic.Cone','params':{'ra':pos.ra.deg,'dec':pos.dec.deg,'radius':10/3600},'format':'json','pagesize':1000,'page':1}
            tic,receipt=client.query('MAST','POST','https://mast.stsci.edu/api/v0/invoke',data={'request':json.dumps(request)})
            write_json(OUT/(star['id']+'-tic.json'),{'response':tic,'receipt':receipt})
            if tic['paging']['pagesFiltered']>1 or len(tic['data'])!=tic['paging']['rowsFiltered']:raise ValueError('Incomplete TIC neighborhood')
            matched=[(pos.separation(SkyCoord(r['ra'],r['dec'],unit='deg')).arcsec,r) for r in tic['data']]
            matched=sorted(matched,key=lambda x:x[0]); close=[(s,r) for s,r in matched if s<2]
            if len(close)!=1:raise ValueError('Need exactly one TIC within 2 arcsec of paper J2000 position')
            sep,target=close[0];identity=str(target['ID'])
            case.update(tic=identity,identity_sep_arcsec=float(sep),ra_deg=target['ra'],dec_deg=target['dec'])
            filters=[{'paramName':k,'values':[v]} for k,v in [('obs_collection','TESS'),('provenance_name','SPOC'),('dataproduct_type','timeseries'),('target_name',identity)]]
            rows,receipts=client.mast_rows(filters)
            write_json(OUT/(star['id']+'-observations.json'),{'observations':rows,'receipts':receipts})
            sectors={int(r['sequence_number']):r for r in rows if r.get('dataURL','').endswith('_lc.fits') and '_fast' not in r['dataURL']}
            if len(sectors)<2:raise ValueError('Fewer than two supported non-fast SPOC sectors')
            ordered=sorted(sectors,key=lambda s:(sectors[s]['t_min'],sectors[s]['dataURL']))
            for sector in [ordered[0],ordered[-1]]:
                uri=sectors[sector]['dataURL'];path,digest=client.download(uri)
                with fits.open(path) as h:
                    if str(h[0].header['TICID'])!=identity or int(h[0].header['SECTOR'])!=sector:raise ValueError('FITS identity mismatch')
                case['inputs'].append({'path':str(path.relative_to(ROOT)),'sector':sector,'uri':uri,'sha256':digest})
            case['status']='acquired'
        except Exception as exc:
            case.update(status='unavailable',unavailable_reason=str(exc));case['errors'].append(str(exc))
        manifest['cases'].append(case);write_json(OUT/'input-manifest.json',manifest)
        print(case['name'],case['status'],case.get('tic'),case.get('unavailable_reason'),flush=True)
    manifest['completed_at']=now();write_json(OUT/'input-manifest.json',manifest)

if __name__=='__main__':main()
