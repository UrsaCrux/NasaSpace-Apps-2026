"""Tests for the C++ core bindings (skipped until `make cpp` is run)."""

import unittest

from fieldshift import native


@unittest.skipUnless(native.is_available(), "C++ core not built (make cpp)")
class NativeTest(unittest.TestCase):
    def test_version(self):
        self.assertRegex(native.version(), r"^\d+\.\d+\.\d+$")

    def test_ndvi(self):
        self.assertAlmostEqual(native.ndvi(0.6, 0.2), 0.5)
        self.assertEqual(native.ndvi(0.0, 0.0), 0.0)
        for got, want in zip(native.ndvi_array([0.6, 0.0], [0.2, 0.0]), [0.5, 0.0]):
            self.assertAlmostEqual(got, want)

    def test_haversine(self):
        # Santiago -> Concepción is about 430 km
        self.assertAlmostEqual(native.haversine_km(-33.45, -70.66, -36.82, -73.05), 430, delta=15)


if __name__ == "__main__":
    unittest.main()
