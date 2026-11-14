"""get_site_data: runs every provider for one area and collects the results."""

import time
from concurrent.futures import ThreadPoolExecutor

from fieldshift.api.geo import Area, Period
from fieldshift.api.models import SiteData, SourceStatus
from fieldshift.api.providers import PLANNED, PROVIDERS, NoData, ProviderUnavailable


# (float lon, float lat, float radius_m = 1000, date|str start = None,
#  date|str end = None, list providers = None, bool include_planned = True)
# queries every data source for the circle around (lon, lat) and returns a
# SiteData. start/end default to the 7 days ending a week ago. providers is an
# optional list of provider names (see list_providers) to limit the query.
# Never raises because of a source: see SiteData.sources for each outcome
def get_site_data(lon, lat, radius_m=1000.0, start=None, end=None, providers=None,
                  include_planned=True):
    area = Area(lon, lat, radius_m)
    period = Period.make(start, end)
    site = SiteData(area, period)

    selected = [cls() for cls in PROVIDERS if providers is None or cls.name in providers]
    with ThreadPoolExecutor(max_workers=max(len(selected), 1)) as pool:
        site.sources = list(pool.map(lambda p: _run(p, area, period, site), selected))

    if include_planned and providers is None:
        site.sources += [SourceStatus(name, "planned", f"{what} ({url})")
                         for name, what, url, _ in PLANNED]
    return site


# ()
# list of (name, title, status) for every provider: implemented or planned
def list_providers():
    rows = [(cls.name, cls.title, "implemented") for cls in PROVIDERS]
    rows += [(name, what, "planned") for name, what, _, _ in PLANNED]
    return rows


def _run(provider, area, period, site):
    t0 = time.monotonic()
    try:
        provider.check()
        provider.fetch(area, period, site)
        status, message = "ok", ""
    except ProviderUnavailable as exc:
        status, message = "skipped", str(exc)
    except NoData as exc:
        status, message = "no_data", str(exc)
    except Exception as exc:                    # one source must not stop the others
        status, message = "error", f"{type(exc).__name__}: {exc}"[:300]
    return SourceStatus(provider.name, status, message, round(time.monotonic() - t0, 2))
