"""Base class and helpers shared by every data provider."""

import importlib
import os
from pathlib import Path


# raised by Provider.check when the provider cannot run here (missing package
# or credentials); reported as "skipped"
class ProviderUnavailable(Exception):
    pass


# raised by Provider.fetch when the source has no data for this area/period
# (sea, urban mask, not yet published); reported as "no_data"
class NoData(Exception):
    pass


# one data source. Subclasses set the class attributes and implement fetch()
class Provider:
    # short identifier used in SiteData.sources and to select providers
    name = ""
    # what the source is, for listings
    title = ""
    # portal / documentation
    url = ""
    # Python packages needed (import names)
    packages = ()
    # environment variables or files needed, as a human-readable hint
    credentials = ""

    # ()
    # raises ProviderUnavailable when a package or credential is missing
    def check(self):
        missing = [p for p in self.packages if importlib.util.find_spec(p) is None]
        if missing:
            raise ProviderUnavailable("missing Python package(s): " + ", ".join(missing)
                                      + " (pip install -r requirements-data.txt)")

    # (Area area, Period period, SiteData site)
    # fetches the data and writes it into site; raises NoData or any error
    def fetch(self, area, period, site):
        raise NotImplementedError


# (str name)
# per-provider download cache: $FIELDSHIFT_CACHE or ~/.cache/fieldshift/<name>
def cache_dir(name):
    root = Path(os.environ.get("FIELDSHIFT_CACHE", Path.home() / ".cache" / "fieldshift"))
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# (str url, dict params = None, float timeout = 60)
# GET a JSON document; raises on HTTP errors
def get_json(url, params=None, timeout=60):
    import requests
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


# (str url, dict params = None, float timeout = 60)
# GET a text document; raises on HTTP errors
def get_text(url, params=None, timeout=60):
    import requests
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.text


# (numpy.ndarray lons, numpy.ndarray lats, Area area)
# boolean mask of the grid cells inside the circle; when none is (radius
# smaller than a cell) the cell nearest to the centre is selected
def circle_mask(lons, lats, area):
    import numpy as np
    lat0, lon0 = np.radians(area.lat), np.radians(area.lon)
    la, lo = np.radians(lats), np.radians(lons)
    a = (np.sin((la - lat0) / 2) ** 2
         + np.cos(lat0) * np.cos(la) * np.sin((lo - lon0) / 2) ** 2)
    dist = 2 * 6_371_008.8 * np.arcsin(np.sqrt(a))
    mask = dist <= area.radius_m
    if not mask.any():
        mask = dist == dist.min()
    return mask


# ()
# logs in to NASA Earthdata with earthaccess (env vars or ~/.netrc);
# raises ProviderUnavailable when no credentials are configured
def earthdata_login():
    import earthaccess
    strategy = "environment" if os.environ.get("EARTHDATA_USERNAME") else "netrc"
    if strategy == "netrc" and not (Path.home() / ".netrc").exists():
        raise ProviderUnavailable("no NASA Earthdata credentials: set EARTHDATA_USERNAME/"
                                  "EARTHDATA_PASSWORD or add urs.earthdata.nasa.gov to ~/.netrc")
    auth = earthaccess.login(strategy=strategy)
    if not auth or not getattr(auth, "authenticated", False):
        raise ProviderUnavailable("NASA Earthdata login failed")
    return auth
