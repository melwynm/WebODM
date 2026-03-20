"""
Tests for semantic plane classification.
"""

import unittest

import numpy as np

from geometry_correction.algorithms.pointcloud import PlaneResult
from geometry_correction.algorithms.semantic import PlaneClass, classify_planes


def make_plane(model, centroid, bbox_min, bbox_max, inlier_count=100):
    return PlaneResult(
        model=np.asarray(model, dtype=np.float64),
        inlier_indices=np.arange(inlier_count, dtype=np.int64),
        centroid=np.asarray(centroid, dtype=np.float64),
        bbox_min=np.asarray(bbox_min, dtype=np.float64),
        bbox_max=np.asarray(bbox_max, dtype=np.float64),
        inlier_count=inlier_count,
    )


class TestSemanticClassification(unittest.TestCase):
    def test_classify_floor_from_horizontal_low_plane(self):
        plane = make_plane([0, 0, 1, 0], [0, 0, 0.1], [-2, -2, 0], [2, 2, 0.2])
        classified = classify_planes([plane], np.array([0.0, 0.0, 0.0]))
        self.assertEqual(classified[0].label, PlaneClass.FLOOR)

    def test_classify_roof_from_horizontal_high_plane(self):
        plane = make_plane([0, 0, 1, -3], [0, 0, 3.0], [-2, -2, 2.8], [2, 2, 3.2])
        classified = classify_planes([plane], np.array([0.0, 0.0, 0.5]))
        self.assertEqual(classified[0].label, PlaneClass.ROOF)

    def test_classify_wall_from_vertical_plane(self):
        plane = make_plane([1, 0, 0, 0], [0.0, 0.0, 1.5], [0.0, -0.1, 0.0], [0.1, 0.1, 3.0])
        classified = classify_planes([plane], np.array([0.0, 0.0, 1.0]))
        self.assertEqual(classified[0].label, PlaneClass.WALL)

    def test_classify_ramp_from_diagonal_plane(self):
        plane = make_plane([0.0, 0.7, 0.7, 0.0], [0.0, 0.0, 0.9], [-2, -2, 0.0], [2, 2, 1.8])
        classified = classify_planes([plane], np.array([0.0, 0.0, 0.5]))
        self.assertEqual(classified[0].label, PlaneClass.RAMP)

    def test_floor_confidence_is_higher_for_perfect_normal(self):
        perfect = make_plane([0, 0, 1, 0], [0, 0, 0.0], [-2, -2, 0.0], [2, 2, 0.1])
        borderline = make_plane([0, 0.51, 0.86, 0], [0, 0, 0.0], [-2, -2, 0.0], [2, 2, 0.1])
        classified = classify_planes([perfect, borderline], np.array([0.0, 0.0, 0.0]))
        self.assertGreater(classified[0].confidence, classified[1].confidence)

    def test_wall_and_floor_in_same_cloud_get_different_labels(self):
        wall = make_plane([1, 0, 0, 0], [0.0, 0.0, 1.0], [0.0, -0.1, 0.0], [0.1, 0.1, 2.5])
        floor = make_plane([0, 0, 1, 0], [0.0, 0.0, 0.0], [-2, -2, 0.0], [2, 2, 0.1])
        classified = classify_planes([wall, floor], np.array([0.0, 0.0, 0.0]))
        self.assertEqual(classified[0].label, PlaneClass.WALL)
        self.assertEqual(classified[1].label, PlaneClass.FLOOR)

    def test_exact_low_boundary_is_ramp(self):
        plane = make_plane([0.953939, 0.0, 0.3, 0.0], [0.0, 0.0, 1.0], [-1, -1, 0.0], [1, 1, 2.0])
        classified = classify_planes([plane], np.array([0.0, 0.0, 0.5]))
        self.assertEqual(classified[0].label, PlaneClass.RAMP)

    def test_exact_high_boundary_is_ramp(self):
        plane = make_plane([0.526783, 0.0, 0.85, 0.0], [0.0, 0.0, 1.2], [-1, -1, 0.0], [1, 1, 2.4])
        classified = classify_planes([plane], np.array([0.0, 0.0, 0.5]))
        self.assertEqual(classified[0].label, PlaneClass.RAMP)

    def test_mid_height_horizontal_plane_remains_unknown(self):
        plane = make_plane([0, 0, 1, 0], [0.0, 0.0, 1.0], [-2, -2, 0.9], [2, 2, 1.1])
        classified = classify_planes([plane], np.array([0.0, 0.0, 0.0]))
        self.assertEqual(classified[0].label, PlaneClass.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
