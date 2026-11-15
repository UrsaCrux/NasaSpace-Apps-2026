"""Soil and site parameters for PCSE / WOFOST from a field's zone data.

Water retention comes from the Saxton & Rawls (2006) pedotransfer equations
(sand, clay, organic matter); when the field has an "available water" value
(SoilGrids or typed by the farmer) the field capacity is set so that
SMFCF - SMW matches it. Values that WOFOST needs but no source gives
(rootable depth, critical air content) use common defaults, noted in
"assumptions".

Saxton, K.E. & Rawls, W.J. (2006). Soil water characteristic estimates by
texture and organic matter for hydrologic solutions. SSSA J. 70:1569-1578.
"""

import math

# WOFOST soil parameters always set from defaults
DEFAULT_RDMSOL_CM = 120.0     # rootable depth of the soil (no source gives it)
DEFAULT_CRAIRC = 0.06         # critical soil air content for aeration
# typical texture (sand, clay %) used when the field has no fractions
TYPICAL_TEXTURE = {"sand": (92, 3), "loamy_sand": (82, 6), "sandy_loam": (65, 10),
                   "loam": (40, 20), "silt_loam": (20, 15), "silt": (7, 6),
                   "sandy_clay_loam": (60, 27), "clay_loam": (32, 34),
                   "silty_clay_loam": (10, 34), "sandy_clay": (52, 42),
                   "silty_clay": (7, 47), "clay": (20, 60)}
# organic matter (% weight) assumed without organic carbon data
DEFAULT_OM_PCT = 2.0


# (float sand_pct, float clay_pct, float om_pct)
# {"wilting_point", "field_capacity", "saturation"} (m³/m³) and
# "ksat_mm_h" from the Saxton & Rawls (2006) equations
def saxton_rawls(sand_pct, clay_pct, om_pct):
    s, c = sand_pct / 100.0, clay_pct / 100.0
    om = min(max(om_pct, 0.0), 8.0)                       # equations valid to 8 %
    t1500 = (-0.024 * s + 0.487 * c + 0.006 * om + 0.005 * s * om - 0.013 * c * om
             + 0.068 * s * c + 0.031)
    wp = t1500 + (0.14 * t1500 - 0.02)
    t33 = (-0.251 * s + 0.195 * c + 0.011 * om + 0.006 * s * om - 0.027 * c * om
           + 0.452 * s * c + 0.299)
    fc = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)
    ts33 = (0.278 * s + 0.034 * c + 0.022 * om - 0.018 * s * om - 0.027 * c * om
            - 0.584 * s * c + 0.078)
    s33 = ts33 + (0.636 * ts33 - 0.107)
    sat = fc + s33 - 0.097 * s + 0.043
    wp, fc = max(wp, 0.01), max(fc, wp + 0.02)
    sat = max(sat, fc + 0.02)
    b = (math.log(1500) - math.log(33)) / (math.log(fc) - math.log(wp))
    ksat = 1930 * (sat - fc) ** (3 - 1 / b)
    return {"wilting_point": wp, "field_capacity": fc, "saturation": sat, "ksat_mm_h": ksat}


def _value(data, key):
    item = data.get(key) or {}
    return item.get("value")


# (dict data)
# PCSE soil + site descriptor of a field from its normalized data:
# {"soil": {SMW, SMFCF, SM0, CRAIRC, K0, SOPE, KSUB, RDMSOL},
#  "site": {WAV, IFUNRN, NOTINF, SSI, SSMAX, SMLIM}, "inputs": {...},
#  "assumptions": [...]}
def site_descriptor(data):
    assumptions = [f"RDMSOL {DEFAULT_RDMSOL_CM:g} cm (rootable depth: no data source)",
                   f"CRAIRC {DEFAULT_CRAIRC:g} (default)"]
    sand, clay = _value(data, "sand"), _value(data, "clay")
    if sand is None or clay is None:
        texture = _value(data, "soil_texture") or "loam"
        sand, clay = TYPICAL_TEXTURE.get(texture, TYPICAL_TEXTURE["loam"])
        assumptions.append(f"sand/clay {sand}/{clay} % typical of the {texture} class")
    oc = _value(data, "organic_carbon")
    om = oc / 10 * 1.724 if oc is not None else DEFAULT_OM_PCT   # g/kg C -> % organic matter
    if oc is None:
        assumptions.append(f"organic matter {DEFAULT_OM_PCT:g} % (no organic carbon data)")
    sr = saxton_rawls(sand, clay, om)
    smw, smfcf, sm0 = sr["wilting_point"], sr["field_capacity"], sr["saturation"]
    available = _value(data, "available_water")
    if available is not None and available > 0:              # keep the field's own value
        smfcf = min(smw + available / 100.0, sm0 - 0.02)
    k0 = sr["ksat_mm_h"] * 2.4                                # mm/h -> cm/day
    sope = min(max(k0, 0.5), 30.0)
    rdmsol = DEFAULT_RDMSOL_CM
    slope = _value(data, "slope") or 0.0
    # rough: part of the rain runs off on slopes (none below 2 degrees)
    notinf = 0.0 if slope < 2 else round(min(0.3, slope / 100.0), 3)
    if notinf:
        assumptions.append(f"NOTINF {notinf} from the slope ({slope:g}°)")
    soil = {"SMW": round(smw, 3), "SMFCF": round(smfcf, 3), "SM0": round(sm0, 3),
            "CRAIRC": DEFAULT_CRAIRC, "K0": round(k0, 2), "SOPE": round(sope, 2),
            "KSUB": round(sope / 2, 2), "RDMSOL": rdmsol}
    # start the season with half of the root zone's available water
    wav = round((soil["SMFCF"] - soil["SMW"]) * rdmsol * 0.5, 1)
    site = {"WAV": wav, "IFUNRN": 0, "NOTINF": notinf, "SSI": 0.0, "SSMAX": 0.0, "SMLIM": 0.4}
    return {"model": "WOFOST 7.2 (PCSE WaterbalanceFD)", "soil": soil, "site": site,
            "inputs": {"sand_pct": sand, "clay_pct": clay, "organic_matter_pct": round(om, 2),
                       "available_water_pct": available, "slope_deg": slope,
                       "elevation_m": _value(data, "elevation")},
            "pedotransfer": "Saxton & Rawls (2006)", "assumptions": assumptions}
