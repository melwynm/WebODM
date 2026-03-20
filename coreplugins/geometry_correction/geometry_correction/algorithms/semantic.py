"""
Semantic plane classification helpers for geometry correction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import TYPE_CHECKING, List

import numpy as np

if TYPE_CHECKING:
    from .pointcloud import PlaneResult


logger = logging.getLogger(__name__)


class PlaneClass(str, Enum):
    WALL = "wall"
    FLOOR = "floor"
    ROOF = "roof"
    RAMP = "ramp"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedPlane:
    plane: "PlaneResult"
    label: PlaneClass
    confidence: float
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label.value,
            "confidence": round(float(self.confidence), 6),
            "inlier_count": int(getattr(self.plane, "inlier_count", 0)),
        }


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _plane_extents(plane: "PlaneResult") -> np.ndarray:
    return np.maximum(np.asarray(plane.bbox_max) - np.asarray(plane.bbox_min), 1e-9)


def _wall_shape_score(plane: "PlaneResult") -> float:
    extents = _plane_extents(plane)
    horizontal_span = max(float(extents[0]), float(extents[1]), 1e-9)
    vertical_span = float(extents[2])
    return _bounded(vertical_span / max(horizontal_span * 2.0, 1e-9))


def _horizontal_shape_score(plane: "PlaneResult") -> float:
    extents = _plane_extents(plane)
    horizontal_span = max(float(extents[0]), float(extents[1]))
    vertical_span = max(float(extents[2]), 1e-9)
    return _bounded(horizontal_span / max(vertical_span * 2.0, 1e-9))


def classify_planes(
    planes: List["PlaneResult"],
    point_cloud_centroid: np.ndarray,
) -> List[ClassifiedPlane]:
    """
    Classify planes using normal orientation, height, and rough aspect cues.
    """
    centroid = np.asarray(point_cloud_centroid, dtype=np.float64)
    classified: List[ClassifiedPlane] = []

    for plane in planes:
        normal = np.asarray(plane.normal, dtype=np.float64)
        abs_normal_z = abs(float(normal[2]))
        height_delta = float(plane.centroid[2] - centroid[2])

        label = PlaneClass.UNKNOWN
        confidence = 0.0

        if abs_normal_z > 0.85:
            normal_score = _bounded((abs_normal_z - 0.85) / 0.15)
            shape_score = _horizontal_shape_score(plane)

            if height_delta < 0.3:
                label = PlaneClass.FLOOR
                height_score = _bounded((0.3 - height_delta) / 0.3)
                confidence = 0.7 * normal_score + 0.2 * height_score + 0.1 * shape_score
            elif height_delta > 1.5:
                label = PlaneClass.ROOF
                height_score = _bounded((height_delta - 1.5) / max(height_delta, 1.5))
                confidence = 0.7 * normal_score + 0.2 * height_score + 0.1 * shape_score
            else:
                confidence = 0.4 * normal_score + 0.6 * shape_score
        elif abs_normal_z < 0.3:
            label = PlaneClass.WALL
            normal_score = _bounded((0.3 - abs_normal_z) / 0.3)
            shape_score = _wall_shape_score(plane)
            confidence = 0.8 * normal_score + 0.2 * shape_score
        elif 0.3 <= abs_normal_z <= 0.85:
            label = PlaneClass.RAMP
            center = 0.575
            spread = 0.275
            normal_score = _bounded(1.0 - abs(abs_normal_z - center) / spread)
            confidence = 0.9 * normal_score + 0.1 * _horizontal_shape_score(plane)

        classified.append(
            ClassifiedPlane(
                plane=plane,
                label=label,
                confidence=round(_bounded(confidence), 6),
            )
        )

    logger.info("Classified %d planes", len(classified))
    return classified
