"""
geometry_correction/tests/test_orthophoto.py

Unit tests for Hough-line detection and rotation correction.
Uses synthetic images — no real GeoTIFF needed.
"""

import unittest
import math
import numpy as np


try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


# ─── pure-python helpers (mirrored from orthophoto.py for isolation) ──────────

def line_angle_deg(x1, y1, x2, y2):
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return angle % 180


def extract_axis_aligned(angles_raw, tolerance=2.0):
    h, v = [], []
    for a in angles_raw:
        if a <= tolerance or a >= (180 - tolerance):
            h.append(a)
        elif abs(a - 90) <= tolerance:
            v.append(a)
    return h, v


def compute_correction_angle(h_angles, v_angles):
    corrections = []
    for a in h_angles:
        corrections.append(180 - a if a > 90 else -a)
    for a in v_angles:
        corrections.append(-(a - 90))
    if not corrections:
        return 0.0
    return float(np.median(corrections))


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLineAngle(unittest.TestCase):

    def test_horizontal_line(self):
        self.assertAlmostEqual(line_angle_deg(0, 0, 100, 0), 0.0)

    def test_vertical_line(self):
        self.assertAlmostEqual(line_angle_deg(0, 0, 0, 100), 90.0)

    def test_diagonal_45(self):
        self.assertAlmostEqual(line_angle_deg(0, 0, 100, 100), 45.0)

    def test_reverse_direction(self):
        # Reversing direction should give supplementary angle mod 180
        a1 = line_angle_deg(0, 0, 100, 5)
        a2 = line_angle_deg(100, 5, 0, 0)
        diff = abs(a1 - a2) % 180
        self.assertAlmostEqual(diff, 0.0, places=5)


class TestExtractAxisAligned(unittest.TestCase):

    def test_horizontal_classification(self):
        h, v = extract_axis_aligned([0.5, 1.0, 179.5], tolerance=2.0)
        self.assertEqual(len(h), 3)
        self.assertEqual(len(v), 0)

    def test_vertical_classification(self):
        h, v = extract_axis_aligned([89.0, 90.5, 91.0], tolerance=2.0)
        self.assertEqual(len(h), 0)
        self.assertEqual(len(v), 3)

    def test_diagonal_ignored(self):
        h, v = extract_axis_aligned([45.0, 30.0, 60.0], tolerance=2.0)
        self.assertEqual(len(h), 0)
        self.assertEqual(len(v), 0)

    def test_mixed(self):
        h, v = extract_axis_aligned([1.0, 89.5, 45.0, 178.0], tolerance=2.0)
        self.assertIn(1.0, h)
        self.assertIn(178.0, h)
        self.assertIn(89.5, v)
        self.assertEqual(len(h), 2)
        self.assertEqual(len(v), 1)


class TestCorrectionAngle(unittest.TestCase):

    def test_perfect_lines_no_correction(self):
        """Perfectly axis-aligned lines need zero correction."""
        self.assertAlmostEqual(compute_correction_angle([0.0], [90.0]), 0.0)

    def test_slight_horizontal_tilt(self):
        """Horizontal lines tilted +1.5° need -1.5° correction."""
        angle = compute_correction_angle([1.5], [])
        self.assertAlmostEqual(angle, -1.5, places=5)

    def test_slight_vertical_tilt(self):
        """Vertical lines at 91.5° need -1.5° correction."""
        angle = compute_correction_angle([], [91.5])
        self.assertAlmostEqual(angle, -1.5, places=5)

    def test_no_lines_returns_zero(self):
        self.assertEqual(compute_correction_angle([], []), 0.0)

    def test_median_used(self):
        """Median should resist an outlier."""
        # Two lines at ~1° tilt, one outlier at 10°
        angle = compute_correction_angle([1.0, 1.2, 10.0], [])
        self.assertAlmostEqual(abs(angle), 1.2, places=0)


@unittest.skipUnless(HAS_CV2, "opencv-python not installed")
class TestHoughDetection(unittest.TestCase):

    def _synthetic_image_with_lines(self, angles_deg, size=512):
        """Draw lines at given angles on a blank image."""
        img = np.zeros((size, size), dtype=np.uint8)
        cx, cy = size // 2, size // 2
        for angle in angles_deg:
            rad = math.radians(angle)
            dx = int(math.cos(rad) * size * 0.45)
            dy = int(math.sin(rad) * size * 0.45)
            cv2.line(img, (cx - dx, cy - dy), (cx + dx, cy + dy), 255, 2)
        return img

    def test_detects_horizontal_line(self):
        from geometry_correction.algorithms.orthophoto import detect_hough_lines
        img = self._synthetic_image_with_lines([0])
        lines = detect_hough_lines(img)
        self.assertIsNotNone(lines)
        self.assertGreater(len(lines), 0)

    def test_detects_vertical_line(self):
        from geometry_correction.algorithms.orthophoto import detect_hough_lines
        img = self._synthetic_image_with_lines([90])
        lines = detect_hough_lines(img)
        self.assertIsNotNone(lines)
        self.assertGreater(len(lines), 0)

    def test_correction_angle_near_zero_for_perfect_grid(self):
        """A perfectly horizontal+vertical grid should yield ~0° correction."""
        from geometry_correction.algorithms.orthophoto import (
            detect_hough_lines, extract_axis_aligned_lines, compute_correction_angle
        )
        img = self._synthetic_image_with_lines([0, 90])
        lines = detect_hough_lines(img)
        h, v = extract_axis_aligned_lines(lines)
        angle = compute_correction_angle(h, v)
        self.assertAlmostEqual(angle, 0.0, places=0)


@unittest.skipUnless(HAS_CV2 and HAS_RASTERIO, "opencv-python and rasterio required")
class TestCorrectOrthophotoIntegration(unittest.TestCase):

    def _make_temp_geotiff(self, path, angle_offset=1.5):
        """Create a tiny synthetic GeoTIFF with a slightly tilted grid."""
        import rasterio
        from rasterio.transform import from_bounds

        size = 256
        arr = np.zeros((3, size, size), dtype=np.uint8)

        # Draw nearly-horizontal lines (tilted by angle_offset degrees)
        for row in range(0, size, 32):
            shift = int(math.tan(math.radians(angle_offset)) * size)
            cv2.line(arr[0], (0, row), (size - 1, row + shift), 255, 1)

        transform = from_bounds(0, 0, 1, 1, size, size)
        profile = {
            "driver": "GTiff", "dtype": "uint8", "width": size, "height": size,
            "count": 3, "crs": "EPSG:4326", "transform": transform,
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr)

    def test_correction_produces_output(self):
        import tempfile, os
        from geometry_correction.algorithms.orthophoto import correct_orthophoto

        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "test_ortho.tif")
            out = os.path.join(tmp, "test_ortho_corrected.tif")
            self._make_temp_geotiff(inp, angle_offset=1.5)

            stats = correct_orthophoto(inp, out, angle_tolerance=2.0)

            self.assertIn("correction_angle_deg", stats)
            self.assertTrue(os.path.exists(out))
            self.assertIsInstance(stats["total_lines_detected"], int)


if __name__ == "__main__":
    unittest.main()
