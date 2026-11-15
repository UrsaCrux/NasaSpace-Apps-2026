"""Which WOFOST crop model simulates a crop, and its parameters.

WOFOST (through PCSE) only has models for annual field crops; this module
maps the crops of the catalogue (fieldshift/crops/crops.json) and FAO
EcoCrop plants (by scientific name) to a WOFOST crop and variety of the
bundled parameter files (wofost_parameters/, WOFOST 7.2, EUPL 1.2). Crops
without a model (fruit trees, vegetables, forage...) get None.

    info = crop_info("maize.v1")
    info["crop_name"], info["variety_name"]        # 'maize', 'Grain_maize_201'
    info["parameters"]["TSUM1"]                    # the full parameter set
"""

from pathlib import Path

from fieldshift import crops

# folder with the bundled WOFOST 7.2 crop parameter files
PARAMETERS_DIR = Path(__file__).resolve().parent / "wofost_parameters"
# PCSE model the parameters are for (water-limited, free drainage)
MODEL = "Wofost72_WLP_FD"
SOURCE = "WOFOST_crop_parameters (wofost72 branch, EUPL 1.2)"

# WOFOST crop -> (scientific name, default variety, sowing (month, day) in the
# southern hemisphere, longest season in days). Northern hemisphere: +6 months
WOFOST_CROPS = {
    "barley": ("Hordeum vulgare", "Spring_barley_301", (8, 15), 200),
    "cassava": ("Manihot esculenta", "Cassava_VanHeemst_1988", (10, 1), 330),
    "chickpea": ("Cicer arietinum", "Chickpea_VanHeemst_1988", (6, 15), 200),
    "cotton": ("Gossypium hirsutum", "Cotton_VanHeemst_1988", (10, 15), 220),
    "cowpea": ("Vigna unguiculata", "Cowpea_VanHeemst_1988", (11, 15), 150),
    "fababean": ("Vicia faba", "Faba_bean_801", (5, 15), 220),
    "groundnut": ("Arachis hypogaea", "Groundnut_VanHeemst_1988", (11, 1), 180),
    "maize": ("Zea mays", "Grain_maize_201", (10, 15), 240),
    "millet": ("Pennisetum glaucum", "Millet_VanHeemst_1988", (11, 15), 150),
    "mungbean": ("Vigna radiata", "Mungbean_VanHeemst_1988", (11, 15), 120),
    "pigeonpea": ("Cajanus cajan", "Pigeonpea_VanHeemst_1988", (11, 15), 240),
    "potato": ("Solanum tuberosum", "Potato_701", (9, 15), 200),
    "rapeseed": ("Brassica napus", "Oilseed_rape_1001", (4, 15), 300),
    "rice": ("Oryza sativa", "Rice_501", (10, 15), 200),
    "seed_onion": ("Allium cepa", "onion_agriadapt", (7, 15), 220),
    "sorghum": ("Sorghum bicolor", "Sorghum_VanHeemst_1988", (11, 15), 180),
    "soybean": ("Glycine max", "Soybean_901", (11, 15), 180),
    "sugarbeet": ("Beta vulgaris var. saccharifera", "Sugarbeet_601", (9, 15), 240),
    "sugarcane": ("Saccharum officinarum", "Sugarcane_VanHeemst_1988", (9, 15), 365),
    "sunflower": ("Helianthus annuus", "Sunflower_1101", (10, 15), 200),
    "sweetpotato": ("Ipomoea batatas", "Sweetpotato_VanHeemst_1988", (10, 15), 200),
    "tobacco": ("Nicotiana tabacum", "Tobacco_VanHeemst_1988", (10, 15), 180),
    "wheat": ("Triticum aestivum", "Winter_wheat_101", (5, 15), 300),
}

# catalogue crops simulated with another, similar crop's model ("proxy")
PROXIES = {"oat": "barley", "lentil": "chickpea", "pea": "fababean", "lupin": "fababean",
           "bean": "cowpea"}

_providers = {}


# (str crop_id)
# (WOFOST crop name, "exact" | "proxy") for a catalogue crop or EcoCrop
# scientific name, or None when WOFOST has no model for it
def wofost_crop_for(crop_id=None, scientific_name=None):
    if crop_id in PROXIES:
        return PROXIES[crop_id], "proxy"
    names = {scientific_name} if scientific_name else set()
    if crop_id:
        names.add(crops.ecocrop_name(f"{crop_id}.v1"))
    for name, (sci, *_rest) in WOFOST_CROPS.items():
        if sci in names or any(n and n.startswith(sci + " ") for n in names):
            return name, "exact"
    return None


def _provider():
    if "provider" not in _providers:
        from pcse.input import YAMLCropDataProvider
        from pcse.models import Wofost72_WLP_FD
        _providers["provider"] = YAMLCropDataProvider(model=Wofost72_WLP_FD,
                                                      fpath=str(PARAMETERS_DIR))
    return _providers["provider"]


# (str crop_name, str variety_name)
# {parameter: value} of a WOFOST crop variety from the bundled files
def parameters(crop_name, variety_name):
    provider = _provider()
    provider.set_active_crop(crop_name, variety_name)
    return {key: _plain(provider[key]) for key in provider.keys()}


def _plain(value):
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "item"):                    # numpy number
        return value.item()
    return value


# (str value, str display_name = None)
# hidden WOFOST data stored with a field for its crop ("peach.v1",
# "ecocrop:2175"...): model, crop, variety, sowing date, season length and
# the full parameter set; None when WOFOST cannot simulate the crop
def crop_info(value, display_name=None):
    variety = crops.variety_by_id(value)
    crop_id = variety.crop if variety else None
    scientific = None
    if crops.ecocrop_number(value) is not None:
        scientific = display_name or crops.label(value)
    match = wofost_crop_for(crop_id, scientific)
    if match is None:
        return None
    crop_name, kind = match
    _sci, variety_name, sowing, max_days = WOFOST_CROPS[crop_name]
    return {"model": MODEL, "crop_name": crop_name, "variety_name": variety_name,
            "match": kind, "sowing_south": list(sowing), "max_duration": max_days,
            "source": SOURCE, "parameters": parameters(crop_name, variety_name)}
