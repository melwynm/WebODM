"""
Tests for confidence map generation and orthophoto correction stats.
"""

import os
import tempfile
import unittest
from unittest import mock

import numpy as np

try:
    import rasterio
    from rasterio.transform import from_origin

    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

from geometry_correction.algorithms.confidence_map import (
    compute_correction_coverage_pct,
    generate_confidence_map,
)
from geometry_correction.algorithms.orthophoto import run_orthophoto_correction


@unittest.skipUnless(HAS_RASTERIO, "rasterio not installed")
class TestConfidenceMap(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "driver": "GTiff",
            "dtype": "uint8",
            "width": 4,
            "height": 4,
            "count": 3,
            "crs": "EPSG:4326",
            "transform": from_origin(10, 20, 0.5, 0.5),
        }

    def _read_map(self, path):
        with rasterio.open(path) as dataset:
            return dataset.read(1), dataset.profile.copy(), dataset.transform, dataset.crs

    def test_unchanged_image_produces_zero_map(self):
        image = np.zeros((3, 4, 4), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "confidence.tif")
            path = generate_confidence_map(image, image.copy(), self.profile, output)
            data, _, _, _ = self._read_map(path)
            self.assertTrue(np.all(data == 0))

    def test_shifted_image_produces_non_zero_map(self):
        original = np.zeros((3, 4, 4), dtype=np.uint8)
        corrected = np.full((3, 4, 4), 255, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "confidence.tif")
            path = generate_confidence_map(original, corrected, self.profile, output)
            data, _, _, _ = self._read_map(path)
            self.assertGreater(int(data.max()), 0)

    def test_compute_coverage_returns_zero_for_identical_map(self):
        data = np.zeros((4, 4), dtype=np.uint8)
        self.assertEqual(compute_correction_coverage_pct(data), 0.0)

    def test_compute_coverage_returns_hundred_for_all_changed_pixels(self):
        data = np.full((4, 4), 255, dtype=np.uint8)
        self.assertEqual(compute_correction_coverage_pct(data), 100.0)

    def test_output_preserves_crs_and_transform(self):
        original = np.zeros((3, 4, 4), dtype=np.uint8)
        corrected = np.full((3, 4, 4), 255, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_confidence_map(original, corrected, self.profile, os.path.join(tmp, "confidence.tif"))
            _, _, transform, crs = self._read_map(path)
            self.assertEqual(transform, self.profile["transform"])
            self.assertEqual(crs.to_string(), "EPSG:4326")

    def test_output_is_single_band_uint8(self):
        original = np.zeros((3, 4, 4), dtype=np.uint8)
        corrected = np.full((3, 4, 4), 255, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_confidence_map(original, corrected, self.profile, os.path.join(tmp, "confidence.tif"))
            _, profile, _, _ = self._read_map(path)
            self.assertEqual(profile["count"], 1)
            self.assertEqual(profile["dtype"], "uint8")

    def test_threshold_changes_reported_coverage(self):
        data = np.array([[0, 4, 5, 6]], dtype=np.uint8)
        self.assertEqual(compute_correction_coverage_pct(data, threshold=5), 25.0)
        self.assertEqual(compute_correction_coverage_pct(data, threshold=3), 75.0)

    def test_run_orthophoto_correction_populates_confidence_stats(self):
        source = np.zeros((3, 8, 8), dtype=np.uint8)
        profile = {
            "driver": "GTiff",
            "dtype": "uint8",
            "width": 8,
            "height": 8,
            "count": 3,
            "crs": "EPSG:4326",
            "transform": from_origin(5, 10, 1, 1),
        }

        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "source.tif")
            output_path = os.path.join(tmp, "corrected.tif")
            with rasterio.open(input_path, "w", **profile) as dataset:
                dataset.write(source)

            corrected = np.full_like(source, 20)
            fake_lines = np.array([[[0, 0, 7, 0]]], dtype=np.int32)

            with mock.patch("geometry_correction.algorithms.orthophoto._require_cv2"), \
                 mock.patch("geometry_correction.algorithms.orthophoto.detect_hough_lines", return_value=fake_lines), \
                 mock.patch("geometry_correction.algorithms.orthophoto.compute_correction_angle", return_value=1.5), \
                 mock.patch("geometry_correction.algorithms.orthophoto.rotate_image_array", return_value=corrected):
                stats = run_orthophoto_correction(
                    input_path,
                    output_path,
                    angle_tolerance=2.0,
                    generate_confidence_map=True,
                )

            self.assertTrue(stats.correction_applied)
            self.assertTrue(os.path.exists(stats.confidence_map_path))
            self.assertGreater(stats.coverage_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
