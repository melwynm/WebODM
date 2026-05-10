import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject
from rasterio.windows import Window, from_bounds, transform as window_transform
from scipy.ndimage import sobel

from .common import (
    CHANGE_ALPHA_GAIN, CHANGE_ALPHA_THRESHOLD, TERRAIN_ALPHA_GAIN, TERRAIN_ALPHA_THRESHOLD,
    MonitoringError, clamp_window, normalize_values, overlap_window_after_shift,
    percentile_range, preview_dimensions, read_preview, render_indexes, shifted_dataset_transform,
    to_grayscale,
)

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

def build_terrain_delta_overlay(reference_path, compare_path, alignment, output_path):
    with rasterio.open(reference_path) as reference_ds, rasterio.open(compare_path) as compare_ds:
        output_window, output_bounds = overlap_window_after_shift(reference_ds, compare_ds, alignment)
        if output_window.width <= 0 or output_window.height <= 0:
            raise MonitoringError("The terrain delta overlap area is empty")

        output_transform = window_transform(output_window, reference_ds.transform)
        output_width = int(output_window.width)
        output_height = int(output_window.height)
        shifted_transform = shifted_dataset_transform(compare_ds.transform, alignment)

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

        pixel_area = abs(float(output_transform.a) * float(output_transform.e))
        positive_volume = 0.0
        negative_volume = 0.0
        min_delta = None
        max_delta = None
        valid_pixels = 0

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

                    reference_nodata = reference_ds.nodata if reference_ds.nodata is not None else 0
                    compare_nodata = compare_ds.nodata if compare_ds.nodata is not None else 0

                    reference_block = reference_ds.read(
                        indexes=1,
                        window=ref_window,
                        out_shape=(int(window.height), int(window.width)),
                        boundless=True,
                        masked=True,
                        fill_value=reference_nodata,
                        resampling=Resampling.bilinear,
                    ).astype(np.float32)

                    with WarpedVRT(
                        compare_ds,
                        crs=reference_ds.crs,
                        transform=local_transform,
                        width=int(window.width),
                        height=int(window.height),
                        resampling=Resampling.bilinear,
                        nodata=compare_nodata,
                    ) as compare_vrt:
                        compare_block = compare_vrt.read(
                            indexes=1,
                            masked=True,
                            out_dtype="float32",
                        )

                    delta = np.ma.array(reference_block - compare_block)
                    valid = ~np.ma.getmaskarray(delta)
                    if valid.any():
                        values = delta.data[valid].astype(np.float64)
                        positive_volume += float(values[values > 0].sum() * pixel_area)
                        negative_volume += float(values[values < 0].sum() * pixel_area)
                        valid_pixels += int(valid.sum())
                        block_min = float(values.min())
                        block_max = float(values.max())
                        min_delta = block_min if min_delta is None else min(min_delta, block_min)
                        max_delta = block_max if max_delta is None else max(max_delta, block_max)

                    output_ds.write(build_terrain_delta_rgba(delta, valid), window=window)

        return {
            "bounds": list(map(float, output_bounds)),
            "stats": {
                "positive_volume": round(positive_volume, 3),
                "negative_volume": round(negative_volume, 3),
                "net_volume": round(positive_volume + negative_volume, 3),
                "min_delta": round(min_delta, 3) if min_delta is not None else None,
                "max_delta": round(max_delta, 3) if max_delta is not None else None,
                "valid_pixels": valid_pixels,
                "units": "source CRS units cubed",
            },
        }

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

def build_terrain_delta_rgba(delta, valid):
    values = np.ma.filled(delta, 0).astype(np.float32)
    magnitude = np.abs(values)
    alpha = np.clip((magnitude - TERRAIN_ALPHA_THRESHOLD) * TERRAIN_ALPHA_GAIN, 0, 220).astype(np.uint8)
    alpha[~valid] = 0

    positive = values >= 0
    rgba = np.zeros((4, values.shape[0], values.shape[1]), dtype=np.uint8)
    rgba[0][positive] = 46
    rgba[1][positive] = 160
    rgba[2][positive] = 67
    rgba[0][~positive] = 215
    rgba[1][~positive] = 48
    rgba[2][~positive] = 39
    rgba[3] = alpha
    return rgba
