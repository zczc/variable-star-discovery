"""Read public SPOC background, pointing and centroid columns for source checks."""
from astropy.io import fits
import numpy as np
from .photometry import LightCurve, bin_lightcurve


def read_auxiliary(path, bin_minutes=10):
    result = {}
    with fits.open(path, memmap=False) as h:
        table = h[1].data
        time = np.asarray(table["TIME"], float)
        good = np.isfinite(time) & (table["QUALITY"] == 0)
        for column in ["SAP_BKG", "POS_CORR1", "POS_CORR2", "MOM_CENTR1", "MOM_CENTR2"]:
            if column not in table.names:
                continue
            values = np.asarray(table[column], float)
            mask = good & np.isfinite(values)
            if mask.sum() < 100:
                continue
            order = np.argsort(time[mask])
            result[column] = bin_lightcurve(LightCurve(time[mask][order], values[mask][order], np.ones(mask.sum()),
                                                     {"column": column, "same_observation": True}), bin_minutes)
    return result
