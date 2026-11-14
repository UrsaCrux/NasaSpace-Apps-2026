"""Map abstraction layer.

The rest of the application only talks to :class:`MapView` and
:class:`LayerSpec`. The concrete engine (QGIS today) lives behind
:func:`create_map_view`, so it can be replaced or mocked without touching the
UI.
"""

from fieldshift.map.events import Event
from fieldshift.map.layer import LayerInfo, LayerKind, LayerSpec
from fieldshift.map.view import MapView
from fieldshift.map.factory import create_map_view

__all__ = [
    "Event",
    "LayerInfo",
    "LayerKind",
    "LayerSpec",
    "MapView",
    "create_map_view",
]
