"""Local eclipse measurements for manual alias review, not automatic classification."""
from dataclasses import dataclass
import numpy as np
from .screening import template_predict, validate_curve


@dataclass(frozen=True)
class EventConfig:
    core_half_width: float = .06
    side_inner: float = .35
    side_outer: float = .45
    min_core_points: int = 3
    min_side_points: int = 3
    bootstrap_draws: int = 2000
    bootstrap_seed: int = 6137

    def __post_init__(self):
        if not 0 < self.core_half_width < self.side_inner < self.side_outer < .5:
            raise ValueError('Event windows must be disjoint and inside adjacent event midpoints')
        if self.min_core_points < 2 or self.min_side_points < 2 or self.bootstrap_draws < 100:
            raise ValueError('Insufficient event sampling or bootstrap draws')


def phase_anchor(lc, period):
    validate_curve(lc)
    if not np.isfinite(period) or period <= 0:
        raise ValueError('Period must be positive')
    grid=(np.arange(192)+.5)/192
    phase=((lc.time-lc.time[0])/period)%1
    model,coverage=template_predict(phase,lc.flux,lc.error,grid,192)
    if coverage < .8:
        raise ValueError('Insufficient full-data phase coverage to locate a minimum')
    return float(lc.time[0]+period*grid[np.argmin(model)])


def measure_events(lc, spacing, epoch, config=None):
    """Linearly interpolate local side windows across each predicted minimum.

Time is copied in its input standard (TESS BTJD); no HJD conversion is implied.
Use raw cadence so broad eclipses in short-period binaries retain samples.
"""
    cfg=config or EventConfig();validate_curve(lc)
    if not np.isfinite([spacing,epoch]).all() or spacing <= 0:
        raise ValueError('Need positive finite spacing and a finite epoch')
    records=[];profiles=[]
    for cycle in range(int(np.ceil((lc.time[0]-epoch)/spacing)),int(np.floor((lc.time[-1]-epoch)/spacing))+1):
        center=epoch+cycle*spacing;dt=(lc.time-center)/spacing
        core=abs(dt)<=cfg.core_half_width
        before=(dt>=-cfg.side_outer)&(dt<=-cfg.side_inner)
        after=(dt>=cfg.side_inner)&(dt<=cfg.side_outer)
        row={'cycle':cycle,'center_input_time':float(center),'core_points':int(core.sum()),
             'before_points':int(before.sum()),'after_points':int(after.sum())}
        if core.sum()<cfg.min_core_points or min(before.sum(),after.sum())<cfg.min_side_points:
            records.append(dict(row,status='missing_bracketing_data'));continue
        # Medians of a linear function correspond to the median sample time.
        t1,t2=np.median(dt[before]),np.median(dt[after])
        y1,y2=np.median(lc.flux[before]),np.median(lc.flux[after])
        near=abs(dt)<=cfg.side_outer
        baseline=y1+(y2-y1)*(dt-t1)/(t2-t1)
        level=1+baseline
        if np.any(level[near]<=0):
            records.append(dict(row,status='nonpositive_local_baseline'));continue
        decrease=(baseline[core]-lc.flux[core])/level[core]
        depth=float(np.mean(decrease))
        measurement_error=float(np.sqrt(np.sum((lc.error[core]/level[core])**2))/core.sum())
        row.update(status='measured',depth_fraction=depth,point_error_only=measurement_error,
                   local_slope_per_day=float((y2-y1)/(t2-t1)/spacing))
        records.append(row)
        profiles.append({'cycle':cycle,'phase_from_event':dt[near],
                         'relative_decrease':(baseline[near]-lc.flux[near])/level[near]})
    measured={r['cycle']:r for r in records if r['status']=='measured'}
    pairs=[{'even_cycle':i,'odd_cycle':i+1,'difference':measured[i]['depth_fraction']-measured[i+1]['depth_fraction']}
           for i in sorted(measured) if i%2==0 and i+1 in measured]
    summary={'measured_events':len(measured),'missing_events':len(records)-len(measured),'adjacent_pairs':len(pairs),
             'even_depth_median':None,'odd_depth_median':None,'paired_difference':None,'bootstrap_interval_95':None,
             'note':'Adjacent-event bootstrap is descriptive; residual correlation and baseline uncertainty are not calibrated. Equal depths alone cannot establish an orbit.'}
    for parity,name in [(0,'even_depth_median'),(1,'odd_depth_median')]:
        vals=[r['depth_fraction'] for i,r in measured.items() if i%2==parity]
        if vals:summary[name]=float(np.median(vals))
    if len(pairs)>=3:
        delta=np.array([p['difference'] for p in pairs]);rng=np.random.default_rng(cfg.bootstrap_seed)
        samples=rng.choice(delta,(cfg.bootstrap_draws,len(delta)),replace=True).mean(axis=1)
        summary.update(paired_difference=float(delta.mean()),bootstrap_interval_95=np.percentile(samples,[2.5,97.5]).tolist(),
                       first_half_difference=float(delta[:max(1,len(delta)//2)].mean()),
                       second_half_difference=float(delta[max(1,len(delta)//2):].mean()))
    return {'spacing_d':float(spacing),'epoch_input_time':float(epoch),'events':records,'pairs':pairs,'summary':summary},profiles
