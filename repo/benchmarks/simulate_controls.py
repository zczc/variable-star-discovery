"""Fixed development signal generator; parameters live in mixed-protocol-v01.json.

Time is the unbinned, quality-filtered real cadence. Epoch noise draws are
independent. Periodic signals share an absolute phase across both epochs.
These are simulations on real timestamps, not injections into real stellar flux.
"""
import numpy as np
from vstar.photometry import LightCurve


def generate(case, time, origin, epoch_index):
    rng = np.random.default_rng(np.random.SeedSequence([case["seed"], epoch_index]))
    kind, sigma = case["kind"], case["noise_sigma"]
    signal = np.zeros(len(time))
    auxiliary = np.empty(0)
    if kind == "synthetic_correlated_noise":
        # Stationary OU process on irregular sampling, including real gaps.
        rho = np.exp(-np.diff(time) / case["correlation_timescale_d"])
        innovations = rng.normal(size=len(time))
        signal[0] = case["correlated_sigma"] * innovations[0]
        for i in range(1, len(time)):
            signal[i] = rho[i-1] * signal[i-1] + case["correlated_sigma"] * np.sqrt(1-rho[i-1]**2) * innovations[i]
    elif kind == "synthetic_trend":
        u = (time-time.min()) / np.ptp(time) - .5
        signal = case["slope"] * (u + case["curvature"] * u**2)
    elif kind in {"synthetic_sinusoid", "synthetic_common_mode"}:
        signal = case["amplitude"] * np.sin(2*np.pi*((time-origin)/case["period_d"] + .137))
    elif kind in {"synthetic_equal_eclipses", "synthetic_unequal_eclipses"}:
        phase = ((time-origin)/case["period_d"] + .137) % 1
        width = case["duration_fraction"]
        for center, depth in [(0, case["primary_depth"]), (.5, case["primary_depth"]*case["secondary_fraction"])]:
            distance = abs((phase-center+.5) % 1-.5)
            inside = distance < width/2
            signal[inside] -= depth * np.cos(np.pi*distance[inside]/width)**2
    elif kind != "synthetic_white_noise":
        raise ValueError(f"Unknown synthetic family {kind}")
    flux = 1 + signal + rng.normal(0, sigma, len(time))
    if kind == "synthetic_common_mode":
        auxiliary = signal + rng.normal(0, sigma, len(time))
    return {"time": time, "flux": flux, "error": np.full(len(time), sigma),
            "injected_signal": signal, "auxiliary": auxiliary}


def as_lightcurve(arrays, metadata):
    scale = float(np.median(arrays["flux"]))
    return LightCurve(arrays["time"], arrays["flux"]/scale-1, arrays["error"]/scale,
                      dict(metadata, normalization_median=scale, simulated=True))
