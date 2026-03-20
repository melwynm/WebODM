"""
geometry_correction/algorithms/orthophoto.py

Orthomosaic geometric correction using Hough-line detection.

Pipeline:
  1. Load GeoTIFF orthomosaic with rasterio (preserves CRS + geotransform)
  2. Convert first 3 bands to grayscale for edge detection
  3. Detect line segments with probabilistic Hough transform
  4. Find lines that should be axis-aligned (within LINE_ANGLE_TOLERANCE)
  5. Compute a global rotation correction angle
  6. Apply affine correction, re-export GeoTIFF with original metadata intact
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.enums import Resampling
    from rasterio import warp
except ImportError:
    rasterio = None

from .. import config

logger = logging.getLogger(__name__)


def _require_cv2():
    if cv2 is None:
        raise ImportError("opencv-python is required: pip install opencv-python")


def _require_rasterio():
    if rasterio is None:
        raise ImportError("rasterio is required: pip install rasterio")


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_uint8_gray(arr: np.ndarray) -> np.ndarray:
    """
    Convert an ndarray (bands, H, W) or (H, W) to a uint8 grayscale image.
    """
    if arr.ndim == 3:
        # Use first 3 bands or fewer
        n = min(3, arr.shape[0])
        rgb = arr[:n].astype(np.float32)
        rgb = (rgb - rgb.min()) / (rgb.ptp() + 1e-9) * 255
        gray = np.mean(rgb, axis=0)
    else:
        gray = arr.astype(np.float32)
        gray = (gray - gray.min()) / (gray.ptp() + 1e-9) * 255

    return gray.astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# Line detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_hough_lines(
    gray: np.ndarray,
    canny_low: int = config.CANNY_LOW,
    canny_high: int = config.CANNY_HIGH,
    rho: float = config.HOUGH_RHO,
    theta_deg: float = config.HOUGH_THETA_DEGREES,
    threshold: int = config.HOUGH_THRESHOLD,
    min_length: int = config.HOUGH_MIN_LINE_LENGTH,
    max_gap: int = config.HOUGH_MAX_LINE_GAP,
) -> np.ndarray | None:
    """
    Run Canny + probabilistic Hough on a uint8 grayscale image.
    Returns array of shape (N, 1, 4) with [x1,y1,x2,y2] or None.
    """
    _require_cv2()
    edges = cv2.Canny(gray, canny_low, canny_high)
    lines = cv2.HoughLinesP(
        edges,
        rho=rho,
        theta=np.deg2rad(theta_deg),
        threshold=threshold,
        minLineLength=min_length,
        maxLineGap=max_gap,
    )
    return lines


def _line_angle_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    """Return angle of a line in degrees [0, 180)."""
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return angle % 180


def extract_axis_aligned_lines(
    lines: np.ndarray,
    tolerance: float = config.LINE_ANGLE_TOLERANCE,
) -> Tuple[List[float], List[float]]:
    """
    Split detected lines into near-horizontal and near-vertical groups.

    Returns (horizontal_angles, vertical_angles) as lists of raw angle values.
    """
    h_angles, v_angles = [], []
    if lines is None:
        return h_angles, v_angles

    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = _line_angle_deg(x1, y1, x2, y2)

        # Near horizontal: 0° ± tol  or  180° ± tol
        if angle <= tolerance or angle >= (180 - tolerance):
            h_angles.append(angle)
        # Near vertical: 90° ± tol
        elif abs(angle - 90) <= tolerance:
            v_angles.append(angle)

    logger.debug("Axis-aligned lines — H: %d  V: %d", len(h_angles), len(v_angles))
    return h_angles, v_angles


def compute_correction_angle(
    h_angles: List[float],
    v_angles: List[float],
) -> float:
    """
    Compute the median rotation correction angle (degrees) needed to make
    detected lines perfectly horizontal/vertical.
    """
    corrections = []

    # Horizontal lines: ideal is 0°; deviation is the angle itself
    for a in h_angles:
        if a > 90:
            corrections.append(180 - a)   # lines near 180° → correct by (180-a)
        else:
            corrections.append(-a)        # lines near 0° → correct by -a

    # Vertical lines: ideal is 90°; deviation is (a - 90)
    for a in v_angles:
        corrections.append(-(a - 90))

    if not corrections:
        logger.info("No axis-aligned lines found — no rotation needed")
        return 0.0

    angle = float(np.median(corrections))
    logger.info("Computed correction angle: %.3f°", angle)
    return angle


# ─────────────────────────────────────────────────────────────────────────────
# Image rotation (preserving GeoTIFF metadata)
# ─────────────────────────────────────────────────────────────────────────────

def rotate_image_array(arr: np.ndarray, angle_deg: float) -> np.ndarray:
    """
    Rotate a (bands, H, W) or (H, W) array by angle_deg.
    Uses OpenCV for sub-pixel accuracy.  Fills with 0 (nodata).
    """
    _require_cv2()
    if arr.ndim == 2:
        arr = arr[np.newaxis]

    bands, h, w = arr.shape
    cx, cy = w / 2.0, h / 2.0
    M = cv2.getRotationMatrix2D((cx, cy), angle_deg, scale=1.0)
    rotated = np.zeros_like(arr)

    for b in range(bands):
        rotated[b] = cv2.warpAffine(
            arr[b].astype(np.float32),
            M,
            (w, h),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        ).astype(arr.dtype)

    return rotated


# ─────────────────────────────────────────────────────────────────────────────
# High-level entry point
# ─────────────────────────────────────────────────────────────────────────────

def correct_orthophoto(
    input_path: str | Path,
    output_path: str | Path,
    angle_tolerance: float = config.LINE_ANGLE_TOLERANCE,
) -> dict:
    """
    Full pipeline: load GeoTIFF → detect lines → compute rotation →
    apply rotation → save corrected GeoTIFF.

    Returns a statistics dict.
    """
    _require_cv2()
    _require_rasterio()

    input_path = Path(input_path)
    output_path = Path(output_path)

    with rasterio.open(input_path) as src:
        data = src.read()
        meta = src.meta.copy()
        crs = src.crs
        transform = src.transform

    logger.info(
        "Loaded orthomosaic: %d bands, %d×%d px, CRS=%s",
        data.shape[0], data.shape[2], data.shape[1], crs,
    )

    gray = _to_uint8_gray(data)
    lines = detect_hough_lines(gray, canny_low=config.CANNY_LOW, canny_high=config.CANNY_HIGH)
    total_lines = len(lines) if lines is not None else 0

    h_angles, v_angles = extract_axis_aligned_lines(lines, tolerance=angle_tolerance)
    correction_angle = compute_correction_angle(h_angles, v_angles)

    if abs(correction_angle) < 0.01:
        logger.info("Correction angle negligible — copying input to output")
        import shutil
        shutil.copy2(input_path, output_path)
        return {
            "total_lines_detected": total_lines,
            "axis_aligned_lines": len(h_angles) + len(v_angles),
            "correction_angle_deg": 0.0,
            "corrected_orthophoto": str(output_path),
            "correction_applied": False,
        }

    corrected_data = rotate_image_array(data, correction_angle)

    # Update metadata
    meta.update(dtype=corrected_data.dtype, compress="lzw")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(corrected_data)

    logger.info("Saved corrected orthomosaic → %s", output_path)

    return {
        "total_lines_detected": total_lines,
        "axis_aligned_lines": len(h_angles) + len(v_angles),
        "correction_angle_deg": correction_angle,
        "corrected_orthophoto": str(output_path),
        "correction_applied": True,
    }
