"""
Point-cloud correction utilities for geometry_correction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None  # handled at runtime

try:
    import laspy
except ImportError:
    laspy = None

try:
    from scipy.spatial import cKDTree
except ImportError:
    cKDTree = None

from .. import config

logger = logging.getLogger(__name__)


@dataclass
class PlaneResult:
    """
    Plane-detection result with tuple-style compatibility.
    """

    model: np.ndarray
    inlier_indices: np.ndarray
    centroid: np.ndarray
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    inlier_count: int
    errors: List[str] = field(default_factory=list)

    @property
    def normal(self) -> np.ndarray:
        normal = np.asarray(self.model[:3], dtype=np.float64)
        norm = float(np.linalg.norm(normal))
        if norm <= 0.0:
            return np.array([0.0, 0.0, 0.0], dtype=np.float64)
        return normal / norm

    def __iter__(self):
        yield self.model
        yield self.inlier_indices

    def __getitem__(self, index: int):
        if index == 0:
            return self.model
        if index == 1:
            return self.inlier_indices
        raise IndexError(index)

    def to_dict(self) -> dict:
        return {
            "model": np.asarray(self.model, dtype=np.float64).round(6).tolist(),
            "centroid": np.asarray(self.centroid, dtype=np.float64).round(6).tolist(),
            "bbox_min": np.asarray(self.bbox_min, dtype=np.float64).round(6).tolist(),
            "bbox_max": np.asarray(self.bbox_max, dtype=np.float64).round(6).tolist(),
            "inlier_count": int(self.inlier_count),
            "errors": list(self.errors),
        }


@dataclass
class ResolvedPlaneProfile:
    classified_plane: object
    profile: object

    @property
    def plane(self) -> PlaneResult:
        return self.classified_plane.plane

    def to_dict(self) -> dict:
        return {
            "label": getattr(self.classified_plane.label, "value", str(self.classified_plane.label)),
            "confidence": float(getattr(self.classified_plane, "confidence", 0.0)),
            "profile": {
                "snap_threshold_m": float(self.profile.snap_threshold_m),
                "ransac_distance_m": float(self.profile.ransac_distance_m),
                "smoothing_iterations": int(self.profile.smoothing_iterations),
                "enabled": bool(self.profile.enabled),
            },
            "plane": self.plane.to_dict(),
        }


@dataclass
class PointCloudCorrectionStats:
    original_points: int
    planes_detected: int
    corrected_point_cloud: str
    corrected_mesh: Optional[str] = None
    mesh_vertices: int = 0
    mesh_triangles: int = 0
    plane_profiles: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "original_points": int(self.original_points),
            "planes_detected": int(self.planes_detected),
            "corrected_point_cloud": self.corrected_point_cloud,
            "corrected_mesh": self.corrected_mesh,
            "mesh_vertices": int(self.mesh_vertices),
            "mesh_triangles": int(self.mesh_triangles),
            "plane_profiles": list(self.plane_profiles),
            "errors": list(self.errors),
        }


def _require_open3d() -> None:
    if o3d is None:
        raise ImportError(
            "open3d is required for point-cloud correction. "
            "Install it with: pip install open3d"
        )


def load_pointcloud(path: str | Path) -> "o3d.geometry.PointCloud":
    """
    Load a .ply, .laz, or .las file into an Open3D point cloud.
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

    raise ValueError("Unsupported point cloud format: {}".format(path.suffix))


def save_pointcloud(pcd: "o3d.geometry.PointCloud", path: str | Path) -> None:
    _require_open3d()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_point_cloud(str(destination), pcd)
    logger.info("Saved corrected point cloud to %s", destination)


def _build_plane_result(points: np.ndarray, plane_model: Sequence[float], inlier_indices: Sequence[int]) -> PlaneResult:
    indices = np.asarray(inlier_indices, dtype=np.int64)
    inlier_points = np.asarray(points[indices], dtype=np.float64)
    if inlier_points.size == 0:
        centroid = np.zeros(3, dtype=np.float64)
        bbox_min = np.zeros(3, dtype=np.float64)
        bbox_max = np.zeros(3, dtype=np.float64)
    else:
        centroid = inlier_points.mean(axis=0)
        bbox_min = inlier_points.min(axis=0)
        bbox_max = inlier_points.max(axis=0)

    return PlaneResult(
        model=np.asarray(plane_model, dtype=np.float64),
        inlier_indices=indices,
        centroid=centroid,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        inlier_count=int(indices.size),
    )


def _coerce_plane_result(plane: PlaneResult | Sequence[object], points: Optional[np.ndarray] = None) -> PlaneResult:
    if isinstance(plane, PlaneResult):
        return plane

    model = np.asarray(plane[0], dtype=np.float64)
    inlier_indices = np.asarray(plane[1], dtype=np.int64)
    if points is None:
        zeros = np.zeros(3, dtype=np.float64)
        return PlaneResult(
            model=model,
            inlier_indices=inlier_indices,
            centroid=zeros,
            bbox_min=zeros,
            bbox_max=zeros,
            inlier_count=int(inlier_indices.size),
            errors=["Plane metadata unavailable when coercing tuple result."],
        )
    return _build_plane_result(points, model, inlier_indices)


def detect_planes(
    pcd: "o3d.geometry.PointCloud",
    distance_threshold: float = config.PLANE_DISTANCE_THRESHOLD,
    ransac_n: int = config.PLANE_RANSAC_N,
    num_iterations: int = config.PLANE_NUM_ITERATIONS,
    min_inliers: int = config.PLANE_MIN_INLIERS,
    max_planes: int = config.MAX_PLANES,
) -> List[PlaneResult]:
    """
    Iteratively detect dominant planes using RANSAC.
    """
    _require_open3d()

    points = np.asarray(pcd.points)
    if points.size == 0:
        return []

    remaining = pcd
    planes: List[PlaneResult] = []
    all_indices = np.arange(len(points))
    remaining_mask = np.ones(len(points), dtype=bool)

    for plane_index in range(max_planes):
        if len(remaining.points) < min_inliers:
            break

        plane_model, local_inliers = remaining.segment_plane(
            distance_threshold=distance_threshold,
            ransac_n=ransac_n,
            num_iterations=num_iterations,
        )

        local_inliers = np.asarray(local_inliers, dtype=np.int64)
        if local_inliers.size < min_inliers:
            logger.debug("Plane %d below inlier threshold (%d)", plane_index, local_inliers.size)
            break

        global_inlier_idx = all_indices[remaining_mask][local_inliers]
        plane = _build_plane_result(points, plane_model, global_inlier_idx)
        planes.append(plane)

        logger.info(
            "Plane %d detected: [%.3f, %.3f, %.3f, %.3f] with %d inliers",
            plane_index,
            plane.model[0],
            plane.model[1],
            plane.model[2],
            plane.model[3],
            plane.inlier_count,
        )

        remaining_mask[global_inlier_idx] = False
        remaining_pts = points[remaining_mask]
        remaining = o3d.geometry.PointCloud()
        remaining.points = o3d.utility.Vector3dVector(remaining_pts)

        if pcd.has_colors():
            remaining.colors = o3d.utility.Vector3dVector(np.asarray(pcd.colors)[remaining_mask])
        if pcd.has_normals():
            remaining.normals = o3d.utility.Vector3dVector(np.asarray(pcd.normals)[remaining_mask])

    logger.info("Total planes detected: %d", len(planes))
    return planes


def _signed_distance_to_plane(points: np.ndarray, plane: Sequence[float]) -> np.ndarray:
    a, b, c, d = plane
    normal = np.asarray([a, b, c], dtype=np.float64)
    norm = float(np.linalg.norm(normal))
    if norm <= 0.0:
        return np.zeros(len(points), dtype=np.float64)
    return (np.asarray(points, dtype=np.float64) @ normal + float(d)) / norm


def _project_onto_plane(points: np.ndarray, plane: Sequence[float]) -> np.ndarray:
    normal = np.asarray(plane[:3], dtype=np.float64)
    norm_sq = float(np.dot(normal, normal))
    if norm_sq <= 0.0:
        return np.asarray(points, dtype=np.float64)
    distances = (np.asarray(points, dtype=np.float64) @ normal + float(plane[3])) / norm_sq
    return np.asarray(points, dtype=np.float64) - np.outer(distances, normal)


def smooth_points_on_plane(
    points: np.ndarray,
    neighbors: int = config.PLANE_SMOOTHING_NEIGHBORS,
    iterations: int = 1,
) -> np.ndarray:
    """
    Apply light neighborhood smoothing after snapping.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.size == 0 or iterations <= 0 or neighbors <= 1 or cKDTree is None:
        return pts

    smoothed = pts.copy()
    k = min(int(neighbors), len(smoothed))
    if k <= 1:
        return smoothed

    for _ in range(int(iterations)):
        tree = cKDTree(smoothed)
        _, neighbor_idx = tree.query(smoothed, k=k)
        if k == 1:
            neighbor_idx = neighbor_idx[:, np.newaxis]
        smoothed = np.mean(smoothed[neighbor_idx], axis=1)

    return smoothed


def resolve_plane_profiles(
    planes: Iterable[PlaneResult | Sequence[object]],
    point_cloud_centroid: np.ndarray,
    overrides: Optional[dict] = None,
) -> List[ResolvedPlaneProfile]:
    """
    Classify planes and resolve their correction profiles.
    """
    from .correction_profiles import get_profile
    from .semantic import classify_planes

    normalized_planes = [plane if isinstance(plane, PlaneResult) else _coerce_plane_result(plane) for plane in planes]
    classified = classify_planes(normalized_planes, point_cloud_centroid=np.asarray(point_cloud_centroid, dtype=np.float64))

    resolved: List[ResolvedPlaneProfile] = []
    for classified_plane in classified:
        profile = get_profile(classified_plane.label, overrides=overrides)
        resolved.append(ResolvedPlaneProfile(classified_plane=classified_plane, profile=profile))

    return resolved


def snap_points_to_planes(
    pcd: "o3d.geometry.PointCloud",
    planes: Iterable[PlaneResult | Sequence[object]],
    snap_threshold: float = config.SNAP_DEVIATION_THRESHOLD,
    resolved_profiles: Optional[Iterable[ResolvedPlaneProfile]] = None,
) -> "o3d.geometry.PointCloud":
    """
    Snap nearby plane inliers to their best-fit plane.
    """
    _require_open3d()

    pts = np.asarray(pcd.points).copy()
    profile_by_key = {}
    if resolved_profiles is not None:
        for resolved in resolved_profiles:
            key = tuple(int(v) for v in np.asarray(resolved.plane.inlier_indices, dtype=np.int64).tolist())
            profile_by_key[key] = resolved

    snapped_count = 0
    for plane_like in planes:
        plane = _coerce_plane_result(plane_like, pts)
        key = tuple(int(v) for v in plane.inlier_indices.tolist())
        resolved = profile_by_key.get(key)
        threshold = float(snap_threshold)
        smoothing_iterations = 0

        if resolved is not None:
            if not bool(resolved.profile.enabled):
                logger.debug("Skipping disabled semantic class %s", resolved.classified_plane.label.value)
                continue
            threshold = float(resolved.profile.snap_threshold_m)
            smoothing_iterations = int(resolved.profile.smoothing_iterations)

        inlier_pts = pts[plane.inlier_indices]
        dists = np.abs(_signed_distance_to_plane(inlier_pts, plane.model))
        snap_mask = dists < threshold
        snap_indices = plane.inlier_indices[snap_mask]

        if snap_indices.size == 0:
            continue

        snapped = _project_onto_plane(pts[snap_indices], plane.model)
        if smoothing_iterations > 0:
            snapped = smooth_points_on_plane(snapped, iterations=smoothing_iterations)
        pts[snap_indices] = snapped
        snapped_count += int(snap_indices.size)

    logger.info("Total points snapped: %d", snapped_count)

    corrected = o3d.geometry.PointCloud()
    corrected.points = o3d.utility.Vector3dVector(pts)
    if pcd.has_colors():
        corrected.colors = o3d.utility.Vector3dVector(np.asarray(pcd.colors).copy())
    if pcd.has_normals():
        corrected.normals = o3d.utility.Vector3dVector(np.asarray(pcd.normals).copy())

    return corrected


def remesh_poisson(
    pcd: "o3d.geometry.PointCloud",
    depth: int = config.POISSON_DEPTH,
    min_density_quantile: float = config.POISSON_MIN_DENSITY_QUANTILE,
) -> "o3d.geometry.TriangleMesh":
    """
    Generate a Poisson mesh from the corrected point cloud.
    """
    _require_open3d()

    if not pcd.has_normals():
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
        )
        pcd.orient_normals_consistent_tangent_plane(100)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)
    densities_np = np.asarray(densities)
    if densities_np.size > 0:
        threshold = np.quantile(densities_np, min_density_quantile)
        keep = densities_np >= threshold
        mesh.remove_vertices_by_mask(~keep)

    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()

    logger.info("Poisson mesh: %d vertices, %d triangles", len(mesh.vertices), len(mesh.triangles))
    return mesh


def save_mesh(mesh: "o3d.geometry.TriangleMesh", path: str | Path) -> None:
    _require_open3d()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_triangle_mesh(str(destination), mesh)
    logger.info("Saved corrected mesh to %s", destination)


def run_pointcloud_correction(
    input_path: str | Path,
    output_pc_path: str | Path,
    output_mesh_path: str | Path | None = None,
    plane_distance_threshold: float = config.PLANE_DISTANCE_THRESHOLD,
    snap_threshold: float = config.SNAP_DEVIATION_THRESHOLD,
    min_inliers: int = config.PLANE_MIN_INLIERS,
    use_semantic_profiles: bool = config.USE_SEMANTIC_PROFILES,
    profile_overrides: Optional[dict] = None,
) -> PointCloudCorrectionStats:
    """
    Load, detect planes, snap, and optionally remesh a point cloud.
    """
    pcd = load_pointcloud(input_path)
    points = np.asarray(pcd.points)
    original_count = len(points)

    planes = detect_planes(
        pcd,
        distance_threshold=plane_distance_threshold,
        min_inliers=min_inliers,
    )

    resolved_profiles: List[ResolvedPlaneProfile] = []
    if use_semantic_profiles and len(planes) > 0:
        resolved_profiles = resolve_plane_profiles(
            planes,
            point_cloud_centroid=points.mean(axis=0),
            overrides=profile_overrides,
        )

    corrected = snap_points_to_planes(
        pcd,
        planes,
        snap_threshold=snap_threshold,
        resolved_profiles=resolved_profiles or None,
    )
    save_pointcloud(corrected, output_pc_path)

    stats = PointCloudCorrectionStats(
        original_points=original_count,
        planes_detected=len(planes),
        corrected_point_cloud=str(output_pc_path),
        plane_profiles=[resolved.to_dict() for resolved in resolved_profiles],
    )

    if output_mesh_path:
        mesh = remesh_poisson(corrected)
        save_mesh(mesh, output_mesh_path)
        stats.corrected_mesh = str(output_mesh_path)
        stats.mesh_vertices = len(mesh.vertices)
        stats.mesh_triangles = len(mesh.triangles)

    return stats


def correct_pointcloud(
    input_path: str | Path,
    output_pc_path: str | Path,
    output_mesh_path: str | Path | None = None,
    plane_distance_threshold: float = config.PLANE_DISTANCE_THRESHOLD,
    snap_threshold: float = config.SNAP_DEVIATION_THRESHOLD,
    min_inliers: int = config.PLANE_MIN_INLIERS,
    use_semantic_profiles: bool = config.USE_SEMANTIC_PROFILES,
    profile_overrides: Optional[dict] = None,
) -> dict:
    """
    Backwards-compatible dict wrapper around ``run_pointcloud_correction``.
    """
    return run_pointcloud_correction(
        input_path=input_path,
        output_pc_path=output_pc_path,
        output_mesh_path=output_mesh_path,
        plane_distance_threshold=plane_distance_threshold,
        snap_threshold=snap_threshold,
        min_inliers=min_inliers,
        use_semantic_profiles=use_semantic_profiles,
        profile_overrides=profile_overrides,
    ).to_dict()
