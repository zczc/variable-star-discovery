README file for TESS-EBs: TESS Eclipsing Binaries
MAST webpage: https://archive.stsci.edu/hlsp/tess-ebs
Refer to this HLSP with DOI: https://dx.doi.org/10.17909/t9-9gm4-fx30

######## Data columns:

tess_id: (int) TESS input catalog (TIC) identification number

signal_id: (int) Enumerates distinct ephemerides associated with a single TIC. Additional events that do not fold to the original ephemeris, or background EBs that are detected in the same light curve, get a new signal id.

date_added: (date) Date and time the target was ingested into the catalog (UT, year-mm-dd hh:mm:ss)

date_modified: (date) Date and time of last modification of any target parameters (UT, year-mm-dd hh:mm:ss)

source: (string) data source for the target; currently only lightcurve files (LCF) are ingested, but future versions of the catalog will contain Full Frame Image (FFI) sources as well

ra: (float) Right ascension of the target, in decimal degrees (epoch J2000, equinox J2000)

dec: (float) Declination of the target, in decimal degrees (epoch J2000, equinox J2000)

pmra: (float) proper motion in right ascension from TIC (mas/yr)

pmdec: (float) proper motion in declination from TIC (mas/yr)

Tmag: (float) TESS magnitude from TIC

bjd0: (float) barycentric Julian date of the first primary eclipse (days)

bjd0_uncert: (float) uncertainty in Bjd0 (days)

period: (float) binary star orbital period (days)

period_uncert: (float) uncertainty in the orbital period (days)

morph_coeff: (float) a value between 0 and 1 that denotes the degree of contact

prim_width_pf: (float) primary eclipse width estimate from the polychain fit to the phased lightcurve, in phase units

prim_depth_pf: (float) primary eclipse depth estimate from the polychain fit to the phased lightcurve, in phase units

prim_pos_pf: (float) the phase estimate of the primary eclipse from the polychain fit to the phased lightcurve

sec_width_pf: (float) secondary eclipse width estimate from the polychain fit to the phased lightcurve, in phase units

sec_depth_pf: (float) secondary eclipse depth estimate from the polychain fit to the phased lightcurve, in phase units

sec_pos_pf: (float) the phase estimate of the secondary eclipse from the polychain fit to the phased lightcurve

prim_width_2g: (float) primary eclipse width estimate from the 2-gaussian fit to the phased lightcurve, in phase units

prim_depth_2g: (float) primary eclipse depth estimate from the 2-gaussian fit to the phased lightcurve, in phase units

prim_pos_2g: (float) the phase estimate of the primary eclipse from the 2-gaussian fit to the phased lightcurve

sec_width_2g: (float) secondary eclipse width estimate from the 2-gaussian fit to the phased lightcurve, in phase units

sec_depth_2g: (float) secondary eclipse depth estimate from the 2-gaussian fit to the phased lightcurve, in phase units

sec_pos_2g: (float) the phase estimate of the secondary eclipse from the 2-gaussian fit to the phased lightcurve

sectors: (list of ints) a comma-separated list of sectors that the target has been observed in

######## Summary:

TESS-EBs is a catalog containing locations, ephemerides and basic light curve properties for eclipsing binary stars found in data from the Transiting Exoplanet Survey Satellite (TESS).  Prša et al. 2022 discuss the selection criteria for eclipsing binary candidates, the detection of hither-to unknown eclipsing systems, the determination of ephemerides, the validation and triage process, and the derivation of heuristic estimates for the ephemerides. They also present statistical properties of the sample and qualitative estimates of completeness. Instead of keeping to the widely used discrete classes, the authors propose a binary star morphology classification based on a dimensionality reduction algorithm.

The current version on MAST (v1.0) contains about 4580 eclipsing binary stars found in the first two years (Sectors 1-26) of TESS 2-minute cadence Light Curve Files (LCFs). The catalog will continue to be updated with new sectors of data as they become available, and will later be broadened to include all eclipsing binaries found in Full Frame Images (FFIs). The deliverables presented here are curated by the TESS Eclipsing Binary Working Group, an open group of professional and citizen scientists.

######## Data products:

The catalog's file name in v1.0 is "hlsp_tess-ebs_tess_lcf_s0001-s0026_tess_v1.0_cat.csv", which will change in future data releases following this pattern:

hlsp_tess-ebs_tess_<tessproduct>_<sectors>_tess_<ver>_cat.csv

where:

    <tessproduct> = some dash-separated combination of "lcf" (Light Curve Files), "tpf" (Target Pixel Files), and/or "ffi" (Full Frame Images), referring to the TESS products from which the detections and ephemerides were derived. In v1.0, all information was derived solely from LCFs, so this field is "lcf" for now.
    <sectors> = the dash-separated range of sectors covered by the catalog. In v1.0, this field is s0001-s0026, meaning TESS Sectors 1 through 26.
    <ver> = MAST version number of the catalog, e.g. "v1.0".

######## Data access:

The catalog is a single table, which can be retrieved as a direct-download CSV file, or queried on MAST CasJobs. See the MAST webpage or DOI link at the top of this readme file for detailed instructions. A live version, which is not owned or maintained by MAST, can also be browsed at: https://tessebs.villanova.edu/

######## HLSP authors:

Andrej Prsa (Villanova University, USA)
Angela Kochoska (Villanova University, USA)
Kyle Conroy (Space Telescope Science Institute, USA)
Nora Eisner (University of Oxford, UK)
Daniel Hey (University of Sydney, Australia)
Luc IJspeert (Leuven University, Belgium)
Ethan Kruse (NASA Goddard Space Flight Center, USA)
Scott Fleming (Space Telescope Science Institute, USA)
Cole Johnston (Radboud University Nijmegen, Netherlands)
Martti Kristiansen (Brorfelde Observatory, Denmark)
Daryll LaCourse (Amateur Astronomer)
Danielle Mortensen (Villanova University, USA)
Joshua Pepper (Lehigh University, USA)
Keivan Stassun (Vanderbilt University, USA)
Guillermo Torres (Center for Astrophysics, Harvard-Smithsonian, USA)

######## References:
Prša et al. 2022, ApJS, 258, 16
