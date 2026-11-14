"""Chooses the map engine."""

from fieldshift.qt import HAS_QGIS


# (str backend = None)
# returns a MapView: "qgis" (default when QGIS is installed) or "placeholder"
def create_map_view(backend=None):
    backend = backend or ("qgis" if HAS_QGIS else "placeholder")
    if backend == "qgis":
        from fieldshift.map.qgis_view import QgisMapView
        return QgisMapView()
    if backend == "placeholder":
        from fieldshift.map.placeholder_view import PlaceholderMapView
        return PlaceholderMapView()
    raise ValueError(f"unknown map backend: {backend!r}")
