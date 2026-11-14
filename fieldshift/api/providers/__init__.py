"""Registry of data providers used by get_site_data."""

from fieldshift.api.providers.base import NoData, Provider, ProviderUnavailable
from fieldshift.api.providers.catalog import PLANNED
from fieldshift.api.providers.copernicus_dem import CopernicusDemProvider
from fieldshift.api.providers.era5_land import Era5LandProvider
from fieldshift.api.providers.firms import FirmsProvider
from fieldshift.api.providers.gpm_imerg import GpmImergProvider
from fieldshift.api.providers.smap import SmapProvider
from fieldshift.api.providers.soilgrids import SoilGridsProvider
from fieldshift.api.providers.wapor import WaporProvider

# implemented providers, in the order they are reported
PROVIDERS = [
    SoilGridsProvider,
    CopernicusDemProvider,
    WaporProvider,
    Era5LandProvider,
    SmapProvider,
    GpmImergProvider,
    FirmsProvider,
]

__all__ = ["PLANNED", "PROVIDERS", "NoData", "Provider", "ProviderUnavailable"]
