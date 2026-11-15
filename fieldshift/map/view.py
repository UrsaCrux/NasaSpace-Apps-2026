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
        # emitted with (list vertices) when the user closes a polygon started
        # with start_polygon_drawing; vertices are (lon, lat) tuples and the
        # first one is not repeated at the end
        self.polygon_drawn = Event()
        # emitted with no arguments when a drawing ends without a polygon
        self.drawing_cancelled = Event()
        # emitted with (str layer_id, float lon, float lat) when the user
        # double-clicks a feature of a layer that is not locked (topmost
        # layer first). never while drawing a polygon. a double click on a
        # feature does not zoom the map in
        self.layer_double_clicked = Event()
        # emitted with no arguments after the visible area changes (pan, zoom,
        # resize); read meters_per_pixel() to draw a scale bar
        self.view_changed = Event()
        # emitted with (str layer_id or None, float lon, float lat) when the
        # mouse moves onto a feature of another visible, unlocked layer, or off
        # every feature (None). not while dragging or drawing
        self.layer_hovered = Event()
        # emitted with (str layer_id, float lon, float lat) when the user
        # right-clicks a feature of a visible, unlocked layer (topmost first);
        # not while drawing. the UI opens its menu there
        self.layer_right_clicked = Event()

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

    # ()
    # lets the user draw a polygon on the map (click adds a vertex; double
    # click, right click or a click on the first vertex closes it; Backspace
    # removes the last vertex; Esc cancels). ends with polygon_drawn or
    # drawing_cancelled, then the map goes back to panning
    @abstractmethod
    def start_polygon_drawing(self):
        ...

    # ()
    # stops the current drawing and emits drawing_cancelled; no-op when idle
    @abstractmethod
    def cancel_drawing(self):
        ...

    # ()
    # True while a drawing started with start_polygon_drawing is in progress
    @abstractmethod
    def is_drawing(self):
        ...

    # ()
    # ground distance in metres covered by one screen pixel, measured across
    # the centre of the view (it changes with latitude in Web Mercator), or
    # None when the backend cannot tell
    @abstractmethod
    def meters_per_pixel(self):
        ...

    # (float factor)
    # zooms around the centre of the view: the visible width is multiplied by
    # factor (0.5 zooms in twice as close, 2 zooms out)
    @abstractmethod
    def zoom_by(self, factor):
        ...

    # (list vertices)
    # draws a bright outline around this (lon, lat) polygon, on top of every
    # layer; None removes it. only one polygon is highlighted at a time
    @abstractmethod
    def set_highlight(self, vertices):
        ...

    # ()
    # the highlighted (lon, lat) vertices, or None
    @abstractmethod
    def highlighted(self):
        ...

    # (list polygons)
    # draws a thick outline around each (lon, lat) polygon of the list (the
    # fields the user checked), under the hover highlight; [] removes them
    @abstractmethod
    def set_marked(self, polygons):
        ...

    # ()
    # the polygons given to set_marked, as lists of (lon, lat) tuples
    @abstractmethod
    def marked(self):
        ...
