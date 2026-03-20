"""
geometry_correction/tests/test_pointcloud.py

Unit tests for RANSAC plane detection and point snapping.
Uses synthetic point clouds — no real drone data needed.
"""

import unittest
import numpy as np


# ─── minimal stubs so tests run without open3d installed ──────────────────────
try:
    import open3d as o3d
    HAS_OPEN3D = True
except ImportError:
    HAS_OPEN3D = False

# ─────────────────────────────────────────────────────────────────────────────
# Pure-numpy helpers (extracted from pointcloud.py for isolated testing)
# ─────────────────────────────────────────────────────────────────────────────

def signed_distance_to_plane(points, plane):
    a, b, c, d = plane
    normal = np.array([a, b, c])
    return (points @ normal + d) / np.linalg.norm(normal)


def project_onto_plane(points, plane):
    a, b, c, d = plane
    normal = np.array([a, b, c])
    norm_sq = np.dot(normal, normal)
    distances = (points @ normal + d) / norm_sq
    return points - np.outer(distances, normal)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSignedDistance(unittest.TestCase):

    def test_points_on_xy_plane(self):
        """Points with z=0 should have zero distance to the XY plane (z=0)."""
        pts = np.array([[1., 2., 0.], [3., 4., 0.], [-1., -5., 0.]])
        plane = np.array([0., 0., 1., 0.])   # z = 0
        dists = signed_distance_to_plane(pts, plane)
        np.testing.assert_allclose(dists, [0., 0., 0.], atol=1e-9)

    def test_points_above_below_plane(self):
        """z=1 is +1 above XY plane; z=-2 is -2 below."""
        pts = np.array([[0., 0., 1.], [0., 0., -2.]])
        plane = np.array([0., 0., 1., 0.])
        dists = signed_distance_to_plane(pts, plane)
        np.testing.assert_allclose(dists, [1., -2.], atol=1e-9)

    def test_oblique_plane(self):
        """Distance from origin to plane x+y+z=3 (normalised) should be 3/√3."""
        pts = np.array([[0., 0., 0.]])
        plane = np.array([1., 1., 1., -3.])   # x+y+z-3=0
        d = signed_distance_to_plane(pts, plane)
        expected = -3.0 / np.sqrt(3)
        np.testing.assert_allclose(d, [expected], atol=1e-9)


class TestProjectOntoPlane(unittest.TestCase):

    def test_project_to_xy_plane(self):
        """Any point projected to z=0 should have z=0."""
        pts = np.array([[1., 2., 0.5], [3., 4., -0.3]])
        plane = np.array([0., 0., 1., 0.])
        proj = project_onto_plane(pts, plane)
        np.testing.assert_allclose(proj[:, 2], [0., 0.], atol=1e-9)
        # XY unchanged
        np.testing.assert_allclose(proj[:, :2], pts[:, :2], atol=1e-9)

    def test_idempotent(self):
        """Projecting an already-on-plane point should not move it."""
        pts = np.array([[5., -3., 0.]])
        plane = np.array([0., 0., 1., 0.])
        proj = project_onto_plane(pts, plane)
        np.testing.assert_allclose(proj, pts, atol=1e-9)

    def test_vertical_wall(self):
        """Project points to the YZ plane (x=0, plane: [1,0,0,0])."""
        pts = np.array([[2., 3., 4.], [-1., 5., 6.]])
        plane = np.array([1., 0., 0., 0.])
        proj = project_onto_plane(pts, plane)
        np.testing.assert_allclose(proj[:, 0], [0., 0.], atol=1e-9)
        np.testing.assert_allclose(proj[:, 1:], pts[:, 1:], atol=1e-9)


class TestSnapThreshold(unittest.TestCase):

    def _snap_points(self, pts, plane, snap_threshold):
        """Minimal re-implementation of the snap logic for testing."""
        dists = np.abs(signed_distance_to_plane(pts, plane))
        snap_mask = dists < snap_threshold
        result = pts.copy()
        if snap_mask.any():
            result[snap_mask] = project_onto_plane(pts[snap_mask], plane)
        return result, snap_mask

    def test_only_close_points_snapped(self):
        """Points within threshold get snapped; far points are untouched."""
        plane = np.array([0., 0., 1., 0.])           # z = 0
        pts = np.array([
            [0., 0., 0.03],   # 3 cm — SHOULD be snapped (< 5 cm)
            [0., 0., 0.08],   # 8 cm — should NOT be snapped
            [0., 0., -0.04],  # 4 cm below — SHOULD be snapped
        ])
        result, mask = self._snap_points(pts, plane, snap_threshold=0.05)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])
        self.assertTrue(mask[2])
        np.testing.assert_allclose(result[0, 2], 0., atol=1e-9)
        np.testing.assert_allclose(result[2, 2], 0., atol=1e-9)
        np.testing.assert_allclose(result[1, 2], 0.08, atol=1e-9)  # unchanged

    def test_zero_threshold_snaps_nothing(self):
        pts = np.array([[0., 0., 0.01]])
        plane = np.array([0., 0., 1., 0.])
        result, mask = self._snap_points(pts, plane, snap_threshold=0.0)
        self.assertFalse(mask[0])
        np.testing.assert_allclose(result, pts)


@unittest.skipUnless(HAS_OPEN3D, "open3d not installed")
class TestOpen3DIntegration(unittest.TestCase):

    def _make_noisy_wall(self, n=500, noise_std=0.02):
        """Create a synthetic flat wall in the XZ plane with Gaussian noise."""
        rng = np.random.default_rng(42)
        x = rng.uniform(0, 5, n)
        z = rng.uniform(0, 3, n)
        y = rng.normal(0, noise_std, n)   # wall at y≈0 with noise
        pts = np.column_stack([x, y, z])
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        return pcd

    def test_detect_wall_plane(self):
        from geometry_correction.algorithms.pointcloud import detect_planes
        pcd = self._make_noisy_wall(n=600)
        planes = detect_planes(pcd, distance_threshold=0.05, min_inliers=100)
        self.assertGreaterEqual(len(planes), 1)
        # The detected plane normal should be approximately [0, ±1, 0]
        a, b, c, d = planes[0][0]
        normal = np.array([a, b, c]) / np.linalg.norm([a, b, c])
        self.assertAlmostEqual(abs(normal[1]), 1.0, places=1)

    def test_snap_reduces_deviation(self):
        from geometry_correction.algorithms.pointcloud import (
            detect_planes, snap_points_to_planes
        )
        pcd = self._make_noisy_wall(n=600, noise_std=0.03)
        planes = detect_planes(pcd, distance_threshold=0.05, min_inliers=100)
        corrected = snap_points_to_planes(pcd, planes, snap_threshold=0.04)

        original_pts = np.asarray(pcd.points)
        corrected_pts = np.asarray(corrected.points)

        # Wall normal is ~Y; corrected Y values should be closer to 0
        orig_std = np.std(original_pts[:, 1])
        corr_std = np.std(corrected_pts[:, 1])
        self.assertLess(corr_std, orig_std,
                        "Corrected point cloud should have lower Y deviation")


if __name__ == "__main__":
    unittest.main()
