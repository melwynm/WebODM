import json
import logging
import os
import shutil
from datetime import datetime

import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as transform_points, transform_bounds, reproject
from rasterio.windows import Window, from_bounds, transform as window_transform
from scipy.ndimage import shift as nd_shift
from scipy.ndimage import sobel

from webodm import settings

logger = logging.getLogger("app.logger")

MONITORING_CACHE_VERSION = 2
PREVIEW_LONG_SIDE = 2048
MIN_VALID_PIXELS = 4096
CHANGE_ALPHA_THRESHOLD = 18.0
CHANGE_ALPHA_GAIN = 3.4


class MonitoringError(Exception):
    pass


def monitoring_cache_dir(reference_task_id, compare_task_id):
    return os.path.join(
        settings.MEDIA_CACHE,
        "monitoring",
        str(reference_task_id),
        str(compare_task_id),
    )


def clear_monitoring_cache_for_task(task_id):
    monitoring_root = os.path.join(settings.MEDIA_CACHE, "monitoring")
    task_id = str(task_id)

    if not os.path.isdir(monitoring_root):
        return

    direct_reference_path = os.path.join(monitoring_root, task_id)
    if os.path.isdir(direct_reference_path):
        shutil.rmtree(direct_reference_path, ignore_errors=True)

    for reference_id in os.listdir(monitoring_root):
        reference_path = os.path.join(monitoring_root, reference_id)
        if not os.path.isdir(reference_path):
            continue

        compare_path = os.path.join(reference_path, task_id)
        if os.path.isdir(compare_path):
            shutil.rmtree(compare_path, ignore_errors=True)

        try:
            if reference_id != task_id and not os.listdir(reference_path):
                os.rmdir(reference_path)
        except OSError:
            continue


def monitoring_task_input(task):
    orthophoto_path = task.get_asset_download_path("orthophoto.tif")
    asset_mtime = None
    if os.path.isfile(orthophoto_path):
        asset_mtime = round(float(os.path.getmtime(orthophoto_path)), 6)

    return {
        "task_id": str(task.id),
        "task_name": task.name,
        "task_created_at": task.created_at.isoformat() if task.created_at else None,
        "asset_mtime": asset_mtime,
    }


def monitoring_inputs(reference_task, compare_task):
    return {
        "reference": monitoring_task_input(reference_task),
        "compare": monitoring_task_input(compare_task),
    }

def ensure_monitoring_products(reference_task, compare_task, progress_callback=None):
    cache_dir = monitoring_cache_dir(reference_task.id, compare_task.id)
    metadata_path = os.path.join(cache_dir, "metadata.json")
    current_inputs = monitoring_inputs(reference_task, compare_task)

    metadata = _load_cached_metadata(cache_dir, metadata_path, reference_task, compare_task)
    if metadata is not None:
        return _with_paths(cache_dir, metadata)

    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    os.makedirs(cache_dir, exist_ok=True)

    reference_path = reference_task.get_asset_download_path("orthophoto.tif")
    compare_path = compare_task.get_asset_download_path("orthophoto.tif")

    if not os.path.isfile(reference_path):
        raise MonitoringError("Reference task does not have an orthophoto")
    if not os.path.isfile(compare_path):
        raise MonitoringError("Comparison task does not have an orthophoto")

    _progress(progress_callback, "Estimating alignment", 0.15)
    alignment = estimate_alignment(reference_path, compare_path)

    aligned_path = os.path.join(cache_dir, "aligned_overlay.tif")
    change_path = os.path.join(cache_dir, "change_overlay.tif")

    _progress(progress_callback, "Generating aligned overlay", 0.45)
    aligned_info = build_aligned_overlay(reference_path, compare_path, alignment, aligned_path)

    _progress(progress_callback, "Generating change heatmap", 0.8)
    build_change_overlay(reference_path, aligned_path, alignment, change_path)

    metadata = {
        "version": MONITORING_CACHE_VERSION,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "inputs": current_inputs,
        "alignment": alignment,
        "aligned_overlay": {
            "path": os.path.basename(aligned_path),
            "bounds": aligned_info["bounds"],
            "rescale": aligned_info["rescale"],
        },
        "change_overlay": {
            "path": os.path.basename(change_path),
            "bounds": aligned_info["bounds"],
        },
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    _progress(progress_callback, "Monitoring comparison ready", 1.0)
    return _with_paths(cache_dir, metadata)


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

        shift_y_px, shift_x_px, peak = phase_correlation(reference_feature, compare_feature)

        shifted_compare = nd_shift(
            compare_gray,
            shift=(shift_y_px, shift_x_px),
            order=1,
            mode="constant",
            cval=0.0,
            prefilter=False,
        )
        shifted_valid = nd_shift(
            compare_valid.astype(np.float32),
            shift=(shift_y_px, shift_x_px),
            order=0,
            mode="constant",
            cval=0.0,
            prefilter=False,
        ) > 0.5

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
            "overlap_bounds": list(map(float, overlap_bounds)),
            "preview_size": [preview_width, preview_height],
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


def build_aligned_overlay(reference_path, compare_path, alignment, output_path):
    with rasterio.open(reference_path) as reference_ds, rasterio.open(compare_path) as compare_ds:
        output_window, output_bounds = overlap_window_after_shift(reference_ds, compare_ds, alignment)
        if output_window.width <= 0 or output_window.height <= 0:
            raise MonitoringError("The aligned overlap area is empty")

        output_transform = window_transform(output_window, reference_ds.transform)
        output_width = int(output_window.width)
        output_height = int(output_window.height)

        indexes = render_indexes(compare_ds)
        shifted_transform = shifted_dataset_transform(compare_ds.transform, alignment)

        profile = reference_ds.profile.copy()
        profile.update(
            driver="GTiff",
            width=output_width,
            height=output_height,
            transform=output_transform,
            crs=reference_ds.crs,
            count=len(indexes),
            dtype=compare_ds.dtypes[indexes[0] - 1],
            tiled=True,
            compress="DEFLATE",
            BIGTIFF="IF_SAFER",
            nodata=0,
        )

        with rasterio.open(output_path, "w", **profile) as output_ds:
            output_colorinterp = []
            for out_idx, src_idx in enumerate(indexes, start=1):
                is_alpha = compare_ds.colorinterp[src_idx - 1] == ColorInterp.alpha
                reproject(
                    source=rasterio.band(compare_ds, src_idx),
                    destination=rasterio.band(output_ds, out_idx),
                    src_transform=shifted_transform,
                    src_crs=compare_ds.crs,
                    dst_transform=output_transform,
                    dst_crs=reference_ds.crs,
                    src_nodata=compare_ds.nodata,
                    dst_nodata=0,
                    resampling=Resampling.nearest if is_alpha else Resampling.bilinear,
                )
                output_colorinterp.append(compare_ds.colorinterp[src_idx - 1])

            output_ds.colorinterp = tuple(output_colorinterp)

        with rasterio.open(output_path) as aligned_ds:
            preview_width, preview_height = preview_dimensions(tuple(output_bounds))
            preview, valid = read_preview(
                aligned_ds,
                tuple(output_bounds),
                aligned_ds.crs,
                preview_width,
                preview_height,
            )
            rescale = percentile_range(preview, valid)

        return {
            "bounds": list(map(float, output_bounds)),
            "rescale": rescale,
        }


def build_change_overlay(reference_path, aligned_path, alignment, output_path):
    with rasterio.open(reference_path) as reference_ds, rasterio.open(aligned_path) as aligned_ds:
        output_bounds = tuple(alignment["aligned_overlay_bounds"])
        output_window = from_bounds(*output_bounds, transform=reference_ds.transform)
        output_window = clamp_window(output_window, reference_ds.width, reference_ds.height)
        output_width = int(output_window.width)
        output_height = int(output_window.height)
        if output_width <= 0 or output_height <= 0:
            raise MonitoringError("The change overlay area is empty")

        output_transform = window_transform(output_window, reference_ds.transform)
        reference_indexes = render_indexes(reference_ds)[:3]
        aligned_indexes = render_indexes(aligned_ds)[:3]

        profile = reference_ds.profile.copy()
        profile.update(
            driver="GTiff",
            width=output_width,
            height=output_height,
            transform=output_transform,
            crs=reference_ds.crs,
            count=4,
            dtype="uint8",
            tiled=True,
            compress="DEFLATE",
            BIGTIFF="IF_SAFER",
            nodata=0,
        )

        reference_range = tuple(alignment["reference_display_range"])
        compare_range = tuple(alignment["compare_display_range"])

        block_size = 1024
        with rasterio.open(output_path, "w", **profile) as output_ds:
            output_ds.colorinterp = (
                ColorInterp.red,
                ColorInterp.green,
                ColorInterp.blue,
                ColorInterp.alpha,
            )

            for row in range(0, output_height, block_size):
                for col in range(0, output_width, block_size):
                    window = Window(
                        col,
                        row,
                        min(block_size, output_width - col),
                        min(block_size, output_height - row),
                    )
                    bounds = rasterio.windows.bounds(window, output_transform)
                    local_transform = window_transform(window, output_transform)
                    ref_window = from_bounds(*bounds, transform=reference_ds.transform)
                    ref_window = clamp_window(ref_window, reference_ds.width, reference_ds.height)

                    reference_block = reference_ds.read(
                        indexes=reference_indexes,
                        window=ref_window,
                        out_shape=(len(reference_indexes), int(window.height), int(window.width)),
                        boundless=True,
                        masked=True,
                        fill_value=0,
                        resampling=Resampling.bilinear,
                    ).astype(np.float32)

                    with WarpedVRT(
                        aligned_ds,
                        crs=reference_ds.crs,
                        transform=local_transform,
                        width=int(window.width),
                        height=int(window.height),
                        resampling=Resampling.bilinear,
                        nodata=0,
                    ) as compare_vrt:
                        compare_block = compare_vrt.read(
                            indexes=aligned_indexes,
                            masked=True,
                            out_dtype="float32",
                        )

                    rgba = build_change_rgba(
                        reference_block,
                        compare_block,
                        reference_range,
                        compare_range,
                    )
                    output_ds.write(rgba, window=window)


def render_layer_payload(reference_task, compare_task, metadata):
    aligned = metadata["aligned_overlay"]
    change = metadata["change_overlay"]
    alignment = metadata["alignment"]

    return {
        "reference_task": {
            "id": str(reference_task.id),
            "project": reference_task.project.id,
            "name": reference_task.name,
            "created_at": reference_task.created_at.isoformat(),
        },
        "compare_task": {
            "id": str(compare_task.id),
            "project": compare_task.project.id,
            "name": compare_task.name,
            "created_at": compare_task.created_at.isoformat(),
        },
        "timeline": {
            "generated_at": metadata.get("generated_at"),
            "reference_task_id": str(reference_task.id),
            "compare_task_id": str(compare_task.id),
        },
        "alignment": alignment,
        "layers": {
            "aligned_overlay": {
                "name": f"Aligned: {compare_task.name or compare_task.id}",
                "icon": "fa fa-layer-group fa-fw",
                "bounds": aligned["bounds"],
                "rescale": aligned["rescale"],
                "url": monitoring_tile_url(reference_task, compare_task, "aligned"),
                "maxzoom": 24,
                "side_by_side": True,
                "opacity": 1.0,
            },
            "change_overlay": {
                "name": f"Change Heatmap: {compare_task.name or compare_task.id}",
                "icon": "fa fa-fire fa-fw",
                "bounds": change["bounds"],
                "url": monitoring_tile_url(reference_task, compare_task, "change"),
                "maxzoom": 24,
                "side_by_side": False,
                "opacity": 0.8,
            },
        },
    }


def monitoring_tile_url(reference_task, compare_task, layer_type):
    return (
        f"/api/projects/{reference_task.project.id}/tasks/{reference_task.id}/"
        f"monitoring/{compare_task.id}/{layer_type}/tiles/{{z}}/{{x}}/{{y}}.png"
    )


def monitoring_layer_path(reference_task, compare_task, layer_type):
    cache_dir = monitoring_cache_dir(reference_task.id, compare_task.id)
    filename = {
        "aligned": "aligned_overlay.tif",
        "change": "change_overlay.tif",
    }.get(layer_type)
    if filename is None:
        raise MonitoringError("Invalid monitoring layer requested")

    path = os.path.join(cache_dir, filename)
    if not os.path.isfile(path):
        raise MonitoringError("Monitoring layer is not available yet")
    return path


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
    shift_x = alignment["shift_units"]["x"]
    shift_y = alignment["shift_units"]["y"]
    return Affine(transform.a, transform.b, transform.c + shift_x, transform.d, transform.e, transform.f + shift_y)


def overlap_window_after_shift(reference_ds, compare_ds, alignment):
    compare_bounds_in_reference = transform_bounds(
        compare_ds.crs,
        reference_ds.crs,
        *compare_ds.bounds,
        densify_pts=21,
    )

    shifted_bounds = (
        compare_bounds_in_reference[0] + alignment["shift_units"]["x"],
        compare_bounds_in_reference[1] + alignment["shift_units"]["y"],
        compare_bounds_in_reference[2] + alignment["shift_units"]["x"],
        compare_bounds_in_reference[3] + alignment["shift_units"]["y"],
    )

    overlap_bounds = intersect_bounds(tuple(reference_ds.bounds), shifted_bounds)
    if overlap_bounds is None:
        raise MonitoringError("The aligned comparison does not overlap the reference task")

    window = from_bounds(*overlap_bounds, transform=reference_ds.transform)
    window = clamp_window(window, reference_ds.width, reference_ds.height)
    snapped_bounds = list(rasterio.windows.bounds(window, reference_ds.transform))
    alignment["aligned_overlay_bounds"] = list(map(float, snapped_bounds))
    return window, snapped_bounds


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


def build_change_rgba(reference_block, compare_block, reference_range, compare_range):
    valid = (~np.ma.getmaskarray(reference_block).any(axis=0)) & (~np.ma.getmaskarray(compare_block).any(axis=0))
    reference_gray = to_grayscale(np.ma.filled(reference_block, 0))
    compare_gray = to_grayscale(np.ma.filled(compare_block, 0))

    reference_gray = normalize_values(reference_gray, valid, reference_range)
    compare_gray = normalize_values(compare_gray, valid, compare_range)

    edge_reference = np.hypot(sobel(reference_gray, axis=1), sobel(reference_gray, axis=0))
    edge_compare = np.hypot(sobel(compare_gray, axis=1), sobel(compare_gray, axis=0))
    difference = 0.65 * np.abs(reference_gray - compare_gray) + 0.35 * np.abs(edge_reference - edge_compare)
    difference[~valid] = 0.0

    alpha = np.clip((difference - CHANGE_ALPHA_THRESHOLD) * CHANGE_ALPHA_GAIN, 0, 255).astype(np.uint8)
    rgba = np.zeros((4, reference_gray.shape[0], reference_gray.shape[1]), dtype=np.uint8)
    rgba[0] = 255
    rgba[1] = 104
    rgba[2] = 24
    rgba[3] = alpha
    return rgba


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


def _load_cached_metadata(cache_dir, metadata_path, reference_task=None, compare_task=None):
    if not os.path.isfile(metadata_path):
        return None

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        if metadata.get("version") != MONITORING_CACHE_VERSION:
            return None

        aligned_path = os.path.join(cache_dir, metadata["aligned_overlay"]["path"])
        change_path = os.path.join(cache_dir, metadata["change_overlay"]["path"])
        if not os.path.isfile(aligned_path) or not os.path.isfile(change_path):
            return None

        if reference_task is not None and compare_task is not None:
            if metadata.get("inputs") != monitoring_inputs(reference_task, compare_task):
                return None

        return metadata
    except Exception as e:
        logger.warning("Cannot load monitoring cache %s: %s", metadata_path, e)
        return None


def _with_paths(cache_dir, metadata):
    payload = json.loads(json.dumps(metadata))
    payload["aligned_overlay"]["absolute_path"] = os.path.join(cache_dir, payload["aligned_overlay"]["path"])
    payload["change_overlay"]["absolute_path"] = os.path.join(cache_dir, payload["change_overlay"]["path"])
    return payload
