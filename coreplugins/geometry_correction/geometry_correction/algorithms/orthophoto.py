"""
Orthophoto correction utilities for geometry_correction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
from pathlib import Path
import shutil
from typing import List, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import rasterio
except ImportError:
    rasterio = None

from .. import config
from .confidence_map import compute_correction_coverage_pct, generate_confidence_map as write_confidence_map

logger = logging.getLogger(__name__)


@dataclass
class OrthoCorrectionStats:
    total_lines_detected: int
    axis_aligned_lines: int
    correction_angle_deg: float
    corrected_orthophoto: str
    correction_applied: bool
    confidence_map_path: str = ""
    coverage_pct: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_lines_detected": int(self.total_lines_detected),
            "axis_aligned_lines": int(self.axis_aligned_lines),
            "correction_angle_deg": float(self.correction_angle_deg),
            "corrected_orthophoto": self.corrected_orthophoto,
            "correction_applied": bool(self.correction_applied),
            "confidence_map_path": self.confidence_map_path,
            "coverage_pct": float(self.coverage_pct),
            "errors": list(self.errors),
        }


def _require_cv2() -> None:
    if cv2 is None:
        raise ImportError("OpenCV is required: pip install opencv-python-headless")


def _require_rasterio() -> None:
    if rasterio is None:
        raise ImportError("rasterio is required: pip install rasterio")


def _to_uint8_gray(arr: np.ndarray) -> np.ndarray:
    """
    Convert an ndarray in band-first or single-band format to uint8 grayscale.
    """
    image = np.asarray(arr)
    if image.ndim == 3:
        band_count = min(3, image.shape[0])
        rgb = image[:band_count].astype(np.float32)
        span = float(np.ptp(rgb))
        if span > 0.0:
            rgb = (rgb - float(rgb.min())) / span * 255.0
        gray = np.mean(rgb, axis=0)
    else:
        gray = image.astype(np.float32)
        span = float(np.ptp(gray))
        if span > 0.0:
            gray = (gray - float(gray.min())) / span * 255.0

    return np.clip(gray, 0, 255).astype(np.uint8)


def detect_hough_lines(
    gray: np.ndarray,
    canny_low: int = config.CANNY_LOW,
    canny_high: int = config.CANNY_HIGH,
    rho: float = config.HOUGH_RHO,
    theta_deg: float = config.HOUGH_THETA_DEGREES,
    threshold: int = config.HOUGH_THRESHOLD,
    min_length: int = config.HOUGH_MIN_LINE_LENGTH,
    max_gap: int = config.HOUGH_MAX_LINE_GAP,
) -> Optional[np.ndarray]:
    """
    Run Canny plus probabilistic Hough on a grayscale image.
    """
    _require_cv2()
    edges = cv2.Canny(gray, canny_low, canny_high)
    return cv2.HoughLinesP(
        edges,
        rho=rho,
        theta=np.deg2rad(theta_deg),
        threshold=threshold,
        minLineLength=min_length,
        maxLineGap=max_gap,
    )


def _line_angle_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return angle % 180


def extract_axis_aligned_lines(
    lines: Optional[np.ndarray],
    tolerance: float = config.LINE_ANGLE_TOLERANCE,
) -> Tuple[List[float], List[float]]:
    """
    Split lines into near-horizontal and near-vertical angle groups.
    """
    horizontal, vertical = [], []
    if lines is None:
        return horizontal, vertical

    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = _line_angle_deg(x1, y1, x2, y2)

        if angle <= tolerance or angle >= (180.0 - tolerance):
            horizontal.append(angle)
        elif abs(angle - 90.0) <= tolerance:
            vertical.append(angle)

    logger.debug("Axis-aligned line counts: H=%d V=%d", len(horizontal), len(vertical))
    return horizontal, vertical


def compute_correction_angle(h_angles: List[float], v_angles: List[float]) -> float:
    """
    Compute the median angle correction needed to axis-align candidate lines.
    """
    corrections = []

    for angle in h_angles:
        corrections.append(180.0 - angle if angle > 90.0 else -angle)

    for angle in v_angles:
        corrections.append(-(angle - 90.0))

    if not corrections:
        logger.info("No axis-aligned lines found; no rotation needed")
        return 0.0

    result = float(np.median(corrections))
    logger.info("Computed orthophoto correction angle %.3f degrees", result)
    return result


def rotate_image_array(arr: np.ndarray, angle_deg: float) -> np.ndarray:
    """
    Rotate a band-first or single-band array with OpenCV.
    """
    _require_cv2()

    image = np.asarray(arr)
    if image.ndim == 2:
        image = image[np.newaxis, ...]

    bands, height, width = image.shape
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, scale=1.0)
    rotated = np.zeros_like(image)

    for band_index in range(bands):
        rotated[band_index] = cv2.warpAffine(
            image[band_index].astype(np.float32),
            matrix,
            (width, height),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        ).astype(image.dtype)

    return rotated


def _build_confidence_map_path(output_path: Path) -> Path:
    return output_path.with_name(output_path.stem + "_confidence.tif")


def _load_confidence_map(path: Path) -> np.ndarray:
    _require_rasterio()
    with rasterio.open(path) as src:
        return src.read(1)


def run_orthophoto_correction(
    input_path: str | Path,
    output_path: str | Path,
    angle_tolerance: float = config.LINE_ANGLE_TOLERANCE,
    generate_confidence_map: bool = config.GENERATE_CONFIDENCE_MAP,
) -> OrthoCorrectionStats:
    """
    Load a GeoTIFF, estimate a rotation correction, and write a corrected output.
    """
    _require_cv2()
    _require_rasterio()

    input_path = Path(input_path)
    output_path = Path(output_path)

    with rasterio.open(input_path) as src:
        data = src.read()
        profile = src.profile.copy()

    gray = _to_uint8_gray(data)
    lines = detect_hough_lines(gray, canny_low=config.CANNY_LOW, canny_high=config.CANNY_HIGH)
    total_lines = len(lines) if lines is not None else 0

    horizontal, vertical = extract_axis_aligned_lines(lines, tolerance=angle_tolerance)
    correction_angle = compute_correction_angle(horizontal, vertical)

    correction_applied = abs(correction_angle) >= 0.01
    if correction_applied:
        corrected_data = rotate_image_array(data, correction_angle)
    else:
        corrected_data = np.asarray(data).copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile.update(dtype=str(corrected_data.dtype), compress="lzw")
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(corrected_data)

    if not correction_applied and input_path != output_path:
        try:
            shutil.copystat(input_path, output_path)
        except OSError:
            pass

    stats = OrthoCorrectionStats(
        total_lines_detected=total_lines,
        axis_aligned_lines=len(horizontal) + len(vertical),
        correction_angle_deg=correction_angle if correction_applied else 0.0,
        corrected_orthophoto=str(output_path),
        correction_applied=correction_applied,
    )

    if generate_confidence_map:
        confidence_map_path = _build_confidence_map_path(output_path)
        stats.confidence_map_path = write_confidence_map(
            original_bgr=data,
            corrected_bgr=corrected_data,
            profile=profile,
            output_path=str(confidence_map_path),
        )
        stats.coverage_pct = compute_correction_coverage_pct(_load_confidence_map(confidence_map_path))

    logger.info("Saved corrected orthophoto to %s", output_path)
    return stats


def correct_orthophoto(
    input_path: str | Path,
    output_path: str | Path,
    angle_tolerance: float = config.LINE_ANGLE_TOLERANCE,
    generate_confidence_map: bool = config.GENERATE_CONFIDENCE_MAP,
) -> dict:
    """
    Backwards-compatible dict wrapper around ``run_orthophoto_correction``.
    """
    return run_orthophoto_correction(
        input_path=input_path,
        output_path=output_path,
        angle_tolerance=angle_tolerance,
        generate_confidence_map=generate_confidence_map,
    ).to_dict()
