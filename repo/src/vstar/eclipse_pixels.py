"""Event-bracketed difference images; exploratory, not a calibrated PRF localization."""
import numpy as np


def difference_image(time, cube, period, epoch, duration, min_in=3, min_side=3):
    time, cube = np.asarray(time), np.asarray(cube)
    if cube.ndim != 3 or len(time) != len(cube) or not np.all(np.diff(time) > 0):
        raise ValueError("Need a time-sorted pixel cube without duplicate times")
    if not (np.isfinite([period, epoch, duration]).all() and 0 < 6 * duration < period):
        raise ValueError("Event and baseline windows must not overlap neighboring events")
    images, baselines, events = [], [], []
    for cycle in range(int(np.floor((time.min() - epoch) / period)), int(np.ceil((time.max() - epoch) / period)) + 1):
        center = epoch + cycle * period
        dt = time - center
        inside = abs(dt) <= duration / 2
        before = (dt >= -3 * duration) & (dt <= -1.5 * duration)
        after = (dt >= 1.5 * duration) & (dt <= 3 * duration)
        if inside.sum() < min_in or before.sum() < min_side or after.sum() < min_side:
            continue
        t1, t2, ti = np.median(time[before]), np.median(time[after]), np.mean(time[inside])
        weight = (ti - t1) / (t2 - t1)
        baseline = (1 - weight) * np.median(cube[before], axis=0) + weight * np.median(cube[after], axis=0)
        difference = baseline - np.mean(cube[inside], axis=0)
        if not np.isfinite(difference).all():
            continue
        images.append(difference)
        baselines.append(baseline)
        events.append({"cycle": cycle, "center_btjd": float(center), "in_points": int(inside.sum()),
                       "before_points": int(before.sum()), "after_points": int(after.sum())})
    if len(images) < 2:
        raise ValueError("Need at least two events with usable bracketing baselines")
    return np.median(images, axis=0), np.asarray(images), np.asarray(baselines), events


def peak_location(signal):
    if not np.isfinite(signal).all() or signal.max() <= 0:
        raise ValueError("No positive flux decrease to localize")
    y, x = np.unravel_index(np.argmax(signal), signal.shape)
    yy, xx = np.indices(signal.shape)
    window = (abs(xx - x) <= 1) & (abs(yy - y) <= 1)
    weights = np.maximum(signal, 0) * window
    return {"peak_pixel": [int(x), int(y)],
            "positive_core_centroid": [float(np.sum(xx * weights) / weights.sum()), float(np.sum(yy * weights) / weights.sum())],
            "note": "Positive-weight centroid in a 3x3 region around the peak; not a fitted source position or uncertainty."}
