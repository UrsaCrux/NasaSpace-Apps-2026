# Field data API (`fieldshift.api`)

One call returns everything the data sources of the project report
(*Informe de Mejores Candidatos de Datos Agrícolas y Satelitales para Chile*)
and the resources of the NASA Space Apps challenge *Field Shift: Adapting
Farms with NASA Data* know about a place: weather and its extremes (frost,
heat, wettest day), long-term monthly climate normals, soil type and
properties, soil moisture and temperature, water balance and long-term water
storage, relief, vegetation vigour (NDVI) and productivity, and fires.

```python
from fieldshift.api import get_site_data

site = get_site_data(lon=-71.0, lat=-34.5, radius_m=1500)   # last available week
site = get_site_data(-71.0, -34.5, 1500, start="2026-10-01", end="2026-10-07")

print(site.summary())                       # readable report
site.soil.type.value                        # 'Leptosols'
site.soil.clay["0-5cm"]                     # Measurement(value=21.1, unit='%', source='soilgrids')
site.water.actual_et.value                  # 3.09 (mm/day)
site.weather.air_temperature                # NASA POWER, or ERA5-Land when configured
site.weather.frost_days                     # days with minimum <= 0 °C in the period
site.climate.frost_days["JUL"]              # long-term mean frost days in July
site.vegetation.ndvi                        # MODIS 16-day NDVI
site.to_dict()                              # JSON-ready dict
[(s.name, s.status, s.message) for s in site.sources]
```

From the shell:

```bash
make site LON=-71.0 LAT=-34.5 RADIUS=1500
```

```bash
python -m fieldshift.api -71.0 -34.5 --radius 1500 --json
```

```bash
python -m fieldshift.api --list
```

## How it works

```
get_site_data(lon, lat, radius_m, start, end)
   │  Area (circle) + Period (dates, default: the 7 days ending a week ago)
   ├─ NasaPowerProvider ──┐
   ├─ SoilGridsProvider     │
   ├─ CopernicusDemProvider │   run in parallel; each one writes its part
   ├─ WaporProvider         │   of SiteData and reports a SourceStatus
   ├─ ModisNdviProvider     ├─►
   ├─ Era5LandProvider      │   weather: each source fills
   ├─ SmapProvider          │   weather_by_source[name]; then `weather`
   ├─ GpmImergProvider      │   takes each field from ERA5-Land, else
   ├─ EcostressProvider     │   NASA POWER (WEATHER_PRIORITY in client.py)
   ├─ GldasProvider         │
   ├─ GraceProvider         │
   └─ FirmsProvider ───────┘
```

- Values are averaged over the circle; when the circle is smaller than one
  pixel of a source, the pixel at the centre is used. SoilGrids is queried
  at the centre point (its API has no area query).
- Every value is a `Measurement(value, unit, source, note)`, so you always
  know where a number came from. Depth-dependent values are dicts keyed by
  depth (`"0-5cm"`); moisture and temperature keys also name the source
  (`"0-7cm ERA5-Land"`, `"0-5cm SMAP"`).
- A source never makes the call fail. `site.sources` tells, per source:

| Status | Meaning |
|--------|---------|
| `ok` | data added |
| `no_data` | the source has nothing here (sea, urban mask, period not published) |
| `skipped` | missing package or credentials; the message says what to set up |
| `error` | the request failed; the message has the error |
| `planned` | in the report but not implemented yet |

## Sources

| Provider | Data added | Resolution | Access |
|----------|-----------|------------|--------|
| `nasa_power` — NASA POWER | weather (temperature mean/min/max, dewpoint, humidity, rain, wettest day, radiation, wind, frost and heat days), soil wetness, skin temperature; monthly climate normals 2001–2025 | ~0.5°, daily | public REST, no key |
| `modis_ndvi` — MODIS MOD13Q1 via ORNL DAAC | NDVI | 250 m, 16-day | public REST, no key (slow: ~30 s) |
| `soilgrids` — ISRIC SoilGrids 2.0 | soil type (WRB), clay/sand/silt, organic carbon, pH, bulk density, CEC, nitrogen, field capacity, wilting point; 6 depths | 250 m | public REST, no key |
| `copernicus_dem` — Copernicus DEM GLO-30 | elevation mean/min/max, slope | 30 m | public AWS bucket, no key |
| `wapor` — FAO WaPOR v3 L1 | actual ET, reference ET, transpiration, evaporation, precipitation, net primary production | 300 m, 10-day | public REST, no key |
| `era5_land` — ECMWF ERA5-Land | air temperature (mean/min/max), dewpoint, relative humidity, precipitation, solar radiation, soil moisture and soil temperature at 4 depths | 9 km, hourly | CDS API key |
| `smap_l4` — NASA SMAP SPL4SMGP v8 | surface and root-zone soil moisture, soil and surface temperature | 9 km, 3-hourly | NASA Earthdata login |
| `gpm_imerg` — NASA GPM IMERG V07 daily | satellite precipitation | 0.1°, daily | NASA Earthdata login |
| `ecostress` — NASA ECOSTRESS v003 | actual ET (JET), land surface temperature (LSTE, cloud-masked) | 70 m, irregular overpasses | NASA Earthdata login |
| `gldas` — NASA GLDAS-2.1 Noah monthly | soil moisture and temperature at 4 depths, ET | 0.25°, monthly (~1–4 months delay) | NASA Earthdata login |
| `grace` — GRACE/GRACE-FO JPL mascons | water storage anomaly (latest month) and 10-year trend | ~3° mascons, monthly | NASA Earthdata login |
| `firms` — NASA FIRMS (VIIRS) | active fire detections, nearest fire | 375 m | FIRMS MAP_KEY |

Planned (listed in `site.sources` as `planned`): Sentinel-2, HLS, Landsat,
VIIRS NDVI, GEDI, FAO GAEZ, CR2MET, INIA, DMC, DGA/SNIA, CIREN, ODEPA,
CONAF — see `fieldshift/api/providers/catalog.py`.

Heat days use `HEAT_DAY_C` (35 °C, in `fieldshift/api/models.py`). The
climate normals' `temperature_extreme_max/min` are the monthly extremes of the
period, not the mean daily maximum/minimum.

## Challenge resources (Space Apps "Field Shift")

| Resource | Status here |
|----------|-------------|
| SMAP | `smap_l4` |
| GPM / IMERG | `gpm_imerg` |
| Landsat, MODIS/VIIRS NDVI | `modis_ndvi`; Landsat and VIIRS planned |
| NASA POWER | `nasa_power` |
| SRTM / NASA elevation | `copernicus_dem` (GLO-30, the report's replacement for SRTM: same 30 m, newer) |
| ECOSTRESS | `ecostress` |
| GRACE / GRACE-FO | `grace` |
| NLDAS / GLDAS | `gldas` (NLDAS covers North America only) |
| GEDI | planned |
| FAO GAEZ | planned |
| ERA5 (ECMWF) | `era5_land` (ERA5-Land, the 9 km land version) |
| Copernicus Sentinel-2 | planned |
| PRISM, SSURGO/STATSGO2, Web Soil Survey, CropScape CDL, NAIP, NLCD, NWIS, OpenET, LANDFIRE, NASS QuickStats, AMS Market News, CoCoRaHS, Ag Data Commons | United States only, no data for Chile. Substitutes: ERA5-Land / POWER / CR2MET (PRISM), SoilGrids / CIREN (soil surveys), CIREN-ODEPA cadastre (CDL), Sentinel-2 (NAIP), GLDAS (NLDAS), DGA SNIA (NWIS), ECOSTRESS / WaPOR (OpenET), ODEPA (market prices), INE census (NASS), INIA / DMC stations (CoCoRaHS) |

Data latency: ERA5-Land ~5 days, SMAP L4 ~3 days, IMERG late run ~1–2 days,
WaPOR ~1 dekad. When WaPOR has not published the period yet, the latest
dekad is used and the value's `note` says which.

## Credentials

All free. Without them the provider is simply `skipped`.

**ERA5-Land (Copernicus Climate Data Store).** Create an account at
<https://cds.climate.copernicus.eu>, accept the ERA5-Land licence on the
dataset page, copy your API key from your profile, and create `~/.cdsapirc`:

```
url: https://cds.climate.copernicus.eu/api
key: <your-api-key>
```

CDS requests are queued and can take minutes; results are cached in
`~/.cache/fieldshift/era5_land` (change with `FIELDSHIFT_CACHE`).

**NASA Earthdata (SMAP, GPM IMERG, ECOSTRESS, GLDAS, GRACE).** Create an account at
<https://urs.earthdata.nasa.gov>, then either export
`EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`, or add to `~/.netrc`
(permissions `600`):

```
machine urs.earthdata.nasa.gov login <user> password <password>
```

**NASA FIRMS.** Request a MAP_KEY at
<https://firms.modaps.eosdis.nasa.gov/api/map_key/> and export
`FIRMS_MAP_KEY`.

## Installing the packages

`make env` installs them with QGIS. For an existing environment:
`make env-data`. With pip: `pip install -r requirements-data.txt`.

## Adding a source

1. Create `fieldshift/api/providers/<name>.py` with a `Provider` subclass:
   set `name`, `title`, `url`, `packages`, `credentials`; override `check()`
   if it needs credentials (raise `ProviderUnavailable`), and implement
   `fetch(area, period, site)` writing `Measurement`s into `site`. Raise
   `NoData` when the source has nothing for the area.
2. If it brings a new kind of value, add a field to the matching dataclass in
   `fieldshift/api/models.py` (with a comment: it shows up in the docs).
3. Register it in `PROVIDERS` in `fieldshift/api/providers/__init__.py` and
   remove its entry from `catalog.py`.
4. Add a test in `tests/test_api.py` that feeds a small synthetic file or
   response in the source's format, so it runs offline.
5. `make test`, `make test-live`, `make docs`.

Tested live: `nasa_power`, `modis_ndvi`, `soilgrids`, `copernicus_dem`,
`wapor`. The providers that need credentials (`era5_land`, `smap_l4`,
`gpm_imerg`, `ecostress`, `gldas`, `grace`, `firms`) are tested with
synthetic files in each product's format, with product names and file
layouts checked against NASA's CMR catalogue; run them once with your keys
before relying on them.
