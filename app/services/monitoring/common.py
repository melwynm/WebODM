import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as transform_points, transform_bounds
from rasterio.windows import Window, from_bounds, transform as window_transform

MONITORING_CACHE_VERSION = 3
PREVIEW_LONG_SIDE = 768
MIN_VALID_PIXELS = 4096
ALIGNMENT_ROTATION_CANDIDATES = (-3.0, -1.5, 0.0, 1.5, 3.0)
ALIGNMENT_SCALE_CANDIDATES = (0.985, 1.0, 1.015)
ALIGNMENT_ADVANCED_SEARCH_CONFIDENCE = 0.35
CHANGE_ALPHA_THRESHOLD = 18.0
CHANGE_ALPHA_GAIN = 3.4
TERRAIN_ALPHA_THRESHOLD = 0.05
TERRAIN_ALPHA_GAIN = 48.0


class MonitoringError(Exception):
    pass

def render_indexes(dataset):
    colorinterp = list(dataset.colorinterp)

    if not colorinterp:
        if dataset.count == 1:
            return (1,)
        return tuple(range(1, min(dataset.count, 3) + 1))

    if ColorInterp.red in colorinterp and ColorInterp.green in colorinterp and ColorInterp.blue in colorinterp:
        indexes = [
            colorinterp.index(ColorInterp.red) + 1,
            colorinterp.index(ColorInterp.green) + 1,
            colorinterp.index(ColorInterp.blue) + 1,
        ]
    elif dataset.count >= 3:
        indexes = [1, 2, 3]
    else:
        indexes = [1]

    if ColorInterp.alpha in colorinterp:
        indexes.append(colorinterp.index(ColorInterp.alpha) + 1)

    return tuple(indexes)

def shifted_dataset_transform(transform, alignment):
    return aligned_dataset_transform(transform, alignment)

def aligned_dataset_transform(transform, alignment):
    return alignment_similarity_transform(alignment) * transform

def overlap_window_after_shift(reference_ds, compare_ds, alignment):
    compare_bounds_in_reference = transform_bounds(
        compare_ds.crs,
        reference_ds.crs,
        *compare_ds.bounds,
        densify_pts=21,
    )

    shifted_bounds = aligned_bounds(compare_bounds_in_reference, alignment)

    overlap_bounds = intersect_bounds(tuple(reference_ds.bounds), shifted_bounds)
    if overlap_bounds is None:
        raise MonitoringError("The aligned comparison does not overlap the reference task")

    window = from_bounds(*overlap_bounds, transform=reference_ds.transform)
    window = clamp_window(window, reference_ds.width, reference_ds.height)
    snapped_bounds = list(rasterio.windows.bounds(window, reference_ds.transform))
    alignment["aligned_overlay_bounds"] = list(map(float, snapped_bounds))
    return window, snapped_bounds

def aligned_bounds(bounds, alignment):
    transform = alignment_similarity_transform(alignment)
    points = [
        transform * (bounds[0], bounds[1]),
        transform * (bounds[0], bounds[3]),
        transform * (bounds[2], bounds[1]),
        transform * (bounds[2], bounds[3]),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)

def alignment_similarity_transform(alignment):
    shift_x = alignment["shift_units"]["x"]
    shift_y = alignment["shift_units"]["y"]
    center = alignment.get("center_units") or {}
    center_x = float(center.get("x", 0.0))
    center_y = float(center.get("y", 0.0))
    rotation = float(alignment.get("rotation_degrees", 0.0))
    scale = float(alignment.get("scale", 1.0))
    return (
        Affine.translation(shift_x, shift_y)
        * Affine.translation(center_x, center_y)
        * Affine.rotation(rotation)
        * Affine.scale(scale, scale)
        * Affine.translation(-center_x, -center_y)
    )

def clamp_window(window, width, height):
    col_off = max(0, min(int(round(window.col_off)), width))
    row_off = max(0, min(int(round(window.row_off)), height))
    max_width = max(0, width - col_off)
    max_height = max(0, height - row_off)
    win_width = max(0, min(int(round(window.width)), max_width))
    win_height = max(0, min(int(round(window.height)), max_height))
    return Window(col_off, row_off, win_width, win_height)

def preview_dimensions(bounds):
    width = max(float(bounds[2] - bounds[0]), 1e-9)
    height = max(float(bounds[3] - bounds[1]), 1e-9)
    if width >= height:
        preview_width = PREVIEW_LONG_SIDE
        preview_height = max(256, int(round(PREVIEW_LONG_SIDE * (height / width))))
    else:
        preview_height = PREVIEW_LONG_SIDE
        preview_width = max(256, int(round(PREVIEW_LONG_SIDE * (width / height))))
    return preview_width, preview_height

def read_preview(dataset, bounds, dst_crs, width, height):
    indexes = render_indexes(dataset)[:3]
    dst_transform = rasterio.transform.from_bounds(*bounds, width, height)

    with WarpedVRT(
        dataset,
        crs=dst_crs,
        transform=dst_transform,
        width=width,
        height=height,
        resampling=Resampling.bilinear,
        nodata=0,
    ) as vrt:
        preview = vrt.read(indexes=indexes, masked=True, out_dtype="float32")

    valid = ~np.ma.getmaskarray(preview).any(axis=0)
    preview = np.ma.filled(preview, 0).astype(np.float32)
    return preview, valid

def to_grayscale(data):
    if data.ndim == 2:
        return data.astype(np.float32)
    if data.shape[0] == 1:
        return data[0].astype(np.float32)

    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    band_count = min(data.shape[0], 3)
    return np.tensordot(weights[:band_count], data[:band_count], axes=(0, 0)).astype(np.float32)

def normalize_values(values, valid, minmax=None):
    if minmax is None:
        vmin, vmax = percentile_range(values, valid)
    else:
        vmin, vmax = minmax

    if vmax <= vmin:
        vmax = vmin + 1.0

    normalized = (values.astype(np.float32) - float(vmin)) * (255.0 / float(vmax - vmin))
    normalized = np.clip(normalized, 0, 255)
    normalized[~valid] = 0.0
    return normalized

def percentile_range(values, valid):
    if values.ndim == 3:
        values = values[:, valid]
    else:
        values = values[valid]

    if values.size == 0:
        return [0.0, 255.0]

    p2 = float(np.nanpercentile(values, 2))
    p98 = float(np.nanpercentile(values, 98))
    if p98 <= p2:
        p98 = p2 + 1.0
    return [round(p2, 3), round(p98, 3)]

def correlation(reference, compare, valid):
    if int(valid.sum()) < 2:
        return 0.0

    ref = reference[valid].astype(np.float32)
    cmp = compare[valid].astype(np.float32)
    ref -= ref.mean()
    cmp -= cmp.mean()
    denom = np.sqrt((ref ** 2).sum() * (cmp ** 2).sum())
    if denom <= 1e-9:
        return 0.0
    return float(np.clip((ref * cmp).sum() / denom, -1.0, 1.0))

def shift_in_meters(crs, center_x, center_y, shift_x, shift_y):
    try:
        xs, ys = transform_points(
            crs,
            "EPSG:3857",
            [center_x, center_x + shift_x],
            [center_y, center_y + shift_y],
        )
        return xs[1] - xs[0], ys[1] - ys[0]
    except Exception:
        return shift_x, shift_y

def intersect_bounds(bounds_a, bounds_b):
    minx = max(bounds_a[0], bounds_b[0])
    miny = max(bounds_a[1], bounds_b[1])
    maxx = min(bounds_a[2], bounds_b[2])
    maxy = min(bounds_a[3], bounds_b[3])
    if maxx <= minx or maxy <= miny:
        return None
    return (minx, miny, maxx, maxy)

def _progress(progress_callback, status, progress):
    if callable(progress_callback):
        progress_callback(status, progress)
