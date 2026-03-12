import os

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject
from rio_tiler.colormap import cmap as color_maps

from coreplugins.thermal_ortho.workers.radiometric import THERMAL_NODATA


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

    accumulator = np.zeros((ref_height, ref_width), dtype=np.float64)
    weights = np.zeros((ref_height, ref_width), dtype=np.float64)

    for frame in aligned_thermals:
        source = frame['array']
        bounds = frame['bounds']
        weight = float(frame.get('weight', 1.0))
        destination = np.full((ref_height, ref_width), THERMAL_NODATA, dtype=np.float32)

        transform = from_bounds(bounds['left'], bounds['bottom'], bounds['right'], bounds['top'], source.shape[1], source.shape[0])
        reproject(
            source=source,
            destination=destination,
            src_transform=transform,
            src_crs=frame.get('crs', 'EPSG:4326'),
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            src_nodata=THERMAL_NODATA,
            dst_nodata=THERMAL_NODATA,
            resampling=Resampling.bilinear,
        )

        valid = np.isfinite(destination) & (destination > -9000.0)
        accumulator[valid] += destination[valid] * weight
        weights[valid] += weight

    output = np.full((ref_height, ref_width), THERMAL_NODATA, dtype=np.float32)
    valid = weights > 0
    output[valid] = (accumulator[valid] / weights[valid]).astype(np.float32)

    profile.update({
        'driver': 'GTiff',
        'dtype': rasterio.float32,
        'count': 1,
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
    }
