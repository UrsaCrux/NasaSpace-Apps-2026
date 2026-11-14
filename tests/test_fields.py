"""Tests for saved fields: create, delete, names and GeoJSON export (no map)."""

import json
import tempfile
import unittest
from pathlib import Path

from fieldshift.fields import FieldStore, polygon_area_ha

# about 1.1 km x 1.1 km near Santiago, clockwise on purpose
SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


class FieldStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "fields"
        self.store = FieldStore(self.folder)

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_writes_a_geojson_file(self):
        field = self.store.create("  North plot ", SQUARE, created="2026-11-14T12:00:00+00:00")
        self.assertEqual(field.name, "North plot")
        self.assertTrue(field.path.is_file())
        data = json.loads(field.path.read_text("utf-8"))
        feature = data["features"][0]
        self.assertEqual(feature["properties"]["name"], "North plot")
        ring = feature["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])              # closed ring
        self.assertEqual(len(ring), 5)
        self.assertEqual([f.name for f in self.store.fields()], ["North plot"])

    def test_ring_is_counter_clockwise(self):
        (x1, y1), (x2, y2), (x3, y3) = self.store.create("a", SQUARE).vertices[:3]
        self.assertGreater((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1), 0)

    def test_names_are_required_and_unique_ignoring_case(self):
        self.store.create("Field 1", SQUARE)
        self.assertEqual(self.store.name_problem("   "), "empty")
        self.assertEqual(self.store.name_problem("field 1"), "duplicate")
        self.assertIsNone(self.store.name_problem("Field 2"))
        with self.assertRaises(ValueError):
            self.store.create("FIELD 1", SQUARE)

    def test_suggest_name_fills_the_first_gap(self):
        self.assertEqual(self.store.suggest_name("Field"), "Field 1")
        self.store.create("Field 1", SQUARE)
        self.store.create("Field 3", SQUARE)
        self.assertEqual(self.store.suggest_name("Field"), "Field 2")

    def test_needs_three_distinct_vertices(self):
        with self.assertRaises(ValueError):
            self.store.create("line", [(0, 0), (1, 1), (1, 1), (0, 0)])

    def test_unsafe_characters_in_names(self):
        a = self.store.create("Lote 1/2: sur", SQUARE)
        b = self.store.create("Lote 1_2_ sur", SQUARE)   # same file stem
        self.assertEqual(a.path.parent, self.folder)
        self.assertNotEqual(a.path, b.path)
        self.assertEqual(self.store.get("lote 1/2: SUR").name, "Lote 1/2: sur")

    def test_delete(self):
        field = self.store.create("Field 1", SQUARE)
        self.assertTrue(self.store.delete("field 1"))
        self.assertFalse(field.path.exists())
        self.assertFalse(self.store.delete("Field 1"))
        self.assertEqual(self.store.fields(), [])

    def test_export_feature_collection(self):
        self.store.create("A", SQUARE, created="2026-01-01T00:00:00+00:00")
        self.store.create("B", [(0, 0), (0.01, 0), (0, 0.01)], created="2026-01-02T00:00:00+00:00")
        out = Path(self._tmp.name) / "all.geojson"
        self.assertEqual(self.store.export(out), 2)
        data = json.loads(out.read_text("utf-8"))
        self.assertEqual(data["type"], "FeatureCollection")
        props = [f["properties"] for f in data["features"]]
        self.assertEqual([p["name"] for p in props], ["A", "B"])
        self.assertEqual(props[0]["created"], "2026-01-01T00:00:00+00:00")
        self.assertGreater(props[0]["area_ha"], 0)

    def test_broken_files_are_skipped(self):
        self.store.create("ok", SQUARE)
        (self.folder / "broken.geojson").write_text("{not json", "utf-8")
        self.assertEqual([f.name for f in self.store.fields()], ["ok"])


class AreaTest(unittest.TestCase):
    def test_one_degree_square_at_the_equator(self):
        # R^2 * 1 deg * sin(1 deg) = 12 391 km2 on the sphere used here
        area = polygon_area_ha([(0, 0), (1, 0), (1, 1), (0, 1)])
        self.assertAlmostEqual(area / 1_239_140, 1, delta=0.001)

    def test_santiago_square_and_orientation(self):
        area = polygon_area_ha(SQUARE)
        self.assertAlmostEqual(area, polygon_area_ha(SQUARE[::-1]))
        self.assertAlmostEqual(area / 103.3, 1, delta=0.02)   # ~0.93 km x 1.11 km


if __name__ == "__main__":
    unittest.main()
