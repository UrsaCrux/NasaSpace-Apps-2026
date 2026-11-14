"""Fields (farm plots) drawn by the user: storage and geometry helpers.

store.py does not depend on Qt or QGIS, so it can be tested and reused
anywhere (export scripts, data processing...). manager.py
(``FieldsManager``) shows the fields on a MapView.
"""

from fieldshift.fields.store import (
    DEFAULT_FIELDS_DIR,
    Field,
    FieldStore,
    polygon_area_ha,
    to_feature,
)

__all__ = ["DEFAULT_FIELDS_DIR", "Field", "FieldStore", "polygon_area_ha", "to_feature"]
