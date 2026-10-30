import math
import os

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import Affine, from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds
from rio_tiler.colormap import cmap as color_maps

from coreplugins.thermal_ortho.workers.radiometric import THERMAL_NODATA


def _frame_bounds_in(frame, dst_crs):
    bounds = frame['bounds']
    return transform_bounds(
        frame.get('crs', 'EPSG:4326'), dst_crs,
        bounds['left'], bounds['bottom'], bounds['right'], bounds['top'],
    )


def choose_output_scale(aligned_thermals, ref_transform, ref_crs):
    """
    Thermal sensors are far coarser than the RGB camera, so the output grid is
    the reference grid downsampled to the native thermal ground resolution.
    Returns an integer factor >= 1.
    """
    ref_gsd = min(abs(ref_transform.a), abs(ref_transform.e))
    if ref_gsd <= 0:
        return 1

    gsds = []
    for frame in aligned_thermals:
        native_shape = frame.get('native_shape') or frame['array'].shape
        if not native_shape or native_shape[1] <= 0:
            continue
        left, _bottom, right, _top = _frame_bounds_in(frame, ref_crs)
        gsds.append((right - left) / float(native_shape[1]))

    if not gsds:
        return 1

    thermal_gsd = float(np.median(gsds))
    return max(1, int(math.floor(thermal_gsd / ref_gsd)))


def compute_temperature_stats(celsius_array):
    valid = np.isfinite(celsius_array) & (celsius_array > -9000.0)
    if not valid.any():
        return None

    values = celsius_array[valid]
    return {
        'min': round(float(values.min()), 3),
        'max': round(float(values.max()), 3),
        'mean': round(float(values.mean()), 3),
        'percentiles': [
            round(float(np.percentile(values, 2)), 3),
            round(float(np.percentile(values, 98)), 3),
        ],
        'count': int(values.size),
    }


def export_preview_png(celsius_array, output_path, stats=None):
    stats = stats or compute_temperature_stats(celsius_array)
    if stats is None:
        return

    valid = np.isfinite(celsius_array) & (celsius_array > -9000.0)
    vmin, vmax = stats['percentiles']
    normalized = np.zeros_like(celsius_array, dtype=np.float32)
    normalized[valid] = np.clip((celsius_array[valid] - vmin) / max(vmax - vmin, 1e-6), 0, 1)

    inferno = color_maps.get('inferno')
    lut = np.array([inferno[i] for i in range(256)], dtype=np.uint8)
    rgba = lut[(normalized * 255).astype(np.uint8)]
    rgba[~valid, 3] = 0

    Image.fromarray(rgba, 'RGBA').save(output_path)


def blend_thermal_orthomosaic(aligned_thermals, reference_orthophoto_path, output_path):
    with rasterio.open(reference_orthophoto_path) as reference:
        profile = reference.profile.copy()
        ref_transform = reference.transform
        ref_crs = reference.crs
        ref_height = reference.height
        ref_width = reference.width

    scale = choose_output_scale(aligned_thermals, ref_transform, ref_crs)
    out_transform = ref_transform * Affine.scale(scale)
    out_height = max(1, int(math.ceil(ref_height / float(scale))))
    out_width = max(1, int(math.ceil(ref_width / float(scale))))

    accumulator = np.zeros((out_height, out_width), dtype=np.float32)
    weights = np.zeros((out_height, out_width), dtype=np.float32)
    inverse = ~out_transform

    for frame in aligned_thermals:
        source = frame['array']
        bounds = frame['bounds']
        weight = float(frame.get('weight', 1.0))

        # Only the part of the output grid this frame can touch is allocated.
        left, bottom, right, top = _frame_bounds_in(frame, ref_crs)
        col_min, row_min = inverse * (left, top)
        col_max, row_max = inverse * (right, bottom)
        col_off = max(0, int(math.floor(min(col_min, col_max))) - 1)
        row_off = max(0, int(math.floor(min(row_min, row_max))) - 1)
        col_end = min(out_width, int(math.ceil(max(col_min, col_max))) + 1)
        row_end = min(out_height, int(math.ceil(max(row_min, row_max))) + 1)
        if col_end <= col_off or row_end <= row_off:
            continue

        destination = np.full((row_end - row_off, col_end - col_off), THERMAL_NODATA, dtype=np.float32)
        transform = from_bounds(bounds['left'], bounds['bottom'], bounds['right'], bounds['top'], source.shape[1], source.shape[0])
        reproject(
            source=source,
            destination=destination,
            src_transform=transform,
            src_crs=frame.get('crs', 'EPSG:4326'),
            dst_transform=out_transform * Affine.translation(col_off, row_off),
            dst_crs=ref_crs,
            src_nodata=THERMAL_NODATA,
            dst_nodata=THERMAL_NODATA,
            resampling=Resampling.bilinear,
        )

        valid = np.isfinite(destination) & (destination > -9000.0)
        window_acc = accumulator[row_off:row_end, col_off:col_end]
        window_weights = weights[row_off:row_end, col_off:col_end]
        window_acc[valid] += destination[valid] * weight
        window_weights[valid] += weight

    output = np.full((out_height, out_width), THERMAL_NODATA, dtype=np.float32)
    valid = weights > 0
    output[valid] = (accumulator[valid] / weights[valid]).astype(np.float32)

    profile.update({
        'driver': 'GTiff',
        'dtype': rasterio.float32,
        'count': 1,
        'width': out_width,
        'height': out_height,
        'transform': out_transform,
        'compress': 'deflate',
        'tiled': True,
        'blockxsize': 256,
        'blockysize': 256,
        'nodata': THERMAL_NODATA,
    })
    profile.pop('photometric', None)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(output, 1)
        dst.set_band_description(1, 'LWIR')
        dst.update_tags(1, DESCRIPTION='Temperature in Celsius', UNIT='Celsius')
        dst.update_tags(DESCRIPTION='Thermal orthophoto', UNITS='Celsius')

    stats = compute_temperature_stats(output)
    preview_path = os.path.join(os.path.dirname(output_path), 'thermal_preview.png')
    export_preview_png(output, preview_path, stats=stats)

    return {
        'output_path': output_path,
        'preview_path': preview_path,
        'stats': stats,
        'scale': scale,
        'shape': (out_height, out_width),
    }
