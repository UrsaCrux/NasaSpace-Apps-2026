"""Sources from the data report that are not implemented yet.

They are listed by get_site_data with status "planned" so the gap is visible.
To implement one, write a Provider subclass and replace its entry in
fieldshift/api/providers/__init__.py (see docs/data-api.md).
"""

# (name, what it would add, portal, suggested Python packages)
PLANNED = [
    ("sentinel2", "NDVI / EVI / NDMI at 10 m", "https://dataspace.copernicus.eu",
     "openeo, pystac-client"),
    ("hls", "NDVI from Harmonized Landsat Sentinel-2 v2.0 (30 m)",
     "https://hls.gsfc.nasa.gov", "earthaccess, rasterio"),
    ("ecostress", "land surface temperature and ET at 70 m (ECO_L2T_LSTE, ECO_L3T_JET)",
     "https://ecostress.jpl.nasa.gov", "earthaccess, rasterio"),
    ("landsat", "Landsat C2 L2 surface reflectance and temperature",
     "https://earthexplorer.usgs.gov", "landsatxplore, earthaccess"),
    ("grace", "terrestrial water storage anomaly (GRACE/GRACE-FO mascons)",
     "https://grace.jpl.nasa.gov", "xarray, netCDF4"),
    ("cr2met", "bias-corrected precipitation / temperature for Chile (5 km)",
     "https://www.cr2.cl", "xarray, requests"),
    ("inia", "INIA weather stations (RAN, API v4)", "https://agrometeorologia.cl", "requests"),
    ("dmc", "DMC weather stations (MeteoChile)", "https://climatologia.meteochile.gob.cl",
     "requests"),
    ("dga", "DGA wells, river flow and water rights (SNIA)", "https://snia.mop.gob.cl",
     "requests, pandas"),
    ("ciren", "CIREN soil series and land-use capability (1:10 000)", "https://www.ciren.cl",
     "OWSLib, geopandas"),
    ("odepa", "wholesale market prices", "https://datos.odepa.gob.cl", "ckanapi"),
    ("conaf", "CONAF vegetation cadastre and fire records", "https://www.conaf.cl",
     "geopandas"),
]
