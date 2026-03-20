"""
Confidence-map generation for orthophoto corrections.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

try:
    import rasterio
except ImportError:
    rasterio = None


logger = logging.getLogger(__name__)


def _require_rasterio() -> None:
    if rasterio is None:
        raise ImportError("rasterio is required: pip install rasterio")


def _to_hwc(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image[:, :, np.newaxis]
    if image.ndim == 3 and image.shape[0] <= 4:
        return np.moveaxis(image, 0, -1)
    return image


def generate_confidence_map(
    original_bgr: np.ndarray,
    corrected_bgr: np.ndarray,
    profile: dict,
    output_path: str,
) -> str:
    """
    Save a single-band GeoTIFF showing normalized per-pixel change magnitude.
    """
    _require_rasterio()

    original = _to_hwc(np.asarray(original_bgr, dtype=np.float32))
    corrected = _to_hwc(np.asarray(corrected_bgr, dtype=np.float32))
    if original.shape != corrected.shape:
        raise ValueError("original_bgr and corrected_bgr must have identical shapes")

    diff = np.linalg.norm(corrected - original, axis=2)
    max_diff = float(diff.max()) if diff.size else 0.0
    if max_diff <= 0.0:
        confidence_map = np.zeros(diff.shape, dtype=np.uint8)
    else:
        confidence_map = np.clip((diff / max_diff) * 255.0, 0, 255).astype(np.uint8)

    raster_profile = dict(profile)
    raster_profile.update(count=1, dtype="uint8")
    raster_profile.pop("photometric", None)
    raster_profile.pop("compress", None)
    raster_profile["compress"] = "lzw"

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(destination, "w", **raster_profile) as dst:
        dst.write(confidence_map, 1)

    logger.info("Saved confidence map to %s", destination)
    return str(destination)


def compute_correction_coverage_pct(confidence_map: np.ndarray, threshold: int = 5) -> float:
    """
    Return the percentage of pixels whose confidence exceeds ``threshold``.
    """
    arr = np.asarray(confidence_map)
    if arr.size == 0:
        return 0.0

    if arr.ndim == 3:
        arr = arr[:, :, 0] if arr.shape[-1] == 1 else arr[0]

    changed = np.count_nonzero(arr > threshold)
    return round((float(changed) / float(arr.size)) * 100.0, 6)
