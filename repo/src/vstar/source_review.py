"""Conservative source review after frozen period adjudication.

A selected period is not target attribution. Harmonic pixel maps are exploratory,
not a PRF fit, astrometric uncertainty, or calibrated false-positive probability.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .photometry import read_lightcurve, bin_lightcurve, LightCurve
from .auxiliary import read_auxiliary
from .screening import detrend, check_auxiliary
from .screening_v3 import ScreeningConfig
from .io import now, sha256


@dataclass(frozen=True)
class SourceReviewConfig:
    harmonics: int = 4
    min_segment_cycles: float = 3.
    target_radius_pixels: float = 1.
    neighbor_radius_pixels: float = .75
    peak_stability_pixels: float = 1.
    neighbor_period_tolerance: float = .02

    def __post_init__(self):
        if not 1<=self.harmonics<=8 or self.min_segment_cycles<3:
            raise ValueError('Insufficient source-map model or cycle coverage')
        if not all(np.isfinite(x) and x>0 for x in [self.target_radius_pixels,self.neighbor_radius_pixels,self.peak_stability_pixels,self.neighbor_period_tolerance]):
            raise ValueError('Invalid source comparison threshold')


def harmonic_map(time, cube, reference, period, harmonics=4):
    """Project pixel Fourier coefficients onto the light curve's coherent shape."""
    time=np.asarray(time,float);reference=np.asarray(reference,float);cube=np.asarray(cube,float)
    if len(time)<100 or cube.ndim!=3 or len(cube)!=len(time) or len(reference)!=len(time):
        raise ValueError('Insufficient or inconsistent pixel samples')
    if not np.all(np.isfinite(cube)) or not np.all(np.isfinite(reference)) or not np.all(np.diff(time)>0) or period<=0:
        raise ValueError('Need finite, strictly ordered pixel data and positive period')
    u=(time-time.mean())/np.ptp(time);gaps=np.cumsum(np.r_[0,np.diff(time)>.5])
    baseline=[np.ones(len(time)),u,u*u,u*u*u]+[(gaps==g).astype(float) for g in np.unique(gaps)[1:]]
    phase=2*np.pi*((time-time[0])/period%1)
    waves=[fn(k*phase) for k in range(1,harmonics+1) for fn in (np.sin,np.cos)]
    design=np.column_stack(baseline+waves)
    coef=np.linalg.lstsq(design,cube.reshape(len(time),-1),rcond=None)[0][-2*harmonics:]
    ref=np.linalg.lstsq(design,reference,rcond=None)[0][-2*harmonics:]
    norm=np.linalg.norm(ref)
    if not np.isfinite(norm) or norm<1e-10:raise ValueError('No usable coherent reference')
    return (ref/norm@coef).reshape(cube.shape[1:])


def summarize_maps(maps,target_pixel,neighbors,period,cfg=None):
    cfg=cfg or SourceReviewConfig();records=[]
    target_pixel=np.asarray(target_pixel,float)
    if not np.isfinite(target_pixel).all():raise ValueError('Invalid target pixel coordinate')
    for name,signal in maps.items():
        if not np.all(np.isfinite(signal)) or signal.max()<=0:raise ValueError('No positive coherent map')
        y,x=np.unravel_index(np.argmax(signal),signal.shape)
        records.append({'segment':name,'peak_pixel':[int(x),int(y)],
                        'target_distance_pixels':float(np.hypot(x-target_pixel[0],y-target_pixel[1]))})
    if set(maps)!={'full','first_half','second_half'}:raise ValueError('Require full and both temporal halves')
    separation=max(np.linalg.norm(np.array(a['peak_pixel'])-b['peak_pixel']) for a in records for b in records)
    stable=bool(separation<=cfg.peak_stability_pixels)
    compatible=[]
    for neighbor in neighbors:
        p=neighbor.get('period_d');xy=np.asarray(neighbor['pixel'],float)
        if p is None or not np.isfinite(p) or p<=0 or not np.isfinite(xy).all():continue
        period_error=min(abs(period/(p*h)-1) for h in [.5,1,2])
        distances=[float(np.linalg.norm(np.array(r['peak_pixel'])-xy)) for r in records]
        if period_error<=cfg.neighbor_period_tolerance and max(distances)<=cfg.neighbor_radius_pixels:
            compatible.append(dict(neighbor,peak_distances_pixels=distances,period_fractional_error=period_error))
    away=all(r['target_distance_pixels']>cfg.target_radius_pixels for r in records)
    near=all(r['target_distance_pixels']<=cfg.target_radius_pixels for r in records)
    status=('inconsistent_pixel_maps' if not stable else 'likely_neighbor_contamination' if away and compatible
            else 'off_target_signal' if away else 'consistent_with_target' if near else 'unresolved_location')
    return {'status':status,'target_pixel':target_pixel.tolist(),'segments':records,'stable_peak':stable,
            'maximum_peak_displacement_pixels':float(separation),'compatible_neighbors':compatible,
            'note':'Peak pixels from full/half data are not independent measurements or localization uncertainties. Unresolved neighbors and common instrumental effects remain possible.'}


def pixel_review(tpf,lightcurve,target,period,plot,cfg=None):
    cfg=cfg or SourceReviewConfig();lightcurve=Path(lightcurve);tpf=Path(tpf)
    lc=read_lightcurve(lightcurve)
    with fits.open(tpf,memmap=False) as h:
        meta=dict(h[0].header)|dict(h[1].header)
        if meta.get('TICID')!=lc.metadata['TICID'] or meta.get('SECTOR')!=lc.metadata['SECTOR']:
            raise ValueError('Pixel/lightcurve identity or sector mismatch')
        for key in ['TIMESYS','BJDREFI','BJDREFF']:
            if meta.get(key)!=lc.metadata.get(key):raise ValueError('Pixel/lightcurve time reference mismatch')
        data=h[1].data;time=np.asarray(data['TIME'],float);cube=np.asarray(data['FLUX'],float)
        good=np.isfinite(time)&(data['QUALITY']==0)&np.isfinite(cube).all(axis=(1,2))
        time,cube=time[good],cube[good];wcs=WCS(h[2].header)
        aperture=np.asarray(h[2].data)
    right=np.clip(np.searchsorted(lc.time,time),0,len(lc.time)-1);left=np.maximum(right-1,0)
    valid=(time>=lc.time.min())&(time<=lc.time.max())&(np.minimum(abs(time-lc.time[left]),abs(time-lc.time[right]))<=.015)
    time,cube=time[valid],cube[valid]
    if len(time)<200 or not np.all(np.diff(time)>0):raise ValueError('Insufficient matching ordered pixel samples')
    reference=np.interp(time,lc.time,lc.flux);mid=(time[0]+time[-1])/2
    masks={'full':np.ones(len(time),bool),'first_half':time<=mid,'second_half':time>mid}
    maps={}
    for name,mask in masks.items():
        if mask.sum()<100 or np.ptp(time[mask])/period<cfg.min_segment_cycles:raise ValueError('Insufficient pixel segment cycles: '+name)
        maps[name]=harmonic_map(time[mask],cube[mask],reference[mask],period,cfg.harmonics)
    xy=list(map(float,wcs.world_to_pixel_values(target['ra_deg'],target['dec_deg'])))
    neighbors=[]
    for n in target.get('vsx_neighbors',[]):
        p=float(n.get('Period',0) or 0)
        neighbors.append({'name':n['Name'],'period_d':p or None,
            'pixel':list(map(float,wcs.world_to_pixel_values(float(n['RA2000']),float(n['Declination2000']))))})
    result=summarize_maps(maps,xy,neighbors,period,cfg)
    fig,axes=plt.subplots(1,4,figsize=(15,4),layout='constrained')
    axes[0].imshow(np.log10(np.maximum(np.median(cube,axis=0),1)),origin='lower',cmap='magma');axes[0].set_title('Median measured pixels')
    for ax,(name,signal) in zip(axes[1:],maps.items()):
        limit=max(np.max(abs(signal)),1e-10);ax.imshow(signal,origin='lower',cmap='coolwarm',vmin=-limit,vmax=limit);ax.set_title(name.replace('_',' '))
    for ax in axes:
        ax.plot(*xy,'o',mfc='none',mec='lime',ms=10)
        for n in neighbors:ax.plot(*n['pixel'],'x',color='cyan')
        if np.any(aperture&2) and np.any((aperture&2)==0):ax.contour((aperture&2)>0,levels=[.5],colors='white',linewidths=.7)
        ax.set(xlim=(-.5,aperture.shape[1]-.5),ylim=(-.5,aperture.shape[0]-.5),xlabel='Pixel column',ylabel='Pixel row')
    fig.suptitle(f'P={period:.7f} d | {result["status"]} | green: target; cyan: catalog objects')
    fig.savefig(plot,dpi=130);plt.close(fig)
    result.update(period_d=period,tic=lc.metadata['TICID'],sector=lc.metadata['SECTOR'],config=asdict(cfg),
                  pixels={'path':str(tpf),'sha256':sha256(tpf)},lightcurve={'path':str(lightcurve),'sha256':sha256(lightcurve)},
                  plot=Path(plot).name,plot_sha256=sha256(plot),matched_samples=len(time))
    return result


def route_review(selected_period,observations,errors=None):
    """A manual-review queue, never an automatic declaration of a variable/new star."""
    pixels=[o['pixels'] for o in observations if o.get('pixels')]
    instrument=[];centroid=[];missing=[]
    for o in observations:
        for product,checks in o.get('auxiliary',{}).items():
            for check in checks:
                if check.get('source_caution'):
                    item=dict(check,sector=o['sector'],product=product)
                    (centroid if check['name'].startswith('MOM_CENTR') else instrument).append(item)
            observed={c['name'] for c in checks if c['status'] in {'correlated_periodic_channel','no_strong_correlation'}}
            # Missing or constant diagnostic channels do not clear the instrumental check.
            absent={'SAP_BKG','POS_CORR1','POS_CORR2'}-observed
            if absent:missing.append({'sector':o['sector'],'product':product,'channels':sorted(absent)})
    statuses={p['status'] for p in pixels}
    source=('likely_neighbor_contamination' if 'likely_neighbor_contamination' in statuses else
            'off_target_signal' if 'off_target_signal' in statuses else
            'instrument_caution' if instrument else
            'target_supported_at_tess_resolution' if len(pixels)==len(observations)>=2 and statuses=={'consistent_with_target'} else
            'source_evidence_incomplete')
    route=('analysis_failed' if errors else 'exclude_signal_from_target' if source in {'likely_neighbor_contamination','off_target_signal'} else
           'instrument_review_required' if instrument else 'period_review_required' if selected_period is None else
           'source_evidence_required' if source!='target_supported_at_tess_resolution' or missing else 'manual_target_review')
    return {'route':route,'source_status':source,'eligible_for_manual_target_review':route=='manual_target_review',
            'instrument_cautions':instrument,'centroid_cautions':centroid,'missing_auxiliary':missing,
            'confirmed_variable':False,'submission_ready':False,'novelty_assessed':False,
            'note':'No warning does not prove an astrophysical origin. Pixel agreement is limited by TESS resolution; catalog completeness and unresolved blends need manual review.'}


def review_case(inputs,decision,target,out,root=None,diagnostic_period=None,cfg=None):
    root=Path(root or '.');out=Path(out);out.mkdir(parents=True,exist_ok=False);cfg=cfg or SourceReviewConfig()
    selected=decision.get('selected_period_d');period=selected if selected is not None else diagnostic_period
    result={'created_at':now(),'config':asdict(cfg),'period_d':period,'selected_period_d':selected,
            'period_usage':'selected_by_v4' if selected is not None else 'diagnostic_only_not_selected',
            'observations':[],'errors':[]}
    if period is not None and (not np.isfinite(period) or period<=0):raise ValueError('Invalid review period')
    identities=set();sectors=set()
    for item in inputs:
        try:
            path=root/item['path']
            if sha256(path)!=item['sha256']:raise ValueError('Lightcurve hash mismatch')
            raw=read_lightcurve(path);sector=raw.metadata['SECTOR'];identities.add(raw.metadata['TICID'])
            if len(identities)!=1 or sector in sectors or sector!=item['sector']:raise ValueError('Mixed targets or duplicate/mismatched sectors')
            sectors.add(sector);obs={'sector':sector,'input':item,'auxiliary':{},'pixels':None}
            if period is not None:
                auxiliary=read_auxiliary(path,10)
                for product in ['SAP','PDCSAP']:
                    clean,_=detrend(bin_lightcurve(read_lightcurve(path,product+'_FLUX'),10))
                    obs['auxiliary'][product]=check_auxiliary(clean,auxiliary,period,ScreeningConfig())
                if item.get('pixels'):
                    pixels=root/item['pixels']['path']
                    if sha256(pixels)!=item['pixels']['sha256']:raise ValueError('Pixel hash mismatch')
                    if target is None:raise ValueError('Missing target coordinates for source review')
                    obs['pixels']=pixel_review(pixels,path,target,period,out/f's{sector}-pixels.png',cfg)
                    for key in ['pixels','lightcurve']:obs['pixels'][key]['path']=str(Path(obs['pixels'][key]['path']).resolve().relative_to(root.resolve()))
            result['observations'].append(obs)
        except Exception as exc:result['errors'].append({'path':item['path'],'error':str(exc)})
    result['conclusion']=route_review(selected,result['observations'],result['errors'])
    return result


def main():
    import argparse
    from .io import read_json,write_json
    from .reports import page
    parser=argparse.ArgumentParser(description='来源审查；需先有 v4 周期判断，不确认发现')
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    args=parser.parse_args();spec=read_json(args.manifest)
    # Expected manifest: inputs, decision, target, optional diagnostic_period.
    result=review_case(spec['inputs'],spec['decision'],spec.get('target'),args.output,args.root,spec.get('diagnostic_period'))
    write_json(args.output/'source-review.json',result)
    body='<h1>周期信号的来源审查</h1><p>状态：'+result['conclusion']['route']+'</p><p>来源结论：'+result['conclusion']['source_status']+'</p>'
    body+='<p>进入人工复核不等于确认目标变光或新发现。缺少像素或辅助证据不会自动通过。</p>'
    for obs in result['observations']:
        if obs['pixels']:body+=f'<img src="{obs["pixels"]["plot"]}" alt="全段与前后半段的周期信号位置">'
    body+='<p><a href="source-review.json">完整判据与未完成事项</a></p>'
    (args.output/'index.html').write_text(page('来源审查',body))
    print(args.output.resolve()/'index.html')
    if result['errors']:raise SystemExit(2)


if __name__=='__main__':main()
