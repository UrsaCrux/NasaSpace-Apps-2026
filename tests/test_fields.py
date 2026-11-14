"""Tests for saved fields: create, delete, names and GeoJSON export (no map)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_export_some_names(self):
        self.store.create("A", SQUARE)
        self.store.create("B", SQUARE)
        out = Path(self._tmp.name) / "b.geojson"
        self.assertEqual(self.store.export(out, ["b"]), 1)
        data = json.loads(out.read_text("utf-8"))
        self.assertEqual([f["properties"]["name"] for f in data["features"]], ["B"])

    def test_broken_files_are_skipped(self):
        self.store.create("ok", SQUARE)
        (self.folder / "broken.geojson").write_text("{not json", "utf-8")
        self.assertEqual([f.name for f in self.store.fields()], ["ok"])


class FolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_default_folder_is_terrenos_in_the_repo_root(self):
        from fieldshift.fields import store
        self.assertEqual(store.DEFAULT_FIELDS_DIR.name, "terrenos")
        self.assertTrue((store.REPO_DIR / "fieldshift").is_dir())
        self.assertEqual(store.DEFAULT_FIELDS_DIR.parent, store.REPO_DIR)

    def test_old_files_are_moved(self):
        from fieldshift.fields import store
        old, new = self.root / "old", self.root / "terrenos"
        FieldStore(old).create("A", SQUARE)
        FieldStore(old).create("B", SQUARE)
        with mock.patch("sys.stderr"):
            self.assertEqual(store.migrate_fields(old, new), 2)
        self.assertFalse(old.exists())                 # empty folder is removed
        self.assertEqual([f.name for f in FieldStore(new).fields()], ["A", "B"])

    def test_existing_file_is_not_overwritten(self):
        from fieldshift.fields import store
        old, new = self.root / "old", self.root / "new"
        FieldStore(old).create("A", SQUARE)
        FieldStore(new).create("A", [(0, 0), (1, 0), (0, 1)])
        with mock.patch("sys.stderr"):
            self.assertEqual(store.migrate_fields(old, new), 0)
        self.assertTrue((old / "A.geojson").is_file())           # kept
        self.assertEqual(FieldStore(new).get("A").vertices[1], (1.0, 0.0))

    def test_default_store_migrates_and_env_var_wins(self):
        from fieldshift.fields import store
        old, new = self.root / "legacy", self.root / "default"
        FieldStore(old).create("Old field", SQUARE)
        with mock.patch.object(store, "LEGACY_FIELDS_DIR", old), \
                mock.patch.object(store, "DEFAULT_FIELDS_DIR", new), \
                mock.patch("sys.stderr"):
            with mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": str(self.root / "x")}):
                self.assertEqual(FieldStore().folder, self.root / "x")
                self.assertTrue(old.exists())          # env var: nothing is moved
            with mock.patch.dict(os.environ):
                os.environ.pop("FIELDSHIFT_FIELDS_DIR", None)
                self.assertEqual([f.name for f in FieldStore().fields()], ["Old field"])
        self.assertTrue((new / "Old field.geojson").is_file())


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
