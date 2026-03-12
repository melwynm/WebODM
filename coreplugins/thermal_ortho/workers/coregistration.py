import os

import numpy as np
from PIL import Image
from scipy import ndimage

from coreplugins.thermal_ortho.workers.radiometric import THERMAL_NODATA


def load_rgb_gray(rgb_path):
    with Image.open(rgb_path) as image:
        return np.array(image.convert('L'), dtype=np.float32)


def normalize_stem(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    upper = stem.upper()
    for suffix in ('_W', '_V', '_RGB', '_VIS', '_R', '_T', '_THERMAL'):
        if upper.endswith(suffix):
            stem = stem[:-len(suffix)]
            upper = stem.upper()
    return stem.rstrip('_-')


def match_rgb_thermal_pairs(rgb_paths, thermal_paths):
    rgb_map = {normalize_stem(path): path for path in rgb_paths}
    thermal_map = {normalize_stem(path): path for path in thermal_paths}

    pairs = []
    for key, rgb_path in rgb_map.items():
        if key in thermal_map:
            pairs.append((rgb_path, thermal_map[key]))

    if pairs:
        return pairs

    return list(zip(sorted(rgb_paths), sorted(thermal_paths)))


def _resize_to_shape(array, shape):
    zoom_y = shape[0] / float(array.shape[0])
    zoom_x = shape[1] / float(array.shape[1])
    resized = ndimage.zoom(array, (zoom_y, zoom_x), order=1)

    if resized.shape[0] != shape[0] or resized.shape[1] != shape[1]:
        corrected = np.full(shape, THERMAL_NODATA, dtype=resized.dtype)
        height = min(shape[0], resized.shape[0])
        width = min(shape[1], resized.shape[1])
        corrected[:height, :width] = resized[:height, :width]
        return corrected

    return resized


def _to_match_image(celsius):
    valid = np.isfinite(celsius) & (celsius > -9000.0)
    if not valid.any():
        return np.zeros_like(celsius, dtype=np.float32)

    minimum = float(np.percentile(celsius[valid], 2))
    maximum = float(np.percentile(celsius[valid], 98))
    if maximum <= minimum:
        return np.zeros_like(celsius, dtype=np.float32)

    clipped = np.clip((celsius - minimum) / (maximum - minimum), 0, 1)
    return clipped.astype(np.float32)


def _edge_image(image):
    blurred = ndimage.gaussian_filter(image, sigma=1.0)
    gx = ndimage.sobel(blurred, axis=1)
    gy = ndimage.sobel(blurred, axis=0)
    magnitude = np.hypot(gx, gy)
    max_value = float(magnitude.max())
    if max_value <= 0:
        return magnitude.astype(np.float32)
    return (magnitude / max_value).astype(np.float32)


def _estimate_translation(reference, moving):
    f_ref = np.fft.fft2(reference)
    f_mov = np.fft.fft2(moving)
    cross = f_ref * np.conj(f_mov)
    cross /= np.maximum(np.abs(cross), 1e-9)
    correlation = np.fft.ifft2(cross)
    maxima = np.unravel_index(np.argmax(np.abs(correlation)), correlation.shape)
    shifts = np.array(maxima, dtype=np.float32)

    for axis, size in enumerate(reference.shape):
        if shifts[axis] > size / 2.0:
            shifts[axis] -= size

    return shifts


def coregister_thermal_to_rgb(rgb_path, celsius_array):
    rgb_gray = load_rgb_gray(rgb_path)
    resized = _resize_to_shape(celsius_array, rgb_gray.shape)

    rgb_edges = _edge_image(rgb_gray)
    thermal_edges = _edge_image(_to_match_image(resized))
    shift = _estimate_translation(rgb_edges, thermal_edges)

    if np.any(np.abs(shift) > max(rgb_gray.shape) * 0.2):
        shift = np.array([0.0, 0.0], dtype=np.float32)

    aligned = ndimage.shift(resized, shift=shift, order=1, mode='constant', cval=THERMAL_NODATA)
    return aligned.astype(np.float32)
