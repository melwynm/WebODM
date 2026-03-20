"""
geometry_correction/algorithms/mesh.py

OBJ mesh loading/saving helpers and mesh-level correction utilities.
The primary correction is done at point-cloud level (pointcloud.py);
this module handles:
  - Loading an existing ODM .obj mesh as Open3D TriangleMesh
  - Applying RANSAC-based vertex snapping directly on a mesh
  - Exporting corrected .obj files
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None

from .. import config
from .pointcloud import (
    _require_open3d,
    detect_planes,
    snap_points_to_planes,
)

logger = logging.getLogger(__name__)


def load_mesh(path: str | Path) -> "o3d.geometry.TriangleMesh":
    _require_open3d()
    mesh = o3d.io.read_triangle_mesh(str(path))
    if not mesh.has_vertices():
        raise ValueError(f"No vertices loaded from {path}")
    logger.info(
        "Loaded mesh: %d vertices, %d triangles — %s",
        len(mesh.vertices), len(mesh.triangles), path,
    )
    return mesh


def save_mesh(mesh: "o3d.geometry.TriangleMesh", path: str | Path) -> None:
    _require_open3d()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_triangle_mesh(str(path), mesh)
    logger.info("Saved mesh → %s", path)


def mesh_to_pcd(mesh: "o3d.geometry.TriangleMesh") -> "o3d.geometry.PointCloud":
    """Convert mesh vertices to a PointCloud for plane detection."""
    _require_open3d()
    pcd = o3d.geometry.PointCloud()
    pcd.points = mesh.vertices
    if mesh.has_vertex_colors():
        pcd.colors = mesh.vertex_colors
    if mesh.has_vertex_normals():
        pcd.normals = mesh.vertex_normals
    return pcd


def correct_mesh(
    input_path: str | Path,
    output_path: str | Path,
    plane_distance_threshold: float = config.PLANE_DISTANCE_THRESHOLD,
    snap_threshold: float = config.SNAP_DEVIATION_THRESHOLD,
    min_inliers: int = config.PLANE_MIN_INLIERS,
) -> dict:
    """
    Load mesh → detect planes on its vertices → snap deviating vertices →
    rewrite triangles with corrected vertices → save.

    Returns a statistics dict.
    """
    mesh = load_mesh(input_path)
    pcd = mesh_to_pcd(mesh)

    planes = detect_planes(
        pcd,
        distance_threshold=plane_distance_threshold,
        min_inliers=min_inliers,
    )
    corrected_pcd = snap_points_to_planes(pcd, planes, snap_threshold=snap_threshold)

    # Replace mesh vertices with corrected positions
    mesh.vertices = corrected_pcd.points
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()

    save_mesh(mesh, output_path)

    return {
        "input_mesh": str(input_path),
        "output_mesh": str(output_path),
        "planes_detected": len(planes),
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.triangles),
    }
