"""Sources from the data report that are not implemented yet.

They are listed by get_site_data with status "planned" so the gap is visible.
To implement one, write a Provider subclass and replace its entry in
fieldshift/api/providers/__init__.py (see docs/data-api.md).
"""

# Resources of the Space Apps "Field Shift" challenge that cover only the
# United States and therefore not Chile (substitute in parentheses):
# PRISM (ERA5-Land, NASA POWER, CR2MET), SSURGO/STATSGO2 and Web Soil Survey
# (SoilGrids, CIREN), CropScape CDL (CIREN-ODEPA fruit cadastre), NAIP
# (Sentinel-2), NLCD (ESA WorldCover / CONAF), NLDAS (GLDAS), NWIS (DGA SNIA),
# OpenET (ECOSTRESS, WaPOR), LANDFIRE (CONAF), NASS QuickStats (INE census),
# AMS Market News (ODEPA), CoCoRaHS (INIA / DMC stations), Ag Data Commons.
US_ONLY = ["PRISM", "SSURGO/STATSGO2", "Web Soil Survey", "CropScape CDL", "NAIP", "NLCD",
           "NLDAS", "NWIS", "OpenET", "LANDFIRE", "NASS QuickStats", "AMS Market News",
           "CoCoRaHS", "Ag Data Commons"]

# (name, what it would add, portal, suggested Python packages)
PLANNED = [
    ("sentinel2", "NDVI / EVI / NDMI at 10 m", "https://dataspace.copernicus.eu",
     "openeo, pystac-client"),
    ("hls", "NDVI from Harmonized Landsat Sentinel-2 v2.0 (30 m)",
     "https://hls.gsfc.nasa.gov", "earthaccess, rasterio"),
    ("landsat", "Landsat C2 L2 surface reflectance and temperature",
     "https://earthexplorer.usgs.gov", "landsatxplore, earthaccess"),
    ("viirs_ndvi", "VIIRS NDVI, successor of MODIS (VNP13A1 v002)",
     "https://lpdaac.usgs.gov/products/vnp13a1v002/", "earthaccess, h5py"),
    ("gedi", "GEDI L4B above-ground biomass around the fields (1 km, 2019-2023)",
     "https://gedi.umd.edu/data", "earthaccess, rasterio"),
    ("gaez", "FAO GAEZ v5 crop suitability and attainable yield", "https://gaez.fao.org",
     "requests, rasterio"),
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
