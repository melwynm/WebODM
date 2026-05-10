import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from scipy.ndimage import affine_transform as nd_affine_transform
from scipy.ndimage import shift as nd_shift
from scipy.ndimage import sobel

from .common import (
    ALIGNMENT_ADVANCED_SEARCH_CONFIDENCE, ALIGNMENT_ROTATION_CANDIDATES,
    ALIGNMENT_SCALE_CANDIDATES, MIN_VALID_PIXELS, MonitoringError, correlation,
    intersect_bounds, normalize_values, percentile_range, preview_dimensions,
    read_preview, shift_in_meters, to_grayscale,
)

def estimate_alignment(reference_path, compare_path):
    with rasterio.open(reference_path) as reference_ds, rasterio.open(compare_path) as compare_ds:
        if reference_ds.crs is None or compare_ds.crs is None:
            raise MonitoringError("Monitoring requires georeferenced orthophotos")

        reference_bounds = tuple(reference_ds.bounds)
        compare_bounds_in_reference = transform_bounds(
            compare_ds.crs,
            reference_ds.crs,
            *compare_ds.bounds,
            densify_pts=21,
        )

        overlap_bounds = intersect_bounds(reference_bounds, compare_bounds_in_reference)
        if overlap_bounds is None:
            raise MonitoringError("The selected tasks do not overlap enough for monitoring")

        preview_width, preview_height = preview_dimensions(overlap_bounds)
        reference_preview, reference_valid = read_preview(
            reference_ds, overlap_bounds, reference_ds.crs, preview_width, preview_height
        )
        compare_preview, compare_valid = read_preview(
            compare_ds, overlap_bounds, reference_ds.crs, preview_width, preview_height
        )

        valid = reference_valid & compare_valid
        if int(valid.sum()) < MIN_VALID_PIXELS:
            raise MonitoringError("The overlapping area is too small to estimate a reliable alignment")

        reference_gray = to_grayscale(reference_preview)
        compare_gray = to_grayscale(compare_preview)

        reference_feature = make_alignment_feature(reference_gray, valid)
        compare_feature = make_alignment_feature(compare_gray, valid)

        similarity = estimate_similarity_alignment(
            reference_feature,
            compare_feature,
            reference_gray,
            compare_gray,
            compare_valid,
            reference_valid,
        )
        shifted_compare = similarity["aligned_gray"]
        shifted_valid = similarity["aligned_valid"]
        shift_y_px = similarity["shift_y_px"]
        shift_x_px = similarity["shift_x_px"]
        peak = similarity["phase_peak"]

        overlap_valid = reference_valid & shifted_valid
        if int(overlap_valid.sum()) < MIN_VALID_PIXELS:
            raise MonitoringError("The estimated alignment does not leave enough overlapping pixels")

        confidence = correlation(reference_gray, shifted_compare, overlap_valid)

        pixel_width = float(overlap_bounds[2] - overlap_bounds[0]) / float(preview_width)
        pixel_height = float(overlap_bounds[3] - overlap_bounds[1]) / float(preview_height)
        shift_x_units = shift_x_px * pixel_width
        shift_y_units = -shift_y_px * pixel_height

        center_x = (overlap_bounds[0] + overlap_bounds[2]) / 2.0
        center_y = (overlap_bounds[1] + overlap_bounds[3]) / 2.0
        meter_shift_x, meter_shift_y = shift_in_meters(
            reference_ds.crs,
            center_x,
            center_y,
            shift_x_units,
            shift_y_units,
        )

        warnings = []
        if confidence < 0.2:
            warnings.append(
                "Low alignment confidence. The datasets might have limited visual overlap or large scene changes."
            )

        return {
            "reference_crs": reference_ds.crs.to_string(),
            "transform_type": similarity["transform_type"],
            "overlap_bounds": list(map(float, overlap_bounds)),
            "preview_size": [preview_width, preview_height],
            "rotation_degrees": round(float(similarity["rotation_degrees"]), 4),
            "scale": round(float(similarity["scale"]), 6),
            "center_units": {
                "x": round(float(center_x), 6),
                "y": round(float(center_y), 6),
            },
            "shift_pixels": {
                "x": round(float(shift_x_px), 3),
                "y": round(float(shift_y_px), 3),
            },
            "shift_units": {
                "x": round(float(shift_x_units), 6),
                "y": round(float(shift_y_units), 6),
            },
            "shift_meters": {
                "x": round(float(meter_shift_x), 3),
                "y": round(float(meter_shift_y), 3),
            },
            "confidence": round(float(confidence), 4),
            "phase_peak": round(float(peak), 6),
            "reference_display_range": percentile_range(reference_preview, reference_valid),
            "compare_display_range": percentile_range(compare_preview, compare_valid),
            "warnings": warnings,
        }

def make_alignment_feature(gray, valid):
    feature = normalize_values(gray, valid)
    gx = sobel(feature, axis=1, mode="constant")
    gy = sobel(feature, axis=0, mode="constant")
    gradient = np.hypot(gx, gy)
    gradient[~valid] = 0.0

    window_y = np.hanning(gradient.shape[0]).astype(np.float32)
    window_x = np.hanning(gradient.shape[1]).astype(np.float32)
    feature_window = np.outer(window_y, window_x)
    return gradient * feature_window

def phase_correlation(reference, compare):
    spectrum = np.fft.fft2(reference) * np.conj(np.fft.fft2(compare))
    spectrum /= np.maximum(np.abs(spectrum), 1e-9)
    corr = np.abs(np.fft.ifft2(spectrum))

    peak_index = np.unravel_index(np.argmax(corr), corr.shape)
    peak_y, peak_x = peak_index
    peak_value = float(corr[peak_y, peak_x])

    shift_y = signed_shift(peak_y, corr.shape[0])
    shift_x = signed_shift(peak_x, corr.shape[1])

    shift_y += quadratic_offset(corr[:, peak_x], peak_y)
    shift_x += quadratic_offset(corr[peak_y, :], peak_x)

    return shift_y, shift_x, peak_value

def estimate_similarity_alignment(reference_feature, compare_feature, reference_gray, compare_gray, compare_valid, reference_valid):
    best = score_similarity_candidate(
        reference_feature,
        compare_feature,
        reference_gray,
        compare_gray,
        compare_valid,
        reference_valid,
        0.0,
        1.0,
    )
    if best["confidence"] >= ALIGNMENT_ADVANCED_SEARCH_CONFIDENCE:
        return best

    for rotation in ALIGNMENT_ROTATION_CANDIDATES:
        for scale in ALIGNMENT_SCALE_CANDIDATES:
            candidate = score_similarity_candidate(
                reference_feature,
                compare_feature,
                reference_gray,
                compare_gray,
                compare_valid,
                reference_valid,
                rotation,
                scale,
            )
            if candidate["score"] > best["score"]:
                best = candidate

    return best

def score_similarity_candidate(reference_feature, compare_feature, reference_gray, compare_gray, compare_valid, reference_valid, rotation, scale):
    transformed_feature = warp_preview_similarity(compare_feature, rotation, scale, order=1)
    shift_y, shift_x, peak = phase_correlation(reference_feature, transformed_feature)
    transformed_gray = warp_preview_similarity(compare_gray, rotation, scale, order=1)
    transformed_valid = warp_preview_similarity(compare_valid.astype(np.float32), rotation, scale, order=0) > 0.5

    aligned_gray = nd_shift(
        transformed_gray,
        shift=(shift_y, shift_x),
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    aligned_valid = nd_shift(
        transformed_valid.astype(np.float32),
        shift=(shift_y, shift_x),
        order=0,
        mode="constant",
        cval=0.0,
        prefilter=False,
    ) > 0.5
    valid = reference_valid & aligned_valid
    confidence = correlation(reference_gray, aligned_gray, valid)
    score = confidence - (abs(rotation) * 0.01) - (abs(scale - 1.0) * 1.0)

    return {
        "transform_type": "similarity" if abs(rotation) > 1e-6 or abs(scale - 1.0) > 1e-6 else "translation",
        "rotation_degrees": rotation,
        "scale": scale,
        "shift_y_px": shift_y,
        "shift_x_px": shift_x,
        "phase_peak": peak,
        "confidence": confidence,
        "score": score,
        "aligned_gray": aligned_gray,
        "aligned_valid": aligned_valid,
    }

def warp_preview_similarity(values, rotation_degrees, scale, order=1):
    if abs(rotation_degrees) < 1e-9 and abs(scale - 1.0) < 1e-9:
        return values.copy()

    height, width = values.shape
    center = np.array([(height - 1) / 2.0, (width - 1) / 2.0], dtype=np.float64)
    theta = np.deg2rad(rotation_degrees)
    cos_t = np.cos(theta) * scale
    sin_t = np.sin(theta) * scale
    forward = np.array(
        [
            [cos_t, -sin_t],
            [sin_t, cos_t],
        ],
        dtype=np.float64,
    )
    inverse = np.linalg.inv(forward)
    offset = center - inverse @ center
    return nd_affine_transform(
        values,
        inverse,
        offset=offset,
        output_shape=values.shape,
        order=order,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )

def signed_shift(value, size):
    if value > size / 2:
        return float(value - size)
    return float(value)

def quadratic_offset(values, index):
    prev_val = float(values[(index - 1) % len(values)])
    curr_val = float(values[index])
    next_val = float(values[(index + 1) % len(values)])
    denom = prev_val - 2.0 * curr_val + next_val
    if abs(denom) < 1e-9:
        return 0.0
    return 0.5 * (prev_val - next_val) / denom
