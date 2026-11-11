"""Experimental v4 period adjudication. Does not attribute or confirm variability."""
from dataclasses import dataclass,asdict
from pathlib import Path
import numpy as np
from .photometry import read_lightcurve,bin_lightcurve
from .screening import detrend,template_predict
from .eclipse_events import phase_anchor,measure_events
from .products import review_products
from .io import write_json,now,code_fingerprint
from .reports import page


@dataclass(frozen=True)
class AdjudicationConfig:
    period_tolerance: float = .01
    minimum_pairs: int = 3
    minimum_relative_difference: float = .01
    minimum_standard_error_ratio: float = 3.
    minimum_same_sign_fraction: float = .75
    phase_grid: int = 256

    def __post_init__(self):
        if not 0<self.period_tolerance<.1 or not 0<self.minimum_relative_difference<1:
            raise ValueError('Invalid comparison tolerance')
        if self.minimum_pairs<3 or self.phase_grid<32 or self.minimum_standard_error_ratio<=0 or not .5<self.minimum_same_sign_fraction<=1:
            raise ValueError('Insufficient event evidence or phase resolution')


def pair_contrast(events,step,start_mod,modulus,cfg):
    points={r['cycle']:r for r in events if r['status']=='measured'}
    pairs=[(i,i+step) for i in sorted(points) if i%modulus==start_mod and i+step in points]
    delta=np.array([points[a]['depth_fraction']-points[b]['depth_fraction'] for a,b in pairs])
    depth=np.array([points[i]['depth_fraction'] for pair in pairs for i in pair])
    out={'pairs':pairs,'count':len(pairs),'different':False,'sufficient':len(pairs)>=cfg.minimum_pairs}
    if not out['sufficient']:return out
    mean=float(delta.mean());se=float(delta.std(ddof=1)/np.sqrt(len(delta)))
    scale=max(float(np.median(abs(depth))),1e-12)
    threshold=max(cfg.minimum_relative_difference*scale,cfg.minimum_standard_error_ratio*se)
    sign=float(np.mean(np.sign(delta)==np.sign(mean)))
    out.update(mean_difference=mean,standard_error_proxy=se,threshold=threshold,same_sign_fraction=sign,
               different=bool(abs(mean)>threshold and sign>=cfg.minimum_same_sign_fraction))
    return out


def event_alias_check(lc,period,cfg=None):
    cfg=cfg or AdjudicationConfig()
    anchor=phase_anchor(lc,period)
    measured,_=measure_events(lc,period/2,anchor)
    events=measured['events']
    half=pair_contrast(events,1,0,2,cfg)
    primary=pair_contrast(events,2,0,4,cfg)
    secondary=pair_contrast(events,2,1,4,cfg)
    # Both minima must actually dim; a sine's maximum is not a secondary eclipse.
    groups=[[e['depth_fraction'] for e in events if e['status']=='measured' and e['cycle']%2==parity] for parity in [0,1]]
    positive=all(g and np.median(g)>0 for g in groups)
    passed=(positive and half['different'] and primary['sufficient'] and secondary['sufficient']
            and not primary['different'] and not secondary['different'])
    return {'passed':bool(passed),'period_d':period,'epoch_input_time':anchor,'half_cycle':half,
            'primary_same_family':primary,'secondary_same_family':secondary,'positive_minima':bool(positive),
            'events':events,'note':'Same local windows for all contrasts; thresholds are uncalibrated development rules, not significance or a full orbital model.'}


def transfer_short_epoch(training,target,period,cfg=None):
    """Freeze P and template from a long epoch. Calibrate phase on first short cycle only.

The later short-epoch samples are held out from offset/amplitude/phase fitting.
This diagnostic NEVER promotes a short epoch to independent period detection.
"""
    cfg=cfg or AdjudicationConfig();train,_=detrend(bin_lightcurve(training,10));test=bin_lightcurve(target,10)
    relative=(test.time-test.time[0])/period
    calibration=relative<1;holdout=~calibration
    base={'period_d':period,'training_samples':len(train.time),'calibration_samples':int(calibration.sum()),
          'holdout_samples':int(holdout.sum()),'independent_period_measurement':False}
    if np.ptp(train.time)/period<3 or not 1.25<=np.ptp(test.time)/period<3 or min(calibration.sum(),holdout.sum())<50:
        return dict(base,status='insufficient_transfer_coverage'),None
    phase=((train.time-train.time[0])/period)%1
    grid=(np.arange(96)+.5)/96
    model,coverage=template_predict(phase,train.flux,train.error,grid,96)
    if coverage<.8:return dict(base,status='insufficient_training_template'),None
    def pattern(offset):
        ph=(relative+offset)%1
        return np.interp(ph,np.r_[grid-1,grid,grid+1],np.tile(model,3))
    # First-cycle fit, including phase search, cannot use the held-out brightness.
    trend=np.column_stack([np.ones(len(test.time)),relative])
    weights=1/test.error[calibration]
    null_coef=np.linalg.lstsq(trend[calibration]*weights[:,None],test.flux[calibration]*weights,rcond=None)[0]
    best=None
    for offset in np.arange(cfg.phase_grid)/cfg.phase_grid:
        design=np.column_stack([trend,pattern(offset)])
        coef=np.linalg.lstsq(design[calibration]*weights[:,None],test.flux[calibration]*weights,rcond=None)[0]
        if coef[-1]<=0:continue
        loss=float(np.sum(((test.flux[calibration]-design[calibration]@coef)*weights)**2))
        if best is None or loss<best[0]:best=(loss,float(offset),coef,design@coef)
    if best is None:return dict(base,status='no_positive_template_fit'),None
    _,offset,coef,pred=best
    y=test.flux[holdout];err=test.error[holdout]
    residual=float(np.sum(((y-pred[holdout])/err)**2))
    null=float(np.sum(((y-(trend@null_coef)[holdout])/err)**2))
    centered=float(np.sum(((y-np.average(y,weights=1/err**2))/err)**2))
    corr=float(np.corrcoef(y,pred[holdout])[0,1]) if min(np.std(y),np.std(pred[holdout]))>0 else 0.
    result=dict(base,status='evaluated',phase_offset_fit_first_cycle=offset,template_amplitude=float(coef[-1]),
        holdout_gain_vs_extrapolated_linear=1-residual/max(null,1e-30),holdout_gain_vs_heldout_mean=1-residual/max(centered,1e-30),
        holdout_correlation=corr,note='Period/template frozen from another epoch; phase and affine baseline fit only the first short cycle. No unique period, coherent inter-year phase connection or false-alarm probability established.')
    return result,(test,pred,calibration)


def adjudicate(row,root=None,cfg=None):
    cfg=cfg or AdjudicationConfig();root=Path(root or '.')
    result={'created_at':now(),'config':asdict(cfg),'selected_period_d':None,'preferred_product':None,
            'status':'unresolved','source_status':'needs_independent_source_review','confirmed_variable':False,
            'target_candidate':False,'event_checks':[],'short_epoch_checks':[],
            'note':'Selection concerns a photometric period only; source, novelty and submission readiness are not assessed.'}
    if row.get('errors'):
        result['status']='analysis_failed';return result
    conclusions=row['conclusions'];selected={n:c['selected_period_d'] for n,c in conclusions.items() if c.get('selected_period_d')}
    if len(selected)==2 and abs(selected['SAP']/selected['PDCSAP']-1)<=cfg.period_tolerance:
        result.update(selected_period_d=float(np.median(list(selected.values()))),preferred_product='both',status='product_agreement')
    elif len(selected)==1:
        product,p=next(iter(selected.items()));other='PDCSAP' if product=='SAP' else 'SAP'
        if conclusions[other]['period_status'] not in {'cross_epoch_harmonic_conflict','half_double_ambiguous','preferred_lightcurve_cycle'}:
            result['status']='nonharmonic_or_missing_product_support'
        else:
            checks=[]
            for obs in row['observations']:
                alternatives=obs['products'][other]['result']['candidates']
                support=any(c['qualifies'] and abs(c['period_d']/p-1)<=cfg.period_tolerance for c in alternatives)
                local_p=obs['products'][product]['result']['selected_period_d']
                if not support or local_p is None:
                    checks.append({'sector':obs['sector'],'passed':False,'reason':'Same period lacks qualified support in both products'});continue
                try:
                    lc=read_lightcurve(root/obs['input']['path'],product+'_FLUX')
                    check=event_alias_check(lc,local_p,cfg);check.update(sector=obs['sector'],product=product)
                    checks.append(check)
                except ValueError as exc:checks.append({'sector':obs['sector'],'passed':False,'reason':str(exc)})
            result['event_checks']=checks
            if len(checks)>=2 and all(c['passed'] for c in checks):
                result.update(selected_period_d=p,preferred_product=product,status='event_supported_period_product_caution')
    # Additional diagnostic for genuinely short epochs, never changes selected_period_d.
    for product in ['SAP','PDCSAP']:
        anchors=[o for o in row['observations'] if o['products'][product]['result'].get('selected_period_d')]
        if not anchors:continue
        anchor=max(anchors,key=lambda o:o['products'][product]['baseline']['span_d'])
        period=anchor['products'][product]['result']['selected_period_d']
        for obs in row['observations']:
            if obs is anchor or obs['products'][product]['baseline']['span_d']/period>=3:continue
            diagnostic,_=transfer_short_epoch(read_lightcurve(root/anchor['input']['path'],product+'_FLUX'),
                read_lightcurve(root/obs['input']['path'],product+'_FLUX'),period,cfg)
            result['short_epoch_checks'].append(dict(diagnostic,product=product,training_sector=anchor['sector'],target_sector=obs['sector']))
    return result


def review_files(paths,out):
    row=review_products(paths,out);decision=adjudicate(row)
    write_json(out/'adjudication.json',decision)
    (out/'index.html').rename(out/'products.html')
    body=f'<h1>第四版周期复核</h1><p>状态：{decision["status"]}；优选光变周期：{decision["selected_period_d"]} 天。</p>'
    body+='<div class="notice">优选周期不等于确认目标变光，更不等于新发现。产品争议、来源和短时段限制仍需人工检查。</div>'
    body+='<p><a href="products.html">两产品的原始报告与图表</a> · <a href="adjudication.json">完整规则与逐事件依据</a></p>'
    (out/'index.html').write_text(page('第四版周期复核',body))
    return row,decision
