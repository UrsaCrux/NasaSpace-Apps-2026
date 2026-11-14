"""Field data API: everything known about a place, from many data sources.

    from fieldshift.api import get_site_data

    site = get_site_data(lon=-71.0, lat=-34.5, radius_m=1000)
    print(site.summary())
    site.soil.clay["0-5cm"].value          # %
    site.water.actual_et.value             # mm/day

Each data source of docs/data-api.md is a Provider (fieldshift/api/providers/).
Providers that are not configured (missing package or credentials) or that
fail are reported in ``site.sources`` and never stop the others.
"""

from fieldshift.api.client import get_site_data, list_providers
from fieldshift.api.geo import Area, Period
from fieldshift.api.models import (
    Fires, Measurement, SiteData, Soil, SourceStatus, Terrain, Vegetation, Water, Weather,
)

__all__ = [
    "Area", "Fires", "Measurement", "Period", "SiteData", "Soil", "SourceStatus",
    "Terrain", "Vegetation", "Water", "Weather", "get_site_data", "list_providers",
]
