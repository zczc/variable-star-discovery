"""Late primary-catalog checks; never changes the frozen list or detector."""
import argparse,csv,hashlib,io,json,time,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
from select_discovery_2000 import ROOT,OUT,read_json,write_json,now

JOBS=[('tars-zenodo','tars_table_2.csv.zip'),('rotation2024-zenodo','complete.csv')]

def download(job):
    name,key=job;metadata=read_json(OUT/'sources'/name/'attempt-1.json');data=json.loads(metadata['body']);item=next(f for f in data['files'] if f['key']==key)
    dest=OUT/'late-catalogs'/name;dest.mkdir(parents=True,exist_ok=True);path=dest/key
    if path.exists():
        with path.open('rb') as f:
            if 'md5:'+hashlib.file_digest(f,'md5').hexdigest()==item['checksum']:return
    for attempt in range(1,4):
        record={'at':now(),'url':item['links']['self'],'expected_bytes':item['size'],'expected_checksum':item['checksum']};tmp=path.with_suffix(path.suffix+'.part')
        try:
            with requests.get(item['links']['self'],stream=True,timeout=(15,90)) as response:
                record['status_code']=response.status_code;response.raise_for_status()
                with tmp.open('wb') as f:
                    for block in response.iter_content(1024*1024):f.write(block)
            assert tmp.stat().st_size==item['size']
            with tmp.open('rb') as f:assert 'md5:'+hashlib.file_digest(f,'md5').hexdigest()==item['checksum']
            tmp.replace(path)
            with path.open('rb') as f:record.update(sha256=hashlib.file_digest(f,'sha256').hexdigest(),status='verified')
            write_json(dest/f'download-{attempt}.json',record);print(name,'verified',item['size'],flush=True);return
        except Exception as exc:
            record.update(status='failed',error=str(exc));write_json(dest/f'download-{attempt}.json',record)
    raise RuntimeError(name+' catalogue could not be downloaded')

def match():
    targets={c['tic'] for c in read_json(OUT/'targets.json')['cases']};aliases={'160097983':'1102716939'};wanted=targets|set(aliases)
    for name,key in JOBS:
        path=OUT/'late-catalogs'/name/key
        if not path.exists():continue
        if key.endswith('.zip'):
            archive=zipfile.ZipFile(path);print(archive.namelist(),flush=True);file=archive.open(next(n for n in archive.namelist() if n.endswith('.csv')));stream=io.TextIOWrapper(file)
        else:stream=path.open()
        reader=csv.DictReader(stream);print(name,'columns',reader.fieldnames,flush=True);matches=[];count=0;control=[]
        # Inspect columns before choosing the actual identity field.
        idfield=next((f for f in reader.fieldnames if f.lower() in ['tic','tic_id','ticid']),None)
        if idfield is None:raise ValueError('Unrecognized TIC column')
        for row in reader:
            count+=1
            if count<=3:control.append(row)
            tic=row[idfield].strip().removesuffix('.0')
            if tic in wanted:matches.append({'matched_tic':tic,'project_tic':aliases.get(tic,tic),'row':row})
        write_json(OUT/f'{name}-crossmatch.json',{'at':now(),'catalogue_rows':count,'idfield':idfield,'columns':reader.fieldnames,'matches':matches,'controls_from_full_table':control,'source':str(path.relative_to(ROOT)),'note':'Full exact-TIC crossmatch after analysis; catalogue row quality/period-adoption flags must be interpreted using the paper. No selection or science threshold changes.'})
        print(name,count,len(matches),'detections',[m['project_tic'] for m in matches if (OUT/'followup-results'/f'{m["project_tic"]}.json').exists()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['download','match']);a=p.parse_args()
    if a.action=='download':
        with ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(download,JOBS))
    else:match()
