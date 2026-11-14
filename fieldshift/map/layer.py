"""Engine-independent description of map layers."""

from dataclasses import dataclass, field
from enum import Enum


# kind of data a layer holds; each backend maps it to its own provider
class LayerKind(Enum):
    XYZ = "xyz"
    VECTOR = "vector"
    RASTER = "raster"


# what to load: the UI builds one of these and hands it to MapView.add_layer.
# options may hold "provider" (force a data provider) and, for vectors,
# "fill_color" / "stroke_color" (CSS colour strings)
@dataclass(frozen=True)
class LayerSpec:
    name: str
    source: str
    kind: LayerKind
    options: dict = field(default_factory=dict)

    # (str name, str url_template, int zmin = 0, int zmax = 19)
    # tile layer such as OpenStreetMap; url uses {x} {y} {z} placeholders
    @classmethod
    def xyz(cls, name, url, zmin=0, zmax=19):
        return cls(name, url, LayerKind.XYZ, {"zmin": zmin, "zmax": zmax})

    # (str name, str path, **options)
    # vector file readable by OGR: GeoJSON, Shapefile, GeoPackage, KML...
    @classmethod
    def vector(cls, name, path, **options):
        return cls(name, path, LayerKind.VECTOR, options)

    # (str name, str path)
    # raster file readable by GDAL: GeoTIFF, NetCDF, HDF...
    @classmethod
    def raster(cls, name, path):
        return cls(name, path, LayerKind.RASTER)


# what MapView.layers returns: a loaded layer as seen by the UI
@dataclass(frozen=True)
class LayerInfo:
    id: str
    name: str
    kind: LayerKind
    visible: bool
