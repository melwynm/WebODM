"""
Per-class correction profile definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from typing import Any, Dict, Optional

from .semantic import PlaneClass


logger = logging.getLogger(__name__)


@dataclass
class CorrectionProfile:
    snap_threshold_m: float
    ransac_distance_m: float
    smoothing_iterations: int
    enabled: bool


DEFAULT_PROFILES = {
    PlaneClass.WALL: CorrectionProfile(0.04, 0.03, 2, True),
    PlaneClass.FLOOR: CorrectionProfile(0.06, 0.05, 1, True),
    PlaneClass.ROOF: CorrectionProfile(0.05, 0.04, 2, True),
    PlaneClass.RAMP: CorrectionProfile(0.08, 0.06, 3, True),
    PlaneClass.UNKNOWN: CorrectionProfile(0.05, 0.05, 1, False),
}


def _match_override(label: PlaneClass, overrides: Optional[dict]) -> Dict[str, Any]:
    if not overrides:
        return {}

    if any(key in overrides for key in ("snap_threshold_m", "ransac_distance_m", "smoothing_iterations", "enabled")):
        return dict(overrides)

    candidates = [label, label.value, label.name, label.name.lower()]
    for key in candidates:
        if key in overrides and isinstance(overrides[key], dict):
            return dict(overrides[key])
    return {}


def get_profile(label: PlaneClass, overrides: Optional[dict] = None) -> CorrectionProfile:
    """
    Return a copy of the default profile for ``label`` with optional overrides.
    """
    base = DEFAULT_PROFILES.get(label, DEFAULT_PROFILES[PlaneClass.UNKNOWN])
    merged = replace(base)

    for field_name, value in _match_override(label, overrides).items():
        if hasattr(merged, field_name):
            setattr(merged, field_name, value)

    logger.debug("Resolved correction profile for %s: %s", label.value, merged)
    return merged
