"""
Tests for semantic correction profiles.
"""

import unittest

import numpy as np

from geometry_correction.algorithms.correction_profiles import DEFAULT_PROFILES, get_profile
from geometry_correction.algorithms.pointcloud import PlaneResult, resolve_plane_profiles
from geometry_correction.algorithms.semantic import PlaneClass


def make_plane(model, centroid, bbox_min, bbox_max, inlier_count=80):
    return PlaneResult(
        model=np.asarray(model, dtype=np.float64),
        inlier_indices=np.arange(inlier_count, dtype=np.int64),
        centroid=np.asarray(centroid, dtype=np.float64),
        bbox_min=np.asarray(bbox_min, dtype=np.float64),
        bbox_max=np.asarray(bbox_max, dtype=np.float64),
        inlier_count=inlier_count,
    )


class TestCorrectionProfiles(unittest.TestCase):
    def test_wall_profile_is_tighter_than_floor_profile(self):
        self.assertLess(
            DEFAULT_PROFILES[PlaneClass.WALL].snap_threshold_m,
            DEFAULT_PROFILES[PlaneClass.FLOOR].snap_threshold_m,
        )

    def test_unknown_profile_is_disabled_by_default(self):
        self.assertFalse(DEFAULT_PROFILES[PlaneClass.UNKNOWN].enabled)

    def test_flat_override_replaces_profile_values(self):
        profile = get_profile(
            PlaneClass.WALL,
            overrides={"snap_threshold_m": 0.02, "enabled": False},
        )
        self.assertEqual(profile.snap_threshold_m, 0.02)
        self.assertFalse(profile.enabled)

    def test_label_specific_override_replaces_profile_values(self):
        profile = get_profile(
            PlaneClass.FLOOR,
            overrides={"floor": {"snap_threshold_m": 0.12, "smoothing_iterations": 4}},
        )
        self.assertEqual(profile.snap_threshold_m, 0.12)
        self.assertEqual(profile.smoothing_iterations, 4)

    def test_resolve_plane_profiles_assigns_distinct_thresholds(self):
        wall = make_plane([1, 0, 0, 0], [0.0, 0.0, 1.0], [0.0, -0.1, 0.0], [0.1, 0.1, 2.5])
        floor = make_plane([0, 0, 1, 0], [0.0, 0.0, 0.0], [-2, -2, 0.0], [2, 2, 0.1])
        resolved = resolve_plane_profiles([wall, floor], np.array([0.0, 0.0, 0.0]))
        thresholds = {entry.classified_plane.label: entry.profile.snap_threshold_m for entry in resolved}
        self.assertLess(thresholds[PlaneClass.WALL], thresholds[PlaneClass.FLOOR])

    def test_resolve_plane_profiles_applies_overrides_end_to_end(self):
        wall = make_plane([1, 0, 0, 0], [0.0, 0.0, 1.0], [0.0, -0.1, 0.0], [0.1, 0.1, 2.5])
        resolved = resolve_plane_profiles(
            [wall],
            np.array([0.0, 0.0, 0.0]),
            overrides={"wall": {"snap_threshold_m": 0.015, "enabled": True}},
        )
        self.assertEqual(resolved[0].profile.snap_threshold_m, 0.015)
        self.assertTrue(resolved[0].profile.enabled)

    def test_unknown_plane_resolves_to_disabled_profile(self):
        unknown = make_plane([0, 0, 1, 0], [0.0, 0.0, 1.0], [-1, -1, 0.95], [1, 1, 1.05])
        resolved = resolve_plane_profiles([unknown], np.array([0.0, 0.0, 0.0]))
        self.assertEqual(resolved[0].classified_plane.label, PlaneClass.UNKNOWN)
        self.assertFalse(resolved[0].profile.enabled)


if __name__ == "__main__":
    unittest.main()
