# Crop growth simulation (PCSE / WOFOST)

The **Crop growth** analysis simulates the season of a field's crop with
WOFOST 7.2 through [PCSE](https://pcse.readthedocs.io) (`pip install pcse`,
done by `make env` / `make env-data`).

## What the field file carries (hidden)

When a field is saved (`FieldStore.create` / `update`,
`fieldshift/fields/model_inputs.py`), two keys are written into its `data`,
never shown to the user:

| Key | Content | Code |
|-----|---------|------|
| `wofost` | model (`Wofost72_WLP_FD`), WOFOST crop and variety, `match` (`exact` or `proxy`), usual sowing date (southern hemisphere), longest season, and the **full crop parameter set**; `null` when WOFOST has no model for the crop | `fieldshift/crops/wofost_crops.py` |
| `pcse_site` | PCSE soil (`SMW`, `SMFCF`, `SM0`, `CRAIRC`, `K0`, `SOPE`, `KSUB`, `RDMSOL`) and site (`WAV`, `IFUNRN`, `NOTINF`, `SSI`, `SSMAX`, `SMLIM`) parameters, the inputs used and the assumptions made | `fieldshift/simulation/soil.py` |

Both are recomputed on every save, so editing the crop or the soil data
updates them. Older files without them get them computed on the fly.

**Crop models.** WOFOST simulates annual field crops. The bundled parameter
files (`fieldshift/crops/wofost_parameters/`, WOFOST 7.2, EUPL 1.2) cover 23
crops: barley, cassava, chickpea, cotton, cowpea, faba bean, groundnut,
maize, millet, mung bean, pigeon pea, potato, rapeseed, rice, onion, sorghum,
soybean, sugar beet, sugarcane, sunflower, sweet potato, tobacco, wheat.
Catalogue crops map by their EcoCrop scientific name; oat, lentil, pea,
lupin and common bean use a similar crop's model (`proxy`); fruit trees,
vegetables and forage have none (the analysis says so). The varieties are
WOFOST's generic ones.

**Soil.** Water retention from the Saxton & Rawls (2006) pedotransfer
equations (sand, clay, organic matter from SoilGrids or typed); the field's
"available water" sets `SMFCF - SMW` when known. No source gives the rootable
depth: 120 cm is assumed (listed in `assumptions`). Slopes above 2° make part
of the rain run off (`NOTINF`, rough).

## The season and its weather

* Sowing on the crop's usual date (southern hemisphere; +6 months in the
  north). If that was less than 120 days ago, the **current season** is
  simulated from it; otherwise the **next** one.
* Weather (`fieldshift/simulation/weather.py`), per day:
  1. observed — Open-Meteo (archive + recent days), or NASA POWER when
     Open-Meteo fails or is rate-limited;
  2. forecast — Open-Meteo, up to 16 days;
  3. climate — the rest of the season takes the weather of the same day of
     the previous year (a real recent year of the zone).
  The result shows how many days came from each ("observed / forecast /
  climate") and flags seasons mostly made of climate.
* Model: `Wofost72_WLP_FD` (water-limited, free drainage) for rain-fed
  fields; `Wofost72_PP` (potential) when the field is marked **irrigated**.
  The potential yield is always computed too, so the result shows the yield
  lost to water shortage.

## Result

Leaf area index over the season (chart, slider, field colour), expected and
potential yield (dry weight of the storage organs), total biomass, maximum
LAI, maturity date and the weather mix; recommendations about the water gap,
proxy models and climate-based days.

## Code

| File | What |
|------|------|
| `fieldshift/crops/wofost_crops.py` | crop → WOFOST model, parameters from the bundled YAML |
| `fieldshift/simulation/soil.py` | Saxton & Rawls, soil / site descriptor |
| `fieldshift/simulation/weather.py` | weather assembly and the PCSE weather provider |
| `fieldshift/simulation/run.py` | season dates, agromanagement, model run |
| `fieldshift/analysis/crop_growth.py` | the analysis |

## Climate shift scenarios (Field Shift)

`fieldshift/simulation/scenario.py` runs the same season three times
(`run_scenario(field)`), and the **Climate shift** analysis
(`fieldshift/analysis/climate_shift.py`) compares them:

1. **today** — the season's weather as above;
2. **shifted** — every day +2 °C (min and max), rain × 0.85, vapour pressure
   × 1.07 per °C (same relative humidity): `Scenario(temp_offset_c,
   rain_scale)`, default `FIELD_SHIFT`;
3. **shifted + regulated deficit irrigation** — the shifted weather with
   2 cm every 14 days from day 30 after sowing, as PCSE irrigation events
   (`simulate(..., irrigation=[(days after sowing, cm)])`); only for rain-fed
   fields (irrigated ones already run as potential production).

The result shows the yield of each run, the change, the season length and
the water-stress days (`RFTRA` < 0.7, transpiration under 70 % of potential).
It is a simple scenario on the season's weather, not a climate projection.
WOFOST 7.2 has no CO2 response, so CO2 is not a scenario parameter.

Perennial crops (vines, orchards, berries) have no WOFOST model: Crop growth
says so, and Climate shift measures the same shift on climate indices of the
last 12 months (NASA POWER daily) instead of a yield: growing degree-days base
10 °C over the growing season (and the Winkler region for grapes), hot days
above the crop's EcoCrop limit, spring frost days, yearly rain, and the crop's
EcoCrop climate suitability with irrigation — no made-up crop parameters.

## Cultivar names

`crops.json` may give a crop `variety_names` (Chilean cultivars: Cabernet
Sauvignon, Carménère, Merlot, Sauvignon Blanc; Thompson Seedless, Red Globe,
Crimson Seedless; Santina, Lapins, Regina; Gala, Fuji, Pink Lady; Chandler,
Serr; Hass; Duke, Legacy, Brigitta). Ids stay `<crop>.v<n>` (saved fields keep
working); `crops.label()` shows the name and the crop search finds them
("cabernet" → Wine grape – Cabernet Sauvignon). WOFOST still uses its generic
varieties.
