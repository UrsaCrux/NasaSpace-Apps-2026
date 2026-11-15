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
