"""
geometry_correction/algorithms/pointcloud.py

RANSAC-based plane detection and point projection for correcting
photogrammetric point clouds and meshes.

Pipeline:
  1. Load .laz / .ply point cloud
  2. Detect dominant planes (walls, floors, rooftops) with RANSAC
  3. Snap nearby-deviating points onto their detected planes
  4. Optionally re-mesh with Poisson surface reconstruction
  5. Save corrected outputs
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None  # handled at runtime

try:
    import laspy
except ImportError:
    laspy = None

from .. import config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _require_open3d():
    if o3d is None:
        raise ImportError(
            "open3d is required for point-cloud correction. "
            "Install it with:  pip install open3d"
        )


def load_pointcloud(path: str | Path) -> "o3d.geometry.PointCloud":
    """
    Load a .ply, .laz, or .las file into an Open3D PointCloud.
    LAZ/LAS are converted via laspy → numpy → Open3D.
    """
    _require_open3d()
    path = Path(path)

    if path.suffix.lower() == ".ply":
        pcd = o3d.io.read_point_cloud(str(path))
        logger.info("Loaded PLY: %d points", len(pcd.points))
        return pcd

    if path.suffix.lower() in (".laz", ".las"):
        if laspy is None:
            raise ImportError("laspy is required for LAZ/LAS files: pip install laspy[lazrs]")
        las = laspy.read(str(path))
        xyz = np.vstack((las.x, las.y, las.z)).T
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
        if hasattr(las, "red"):
            rgb = np.vstack((las.red, las.green, las.blue)).T / 65535.0
            pcd.colors = o3d.utility.Vector3dVector(rgb.astype(np.float64))
        logger.info("Loaded LAZ/LAS: %d points", len(pcd.points))
        return pcd

    raise ValueError(f"Unsupported point cloud format: {path.suffix}")


def save_pointcloud(pcd: "o3d.geometry.PointCloud", path: str | Path) -> None:
    _require_open3d()
    o3d.io.write_point_cloud(str(path), pcd)
    logger.info("Saved corrected point cloud → %s", path)


# ─────────────────────────────────────────────────────────────────────────────
# Plane detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_planes(
    pcd: "o3d.geometry.PointCloud",
    distance_threshold: float = config.PLANE_DISTANCE_THRESHOLD,
    ransac_n: int = config.PLANE_RANSAC_N,
    num_iterations: int = config.PLANE_NUM_ITERATIONS,
    min_inliers: int = config.PLANE_MIN_INLIERS,
    max_planes: int = 20,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Iteratively detect dominant planes in the point cloud using RANSAC.

    Returns:
        List of (plane_model, inlier_indices) tuples.
        plane_model is [a, b, c, d] where ax+by+cz+d=0.
    """
    _require_open3d()
    remaining = pcd
    planes: List[Tuple[np.ndarray, np.ndarray]] = []
    all_indices = np.arange(len(pcd.points))
    remaining_mask = np.ones(len(pcd.points), dtype=bool)

    for i in range(max_planes):
        if len(remaining.points) < min_inliers:
            break

        plane_model, local_inliers = remaining.segment_plane(
            distance_threshold=distance_threshold,
            ransac_n=ransac_n,
            num_iterations=num_iterations,
        )

        if len(local_inliers) < min_inliers:
            logger.debug("Plane %d: only %d inliers — stopping", i, len(local_inliers))
            break

        # Map local inlier indices back to global indices
        global_inlier_idx = all_indices[remaining_mask][local_inliers]
        planes.append((np.array(plane_model), global_inlier_idx))
        logger.info(
            "Plane %d detected: [%.3f, %.3f, %.3f, %.3f] — %d inliers",
            i, *plane_model, len(local_inliers),
        )

        # Remove inliers and continue with the rest
        remaining_mask[global_inlier_idx] = False
        remaining_pts = np.asarray(pcd.points)[remaining_mask]
        remaining = o3d.geometry.PointCloud()
        remaining.points = o3d.utility.Vector3dVector(remaining_pts)
        if pcd.has_colors():
            remaining.colors = o3d.utility.Vector3dVector(
                np.asarray(pcd.colors)[remaining_mask]
            )

    logger.info("Total planes detected: %d", len(planes))
    return planes


# ─────────────────────────────────────────────────────────────────────────────
# Point snapping
# ─────────────────────────────────────────────────────────────────────────────

def _signed_distance_to_plane(points: np.ndarray, plane: np.ndarray) -> np.ndarray:
    """
    Signed distance from each point to the plane ax+by+cz+d=0.
    plane = [a, b, c, d].
    """
    a, b, c, d = plane
    normal = np.array([a, b, c])
    norm = np.linalg.norm(normal)
    return (points @ normal + d) / norm


def _project_onto_plane(points: np.ndarray, plane: np.ndarray) -> np.ndarray:
    """Project points onto the plane (snap them to it)."""
    a, b, c, d = plane
    normal = np.array([a, b, c])
    norm_sq = np.dot(normal, normal)
    distances = (points @ normal + d) / norm_sq
    return points - np.outer(distances, normal)


def snap_points_to_planes(
    pcd: "o3d.geometry.PointCloud",
    planes: List[Tuple[np.ndarray, np.ndarray]],
    snap_threshold: float = config.SNAP_DEVIATION_THRESHOLD,
) -> "o3d.geometry.PointCloud":
    """
    For each detected plane, snap inlier points that deviate by less than
    snap_threshold metres onto the ideal plane.

    Returns a new corrected PointCloud.
    """
    _require_open3d()
    pts = np.asarray(pcd.points).copy()
    snapped_count = 0

    for plane_model, inlier_idx in planes:
        inlier_pts = pts[inlier_idx]
        dists = np.abs(_signed_distance_to_plane(inlier_pts, plane_model))
        snap_mask = dists < snap_threshold
        snap_idx = inlier_idx[snap_mask]

        if snap_idx.size == 0:
            continue

        pts[snap_idx] = _project_onto_plane(pts[snap_idx], plane_model)
        snapped_count += snap_idx.size
        logger.debug("Snapped %d / %d inliers for plane", snap_idx.size, len(inlier_idx))

    logger.info("Total points snapped: %d", snapped_count)

    corrected = o3d.geometry.PointCloud()
    corrected.points = o3d.utility.Vector3dVector(pts)
    if pcd.has_colors():
        corrected.colors = o3d.utility.Vector3dVector(np.asarray(pcd.colors).copy())
    if pcd.has_normals():
        corrected.normals = o3d.utility.Vector3dVector(np.asarray(pcd.normals).copy())

    return corrected


# ─────────────────────────────────────────────────────────────────────────────
# Poisson re-meshing
# ─────────────────────────────────────────────────────────────────────────────

def remesh_poisson(
    pcd: "o3d.geometry.PointCloud",
    depth: int = config.POISSON_DEPTH,
    min_density_quantile: float = config.POISSON_MIN_DENSITY_QUANTILE,
) -> "o3d.geometry.TriangleMesh":
    """
    Estimate normals (if missing) and run Poisson surface reconstruction.
    Removes low-density vertices to clean up fringe artefacts.
    """
    _require_open3d()

    if not pcd.has_normals():
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
        )
        pcd.orient_normals_consistent_tangent_plane(100)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=depth
    )

    # Remove low-density vertices (fringe artefacts)
    densities_np = np.asarray(densities)
    threshold = np.quantile(densities_np, min_density_quantile)
    keep = densities_np >= threshold
    mesh.remove_vertices_by_mask(~keep)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()

    logger.info(
        "Poisson mesh: %d vertices, %d triangles",
        len(mesh.vertices), len(mesh.triangles),
    )
    return mesh


def save_mesh(mesh: "o3d.geometry.TriangleMesh", path: str | Path) -> None:
    _require_open3d()
    o3d.io.write_triangle_mesh(str(path), mesh)
    logger.info("Saved corrected mesh → %s", path)


# ─────────────────────────────────────────────────────────────────────────────
# High-level entry point
# ─────────────────────────────────────────────────────────────────────────────

def correct_pointcloud(
    input_path: str | Path,
    output_pc_path: str | Path,
    output_mesh_path: str | Path | None = None,
    plane_distance_threshold: float = config.PLANE_DISTANCE_THRESHOLD,
    snap_threshold: float = config.SNAP_DEVIATION_THRESHOLD,
    min_inliers: int = config.PLANE_MIN_INLIERS,
) -> dict:
    """
    Full pipeline: load → detect planes → snap → save corrected cloud + mesh.

    Returns a statistics dict.
    """
    pcd = load_pointcloud(input_path)
    original_count = len(pcd.points)

    planes = detect_planes(
        pcd,
        distance_threshold=plane_distance_threshold,
        min_inliers=min_inliers,
    )

    corrected = snap_points_to_planes(pcd, planes, snap_threshold=snap_threshold)
    save_pointcloud(corrected, output_pc_path)

    mesh_vertices = 0
    mesh_triangles = 0
    if output_mesh_path:
        mesh = remesh_poisson(corrected)
        save_mesh(mesh, output_mesh_path)
        mesh_vertices = len(mesh.vertices)
        mesh_triangles = len(mesh.triangles)

    return {
        "original_points": original_count,
        "planes_detected": len(planes),
        "corrected_point_cloud": str(output_pc_path),
        "corrected_mesh": str(output_mesh_path) if output_mesh_path else None,
        "mesh_vertices": mesh_vertices,
        "mesh_triangles": mesh_triangles,
    }
