"""Abstract map view. Every map engine implements this interface."""

from abc import ABC, abstractmethod

from fieldshift.map.events import Event


# abstract map: the only map API the UI is allowed to use.
# coordinates are always longitude / latitude in degrees (EPSG:4326)
class MapView(ABC):

    # ()
    # sets up the events; subclasses must call super().__init__()
    def __init__(self):
        # emitted with (float lon, float lat) when the mouse moves over the map
        self.cursor_moved = Event()
        # emitted with (float lon, float lat) when the map is clicked
        self.clicked = Event()
        # emitted with no arguments after a layer is added, removed or toggled
        self.layers_changed = Event()

    # ()
    # the QWidget to put in a window; created once and reused
    @abstractmethod
    def widget(self):
        ...

    # (LayerSpec spec)
    # loads the layer on top of the others; returns its id. raises
    # ValueError when the source cannot be opened
    @abstractmethod
    def add_layer(self, spec):
        ...

    # (str layer_id)
    # removes a layer added with add_layer; unknown ids are ignored
    @abstractmethod
    def remove_layer(self, layer_id):
        ...

    # ()
    # list of LayerInfo, top layer first
    @abstractmethod
    def layers(self):
        ...

    # (str layer_id, bool visible)
    # shows or hides a layer without removing it
    @abstractmethod
    def set_layer_visible(self, layer_id, visible):
        ...

    # (float lon, float lat, float scale = None)
    # centres the map on a point; keeps the current scale when none is given
    @abstractmethod
    def set_center(self, lon, lat, scale=None):
        ...

    # (float xmin, float ymin, float xmax, float ymax)
    # fits the view to a lon/lat bounding box
    @abstractmethod
    def zoom_to_extent(self, xmin, ymin, xmax, ymax):
        ...

    # (str layer_id)
    # fits the view to the extent of one layer
    @abstractmethod
    def zoom_to_layer(self, layer_id):
        ...

    # ()
    # redraws the map
    @abstractmethod
    def refresh(self):
        ...
